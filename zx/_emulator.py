#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

# TODO: Remove unused imports.
import numpy
import time
import types
import typing

from ._beeper import Beeper
from ._data import MachineSnapshot
from ._data import SoundFile
from ._device import Device
from ._device import EndOfFrame
from ._device import OutputFrame
from ._device import GetTapeLevel
from ._device import IsTapePlayerPaused
from ._device import IsTapePlayerStopped
from ._device import KeyStroke
from ._device import LoadTape
from ._device import PauseStateUpdated
from ._device import PauseUnpauseTape
from ._device import QuantumRun
from ._device import ReadPort
from ._device import EndOfFrame
from ._device import Dispatcher
from ._device import Destroy
from ._device import DeviceEvent
from ._device import GetEmulationPauseState
from ._device import GetEmulationTime
from ._device import LoadFile
from ._device import SaveSnapshot
from ._device import ToggleEmulationPause
from ._device import ToggleTapePause
from ._error import Error
from ._except import EmulationExit
from ._except import EmulatorException
from ._file import parse_file
from ._gui import ScreenWindow
from ._keyboard import Keyboard
from ._keyboard import KEYS
from ._machine import MachineState
from ._machine import RunEvents
from ._machine import Spectrum48
from ._playback import PlaybackPlayer
from ._rzx import RZXFile, make_rzx
from ._scr import _SCRSnapshot
from ._sound import SoundDevice
from ._tape import TapePlayer
from ._time import Time
from ._z80snapshot import Z80Snapshot
from ._zxb import ZXBasicCompilerProgram
from ._gamepad import Gamepad


# Stores information about the running code.
class Profile(object):
    _annots: dict[int, str] = dict()

    def add_instr_addr(self, addr: int) -> None:
        self._annots[addr] = 'instr'

    def __iter__(self) -> typing.Iterable[tuple[int, str]]:
        for addr in sorted(self._annots):
            yield addr, self._annots[addr]


# TODO: Eliminate this class. Move everything to Spectrum48.
class Emulator(Spectrum48):
    FRAME_SIZE = 48 + 256 + 48, 48 + 192 + 40

    _SPIN_V0P5_INFO = {'id': 'info',
                       'creator': b'SPIN 0.5            ',
                       'creator_major_version': 0,
                       'creator_minor_version': 5}

    devices: Dispatcher
    __profile: None | Profile
    __playback_player: None | PlaybackPlayer

    def __init__(self, *,
                 screen: Device | None = None,
                 keyboard: Device | None = None,
                 beeper: Device | None = None,
                 sound_device: Device | None = None,
                 headless: bool = False,
                 devices: list[Device] | None = None,
                 profile: Profile | None = None):
        super().__init__()

        self.frame_count = 0
        # TODO: Double-underscore or make public.
        self._emulation_time = Time()
        self.__headless = headless

        self.__events_to_signal = RunEvents.NO_EVENTS

        if devices is None:
            if keyboard is None:
                keyboard = Keyboard()
            if beeper is None:
                beeper = Beeper()

            devices = [self, TapePlayer(), keyboard, beeper]

            if not headless:
                if screen is None:
                    screen = ScreenWindow(self.FRAME_SIZE)
                if sound_device is None:
                    sound_device = SoundDevice()

                devices.extend([screen, sound_device, Gamepad()])

        dispatcher = Dispatcher(devices)

        self.devices = dispatcher  # TODO: Rename the field?

        self.set_on_input_callback(self.__on_input)

        self.__playback_player = None

        self.__profile = profile
        if self.__profile:
            self.set_breakpoints(0, 0x10000)

        self.__paused = False

    # TODO: Double-underscore or make public.
    def _save_snapshot_file(self, format: type[MachineSnapshot],
                            filename: str) -> None:
        with open(filename, 'wb') as f:
            f.write(format.encode(self))

    # TODO: Double-underscore or make public.
    def _is_tape_paused(self) -> bool:
        return bool(self.devices.notify(IsTapePlayerPaused()))

    def __pause_tape(self, is_paused: bool = True) -> None:
        self.devices.notify(PauseUnpauseTape(is_paused))

    def __unpause_tape(self) -> None:
        self.__pause_tape(is_paused=False)

    def _toggle_tape_pause(self) -> None:
        self.__pause_tape(not self._is_tape_paused())

    # TODO: Should we introduce TapeFile? Or PulseFile?
    def __load_tape_to_player(self, file: SoundFile) -> None:
        self.devices.notify(LoadTape(file))
        self.__pause_tape()

    # TODO: Do we still need?
    def __is_end_of_tape(self) -> bool:
        return bool(self.devices.notify(IsTapePlayerStopped()))

    def __translate_key_strokes(self, keys: typing.Iterable[int | str]) -> (
            typing.Iterator[str]):
        for key in keys:
            if isinstance(key, int):
                yield from str(key)
            else:
                yield key

    def generate_key_strokes(self, *keys: int | str) -> None:
        for key in self.__translate_key_strokes(keys):
            strokes = key.split('+')
            # print(strokes)

            for id in strokes:
                # print(id)
                self.devices.notify(KeyStroke(KEYS[id].ID, pressed=True))
                self.run(duration=0.1, fast_forward=True)

            for id in reversed(strokes):
                # print(id)
                self.devices.notify(KeyStroke(KEYS[id].ID, pressed=False))
                self.run(duration=0.1, fast_forward=True)

    def __on_input(self, addr: int) -> int:
        # Handle playbacks.
        if self.__playback_player:
            sample = None
            for sample in self.__playback_player.samples:
                break

            if sample == 'END_OF_FRAME':
                sample_i = 0  # TODO
                assert 0
                '''
                raise Error(
                    'Too few input samples at frame %d of %d. '
                    'Given %d, used %d.' % (
                        self.__playback_player.playback_frame_count,
                        len(self.__playback_player.playback_chunk['frames']),
                        len(self.__playback_player.samples), sample_i),
                    id='too_few_input_samples')
                '''

            # assert 0  # TODO
            # print('__on_input() returns %d' % sample)
            assert isinstance(sample, int)
            return sample

        # Scan keyboard.
        n = 0xbf
        n &= self.devices.notify(ReadPort(addr), 0xff)

        # TODO: Use the tick when the ear value is sampled
        #       instead of the tick of the beginning of the input
        #       cycle.
        if self.devices.notify(GetTapeLevel(self.ticks_since_int)):
            n |= 0x40

        END_OF_TAPE = RunEvents.END_OF_TAPE
        if END_OF_TAPE in self.__events_to_signal and self.__is_end_of_tape():
            self.raise_events(END_OF_TAPE)
            self.__events_to_signal &= ~END_OF_TAPE

        # print('0x%04x 0x%02x' % (addr, n))

        return n

    def __save_crash_rzx(self, player: PlaybackPlayer, state: MachineState,
                         chunk_i: int, frame_i: int) -> None:
        snapshot = Z80Snapshot.encode(state)

        assert 0  # TODO
        crash_recording = {
            'chunks': [
                player.find_recording_info_chunk(),
                {
                    'id': 'snapshot',
                    'image': snapshot,
                },
                {
                    'id': 'port_samples',
                    'first_tick': 0,
                    # TODO
                    # 'frames':
                    # recording['chunks'][chunk_i]['frames'][frame_i:],
                },
            ],
        }

        with open('__crash.z80', 'wb') as f:
            f.write(snapshot)

        with open('__crash.rzx', 'wb') as f:
            f.write(make_rzx(crash_recording))

    def __enter_playback_mode(self) -> None:
        # Interrupts are supposed to be controlled by the
        # recording.
        self.suppress_interrupts = True
        self.allow_int_after_ei = True
        # self.enable_trace()

    # TODO: Double-underscore or make public.
    def _quit_playback_mode(self) -> None:
        self.__playback_player = None

        self.suppress_interrupts = False
        self.allow_int_after_ei = False

    def __run_quantum(self, fast_forward: bool = False) -> None:
        fast_forward = fast_forward or self.__headless

        if self.__playback_player:
            creator_info = self.__playback_player.find_recording_info_chunk()

        if True:  # TODO
            self.devices.notify(QuantumRun())

            # TODO: For debug purposes.
            '''
            frame_count += 1
            if frame_count == -12820:
                frame_state = MachineState(bytes(self.image))
                self.__save_crash_rzx(player, frame_state, chunk_i, frame_i)
                assert 0

            if frame_count == -65952 - 1000:
                self.enable_trace()
            '''

            if self.paused:
                # Headless runs should never be paused.
                assert not self.__headless

                # Give the CPU some spare time if emulation is paused.
                time.sleep(1 / 50)
                return

            events = RunEvents(self._run())
            # TODO: print(events)

            if RunEvents.BREAKPOINT_HIT in events:
                self.on_breakpoint()

                if self.__profile:
                    pc = self.pc
                    self.__profile.add_instr_addr(pc)

                # SPIN v0.5 skips executing instructions
                # of the bytes-saving ROM procedure in
                # fast save mode.
                if (self.__playback_player and
                        self.__playback_player.samples and
                        creator_info == self._SPIN_V0P5_INFO and
                        self.pc == 0x04d4):
                    sp = self.sp
                    ret_addr = self.read16(sp)
                    self.sp = sp + 2
                    self.pc = ret_addr

            if RunEvents.END_OF_FRAME in events:
                # TODO: Can we translate the screen chunks into pixels
                # on the Python side using numpy?
                self.render_screen()
                self.devices.notify(EndOfFrame(
                    port_writes=numpy.frombuffer(self.get_port_writes(),
                                                 dtype=numpy.uint64)))
                self.devices.notify(OutputFrame(
                    pixels=self.get_frame_pixels(),
                    fast_forward=fast_forward))
                self.frame_count += 1
                self._emulation_time.advance(1 / 50)

            if (self.__playback_player and
                    RunEvents.FETCHES_LIMIT_HIT in events):
                # Some emulators, e.g., SPIN, may store an interrupt
                # point in the middle of a IX- or IY-prefixed
                # instruction, so we continue until such
                # instruction, if any, is completed.
                if self.iregp_kind != 'hl':
                    self.fetches_limit = 1
                    return

                # SPIN doesn't update the fetch counter if the last
                # instruction in frame is IN.
                if (self.__playback_player.samples and
                        creator_info == self._SPIN_V0P5_INFO and
                        self.__playback_player.playback_sample_i + 1 <
                        len(self.__playback_player.playback_sample_values)):
                    self.fetches_limit = 1
                    return

                sample = None
                for sample in self.__playback_player.samples:
                    break
                if sample != 'END_OF_FRAME':
                    assert 0  # TODO
                    '''
                    raise Error(
                        'Too many input samples at frame %d of %d. '
                        'Given %d, used %d.' % (
                            self.__playback_player.playback_frame_count,
                            len(self.__playback_player.
                                playback_chunk['frames']),
                            len(self.__playback_player.samples),
                            self.__playback_player.playback_sample_i + 1),
                        id='too_many_input_samples')
                    '''

                sample = None
                for sample in self.__playback_player.samples:
                    break
                if sample is None:
                    self.stop()
                    return

                assert sample == 'START_OF_FRAME'
                self.on_handle_active_int()

    def run(self, duration: None | float = None,
            fast_forward: bool = False) -> None:
        end_time = None
        if duration is not None:
            end_time = self._emulation_time.get() + duration

        while (end_time is None or
               self._emulation_time.get() < end_time):
            self.__run_quantum(fast_forward=fast_forward)

    def __load_input_recording(self, file: RZXFile) -> None:
        self.__playback_player = PlaybackPlayer(self, file)
        creator_info = self.__playback_player.find_recording_info_chunk()

        # SPIN v0.5 alters ROM to implement fast tape loading,
        # but that affects recorded RZX files.
        if creator_info == self._SPIN_V0P5_INFO:
            self.write(0x1f47, b'\xf5')

        # The bytes-saving ROM procedure needs special processing.
        self.set_breakpoint(0x04d4)

        # Process frames in order.
        sample = None
        for sample in self.__playback_player.samples:
            break
        assert sample == 'START_OF_FRAME'

    def reset_and_wait(self) -> None:
        self.pc = 0x0000
        self.run(duration=1.8, fast_forward=True)

    def __load_zx_basic_compiler_program(
            self, file: ZXBasicCompilerProgram) -> None:
        assert isinstance(file, ZXBasicCompilerProgram)

        self.reset_and_wait()

        # CLEAR <entry_point>
        entry_point = file.entry_point
        self.generate_key_strokes('X', entry_point, 'ENTER')

        self.write(entry_point, file.program_bytes)

        # RANDOMIZE USR <entry_point>
        self.generate_key_strokes('T', 'CS+SS', 'L', entry_point, 'ENTER')

        # assert 0, list(file)

    # TODO: Double-underscore or make public.
    def _load_file(self, filename: str) -> None:
        file = parse_file(filename)

        if isinstance(file, MachineSnapshot):
            self.install_snapshot(file)
        elif isinstance(file, RZXFile):
            self.__load_input_recording(file)
            self.__enter_playback_mode()
        elif isinstance(file, SoundFile):
            self.__load_tape_to_player(file)
        elif isinstance(file, ZXBasicCompilerProgram):
            self.__load_zx_basic_compiler_program(file)
        else:
            raise Error("Don't know how to load file %r." % filename)

    # TODO: Double-underscore or make public.
    def _run_file(self, filename: str, *, fast_forward: bool = False) -> None:
        self._load_file(filename)
        self.run(fast_forward=fast_forward)

    def load_tape(self, filename: str) -> None:
        tape = parse_file(filename)
        if not isinstance(tape, SoundFile):
            raise Error('%r does not seem to be a tape file.' % filename)

        # Let the initialization complete.
        self.reset_and_wait()

        # Type in 'LOAD ""'.
        self.generate_key_strokes('J', 'SS+P', 'SS+P', 'ENTER')

        # Load and run the tape.
        self.__load_tape_to_player(tape)
        self.__unpause_tape()

        # Wait till the end of the tape.
        self.__events_to_signal |= RunEvents.END_OF_TAPE
        while not self.__is_end_of_tape():
            self.__run_quantum(fast_forward=True)

    def __enter__(self) -> 'Emulator':
        return self

    def __exit__(self, xtype: None | type[BaseException],
                 value: None | BaseException,
                 traceback: None | types.TracebackType) -> None:
        self.devices.notify(Destroy())

    def stop(self) -> None:
        raise EmulationExit()

    @property
    def paused(self) -> bool:
        return self.__paused

    @paused.setter
    def paused(self, value: bool) -> None:
        self.__paused = value
        assert self.devices is not None
        self.devices.notify(PauseStateUpdated())

    def set_breakpoints(self, addr: int, size: int) -> None:
        self.mark_addrs(addr, size, self.__BREAKPOINT_MARK)

    def set_breakpoint(self, addr: int) -> None:
        self.set_breakpoints(addr, 1)

    def on_breakpoint(self) -> None:
        raise EmulatorException('Breakpoint triggered.')

    def on_event(self, event: DeviceEvent, devices: Dispatcher,
                 result: typing.Any) -> typing.Any:
        if isinstance(event, GetEmulationPauseState):
            return self.paused
        elif isinstance(event, GetEmulationTime):
            return self._emulation_time
        elif isinstance(event, KeyStroke):
            key = KEYS.get(event.id, None)
            if key:
                self.paused = False
                self._quit_playback_mode()
        elif isinstance(event, LoadFile):
            self._load_file(event.filename)
        elif isinstance(event, SaveSnapshot):
            self._save_snapshot_file(Z80Snapshot, event.filename)
        elif isinstance(event, ToggleEmulationPause):
            self.paused ^= True
        elif isinstance(event, ToggleTapePause):
            self._toggle_tape_pause()
        return result

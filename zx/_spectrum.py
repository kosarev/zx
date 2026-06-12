#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

# TODO: Remove unused imports.
import enum
import numpy
import types
import typing

from ._beeper import Beeper
from ._data import MachinePlayback
from ._data import MachineSnapshot
from ._data import MemoryBlock
from ._data import SoundFile
from ._data import Spectrum48
from ._data import SpectrumModel
from ._data import UnifiedPlayback
from ._data import UnifiedSnapshot
from ._device import Destroy
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import EmulatorReset
from ._device import EndOfFrame
from ._device import BreakpointHit
from ._device import FetchesLimitHit
from ._device import SetBreakpoint
from ._device import GetEmulationPauseState
from ._device import GetEmulationTime
from ._device import GetFramePixels
from ._device import InstallSnapshot
from ._device import IsTapePlayerPaused
from ._device import SetFetchesLimit
from ._device import StartPlayback
from ._device import StopPlayback
from ._device import IsTapePlayerStopped
from ._device import KeyStroke
from ._device import LoadFile
from ._device import LoadTape
from ._device import OutputFrame
from ._device import GetHoldState
from ._device import GetQuantumTickLimit
from ._device import NewPortWrites
from ._device import PauseStateUpdated
from ._device import PauseUnpauseTape
from ._device import QuantumRun
from ._device import ReadPort
from ._device import TimeAdvanced
from ._device import SaveSnapshot
from ._device import SetFastForward
from ._device import ToggleEmulationPause
from ._device import ToggleTapePause
from ._error import Error
from ._except import EmulationExit
from ._file import parse_file
from ._keyboard import Keyboard
from ._keyboard import KEYS
from ._playback import PlaybackPlayer
from ._playback import PlaybackRecorder
from ._rom import load_rom_image
from ._rzx import make_rzx
from ._screen import ScreenWindow
from ._scr import _SCRSnapshot
from ._sound import SDLSound
from ._spectrumbase import _SpectrumBase
from ._tape import TapePlayer
from ._time import Time
from ._z80snapshot import Z80Snapshot
from ._zxb import ZXBasicCompilerProgram


class RunEvents(enum.IntFlag):
    NO_EVENTS = 0
    END_OF_FRAME = 1 << 1
    FETCHES_LIMIT_HIT = 1 << 3
    BREAKPOINT_HIT = 1 << 4
    END_OF_TAPE = 1 << 5


class StateParser(object):
    def __init__(self, image: memoryview) -> None:
        self.__image = image
        self.__pos = 0

    @property
    def parsed_image(self) -> memoryview:
        return self.__image[:self.__pos]

    def read_bytes(self, size: int) -> memoryview:
        block = self.__image[self.__pos:self.__pos + size]
        self.__pos += size
        assert len(block) == size
        return block

    def parse8(self) -> memoryview:
        return self.read_bytes(1)

    def parse16(self) -> memoryview:
        return self.read_bytes(2)

    def parse32(self) -> memoryview:
        return self.read_bytes(4)


class Z80State(object):
    def __init__(self, image: memoryview) -> None:
        p = StateParser(image)
        self.__bc = p.parse16()
        self.__de = p.parse16()
        self.__hl = p.parse16()
        self.__af = p.parse16()
        self.__ix = p.parse16()
        self.__iy = p.parse16()
        self.__alt_bc = p.parse16()
        self.__alt_de = p.parse16()
        self.__alt_hl = p.parse16()
        self.__alt_af = p.parse16()
        self.__pc = p.parse16()
        self.__sp = p.parse16()
        self.__ir = p.parse16()
        self.__wz = p.parse16()
        self.__iff1 = p.parse8()
        self.__iff2 = p.parse8()
        self.__int_mode = p.parse8()
        self.__iregp_kind = p.parse8()

    # TODO: Use a mix-in from the z80 module to implement these?
    @property
    def bc(self) -> int:
        return int.from_bytes(self.__bc, 'little')

    @bc.setter
    def bc(self, value: int) -> None:
        self.__bc[:] = value.to_bytes(2, 'little')

    @property
    def de(self) -> int:
        return int.from_bytes(self.__de, 'little')

    @de.setter
    def de(self, value: int) -> None:
        self.__de[:] = value.to_bytes(2, 'little')

    @property
    def hl(self) -> int:
        return int.from_bytes(self.__hl, 'little')

    @hl.setter
    def hl(self, value: int) -> None:
        self.__hl[:] = value.to_bytes(2, 'little')

    @property
    def af(self) -> int:
        return int.from_bytes(self.__af, 'little')

    @af.setter
    def af(self, value: int) -> None:
        self.__af[:] = value.to_bytes(2, 'little')

    @property
    def a(self) -> int:
        return self.__af[1]

    @property
    def f(self) -> int:
        return self.__af[0]

    @property
    def ix(self) -> int:
        return int.from_bytes(self.__ix, 'little')

    @ix.setter
    def ix(self, value: int) -> None:
        self.__ix[:] = value.to_bytes(2, 'little')

    @property
    def iy(self) -> int:
        return int.from_bytes(self.__iy, 'little')

    @iy.setter
    def iy(self, value: int) -> None:
        self.__iy[:] = value.to_bytes(2, 'little')

    @property
    def alt_bc(self) -> int:
        return int.from_bytes(self.__alt_bc, 'little')

    @alt_bc.setter
    def alt_bc(self, value: int) -> None:
        self.__alt_bc[:] = value.to_bytes(2, 'little')

    @property
    def alt_de(self) -> int:
        return int.from_bytes(self.__alt_de, 'little')

    @alt_de.setter
    def alt_de(self, value: int) -> None:
        self.__alt_de[:] = value.to_bytes(2, 'little')

    @property
    def alt_hl(self) -> int:
        return int.from_bytes(self.__alt_hl, 'little')

    @alt_hl.setter
    def alt_hl(self, value: int) -> None:
        self.__alt_hl[:] = value.to_bytes(2, 'little')

    @property
    def alt_af(self) -> int:
        return int.from_bytes(self.__alt_af, 'little')

    @alt_af.setter
    def alt_af(self, value: int) -> None:
        self.__alt_af[:] = value.to_bytes(2, 'little')

    @property
    def alt_a(self) -> int:
        return self.__alt_af[1]

    @property
    def alt_f(self) -> int:
        return self.__alt_af[0]

    @property
    def pc(self) -> int:
        return int.from_bytes(self.__pc, 'little')

    @pc.setter
    def pc(self, value: int) -> None:
        self.__pc[:] = value.to_bytes(2, 'little')

    @property
    def sp(self) -> int:
        return int.from_bytes(self.__sp, 'little')

    @sp.setter
    def sp(self, value: int) -> None:
        self.__sp[:] = value.to_bytes(2, 'little')

    @property
    def ir(self) -> int:
        return int.from_bytes(self.__ir, 'little')

    @ir.setter
    def ir(self, value: int) -> None:
        self.__ir[:] = value.to_bytes(2, 'little')

    @property
    def i(self) -> int:
        return self.__ir[1]

    @property
    def r(self) -> int:
        return self.__ir[0]

    @property
    def iff1(self) -> int:
        return bool(self.__iff1[0])

    @iff1.setter
    def iff1(self, value: int) -> None:
        self.__iff1[0] = value

    @property
    def iff2(self) -> int:
        return bool(self.__iff2[0])

    @iff2.setter
    def iff2(self, value: int) -> None:
        self.__iff2[0] = value

    @property
    def int_mode(self) -> int:
        return self.__int_mode[0]

    @int_mode.setter
    def int_mode(self, value: int) -> None:
        self.__int_mode[0] = value

    @property
    def iregp_kind(self) -> str:
        n = self.__iregp_kind[0]
        return {0: 'hl', 1: 'ix', 2: 'iy'}[n]

    @iregp_kind.setter
    def iregp_kind(self, value: str) -> None:
        n = {'hl': 0, 'ix': 1, 'iy': 2}[value]
        self.__iregp_kind[0] = n


class SpectrumState(Z80State):
    __PAGE_SIZE = 0x4000

    __ROM_PAGE_IMAGE_OFFSETS = {0: 0 * __PAGE_SIZE,
                                1: 4 * __PAGE_SIZE}

    __RAM_PAGE_IMAGE_OFFSETS = {5: 1 * __PAGE_SIZE,
                                2: 2 * __PAGE_SIZE,
                                0: 3 * __PAGE_SIZE,
                                1: 5 * __PAGE_SIZE,
                                3: 6 * __PAGE_SIZE,
                                4: 7 * __PAGE_SIZE,
                                6: 8 * __PAGE_SIZE,
                                7: 9 * __PAGE_SIZE}

    def __init__(self, image: memoryview) -> None:
        p = StateParser(image)

        self.z80_image = p.read_bytes(32)
        Z80State.__init__(self, self.z80_image)

        self.__ticks_since_int = p.parse32()
        self.__tick_count = p.parse32()
        self.__fetches_to_stop = p.parse32()
        self.__ticks_to_stop = p.parse32()
        self.__events = p.parse32()
        self.__int_suppressed = p.parse8()
        self.__int_after_ei_allowed = p.parse8()
        self.__border_colour = p.parse8()
        self.__trace_enabled = p.parse8()
        self.__model = p.parse8()
        padding1 = p.parse8()
        padding2 = p.parse8()
        padding3 = p.parse8()

        self.__memory = p.read_bytes(10 * self.__PAGE_SIZE)

    @property
    def suppress_interrupts(self) -> bool:
        return bool(self.__int_suppressed[0])

    @suppress_interrupts.setter
    def suppress_interrupts(self, suppress: bool) -> None:
        self.__int_suppressed[0] = int(suppress)

    @property
    def allow_int_after_ei(self) -> bool:
        return bool(self.__int_after_ei_allowed[0])

    @allow_int_after_ei.setter
    def allow_int_after_ei(self, allow: bool) -> None:
        self.__int_after_ei_allowed[0] = int(allow)

    @property
    def fetches_limit(self) -> int:
        assert 0  # TODO
        # return self.get('fetches_to_stop')

    @fetches_limit.setter
    def fetches_limit(self, fetches_to_stop: int) -> None:
        self.__fetches_to_stop[:] = fetches_to_stop.to_bytes(4, 'little')

    # The number of ticks after which the run loop stops between
    # instructions (raising ticks_limit_hit), without ending the
    # frame. Null means no limit. Set per quantum to cap how far a
    # quantum advances, e.g. for sub-frame quanta at slow speeds.
    @property
    def ticks_limit(self) -> int:
        return int.from_bytes(self.__ticks_to_stop, 'little')

    @ticks_limit.setter
    def ticks_limit(self, ticks_to_stop: int) -> None:
        self.__ticks_to_stop[:] = ticks_to_stop.to_bytes(4, 'little')

    # TODO: Can we do without this?
    def get_events(self) -> int:
        return int.from_bytes(self.__events, 'little')

    # TODO: Can we do without this?
    def set_events(self, events: int) -> None:
        self.__events[:] = events.to_bytes(4, 'little')

    # TODO: Can we do without this?
    def raise_events(self, events: int) -> None:
        self.set_events(self.get_events() | events)

    @property
    def ticks_since_int(self) -> int:
        return int.from_bytes(self.__ticks_since_int, 'little')

    @ticks_since_int.setter
    def ticks_since_int(self, ticks: int) -> None:
        self.__ticks_since_int[:] = ticks.to_bytes(4, 'little')

    # The number of ticks since the machine creation, wrapping on
    # overflow. Free-running, so per-quantum counts are wrap-aware
    # deltas between readings.
    @property
    def tick_count(self) -> int:
        return int.from_bytes(self.__tick_count, 'little')

    @property
    def border_colour(self) -> int:
        return self.__border_colour[0]

    @border_colour.setter
    def border_colour(self, value: int) -> None:
        self.__border_colour[0] = value

    ''' TODO
    def enable_trace(self, enable=True):
        self.set('trace_enabled', int(enable))
    '''

    @property
    def model(self) -> type[SpectrumModel]:
        return SpectrumModel._MODELS_BY_CXX_CODES[self.__model[0]]

    @model.setter
    def model(self, model: type[SpectrumModel]) -> None:
        self.__model[0] = model._CXX_MODEL_CODE

    def read(self, addr: int, size: int) -> bytes:
        assert addr + size <= 0x10000  # TODO
        return bytes(self.__memory[addr:addr + size])

    def write(self, addr: int, block: bytes, *,
              rom_page: int | None = None,
              ram_page: int | None = None) -> None:
        assert addr + len(block) <= 0x10000  # TODO
        while block:
            next_page_addr = (addr // self.__PAGE_SIZE + 1) * self.__PAGE_SIZE
            chunk = block[:next_page_addr - addr]

            if addr < 0x4000:
                # TODO: Write to the current ROM otherwise.
                assert rom_page is not None
                offset = self.__ROM_PAGE_IMAGE_OFFSETS[rom_page]
            elif addr < 0xc000:
                offset = addr
            else:
                # TODO: Write to the current RAM otherwise.
                assert ram_page is not None
                offset = self.__RAM_PAGE_IMAGE_OFFSETS[ram_page]

            self.__memory[offset:offset + len(chunk)] = chunk

            addr += len(chunk)
            block = block[len(chunk):]

    def read8(self, addr: int) -> int:
        return self.read(addr, 1)[0]

    def read16(self, addr: int) -> int:
        return int.from_bytes(self.read(addr, 2), 'little')

    def to_snapshot(self) -> UnifiedSnapshot:
        # TODO: Store all fields.
        assert self.model is Spectrum48  # TODO: Support 128K.
        return UnifiedSnapshot(
            af=self.af, bc=self.bc, de=self.de, hl=self.hl,
            ix=self.ix, iy=self.iy,
            alt_af=self.alt_af, alt_bc=self.alt_bc,
            alt_de=self.alt_de, alt_hl=self.alt_hl,
            pc=self.pc, sp=self.sp, ir=self.ir,
            # TODO: wz=self.wz,
            iff1=self.iff1, iff2=self.iff2, int_mode=self.int_mode,
            iregp_kind=self.iregp_kind,
            memory_blocks=[MemoryBlock(addr=0x4000, rom_page=0, ram_page=0,
                                       data=self.__memory[0x4000:0x10000])],
            ticks_since_int=self.ticks_since_int,
            border_colour=self.border_colour)

    def install_snapshot(self, snapshot: MachineSnapshot) -> None:
        for field, value in snapshot.to_unified_snapshot():
            if field == 'memory_blocks':
                for block in value:
                    self.write(block.addr, block.data.data,
                               rom_page=block.rom_page,
                               ram_page=block.ram_page)
            else:
                setattr(self, field, value)


# Stores information about the running code.
class Profile(object):
    _annots: dict[int, str] = dict()

    def add_instr_addr(self, addr: int) -> None:
        self._annots[addr] = 'instr'

    def __iter__(self) -> typing.Iterable[tuple[int, str]]:
        for addr in sorted(self._annots):
            yield addr, self._annots[addr]


class Spectrum(_SpectrumBase, SpectrumState, Device):
    # Memory marks.
    __NO_MARKS = 0
    __BREAKPOINT_MARK = 1 << 0

    FRAME_SIZE = 48 + 256 + 48, 48 + 192 + 40

    devices: Dispatcher
    __profile: None | Profile
    __playback: UnifiedPlayback | None

    def __init__(self, *,
                 model: type[SpectrumModel] | None = None,
                 screen: Device | None = None,
                 keyboard: Device | None = None,
                 beeper: Device | None = None,
                 sound_device: Device | None = None,
                 headless: bool = False,
                 devices: list[Device] | None = None,
                 playback_player: PlaybackPlayer | None = None,
                 playback_recorder: PlaybackRecorder | None = None,
                 extra_devices: list[Device] | None = None,
                 profile: Profile | None = None):
        SpectrumState.__init__(self, self._get_state_view())
        Device.__init__(self)

        self.model = model if model is not None else Spectrum48

        self.__install_rom()

        self.frame_count = 0
        # TODO: Double-underscore or make public.
        self._emulation_time = Time()

        self.__events_to_signal = RunEvents.NO_EVENTS

        if devices is None:
            if keyboard is None:
                keyboard = Keyboard()
            if beeper is None:
                beeper = Beeper(self.model)

            devices = [self, TapePlayer(self.model), keyboard, beeper,
                       playback_player or PlaybackPlayer(),
                       playback_recorder or PlaybackRecorder()]

            if not headless:
                if screen is None:
                    screen = ScreenWindow(self.FRAME_SIZE)
                if sound_device is None:
                    sound_device = SDLSound(self.model)

                devices.extend([screen, sound_device])

            # The caller's extra devices come last — typically the
            # end-user tool layer adding environment-coupling agents
            # (e.g. a settings-persistence manager), kept out of the
            # default set so an API- or test-built emulator stays
            # hermetic.
            if extra_devices is not None:
                devices.extend(extra_devices)

        dispatcher = Dispatcher(devices)

        self.devices = dispatcher  # TODO: Rename the field?

        self.set_on_input_callback(self.__on_input)

        self.__port_reads = bytearray()

        self.__playback: UnifiedPlayback | None = None

        self.__profile = profile
        if self.__profile:
            self.set_breakpoints(0, 0x10000)

        self.__paused = False

    def reset(self) -> None:
        self.devices.notify(EmulatorReset())

    def __install_rom(self) -> None:
        PAGE_SIZE = 0x4000
        rom = load_rom_image(self.model._ROM_FILE_NAME)
        assert len(rom) >= PAGE_SIZE
        self.write(0x0000, rom[:PAGE_SIZE], rom_page=0)
        if len(rom) > PAGE_SIZE:
            assert len(rom) == 2 * PAGE_SIZE
            self.write(0x0000, rom[PAGE_SIZE:], rom_page=1)

    # TODO: Double-underscore or make public.
    def _save_snapshot_file(self, format: type[MachineSnapshot],
                            filename: str) -> None:
        with open(filename, 'wb') as f:
            f.write(format.from_snapshot(self.to_snapshot()).encode())

    # TODO: Double-underscore or make public.
    def _is_tape_paused(self) -> bool:
        tape_state = IsTapePlayerPaused()
        self.devices.notify(tape_state)
        return tape_state.paused

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
        tape_state = IsTapePlayerStopped()
        self.devices.notify(tape_state)
        return tape_state.stopped

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
        read_port = ReadPort(addr, self.tick_count)
        self.devices.notify(read_port)
        v = read_port.value
        self.__port_reads.append(v)

        END_OF_TAPE = RunEvents.END_OF_TAPE
        if END_OF_TAPE in self.__events_to_signal and self.__is_end_of_tape():
            self.raise_events(END_OF_TAPE)
            self.__events_to_signal &= ~END_OF_TAPE

        return v

    def __save_crash_rzx(self, player: PlaybackPlayer, state: SpectrumState,
                         chunk_i: int, frame_i: int) -> None:
        snapshot = Z80Snapshot.from_snapshot(state.to_snapshot()).encode()

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

    def __on_end_of_frame(self, devices: Dispatcher) -> None:
        # TODO: Can we translate the screen chunks into pixels
        # on the Python side using numpy?
        self.render_screen()

        if self.__playback is not None:
            self.on_handle_active_int()

        devices.notify(OutputFrame(
            pixels=self.get_frame_pixels(),
            port_reads=self.__port_reads))
        self.__port_reads.clear()

        self.frame_count += 1
        self._emulation_time.advance(1 / 50)

    def __enter_playback_mode(self, playback: UnifiedPlayback) -> None:
        self.__playback = playback
        # Interrupts are supposed to be controlled by the recording.
        self.suppress_interrupts = True
        self.allow_int_after_ei = True

    # TODO: Double-underscore or make public.
    def _quit_playback_mode(self) -> None:
        self.__playback = None
        self.suppress_interrupts = False
        self.allow_int_after_ei = False

    def __run_quantum(self) -> None:
        # Evaluate the hold once per quantum and broadcast the
        # result, so devices never re-query it.
        hold = GetHoldState()
        self.devices.notify(hold)

        self.devices.notify(QuantumRun(held=hold.held,
                                       wake_in=hold.wake_in))

        # TODO: For debug purposes.
        '''
        frame_count += 1
        if frame_count == -12820:
            frame_state = SpectrumState(bytes(self.image))
            self.__save_crash_rzx(player, frame_state, chunk_i, frame_i)
            assert 0

        if frame_count == -65952 - 1000:
            self.enable_trace()
        '''

        if hold.held:
            return

        # Cap how far this quantum advances, e.g. for sub-frame quanta
        # at slow speeds. With no device declaring a limit the quantum
        # runs to the frame end as before.
        limit = GetQuantumTickLimit()
        self.devices.notify(limit)
        self.ticks_limit = (0 if limit.stop_after_ticks is None
                            else limit.stop_after_ticks)

        events = RunEvents(self._run())

        now = self.tick_count

        writes = numpy.frombuffer(self.drain_port_writes(),
                                  dtype=numpy.uint64)
        if len(writes):
            self.devices.notify(NewPortWrites(now, writes))

        if RunEvents.BREAKPOINT_HIT in events:
            self.on_breakpoint()

        if self.__playback is not None:
            if RunEvents.FETCHES_LIMIT_HIT in events:
                self.devices.notify(FetchesLimitHit())
        elif RunEvents.END_OF_FRAME in events:
            self.devices.notify(EndOfFrame())

        # TimeAdvanced goes last: all facts about the elapsed span
        # of time are published by the time its dispatch completes.
        self.devices.notify(TimeAdvanced(now))

    def run(self, duration: None | float = None,
            fast_forward: bool = False) -> None:
        end_time = None
        if duration is not None:
            end_time = self._emulation_time.get() + duration

        if fast_forward:
            self.devices.notify(SetFastForward(True))
        try:
            while (end_time is None or
                   self._emulation_time.get() < end_time):
                self.__run_quantum()
        finally:
            if fast_forward:
                self.devices.notify(SetFastForward(False))

    def _load_input_recording(self, file: MachinePlayback) -> None:
        self.devices.notify(StartPlayback(file.to_unified_playback()))

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

        self.devices.notify(EmulatorReset())

        if isinstance(file, MachineSnapshot):
            self.install_snapshot(file)
        elif isinstance(file, MachinePlayback):
            self._load_input_recording(file)
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
        self.devices.notify(SetFastForward(True))
        try:
            while not self.__is_end_of_tape():
                self.__run_quantum()
        finally:
            self.devices.notify(SetFastForward(False))

    def __enter__(self) -> 'Spectrum':
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
        if self.__profile:
            self.__profile.add_instr_addr(self.pc)

        self.devices.notify(BreakpointHit())

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if isinstance(event, GetEmulationPauseState):
            event.paused |= self.paused
        elif isinstance(event, GetHoldState):
            # User pause holds with no deadline: only input can
            # change the answer.
            if self.paused:
                event.hold()
        elif isinstance(event, GetEmulationTime):
            event.time = self._emulation_time
        elif isinstance(event, GetFramePixels):
            # The core has already rendered the screen up to the
            # current tick on returning control, so this is current.
            event.pixels = self.get_frame_pixels()
        elif isinstance(event, KeyStroke):
            key = KEYS.get(event.id, None)
            if key:
                self.paused = False
                self.devices.notify(StopPlayback())
        elif isinstance(event, EndOfFrame):
            self.__on_end_of_frame(devices)
        elif isinstance(event, SetBreakpoint):
            self.set_breakpoint(event.addr)
        elif isinstance(event, InstallSnapshot):
            self.install_snapshot(event.snapshot)
        elif isinstance(event, SetFetchesLimit):
            self.fetches_limit = event.num_fetches
        elif isinstance(event, StartPlayback):
            self.__enter_playback_mode(event.playback)
        elif isinstance(event, StopPlayback):
            self._quit_playback_mode()
        elif isinstance(event, EmulatorReset):
            self.on_reset()
            self.__install_rom()
        elif isinstance(event, LoadFile):
            self._load_file(event.filename)
        elif isinstance(event, SaveSnapshot):
            self._save_snapshot_file(Z80Snapshot, event.filename)
        elif isinstance(event, ToggleEmulationPause):
            self.paused ^= True
        elif isinstance(event, ToggleTapePause):
            self._toggle_tape_pause()

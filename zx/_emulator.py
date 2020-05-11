#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.

import time
from ._data import MachineSnapshot
from ._data import SoundFile
from ._device import DeviceEvent
from ._error import Error
from ._file import parse_file
from ._gui import ScreenWindow
from ._keyboard import KEYS_INFO
from ._machine import Events
from ._machine import Spectrum48
from ._rzx import RZXFile
from ._tape import TapePlayer
from ._time import Time
from ._z80snapshot import Z80SnapshotFormat


# TODO: Rework to a time machine interface.
class PlaybackPlayer(object):
    def __init__(self, file):
        assert isinstance(file, RZXFile)
        self._recording = file._recording

    def find_recording_info_chunk(self):
        for chunk in self._recording['chunks']:
            if chunk['id'] == 'info':
                return chunk
        assert 0  # TODO

    def get_chunks(self):
        return self._recording['chunks']


class Emulator(object):
    _SPIN_V0P5_INFO = {'id': 'info',
                       'creator': b'SPIN 0.5            ',
                       'creator_major_version': 0,
                       'creator_minor_version': 5}

    def __init__(self, speed_factor=1.0, profile=None, devices=None):
        self._emulation_time = Time()
        self._speed_factor = speed_factor

        # TODO: Hide this flag. Its public use is deprecated.
        self.done = False

        self._is_paused_flag = False
        self._events_to_signal = Events.NO_EVENTS

        # Don't even create the window on full throttle.
        self._devices = devices if devices is not None else []
        if devices is None and self._speed_factor is not None:
            self._devices = [ScreenWindow(self)]

        self._machine = Spectrum48()

        # TODO: Move this to a separate class.
        self.keyboard_state = [0xff] * 8
        self._machine.set_on_input_callback(self._on_input)

        self.tape_player = TapePlayer()

        self.playback_player = None
        self.playback_samples = None

        self._profile = profile
        if self._profile:
            self._machine.set_breakpoints(0, 0x10000)

    def __enter__(self):
        return self

    def destroy(self):
        for device in self._devices:
            device.destroy()

    def __exit__(self, type, value, tb):
        self.destroy()

    def _is_paused(self):
        return self._is_paused_flag

    def _notify(self, id, *args):
        for device in self._devices:
            device._on_emulator_event(id, *args)

    def _pause(self, is_paused=True):
        self._is_paused_flag = is_paused
        self._notify(DeviceEvent.PAUSE_STATE_UPDATED)

    def _toggle_pause(self):
        self._pause(not self._is_paused())

    def _save_snapshot_file(self, format, filename):
        with open(filename, 'wb') as f:
            snapshot = format().make_snapshot(self._machine)
            # TODO: make_snapshot() shall always return a snapshot object.
            if issubclass(type(snapshot), MachineSnapshot):
                image = snapshot.get_file_image()
            else:
                image = snapshot
            f.write(image)

    def quit(self):
        self.done = True

    def _is_tape_paused(self):
        return self.tape_player.is_paused()

    def _pause_tape(self, is_paused=True):
        self.tape_player.pause(is_paused)
        self._notify(DeviceEvent.TAPE_STATE_UPDATED)

    def _unpause_tape(self):
        self._pause_tape(is_paused=False)

    def _toggle_tape_pause(self):
        self._pause_tape(not self._is_tape_paused())

    def _load_tape_to_player(self, file):
        self.tape_player.load_tape(file)
        self._pause_tape()

    def _is_end_of_tape(self):
        return self.tape_player.is_end()

    def _handle_key_stroke(self, key_info, pressed):
        # print(key_info['id'])
        addr_line = key_info['address_line']
        mask = 1 << key_info['port_bit']

        if pressed:
            self.keyboard_state[addr_line - 8] &= mask ^ 0xff
        else:
            self.keyboard_state[addr_line - 8] |= mask

    def _generate_key_strokes(self, *keys):
        for key in keys:
            strokes = key.split('+')

            # TODO: Refine handling of aliases.
            ALIASES = {'SS': 'SYMBOL SHIFT'}
            strokes = [ALIASES.get(s, s) for s in strokes]
            # print(strokes)

            for id in strokes:
                # print(id)
                self._handle_key_stroke(KEYS_INFO[id], pressed=True)
                self._run(0.03)

            for id in reversed(strokes):
                # print(id)
                self._handle_key_stroke(KEYS_INFO[id], pressed=False)
                self._run(0.03)

    def _on_input(self, addr):
        # Handle playbacks.
        if self.playback_samples:
            sample = None
            for sample in self.playback_samples:
                break

            if sample == 'END_OF_FRAME':
                raise Error(
                    'Too few input samples at frame %d of %d. '
                    'Given %d, used %d.' % (
                        self.playback_frame_count,
                        len(self.playback_chunk['frames']),
                        len(self.playback_samples), sample_i),
                    id='too_few_input_samples')

            # print('_on_input() returns %d' % sample)
            return sample

        # Scan keyboard.
        n = 0xbf
        addr ^= 0xffff
        if addr & (1 << 8):
            n &= self.keyboard_state[0]
        if addr & (1 << 9):
            n &= self.keyboard_state[1]
        if addr & (1 << 10):
            n &= self.keyboard_state[2]
        if addr & (1 << 11):
            n &= self.keyboard_state[3]
        if addr & (1 << 12):
            n &= self.keyboard_state[4]
        if addr & (1 << 13):
            n &= self.keyboard_state[5]
        if addr & (1 << 14):
            n &= self.keyboard_state[6]
        if addr & (1 << 15):
            n &= self.keyboard_state[7]

        # TODO: Use the tick when the ear value is sampled
        #       instead of the tick of the beginning of the input
        #       cycle.
        tick = self._machine.get_ticks_since_int()
        if self.tape_player.get_level_at_frame_tick(tick):
            n |= 0x40

        END_OF_TAPE = Events.END_OF_TAPE
        if END_OF_TAPE in self._events_to_signal and self._is_end_of_tape():
            self._machine.raise_events(END_OF_TAPE)
            self._events_to_signal &= ~END_OF_TAPE

        return n

    def _save_crash_rzx(self, player, state, chunk_i, frame_i):
        snapshot = Z80SnapshotFormat().make(state)

        crash_recording = {
            'id': 'input_recording',
            'chunks': [
                player.find_recording_info_chunk(),
                {
                    'id': 'snapshot',
                    'image': snapshot,
                },
                {
                    'id': 'port_samples',
                    'first_tick': 0,
                    'frames': recording['chunks'][chunk_i]['frames'][frame_i:],
                },
            ],
        }

        with open('__crash.z80', 'wb') as f:
            f.write(snapshot)

        with open('__crash.rzx', 'wb') as f:
            f.write(make_rzx(crash_recording))

    def _enter_playback_mode(self):
        # Interrupts are supposed to be controlled by the
        # recording.
        self._machine.suppress_int()
        self._machine.allow_int_after_ei()
        # self._machine.enable_trace()

    def _quit_playback_mode(self):
        self.playback_player = None
        self.playback_samples = None

        self._machine.suppress_int(False)
        self._machine.allow_int_after_ei(False)

    def _get_playback_samples(self):
        # TODO: Have a class describing playback state.
        self.playback_frame_count = 0
        self.playback_chunk = 0
        self.playback_sample_values = []
        self.playback_sample_i = 0

        frame_count = 0
        for chunk_i, chunk in enumerate(self.playback_player.get_chunks()):
            if isinstance(chunk, MachineSnapshot):
                self._machine.install_snapshot(chunk)
                continue

            if chunk['id'] != 'port_samples':
                continue

            self._machine.set_ticks_since_int(chunk['first_tick'])

            for frame_i, frame in enumerate(chunk['frames']):
                num_of_fetches, samples = frame
                # print(num_of_fetches, samples)

                self._machine.set_fetches_limit(num_of_fetches)
                # print(num_of_fetches, samples, flush=True)

                # print('START_OF_FRAME', flush=True)
                yield 'START_OF_FRAME'

                for sample_i, sample in enumerate(samples):
                    # print(self._machine.get_fetches_limit())
                    # fetch = num_of_fetches -
                    #         self._machine.get_fetches_limit()
                    # print('Input at fetch', fetch, 'of', num_of_fetches)
                    # TODO: print('read_port 0x%04x 0x%02x' % (addr, n),
                    #             flush=True)

                    # TODO: Have a class describing playback state.
                    self.playback_frame_count = frame_count
                    self.playback_chunk = chunk
                    self.playback_sample_values = samples
                    self.playback_sample_i = sample_i
                    # print(frame_count, chunk_i, frame_i, sample_i, sample,
                    #       flush=True)

                    yield sample

                # print('END_OF_FRAME', flush=True)
                yield 'END_OF_FRAME'

                frame_count += 1

    def _run_quantum(self):
        if self.playback_player:
            creator_info = self.playback_player.find_recording_info_chunk()

        if True:  # TODO
            self._notify(DeviceEvent.QUANTUM_RUN)

            # TODO: For debug purposes.
            '''
            frame_count += 1
            if frame_count == -12820:
                frame_state = self._machine.clone()
                self._save_crash_rzx(player, frame_state, chunk_i, frame_i)
                assert 0

            if frame_count == -65952 - 1000:
                self._machine.enable_trace()
            '''

            if self._is_paused():
                # Give the CPU some spare time.
                if self._speed_factor:
                    time.sleep((1 / 50) * self._speed_factor)
                return

            events = Events(self._machine.run())
            # TODO: print(events)

            if Events.BREAKPOINT_HIT in events:
                self.on_breakpoint()

                if self._profile:
                    pc = self._machine.get_pc()
                    self._profile.add_instr_addr(pc)

                # SPIN v0.5 skips executing instructions
                # of the bytes-saving ROM procedure in
                # fast save mode.
                if (self.playback_samples and
                        creator_info == self._SPIN_V0P5_INFO and
                        self._machine.get_pc() == 0x04d4):
                    sp = self._machine.get_sp()
                    ret_addr = self._machine.read16(sp)
                    self._machine.set_sp(sp + 2)
                    self._machine.set_pc(ret_addr)

            if Events.END_OF_FRAME in events:
                self._machine.render_screen()

                pixels = self._machine.get_frame_pixels()
                self._notify(DeviceEvent.SCREEN_UPDATED, pixels)

                self.tape_player.skip_rest_of_frame()
                self._emulation_time.advance(1 / 50)

                if self._speed_factor:
                    time.sleep((1 / 50) * self._speed_factor)

            if self.playback_samples and Events.FETCHES_LIMIT_HIT in events:
                # Some simulators, e.g., SPIN, may store an interrupt
                # point in the middle of a IX- or IY-prefixed
                # instruction, so we continue until such
                # instruction, if any, is completed.
                if self._machine.get_iregp_kind() != 'hl':
                    self._machine.set_fetches_limit(1)
                    return

                # SPIN doesn't update the fetch counter if the last
                # instruction in frame is IN.
                if (self.playback_samples and
                        creator_info == self._SPIN_V0P5_INFO and
                        self.playback_sample_i + 1 <
                        len(self.playback_sample_values)):
                    self._machine.set_fetches_limit(1)
                    return

                sample = None
                for sample in self.playback_samples:
                    break
                if sample != 'END_OF_FRAME':
                    raise Error(
                        'Too many input samples at frame %d of %d. '
                        'Given %d, used %d.' % (
                            self.playback_frame_count,
                            len(self.playback_chunk['frames']),
                            len(self.playback_samples),
                            self.playback_sample_i + 1),
                        id='too_many_input_samples')

                sample = None
                for sample in self.playback_samples:
                    break
                if sample is None:
                    self.done = True
                    return

                assert sample == 'START_OF_FRAME'
                self._machine.on_handle_active_int()

    def _run(self, duration):
        end_time = self._emulation_time.get() + duration
        while not self.done and self._emulation_time.get() < end_time:
            self._run_quantum()

    def main(self):
        while not self.done:
            self._run_quantum()

        self._quit_playback_mode()

    def _load_input_recording(self, file):
        self.playback_player = PlaybackPlayer(file)
        creator_info = self.playback_player.find_recording_info_chunk()

        # SPIN v0.5 alters ROM to implement fast tape loading,
        # but that affects recorded RZX files.
        if creator_info == self._SPIN_V0P5_INFO:
            self._machine.set_memory_block(0x1f47, b'\xf5')

        # The bytes-saving ROM procedure needs special processing.
        self._machine.set_breakpoint(0x04d4)

        # Process frames in order.
        self.playback_samples = self._get_playback_samples()
        sample = None
        for sample in self.playback_samples:
            break
        assert sample == 'START_OF_FRAME'

    def _load_file(self, filename):
        file = parse_file(filename)

        if isinstance(file, MachineSnapshot):
            self._machine.install_snapshot(file)
        elif isinstance(file, RZXFile):
            self._load_input_recording(file)
            self._enter_playback_mode()
        elif isinstance(file, SoundFile):
            self._load_tape_to_player(file)
        else:
            raise Error("Don't know how to load file %r." % filename)

    def _run_file(self, filename):
        self._load_file(filename)
        self.main()

    def load_tape(self, filename):
        tape = parse_file(filename)
        if not isinstance(tape, SoundFile):
            raise Error('%r does not seem to be a tape file.' % filename)

        # Let the initialization complete.
        self._machine.set_pc(0x0000)
        self._run(1.8)

        # Type in 'LOAD ""'.
        self._generate_key_strokes('J', 'SS+P', 'SS+P', 'ENTER')

        # Load and run the tape.
        self._load_tape_to_player(tape)
        self._unpause_tape()

        # Wait till the end of the tape.
        self._events_to_signal |= Events.END_OF_TAPE
        while not self.done and not self._is_end_of_tape():
            self._run_quantum()

    def set_breakpoint(self, addr):
        self._machine.set_breakpoint(addr)

    def on_breakpoint(self):
        pass

    def get_memory_view(self, addr, size):
        return self._machine.get_memory_block(addr, size)

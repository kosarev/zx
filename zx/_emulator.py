#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.

import cairo
import enum
import gi
import time
from ._data import MachineSnapshot
from ._data import SoundFile
from ._error import Error
from ._error import verbalize_error
from ._file import parse_file
from ._gui import draw_pause_notification
from ._gui import draw_tape_pause_notification
from ._gui import draw_tape_resume_notification
from ._gui import Notification
from ._gui import rgb
from ._keyboard import KEYS_INFO
from ._machine import Events
from ._machine import Spectrum48
from ._rzx import RZXFile
from ._tape import TapePlayer
from ._time import Time
from ._utils import div_ceil
from ._z80snapshot import Z80SnapshotFormat
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk  # nopep8


SCREENCAST = False


# TODO: A quick solution for making screencasts.
class Screencast(object):
    def __init__(self):
        self._counter = 0

    def on_draw(self, surface):
        if not SCREENCAST:
            return

        filename = '%05d.png' % self._counter
        surface.write_to_png(filename)
        self._counter += 1


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


class EmulatorEvent(enum.Enum):
    PAUSE_STATE_UPDATED = enum.auto()
    TAPE_STATE_UPDATED = enum.auto()
    RUN_QUANTUM = enum.auto()


class ScreenWindow(Gtk.Window):
    _SCREEN_AREA_BACKGROUND_COLOUR = rgb('#1e1e1e')

    def __init__(self, emulator):
        super().__init__()

        self._emulator = emulator

        self._KEY_HANDLERS = {
            'ESCAPE': self._emulator._quit,
            'F10': self._emulator._quit,
            'F1': self._show_help,
            'F2': self._save_snapshot,
            'F3': self._choose_and_load_file,
            'F6': self._emulator._toggle_tape_pause,
            'F11': self._toggle_fullscreen,
            'PAUSE': self._emulator._toggle_pause,
        }

        self._EMULATOR_EVENT_HANDLERS = {
            EmulatorEvent.PAUSE_STATE_UPDATED: self._on_pause_state_update,
            EmulatorEvent.TAPE_STATE_UPDATED: self._on_tape_state_update,
            EmulatorEvent.RUN_QUANTUM: self._on_run_quantum,
        }

        self._notification = Notification()
        self._screencast = Screencast()

        # TODO: Hide members like this.
        self.frame_width = 48 + 256 + 48
        self.frame_height = 48 + 192 + 40

        self.scale = 1 if SCREENCAST else 2

        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self._on_draw_area)
        self.add(self.area)

        self.set_title("ZX Spectrum Emulator")
        if SCREENCAST:
            width, height = 640, 390
        else:
            width, height = (self.frame_width * self.scale,
                             self.frame_height * self.scale)
        self.resize(width, height)
        minimum_size = self.frame_width // 4, self.frame_height // 4
        self.set_size_request(*minimum_size)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("delete-event", self._emulator._on_done)

        self.show_all()

        self.frame_size = self.frame_width * self.frame_height
        self.frame = cairo.ImageSurface(cairo.FORMAT_RGB24,
                                        self.frame_width, self.frame_height)
        self.frame_data = self.frame.get_data()

        self.pattern = cairo.SurfacePattern(self.frame)
        if not SCREENCAST:
            self.pattern.set_filter(cairo.FILTER_NEAREST)

        self.keys = {'RETURN': KEYS_INFO['ENTER'],
                     'ALT_L': KEYS_INFO['CAPS SHIFT'],
                     'SHIFT_L': KEYS_INFO['CAPS SHIFT'],
                     'ALT_R': KEYS_INFO['SYMBOL SHIFT'],
                     'SHIFT_R': KEYS_INFO['SYMBOL SHIFT'],
                     'SPACE': KEYS_INFO['BREAK SPACE']}
        for id in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                   'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
                   'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T',
                   'U', 'V', 'W', 'X', 'Y', 'Z']:
            self.keys[id] = KEYS_INFO[id]

        self.connect('key-press-event', self._on_key_press)
        self.connect('key-release-event', self._on_key_release)
        self.connect('button-press-event', self._on_click)
        self.connect('window-state-event', self._on_window_state_event)

    def _on_draw_area(self, widget, context):
        window_size = self.get_size()
        window_width, window_height = window_size
        width = min(window_width,
                    div_ceil(window_height * self.frame_width,
                             self.frame_height))
        height = min(window_height,
                     div_ceil(window_width * self.frame_height,
                              self.frame_width))

        # Draw the background.
        context.save()
        context.rectangle(0, 0, window_width, window_height)
        context.set_source_rgba(*self._SCREEN_AREA_BACKGROUND_COLOUR)
        context.fill()

        # Draw the emulated screen.
        context.save()
        context.translate((window_width - width) // 2,
                          (window_height - height) // 2)
        context.scale(width / self.frame_width, height / self.frame_height)
        context.set_source(self.pattern)
        context.paint()
        context.restore()

        self._notification.draw(window_size, (width, height), context)
        context.restore()

        self._screencast.on_draw(context.get_group_target())

    def update_frame(self, pixels):
        self.frame_data[:] = pixels
        self.area.queue_draw()

    def _show_help(self):
        KEYS = [
            ('F1', 'Show help.'),
            ('F2', 'Save snapshot.'),
            ('F3', 'Load snapshot or tape file.'),
            ('F6', 'Pause/resume tape.'),
            ('F10', 'Quit.'),
            ('F11', 'Fullscreen/windowed mode.'),
            ('PAUSE', 'Pause/resume emulation.'),
        ]

        for entry in KEYS:
            print('%7s  %s' % entry)

    def _save_snapshot(self):
        # TODO: Add file filters.
        dialog = Gtk.FileChooserDialog(
            'Save snapshot', self,
            Gtk.FileChooserAction.SAVE,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
        dialog.set_do_overwrite_confirmation(True)
        if dialog.run() == Gtk.ResponseType.OK:
            try:
                self._emulator._save_snapshot_file(Z80SnapshotFormat,
                                                   dialog.get_filename())
            except (Error, IOError) as e:
                self._error_box('File error', verbalize_error(e))

        dialog.destroy()

    def _error_box(self, title, message):
        dialog = Gtk.MessageDialog(
            self, 0, Gtk.MessageType.ERROR,
            Gtk.ButtonsType.OK, title)
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def _choose_and_load_file(self):
        # TODO: Add file filters.
        dialog = Gtk.FileChooserDialog(
            'Load file', self,
            Gtk.FileChooserAction.OPEN,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_OPEN, Gtk.ResponseType.OK))

        if dialog.run() == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            try:
                self._emulator._load_file(filename)
            except BaseException as e:
                self._error_box('File error', verbalize_error(e))

        dialog.destroy()

    def _toggle_fullscreen(self):
        if self._is_fullscreen:
            self.unfullscreen()
        else:
            self.fullscreen()

    def _on_key(self, event, pressed):
        key_id = Gdk.keyval_name(event.keyval).upper()
        # print(key_id)

        if pressed and key_id in self._KEY_HANDLERS:
            self._KEY_HANDLERS[key_id]()

        key_info = self.keys.get(key_id, None)
        if key_info:
            self._emulator._pause(False)
            self._emulator._quit_playback_mode()
            self._emulator._handle_key_stroke(key_info, pressed)

    def _on_key_press(self, widget, event):
        self._on_key(event, pressed=True)

    def _on_key_release(self, widget, event):
        self._on_key(event, pressed=False)

    def _on_click(self, widget, event):
        if event.type == Gdk.EventType.BUTTON_PRESS:
            self._emulator._toggle_pause()
            return True
        elif event.type == Gdk.EventType._2BUTTON_PRESS:
            self._toggle_fullscreen()

    def _on_window_state_event(self, widget, event):
        state = event.new_window_state
        self._is_fullscreen = bool(state & Gdk.WindowState.FULLSCREEN)

    def _on_emulator_event(self, id):
        self._EMULATOR_EVENT_HANDLERS[id]()

    def _on_pause_state_update(self):
        if self._emulator._is_paused():
            self._notification.set(draw_pause_notification,
                                   self._emulator._emulation_time)
        else:
            self._notification.clear()

    def _on_tape_state_update(self):
        tape_paused = self._emulator._is_tape_paused()
        draw = (draw_tape_pause_notification if tape_paused
                else draw_tape_resume_notification)
        tape_time = self._emulator.tape_player.get_time()
        self._notification.set(draw, tape_time)

    def _on_run_quantum(self):
        while Gtk.events_pending():
            Gtk.main_iteration()

        self.area.queue_draw()


class Emulator(object):
    _SPIN_V0P5_INFO = {'id': 'info',
                       'creator': b'SPIN 0.5            ',
                       'creator_major_version': 0,
                       'creator_minor_version': 5}

    def __init__(self, speed_factor=1.0, profile=None):
        self._emulation_time = Time()
        self._speed_factor = speed_factor

        self.done = False
        self._is_paused_flag = False
        self._events_to_signal = Events.NO_EVENTS

        # Don't even create the window on full throttle.
        self._screen_window = (ScreenWindow(self)
                               if self._speed_factor is not None else None)

        self._emulator = Spectrum48()
        self.processor_state = self._emulator  # TODO: Eliminate.

        self.keyboard_state = [0xff] * 8
        self._emulator.set_on_input_callback(self._on_input)

        self.tape_player = TapePlayer()

        self.playback_player = None
        self.playback_samples = None

        self._profile = profile
        if self._profile:
            self._emulator.set_breakpoints(0, 0x10000)

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        if self._screen_window:
            self._screen_window.destroy()

    def _on_done(self, widget, context):
        self._quit()

    def _is_paused(self):
        return self._is_paused_flag

    def _notify(self, id):
        if self._screen_window:
            self._screen_window._on_emulator_event(id)

    def _pause(self, is_paused=True):
        self._is_paused_flag = is_paused
        self._notify(EmulatorEvent.PAUSE_STATE_UPDATED)

    def _toggle_pause(self):
        self._pause(not self._is_paused())

    def _save_snapshot_file(self, format, filename):
        with open(filename, 'wb') as f:
            snapshot = format().make_snapshot(self._emulator)
            # TODO: make_snapshot() shall always return a snapshot object.
            if issubclass(type(snapshot), MachineSnapshot):
                image = snapshot.get_file_image()
            else:
                image = snapshot
            f.write(image)

    # TODO: Make this a public function and hide the 'done' flag.
    def _quit(self):
        self.done = True

    def _is_tape_paused(self):
        return self.tape_player.is_paused()

    def _pause_tape(self, is_paused=True):
        self.tape_player.pause(is_paused)
        self._notify(EmulatorEvent.TAPE_STATE_UPDATED)

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
        tick = self._emulator.get_ticks_since_int()
        if self.tape_player.get_level_at_frame_tick(tick):
            n |= 0x40

        END_OF_TAPE = Events.END_OF_TAPE
        if END_OF_TAPE in self._events_to_signal and self._is_end_of_tape():
            self._emulator.raise_events(END_OF_TAPE)
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
        self._emulator.suppress_int()
        self._emulator.allow_int_after_ei()
        # self._emulator.enable_trace()

    def _quit_playback_mode(self):
        self.playback_player = None
        self.playback_samples = None

        self._emulator.suppress_int(False)
        self._emulator.allow_int_after_ei(False)

    def _get_playback_samples(self):
        # TODO: Have a class describing playback state.
        self.playback_frame_count = 0
        self.playback_chunk = 0
        self.playback_sample_values = []
        self.playback_sample_i = 0

        frame_count = 0
        for chunk_i, chunk in enumerate(self.playback_player.get_chunks()):
            if isinstance(chunk, MachineSnapshot):
                self._emulator.install_snapshot(chunk)
                continue

            if chunk['id'] != 'port_samples':
                continue

            self._emulator.set_ticks_since_int(chunk['first_tick'])

            for frame_i, frame in enumerate(chunk['frames']):
                num_of_fetches, samples = frame
                # print(num_of_fetches, samples)

                self._emulator.set_fetches_limit(num_of_fetches)
                # print(num_of_fetches, samples, flush=True)

                # print('START_OF_FRAME', flush=True)
                yield 'START_OF_FRAME'

                for sample_i, sample in enumerate(samples):
                    # print(self._emulator.get_fetches_limit())
                    # fetch = num_of_fetches -
                    #         self._emulator.get_fetches_limit()
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
            self._notify(EmulatorEvent.RUN_QUANTUM)

            # TODO: For debug purposes.
            '''
            frame_count += 1
            if frame_count == -12820:
                frame_state = self._emulator.clone()
                self._save_crash_rzx(player, frame_state, chunk_i, frame_i)
                assert 0

            if frame_count == -65952 - 1000:
                self._emulator.enable_trace()
            '''

            if self._is_paused():
                # Give the CPU some spare time.
                if self._speed_factor:
                    time.sleep((1 / 50) * self._speed_factor)
                return

            events = Events(self._emulator.run())
            # TODO: print(events)

            if Events.BREAKPOINT_HIT in events:
                self.on_breakpoint()

                if self._profile:
                    pc = self._emulator.get_pc()
                    self._profile.add_instr_addr(pc)

                # SPIN v0.5 skips executing instructions
                # of the bytes-saving ROM procedure in
                # fast save mode.
                if (self.playback_samples and
                        creator_info == self._SPIN_V0P5_INFO and
                        self._emulator.get_pc() == 0x04d4):
                    sp = self._emulator.get_sp()
                    ret_addr = self._emulator.read16(sp)
                    self._emulator.set_sp(sp + 2)
                    self._emulator.set_pc(ret_addr)

            if Events.END_OF_FRAME in events:
                if self._screen_window:
                    self._emulator.render_screen()

                    pixels = self._emulator.get_frame_pixels()
                    self._screen_window.update_frame(pixels)

                self.tape_player.skip_rest_of_frame()
                self._emulation_time.advance(1 / 50)

                if self._speed_factor:
                    time.sleep((1 / 50) * self._speed_factor)

            if self.playback_samples and Events.FETCHES_LIMIT_HIT in events:
                # Some simulators, e.g., SPIN, may store an interrupt
                # point in the middle of a IX- or IY-prefixed
                # instruction, so we continue until such
                # instruction, if any, is completed.
                if self._emulator.get_iregp_kind() != 'hl':
                    self._emulator.set_fetches_limit(1)
                    return

                # SPIN doesn't update the fetch counter if the last
                # instruction in frame is IN.
                if (self.playback_samples and
                        creator_info == self._SPIN_V0P5_INFO and
                        self.playback_sample_i + 1 <
                        len(self.playback_sample_values)):
                    self._emulator.set_fetches_limit(1)
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
                self._emulator.on_handle_active_int()

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
            self._emulator.set_memory_block(0x1f47, b'\xf5')

        # The bytes-saving ROM procedure needs special processing.
        self._emulator.set_breakpoint(0x04d4)

        # Process frames in order.
        self.playback_samples = self._get_playback_samples()
        sample = None
        for sample in self.playback_samples:
            break
        assert sample == 'START_OF_FRAME'

    def _load_file(self, filename):
        file = parse_file(filename)

        if isinstance(file, MachineSnapshot):
            self._emulator.install_snapshot(file)
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
        self._emulator.set_pc(0x0000)
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
        self._emulator.set_breakpoint(addr)

    def on_breakpoint(self):
        pass

    def get_memory_view(self, addr, size):
        return self._emulator.get_memory_block(addr, size)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


import cairo, gi, os, sys, time, collections
import zx, zx._gui as _gui
from zx._gui import rgb
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk


SCREENCAST = False


# TODO: Move to the z80 project.
class ProcessorSnapshot(zx.Data):
    pass


class SnapshotsFormat(zx.FileFormat):
    pass


class RZXFile(zx.Data):
    def __init__(self, recording):
        self._recording = recording


class RZXFileFormat(zx.FileFormat):
    def parse(self, image):
        recording = zx.parse_rzx(image)
        return RZXFile(recording)


def get_timestamp():
    # TODO: We can use this since Python 3.7.
    # return time.time_ns() / (10 ** 9)
    return time.time()


def get_elapsed_time(timestamp):
    return get_timestamp() - timestamp


def detect_file_format(image, filename_extension):
    KNOWN_FORMATS = [
        ('.rzx', b'RZX!', RZXFileFormat),
        ('.scr', None, zx._SCRFileFormat),
        ('.tap', None, zx.TAPFileFormat),
        ('.tzx', b'ZXTape!', zx.TZXFileFormat),
        ('.wav', b'RIFF', zx.WAVFileFormat),
        ('.z80', None, zx.Z80SnapshotsFormat),
        ('.zip', b'PK\x03\x04', zx.ZIPFileFormat),
    ]

    filename_extension = filename_extension.lower()

    # First, try formats without signatures.
    for ext, signature, format in KNOWN_FORMATS:
        if not signature and filename_extension == ext:
            return format

    # Then, look at the signature.
    if image:
        for ext, signature, format in KNOWN_FORMATS:
            if signature and image[:len(signature)] == signature:
                return format

    # Finally, just try to guess by the given extension.
    for ext, signature, format in KNOWN_FORMATS:
        if filename_extension == ext:
            return format

    return None


def parse_archive(format, image):
    candidates = []
    for member_name, member_image in format().read_files(image):
        base, ext = os.path.splitext(member_name)
        member_format = detect_file_format(member_image, ext)

        if not member_format:
            continue

        # Recursively parse member archives.
        if issubclass(member_format, zx.ArchiveFileFormat):
            candidates.extend(parse_archive(member_format, member_image))
            continue

        candidates.append((member_name, member_format, member_image))

    return candidates


def parse_file_image(filename, image):
    base, ext = os.path.splitext(filename)
    format = detect_file_format(image, ext)
    if not format:
        raise zx.Error('Cannot determine the format of file %r.' % filename)

    if issubclass(format, zx.ArchiveFileFormat):
        candidates = parse_archive(format, image)
        if len(candidates) == 0:
            raise zx.Error('No files of known formats in archive %r.' %
                               filename)

        if len(candidates) > 1:
            raise zx.Error(
                'More than one file of a known format in archive %r: %s.' % (
                    filename, ', '.join(repr(n) for n, f, im in candidates)))

        filename, format, image = candidates[0]

    return format().parse(image)


def open_file_or_url(path):
    if path.startswith(('http:', 'https:', 'ftp:')):
        import urllib.request
        import urllib.error
        try:
            HEADERS = {
                'User-Agent': 'Mozilla/5.0 (Windows; U; Windows NT 5.1; '
                              'en-US; rv:1.9.0.7) Gecko/2009021910 '
                              'Firefox/3.0.7',
            }
            req = urllib.request.Request(path, headers=HEADERS)
            return urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            raise zx.Error('Cannot read remote file: %s, code %d.' % (
                               e.reason, e.code))

    return open(path, 'rb')


def parse_file(filename):
    with open_file_or_url(filename) as f:
        image = f.read()

    return parse_file_image(filename, image)


class Time(object):
    def __init__(self):
        self._seconds = 0

    def get(self):
        return self._seconds

    def advance(self, s):
        self._seconds += s


class TapePlayer(object):
    def __init__(self):
        self._is_paused = True
        self._pulses = []
        self._tick = 0
        self._level = False
        self._pulse = 0
        self._ticks_per_frame = 69888  # TODO
        self._time = Time()
        self._is_end = False

    def is_paused(self):
        return self._is_paused

    def pause(self, is_paused=True):
        self._is_paused = is_paused

    def unpause(self):
        self.pause(is_paused=False)

    def toggle_pause(self):
        self.pause(not self.is_paused())

    def is_end(self):
        return self._is_end

    def get_time(self):
        return self._time

    def load_parsed_file(self, file):
        self._pulses = file.get_pulses()
        self._level = False
        self.pause()

    def load_tape(self, file):
        self.load_parsed_file(file)
        self._is_end = False

    def get_level_at_frame_tick(self, tick):
        assert self._tick <= tick, (self._tick, tick)

        while self._tick < tick:
            if self._is_paused:
                self._tick = tick
                continue

            # See if we already have a non-zero-length pulse.
            if self._pulse:
                ticks_to_skip = min(self._pulse, tick - self._tick)
                self._pulse -= ticks_to_skip
                self._tick += ticks_to_skip
                self._time.advance(ticks_to_skip / (self._ticks_per_frame * 50))
                continue

            # Get subsequent pulse, if any.
            got_new_pulse = False
            for level, pulse in self._pulses:
                got_new_pulse = True
                self._level = level
                self._pulse = pulse
                # print(self._pulse)
                break

            # Do nothing, if there are no more pulses available.
            if not got_new_pulse:
                self._level = False
                self._tick = tick
                self._is_end = True

        return self._level

    def skip_rest_of_frame(self):
        if self._tick < self._ticks_per_frame:
            self.get_level_at_frame_tick(self._ticks_per_frame)

        assert self._tick >= self._ticks_per_frame
        self._tick -= self._ticks_per_frame


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


class Notification(object):
    def __init__(self):
        self.clear()

    def set(self, draw, time):
        self._timestamp = get_timestamp()
        self._draw = draw
        self._time = time

    def clear(self):
        self._timestamp = None
        self._draw = None

    def draw(self, window_size, screen_size, context):
        if not self._timestamp:
            return

        width, height = screen_size
        window_width, window_height = window_size

        size = min(80, width * 0.2)
        x = (window_width - size) // 2
        y = (window_height - size) // 2

        alpha = 1.5 - get_elapsed_time(self._timestamp)
        alpha = max(0, min(0.7, alpha))

        if not alpha:
            self.clear()
            return

        self._draw(context, x + size / 2, y + size / 2, size, alpha,
                   self._time.get())


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


# Stores information about the running code.
class Profile(object):
    _annots = dict()

    def add_instr_addr(self, addr):
        self._annots[addr] = 'instr'

    def __iter__(self):
        for addr in sorted(self._annots):
            yield addr, self._annots[addr]


class Emulator(Gtk.Window):
    SCREEN_AREA_BACKGROUND_COLOUR = rgb('#1e1e1e')

    SPIN_V0P5_INFO = {'id': 'info',
                      'creator': b'SPIN 0.5            ',
                      'creator_major_version': 0,
                      'creator_minor_version': 5}

    def __init__(self, speed_factor=1.0, profile=None):
        super(Emulator, self).__init__()

        self._screencast = Screencast()

        self._emulation_time = Time()
        self._speed_factor = speed_factor

        self.frame_width = 48 + 256 + 48
        self.frame_height = 48 + 192 + 40

        self._notification = Notification()
        self.done = False
        self._is_paused = False

        self.scale = 1 if SCREENCAST else 2

        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self.on_draw_area)
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
        self.connect("delete-event", self.on_done)

        # Don't even show the window on full throttle.
        if self._speed_factor is not None:
            self.show_all()

        self.frame_size = self.frame_width * self.frame_height
        self.frame = cairo.ImageSurface(cairo.FORMAT_RGB24,
                                        self.frame_width, self.frame_height)
        self.frame_data = self.frame.get_data()

        self.pattern = cairo.SurfacePattern(self.frame)
        if not SCREENCAST:
            self.pattern.set_filter(cairo.FILTER_NEAREST)

        self._emulator = zx.Spectrum48()
        self.processor_state = self._emulator  # TODO: Eliminate.

        self.keyboard_state = [0xff] * 8
        self.keys = {'RETURN': zx.KEYS_INFO['ENTER'],
                     'ALT_L': zx.KEYS_INFO['CAPS SHIFT'],
                     'SHIFT_L': zx.KEYS_INFO['CAPS SHIFT'],
                     'ALT_R': zx.KEYS_INFO['SYMBOL SHIFT'],
                     'SHIFT_R': zx.KEYS_INFO['SYMBOL SHIFT'],
                     'SPACE': zx.KEYS_INFO['BREAK SPACE']}
        for id in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                   'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
                   'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T',
                   'U', 'V', 'W', 'X', 'Y', 'Z']:
            self.keys[id] = zx.KEYS_INFO[id]
        self._emulator.set_on_input_callback(self.on_input)
        self.connect("key-press-event", self.on_key_press)
        self.connect("key-release-event", self.on_key_release)

        self.connect("button-press-event", self.on_click)
        self.connect("window-state-event", self.on_window_state_event)

        self.tape_player = TapePlayer()

        self.playback_player = None
        self.playback_samples = None

        self._profile = profile
        if self._profile:
            self._emulator.set_breakpoints(0, 0x10000)

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        self.destroy()

    def on_done(self, widget, context):
        self.done = True

    def on_draw_area(self, widget, context):
        window_size = self.get_size()
        window_width, window_height = window_size
        width = min(window_width,
                    zx.div_ceil(window_height * self.frame_width,
                                self.frame_height))
        height = min(window_height,
                     zx.div_ceil(window_width * self.frame_height,
                                 self.frame_width))

        # Draw the background.
        context.save()
        context.rectangle(0, 0, window_width, window_height)
        context.set_source_rgba(*self.SCREEN_AREA_BACKGROUND_COLOUR)
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

    def show_help(self):
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

    def is_paused(self):
        return self._is_paused

    def pause(self, is_paused = True):
        self._is_paused = is_paused
        if self.is_paused():
            self._notification.set(_gui.draw_pause_notification,
                                   self._emulation_time)
        else:
            self._notification.clear()

    def toggle_pause(self):
        self.pause(not self.is_paused())

    def error_box(self, title, message):
        dialog = Gtk.MessageDialog(
            self, 0, Gtk.MessageType.ERROR,
            Gtk.ButtonsType.OK, title)
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def choose_and_load_file(self):
        # TODO: Add file filters.
        dialog = Gtk.FileChooserDialog(
            'Load file', self,
            Gtk.FileChooserAction.OPEN,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_OPEN, Gtk.ResponseType.OK))

        if dialog.run() == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            try:
                self.load_file(filename)
            except zx.Error as e:
                self.error_box('File error', '%s' % e.args)

        dialog.destroy()

    def save_snapshot_file(self, format, filename):
        try:
            with open(filename, 'wb') as f:
                snapshot = format().make_snapshot(self._emulator)
                # TODO: make_snapshot() shall always return a snapshot object.
                if issubclass(type(snapshot), zx._MachineSnapshot):
                    image = snapshot.get_file_image()
                else:
                    image = snapshot
                f.write(image)
        except zx.Error as e:
            self.error_box('File error', '%s' % e.args)

    def save_snapshot(self):
        # TODO: Add file filters.
        dialog = Gtk.FileChooserDialog(
            'Save snapshot', self,
            Gtk.FileChooserAction.SAVE,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
        dialog.set_do_overwrite_confirmation(True)
        if dialog.run() == Gtk.ResponseType.OK:
            self.save_snapshot_file(zx.Z80SnapshotsFormat,
                                    dialog.get_filename())
        dialog.destroy()

    def quit(self):
        self.done = True

    def is_tape_paused(self):
        return self.tape_player.is_paused()

    def pause_tape(self, is_paused=True):
        self.tape_player.pause(is_paused)

        draw = (_gui.draw_tape_pause_notification if self.is_tape_paused()
                    else _gui.draw_tape_resume_notification)
        self._notification.set(draw, self.tape_player.get_time())

    def unpause_tape(self):
        self.pause_tape(is_paused=False)

    def toggle_tape_pause(self):
        self.pause_tape(not self.is_tape_paused())

    def _load_tape_to_player(self, file):
        self.tape_player.load_tape(file)
        self.pause_tape()

    def is_end_of_tape(self):
        return self.tape_player.is_end()

    def on_window_state_event(self, widget, event):
        state = event.new_window_state
        self._is_fullscreen = bool(state & Gdk.WindowState.FULLSCREEN)

    def toggle_fullscreen(self):
        if self._is_fullscreen:
            self.unfullscreen()
        else:
            self.fullscreen()

    KEY_HANDLERS = {
        'ESCAPE': quit,
        'F10': quit,
        'F1': show_help,
        'F2': save_snapshot,
        'F3': choose_and_load_file,
        'F6': toggle_tape_pause,
        'F11': toggle_fullscreen,
        'PAUSE': toggle_pause,
    }

    def _handle_key_stroke(self, key_info, pressed):
        # print(key_info['id'])
        addr_line = key_info['address_line']
        mask = 1 << key_info['port_bit']

        if pressed:
            self.keyboard_state[addr_line - 8] &= mask ^ 0xff
        else:
            self.keyboard_state[addr_line - 8] |= mask

    def generate_key_strokes(self, *keys):
        for key in keys:
            strokes = key.split('+')

            # TODO: Refine handling of aliases.
            ALIASES = {'SS': 'SYMBOL SHIFT'}
            strokes = [ALIASES.get(s, s) for s in strokes]
            # print(strokes)

            for id in strokes:
                # print(id)
                self._handle_key_stroke(zx.KEYS_INFO[id], pressed=True)
                self.run(0.03)

            for id in reversed(strokes):
                # print(id)
                self._handle_key_stroke(zx.KEYS_INFO[id], pressed=False)
                self.run(0.03)

    def on_key(self, event, pressed):
        key_id = Gdk.keyval_name(event.keyval).upper()
        # print(key_id)

        if pressed and key_id in self.KEY_HANDLERS:
            self.KEY_HANDLERS[key_id](self)

        key_info = self.keys.get(key_id, None)
        if key_info:
            self.pause(False)
            self._quit_playback_mode()

            self._handle_key_stroke(key_info, pressed)

    def on_key_press(self, widget, event):
        self.on_key(event, pressed=True)

    def on_key_release(self, widget, event):
        self.on_key(event, pressed=False)

    def on_click(self, widget, event):
        if event.type == Gdk.EventType.BUTTON_PRESS:
            self.toggle_pause()
            return True
        elif event.type == Gdk.EventType._2BUTTON_PRESS:
            self.toggle_fullscreen()

    def on_input(self, addr):
        # Handle playbacks.
        if self.playback_samples:
            sample = None
            for sample in self.playback_samples:
                break

            if sample == 'END_OF_FRAME':
                raise zx.Error(
                    'Too few input samples at frame %d of %d. '
                    'Given %d, used %d.' % (
                        self.playback_frame_count,
                        len(self.playback_chunk['frames']),
                        len(self.playback_samples), sample_i),
                    id='too_few_input_samples')

            # print('on_input() returns %d' % sample)
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

        return n

    def _save_crash_rzx(self, player, state, chunk_i, frame_i):
        snapshot = zx.Z80SnapshotsFormat().make(state)

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
            f.write(zx.make_rzx(crash_recording))

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
            if isinstance(chunk, zx._MachineSnapshot):
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
                    # fetch = num_of_fetches - self._emulator.get_fetches_limit()
                    # print('Input at fetch', fetch, 'of', num_of_fetches)
                    # TODO: print('read_port 0x%04x 0x%02x' % (addr, n), flush=True)

                    # TODO: Have a class describing playback state.
                    self.playback_frame_count = frame_count
                    self.playback_chunk = chunk
                    self.playback_sample_values = samples
                    self.playback_sample_i = sample_i
                    # print(frame_count, chunk_i, frame_i, sample_i, sample, flush=True)

                    yield sample

                # print('END_OF_FRAME', flush=True)
                yield 'END_OF_FRAME'

                frame_count += 1

    def run_quantum(self):
        if self.playback_player:
            creator_info = self.playback_player.find_recording_info_chunk()

        if True:  # TODO
            while Gtk.events_pending():
                Gtk.main_iteration()

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

            if self._is_paused:
                # Give the CPU some spare time.
                self.area.queue_draw()
                time.sleep(1 / 50)
                return

            events = self._emulator.run()
            # TODO: print(events)

            if events & self._emulator._BREAKPOINT_HIT:
                self.on_breakpoint()

                if self._profile:
                    pc = self._emulator.get_pc()
                    self._profile.add_instr_addr(pc)

                # SPIN v0.5 skips executing instructions
                # of the bytes-saving ROM procedure in
                # fast save mode.
                if (self.playback_samples and
                        creator_info == self.SPIN_V0P5_INFO and
                        self._emulator.get_pc() == 0x04d4):
                    sp = self._emulator.get_sp()
                    ret_addr = self._emulator.read16(sp)
                    self._emulator.set_sp(sp + 2)
                    self._emulator.set_pc(ret_addr)

            if events & self._emulator._END_OF_FRAME:
                if self._speed_factor is not None:
                    self._emulator.render_screen()
                    self.frame_data[:] = self._emulator.get_frame_pixels()
                    self.area.queue_draw()
                    time.sleep((1 / 50) * self._speed_factor)

                self.tape_player.skip_rest_of_frame()
                self._emulation_time.advance(1 / 50)

            if (self.playback_samples and
                events & self._emulator._FETCHES_LIMIT_HIT):
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
                        creator_info == self.SPIN_V0P5_INFO and
                        self.playback_sample_i + 1 < len(self.playback_sample_values)):
                    self._emulator.set_fetches_limit(1)
                    return

                sample = None
                for sample in self.playback_samples:
                    break
                if sample != 'END_OF_FRAME':
                    raise zx.Error(
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

    def run(self, duration):
        end_time = self._emulation_time.get() + duration
        while not self.done and self._emulation_time.get() < end_time:
            self.run_quantum()

    def main(self):
        while not self.done:
            self.run_quantum()

        self._quit_playback_mode()

    def load_input_recording(self, file):
        self.playback_player = PlaybackPlayer(file)
        creator_info = self.playback_player.find_recording_info_chunk()

        # SPIN v0.5 alters ROM to implement fast tape loading,
        # but that affects recorded RZX files.
        if creator_info == self.SPIN_V0P5_INFO:
            self._emulator.set_memory_block(0x1f47, b'\xf5')

        # The bytes-saving ROM procedure needs special processing.
        self._emulator.set_breakpoint(0x04d4)

        # Process frames in order.
        self.playback_samples = self._get_playback_samples()
        sample = None
        for sample in self.playback_samples:
            break
        assert sample == 'START_OF_FRAME'

    def load_file(self, filename):
        file = parse_file(filename)

        if isinstance(file, zx._MachineSnapshot):
            self._emulator.install_snapshot(file)
        elif isinstance(file, RZXFile):
            self.load_input_recording(file)
            self._enter_playback_mode()
        elif isinstance(file, zx.SoundFile):
            self._load_tape_to_player(file)
        else:
            raise zx.Error("Don't know how to load file %r." % filename)

    def run_file(self, filename):
        self.load_file(filename)
        self.main()

    def load_tape(self, filename):
        tape = parse_file(filename)
        if not isinstance(tape, zx.SoundFile):
            raise zx.Error('%r does not seem to be a tape file.' % filename)

        # Let the initialization complete.
        self._emulator.set_pc(0x0000)
        self.run(1.8)

        # Type in 'LOAD ""'.
        self.generate_key_strokes('J', 'SS+P', 'SS+P', 'ENTER')

        # Load and run the tape.
        self._load_tape_to_player(tape)
        self.unpause_tape()

        # Wait till the end of the tape.
        while not self.done and not self.is_end_of_tape():
            self.run_quantum()

    def set_breakpoint(self, addr):
        self._emulator.set_breakpoint(addr)

    def on_breakpoint(self):
        pass

    def get_memory_view(self, addr, size):
        return self._emulator.get_memory_block(addr, size)


def pop_argument(args, error):
    if not args:
        raise zx.Error(error)
    return args.pop(0)


def handle_extra_arguments(args):
    if args:
        raise zx.Error('Extra argument %r.' % args[0])


def run(args):
    filename = None
    if args:
        filename = args.pop(0)
        handle_extra_arguments(args)

    app = Emulator()
    if filename:
        app.load_file(filename)
    app.main()
    app.destroy()


def profile(args):
    file_to_run = pop_argument(args, "The file to run is not specified.")
    profile_filename = pop_argument(args, "The profile filename is not "
                                          "specified.")
    handle_extra_arguments(args)

    profile = Profile()
    app = Emulator(profile=profile)
    app.load_file(file_to_run)
    app.main()
    app.destroy()

    # TODO: Amend profile data by reading them out first instead
    # of overwriting.
    with open(profile_filename, 'wt') as f:
        for addr, annot in profile:
            print('@0x%04x %s' % (addr, annot), file=f)


def dump(args):
    if not args:
        raise zx.Error('The file to dump is not specified.')

    filename = args.pop(0)
    handle_extra_arguments(args)

    file = parse_file(filename)
    print(file)


def looks_like_filename(s):
    return '.' in s


def usage():
    print('Usage:')
    print('  zx [run] [<file>]')
    print('  zx [convert] <from-file> <to-filename>')
    print('  zx profile <file-to-run> <profile-filename>')
    print('  zx dump <file>')
    print('  zx help')
    sys.exit()


def test_file(filename):
    print('%r' % filename)
    def move(dest_dir):
        os.makedirs(dest_dir, exist_ok=True)

        # Make sure the destination filename is unique.
        dest_filename = filename
        while True:
            dest_path = os.path.join(dest_dir, dest_filename)
            if not os.path.exists(dest_path):
                break

            dest_filename, ext = os.path.splitext(dest_filename)
            dest_filename = dest_filename.rsplit('--', maxsplit=1)
            if len(dest_filename) == 1:
                dest_filename = dest_filename[0] + '--2'
            else:
                dest_filename = (dest_filename[0] + '--' +
                                     str(int(dest_filename[1]) + 1))

            dest_filename = dest_filename + ext


        os.rename(filename, dest_path)
        print('%r moved to %r' % (filename, dest_dir))

    app = Emulator(speed_factor=None)
    try:
        app.run_file(filename)
        if app.done:
            return False
        move('passed')
    except zx.Error as e:
        move(e.id)

    app.destroy()

    return True


def test(args):
    for filename in args:
        if not test_file(filename):
            break


def fastforward(args):
    for filename in args:
        app = Emulator(speed_factor=0)
        app.run_file(filename)
        if app.done:
            break

        app.destroy()


def _convert_tape_to_snapshot(src, src_filename, src_format,
                              dest_filename, dest_format):
    assert issubclass(src_format, zx.SoundFileFormat), src_format
    assert issubclass(dest_format, SnapshotsFormat), dest_format

    # app = Emulator(speed_factor=None)
    app = Emulator()

    # Load the tape into memory automatically.
    app.load_tape(src_filename)

    # Save snapshot and quit.
    app.save_snapshot_file(dest_format, dest_filename)
    app.destroy()


def _convert_tape_to_tape(src, src_filename, src_format,
                          dest_filename, dest_format):
    assert issubclass(src_format, zx.SoundFileFormat), src_format
    assert issubclass(dest_format, zx.SoundFileFormat), dest_format

    dest_format().save_from_pulses(dest_filename, src.get_pulses())


def _convert_snapshot_to_snapshot(src, src_filename, src_format,
                                  dest_filename, dest_format):
    assert issubclass(src_format, SnapshotsFormat), src_format
    assert issubclass(dest_format, SnapshotsFormat), dest_format

    app = Emulator(speed_factor=None)
    app.load_file(src_filename)
    app.save_snapshot_file(dest_format, dest_filename)
    app.destroy()


def convert_file(src_filename, dest_filename):
    src = parse_file(src_filename)
    src_format = src.get_format()
    # print(src, '->', dest_filename)

    _, dest_ext = os.path.splitext(dest_filename)
    dest_format = detect_file_format(image=None, filename_extension=dest_ext)
    if not dest_format:
        raise zx.Error('Cannot determine the format of file %r.' % (
                           dest_filename))

    CONVERTERS = [
        (zx.SoundFileFormat, zx.SoundFileFormat,
         _convert_tape_to_tape),
        (zx.SoundFileFormat, SnapshotsFormat,
         _convert_tape_to_snapshot),
        (SnapshotsFormat, SnapshotsFormat,
         _convert_snapshot_to_snapshot),
    ]

    for sf, df, conv in CONVERTERS:
        if issubclass(src_format, sf) and issubclass(dest_format, df):
            conv(src, src_filename, src_format, dest_filename, dest_format)
            return

    raise zx.Error("Don't know how to convert from %s to %s files." % (
                   src_format().get_name(),
                   dest_format().get_name()))


def convert(args):
    if not args:
        raise zx.Error('The file to convert from is not specified.')
    src_filename = args.pop(0)

    if not args:
        raise zx.Error('The file to convert to is not specified.')
    dest_filename = args.pop(0)

    handle_extra_arguments(args)

    convert_file(src_filename, dest_filename)


def handle_command_line(args):
    # Guess the command by the arguments.
    if (not args or
        len(args) == 1 and looks_like_filename(args[0])):
        run(args)
        return

    if (len(args) == 2 and looks_like_filename(args[0]) and
        looks_like_filename(args[1])):
        convert(args)
        return

    # Handle an explicitly specified command.
    command = args[0]
    if command in ['help', '-help', '--help',
                   '-h', '-?',
                   '/h', '/help']:
        usage()
        return

    COMMANDS = {
        'convert': convert,
        'dump': dump,
        'profile': profile,
        'run': run,

        # TODO: Hidden commands for internal use.
        '__test': test,
        '__ff': fastforward,
    }

    if command not in COMMANDS:
        raise zx.Error('Unknown command %r.' % command)

    COMMANDS[command](args[1:])


def main():
    try:
        handle_command_line(sys.argv[1:])
    except zx.Error as e:
        print('zx: %s' % e.args)
    except FileNotFoundError as e:
        print('zx: %s: %r.' % (e.args[1], e.filename))


if __name__ == "__main__":
    # import cProfile
    # cProfile.run('main()')
    main()

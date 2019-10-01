#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


import cairo, gi, os, sys, time, zx
import collections
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk



# TODO: Move to the z80 project.
class ProcessorSnapshot(zx.Data):
    pass


class MachineSnapshot(zx.Data):
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


def detect_file_format(image, filename_extension):
    if filename_extension.lower() == '.z80':
        return zx.Z80SnapshotsFormat()

    if image[:4] == b'RZX!':
        return RZXFileFormat()

    if image[:7] == b'ZXTape!':
        return zx.TZXFileFormat()

    return None


def parse_file(filename):
    with open(filename, 'rb') as f:
        image = f.read()

    base, ext = os.path.splitext(filename)
    format = detect_file_format(image, ext)
    if not format:
        raise zx.Error('Cannot determine the format of file %r.' % filename)

    return format.parse(image)


class emulator(Gtk.Window):
    def __init__(self, speed_factor=1.0):
        super(emulator, self).__init__()

        self._speed_factor = speed_factor

        self.frame_width = 48 + 256 + 48
        self.frame_height = 48 + 192 + 40

        self.done = False

        self.scale = 2

        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self.on_draw_area)
        self.add(self.area)

        self.set_title("ZX Spectrum Emulator")
        self.resize(self.frame_width * self.scale,
                    self.frame_height * self.scale)
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
        self.pattern.set_filter(cairo.FILTER_NEAREST)

        self.emulator = zx.Spectrum48()
        self.processor_state = self.emulator  # TODO: Eliminate.

        self.keyboard_state = [0xff] * 8
        self.keys = {'RETURN': zx.KEYS_INFO['ENTER'],
                     'SHIFT_L': zx.KEYS_INFO['CAPS SHIFT'],
                     'SHIFT_R': zx.KEYS_INFO['SYMBOL SHIFT'],
                     'SPACE': zx.KEYS_INFO['BREAK SPACE']}
        for id in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                   'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
                   'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T',
                   'U', 'V', 'W', 'X', 'Y', 'Z']:
            self.keys[id] = zx.KEYS_INFO[id]
        self.emulator.set_on_input_callback(self.on_input)
        self.connect("key-press-event", self.on_key_press)
        self.connect("key-release-event", self.on_key_release)

    def on_done(self, widget, context):
        self.done = True

    def on_draw_area(self, widget, context):
        context.save()
        context.scale(self.scale, self.scale)
        context.set_source(self.pattern)
        context.paint()
        context.restore()

    def handle_spectrum_key(self, key_info, pressed):
        if not key_info:
            return

        # print(key_info['id'])
        addr_line = key_info['address_line']
        mask = 1 << key_info['port_bit']

        if pressed:
            self.keyboard_state[addr_line - 8] &= mask ^ 0xff
        else:
            self.keyboard_state[addr_line - 8] |= mask

    def on_key_press(self, widget, event):
        key_id = Gdk.keyval_name(event.keyval).upper()
        if key_id in ['ESCAPE', 'F10']:
            self.done = True
            return
        if key_id == 'F2':
            # TODO: Let user choose the name.
            self.save_snapshot('saved.z80')

        self.handle_spectrum_key(self.keys.get(key_id, None), pressed=True)

    def on_key_release(self, widget, event):
        key_id = Gdk.keyval_name(event.keyval).upper()
        self.handle_spectrum_key(self.keys.get(key_id, None), pressed=False)

    def on_input(self, addr):
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

        return n

    def save_snapshot(self, filename):
        with open(filename, 'wb') as f:
            f.write(zx.Z80SnapshotsFormat().make(self.emulator))

    def _find_recording_info_chunk(self, recording):
        for chunk in recording['chunks']:
            if chunk['id'] == 'info':
                return chunk
        assert 0  # TODO

    def _save_crash_rzx(self, recording, state, chunk_i, frame_i):
        snapshot = zx.Z80SnapshotsFormat().make(state)

        crash_recording = {
            'id': 'input_recording',
            'chunks': [
                self._find_recording_info_chunk(recording),
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

    def playback_input_recording(self, file):
        # Interrupts are supposed to be controlled by the
        # recording.
        machine_state = self.emulator  # TODO: Eliminate.
        machine_state.suppress_int()
        machine_state.allow_int_after_ei(True)
        # machine_state.enable_trace()

        assert isinstance(file, RZXFile)
        recording = file._recording

        creator_info = self._find_recording_info_chunk(recording)

        # SPIN v0.5 alters ROM to implement fast tape loading,
        # but that affects recorded RZX files.
        spin_v0p5_info = {'id': 'info',
                          'creator': b'SPIN 0.5            ',
                          'creator_major_version': 0,
                          'creator_minor_version': 5 }
        if creator_info == spin_v0p5_info:
            machine_state.set_memory_block(0x1f47, b'\xf5')

        # The bytes-saving ROM procedure needs special processing.
        machine_state.set_breakpoint(0x04d4)

        # Process chunks in order.
        frame_count = 0
        chunks = recording['chunks']
        for chunk_i, chunk in enumerate(chunks):
            if self.done:
                break

            if isinstance(chunk, MachineSnapshot):
                self.emulator.install_snapshot(chunk)
                continue

            if chunk['id'] != 'port_samples':
                continue

            first_tick = chunk['first_tick']
            machine_state.set_ticks_since_int(first_tick)

            for frame_i, frame in enumerate(chunk['frames']):
                if self.done:
                    break

                frame_state = machine_state.clone()

                # TODO: For debug purposes.
                '''
                frame_count += 1
                if frame_count == -12820:
                    self._save_crash_rzx(recording, frame_state, chunk_i, frame_i)
                    assert 0

                if frame_count == -65952 - 1000:
                    machine_state.enable_trace()
                '''

                num_of_fetches, samples = frame
                # print(num_of_fetches, samples)
                self.sample_i = 0
                def on_input(addr):
                    # print(machine_state.get_fetches_limit())
                    fetch = num_of_fetches - machine_state.get_fetches_limit()
                    # print('Input at fetch', fetch, 'of', num_of_fetches)

                    if self.sample_i >= len(samples):
                        raise zx.Error(
                            'Too few input samples at frame %d of %d. '
                            'Given %d, used %d.' % (
                                frame_count, len(chunk['frames']),
                                len(samples), self.sample_i),
                            id='too_few_input_samples')

                    n = samples[self.sample_i]
                    # TODO: print('read_port 0x%04x 0x%02x' % (addr, n), flush=True)
                    self.sample_i += 1
                    return n

                self.emulator.set_on_input_callback(on_input)

                # TODO: print(num_of_fetches, samples, flush=True)
                machine_state.set_fetches_limit(num_of_fetches)

                while not self.done:
                    while Gtk.events_pending():
                        Gtk.main_iteration()

                    events = self.emulator.run()
                    # TODO: print(events)

                    if events & machine_state._BREAKPOINT_HIT:
                        # SPIN v0.5 skips executing instructions
                        # of the bytes-saving ROM procedure in
                        # fast save mode.
                        if (creator_info == spin_v0p5_info and
                                machine_state.get_pc() == 0x04d4):
                            sp = machine_state.get_sp()
                            ret_addr = machine_state.read16(sp)
                            machine_state.set_sp(sp + 2)
                            machine_state.set_pc(ret_addr)

                    if (events & machine_state._END_OF_FRAME and
                            self._speed_factor is not None):
                        self.emulator.render_frame()
                        self.frame_data[:] = self.emulator.get_frame_pixels()
                        self.area.queue_draw()
                        # print(self.processor_state.get_bc())
                        time.sleep((1 / 50) * self._speed_factor)

                    if events & machine_state._FETCHES_LIMIT_HIT:
                        # Some simulators, e.g., SPIN, may store an interrupt
                        # point in the middle of a IX- or IY-prefixed
                        # instruction, so we continue until such
                        # instruction, if any, is completed.
                        if machine_state.get_index_rp_kind() != 'hl':
                            machine_state.set_fetches_limit(1)
                            continue

                        # SPIN doesn't update the fetch counter if the last
                        # instruction in frame is IN.
                        if (creator_info == spin_v0p5_info and
                                self.sample_i < len(samples)):
                            machine_state.set_fetches_limit(1)
                            continue

                        self.emulator.handle_active_int()
                        break

                if self.sample_i != len(samples):
                    raise zx.Error(
                        'Too many input samples at frame %d of %d. '
                        'Given %d, used %d.' % (
                            frame_count, len(chunk['frames']),
                            len(samples), self.sample_i),
                        id='too_many_input_samples')


    def main(self):
        # self.emulator.enable_trace()

        while not self.done:
            while Gtk.events_pending():
                Gtk.main_iteration()

            events = self.emulator.run()
            # TODO: print(events)

            if events & self.emulator._FETCHES_LIMIT_HIT:
                set_fetches_limit = True

            if events & self.emulator._END_OF_FRAME:
                self.emulator.render_frame()
                self.frame_data[:] = self.emulator.get_frame_pixels()
                self.area.queue_draw()
                time.sleep((1 / 50) * self._speed_factor)

    def run_file(self, filename):
        file = parse_file(filename)

        if isinstance(file, MachineSnapshot):
            self.emulator.install_snapshot(file)
            self.main()
        elif isinstance(file, RZXFile):
            self.playback_input_recording(file)
        elif isinstance(file, zx.TapeFile):
            assert 0  # TODO
        else:
            raise zx.Error("Don't know how to run file %r." % filename)


def handle_extra_arguments(args):
    if args:
        raise zx.Error('Extra argument %r.' % args[0])


def run(args):
    if not args:
        app = emulator()
        app.main()
    else:
        filename = args.pop(0)
        handle_extra_arguments(args)

        app = emulator()
        app.run_file(filename)


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
    print('  zx [run] [<filename>]')
    print('  zx dump <filename>')
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

    app = emulator(speed_factor=None)
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
        app = emulator(speed_factor=0)
        app.run_file(filename)
        if app.done:
            break

        app.destroy()


def convert_file(src_filename, dest_filename):
    src = parse_file(src_filename)
    print(src, '->', dest_filename)


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


if __name__ == "__main__":
    # import cProfile
    # cProfile.run('main()')
    main()

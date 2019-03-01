#!/usr/bin/env python3
# -*- coding: utf-8 -*-

''' ZX Spectrum Emulator.

    Copyright (C) 2017 Ivan Kosarev.
    ivan@kosarev.info

    Published under the MIT license.
'''

import cairo, gi, os, sys, time, zx
import collections
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk


class Data(object):
    def __init__(self, fields):
        self._fields = fields

    def __contains__(self, id):
        return id in self._fields

    def __getitem__(self, id):
        return self._fields[id]

    def __repr__(self):
        return repr(self._fields)

    def __iter__(self):
        for id in self._fields:
            yield id

    def items(self):
        for field in self._fields.items():
            yield field



# TODO: Move to the z80 project.
class ProcessorSnapshot(Data):
    pass


class MachineSnapshot(Data):
    pass


class FileFormat(object):
    pass


class SnapshotsFormat(FileFormat):
    pass


class RZXFile(Data):
    def __init__(self, recording):
        self._recording = recording


class RZXFilesFormat(FileFormat):
    def parse(self, image):
        recording = zx.parse_rzx(image)
        return RZXFile(recording)


def detect_file_format(image, filename_extension):
    if filename_extension.lower() == '.z80':
        return zx.Z80SnapshotsFormat()

    if image[:4] == b'RZX!':
        return RZXFilesFormat()

    return None


def parse_file(filename):
    with open(filename, 'rb') as f:
        image = f.read()

    base, ext = os.path.splitext(filename)
    format = detect_file_format(image, ext)
    if not format:
        raise zx.Error('Cannot determine format of file %r.' % filename)

    return format.parse(image)


class emulator(Gtk.Window):
    _END_OF_FRAME      = 1 << 1
    _FETCHES_LIMIT_HIT = 1 << 3

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
        if self._speed_factor:
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

    def playback_input_recording(self, file):
        # Interrupts are supposed to be controlled by the
        # recording.
        machine_state = self.emulator  # TODO: Eliminate.
        machine_state.suppress_int()
        machine_state.allow_int_after_ei(True)

        assert isinstance(file, RZXFile)
        recording = file._recording
        chunks = recording['chunks']

        # Process chunks in order.
        for chunk in chunks:
            if self.done:
                break

            if isinstance(chunk, MachineSnapshot):
                self.emulator.install_snapshot(chunk)
                continue

            if chunk['id'] != 'port_samples':
                continue

            first_tick = chunk['first_tick']
            machine_state.set_ticks_since_int(first_tick)

            for num_of_fetches, samples in chunk['frames']:
                if self.done:
                    break

                # print(num_of_fetches, samples)
                self.sample_i = 0
                def on_input(addr):
                    if self.sample_i >= len(samples):
                        raise zx.Error('Too few input samples.',
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

                    if events & self._END_OF_FRAME and self._speed_factor:
                        self.emulator.render_frame()
                        self.frame_data[:] = self.emulator.get_frame_pixels()
                        self.area.queue_draw()
                        # print(self.processor_state.get_bc())
                        time.sleep((1 / 50) * self._speed_factor)

                    if events & self._FETCHES_LIMIT_HIT:
                        # Some simulators, e.g., SPIN, may store an interrupt
                        # point in the middle of a IX- or IY-prefixed
                        # instruction, so we continue until such
                        # instruction, if any, is completed.
                        if machine_state.get_index_rp_kind() != 'hl':
                            machine_state.set_fetches_limit(1)
                            continue

                        self.emulator.handle_active_int()
                        break

                if self.sample_i != len(samples):
                    raise zx.Error('Too many input samples.',
                                   id='too_many_input_samples')

    def main(self):
        while not self.done:
            while Gtk.events_pending():
                Gtk.main_iteration()

            events = self.emulator.run()
            # TODO: print(events)

            if events & self._FETCHES_LIMIT_HIT:
                set_fetches_limit = True

            if events & self._END_OF_FRAME:
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
        else:
            assert 0, "Unexpected type of file encountered."


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


def test(args):
    for filename in args:
        print('%r' % filename)
        def move(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)

            dest_path = os.path.join(dest_dir, filename)
            assert not os.path.exists(dest_path)  # TODO

            os.rename(filename, dest_path)
            print('%r moved to %r' % (filename, dest_dir))

        app = emulator(speed_factor=0)
        try:
            app.run_file(filename)
            if app.done:
                break
            move('passed')
        except zx.Error as e:
            move(e.id)

        app.destroy()


def handle_command_line(args):
    if not args or looks_like_filename(args[0]):
        run(args)
        return

    command = args[0]
    if command in ['help', '-help', '--help',
                   '-h', '-?',
                   '/h', '/help']:
        usage()
        return

    if command == 'run':
        run(args[1:])
        return

    if command == 'dump':
        dump(args[1:])
        return


    # TODO: A hidden command for internal use.
    if command == '__test':
        test(args[1:])
        return

    raise zx.Error('Unknown command %r.' % command)


def main():
    try:
        handle_command_line(sys.argv[1:])
    except zx.Error as e:
        print('zx: %s' % e.args)


if __name__ == "__main__":
    # import cProfile
    # cProfile.run('main()')
    main()

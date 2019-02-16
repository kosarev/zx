#!/usr/bin/env python3
# -*- coding: utf-8 -*-

''' ZX Spectrum Emulator.

    Copyright (C) 2017 Ivan Kosarev.
    ivan@kosarev.info

    Published under the MIT license.
'''

import cairo, gi, sys, time, zx
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk


class DataFile(object):
    pass


class SnapshotFile(DataFile):
    pass


class FileFormat(object):
    pass


class SnapshotsFormat(FileFormat):
    pass


class Z80SnapshotFile(SnapshotFile):
    def __init__(self, snapshot):
        self._snapshot = snapshot


class Z80SnapshotsFormat(SnapshotsFormat):
    def parse(self, image):
        snapshot = zx.parse_z80_snapshot(image)
        return Z80SnapshotFile(snapshot)


class RZXFile(DataFile):
    def __init__(self, recording):
        self._recording = recording


class RZXFilesFormat(FileFormat):
    def parse(self, image):
        recording = zx.parse_rzx(image)
        return RZXFile(recording)


class emulator(Gtk.Window):
    _END_OF_FRAME      = 1 << 1
    _FETCHES_LIMIT_HIT = 1 << 3

    def __init__(self):
        super(emulator, self).__init__()

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
        self.show_all()

        self.frame_size = self.frame_width * self.frame_height
        self.frame = cairo.ImageSurface(cairo.FORMAT_RGB24,
                                        self.frame_width, self.frame_height)
        self.frame_data = self.frame.get_data()

        self.pattern = cairo.SurfacePattern(self.frame)
        self.pattern.set_filter(cairo.FILTER_NEAREST)

        self.emulator = zx.Spectrum48()
        self.processor_state = self.emulator.get_processor_state()

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
            f.write(zx.make_z80_snapshot(self.processor_state,
                                         self.emulator._machine_state,
                                         self.emulator.memory[0x4000:]))

    def playback_input_recording(self, file):
        # Interrupts are supposed to be controlled by the
        # recording.
        machine_state = self.emulator.get_machine_state()
        machine_state.suppress_int()

        assert isinstance(file, RZXFile)
        recording = file._recording
        chunks = recording['chunks']

        # Process chunks in order.
        for chunk in chunks:
            if self.done:
                break

            if chunk['id'] == 'snapshot':
                self.emulator.install_snapshot(chunk)
                continue

            if chunk['id'] != 'port_samples':
                continue

            first_tick = chunk['first_tick']
            machine_state.set_ticks_since_int(first_tick)

            for num_of_fetches, samples in chunk['frames']:
                if self.done:
                    break

                self.sample_i = 0
                def on_input(addr):
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

                    if events & self._END_OF_FRAME:
                        self.emulator.render_frame()
                        self.frame_data[:] = self.emulator.get_frame_pixels()
                        self.area.queue_draw()
                        # print(self.processor_state.get_bc())
                        time.sleep(1 / 50)

                    if events & self._FETCHES_LIMIT_HIT:
                        self.emulator.handle_active_int()
                        break

                assert self.sample_i == len(samples), (self.sample_i, samples)

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
                time.sleep(1 / 50)

    def detect_file_format(self, image, filename=None):
        if image[:4] == b'RZX!':
            return RZXFilesFormat()

        return Z80SnapshotsFormat()

    def parse_file(self, filename):
        with open(filename, 'rb') as f:
            image = f.read()

        format = self.detect_file_format(image, filename)
        return format.parse(image)

    def run_file(self, filename):
        file = self.parse_file(filename)

        if isinstance(file, SnapshotFile):
            self.emulator.install_snapshot(file._snapshot)
            self.main()
        elif isinstance(file, RZXFile):
            self.playback_input_recording(file)


def run(filename):
    app = emulator()

    if filename is None:
        app.main()
    elif filename.lower().endswith('.z80'):
        app.run_file(filename)
    elif filename.lower().endswith('.rzx'):
        app.run_file(filename)
    else:
        raise zx.Error('Unknown type of file %r.' % filename)


def process_command_line(args):
    filename = None
    if args:
        filename = args.pop(0)

    if args:
        raise zx.Error('Extra argument %r.' % args[0])

    run(filename)


def main():
    try:
        process_command_line(sys.argv[1:])
    except zx.Error as e:
        print('zx: %s' % e.args)


if __name__ == "__main__":
    # import cProfile
    # cProfile.run('main()')
    main()

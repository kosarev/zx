#!/usr/bin/env python3
# -*- coding: utf-8 -*-

''' ZX Spectrum Emulator.

    Copyright (C) 2017 Ivan Kosarev.
    ivan@kosarev.info

    Published under the MIT license.
'''

import cairo, gi, time, zx
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk


class emulator(Gtk.Window):
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
        self.state = self.emulator.get_state()

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

    def load_snapshot(self, filename):
        with open(filename, 'rb') as f:
            self.emulator.install_snapshot(zx.parse_z80_snapshot(f.read()))

    def main(self):
        while not self.done:
            while Gtk.events_pending():
                Gtk.main_iteration()
            self.emulator.render_frame()
            self.frame_data[:] = self.emulator.get_frame_pixels()
            self.area.queue_draw()
            self.emulator.execute_frame()
            # print(self.state[0] + self.state[1] * 0x100)
            time.sleep(1 / 50)


def main():
    app = emulator()
    # app.load_snapshot('../x.z80')
    app.main()


if __name__ == "__main__":
    # import cProfile
    # cProfile.run('main()')
    main()

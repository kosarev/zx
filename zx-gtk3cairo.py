#!/usr/bin/env python3
# -*- coding: utf-8 -*-

''' ZX Spectrum Emulator.

    Copyright (C) 2017 Ivan Kosarev.
    ivan@kosarev.info

    Published under the MIT license.
'''

import cairo, gi, time, zx
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


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
        self.memory = self.emulator.get_memory()

    def on_done(self, widget, context):
        self.done = True

    def on_draw_area(self, widget, context):
        context.save()
        context.scale(self.scale, self.scale)
        context.set_source(self.pattern)
        context.paint()
        context.restore()

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
    app.main()


if __name__ == "__main__":
    # import cProfile
    # cProfile.run('main()')
    main()

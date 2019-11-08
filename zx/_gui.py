# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.

PI = 3.1415926535

def rgb(color, alpha=1):
    assert color.startswith('#')
    assert len(color) == 7
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    return r / 0xff, g / 0xff, b / 0xff, alpha


def draw_pause(context, x, y, size, alpha=1):
    x += size / 2
    y += size / 2
    context.arc(x, y, size, 0, 2 * PI)
    context.set_source_rgba(*rgb('#1e1e1e', alpha))
    context.fill()

    w = 0.2 * size
    h = 0.8 * size
    d = 0.3 * size
    context.rectangle(x - d, y - h / 2, w, h)
    context.rectangle(x + d - w, y - h / 2, w, h)
    context.set_source_rgba(*rgb('#ffffff', alpha))
    context.fill()

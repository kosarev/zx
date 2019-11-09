# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.

import cairo


PI = 3.1415926535


def rgb(color, alpha=1):
    assert color.startswith('#')
    assert len(color) == 7
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    return r / 0xff, g / 0xff, b / 0xff, alpha


def _draw_pause_sign(context, x, y, size, alpha):
    w = 0.1 * size
    h = 0.4 * size
    d = 0.15 * size
    context.rectangle(x - d, y - h / 2, w, h)
    context.rectangle(x + d - w, y - h / 2, w, h)
    context.fill()


def _draw_tape_sign(context, x, y, size, alpha, t=0):
    R = 0.10
    D = 0.33 - R
    H = 0.6
    RPM = 33.3

    context.set_line_width(size * 0.05)
    context.set_line_cap(cairo.LINE_CAP_ROUND)
    context.set_line_join(cairo.LINE_JOIN_ROUND)

    context.rectangle(x - size * 0.5, y - size * (H / 2), size, size * H)

    context.move_to(x - size * (D - 0.15), y - size * R)
    context.line_to(x + size * (D - 0.15), y - size * R)

    context.move_to(x - size * (D - R), y)
    context.new_sub_path()
    a = t * (RPM * 2 * PI / 60)
    context.arc(x - size * D, y, size * R, a, a + (2 * PI - 0.7))

    context.move_to(x + size * (D + R), y)
    context.new_sub_path()
    a += PI / 5
    # context.arc(x + size * D, y, size * R, 0, 2 * PI)
    context.arc(x + size * D, y, size * R, a, a + (2 * PI - 0.7))

    context.stroke()


def _draw_notification_circle(context, x, y, size, alpha):
    context.arc(x, y, size / 2, 0, 2 * PI)
    context.set_source_rgba(*rgb('#1e1e1e', alpha))
    context.fill()


def draw_pause_notification(context, x, y, size, alpha=1, t=0):
    _draw_notification_circle(context, x, y, size, alpha)

    context.set_source_rgba(*rgb('#ffffff', alpha))
    _draw_pause_sign(context, x, y, size, alpha)


def draw_tape_pause_notification(context, x, y, size, alpha=1, t=0):
    _draw_notification_circle(context, x, y, size, alpha)

    context.set_source_rgba(*rgb('#ffffff', alpha))
    _draw_tape_sign(context, x, y - size * 0.13, size * 0.5, alpha)
    _draw_pause_sign(context, x, y + size * 0.23, size * 0.5, alpha)


def draw_tape_resume_notification(context, x, y, size, alpha=1, t=0):
    _draw_notification_circle(context, x, y, size, alpha)

    context.set_source_rgba(*rgb('#ffffff', alpha))
    _draw_tape_sign(context, x, y - size * 0.015, size * 0.6, alpha, t)

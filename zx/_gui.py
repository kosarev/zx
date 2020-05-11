# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.

import cairo
import gi
from ._device import Device
from ._device import EmulatorEvent
from ._error import USER_ERRORS
from ._error import verbalize_error
from ._keyboard import KEYS_INFO
from ._time import get_elapsed_time
from ._time import get_timestamp
from ._utils import div_ceil
from ._z80snapshot import Z80SnapshotFormat
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk  # nopep8


SCREENCAST = False

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
    _draw_tape_sign(context, x, y - size * 0.13, size * 0.5, alpha, t)
    _draw_pause_sign(context, x, y + size * 0.23, size * 0.5, alpha)


def draw_tape_resume_notification(context, x, y, size, alpha=1, t=0):
    _draw_notification_circle(context, x, y, size, alpha)

    context.set_source_rgba(*rgb('#ffffff', alpha))
    _draw_tape_sign(context, x, y - size * 0.015, size * 0.6, alpha, t)


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


class ScreenWindow(Device):
    _SCREEN_AREA_BACKGROUND_COLOUR = rgb('#1e1e1e')

    def __init__(self, emulator):
        super().__init__(emulator)

        self._window = Gtk.Window()

        self._KEY_HANDLERS = {
            'ESCAPE': self.emulator._quit,
            'F10': self.emulator._quit,
            'F1': self._show_help,
            'F2': self._save_snapshot,
            'F3': self._choose_and_load_file,
            'F6': self.emulator._toggle_tape_pause,
            'F11': self._toggle_fullscreen,
            'PAUSE': self.emulator._toggle_pause,
        }

        self._EMULATOR_EVENT_HANDLERS = {
            EmulatorEvent.PAUSE_STATE_UPDATED: self._on_updated_pause_state,
            EmulatorEvent.QUANTUM_RUN: self._on_quantum_run,
            EmulatorEvent.SCREEN_UPDATED: self._on_updated_screen,
            EmulatorEvent.TAPE_STATE_UPDATED: self._on_updated_tape_state,
        }

        self._notification = Notification()
        self._screencast = Screencast()

        # TODO: Hide members like this.
        self.frame_width = 48 + 256 + 48
        self.frame_height = 48 + 192 + 40

        self.scale = 1 if SCREENCAST else 2

        self.area = Gtk.DrawingArea()
        self.area.connect('draw', self._on_draw_area)
        self._window.add(self.area)

        self._window.set_title('ZX Spectrum Emulator')
        if SCREENCAST:
            width, height = 640, 390
        else:
            width, height = (self.frame_width * self.scale,
                             self.frame_height * self.scale)
        self._window.resize(width, height)
        minimum_size = self.frame_width // 4, self.frame_height // 4
        self._window.set_size_request(*minimum_size)
        self._window.set_position(Gtk.WindowPosition.CENTER)
        self._window.connect("delete-event", self.emulator._on_done)

        self._window.show_all()

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

        self._window.connect('key-press-event', self._on_key_press)
        self._window.connect('key-release-event', self._on_key_release)
        self._window.connect('button-press-event', self._on_click)
        self._window.connect('window-state-event', self._on_window_state_event)

    def _on_draw_area(self, widget, context):
        window_size = self._window.get_size()
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

    def _on_updated_screen(self, pixels):
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
            'Save snapshot', self._window,
            Gtk.FileChooserAction.SAVE,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
        dialog.set_do_overwrite_confirmation(True)
        if dialog.run() == Gtk.ResponseType.OK:
            try:
                self.emulator._save_snapshot_file(Z80SnapshotFormat,
                                                  dialog.get_filename())
            except USER_ERRORS as e:
                self._error_box('File error', verbalize_error(e))

        dialog.destroy()

    def _error_box(self, title, message):
        dialog = Gtk.MessageDialog(
            self._window, 0, Gtk.MessageType.ERROR,
            Gtk.ButtonsType.OK, title)
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def _choose_and_load_file(self):
        # TODO: Add file filters.
        dialog = Gtk.FileChooserDialog(
            'Load file', self._window,
            Gtk.FileChooserAction.OPEN,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_OPEN, Gtk.ResponseType.OK))

        if dialog.run() == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            try:
                self.emulator._load_file(filename)
            except USER_ERRORS as e:
                self._error_box('File error', verbalize_error(e))

        dialog.destroy()

    def _toggle_fullscreen(self):
        if self._is_fullscreen:
            self._window.unfullscreen()
        else:
            self._window.fullscreen()

    def _on_key(self, event, pressed):
        key_id = Gdk.keyval_name(event.keyval).upper()
        # print(key_id)

        if pressed and key_id in self._KEY_HANDLERS:
            self._KEY_HANDLERS[key_id]()

        key_info = self.keys.get(key_id, None)
        if key_info:
            self.emulator._pause(False)
            self.emulator._quit_playback_mode()
            self.emulator._handle_key_stroke(key_info, pressed)

    def _on_key_press(self, widget, event):
        self._on_key(event, pressed=True)

    def _on_key_release(self, widget, event):
        self._on_key(event, pressed=False)

    def _on_click(self, widget, event):
        if event.type == Gdk.EventType.BUTTON_PRESS:
            self.emulator._toggle_pause()
            return True
        elif event.type == Gdk.EventType._2BUTTON_PRESS:
            self._toggle_fullscreen()

    def _on_window_state_event(self, widget, event):
        state = event.new_window_state
        self._is_fullscreen = bool(state & Gdk.WindowState.FULLSCREEN)

    def _on_emulator_event(self, id, *args):
        self._EMULATOR_EVENT_HANDLERS[id](*args)

    def _on_updated_pause_state(self):
        if self.emulator._is_paused():
            self._notification.set(draw_pause_notification,
                                   self.emulator._emulation_time)
        else:
            self._notification.clear()

    def _on_updated_tape_state(self):
        tape_paused = self.emulator._is_tape_paused()
        draw = (draw_tape_pause_notification if tape_paused
                else draw_tape_resume_notification)
        tape_time = self.emulator.tape_player.get_time()
        self._notification.set(draw, tape_time)

    def _on_quantum_run(self):
        while Gtk.events_pending():
            Gtk.main_iteration()

        self.area.queue_draw()

    def destroy(self):
        self._window.destroy()

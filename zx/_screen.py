# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2025 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import typing
import cairo
import enum
import gi  # type: ignore
from ._device import Device
from ._device import DeviceEvent
from ._device import GetEmulationPauseState
from ._device import GetEmulationTime
from ._device import GetTapePlayerTime
from ._device import IsTapePlayerPaused
from ._device import KeyStroke
from ._device import LoadFile
from ._device import PauseStateUpdated
from ._device import QuantumRun
from ._device import SaveSnapshot
from ._device import OutputFrame
from ._device import TapeStateUpdated
from ._device import ToggleEmulationPause
from ._device import ToggleTapePause
from ._device import Dispatcher
from ._error import USER_ERRORS
from ._error import verbalize_error
from ._except import EmulationExit
from ._time import get_elapsed_time, get_timestamp, Time
from ._utils import div_ceil
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk  # type: ignore  # nopep8


SCREENCAST = False

PI = 3.1415926535


def rgb(colour: str, alpha: float = 1) -> tuple[float, float, float, float]:
    assert colour.startswith('#')
    assert len(colour) == 7
    r = int(colour[1:3], 16)
    g = int(colour[3:5], 16)
    b = int(colour[5:7], 16)
    return r / 0xff, g / 0xff, b / 0xff, alpha


_Surface = cairo.Surface
_Context: typing.TypeAlias = 'cairo.Context[_Surface]'
_DrawProc = typing.Callable[[_Context, float, float, float, float, float],
                            None]
_Widget: typing.TypeAlias = Gtk.DrawingArea


def _draw_pause_sign(context: _Context, x: float, y: float, size: float,
                     alpha: float) -> None:
    w = 0.1 * size
    h = 0.4 * size
    d = 0.15 * size
    context.rectangle(x - d, y - h / 2, w, h)
    context.rectangle(x + d - w, y - h / 2, w, h)
    context.fill()


def _draw_tape_sign(context: _Context, x: float, y: float, size: float,
                    alpha: float, t: float = 0) -> None:
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


def _draw_notification_circle(context: _Context, x: float, y: float,
                              size: float, alpha: float) -> None:
    context.arc(x, y, size / 2, 0, 2 * PI)
    context.set_source_rgba(*rgb('#1e1e1e', alpha))
    context.fill()


def draw_pause_notification(context: _Context, x: float, y: float, size: float,
                            alpha: float = 1, t: float = 0) -> None:
    _draw_notification_circle(context, x, y, size, alpha)

    context.set_source_rgba(*rgb('#ffffff', alpha))
    _draw_pause_sign(context, x, y, size, alpha)


def draw_tape_pause_notification(context: _Context, x: float, y: float,
                                 size: float, alpha: float = 1,
                                 t: float = 0) -> None:
    _draw_notification_circle(context, x, y, size, alpha)

    context.set_source_rgba(*rgb('#ffffff', alpha))
    _draw_tape_sign(context, x, y - size * 0.13, size * 0.5, alpha, t)
    _draw_pause_sign(context, x, y + size * 0.23, size * 0.5, alpha)


def draw_tape_resume_notification(context: _Context, x: float, y: float,
                                  size: float, alpha: float = 1,
                                  t: float = 0) -> None:
    _draw_notification_circle(context, x, y, size, alpha)

    context.set_source_rgba(*rgb('#ffffff', alpha))
    _draw_tape_sign(context, x, y - size * 0.015, size * 0.6, alpha, t)


class Notification(object):
    _timestamp: None | float
    _draw: None | _DrawProc

    def __init__(self) -> None:
        self.clear()

    def set(self, draw: _DrawProc, time: Time) -> None:
        self._timestamp = get_timestamp()
        self._draw = draw
        self._time = time

    def clear(self) -> None:
        self._timestamp = None
        self._draw = None

    def draw(self, window_size: tuple[int, int], screen_size: tuple[int, int],
             context: _Context) -> None:
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

        assert self._draw is not None
        self._draw(context, x + size / 2, y + size / 2, size, alpha,
                   self._time.get())


# TODO: A quick solution for making screencasts.
class Screencast(object):
    _counter: int

    def __init__(self) -> None:
        self._counter = 0

    def on_draw(self, surface: _Surface) -> None:
        if not SCREENCAST:
            return

        filename = '%05d.png' % self._counter
        surface.write_to_png(filename)
        self._counter += 1


class _KeyEvent(DeviceEvent):
    def __init__(self, id: str, pressed: bool) -> None:
        self.id = id
        self.pressed = pressed


class _ClickType(enum.Enum):
    Single = enum.auto()
    Double = enum.auto()


class _ClickEvent(DeviceEvent):
    def __init__(self, type: _ClickType) -> None:
        self.type = type


class _ExceptionEvent(DeviceEvent):
    def __init__(self, exception: Exception) -> None:
        self.exception = exception


class ScreenWindow(Device):
    _SCREEN_AREA_BACKGROUND_COLOUR = rgb('#1e1e1e')

    _GTK_KEYS_TO_ZX_KEYS = {
        'RETURN': 'ENTER',
        'ALT_L': 'CAPS SHIFT',
        'SHIFT_L': 'CAPS SHIFT',
        'ALT_R': 'SYMBOL SHIFT',
        'SHIFT_R': 'SYMBOL SHIFT'}

    __events: list[DeviceEvent]

    def __init__(self, frame_size: tuple[int, int]) -> None:
        super().__init__()

        self.__events = []

        self._window = Gtk.Window()

        self._KEY_HANDLERS: dict[str, typing.Callable[[Dispatcher], None]] = {
            'ESCAPE': self.__on_exit,
            'F10': self.__on_exit,
            'F1': self._show_help,
            'F2': self._save_snapshot,
            'F3': self._choose_and_load_file,
            'F6': self.__toggle_tape_pause,
            'F11': self._toggle_fullscreen,
            'PAUSE': self.__toggle_pause,
        }

        self._EVENT_HANDLERS: dict[type[DeviceEvent],
                                   typing.Callable[[DeviceEvent, Dispatcher],
                                                   None]] = {
            _ClickEvent: self.__on_click,
            _ExceptionEvent: self.__on_exception,
            _KeyEvent: self.__on_key,
            PauseStateUpdated: self._on_updated_pause_state,
            QuantumRun: self._on_quantum_run,
            OutputFrame: self._on_output_frame,
            TapeStateUpdated: self._on_updated_tape_state,
        }

        self._notification = Notification()
        self._screencast = Screencast()

        # TODO: Hide members like this.
        self.frame_width, self.frame_height = frame_size

        self.scale = 1 if SCREENCAST else 2

        self.area = Gtk.DrawingArea()
        self.area.connect('draw', self._on_draw_area)
        self.area.connect('button-press-event', self.__on_gdk_click)
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
        self._window.connect('delete-event', self._on_done)

        self._window.show_all()

        self.frame_size = self.frame_width * self.frame_height
        self.frame = cairo.ImageSurface(cairo.FORMAT_RGB24,
                                        self.frame_width, self.frame_height)
        self.frame_data = self.frame.get_data()

        self.pattern = cairo.SurfacePattern(self.frame)
        if not SCREENCAST:
            self.pattern.set_filter(cairo.FILTER_NEAREST)

        self.area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                             Gdk.EventMask.BUTTON_RELEASE_MASK)
        self._window.connect('key-press-event', self.__on_gdk_key)
        self._window.connect('key-release-event', self.__on_gdk_key)
        self._window.connect('window-state-event',
                             self.__on_window_state_event)

    def _on_draw_area(self, widget: _Widget, context: _Context) -> None:
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

    # TODO: Rename devices -> dispatcher.
    def _on_output_frame(self, event: DeviceEvent,
                         devices: Dispatcher) -> typing.Any:
        assert isinstance(event, OutputFrame)
        self.frame_data[:] = event.pixels
        self.area.queue_draw()

    def _show_help(self, devices: Dispatcher) -> None:
        KEYS_HELP = [
            ('F1', 'Show help.'),
            ('F2', 'Save snapshot.'),
            ('F3', 'Load snapshot or tape file.'),
            ('F6', 'Pause/resume tape.'),
            ('F10', 'Quit.'),
            ('F11', 'Fullscreen/windowed mode.'),
            ('PAUSE', 'Pause/resume emulation.'),
        ]

        for entry in KEYS_HELP:
            print('%7s  %s' % entry)

    def _save_snapshot(self, devices: Dispatcher) -> None:
        # TODO: Add file filters.
        dialog = Gtk.FileChooserDialog(
            'Save snapshot', self._window,
            Gtk.FileChooserAction.SAVE,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
        dialog.set_do_overwrite_confirmation(True)
        if dialog.run() == Gtk.ResponseType.OK:
            try:
                devices.notify(SaveSnapshot(dialog.get_filename()))
            except USER_ERRORS as e:
                self._error_box('File error', verbalize_error(e))

        dialog.destroy()

    def _error_box(self, title: str, message: str) -> None:
        dialog = Gtk.MessageDialog(
            self._window, 0, Gtk.MessageType.ERROR,
            Gtk.ButtonsType.OK, title)
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def _choose_and_load_file(self, devices: Dispatcher) -> None:
        # TODO: Add file filters.
        dialog = Gtk.FileChooserDialog(
            'Load file', self._window,
            Gtk.FileChooserAction.OPEN,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_OPEN, Gtk.ResponseType.OK))

        filename = None
        if dialog.run() == Gtk.ResponseType.OK:
            filename = dialog.get_filename()

        # Close the dialog window before trying to load the file
        # as that loading may take significant time, e.g., if it
        # implies simulation of key strokes, etc.
        dialog.destroy()

        if filename is not None:
            try:
                devices.notify(LoadFile(filename))
            except USER_ERRORS as e:
                self._error_box('File error', verbalize_error(e))

    def _toggle_fullscreen(self, devices: Dispatcher) -> None:
        if self._is_fullscreen:
            self._window.unfullscreen()
        else:
            self._window.fullscreen()

    def __queue_event(self, event: DeviceEvent) -> None:
        self.__events.append(event)

    def __on_gdk_key(self, widget: _Widget, event: Gdk.EventKey) -> None:
        # TODO: Do not upper the case here. Ignore unknown key.
        # Translate to our own key ids.
        self.__queue_event(_KeyEvent(
            Gdk.keyval_name(event.keyval).upper(),
            event.type == Gdk.EventType.KEY_PRESS))

    def __on_key(self, event: DeviceEvent, devices: Dispatcher) -> typing.Any:
        assert isinstance(event, _KeyEvent)
        if event.pressed and event.id in self._KEY_HANDLERS:
            self._KEY_HANDLERS[event.id](devices)

        zx_key_id = self._GTK_KEYS_TO_ZX_KEYS.get(event.id, event.id)
        devices.notify(KeyStroke(zx_key_id, event.pressed))

    def __on_gdk_click(self, widget: _Widget, event: Gdk.EventButton) -> bool:
        TYPES = {
            Gdk.EventType.BUTTON_PRESS: _ClickType.Single,
            Gdk.EventType._2BUTTON_PRESS: _ClickType.Double,
        }

        if event.type in TYPES:
            self.__queue_event(_ClickEvent(TYPES[event.type]))
            return True

        return False

    def __on_click(self, event: DeviceEvent,
                   devices: Dispatcher) -> typing.Any:
        assert isinstance(event, _ClickEvent)
        if event.type == _ClickType.Single:
            self.__toggle_pause(devices)
        elif event.type == _ClickType.Double:
            self._toggle_fullscreen(devices)

    def __on_exception(self, event: DeviceEvent,
                       devices: Dispatcher) -> typing.Any:
        assert isinstance(event, _ExceptionEvent,)
        raise event.exception

    def __on_exit(self, devices: Dispatcher) -> None:
        self.__queue_event(_ExceptionEvent(EmulationExit()))

    def _on_done(self, widget: _Widget, context: _Context) -> None:
        self.__queue_event(_ExceptionEvent(EmulationExit()))

    def __on_window_state_event(self, widget: _Widget,
                                event: Gdk.EventWindowState) -> None:
        state = event.new_window_state
        self._is_fullscreen = bool(state & Gdk.WindowState.FULLSCREEN)

    def on_event(self, event: DeviceEvent, devices: Dispatcher,
                 result: typing.Any) -> typing.Any:
        event_type = type(event)
        if event_type in self._EVENT_HANDLERS:
            self._EVENT_HANDLERS[event_type](event, devices)
        return result

    def _on_updated_pause_state(self, event: DeviceEvent,
                                devices: Dispatcher) -> None:
        assert isinstance(event, PauseStateUpdated)
        if devices.notify(GetEmulationPauseState()):
            time = devices.notify(GetEmulationTime())
            self._notification.set(draw_pause_notification, time)
        else:
            self._notification.clear()

    def _on_updated_tape_state(self, event: DeviceEvent,
                               devices: Dispatcher) -> None:
        assert isinstance(event, TapeStateUpdated)
        tape_paused = devices.notify(IsTapePlayerPaused())
        draw = (draw_tape_pause_notification if tape_paused
                else draw_tape_resume_notification)
        tape_time = devices.notify(GetTapePlayerTime())
        self._notification.set(draw, tape_time)

    def _on_quantum_run(self, event: DeviceEvent, devices: Dispatcher) -> None:
        assert isinstance(event, QuantumRun)
        self.area.queue_draw()

        while Gtk.events_pending():
            Gtk.main_iteration()

        while self.__events:
            self.on_event(self.__events.pop(0), devices, None)

    def __toggle_pause(self, devices: Dispatcher) -> None:
        devices.notify(ToggleEmulationPause())

    def __toggle_tape_pause(self, devices: Dispatcher) -> None:
        devices.notify(ToggleTapePause())

    def __on_destroy(self, event: DeviceEvent, devices: Dispatcher) -> None:
        self._window.destroy()

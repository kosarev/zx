# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2025 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import cairo
import ctypes
import enum
import gi  # type: ignore
import numpy
import typing
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


# TODO: Remove once the transition to SDL is done.
def xrgb(colour: str, alpha: float = 1) -> tuple[float, float, float, float]:
    assert colour.startswith('#')
    assert len(colour) == 7
    r = int(colour[1:3], 16)
    g = int(colour[3:5], 16)
    b = int(colour[5:7], 16)
    return r / 0xff, g / 0xff, b / 0xff, alpha


def rgb(colour: str, alpha: float = 1) -> tuple[float, float, float, float]:
    assert colour.startswith('#')
    assert len(colour) == 7
    r = int(colour[1:3], 16)
    g = int(colour[3:5], 16)
    b = int(colour[5:7], 16)
    return r, g, b, int(0xff * alpha)


_Renderer = typing.Any
_DrawProc = typing.Callable[
    [_Renderer, float, float, float, float, float],
    None]
_Widget: typing.TypeAlias = Gtk.DrawingArea


def _draw_pause_sign(renderer: int, x: float, y: float,
                     size: float, alpha: float) -> None:
    w = 0.1 * size
    h = 0.4 * size
    d = 0.15 * size

    import sdl2  # type: ignore
    sdl2.SDL_SetRenderDrawColor(renderer, *rgb('#ffffff', alpha))
    sdl2.SDL_RenderFillRect(
        renderer,
        sdl2.SDL_Rect(int(x - d), int(y - h / 2), int(w), int(h)))
    sdl2.SDL_RenderFillRect(
        renderer,
        sdl2.SDL_Rect(int(x + d - w), int(y - h / 2), int(w), int(h)))


def _draw_tape_sign(renderer: _Renderer, x: float, y: float,
                    size: float, alpha: float, t: float = 0) -> None:
    R = 0.10
    D = 0.33 - R
    H = 0.6
    RPM = 11

    # TODO: Animate the reels.
    a = t * -(RPM * 2 * PI / 60)

    import sdl2
    sdl2.SDL_SetRenderDrawColor(renderer, *rgb('#ffffff', alpha))
    sdl2.SDL_RenderDrawRect(
        renderer,
        sdl2.SDL_Rect(int(x - size * 0.5), int(y - size * (H / 2)),
                      int(size), int(size * H)))

    import sdl2.sdlgfx  # type: ignore
    sdl2.sdlgfx.hlineRGBA(
        renderer,
        int(x - size * (D - 0.15)),
        int(x + size * (D - 0.15)),
        int(y - size * R),
        *rgb('#ffffff', alpha))

    sdl2.sdlgfx.aacircleRGBA(renderer, int(x - size * (D - R / 2)), int(y),
                             int(size * R), *rgb('#ffffff', alpha))
    sdl2.sdlgfx.aacircleRGBA(renderer, int(x + size * (D - R / 2)), int(y),
                             int(size * R), *rgb('#ffffff', alpha))


# TODO: Move to the class. +Same for other drawing functions.
def _draw_notification_circle(renderer: _Renderer,
                              x: float, y: float,
                              size: float, alpha: float) -> None:
    import sdl2
    sdl2.SDL_SetRenderDrawColor(renderer, *rgb('#1e1e1e', alpha))
    sdl2.SDL_RenderFillRect(
        renderer,
        sdl2.SDL_Rect(int(x - size / 2), int(y - size / 2),
                      int(size), int(size)))


def draw_pause_notification(renderer: _Renderer,
                            x: float, y: float,
                            size: float, alpha: float = 1,
                            t: float = 0) -> None:
    _draw_notification_circle(renderer, x, y, size, alpha)
    _draw_pause_sign(renderer, x, y, size, alpha)


def draw_tape_pause_notification(renderer: _Renderer,
                                 x: float, y: float,
                                 size: float, alpha: float = 1,
                                 t: float = 0) -> None:
    _draw_notification_circle(renderer, x, y, size, alpha)
    _draw_tape_sign(renderer, x, y - size * 0.13, size * 0.5, alpha, t)
    _draw_pause_sign(renderer, x, y + size * 0.23, size * 0.5, alpha)


def draw_tape_resume_notification(renderer: _Renderer,
                                  x: float, y: float,
                                  size: float, alpha: float = 1,
                                  t: float = 0) -> None:
    _draw_notification_circle(renderer, x, y, size, alpha)
    _draw_tape_sign(renderer, x, y - size * 0.015, size * 0.6, alpha, t)


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
             renderer: _Renderer) -> None:
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
        self._draw(renderer, x + size / 2, y + size / 2, size, alpha,
                   self._time.get())


# TODO: A quick solution for making screencasts.
class Screencast(object):
    _counter: int

    def __init__(self) -> None:
        self._counter = 0

    def on_draw(self, pixel_texture: typing.Any) -> None:
        if not SCREENCAST:
            return

        # TODO
        '''
        filename = '%05d.png' % self._counter
        surface.write_to_png(filename)
        self._counter += 1
        '''


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
    # TODO: Remove.
    _SCREEN_AREA_BACKGROUND_COLOUR = xrgb('#1e1e1e')

    __SDL_KEYS_TO_ZX_KEYS = {
        'RETURN': 'ENTER',
        'LEFT SHIFT': 'CAPS SHIFT',
        'RIGHT SHIFT': 'SYMBOL SHIFT'}

    __events: list[DeviceEvent]

    def __init__(self, frame_size: tuple[int, int]) -> None:
        super().__init__()

        self.__events = []

        # TODO: Hide members like this.
        self.frame_width, self.frame_height = frame_size

        self.scale = 1 if SCREENCAST else 2

        import sdl2
        sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO)

        self.__window = sdl2.SDL_CreateWindow(
            b'ZX Spectrum Emulator',
            sdl2.SDL_WINDOWPOS_CENTERED,
            sdl2.SDL_WINDOWPOS_CENTERED,
            self.frame_width * self.scale,
            self.frame_height * self.scale,
            sdl2.SDL_WINDOW_SHOWN | sdl2.SDL_WINDOW_RESIZABLE)

        rendering_driver_index = -1
        renderer_flags = 0
        self.__renderer = sdl2.SDL_CreateRenderer(
            self.__window, rendering_driver_index, renderer_flags)

        sdl2.SDL_SetRenderDrawBlendMode(self.__renderer,
                                        sdl2.SDL_BLENDMODE_BLEND)

        self.__pixel_texture = sdl2.SDL_CreateTexture(
            self.__renderer,
            sdl2.SDL_PIXELFORMAT_RGB888,
            sdl2.SDL_TEXTUREACCESS_STREAMING,
            self.frame_width, self.frame_height)

        self.__sdl_event = sdl2.SDL_Event()

        self._gtk_window = Gtk.Window()

        self._KEY_HANDLERS: dict[str, typing.Callable[[Dispatcher], None]] = {
            'F10': self.__on_exit,
            'F1': self._show_help,
            'F2': self._save_snapshot,
            'F3': self._choose_and_load_file,
            'F6': self.__toggle_tape_pause,
            'F11': self.__toggle_fullscreen,
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

        self.area = Gtk.DrawingArea()
        self._gtk_window.add(self.area)

        self._gtk_window.set_title('ZX Spectrum Emulator')
        if SCREENCAST:
            width, height = 640, 390
        else:
            width, height = (self.frame_width * self.scale,
                             self.frame_height * self.scale)
        minimum_size = self.frame_width // 4, self.frame_height // 4
        sdl2.SDL_SetWindowMinimumSize(self.__window, *minimum_size)

        self.frame_size = self.frame_width * self.frame_height
        self.frame = cairo.ImageSurface(cairo.FORMAT_RGB24,
                                        self.frame_width, self.frame_height)
        self.frame_data = self.frame.get_data()

        self.pattern = cairo.SurfacePattern(self.frame)
        if not SCREENCAST:
            self.pattern.set_filter(cairo.FILTER_NEAREST)

    def _on_output_frame(self, event: DeviceEvent,
                         dispatcher: Dispatcher) -> typing.Any:
        assert isinstance(event, OutputFrame)
        self.frame_data[:] = event.pixels
        self.area.queue_draw()

        rect = None
        pitch = self.frame_width * 4
        pixels = ctypes.c_void_p(ctypes.addressof(
            ctypes.c_char.from_buffer(bytearray(event.pixels))))
        import sdl2
        sdl2.SDL_UpdateTexture(self.__pixel_texture, rect,
                               pixels, pitch)

    def __update_screen(self) -> None:
        w, h = ctypes.c_int(), ctypes.c_int()
        import sdl2
        sdl2.SDL_GetWindowSize(self.__window, ctypes.byref(w), ctypes.byref(h))
        window_size = window_width, window_height = w.value, h.value
        width = min(window_width,
                    div_ceil(window_height * self.frame_width,
                             self.frame_height))
        height = min(window_height,
                     div_ceil(window_width * self.frame_height,
                              self.frame_width))

        sdl2.SDL_RenderClear(self.__renderer)

        # Draw the background.
        sdl2.SDL_SetRenderDrawColor(self.__renderer, *rgb('#1e1e1e'))
        sdl2.SDL_RenderFillRect(self.__renderer,
                                sdl2.SDL_Rect(0, 0, *window_size))

        # Draw the emulated screen.
        src_rect = None
        sdl2.SDL_RenderCopy(
            self.__renderer, self.__pixel_texture,
            src_rect,
            sdl2.SDL_Rect((window_width - width) // 2,
                          (window_height - height) // 2,
                          width,
                          height))

        # TODO
        self._screencast.on_draw(self.__pixel_texture)

        # Draw notifications.
        self._notification.draw(window_size, (width, height),
                                self.__renderer)

        sdl2.SDL_RenderPresent(self.__renderer)

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

        # TODO: Use the GUI for that.
        for entry in KEYS_HELP:
            print('%7s  %s' % entry)

    def _save_snapshot(self, devices: Dispatcher) -> None:
        # TODO: Add file filters.
        dialog = Gtk.FileChooserDialog(
            'Save snapshot', self._gtk_window,
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
            self._gtk_window, 0, Gtk.MessageType.ERROR,
            Gtk.ButtonsType.OK, title)
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def _choose_and_load_file(self, devices: Dispatcher) -> None:
        # TODO: Add file filters.
        dialog = Gtk.FileChooserDialog(
            'Load file', self._gtk_window,
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

    def __toggle_fullscreen(self, devices: Dispatcher) -> None:
        import sdl2
        flags = sdl2.SDL_GetWindowFlags(self.__window)
        flags &= sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP
        flags ^= sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP
        sdl2.SDL_SetWindowFullscreen(self.__window, flags)

    def __queue_event(self, event: DeviceEvent) -> None:
        self.__events.append(event)

    def __on_sdl_key(self, event: typing.Any) -> None:
        # TODO: Do not upper the case here. Ignore unknown key.
        # Translate to our own key ids.
        import sdl2
        self.__queue_event(_KeyEvent(
            sdl2.SDL_GetKeyName(event.key.keysym.sym).decode('utf-8').upper(),
            event.type == sdl2.SDL_KEYDOWN))

    def __on_key(self, event: DeviceEvent, devices: Dispatcher) -> typing.Any:
        assert isinstance(event, _KeyEvent)
        if event.pressed and event.id in self._KEY_HANDLERS:
            self._KEY_HANDLERS[event.id](devices)

        zx_key_id = self.__SDL_KEYS_TO_ZX_KEYS.get(event.id, event.id)
        devices.notify(KeyStroke(zx_key_id, event.pressed))

    def __on_sdl_click(self, event: typing.Any) -> bool:
        TYPES = {
            1: _ClickType.Single,
            2: _ClickType.Double,
        }

        if event.button.clicks in TYPES:
            self.__queue_event(_ClickEvent(TYPES[event.button.clicks]))
            return True

        return False

    def __on_click(self, event: DeviceEvent,
                   devices: Dispatcher) -> typing.Any:
        assert isinstance(event, _ClickEvent)
        if event.type == _ClickType.Single:
            self.__toggle_pause(devices)
        elif event.type == _ClickType.Double:
            self.__toggle_fullscreen(devices)

    def __on_exception(self, event: DeviceEvent,
                       devices: Dispatcher) -> typing.Any:
        assert isinstance(event, _ExceptionEvent,)
        raise event.exception

    def __on_exit(self, devices: Dispatcher) -> None:
        self.__queue_event(_ExceptionEvent(EmulationExit()))

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

    def _on_quantum_run(self, event: DeviceEvent,
                        dispatcher: Dispatcher) -> None:
        assert isinstance(event, QuantumRun)
        self.area.queue_draw()

        while Gtk.events_pending():
            Gtk.main_iteration()

        import sdl2
        while sdl2.SDL_PollEvent(ctypes.byref(self.__sdl_event)) != 0:
            if self.__sdl_event.type == sdl2.SDL_QUIT:
                self.__on_exit(dispatcher)
            elif self.__sdl_event.type == sdl2.SDL_MOUSEBUTTONDOWN:
                self.__on_sdl_click(self.__sdl_event)
            elif self.__sdl_event.type in (sdl2.SDL_KEYDOWN, sdl2.SDL_KEYUP):
                self.__on_sdl_key(self.__sdl_event)

        while self.__events:
            self.on_event(self.__events.pop(0), dispatcher, None)

        self.__update_screen()

    def __toggle_pause(self, devices: Dispatcher) -> None:
        devices.notify(ToggleEmulationPause())

    def __toggle_tape_pause(self, devices: Dispatcher) -> None:
        devices.notify(ToggleTapePause())

    def __on_destroy(self, event: DeviceEvent, devices: Dispatcher) -> None:
        self._gtk_window.destroy()

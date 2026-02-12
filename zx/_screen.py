# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import ctypes
import enum
import numpy
import tkinter.filedialog
import tkinter.messagebox
import typing

from ._device import Destroy
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


SCREENCAST = False

PI = 3.1415926535


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


class _OverlayScreen:
    # Key button styling.
    __KEY_BUTTON_TEXT_RGB = (230, 230, 230, 255)
    __KEY_BUTTON_BORDER_RGB = (180, 180, 180, 255)
    __KEY_BUTTON_BG_RGB = (50, 50, 50, 255)
    __KEY_BUTTON_H_PADDING_EM = 0.4
    __KEY_BUTTON_V_PADDING_EM = 0.2
    __KEY_BUTTON_BORDER_THICKNESS = 1
    __KEY_BUTTON_FONT_SCALE = 0.85

    # Overlay background styling.
    __OVERLAY_BG_RGBA = (0, 0, 0, 180)

    class __Font:
        def __init__(self, text_size: int) -> None:
            import sdl2
            import sdl2.sdlttf  # type: ignore
            import importlib.resources
            font_path = str(importlib.resources.files('zx').joinpath('fonts')
                            .joinpath('DejaVuSans.ttf'))
            self.font = sdl2.sdlttf.TTF_OpenFont(
                font_path.encode('utf-8'), text_size)
            em_c_width = sdl2.c_int()
            em_c_height = sdl2.c_int()
            sdl2.sdlttf.TTF_SizeText(
                self.font, b'M', em_c_width, em_c_height)
            self.em = em_c_width.value
            self.em_height = em_c_height.value

    def __init__(self) -> None:
        import sdl2
        self.active = False
        self.__window_size: None | tuple[int, int] = None
        self.__texture = None
        self.__normal_font: None | _OverlayScreen.__Font = None
        self.__key_button_font: None | _OverlayScreen.__Font = None
        self.__current_text_size: None | int = None

        # Pre-create colours using RGBA32 format (used by all surfaces).
        format_rgba32 = sdl2.SDL_AllocFormat(sdl2.SDL_PIXELFORMAT_RGBA32)
        self.__key_button_text_colour = sdl2.SDL_Color(
            *self.__KEY_BUTTON_TEXT_RGB)
        self.__key_button_border_colour = sdl2.SDL_MapRGBA(
            format_rgba32, *self.__KEY_BUTTON_BORDER_RGB)
        self.__key_button_bg_colour = sdl2.SDL_MapRGBA(
            format_rgba32, *self.__KEY_BUTTON_BG_RGB)
        self.__overlay_bg_colour = sdl2.SDL_MapRGBA(
            format_rgba32, *self.__OVERLAY_BG_RGBA)
        sdl2.SDL_FreeFormat(format_rgba32)

    def __draw_key_button(self, font: __Font,
                          key_text: str) -> typing.Any:
        """Draw a key name with a kbd-style box around it.

        Returns a surface with the key button, similar to
        TTF_RenderUTF8_Blended. Caller is responsible for freeing the surface.
        """
        import sdl2
        import sdl2.sdlttf

        # Render the text.
        text_surface = sdl2.sdlttf.TTF_RenderUTF8_Blended(
            font.font, key_text.encode('utf-8'),
            self.__key_button_text_colour)

        # Calculate box dimensions with padding.
        h_padding = int(font.em * self.__KEY_BUTTON_H_PADDING_EM)
        v_padding = int(font.em * self.__KEY_BUTTON_V_PADDING_EM)
        box_w = text_surface.contents.w + h_padding * 2
        box_h = text_surface.contents.h + v_padding * 2

        # Create button surface.
        button_surface = sdl2.SDL_CreateRGBSurfaceWithFormat(
            0, box_w, box_h, 32, sdl2.SDL_PIXELFORMAT_RGBA32)

        # Draw background.
        sdl2.SDL_FillRect(button_surface, None,
                          self.__key_button_bg_colour)

        # Draw border.
        t = self.__KEY_BUTTON_BORDER_THICKNESS
        top_line = (0, 0, box_w, t)
        bottom_line = (0, box_h - t, box_w, t)
        left_line = (0, 0, t, box_h)
        right_line = (box_w - t, 0, t, box_h)
        for rect in (top_line, bottom_line, left_line, right_line):
            sdl2.SDL_FillRect(
                button_surface, sdl2.SDL_Rect(*rect),
                self.__key_button_border_colour)

        # Blit text centered in the box.
        sdl2.SDL_BlitSurface(
            text_surface, None, button_surface,
            sdl2.SDL_Rect(h_padding, v_padding,
                          text_surface.contents.w, text_surface.contents.h))

        sdl2.SDL_FreeSurface(text_surface)
        return button_surface

    def __rebuild(self, window_size: tuple[int, int],
                  renderer: _Renderer) -> None:
        assert self.__window_size != window_size

        width, height = window_size

        # TODO: Use TTF_CloseFont().
        import sdl2.sdlttf
        if width < 450 or height < 400:
            text_size = 14
        else:
            text_size = 18

        # Create fonts if text size changed.
        if text_size != self.__current_text_size:
            self.__normal_font = self.__Font(text_size)
            key_button_text_size = int(
                text_size * self.__KEY_BUTTON_FONT_SCALE)
            self.__key_button_font = self.__Font(key_button_text_size)

            self.__current_text_size = text_size

        assert self.__normal_font is not None
        assert self.__key_button_font is not None

        em = self.__normal_font.em
        em_height = self.__normal_font.em_height
        line_height = sdl2.sdlttf.TTF_FontLineSkip(self.__normal_font.font)

        import sdl2
        surface = sdl2.SDL_CreateRGBSurfaceWithFormat(
            0, width, height, 32, sdl2.SDL_PIXELFORMAT_RGBA32)

        sdl2.SDL_FillRect(surface, None, self.__overlay_bg_colour)

        KEYS_HELP = [
            ('F2', 'Save snapshot'),
            ('F3', 'Load snapshot or tape file'),
            ('F6', 'Pause/resume tape'),
            ('F10', 'Quit'),
            ('F11', 'Fullscreen/windowed mode'),
            ('PAUSE', 'Pause/resume emulation'),
        ]

        hotkey_offset = em * 5
        text_box_width = hotkey_offset + em * 14
        text_box_vspacing = line_height * 2.5
        text_box_height = len(KEYS_HELP) * text_box_vspacing
        text_box_x = max(0, (width - text_box_width) // 2)
        text_box_y = max(0, (height - text_box_height) // 2)

        text_colour = sdl2.SDL_Color(230, 230, 230, 255)
        for i, (hotkey, action) in enumerate(KEYS_HELP):
            hotkey_surface = self.__draw_key_button(
                self.__key_button_font, hotkey)
            action_surface = sdl2.sdlttf.TTF_RenderUTF8_Blended(
                self.__normal_font.font, action.encode('utf-8'), text_colour)
            x = text_box_x + hotkey_offset
            y = int(text_box_y + i * text_box_vspacing +
                    (text_box_vspacing - em_height) / 2)
            sdl2.SDL_BlitSurface(
                hotkey_surface, None, surface,
                sdl2.SDL_Rect(x - hotkey_surface.contents.w - em, y,
                              hotkey_surface.contents.w,
                              hotkey_surface.contents.h))
            sdl2.SDL_BlitSurface(
                action_surface, None, surface,
                sdl2.SDL_Rect(x, y,
                              action_surface.contents.w,
                              action_surface.contents.h))
            sdl2.SDL_FreeSurface(hotkey_surface)
            sdl2.SDL_FreeSurface(action_surface)

        texture = sdl2.SDL_CreateTextureFromSurface(renderer, surface)
        sdl2.SDL_SetTextureBlendMode(texture, sdl2.SDL_BLENDMODE_BLEND)

        sdl2.SDL_FreeSurface(surface)

        if self.__texture:
            sdl2.SDL_DestroyTexture(self.__texture)
        self.__texture = texture

        self.__window_size = window_size

    def draw(self, window_size: tuple[int, int], renderer: _Renderer) -> None:
        if not self.active:
            return

        if self.__window_size != window_size:
            self.__rebuild(window_size, renderer)

        import sdl2
        window_width, window_height = window_size
        sdl2.SDL_RenderCopy(renderer, self.__texture, None,
                            sdl2.SDL_Rect(0, 0, window_width, window_height))


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
        sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_GAMECONTROLLER)

        import sdl2.sdlttf
        sdl2.sdlttf.TTF_Init()

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

        self.__pixels = bytearray()

        self.__pixel_texture = sdl2.SDL_CreateTexture(
            self.__renderer,
            sdl2.SDL_PIXELFORMAT_RGB888,
            sdl2.SDL_TEXTUREACCESS_STREAMING,
            self.frame_width, self.frame_height)

        # TODO: Support as an option.
        if False:
            sdl2.SDL_SetTextureScaleMode(self.__pixel_texture,
                                         sdl2.SDL_ScaleModeLinear)

        self.__sdl_event = sdl2.SDL_Event()

        self._KEY_HANDLERS: dict[str, typing.Callable[[Dispatcher], None]] = {
            'F10': self.__on_exit,
            'ESCAPE': self._toggle_sidebar,
            'F1': self._toggle_sidebar,
            'F2': self._save_snapshot,
            'F3': self.__choose_and_load_file,
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
            Destroy: self.__on_destroy,
        }

        self.__sidebar = _OverlayScreen()
        self._notification = Notification()
        self._screencast = Screencast()

        if SCREENCAST:
            width, height = 640, 390
        else:
            width, height = (self.frame_width * self.scale,
                             self.frame_height * self.scale)
        minimum_size = self.frame_width // 4, self.frame_height // 4
        sdl2.SDL_SetWindowMinimumSize(self.__window, *minimum_size)

        self.frame_size = self.frame_width * self.frame_height

        self.__controllers: dict[int, ctypes.c_void_p] = {}

    def _on_output_frame(self, event: DeviceEvent,
                         dispatcher: Dispatcher) -> typing.Any:
        assert isinstance(event, OutputFrame)
        rect = None
        pitch = self.frame_width * 4
        self.__pixels[:] = event.pixels
        pixels = ctypes.c_void_p(ctypes.addressof(
            ctypes.c_char.from_buffer(self.__pixels)))
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

        # Draw sidebar.
        self.__sidebar.draw(window_size, self.__renderer)

        # Draw notifications.
        self._notification.draw(window_size, (width, height),
                                self.__renderer)

        sdl2.SDL_RenderPresent(self.__renderer)

    def _toggle_sidebar(self, devices: Dispatcher) -> None:
        self.__sidebar.active ^= True

    def _save_snapshot(self, devices: Dispatcher) -> None:
        # TODO: Add file filters.
        filename = tkinter.filedialog.asksaveasfilename(
            defaultextension=".z80",
            filetypes=[("All files", "*.*")],
            title="Save snapshot")

        if isinstance(filename, str):
            try:
                devices.notify(SaveSnapshot(filename))
            except USER_ERRORS as e:
                self.__error_box('File error', verbalize_error(e))

    def __error_box(self, title: str, message: str) -> None:
        tkinter.messagebox.showerror(title, message)

    def __choose_and_load_file(self, devices: Dispatcher) -> None:
        # TODO: Add file filters.
        filename = tkinter.filedialog.askopenfilename(
            title="Load file",
            filetypes=[("All Files", "*.*")])

        if isinstance(filename, str):
            try:
                devices.notify(LoadFile(filename))
            except USER_ERRORS as e:
                self.__error_box('File error', verbalize_error(e))

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

    def __on_controller_event(self, event: typing.Any,
                              dispatcher: Dispatcher) -> None:
        # TODO: Have a separate joystick device instead of sending key
        # strokes directly.
        import sdl2
        if event.type == sdl2.SDL_CONTROLLERDEVICEADDED:
            device_index = event.cdevice.which
            if sdl2.SDL_IsGameController(device_index):
                controller = sdl2.SDL_GameControllerOpen(device_index)
                if controller:
                    joystick = sdl2.SDL_GameControllerGetJoystick(controller)
                    instance_id = sdl2.SDL_JoystickInstanceID(joystick)
                    self.__controllers[instance_id] = controller
            return

        if event.type == sdl2.SDL_CONTROLLERDEVICEREMOVED:
            instance_id = event.cdevice.which
            controller = self.__controllers.pop(instance_id, None)
            if controller:
                sdl2.SDL_GameControllerClose(controller)
            return

        if event.type in (sdl2.SDL_CONTROLLERBUTTONUP,
                          sdl2.SDL_CONTROLLERBUTTONDOWN):
            KEYS = {
                sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT: '5',
                sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT: '8',
                sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP: '7',
                sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN: '6',
                sdl2.SDL_CONTROLLER_BUTTON_X: '0',  # Fire.
            }

            button_key = KEYS.get(event.jbutton.button)
            if button_key:
                pressed = event.jbutton.state == sdl2.SDL_PRESSED
                dispatcher.notify(KeyStroke(button_key, pressed))

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
        import sdl2
        while sdl2.SDL_PollEvent(ctypes.byref(self.__sdl_event)) != 0:
            if self.__sdl_event.type == sdl2.SDL_QUIT:
                self.__on_exit(dispatcher)
            elif self.__sdl_event.type == sdl2.SDL_MOUSEBUTTONDOWN:
                self.__on_sdl_click(self.__sdl_event)
            elif self.__sdl_event.type in (sdl2.SDL_KEYDOWN, sdl2.SDL_KEYUP):
                self.__on_sdl_key(self.__sdl_event)
            elif self.__sdl_event.type in (sdl2.SDL_CONTROLLERDEVICEADDED,
                                           sdl2.SDL_CONTROLLERDEVICEREMOVED,
                                           sdl2.SDL_CONTROLLERBUTTONUP,
                                           sdl2.SDL_CONTROLLERBUTTONDOWN):
                self.__on_controller_event(self.__sdl_event, dispatcher)

        while self.__events:
            self.on_event(self.__events.pop(0), dispatcher, None)

        self.__update_screen()

    def __toggle_pause(self, devices: Dispatcher) -> None:
        devices.notify(ToggleEmulationPause())

    def __toggle_tape_pause(self, devices: Dispatcher) -> None:
        devices.notify(ToggleTapePause())

    def __on_destroy(self, event: DeviceEvent, devices: Dispatcher) -> None:
        import sdl2
        sdl2.SDL_DestroyWindow(self.__window)

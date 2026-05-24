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
import os
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

_Colour = tuple[int, int, int, int]


def rgb(colour: str, alpha: float = 1.0) -> _Colour:
    assert colour.startswith('#')
    assert len(colour) == 7
    r = int(colour[1:3], 16)
    g = int(colour[3:5], 16)
    b = int(colour[5:7], 16)
    return r, g, b, int(0xff * alpha)


_SDLWindow = typing.Any
_SDLRenderer = typing.Any
_SDLTexture = typing.Any
_SDLFont = typing.Any


class _Surface:
    def __init__(self, w: float, h: float) -> None:
        import sdl2  # type: ignore[import-untyped]
        self.sdl_surface = sdl2.SDL_CreateRGBSurfaceWithFormat(
            0, round(w), round(h), 32, sdl2.SDL_PIXELFORMAT_RGBA32)

    @classmethod
    def from_sdl(cls, sdl_surface: typing.Any) -> '_Surface':
        self = cls.__new__(cls)
        self.sdl_surface = sdl_surface
        return self

    @property
    def width(self) -> float:
        return float(self.sdl_surface.contents.w)

    @property
    def height(self) -> float:
        return float(self.sdl_surface.contents.h)

    def fill(self, colour: _Colour) -> None:
        import sdl2
        sdl2.SDL_FillRect(
            self.sdl_surface, None,
            sdl2.SDL_MapRGBA(self.sdl_surface.contents.format, *colour))

    def fill_rect(self, x: float, y: float, w: float, h: float,
                  colour: _Colour) -> None:
        import sdl2
        sdl2.SDL_FillRect(
            self.sdl_surface,
            sdl2.SDL_Rect(round(x), round(y), round(w), round(h)),
            sdl2.SDL_MapRGBA(self.sdl_surface.contents.format, *colour))

    def draw_rect(self, x: float, y: float, w: float, h: float,
                  thickness: float, colour: _Colour) -> None:
        self.fill_rect(x, y, w, thickness, colour)
        self.fill_rect(x, y + h - thickness, w, thickness, colour)
        self.fill_rect(x, y, thickness, h, colour)
        self.fill_rect(x + w - thickness, y, thickness, h, colour)

    def blit(self, src: '_Surface', dst_x: float, dst_y: float) -> None:
        import sdl2
        sdl2.SDL_BlitSurface(
            src.sdl_surface, None, self.sdl_surface,
            sdl2.SDL_Rect(round(dst_x), round(dst_y), 0, 0))

    def free(self) -> None:
        import sdl2
        sdl2.SDL_FreeSurface(self.sdl_surface)
        del self.sdl_surface


class _Texture:
    def __init__(self, sdl_texture: _SDLTexture) -> None:
        self.sdl_texture = sdl_texture

    def free(self) -> None:
        import sdl2
        sdl2.SDL_DestroyTexture(self.sdl_texture)
        del self.sdl_texture


class _Renderer:
    def __init__(self, window: _SDLWindow) -> None:
        import sdl2
        rendering_driver_index = -1
        renderer_flags = 0
        self.sdl_renderer = sdl2.SDL_CreateRenderer(
            window, rendering_driver_index, renderer_flags)
        sdl2.SDL_SetRenderDrawBlendMode(
            self.sdl_renderer, sdl2.SDL_BLENDMODE_BLEND)

    def clear(self) -> None:
        import sdl2
        sdl2.SDL_RenderClear(self.sdl_renderer)

    def set_draw_colour(self, colour: _Colour) -> None:
        import sdl2
        sdl2.SDL_SetRenderDrawColor(self.sdl_renderer, *colour)

    def fill_rect(self, x: float, y: float, w: float, h: float) -> None:
        import sdl2
        sdl2.SDL_RenderFillRect(
            self.sdl_renderer,
            sdl2.SDL_Rect(round(x), round(y), round(w), round(h)))

    def copy(self, texture: _Texture,
             x: float, y: float, w: float, h: float) -> None:
        import sdl2
        sdl2.SDL_RenderCopy(self.sdl_renderer, texture.sdl_texture, None,
                            sdl2.SDL_Rect(round(x), round(y),
                                          round(w), round(h)))

    def draw_rect(self, x: float, y: float, w: float, h: float,
                  thickness: float = 1) -> None:
        self.fill_rect(x, y, w, thickness)
        self.fill_rect(x, y + h - thickness, w, thickness)
        self.fill_rect(x, y, thickness, h)
        self.fill_rect(x + w - thickness, y, thickness, h)

    def hline(self, x1: float, x2: float, y: float,
              colour: _Colour) -> None:
        import sdl2.sdlgfx  # type: ignore[import-untyped]
        sdl2.sdlgfx.hlineRGBA(self.sdl_renderer,
                              round(x1), round(x2), round(y), *colour)

    def aacircle(self, x: float, y: float, r: float,
                 colour: _Colour) -> None:
        import sdl2.sdlgfx
        sdl2.sdlgfx.aacircleRGBA(self.sdl_renderer,
                                 round(x), round(y), round(r), *colour)

    def arc(self, x: float, y: float, r: float,
            start: float, end: float, colour: _Colour) -> None:
        import sdl2.sdlgfx
        sdl2.sdlgfx.arcRGBA(self.sdl_renderer,
                            round(x), round(y), round(r),
                            round(start), round(end), *colour)

    def present(self) -> None:
        import sdl2
        sdl2.SDL_RenderPresent(self.sdl_renderer)

    def create_texture_from_surface(self, surface: _Surface) -> _Texture:
        import sdl2
        sdl_texture = sdl2.SDL_CreateTextureFromSurface(
            self.sdl_renderer, surface.sdl_surface)
        sdl2.SDL_SetTextureBlendMode(sdl_texture, sdl2.SDL_BLENDMODE_BLEND)
        return _Texture(sdl_texture)


class _Font:
    def __init__(self, size: float) -> None:
        self.text_size = size

        import importlib.resources
        font_path = str(importlib.resources.files('zx').joinpath('fonts')
                        .joinpath('DejaVuSans.ttf'))

        import sdl2.sdlttf  # type: ignore[import-untyped]
        self.__font = sdl2.sdlttf.TTF_OpenFont(
            font_path.encode('utf-8'), round(size))

        w, h = ctypes.c_int(), ctypes.c_int()
        sdl2.sdlttf.TTF_SizeText(self.__font, b'M', w, h)
        self.em = w.value
        self.em_height = h.value
        self.line_height = sdl2.sdlttf.TTF_FontLineSkip(self.__font)

    def render(self, text: str, colour: _Colour) -> _Surface:
        import sdl2
        import sdl2.sdlttf
        return _Surface.from_sdl(sdl2.sdlttf.TTF_RenderUTF8_Blended(
            self.__font, text.encode('utf-8'), sdl2.SDL_Color(*colour)))


class _Theme:
    __SIGN_COLOUR = '#ffffff'
    __NOTIFICATION_BG_COLOUR = '#1e1e1e'

    window_size: None | tuple[int, int]
    display_scale: None | float
    normal_font: None | _Font
    key_button_font: None | _Font

    def __init__(self) -> None:
        self.window_size = None
        self.display_scale = None
        self.normal_font = None
        self.key_button_font = None

    def scale(self, value: float) -> float:
        assert self.display_scale is not None
        return value * self.display_scale

    def update(self, window_size: tuple[int, int],
               display_scale: float) -> bool:
        changed = (window_size != self.window_size or
                   display_scale != self.display_scale)
        self.window_size = window_size
        self.display_scale = display_scale

        if changed or self.normal_font is None:
            width, height = window_size
            logical_width = width / display_scale
            logical_height = height / display_scale

            # TODO: Use TTF_CloseFont().
            if logical_width < 450 or logical_height < 400:
                text_size = 14
            else:
                text_size = 17

            self.normal_font = _Font(self.scale(text_size))
            self.key_button_font = _Font(self.scale(text_size * 0.85))

        return changed

    def draw_key_button(self, key_text: str) -> _Surface:
        TEXT_RGB: _Colour = (230, 230, 230, 255)
        BORDER_RGB: _Colour = (180, 180, 180, 255)
        BG_RGB: _Colour = (50, 50, 50, 255)
        H_PADDING_EM = 0.4
        V_PADDING_EM = 0.2
        BORDER_THICKNESS = 1

        assert self.key_button_font is not None
        font = self.key_button_font
        # Render the text.
        text_surface = font.render(key_text, TEXT_RGB)

        # Calculate box dimensions with padding.
        h_padding = font.em * H_PADDING_EM
        v_padding = font.em * V_PADDING_EM
        box_w = text_surface.width + h_padding * 2
        box_h = text_surface.height + v_padding * 2

        # Create button surface.
        button_surface = _Surface(box_w, box_h)

        # Draw background.
        button_surface.fill(BG_RGB)

        # Draw border.
        button_surface.draw_rect(0, 0, box_w, box_h,
                                 self.scale(BORDER_THICKNESS), BORDER_RGB)

        # Blit text centered in the box.
        button_surface.blit(text_surface, h_padding, v_padding)

        text_surface.free()
        return button_surface

    def draw_pause_sign(self, renderer: _Renderer, x: float, y: float,
                        size: float, alpha: float) -> None:
        w = 0.1 * size
        h = 0.4 * size
        d = 0.15 * size

        renderer.set_draw_colour(rgb(self.__SIGN_COLOUR, alpha))
        renderer.fill_rect(x - d, y - h / 2, w, h)
        renderer.fill_rect(x + d - w, y - h / 2, w, h)

    def draw_tape_pause_sign(self, renderer: _Renderer, x: float, y: float,
                             size: float, alpha: float, t: float) -> None:
        self.draw_tape_sign(renderer, x, y - size * 0.13, size * 0.5,
                            alpha, t)
        self.draw_pause_sign(renderer, x, y + size * 0.23, size * 0.5, alpha)

    def draw_notification_background(self, renderer: _Renderer, x: float,
                                     y: float, size: float,
                                     alpha: float) -> None:
        renderer.set_draw_colour(rgb(self.__NOTIFICATION_BG_COLOUR, alpha))
        renderer.fill_rect(x - size / 2, y - size / 2, size, size)

    def draw_tape_sign(self, renderer: _Renderer, x: float, y: float,
                       size: float, alpha: float, t: float = 0) -> None:
        H = 0.6
        colour = rgb(self.__SIGN_COLOUR, alpha)
        renderer.set_draw_colour(colour)
        renderer.draw_rect(x - size * 0.5, y - size * (H / 2),
                           size, size * H, self.scale(1))

        R = 0.10
        D = 0.33 - R
        renderer.hline(x - size * (D - 0.15), x + size * (D - 0.15),
                       y - size * R, colour)

        RPM = 15
        a = t * -(RPM * 2 * PI / 60)
        REEL_GAP = 0.7 * 180 / PI
        REEL_PHASE = 36
        a_deg = a * 180 / PI
        reel_d = size * (D - R / 2)
        renderer.arc(x - reel_d, y, size * R,
                     a_deg, a_deg + 360 - REEL_GAP, colour)
        renderer.arc(x + reel_d, y, size * R,
                     a_deg + REEL_PHASE, a_deg + REEL_PHASE + 360 - REEL_GAP,
                     colour)


class Notification(object):
    _timestamp: None | float

    def __init__(self, time: Time) -> None:
        self._timestamp = get_timestamp()
        self._time = time

    def clear(self) -> None:
        self._timestamp = None

    def _draw(self, theme: _Theme, renderer: _Renderer, x: float, y: float,
              size: float, alpha: float, t: float) -> None:
        raise NotImplementedError

    def draw(self, window_size: tuple[int, int], screen_size: tuple[int, int],
             renderer: _Renderer, theme: _Theme) -> None:
        if not self._timestamp:
            return

        assert theme.display_scale is not None
        width, height = screen_size
        window_width, window_height = window_size

        size = min(80 * theme.display_scale, width * 0.2)
        x = (window_width - size) // 2
        y = (window_height - size) // 2

        alpha = 1.5 - get_elapsed_time(self._timestamp)
        alpha = max(0, min(0.7, alpha))

        if not alpha:
            self.clear()
            return

        cx = x + size / 2
        cy = y + size / 2
        t = self._time.get()
        theme.draw_notification_background(renderer, cx, cy, size, alpha)
        self._draw(theme, renderer, cx, cy, size, alpha, t)


class PauseNotification(Notification):
    def _draw(self, theme: _Theme, renderer: _Renderer, x: float, y: float,
              size: float, alpha: float, t: float) -> None:
        theme.draw_pause_sign(renderer, x, y, size, alpha)


class TapePauseNotification(Notification):
    def _draw(self, theme: _Theme, renderer: _Renderer, x: float, y: float,
              size: float, alpha: float, t: float) -> None:
        theme.draw_tape_pause_sign(renderer, x, y, size, alpha, t)


class TapeResumeNotification(Notification):
    def _draw(self, theme: _Theme, renderer: _Renderer, x: float, y: float,
              size: float, alpha: float, t: float) -> None:
        theme.draw_tape_sign(renderer, x, y - size * 0.015, size * 0.6,
                             alpha, t)


class _MenuItem:
    x: float
    y: float
    width: float
    height: float
    __hotkey_surface: None | _Surface
    __label_surface: None | _Surface
    __hotkey_x: float
    __label_x: float
    __content_y: float

    def __init__(self, hotkey: str, label: str) -> None:
        self.hotkey = hotkey
        self.label = label
        self.x = 0.0
        self.y = 0.0
        self.width = 0.0
        self.height = 0.0
        self.__hotkey_surface = None
        self.__label_surface = None
        self.__hotkey_x = 0.0
        self.__label_x = 0.0
        self.__content_y = 0.0

    def rebuild(self, theme: _Theme) -> None:
        assert theme.normal_font is not None
        font = theme.normal_font
        TEXT_RGB: _Colour = (230, 230, 230, 255)
        if self.__hotkey_surface:
            self.__hotkey_surface.free()
        if self.__label_surface:
            self.__label_surface.free()
        self.__hotkey_surface = theme.draw_key_button(self.hotkey)
        self.__label_surface = font.render(self.label, TEXT_RGB)
        self.__label_x = font.em * 5
        self.__hotkey_x = (self.__label_x
                           - self.__hotkey_surface.width - font.em)
        content_height = max(self.__hotkey_surface.height,
                             self.__label_surface.height)
        padding = content_height * 0.7
        self.height = content_height + padding
        self.__content_y = padding / 2
        self.width = self.__label_x + self.__label_surface.width

    def draw(self, surface: _Surface, theme: _Theme, font: _Font,
             parent_x: float = 0.0, parent_y: float = 0.0) -> None:
        assert self.__hotkey_surface is not None
        assert self.__label_surface is not None
        x = parent_x + self.x
        y = parent_y + self.y + self.__content_y
        surface.blit(self.__hotkey_surface, x + self.__hotkey_x, y)
        surface.blit(self.__label_surface, x + self.__label_x, y)


class _Menu:
    x: float
    y: float
    width: float
    height: float

    def __init__(self, items: list[_MenuItem]) -> None:
        self.__items = items
        self.x = 0.0
        self.y = 0.0
        self.width = 0.0
        self.height = 0.0

    def rebuild(self, theme: _Theme) -> None:
        font = theme.normal_font
        assert font is not None
        padding = font.em * 3
        items_width = 0.0
        self.height = 0.0
        for item in self.__items:
            item.rebuild(theme)
            item.x = padding
            item.y = self.height
            items_width = max(items_width, item.width)
            self.height += item.height
        self.width = items_width + 2 * padding

    def item_at(self, x: float, y: float) -> None | _MenuItem:
        if not (0 <= y < self.height):
            return None
        for item in self.__items:
            if item.y <= y < item.y + item.height:
                return item
        return None

    def draw(self, surface: _Surface, theme: _Theme, font: _Font) -> None:
        for item in self.__items:
            item.draw(surface, theme, font, self.x, self.y)


class _OverlayScreen:
    # Overlay background styling.
    __OVERLAY_BG_RGBA = (0, 0, 0, 180)

    __texture: None | _Texture
    __selected_item: None | _MenuItem

    def __init__(self, theme: _Theme) -> None:
        self.active = False
        self.__theme = theme
        self.__texture = None
        self.__selected_item = None

        self.__emulation_item = _MenuItem('PAUSE', '')
        self.__tape_item = _MenuItem('F6', '')
        self.__menu = _Menu([
            _MenuItem('ESC', 'Toggle help'),
            _MenuItem('F3', 'Load snapshot or tape file'),
            _MenuItem('F2', 'Save snapshot'),
            self.__emulation_item,
            self.__tape_item,
            _MenuItem('F11', 'Toggle fullscreen'),
            _MenuItem('F10', 'Quit'),
        ])

    def invalidate(self) -> None:
        if self.__texture:
            self.__texture.free()
        self.__texture = None
        self.__selected_item = None

    def on_mouse_move(self, x: int, y: int) -> None:
        self.__selected_item = self.__menu.item_at(
            x - self.__menu.x, y - self.__menu.y)

    def __rebuild(self, renderer: _Renderer, dispatcher: Dispatcher) -> None:
        assert self.__texture is None

        theme = self.__theme
        assert theme.normal_font is not None
        assert theme.key_button_font is not None

        assert theme.window_size is not None
        width, height = theme.window_size

        font = theme.normal_font

        surface = _Surface(width, height)
        surface.fill(self.__OVERLAY_BG_RGBA)

        emulation_paused = dispatcher.notify(GetEmulationPauseState())
        self.__emulation_item.label = ('Resume emulation' if emulation_paused
                                       else 'Pause emulation')
        tape_paused = dispatcher.notify(IsTapePlayerPaused())
        self.__tape_item.label = 'Resume tape' if tape_paused else 'Pause tape'

        self.__menu.rebuild(theme)
        self.__menu.x = max(0, (width - self.__menu.width) // 2)
        self.__menu.y = max(0, (height - self.__menu.height) // 2)
        self.__menu.draw(surface, theme, font)

        texture = renderer.create_texture_from_surface(surface)
        surface.free()

        self.__texture = texture

    def toggle(self) -> None:
        self.active ^= True

    def on_event(self, event: DeviceEvent, dispatcher: Dispatcher) -> None:
        if isinstance(event, (PauseStateUpdated, TapeStateUpdated)):
            self.invalidate()

    def draw(self, renderer: _Renderer, dispatcher: Dispatcher) -> None:
        if not self.active:
            return

        if self.__texture is None:
            self.__rebuild(renderer, dispatcher)

        assert self.__texture is not None
        assert self.__theme.window_size is not None
        renderer.copy(self.__texture, 0, 0, *self.__theme.window_size)

        if self.__selected_item is not None:
            item = self.__selected_item
            renderer.set_draw_colour((255, 255, 255, 30))
            renderer.fill_rect(self.__menu.x,
                               self.__menu.y + item.y,
                               self.__menu.width, item.height)


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

        if ('WAYLAND_DISPLAY' in os.environ and
                'SDL_VIDEODRIVER' not in os.environ):
            os.environ['SDL_VIDEODRIVER'] = 'wayland'

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
            sdl2.SDL_WINDOW_SHOWN | sdl2.SDL_WINDOW_RESIZABLE |
            sdl2.SDL_WINDOW_ALLOW_HIGHDPI)

        self.__renderer = _Renderer(self.__window)

        self.__pixels = bytearray()

        self.__pixel_texture = _Texture(sdl2.SDL_CreateTexture(
            self.__renderer.sdl_renderer,
            sdl2.SDL_PIXELFORMAT_RGB888,
            sdl2.SDL_TEXTUREACCESS_STREAMING,
            self.frame_width, self.frame_height))

        # TODO: Support as an option.
        if False:
            sdl2.SDL_SetTextureScaleMode(self.__pixel_texture.sdl_texture,
                                         sdl2.SDL_ScaleModeLinear)

        self.__sdl_event = sdl2.SDL_Event()

        self._KEY_HANDLERS: dict[str, typing.Callable[[Dispatcher], None]] = {
            'F10': self.__on_exit,
            'ESCAPE': self._toggle_overlay,
            'F1': self._toggle_overlay,
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

        self.__theme = _Theme()
        self.__overlay = _OverlayScreen(self.__theme)
        self._notification: None | Notification = None
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
        sdl2.SDL_UpdateTexture(self.__pixel_texture.sdl_texture, rect,
                               pixels, pitch)

    def __update_screen(self, dispatcher: Dispatcher) -> None:
        w, h = ctypes.c_int(), ctypes.c_int()
        lw, lh = ctypes.c_int(), ctypes.c_int()
        import sdl2
        sdl2.SDL_GetRendererOutputSize(self.__renderer.sdl_renderer,
                                       ctypes.byref(w), ctypes.byref(h))
        sdl2.SDL_GetWindowSize(self.__window, ctypes.byref(lw),
                               ctypes.byref(lh))
        window_size = window_width, window_height = w.value, h.value
        display_scale = w.value / lw.value
        if self.__theme.update(window_size, display_scale):
            self.__overlay.invalidate()
        width = min(window_width,
                    div_ceil(window_height * self.frame_width,
                             self.frame_height))
        height = min(window_height,
                     div_ceil(window_width * self.frame_height,
                              self.frame_width))

        self.__renderer.clear()

        # Draw the background.
        self.__renderer.set_draw_colour(rgb('#1e1e1e'))
        self.__renderer.fill_rect(0, 0, *window_size)

        # Draw the emulated screen.
        self.__renderer.copy(self.__pixel_texture,
                             (window_width - width) // 2,
                             (window_height - height) // 2,
                             width, height)

        # TODO
        self._screencast.on_draw(self.__pixel_texture)

        # Draw overlay screen.
        self.__overlay.draw(self.__renderer, dispatcher)

        # Draw notifications.
        if self._notification and not self.__overlay.active:
            self._notification.draw(window_size, (width, height),
                                    self.__renderer, self.__theme)

        self.__renderer.present()

    def _toggle_overlay(self, devices: Dispatcher) -> None:
        self.__overlay.toggle()

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

        if not self.__overlay.active:
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
        if self.__overlay.active:
            return
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
        self.__overlay.on_event(event, devices)

        event_type = type(event)
        if event_type in self._EVENT_HANDLERS:
            self._EVENT_HANDLERS[event_type](event, devices)
        return result

    def _on_updated_pause_state(self, event: DeviceEvent,
                                devices: Dispatcher) -> None:
        assert isinstance(event, PauseStateUpdated)
        if devices.notify(GetEmulationPauseState()):
            time = devices.notify(GetEmulationTime())
            self._notification = PauseNotification(time)
        else:
            self._notification = None

    def _on_updated_tape_state(self, event: DeviceEvent,
                               devices: Dispatcher) -> None:
        assert isinstance(event, TapeStateUpdated)
        tape_paused = devices.notify(IsTapePlayerPaused())
        tape_time = devices.notify(GetTapePlayerTime())
        if tape_paused:
            self._notification = TapePauseNotification(tape_time)
        else:
            self._notification = TapeResumeNotification(tape_time)

    def _on_quantum_run(self, event: DeviceEvent,
                        dispatcher: Dispatcher) -> None:
        assert isinstance(event, QuantumRun)
        import sdl2
        while sdl2.SDL_PollEvent(ctypes.byref(self.__sdl_event)) != 0:
            if self.__sdl_event.type == sdl2.SDL_QUIT:
                self.__on_exit(dispatcher)
            elif self.__sdl_event.type == sdl2.SDL_MOUSEMOTION:
                e = self.__sdl_event.motion
                scale = self.__theme.display_scale or 1.0
                self.__overlay.on_mouse_move(
                    round(e.x * scale), round(e.y * scale))
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

        self.__update_screen(dispatcher)

    def __toggle_pause(self, devices: Dispatcher) -> None:
        devices.notify(ToggleEmulationPause())

    def __toggle_tape_pause(self, devices: Dispatcher) -> None:
        devices.notify(ToggleTapePause())

    def __on_destroy(self, event: DeviceEvent, devices: Dispatcher) -> None:
        import sdl2
        sdl2.SDL_DestroyWindow(self.__window)

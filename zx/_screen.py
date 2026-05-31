# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import ctypes
import abc
import enum
import numpy
import os
import typing

from ._device import Destroy
from ._device import Device
from ._device import DeviceEvent
from ._device import EmulatorReset
from ._device import GetEmulationPauseState
from ._device import GetEmulationTime
from ._device import GetMainMenuItems
from ._device import GetTapePlayerTime
from ._device import IsTapePlayerPaused
from ._device import KeyStroke
from ._device import LoadFile
from ._device import MenuItemDescriptor
from ._device import MenuItemHit
from ._device import PauseStateUpdated
from ._device import RequestLoadFile
from ._device import RequestSaveSnapshot
from ._device import QuantumRun
from ._device import SaveSnapshot
from ._device import OutputFrame
from ._device import TapeStateUpdated
from ._device import ToggleEmulationPause
from ._device import ToggleFullscreen
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

    def set_clip_rect(self, x: float, y: float,
                      w: float, h: float) -> None:
        import sdl2
        sdl2.SDL_SetClipRect(
            self.sdl_surface,
            sdl2.SDL_Rect(round(x), round(y), round(w), round(h)))

    def clear_clip_rect(self) -> None:
        import sdl2
        sdl2.SDL_SetClipRect(self.sdl_surface, None)

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
        self.em = float(w.value)
        self.em_height = float(h.value)
        self.line_height = float(sdl2.sdlttf.TTF_FontLineSkip(self.__font))

    def free(self) -> None:
        import sdl2.sdlttf
        sdl2.sdlttf.TTF_CloseFont(self.__font)

    def render(self, text: str, colour: _Colour,
               wrap_width: float = 0) -> _Surface:
        import sdl2
        import sdl2.sdlttf
        return _Surface.from_sdl(sdl2.sdlttf.TTF_RenderUTF8_Blended_Wrapped(
            self.__font, text.encode('utf-8'), sdl2.SDL_Color(*colour),
            round(wrap_width)))


class _Theme:
    __SIGN_COLOUR = '#ffffff'
    __NOTIFICATION_BG_COLOUR = '#1e1e1e'
    overlay_bg = rgb('#000000', 0.75)

    window_size: None | tuple[int, int]
    display_scale: None | float
    normal_font: None | _Font
    title_font: None | _Font
    key_button_font: None | _Font

    def __init__(self) -> None:
        self.window_size = None
        self.display_scale = None
        self.normal_font = None
        self.title_font = None
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

            if logical_width < 450 or logical_height < 400:
                text_size = 14
            else:
                text_size = 17

            for font in (self.normal_font, self.title_font,
                         self.key_button_font):
                if font is not None:
                    font.free()

            self.normal_font = _Font(self.scale(text_size))
            self.title_font = _Font(self.scale(text_size * 1.3))
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

    def draw_action_hint(self, hotkey: None | str, label: str,
                         ) -> tuple[_Surface, float]:
        assert self.normal_font is not None
        font = self.normal_font
        TEXT_RGB: _Colour = (230, 230, 230, 255)

        label_surface = font.render(label, TEXT_RGB)
        label_width = label_surface.width

        if hotkey is None:
            return label_surface, label_width

        import sdl2
        key_surface = self.draw_key_button(hotkey)

        # Must be integer so that surface.width - label_width reliably gives
        # the hotkey side width.
        gap = round(font.em * 0.5)

        hotkey_width = key_surface.width
        content_h = max(key_surface.height, label_surface.height)
        total_w = hotkey_width + gap + label_width

        result = _Surface(total_w, content_h)
        sdl2.SDL_SetSurfaceBlendMode(result.sdl_surface,
                                     sdl2.SDL_BLENDMODE_BLEND)
        result.fill((0, 0, 0, 0))
        result.blit(key_surface, 0,
                    (content_h - key_surface.height) / 2)
        key_surface.free()
        result.blit(label_surface, hotkey_width + gap,
                    (content_h - label_surface.height) / 2)
        label_surface.free()
        return result, label_width

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


class _Control:
    x: float
    y: float
    width: float
    height: float

    def contains(self, x: float, y: float) -> bool:
        return (self.x <= x < self.x + self.width and
                self.y <= y < self.y + self.height)

    def highlight(self, renderer: _Renderer) -> None:
        pass


class _Button(_Control):
    label_width: float
    v_padding: float
    min_width: float

    def __init__(self, label: str,
                 hotkey: None | str = None) -> None:
        self.label = label
        self.hotkey = hotkey
        self.__surface: None | _Surface = None
        self.x = 0.0
        self.y = 0.0
        self.width = 0.0
        self.height = 0.0
        self.label_width = 0.0
        self.v_padding = 0.0
        self.min_width = 0.0
        self.__content_x = 0.0

    def rebuild(self, theme: _Theme) -> None:
        if self.__surface is not None:
            self.__surface.free()
        surface, self.label_width = theme.draw_action_hint(
            self.hotkey, self.label)
        self.__surface = surface
        self.width = max(surface.width, self.min_width)
        self.height = surface.height + self.v_padding * 2
        self.__content_x = (self.width - surface.width) / 2

    def contains(self, x: float, y: float) -> bool:
        return (self.x <= x < self.x + self.width and
                self.y <= y < self.y + self.height)

    def free(self) -> None:
        if self.__surface is not None:
            self.__surface.free()
            self.__surface = None

    def highlight(self, renderer: _Renderer) -> None:
        renderer.set_draw_colour((255, 255, 255, 30))
        renderer.fill_rect(self.x, self.y, self.width, self.height)

    def draw(self, target: _Surface,
             parent_x: float = 0.0, parent_y: float = 0.0) -> None:
        assert self.__surface is not None
        target.blit(self.__surface,
                    parent_x + self.x + self.__content_x,
                    parent_y + self.y + self.v_padding)


class _MenuItem(_Button):
    def __init__(self, descriptor: MenuItemDescriptor) -> None:
        super().__init__(descriptor.label, descriptor.hotkey)
        self.descriptor = descriptor

    def rebuild(self, theme: _Theme) -> None:
        assert theme.normal_font is not None
        self.v_padding = theme.normal_font.line_height * 0.35
        self.label = self.descriptor.label
        self.hotkey = self.descriptor.hotkey
        super().rebuild(theme)


class _TextInput(_Control):
    v_padding: float
    h_padding: float
    min_width: float

    def __init__(self) -> None:
        self.text = ''
        self.x = 0.0
        self.y = 0.0
        self.width = 0.0
        self.height = 0.0
        self.v_padding = 0.0
        self.h_padding = 0.0
        self.min_width = 0.0
        self.__font: None | _Font = None

    def rebuild(self, theme: _Theme) -> None:
        assert theme.normal_font is not None
        self.__font = theme.normal_font
        self.height = theme.normal_font.line_height + self.v_padding * 2
        self.width = self.min_width

    def highlight(self, renderer: _Renderer) -> None:
        renderer.set_draw_colour((255, 255, 255, 30))
        renderer.fill_rect(self.x, self.y, self.width, self.height)

    def draw(self, target: _Surface,
             parent_x: float = 0.0, parent_y: float = 0.0) -> None:
        assert self.__font is not None
        BG: _Colour = (20, 20, 20, 220)
        TEXT: _Colour = (230, 230, 230, 255)
        x = parent_x + self.x
        y = parent_y + self.y
        target.fill_rect(x, y, self.width, self.height, BG)
        text_surface = self.__font.render(self.text + '|', TEXT)
        target.blit(text_surface, x + self.h_padding, y + self.v_padding)
        text_surface.free()


class _Menu(_Control):
    min_width: float
    indent: float
    padding: float
    max_height: float

    def __init__(self, items: list[_MenuItem]) -> None:
        self.selected_item: None | _MenuItem = None
        self.__view_y = 0.0
        self.__total_height = 0.0
        self.__line_height = 0.0
        self.x = 0.0
        self.y = 0.0
        self.width = 0.0
        self.height = 0.0
        self.min_width = 0.0
        self.indent = 0.0
        self.padding = 0.0
        self.max_height = float('inf')
        self.items = items

    @property
    def items(self) -> list[_MenuItem]:
        return self.__items

    @items.setter
    def items(self, value: list[_MenuItem]) -> None:
        self.__items = value
        selected = self.selected_item
        if selected is not None:
            self.selected_item = next(
                (item for item in value
                 if item.descriptor is selected.descriptor), None)

    def rebuild(self, theme: _Theme) -> None:
        total_height = 0.0
        for item in self.items:
            item.rebuild(theme)
            item.y = total_height
            total_height += item.height

        max_label_offset = max(
            (item.width - item.label_width for item in self.items),
            default=0.0)
        for item in self.items:
            item.x = max_label_offset - (item.width - item.label_width)

        items_width = max(
            (item.x + item.width for item in self.items), default=0.0)

        self.__total_height = total_height
        assert theme.normal_font is not None
        self.__line_height = theme.normal_font.line_height
        self.width = max(items_width, self.min_width)
        self.height = min(total_height, self.max_height)

        item_x = (self.width - items_width) * self.indent + self.padding
        for item in self.items:
            item.x += item_x

    def __compute_step(self, selected: None | _MenuItem, view_y: float,
                       down: bool) -> tuple[_MenuItem, float]:
        if selected is None:
            return self.items[0 if down else -1], view_y

        idx = self.items.index(selected)
        new_idx = idx + (1 if down else -1)
        if not (0 <= new_idx < len(self.items)):
            return selected, view_y

        item = self.items[new_idx]
        if down:
            view_y = max(view_y, item.y + item.height - self.max_height)
        else:
            view_y = min(view_y, item.y)
        return item, view_y

    def __select_adjacent(self, down: bool) -> bool:
        if not self.items:
            return False
        old_view_y = self.__view_y
        self.selected_item, self.__view_y = self.__compute_step(
            self.selected_item, self.__view_y, down)
        return self.__view_y != old_view_y

    def select_next(self) -> bool:
        return self.__select_adjacent(down=True)

    def select_prev(self) -> bool:
        return self.__select_adjacent(down=False)

    def __select_page(self, down: bool) -> bool:
        if not self.items:
            return False
        if self.selected_item is None:
            return self.__select_adjacent(down)

        # Shift the view by one page, keeping one row visible for context.
        sign = 1.0 if down else -1.0
        shift = self.max_height - self.__line_height * 2
        limit = max(0.0, self.__total_height - self.max_height)
        new_view_y = max(0.0, min(self.__view_y + sign * shift, limit))
        if new_view_y == self.__view_y:
            # No more pages; jump to the first/last item.
            self.selected_item = self.items[-1 if down else 0]
            return False

        # Select the item at the same visual offset in the new view.
        item_mid = self.selected_item.y + self.selected_item.height / 2
        target_y = new_view_y + (item_mid - self.__view_y)
        new_item = self.__item_at(target_y) or self.items[-1 if down else 0]

        # Ensure the item's top is visible.
        new_view_y = min(new_view_y, new_item.y)

        self.selected_item = new_item
        self.__view_y = new_view_y
        return True

    def select_page_down(self) -> bool:
        return self.__select_page(down=True)

    def select_page_up(self) -> bool:
        return self.__select_page(down=False)

    def scroll_to_selected(self) -> None:
        if self.selected_item is None:
            return
        item = self.selected_item
        self.__view_y = min(self.__view_y, item.y)
        self.__view_y = max(self.__view_y,
                            item.y + item.height - self.max_height)
        self.__view_y = max(0.0, self.__view_y)

    def select_first(self) -> bool:
        if not self.items:
            return False
        self.selected_item = self.items[0]
        old_view_y = self.__view_y
        self.__view_y = 0.0
        return self.__view_y != old_view_y

    def select_last(self) -> bool:
        if not self.items:
            return False
        self.selected_item = self.items[-1]
        old_view_y = self.__view_y
        limit = max(0.0, self.__total_height - self.max_height)
        self.__view_y = limit
        return self.__view_y != old_view_y

    def on_key(self, key_id: str) -> None | bool:
        if key_id == 'DOWN':
            return self.select_next()
        if key_id == 'UP':
            return self.select_prev()
        if key_id == 'PAGEDOWN':
            return self.select_page_down()
        if key_id == 'PAGEUP':
            return self.select_page_up()
        if key_id == 'HOME':
            return self.select_first()
        if key_id == 'END':
            return self.select_last()
        return None

    def scroll(self, delta: int) -> bool:
        old = self.__view_y
        dy = -delta * self.__line_height * 3
        limit = max(0.0, self.__total_height - self.max_height)
        self.__view_y = max(0.0, min(self.__view_y + dy, limit))
        return self.__view_y != old

    def select_by_descriptor(self,
                             descriptor: MenuItemDescriptor) -> None:
        for item in self.items:
            if item.descriptor is descriptor:
                self.selected_item = item
                return

    def __item_at(self, y: float) -> None | _MenuItem:
        for item in self.items:
            if item.y <= y < item.y + item.height:
                return item
        return None

    def select_at(self, x: float, y: float) -> None:
        if not (0 <= y < self.height):
            self.selected_item = None
            return
        item = self.__item_at(y + self.__view_y)
        if item is not None:
            self.selected_item = item

    def highlight(self, renderer: _Renderer) -> None:
        if self.selected_item is None:
            return
        item = self.selected_item
        # Clip to visible area.
        top = max(self.y + item.y - self.__view_y, self.y)
        bottom = min(self.y + item.y - self.__view_y + item.height,
                     self.y + self.height)
        if bottom <= top:
            return
        renderer.set_draw_colour((255, 255, 255, 30))
        renderer.fill_rect(self.x, top, self.width, bottom - top)

    def draw(self, surface: _Surface) -> None:
        surface.set_clip_rect(self.x, self.y, self.width, self.height)
        for item in self.items:
            if item.y + item.height <= self.__view_y:
                continue
            if item.y >= self.__view_y + self.max_height:
                break
            item.draw(surface, self.x, self.y - self.__view_y)
        surface.clear_clip_rect()


class _KeyEvent(DeviceEvent):
    def __init__(self, id: str, pressed: bool) -> None:
        self.id = id
        self.pressed = pressed


class _ClickType(enum.Enum):
    Single = enum.auto()
    Double = enum.auto()


class _ClickEvent(DeviceEvent):
    def __init__(self, type: _ClickType, x: float, y: float) -> None:
        self.type = type
        self.x = x
        self.y = y


class _MouseMoveEvent(DeviceEvent):
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y


class _ScrollEvent(DeviceEvent):
    def __init__(self, delta: int) -> None:
        self.delta = delta


class _TextInputEvent(DeviceEvent):
    def __init__(self, text: str) -> None:
        self.text = text


class _TogglePanel(DeviceEvent):
    pass


class _ShowMainMenu(DeviceEvent):
    pass


class _ShowError(DeviceEvent):
    def __init__(self, message: str) -> None:
        self.message = message


class _DismissError(DeviceEvent):
    pass


class _ConfirmOverwrite(DeviceEvent):
    pass


class _RequestResetMachine(DeviceEvent):
    pass


class _ConfirmReset(DeviceEvent):
    pass


class _UIEmulatorReset(EmulatorReset):
    pass


class _ExceptionEvent(DeviceEvent):
    def __init__(self, exception: Exception) -> None:
        self.exception = exception


class _Exit(_ExceptionEvent):
    def __init__(self) -> None:
        super().__init__(EmulationExit())


class _Panel(abc.ABC):
    def __init__(self, theme: '_Theme') -> None:
        self._theme = theme
        self._controls: list[_Control] = []
        self._selected_control: None | _Control = None
        self._dialog: None | '_Panel' = None

    def invalidate(self) -> None:
        if self._dialog is not None:
            self._dialog.invalidate()

    def activate(self) -> None:
        self._dialog = None
        self.invalidate()

    def on_event(self, event: DeviceEvent,
                 dispatcher: Dispatcher) -> None:
        if isinstance(event, _ShowError):
            self._dialog = _MessageDialog(
                self._theme, 'Error', (80, 20, 20, 255), event.message,
                [('Close', 'ESC', _DismissError)])
            return

        if isinstance(event, _DismissError):
            self._dialog = None
            return

        if self._dialog is not None:
            self._dialog.on_event(event, dispatcher)
            return

        if isinstance(event, _KeyEvent) and event.pressed:
            if event.id == 'TAB' and self._controls:
                idx = (self._controls.index(self._selected_control)
                       if self._selected_control in self._controls else -1)
                self._selected_control = self._controls[
                    (idx + 1) % len(self._controls)]

    def draw(self, renderer: _Renderer,
             dispatcher: Dispatcher) -> None:
        if self._dialog is not None:
            self._dialog.draw(renderer, dispatcher)


class _PrimaryMainMenuItem(MenuItemDescriptor):
    def __init__(self, label: str, event_type: type[DeviceEvent],
                 hotkey: None | str = None) -> None:
        super().__init__(label, hotkey)
        self.event_type = event_type


class _MainMenuPanel(_Panel):
    __texture: None | _Texture

    def __init__(self, theme: _Theme) -> None:
        super().__init__(theme)
        self.__texture = None
        self.__menu: _Menu = _Menu([])

    def invalidate(self) -> None:
        super().invalidate()
        if self.__texture:
            self.__texture.free()
        self.__texture = None

    def __on_mouse_move(self, event: _MouseMoveEvent) -> None:
        self.__menu.select_at(
            event.x - self.__menu.x, event.y - self.__menu.y)

    def __rebuild(self, renderer: _Renderer, dispatcher: Dispatcher) -> None:
        assert self.__texture is None

        descriptors: list[MenuItemDescriptor] = dispatcher.notify(
            GetMainMenuItems(), result=[])
        existing = {item.descriptor: item for item in self.__menu.items}
        self.__menu.items = [existing.get(d) or _MenuItem(d)
                             for d in descriptors]

        theme = self._theme
        assert theme.normal_font is not None
        assert theme.key_button_font is not None

        assert theme.window_size is not None
        width, height = theme.window_size

        font = theme.normal_font

        surface = _Surface(width, height)
        surface.fill(theme.overlay_bg)

        self.__menu.min_width = float(width)
        self.__menu.indent = 0.5
        self.__menu.rebuild(theme)
        self.__menu.x = 0.0
        self.__menu.y = max(0, (height - self.__menu.height) // 2)
        self.__menu.draw(surface)

        texture = renderer.create_texture_from_surface(surface)
        surface.free()

        self.__texture = texture

    def __activate_selected(self, dispatcher: Dispatcher) -> None:
        item = self.__menu.selected_item
        if item is not None:
            dispatcher.notify(MenuItemHit(item.descriptor))

    def __on_key(self, key_id: str, pressed: bool,
                 dispatcher: Dispatcher) -> None:
        if not pressed:
            return
        if key_id in ('ESCAPE', 'F1', 'BACKSPACE'):
            dispatcher.notify(_TogglePanel())
            return
        if key_id in ('RETURN', 'SPACE'):
            self.__activate_selected(dispatcher)
            return
        invalidated = self.__menu.on_key(key_id)
        if invalidated:
            self.invalidate()

    def __on_click(self, event: _ClickEvent,
                   dispatcher: Dispatcher) -> None:
        if event.type != _ClickType.Single:
            return
        self.__activate_selected(dispatcher)

    def on_event(self, event: DeviceEvent, dispatcher: Dispatcher) -> None:
        dialog = self._dialog
        super().on_event(event, dispatcher)
        if dialog is not None:
            return

        if isinstance(event, _ConfirmReset):
            self._dialog = _MessageDialog(
                self._theme, 'Reset machine?', (80, 60, 20, 255),
                'Reset the emulated machine?',
                [('Yes', None, _UIEmulatorReset),
                 ('No', 'ESC', _DismissError)])
        elif isinstance(event, _UIEmulatorReset):
            dispatcher.notify(_TogglePanel())
        elif isinstance(event, (PauseStateUpdated, TapeStateUpdated)):
            self.invalidate()
        elif isinstance(event, _MouseMoveEvent):
            self.__on_mouse_move(event)
        elif isinstance(event, _ScrollEvent):
            if self.__menu.scroll(event.delta):
                self.invalidate()
        elif isinstance(event, _KeyEvent):
            self.__on_key(event.id, event.pressed, dispatcher)
        elif isinstance(event, _ClickEvent):
            self.__on_click(event, dispatcher)

    def draw(self, renderer: _Renderer, dispatcher: Dispatcher) -> None:
        if self.__texture is None:
            self.__rebuild(renderer, dispatcher)

        assert self.__texture is not None
        assert self._theme.window_size is not None
        renderer.copy(self.__texture, 0, 0, *self._theme.window_size)
        super().draw(renderer, dispatcher)

        self.__menu.highlight(renderer)


class _FileEntryDescriptor(MenuItemDescriptor):
    def __init__(self, name: str, path: str) -> None:
        super().__init__(name)
        self.path = path
        self.is_dir = os.path.isdir(path)


class _FileBrowserPanel(_Panel):
    __texture: None | _Texture
    __descriptors: list[_FileEntryDescriptor]

    def __init__(self, theme: _Theme) -> None:
        super().__init__(theme)
        self.__texture = None
        self.__path = os.getcwd()
        self.__menu: _Menu = _Menu([])
        self.__menu_button = _Button('Main menu', hotkey='BACKSPACE')
        self.__save_button = _Button('Save', hotkey='RETURN')
        self.__text_input = _TextInput()
        self.__text_input.text = 'snapshot.z80'
        self.__save_mode = False
        self.__load_entries()
        self.__update_controls()

    def set_save_mode(self, save: bool) -> None:
        self.__save_mode = save
        self.__update_controls()

    def __update_controls(self) -> None:
        if self.__save_mode:
            self._controls[:] = [self.__menu, self.__text_input,
                                 self.__save_button, self.__menu_button]
            self._selected_control = self.__text_input
        else:
            self._controls[:] = [self.__menu, self.__menu_button]
            self._selected_control = self.__menu

    def __load_entries(self) -> None:
        selected = self.__menu.selected_item
        selected_path: None | str = None
        if selected is not None:
            assert isinstance(selected.descriptor, _FileEntryDescriptor)
            selected_path = selected.descriptor.path

        try:
            names = sorted(os.listdir(self.__path))
        except OSError:
            names = []
        parent = os.path.normpath(os.path.join(self.__path, '..'))
        descriptors = (
            [_FileEntryDescriptor('..', parent)] +
            [_FileEntryDescriptor(n, os.path.normpath(
                os.path.join(self.__path, n))) for n in names]
        )
        self.__menu.selected_item = None
        self.__menu.items[:] = [_MenuItem(d) for d in descriptors]

        if selected_path is not None:
            for item in self.__menu.items:
                assert isinstance(item.descriptor, _FileEntryDescriptor)
                if item.descriptor.path == selected_path:
                    self.__menu.selected_item = item
                    break

        if self.__menu.selected_item is None:
            self.__menu.select_next()
        self._selected_control = self.__menu

    def activate(self) -> None:
        self.__load_entries()
        self.__update_controls()
        super().activate()

    def invalidate(self) -> None:
        super().invalidate()
        if self.__texture:
            self.__texture.free()
        self.__texture = None

    def __rebuild(self, renderer: _Renderer) -> None:
        assert self.__texture is None
        theme = self._theme
        assert theme.window_size is not None
        assert theme.normal_font is not None
        width, height = (float(v) for v in theme.window_size)
        font = theme.normal_font

        DIM_RGB: _Colour = (150, 150, 150, 255)
        FILE_LIST_BG: _Colour = (0, 0, 0, 170)

        menu_y = font.em + font.line_height * 2

        surface = _Surface(width, height)
        surface.fill(theme.overlay_bg)

        path_surface = font.render(self.__path, DIM_RGB)
        surface.blit(path_surface, font.em, (menu_y - font.line_height) / 2)
        path_surface.free()

        self.__menu_button.v_padding = font.em_height * 0.7
        self.__menu_button.min_width = width / 2 if self.__save_mode else width
        self.__menu_button.rebuild(theme)

        if self.__save_mode:
            self.__save_button.v_padding = font.em_height * 0.7
            self.__save_button.min_width = width / 2
            self.__save_button.rebuild(theme)

            self.__text_input.v_padding = font.em_height * 0.5
            self.__text_input.h_padding = font.em
            self.__text_input.min_width = width
            self.__text_input.rebuild(theme)

        bottom_height = self.__menu_button.height
        if self.__save_mode:
            bottom_height += self.__text_input.height

        self.__menu.min_width = width
        self.__menu.padding = font.em
        self.__menu.max_height = height - menu_y - bottom_height
        self.__menu.rebuild(theme)
        self.__menu.scroll_to_selected()
        self.__menu.x = 0.0
        self.__menu.y = menu_y
        surface.fill_rect(0, menu_y, width, self.__menu.height, FILE_LIST_BG)
        self.__menu.draw(surface)

        if self.__save_mode:
            self.__save_button.x = 0.0
            self.__save_button.y = height - self.__save_button.height
            self.__save_button.draw(surface)

            self.__text_input.x = 0.0
            self.__text_input.y = (self.__save_button.y -
                                   self.__text_input.height)
            self.__text_input.draw(surface)

        self.__menu_button.x = width / 2 if self.__save_mode else 0.0
        self.__menu_button.y = height - self.__menu_button.height
        self.__menu_button.draw(surface)

        texture = renderer.create_texture_from_surface(surface)
        surface.free()
        self.__texture = texture

    def __navigate(self, path: str) -> None:
        prev_path = self.__path
        self.__path = path
        self.__load_entries()
        for item in self.__menu.items:
            assert isinstance(item.descriptor, _FileEntryDescriptor)
            if item.descriptor.path == prev_path:
                self.__menu.selected_item = item
                break
        self.invalidate()

    def __save(self, dispatcher: Dispatcher) -> None:
        filename = self.__text_input.text.strip()
        if not filename:
            return
        path = os.path.join(self.__path, filename)
        if os.path.exists(path):
            self._dialog = _MessageDialog(
                self._theme, 'Overwrite?', (80, 60, 20, 255),
                f'{filename!r} already exists. Overwrite?',
                [('Yes', None, _ConfirmOverwrite),
                 ('No', 'ESC', _DismissError)])
            return
        dispatcher.notify(_ConfirmOverwrite())

    def __activate_selected(self, dispatcher: Dispatcher) -> None:
        item = self.__menu.selected_item
        if item is None:
            return
        assert isinstance(item.descriptor, _FileEntryDescriptor)
        if item.descriptor.is_dir:
            self.__navigate(item.descriptor.path)
        elif self.__save_mode:
            self.__text_input.text = item.descriptor.label
            self._selected_control = self.__text_input
            self.invalidate()
        else:
            try:
                dispatcher.notify(LoadFile(item.descriptor.path))
                dispatcher.notify(_TogglePanel())
            except USER_ERRORS as e:
                dispatcher.notify(_ShowError(verbalize_error(e)))

    def __on_key(self, key_id: str, pressed: bool,
                 dispatcher: Dispatcher) -> None:
        if not pressed:
            return
        if (self.__save_mode
                and self._selected_control is self.__text_input):
            if key_id == 'BACKSPACE':
                self.__text_input.text = self.__text_input.text[:-1]
                self.invalidate()
                return
            if key_id in ('RETURN', 'SPACE'):
                self.__save(dispatcher)
                return
        invalidated = self.__menu.on_key(key_id)
        if invalidated is not None:
            self._selected_control = self.__menu
            if invalidated:
                self.invalidate()
            return
        if key_id in ('RETURN', 'SPACE'):
            if self._selected_control is self.__menu_button:
                dispatcher.notify(_ShowMainMenu())
            elif self.__save_mode:
                item = self.__menu.selected_item
                if (self._selected_control is self.__menu
                        and item is not None
                        and isinstance(item.descriptor,
                                       _FileEntryDescriptor)
                        and item.descriptor.is_dir):
                    self.__activate_selected(dispatcher)
                else:
                    self.__save(dispatcher)
            else:
                self.__activate_selected(dispatcher)
        elif key_id in ('ESCAPE', 'F1'):
            dispatcher.notify(_TogglePanel())
        elif key_id == 'BACKSPACE':
            dispatcher.notify(_ShowMainMenu())

    def __on_mouse_move(self, x: float, y: float) -> None:
        for control in self._controls:
            if control.contains(x, y):
                self._selected_control = control
                break
        if isinstance(self._selected_control, _Menu):
            self._selected_control.select_at(
                x - self._selected_control.x,
                y - self._selected_control.y)

    def __on_click(self, event: _ClickEvent,
                   dispatcher: Dispatcher) -> None:
        if event.type != _ClickType.Single:
            return
        self.__on_mouse_move(event.x, event.y)
        if self._selected_control is self.__menu_button:
            dispatcher.notify(_ShowMainMenu())
        elif self._selected_control is self.__save_button:
            self.__save(dispatcher)
        elif self._selected_control is not self.__text_input:
            self.__activate_selected(dispatcher)

    def on_event(self, event: DeviceEvent,
                 dispatcher: Dispatcher) -> None:
        dialog = self._dialog
        super().on_event(event, dispatcher)
        if dialog is not None:
            return

        if isinstance(event, _ConfirmOverwrite):
            filename = self.__text_input.text.strip()
            path = os.path.join(self.__path, filename)
            try:
                dispatcher.notify(SaveSnapshot(path))
                dispatcher.notify(_TogglePanel())
            except USER_ERRORS as e:
                dispatcher.notify(_ShowError(verbalize_error(e)))
        elif isinstance(event, _TextInputEvent):
            if (self.__save_mode
                    and self._selected_control is self.__text_input):
                self.__text_input.text += event.text
                self.invalidate()
        elif isinstance(event, _MouseMoveEvent):
            self.__on_mouse_move(event.x, event.y)
        elif isinstance(event, _ScrollEvent):
            if self.__menu.scroll(event.delta):
                self.invalidate()
        elif isinstance(event, _KeyEvent):
            self.__on_key(event.id, event.pressed, dispatcher)
        elif isinstance(event, _ClickEvent):
            self.__on_click(event, dispatcher)

    def draw(self, renderer: _Renderer,
             dispatcher: Dispatcher) -> None:
        if self.__texture is None:
            self.__rebuild(renderer)
        assert self.__texture is not None
        assert self._theme.window_size is not None
        renderer.copy(self.__texture, 0, 0, *self._theme.window_size)
        assert self._selected_control is not None
        self._selected_control.highlight(renderer)
        super().draw(renderer, dispatcher)


_ButtonSpec = tuple[str, None | str, type[DeviceEvent]]


class _MessageDialog(_Panel):
    __texture: None | _Texture

    def __init__(self, theme: _Theme, title: str, title_colour: _Colour,
                 message: str, buttons: list[_ButtonSpec]) -> None:
        super().__init__(theme)
        self.__title = title
        self.__title_colour = title_colour
        self.__message = message
        self.__texture = None
        self.__buttons: dict[_Button, type[DeviceEvent]] = {
            _Button(label, hotkey=hotkey): event_type
            for label, hotkey, event_type in buttons}
        self._controls[:] = list(self.__buttons)
        self._selected_control = self._controls[-1]

    def invalidate(self) -> None:
        super().invalidate()
        if self.__texture:
            self.__texture.free()
        self.__texture = None

    def __rebuild(self, renderer: _Renderer) -> None:
        assert self.__texture is None
        theme = self._theme
        assert theme.window_size is not None
        assert theme.normal_font is not None
        assert theme.title_font is not None
        width, height = theme.window_size
        font = theme.normal_font
        title_font = theme.title_font

        TEXT_RGB: _Colour = (230, 230, 230, 255)
        BODY_STRIP_RGB: _Colour = (30, 30, 30, 255)

        n = len(self.__buttons)
        button_width = float(width) / n
        for button in self.__buttons:
            button.v_padding = font.em_height * 0.7
            button.min_width = button_width
            button.rebuild(theme)

        button_height = next(iter(self.__buttons)).height

        surface = _Surface(width, height)
        surface.fill(theme.overlay_bg)

        margin = font.em * 4
        title_surface = title_font.render(self.__title, TEXT_RGB)
        msg_surface = font.render(self.__message, TEXT_RGB,
                                  float(width) - margin * 2)

        title_padding = title_font.line_height * 0.5
        padding = font.line_height * 1.5
        gap = font.line_height * 1.5
        title_strip_h = title_surface.height + title_padding * 2
        body_h = msg_surface.height + gap + button_height + padding
        strip_y = (height - title_strip_h - body_h) / 2

        surface.fill_rect(0, strip_y,
                          float(width), title_strip_h, self.__title_colour)
        surface.fill_rect(0, strip_y + title_strip_h,
                          float(width), body_h, BODY_STRIP_RGB)

        y = strip_y + title_padding
        surface.blit(title_surface, (width - title_surface.width) / 2, y)
        title_surface.free()

        y = strip_y + title_strip_h + padding
        surface.blit(msg_surface, (width - msg_surface.width) / 2, y)
        y += msg_surface.height + gap
        msg_surface.free()

        for i, button in enumerate(self.__buttons):
            button.x = i * button_width
            button.y = y
            button.draw(surface)

        self.__texture = renderer.create_texture_from_surface(surface)
        surface.free()

    def __activate(self, button: _Button,
                   dispatcher: Dispatcher) -> None:
        dispatcher.notify(_DismissError())
        event_type = self.__buttons[button]
        if event_type is not _DismissError:
            dispatcher.notify(event_type())

    def on_event(self, event: DeviceEvent,
                 dispatcher: Dispatcher) -> None:
        super().on_event(event, dispatcher)

        if isinstance(event, _MouseMoveEvent):
            self._selected_control = next(
                (b for b in self.__buttons
                 if b.contains(event.x, event.y)), None)
        elif isinstance(event, _ClickEvent):
            if (event.type == _ClickType.Single
                    and self._selected_control is not None):
                assert isinstance(self._selected_control, _Button)
                self.__activate(self._selected_control, dispatcher)
        elif isinstance(event, _KeyEvent) and event.pressed:
            if event.id in ('RETURN', 'SPACE'):
                if self._selected_control is not None:
                    assert isinstance(self._selected_control, _Button)
                    self.__activate(self._selected_control, dispatcher)
            elif event.id in ('LEFT', 'RIGHT'):
                buttons = list(self.__buttons)
                sel = self._selected_control
                idx = (buttons.index(sel)
                       if isinstance(sel, _Button) and sel in self.__buttons
                       else -1)
                delta = 1 if event.id == 'RIGHT' else -1
                self._selected_control = buttons[(idx + delta) % len(buttons)]
                self.invalidate()
            elif event.id in ('ESCAPE', 'BACKSPACE'):
                dispatcher.notify(_DismissError())

    def draw(self, renderer: _Renderer, dispatcher: Dispatcher) -> None:
        if self.__texture is None:
            self.__rebuild(renderer)
        assert self.__texture is not None
        assert self._theme.window_size is not None
        renderer.copy(self.__texture, 0, 0, *self._theme.window_size)
        if self._selected_control is not None:
            self._selected_control.highlight(renderer)
        super().draw(renderer, dispatcher)


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

        _Handler = typing.Callable[[DeviceEvent, Dispatcher, typing.Any],
                                   typing.Any]
        self._EVENT_HANDLERS: dict[type[DeviceEvent], _Handler] = {
            GetMainMenuItems: self.__on_get_main_menu_items,
            MenuItemHit: self.__on_menu_item_hit,
            _ClickEvent: self.__on_click,
            _ExceptionEvent: self.__on_exception,
            _KeyEvent: self.__on_key,
            _TogglePanel: self.__on_toggle_panel,
            _ShowMainMenu: self.__on_show_main_menu,
            PauseStateUpdated: self._on_updated_pause_state,
            QuantumRun: self._on_quantum_run,
            OutputFrame: self._on_output_frame,
            TapeStateUpdated: self._on_updated_tape_state,
            _RequestResetMachine: self.__on_request_reset_machine,
            RequestLoadFile: self.__on_request_load_file,
            RequestSaveSnapshot: self.__on_request_save_snapshot,
            ToggleFullscreen: self.__on_toggle_fullscreen,
            Destroy: self.__on_destroy,
        }

        self._theme = _Theme()
        self.__emulation_item = _PrimaryMainMenuItem(
            'Pause emulation', ToggleEmulationPause, 'PAUSE')
        self.__tape_item = _PrimaryMainMenuItem(
            'Pause tape', ToggleTapePause, 'F6')
        self.__menu_descriptors: list[MenuItemDescriptor] = [
            _PrimaryMainMenuItem('Hide menu', _TogglePanel, 'ESC'),
            _PrimaryMainMenuItem('Load snapshot or tape file',
                                 RequestLoadFile, 'F3'),
            _PrimaryMainMenuItem('Save snapshot', RequestSaveSnapshot, 'F2'),
            self.__emulation_item,
            self.__tape_item,
            _PrimaryMainMenuItem('Reset machine', _RequestResetMachine, 'F5'),
            _PrimaryMainMenuItem('Toggle fullscreen', ToggleFullscreen, 'F11'),
            _PrimaryMainMenuItem('Quit', _Exit, 'F10'),
        ]
        self.__main_menu_panel = _MainMenuPanel(self._theme)
        self.__file_browser_panel = _FileBrowserPanel(self._theme)
        self.__panel: _Panel = self.__main_menu_panel
        self.__panel_active = False
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
                         dispatcher: Dispatcher,
                         result: typing.Any) -> typing.Any:
        assert isinstance(event, OutputFrame)
        rect = None
        pitch = self.frame_width * 4
        self.__pixels[:] = event.pixels
        pixels = ctypes.c_void_p(ctypes.addressof(
            ctypes.c_char.from_buffer(self.__pixels)))
        import sdl2
        sdl2.SDL_UpdateTexture(self.__pixel_texture.sdl_texture, rect,
                               pixels, pitch)
        return result

    def __update_screen(self, dispatcher: Dispatcher) -> None:
        w, h = ctypes.c_int(), ctypes.c_int()
        lw, lh = ctypes.c_int(), ctypes.c_int()
        import sdl2
        sdl2.SDL_GetRendererOutputSize(self.__renderer.sdl_renderer,
                                       ctypes.byref(w), ctypes.byref(h))
        sdl2.SDL_GetWindowSize(self.__window, ctypes.byref(lw),
                               ctypes.byref(lh))
        window_size = window_width, window_height = w.value, h.value
        if (window_width == 0 or window_height == 0) and lw.value and lh.value:
            window_size = window_width, window_height = lw.value, lh.value
        display_scale = w.value / lw.value if lw.value != 0 else 1.0
        if self._theme.update(window_size, display_scale):
            self.__panel.invalidate()
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

        if self.__panel_active:
            self.__panel.draw(self.__renderer, dispatcher)

        if not self.__panel_active and self._notification:
            self._notification.draw(window_size, (width, height),
                                    self.__renderer, self._theme)

        self.__renderer.present()

    def __on_request_save_snapshot(self, event: DeviceEvent,
                                   devices: Dispatcher,
                                   result: typing.Any) -> typing.Any:
        self.__file_browser_panel.set_save_mode(True)
        self.__activate_panel(self.__file_browser_panel)

        # TODO: Remove once SDL-based saving supports all of this.
        # TODO: Add file filters.
        # filename = tkinter.filedialog.asksaveasfilename(
        #     defaultextension=".z80",
        #     filetypes=[("All files", "*.*")],
        #     title="Save snapshot")
        #
        # if isinstance(filename, str):
        #     try:
        #         devices.notify(SaveSnapshot(filename))
        #     except USER_ERRORS as e:
        #         tkinter.messagebox.showerror(
        #             'File error', verbalize_error(e))

        return result

    def __on_request_reset_machine(self, event: DeviceEvent,
                                   devices: Dispatcher,
                                   result: typing.Any) -> typing.Any:
        self.__activate_panel(self.__main_menu_panel)
        devices.notify(_ConfirmReset())
        return result

    def __activate_panel(self, panel: _Panel) -> None:
        panel.activate()
        self.__panel = panel
        self.__panel_active = True

    def __on_request_load_file(self, event: DeviceEvent,
                               devices: Dispatcher,
                               result: typing.Any) -> typing.Any:
        self.__file_browser_panel.set_save_mode(False)
        self.__activate_panel(self.__file_browser_panel)
        # TODO: Remove once file browser panel supports all of this.
        # TODO: Add file filters.
        # filename = tkinter.filedialog.askopenfilename(
        #     title="Load file",
        #     filetypes=[("All Files", "*.*")])
        # if isinstance(filename, str):
        #     try:
        #         devices.notify(LoadFile(filename))
        #     except USER_ERRORS as e:
        #         self.__error_box('File error', verbalize_error(e))
        return result

    def __on_toggle_fullscreen(self, event: DeviceEvent,
                               devices: Dispatcher,
                               result: typing.Any) -> typing.Any:
        import sdl2
        flags = sdl2.SDL_GetWindowFlags(self.__window)
        flags &= sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP
        flags ^= sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP
        sdl2.SDL_SetWindowFullscreen(self.__window, flags)
        return result

    def __queue_event(self, event: DeviceEvent) -> None:
        self.__events.append(event)

    def __on_sdl_key(self, event: typing.Any) -> None:
        # TODO: Do not upper the case here. Ignore unknown key.
        # Translate to our own key ids.
        import sdl2
        key_id = sdl2.SDL_GetKeyName(
            event.key.keysym.sym).decode('utf-8').upper()
        pressed = event.type == sdl2.SDL_KEYDOWN
        self.__queue_event(_KeyEvent(key_id, pressed))

    def __on_key(self, event: DeviceEvent, devices: Dispatcher,
                 result: typing.Any) -> typing.Any:
        assert isinstance(event, _KeyEvent)
        if event.pressed:
            if event.id in ('ESCAPE', 'F1'):
                if not self.__panel_active:
                    devices.notify(_TogglePanel())
                return result

            items: list[MenuItemDescriptor] = devices.notify(
                GetMainMenuItems(), result=[])
            for item in items:
                if item.hotkey == event.id:
                    devices.notify(MenuItemHit(item))

        if not self.__panel_active:
            zx_key_id = self.__SDL_KEYS_TO_ZX_KEYS.get(event.id, event.id)
            devices.notify(KeyStroke(zx_key_id, event.pressed))
        return result

    def __on_sdl_click(self, event: typing.Any) -> bool:
        TYPES = {
            1: _ClickType.Single,
            2: _ClickType.Double,
        }

        if event.button.clicks in TYPES:
            scale = self._theme.display_scale or 1.0
            self.__queue_event(_ClickEvent(TYPES[event.button.clicks],
                                           round(event.button.x * scale),
                                           round(event.button.y * scale)))
            return True

        return False

    def __on_click(self, event: DeviceEvent,
                   devices: Dispatcher,
                   result: typing.Any) -> typing.Any:
        assert isinstance(event, _ClickEvent)
        if not self.__panel_active:
            if event.type == _ClickType.Single:
                devices.notify(ToggleEmulationPause())
            elif event.type == _ClickType.Double:
                self.__on_toggle_fullscreen(event, devices, result)
        return result

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
                       devices: Dispatcher,
                       result: typing.Any) -> typing.Any:
        assert isinstance(event, _ExceptionEvent,)
        raise event.exception

    def __on_exit(self, devices: Dispatcher) -> None:
        self.__queue_event(_Exit())

    def __on_get_main_menu_items(
            self, event: DeviceEvent, devices: Dispatcher,
            result: list[MenuItemDescriptor]) -> list[MenuItemDescriptor]:
        emulation_paused = devices.notify(GetEmulationPauseState())
        tape_paused = devices.notify(IsTapePlayerPaused())
        self.__emulation_item.label = ('Resume emulation' if emulation_paused
                                       else 'Pause emulation')
        self.__tape_item.label = 'Resume tape' if tape_paused else 'Pause tape'
        result.extend(self.__menu_descriptors)
        return result

    def __on_toggle_panel(self, event: DeviceEvent,
                          devices: Dispatcher,
                          result: typing.Any) -> typing.Any:
        self.__panel_active ^= True
        return result

    def __on_show_main_menu(self, event: DeviceEvent,
                            devices: Dispatcher,
                            result: typing.Any) -> typing.Any:
        self.__activate_panel(self.__main_menu_panel)
        return result

    def __on_menu_item_hit(self, event: DeviceEvent,
                           devices: Dispatcher,
                           result: typing.Any) -> typing.Any:
        assert isinstance(event, MenuItemHit)
        item = event.item
        if isinstance(item, _PrimaryMainMenuItem):
            devices.notify(item.event_type())
        return result

    def on_event(self, event: DeviceEvent, devices: Dispatcher,
                 result: typing.Any) -> typing.Any:
        panel_active = self.__panel_active
        for event_type, handler in self._EVENT_HANDLERS.items():
            if isinstance(event, event_type):
                result = handler(event, devices, result)

        if panel_active:
            self.__panel.on_event(event, devices)
        return result

    def _on_updated_pause_state(self, event: DeviceEvent,
                                devices: Dispatcher,
                                result: typing.Any) -> typing.Any:
        assert isinstance(event, PauseStateUpdated)
        if devices.notify(GetEmulationPauseState()):
            time = devices.notify(GetEmulationTime())
            self._notification = PauseNotification(time)
        else:
            self._notification = None
        return result

    def _on_updated_tape_state(self, event: DeviceEvent,
                               devices: Dispatcher,
                               result: typing.Any) -> typing.Any:
        assert isinstance(event, TapeStateUpdated)
        tape_paused = devices.notify(IsTapePlayerPaused())
        tape_time = devices.notify(GetTapePlayerTime())
        if tape_paused:
            self._notification = TapePauseNotification(tape_time)
        else:
            self._notification = TapeResumeNotification(tape_time)
        return result

    def _on_quantum_run(self, event: DeviceEvent,
                        dispatcher: Dispatcher,
                        result: typing.Any) -> typing.Any:
        assert isinstance(event, QuantumRun)
        import sdl2
        while sdl2.SDL_PollEvent(ctypes.byref(self.__sdl_event)) != 0:
            if self.__sdl_event.type == sdl2.SDL_QUIT:
                self.__on_exit(dispatcher)
            elif self.__sdl_event.type == sdl2.SDL_MOUSEMOTION:
                e = self.__sdl_event.motion
                scale = self._theme.display_scale or 1.0
                self.__queue_event(_MouseMoveEvent(
                    round(e.x * scale), round(e.y * scale)))
            elif self.__sdl_event.type == sdl2.SDL_MOUSEBUTTONDOWN:
                self.__on_sdl_click(self.__sdl_event)
            elif self.__sdl_event.type == sdl2.SDL_MOUSEWHEEL:
                self.__queue_event(
                    _ScrollEvent(self.__sdl_event.wheel.y))
            elif self.__sdl_event.type in (sdl2.SDL_KEYDOWN, sdl2.SDL_KEYUP):
                self.__on_sdl_key(self.__sdl_event)
            elif self.__sdl_event.type == sdl2.SDL_TEXTINPUT:
                text = self.__sdl_event.text.text.decode('utf-8')
                self.__queue_event(_TextInputEvent(text))
            elif self.__sdl_event.type in (sdl2.SDL_CONTROLLERDEVICEADDED,
                                           sdl2.SDL_CONTROLLERDEVICEREMOVED,
                                           sdl2.SDL_CONTROLLERBUTTONUP,
                                           sdl2.SDL_CONTROLLERBUTTONDOWN):
                self.__on_controller_event(self.__sdl_event, dispatcher)

        while self.__events:
            self.on_event(self.__events.pop(0), dispatcher, None)

        self.__update_screen(dispatcher)
        return result

    def __on_destroy(self, event: DeviceEvent, devices: Dispatcher,
                     result: typing.Any) -> typing.Any:
        import sdl2
        sdl2.SDL_DestroyWindow(self.__window)
        return result

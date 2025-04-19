# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2025 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import typing

from ._device import Device
from ._device import DeviceEvent
from ._device import KeyStroke
from ._device import QuantumRun
from ._device import Dispatcher


class Gamepad(Device):
    def __init__(self) -> None:
        self.__gamepad = None

        try:
            import evdev
        except ModuleNotFoundError as e:
            return

        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        for device in devices:
            if 'Xbox' in device.name:
                self.__gamepad = device
                self.__gamepad.grab()
                break

        CURSOR_LEFT, CURSOR_RIGHT = '5', '8'
        CURSOR_DOWN, CURSOR_UP = '6', '7'
        CURSOR_FIRE = '0'

        DPAD_H, DPAD_V = evdev.ecodes.ABS_HAT0X, evdev.ecodes.ABS_HAT0Y
        self.__dirs = {DPAD_H: 0, DPAD_V: 0}
        self.__dir_keys = {DPAD_H: {-1: CURSOR_LEFT, 1: CURSOR_RIGHT},
                           DPAD_V: {-1: CURSOR_UP, 1: CURSOR_DOWN}}

        self.__button_keys = {'BTN_X': CURSOR_LEFT, 'BTN_B': CURSOR_RIGHT,
                              'BTN_Y': CURSOR_UP, 'BTN_A': CURSOR_DOWN,
                              'BTN_TL': CURSOR_FIRE, 'BTN_TR': CURSOR_FIRE}

    def __scan_gamepads(self, dispatcher: Dispatcher) -> None:
        if self.__gamepad is None:
            return

        import evdev
        while True:
            e = self.__gamepad.read_one()
            if e is None:
                break

            event = evdev.categorize(e)

            if isinstance(event, evdev.AbsEvent):
                axis, new_dir = event.event.code, event.event.value
                last_dir = self.__dirs.get(axis)
                if last_dir is not None and new_dir != last_dir:
                    if last_dir != 0:
                        dispatcher.notify(KeyStroke(
                            self.__dir_keys[axis][last_dir], pressed=False))
                    if new_dir != 0:
                        dispatcher.notify(KeyStroke(
                            self.__dir_keys[axis][new_dir], pressed=True))
                    self.__dirs[axis] = new_dir

            if isinstance(event, evdev.KeyEvent):
                button_ids, pressed = event.keycode, event.keystate != 0
                if isinstance(button_ids, str):
                    button_ids = (button_ids,)
                for b in button_ids:
                    key = self.__button_keys.get(b)
                    if key is not None:
                        dispatcher.notify(KeyStroke(key, pressed))

    def on_event(self, event: DeviceEvent, dispatcher: Dispatcher,
                 result: typing.Any) -> typing.Any:
        if isinstance(event, QuantumRun):
            self.__scan_gamepads(dispatcher)
        return result

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.

import enum


class EmulatorEvent(enum.Enum):
    PAUSE_STATE_UPDATED = enum.auto()
    TAPE_STATE_UPDATED = enum.auto()
    RUN_QUANTUM = enum.auto()


class Device(object):
    def __init__(self, emulator):
        self.emulator = emulator

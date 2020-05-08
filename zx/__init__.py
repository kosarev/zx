# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


from ._data import Data, File, FileFormat, ArchiveFileFormat
from ._data import SoundFile, SoundFileFormat, _MachineSnapshot
from ._data import _UnifiedSnapshot
from ._keyboard import KEYS_INFO
from ._machine import Spectrum48
from ._main import (main, Emulator, ProcessorSnapshot, SnapshotsFormat)
from ._rom import get_rom_image
from ._rzx import parse_rzx, make_rzx
from ._scr import _SCRFileFormat
from ._tap import TAPFileFormat
from ._tzx import TZXFileFormat
from ._utils import div_ceil, make16
from ._wav import WAVFileFormat
from ._z80snapshot import Z80SnapshotsFormat
from ._zip import ZIPFileFormat


class Error(Exception):
    """Basic exception for the whole ZX module."""
    def __init__(self, reason, id=None):
        super().__init__(reason)

        if id:
            self.id = id

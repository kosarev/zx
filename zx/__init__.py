# -*- coding: utf-8 -*-

from ._keyboard import KEYS_INFO
from ._machine import Spectrum48
from ._rom import get_rom_image
from ._rzx import parse_rzx
from ._z80snapshot import parse_z80_snapshot


class Error(Exception):
    """Basic exception for the whole ZX module."""

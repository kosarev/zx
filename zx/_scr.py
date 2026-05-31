# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import collections
import typing

from ._binary import Bytes, BinaryParser, BinaryWriter
from ._data import ByteData
from ._data import MachineSnapshot
from ._data import UnifiedSnapshot


class _SCRSnapshot(MachineSnapshot, format_name='SCR'):
    dot_patterns: bytes
    colour_attrs: bytes

    def to_unified_snapshot(self) -> UnifiedSnapshot:
        # The address of the endless loop.
        memory_blocks = []
        ROM_PAGE, RAM_PAGE = 0, 0
        memory_blocks.extend([
            (0x4000, ROM_PAGE, RAM_PAGE, ByteData(self.dot_patterns)),
            (0x4000 + 6144, ROM_PAGE, RAM_PAGE, ByteData(self.colour_attrs))])

        # LOOP_ADDR: jp LOOP_ADDR
        LOOP_ADDR = 0x8000
        loop_instr = b'\xc3' + LOOP_ADDR.to_bytes(2, 'little')
        memory_blocks.append((LOOP_ADDR, ROM_PAGE, RAM_PAGE,
                              ByteData(loop_instr)))

        return UnifiedSnapshot(
            pc=LOOP_ADDR,
            iff1=0,
            iff2=0,
            border_colour=0,
            memory_blocks=memory_blocks)

    # TODO: Refine.
    def x_encode(self) -> bytes:
        return self.dot_patterns + self.colour_attrs

    _FIELDS = ['6144s:dot_patterns', '768s:colour_attrs']

    @classmethod
    def parse(cls, filename: str, image: Bytes) -> '_SCRSnapshot':
        parser = BinaryParser(image)
        fields = collections.OrderedDict()
        fields.update(parser.parse(cls._FIELDS))
        return _SCRSnapshot(**fields)

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import collections
import typing

from ._beeper import BeeperSnapshot
from ._binary import BinaryParser
from ._binary import Bytes
from ._core import CoreSnapshot
from ._data import MachineSnapshot
from ._data import MemoryBlock
from ._data import UnifiedSnapshot
from ._keyboard import KeyboardSnapshot


class _SCRSnapshot(MachineSnapshot, format_name='SCR'):
    dot_patterns: bytes
    colour_attrs: bytes

    def to_unified_snapshot(self) -> UnifiedSnapshot:
        # The address of the endless loop.
        memory_blocks = []
        ROM_PAGE, RAM_PAGE = 0, 0
        memory_blocks.extend([
            MemoryBlock(addr=0x4000, rom_page=ROM_PAGE, ram_page=RAM_PAGE,
                        data=self.dot_patterns),
            MemoryBlock(addr=0x4000 + 6144, rom_page=ROM_PAGE,
                        ram_page=RAM_PAGE, data=self.colour_attrs)])

        # LOOP_ADDR: jp LOOP_ADDR
        LOOP_ADDR = 0x8000
        loop_instr = b'\xc3' + LOOP_ADDR.to_bytes(2, 'little')
        memory_blocks.append(MemoryBlock(
            addr=LOOP_ADDR, rom_page=ROM_PAGE, ram_page=RAM_PAGE,
            data=loop_instr))

        return UnifiedSnapshot(core=CoreSnapshot(
            pc=LOOP_ADDR,
            iff1=0,
            iff2=0,
            border_colour=0,
            memory_blocks=memory_blocks),
            keyboard=KeyboardSnapshot(),
            beeper=BeeperSnapshot())

    # TODO: Refine.
    def x_encode(self) -> bytes:
        return self.dot_patterns + self.colour_attrs

    _FIELDS: typing.ClassVar[list[str]] = [
        '6144s:dot_patterns', '768s:colour_attrs']

    @classmethod
    def decode(cls, filename: str, image: Bytes) -> '_SCRSnapshot':
        parser = BinaryParser(image)
        fields = collections.OrderedDict()
        fields.update(parser.parse(cls._FIELDS))
        return _SCRSnapshot(**fields)

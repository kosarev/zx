#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import collections
import typing

from ._binary import BinaryParser
from ._binary import Bytes
from ._core import MemorySnapshot
from ._core import ULASnapshot
from ._core import Z80Snapshot
from ._data import MachineSnapshot
from ._data import SnapshotFile
from ._machines import Spectrum48CoreSnapshot
from ._machines import Spectrum48MemoryBlock
from ._machines import Spectrum48Snapshot


class _SCRFile(SnapshotFile, format_name='SCR'):
    dot_patterns: bytes
    colour_attrs: bytes

    def to_machine_snapshot(self) -> MachineSnapshot:
        # The address of the endless loop.
        memory_blocks = []
        memory_blocks.extend([
            Spectrum48MemoryBlock(addr=0x4000, data=self.dot_patterns),
            Spectrum48MemoryBlock(addr=0x4000 + 6144,
                                  data=self.colour_attrs)])

        # LOOP_ADDR: jp LOOP_ADDR
        LOOP_ADDR = 0x8000
        loop_instr = b'\xc3' + LOOP_ADDR.to_bytes(2, 'little')
        memory_blocks.append(Spectrum48MemoryBlock(
            addr=LOOP_ADDR, data=loop_instr))

        return Spectrum48Snapshot(core=Spectrum48CoreSnapshot(
            z80=Z80Snapshot(
                pc=LOOP_ADDR,
                iff1=0,
                iff2=0),
            ula=ULASnapshot(border_colour=0),
            memory=MemorySnapshot(blocks=memory_blocks)))

    # TODO: Refine.
    def x_encode(self) -> bytes:
        return self.dot_patterns + self.colour_attrs

    _FIELDS: typing.ClassVar[list[str]] = [
        '6144s:dot_patterns', '768s:colour_attrs']

    @classmethod
    def decode(cls, filename: str, image: Bytes) -> '_SCRFile':
        parser = BinaryParser(image)
        fields = collections.OrderedDict()
        fields.update(parser.parse(cls._FIELDS))
        return _SCRFile(**fields)

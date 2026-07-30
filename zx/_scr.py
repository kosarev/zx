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
from ._core import Z80Snapshot
from ._data import ByteData
from ._data import HexData
from ._data import MachineSnapshot
from ._data import MachineSnapshotFile
from ._spectrum48 import Spectrum48CoreSnapshot
from ._spectrum48 import Spectrum48MemorySnapshot
from ._spectrum48 import Spectrum48Snapshot
from ._spectrum48 import Spectrum48ULASnapshot


class _SCRFile(MachineSnapshotFile, format_name='SCR'):
    dot_patterns: ByteData
    colour_attrs: ByteData

    def __init__(self, *, dot_patterns: Bytes | ByteData,
                 colour_attrs: Bytes | ByteData) -> None:
        super().__init__(dot_patterns=HexData.wrap(dot_patterns),
                         colour_attrs=HexData.wrap(colour_attrs))

    def to_machine_snapshot(self) -> MachineSnapshot:
        ram = bytearray(0xc000)
        ram[0:6144] = self.dot_patterns.data
        ram[6144:6912] = self.colour_attrs.data

        # LOOP_ADDR: jp LOOP_ADDR
        LOOP_ADDR = 0x8000
        loop_instr = b'\xc3' + LOOP_ADDR.to_bytes(2, 'little')
        ram[LOOP_ADDR - 0x4000:LOOP_ADDR - 0x4000 + 3] = loop_instr

        return Spectrum48Snapshot(core=Spectrum48CoreSnapshot(
            z80=Z80Snapshot(
                pc=LOOP_ADDR,
                iff1=0,
                iff2=0),
            ula=Spectrum48ULASnapshot(border_colour=0),
            memory=Spectrum48MemorySnapshot(ram=ram)))

    # TODO: Refine.
    def x_encode(self) -> bytes:
        return self.dot_patterns.data + self.colour_attrs.data

    _FIELDS: typing.ClassVar[list[str]] = [
        '6144s:dot_patterns', '768s:colour_attrs']

    @classmethod
    def decode(cls, filename: str, image: Bytes) -> '_SCRFile':
        parser = BinaryParser(image)
        fields = collections.OrderedDict()
        fields.update(parser.parse(cls._FIELDS))
        return _SCRFile(**fields)

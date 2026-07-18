#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import typing

from ._binary import BinaryParser
from ._binary import BinaryWriter
from ._binary import Bytes
from ._core import CoreSnapshot
from ._core import MemorySnapshot
from ._core import ULASnapshot
from ._core import Z80Snapshot
from ._data import ByteData
from ._data import HexData
from ._data import MachineSnapshot
from ._data import SnapshotFile
from ._error import Error
from ._spectrum48 import Spectrum48CoreSnapshot
from ._spectrum48 import Spectrum48MemoryBlock
from ._spectrum48 import Spectrum48MemorySnapshot
from ._spectrum48 import Spectrum48Snapshot


class SNAFile(SnapshotFile, format_name='SNA'):
    _HEADER: typing.ClassVar[list[str]] = [
        'B:i', '<H:alt_hl', '<H:alt_de', '<H:alt_bc', '<H:alt_af',
        '<H:hl', '<H:de', '<H:bc', '<H:iy', '<H:ix',
        'B:iff', 'B:r', '<H:af', '<H:sp',
        'B:int_mode', 'B:border_colour']

    i: int
    alt_hl: int
    alt_de: int
    alt_bc: int
    alt_af: int
    hl: int
    de: int
    bc: int
    iy: int
    ix: int
    iff: int
    r: int
    af: int
    sp: int
    int_mode: int
    border_colour: int
    memory: ByteData

    def __init__(self, *, i: int = 0, alt_hl: int = 0, alt_de: int = 0,
                 alt_bc: int = 0, alt_af: int = 0, hl: int = 0, de: int = 0,
                 bc: int = 0, iy: int = 0, ix: int = 0, iff: int = 0,
                 r: int = 0, af: int = 0, sp: int = 0, int_mode: int = 0,
                 border_colour: int = 0,
                 memory: Bytes | ByteData = b'\x00' * 0xC000) -> None:
        super().__init__(i=i, alt_hl=alt_hl, alt_de=alt_de, alt_bc=alt_bc,
                         alt_af=alt_af, hl=hl, de=de, bc=bc, iy=iy, ix=ix,
                         iff=iff, r=r, af=af, sp=sp, int_mode=int_mode,
                         border_colour=border_colour,
                         memory=HexData.wrap(memory))

    def to_machine_snapshot(self) -> MachineSnapshot:
        sp = self.sp

        # PC was pushed onto the stack when the snapshot was taken; retrieve
        # and pop it. SP points to the pushed PC in the 48K RAM area.
        if sp < 0x4000 or sp > 0xFFFE:
            raise Error(f'SP={sp:#06x} out of range to recover PC from stack.',
                        id='sna_invalid_sp')
        pc_offset = sp - 0x4000
        pc = (self.memory.data[pc_offset] |
              (self.memory.data[pc_offset + 1] << 8))
        sp = (sp + 2) & 0xFFFF

        iff = int(bool(self.iff & 0x04))

        # The file describes a 48K machine.
        return Spectrum48Snapshot(core=Spectrum48CoreSnapshot(
            z80=Z80Snapshot(
                af=self.af, bc=self.bc, de=self.de, hl=self.hl,
                ix=self.ix, iy=self.iy,
                alt_af=self.alt_af, alt_bc=self.alt_bc,
                alt_de=self.alt_de, alt_hl=self.alt_hl,
                pc=pc, sp=sp,
                ir=(self.i << 8) | (self.r & 0x7f),
                iff1=iff, iff2=iff,
                int_mode=self.int_mode),
            ula=ULASnapshot(border_colour=self.border_colour),
            memory=Spectrum48MemorySnapshot(blocks=[
                Spectrum48MemoryBlock(addr=0x4000,
                                      data=self.memory.data)])))

    @classmethod
    def from_snapshot(cls, snapshot: SnapshotFile) -> 'SNAFile':
        core = next(
            (d for _, d in snapshot.to_machine_snapshot()
             if isinstance(d, CoreSnapshot)), None)
        if core is None:
            core = CoreSnapshot()
        z80 = core.z80 or Z80Snapshot()
        ula = core.ula or ULASnapshot()

        blocks = (core.memory or MemorySnapshot()).blocks or []

        memory = bytearray(0x10000)
        for block in blocks:
            memory[block.addr:block.end_addr] = block.data.data

        sp = z80.sp or 0
        pc = z80.pc or 0

        # Push PC onto the stack to match the SNA format convention.
        sp = (sp - 2) & 0xFFFF
        memory[sp] = pc & 0xFF
        memory[sp + 1] = (pc >> 8) & 0xFF

        ir = z80.ir or 0

        return SNAFile(
            i=(ir >> 8) & 0xFF,
            alt_hl=z80.alt_hl or 0,
            alt_de=z80.alt_de or 0,
            alt_bc=z80.alt_bc or 0,
            alt_af=z80.alt_af or 0,
            hl=z80.hl or 0,
            de=z80.de or 0,
            bc=z80.bc or 0,
            iy=z80.iy or 0,
            ix=z80.ix or 0,
            iff=(z80.iff1 or 0) << 2,
            r=ir & 0xFF,
            af=z80.af or 0,
            sp=sp,
            int_mode=z80.int_mode or 0,
            border_colour=ula.border_colour or 0,
            memory=memory[0x4000:0x10000])

    @classmethod
    def decode(cls, filename: str, image: Bytes) -> 'SNAFile':
        parser = BinaryParser(image)
        fields = parser.parse(cls._HEADER)
        if parser.get_remaining_size() == 131076:
            raise Error(f"'{filename}': 128K .sna files are not supported.",
                        id='sna_128k_not_supported')
        memory = parser.read_bytes(0xC000)
        if not parser.is_eof():
            raise Error(f"'{filename}': .sna file is too long.",
                        id='sna_file_too_long')
        return SNAFile(**fields, memory=memory)

    def encode(self) -> bytes:
        writer = BinaryWriter()
        writer.write(self._HEADER, **dict(self))
        writer.write_bytes(self.memory.data)
        return writer.get_image()

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

"""What the 128K Spectrum is, as snapshot types."""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from ._binary import Bytes
    from ._data import ByteData

from ._beeper import BeeperSnapshot
from ._core import MEMORY_PAGE_SIZE
from ._core import RAM_PAGE_IMAGE_OFFSETS
from ._core import ROM_PAGE_IMAGE_OFFSETS
from ._core import CoreSnapshot
from ._core import MemoryBlock
from ._core import MemorySnapshot
from ._core import ULASnapshot
from ._core import Z80Snapshot
from ._data import HexData
from ._data import MachineSnapshot
from ._keyboard import KeyboardSnapshot
from ._resources import RESOURCES


# The 128K ULA. The type fixes the wiring as class keywords, so only
# the volatile fields are constructor parameters.
class Spectrum128ULASnapshot(ULASnapshot,
                             ticks_per_second=3_546_900,
                             ticks_per_horizontal_retrace=52,
                             lines_per_vertical_retrace=23,
                             contention_base=14361):
    def __init__(self, *,
                 ticks_since_int: int | None = None,
                 border_colour: int | None = None) -> None:
        super().__init__(
            ticks_per_second=self.ticks_per_second,
            ticks_per_horizontal_retrace=self.ticks_per_horizontal_retrace,
            lines_per_vertical_retrace=self.lines_per_vertical_retrace,
            contention_base=self.contention_base,
            ticks_since_int=ticks_since_int,
            border_colour=border_colour)


# A block in the 128K's paged address space: the Z80 address plus
# the page selectors, rom_page selecting the ROM at 0x0000-0x3FFF
# and ram_page the RAM page at 0xC000-0xFFFF, translated to image
# offsets at construction.
class Spectrum128MemoryBlock(MemoryBlock):
    def __init__(self, *, addr: int, rom_page: int | None = None,
                 ram_page: int | None = None,
                 data: Bytes | ByteData) -> None:
        data = HexData.wrap(data)
        end_addr = addr + len(data.data)
        assert end_addr <= 0x10000

        if addr < 0x4000:
            assert rom_page is not None
            offset = ROM_PAGE_IMAGE_OFFSETS[rom_page] + addr
            # Only the first ROM is followed by the rest of the 48K
            # map in the image.
            assert end_addr <= 0x4000 or rom_page == 0
        elif addr < 0xc000:
            offset = addr
        else:
            assert ram_page is not None
            offset = RAM_PAGE_IMAGE_OFFSETS[ram_page] + (addr - 0xc000)

        # Past 0xC000 the image continues with ram0 only.
        if addr < 0xc000 and end_addr > 0xc000:
            assert ram_page in (None, 0)

        super().__init__(offset=offset, data=data)

    # The node speaks the 128K vocabulary, translated back from the
    # image offset.
    def to_json(self) -> dict[str, typing.Any]:
        d = super().to_json()
        offset, end_offset = self.offset, self.end_offset

        rom1_offset = ROM_PAGE_IMAGE_OFFSETS[1]
        rom_page = None
        ram_page = None
        if offset < 0x10000:
            # Within the image of the 48K map.
            addr = offset
            if addr < 0x4000:
                rom_page = 0
            if end_offset > 0xc000:
                ram_page = 0
        elif offset < rom1_offset + MEMORY_PAGE_SIZE:
            addr = offset - rom1_offset
            rom_page = 1
            assert end_offset <= rom1_offset + MEMORY_PAGE_SIZE
        else:
            page = next(n for n, o in RAM_PAGE_IMAGE_OFFSETS.items()
                        if o <= offset < o + MEMORY_PAGE_SIZE)
            page_offset = RAM_PAGE_IMAGE_OFFSETS[page]
            addr = 0xc000 + (offset - page_offset)
            ram_page = page
            assert end_offset <= page_offset + MEMORY_PAGE_SIZE

        node: dict[str, typing.Any] = {'addr': addr}
        if rom_page is not None:
            node['rom_page'] = rom_page
        if ram_page is not None:
            node['ram_page'] = ram_page
        node['data'] = d['data']
        return node


# The 128K's memory: a collection of blocks in the 128K's paged
# address space. The given blocks amend the stock ROMs -- blocks
# carrying ROM content replace them.
class Spectrum128MemorySnapshot(MemorySnapshot):
    def __init__(
            self,
            blocks: typing.Sequence[Spectrum128MemoryBlock] | None = None,
            ) -> None:
        blocks = list(blocks or [])

        # A block starting in either ROM page replaces the stock
        # ROMs.
        rom1_offset = ROM_PAGE_IMAGE_OFFSETS[1]
        if not any(b.offset < 0x4000
                   or rom1_offset <= b.offset < (rom1_offset +
                                                 MEMORY_PAGE_SIZE)
                   for b in blocks):
            rom = (RESOURCES / 'roms' / 'Spectrum128.rom').read_bytes()
            blocks = [Spectrum128MemoryBlock(addr=0x0000, rom_page=0,
                                             data=rom[:0x4000]),
                      Spectrum128MemoryBlock(addr=0x0000, rom_page=1,
                                             data=rom[0x4000:]),
                      *blocks]

        super().__init__(blocks=blocks)


# The 128K core: members not specified take their stock values. The
# remaining 128K facts, the clock and the paging, still ride the
# core's model parameter; they become core config fields as the 128K
# work proceeds.
class Spectrum128CoreSnapshot(CoreSnapshot):
    ula: Spectrum128ULASnapshot
    memory: Spectrum128MemorySnapshot

    def __init__(self, *,
                 z80: Z80Snapshot | None = None,
                 ula: ULASnapshot | None = None,
                 memory: Spectrum128MemorySnapshot | None = None) -> None:
        # Lift the ULA facts to the model's type: nothing a given
        # plain record states may disagree with the stock values.
        if ula is None:
            ula = ULASnapshot()
        if not isinstance(ula, Spectrum128ULASnapshot):
            lifted = Spectrum128ULASnapshot(
                ticks_since_int=ula.ticks_since_int,
                border_colour=ula.border_colour)
            assert all(getattr(lifted, f) == v for f, v in ula)
            ula = lifted

        if memory is None:
            memory = Spectrum128MemorySnapshot()

        super().__init__(active=True, z80=z80, ula=ula, memory=memory)


class Spectrum128Snapshot(MachineSnapshot):
    core: CoreSnapshot
    keyboard: KeyboardSnapshot
    beeper: BeeperSnapshot

    # Members not specified take their stock values, so constructing
    # with no arguments gives the stock 128K machine.
    def __init__(self, *, core: CoreSnapshot | None = None,
                 keyboard: KeyboardSnapshot | None = None,
                 beeper: BeeperSnapshot | None = None) -> None:
        if core is None:
            core = Spectrum128CoreSnapshot()
        if keyboard is None:
            keyboard = KeyboardSnapshot(active=True)
        if beeper is None:
            beeper = BeeperSnapshot(active=True)

        super().__init__(core=core, keyboard=keyboard, beeper=beeper)

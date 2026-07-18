#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

"""What the 48K Spectrum is, as snapshot types."""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from ._binary import Bytes
    from ._data import ByteData

from ._beeper import BeeperSnapshot
from ._core import CoreSnapshot
from ._core import MemoryBlock
from ._core import MemorySnapshot
from ._core import ULASnapshot
from ._core import Z80Snapshot
from ._data import HexData
from ._data import MachineSnapshot
from ._keyboard import KeyboardSnapshot
from ._resources import RESOURCES


# The 48K ULA. The type fixes the wiring as class keywords, so only
# the volatile fields are constructor parameters.
class Spectrum48ULASnapshot(ULASnapshot,
                            ticks_per_second=3_500_000,
                            ticks_per_horizontal_retrace=48,
                            lines_per_vertical_retrace=24,
                            contention_base=14335):
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

    # The type fixes the wiring, so the node stores only these fields.
    def to_json(self) -> dict[str, int]:
        d = super().to_json()
        return {name: d[name]
                for name in ('ticks_since_int', 'border_colour')
                if name in d}


# A block in the 48K's flat address space. The map is fixed, so the
# page selectors translate from the address range: only a block
# overlapping a paged region names its page.
class Spectrum48MemoryBlock(MemoryBlock):
    def __init__(self, *, addr: int, data: Bytes | ByteData) -> None:
        data = HexData.wrap(data)
        end_addr = addr + len(data.data)
        super().__init__(
            addr=addr,
            rom_page=0 if addr < 0x4000 else None,
            ram_page=0 if end_addr > 0xc000 else None,
            data=data)

    # The type fixes the 48K map, so the node stores only these fields.
    def to_json(self) -> dict[str, typing.Any]:
        d = super().to_json()
        return {name: d[name] for name in ('addr', 'data') if name in d}


# The 48K's memory: a collection of blocks in the 48K's flat
# address space. The given blocks amend the stock ROM -- a block
# carrying ROM content replaces it.
class Spectrum48MemorySnapshot(MemorySnapshot):
    def __init__(
            self,
            blocks: typing.Sequence[Spectrum48MemoryBlock] | None = None,
            ) -> None:
        blocks = list(blocks or [])
        if not any(b.addr < 0x4000 for b in blocks):
            rom = (RESOURCES / 'roms' / 'Spectrum48.rom').read_bytes()
            blocks = [Spectrum48MemoryBlock(addr=0x0000, data=rom),
                      *blocks]

        super().__init__(blocks=blocks)


# The 48K core: members not specified take their stock values.
class Spectrum48CoreSnapshot(CoreSnapshot):
    ula: Spectrum48ULASnapshot
    memory: Spectrum48MemorySnapshot

    def __init__(self, *,
                 z80: Z80Snapshot | None = None,
                 ula: ULASnapshot | None = None,
                 memory: Spectrum48MemorySnapshot | None = None) -> None:
        # Lift the ULA facts to the model's type: nothing a given
        # plain record states may disagree with the stock values.
        if ula is None:
            ula = ULASnapshot()
        if not isinstance(ula, Spectrum48ULASnapshot):
            lifted = Spectrum48ULASnapshot(
                ticks_since_int=ula.ticks_since_int,
                border_colour=ula.border_colour)
            assert all(getattr(lifted, f) == v for f, v in ula)
            ula = lifted

        if memory is None:
            memory = Spectrum48MemorySnapshot()

        super().__init__(active=True, z80=z80, ula=ula, memory=memory)


class Spectrum48Snapshot(MachineSnapshot):
    core: CoreSnapshot
    keyboard: KeyboardSnapshot
    beeper: BeeperSnapshot

    # Members not specified take their stock values, so constructing
    # with no arguments gives the stock 48K machine.
    def __init__(self, *, core: CoreSnapshot | None = None,
                 keyboard: KeyboardSnapshot | None = None,
                 beeper: BeeperSnapshot | None = None) -> None:
        if core is None:
            core = Spectrum48CoreSnapshot()
        if keyboard is None:
            keyboard = KeyboardSnapshot(active=True)
        if beeper is None:
            beeper = BeeperSnapshot(active=True)

        super().__init__(core=core, keyboard=keyboard, beeper=beeper)

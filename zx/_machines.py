#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

"""Machine definitions as values.

A model is a stock snapshot installed like any other. Devices default
to inactive, so a stock snapshot explicitly activates its machine's
members. Converters compose their output over the stock snapshot of
the machine their format declares.
"""

import importlib.resources

from ._beeper import BeeperSnapshot
from ._core import CoreSnapshot
from ._core import MemorySnapshot
from ._core import ULASnapshot
from ._core import Z80Snapshot
from ._data import MachineSnapshot
from ._data import MemoryBlock
from ._keyboard import KeyboardSnapshot


def _load_rom_image(filename: str) -> bytes:
    path = importlib.resources.files('zx').joinpath('roms').joinpath(filename)
    return path.read_bytes()


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


# The 48K core: members not specified take their stock values, and
# the given memory blocks amend the stock ROM -- a block carrying ROM
# content replaces it.
class Spectrum48CoreSnapshot(CoreSnapshot):
    ula: Spectrum48ULASnapshot
    memory: MemorySnapshot

    def __init__(self, *,
                 z80: Z80Snapshot | None = None,
                 ula: ULASnapshot | None = None,
                 memory: MemorySnapshot | None = None) -> None:
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

        blocks = list(memory.blocks or []) if memory is not None else []
        if not any(b.addr < 0x4000 for b in blocks):
            blocks = [MemoryBlock(addr=0x0000, rom_page=0, ram_page=0,
                                  data=_load_rom_image('Spectrum48.rom')),
                      *blocks]

        super().__init__(active=True, z80=z80, ula=ula,
                         memory=MemorySnapshot(blocks=blocks))


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


# The 128K core: members not specified take their stock values, and
# the given memory blocks amend the stock ROMs -- blocks carrying ROM
# content replace them. The remaining 128K facts, the clock and the
# paging, still ride the core's model parameter; they become core
# config fields as the 128K work proceeds.
class Spectrum128CoreSnapshot(CoreSnapshot):
    ula: Spectrum128ULASnapshot
    memory: MemorySnapshot

    def __init__(self, *,
                 z80: Z80Snapshot | None = None,
                 ula: ULASnapshot | None = None,
                 memory: MemorySnapshot | None = None) -> None:
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

        blocks = list(memory.blocks or []) if memory is not None else []
        if not any(b.addr < 0x4000 for b in blocks):
            rom = _load_rom_image('Spectrum128.rom')
            blocks = [MemoryBlock(addr=0x0000, rom_page=0, ram_page=0,
                                  data=rom[:0x4000]),
                      MemoryBlock(addr=0x0000, rom_page=1, ram_page=0,
                                  data=rom[0x4000:]),
                      *blocks]

        super().__init__(active=True, z80=z80, ula=ula,
                         memory=MemorySnapshot(blocks=blocks))


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

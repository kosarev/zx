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
import typing

from ._beeper import BeeperSnapshot
from ._core import CoreSnapshot
from ._data import MachineSnapshot
from ._data import MemoryBlock
from ._keyboard import KeyboardSnapshot


def _load_rom_image(filename: str) -> bytes:
    path = importlib.resources.files('zx').joinpath('roms').joinpath(filename)
    return path.read_bytes()


# The 48K core: fields not specified take their stock values, and the
# given memory blocks amend the stock ROM -- a block carrying ROM
# content replaces it.
class Spectrum48CoreSnapshot(CoreSnapshot):
    def __init__(self, **fields: typing.Any) -> None:
        fields.setdefault('active', True)
        fields.setdefault('ticks_per_second', 3_500_000)
        fields.setdefault('ticks_per_horizontal_retrace', 48)
        fields.setdefault('lines_per_vertical_retrace', 24)
        fields.setdefault('contention_base', 14335)

        blocks = list(fields.get('memory_blocks') or [])
        if not any(b.addr < 0x4000 for b in blocks):
            blocks = [MemoryBlock(addr=0x0000, rom_page=0, ram_page=0,
                                  data=_load_rom_image('Spectrum48.rom')),
                      *blocks]
        fields['memory_blocks'] = blocks

        super().__init__(**fields)


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


# The 128K core: fields not specified take their stock values, and
# the given memory blocks amend the stock ROMs -- blocks carrying ROM
# content replace them. The remaining 128K facts, the clock and the
# paging, still ride the core's model parameter; they become core
# config fields as the 128K work proceeds.
class Spectrum128CoreSnapshot(CoreSnapshot):
    def __init__(self, **fields: typing.Any) -> None:
        fields.setdefault('active', True)
        fields.setdefault('ticks_per_second', 3_546_900)
        fields.setdefault('ticks_per_horizontal_retrace', 52)
        fields.setdefault('lines_per_vertical_retrace', 23)
        fields.setdefault('contention_base', 14361)

        blocks = list(fields.get('memory_blocks') or [])
        if not any(b.addr < 0x4000 for b in blocks):
            rom = _load_rom_image('Spectrum128.rom')
            blocks = [MemoryBlock(addr=0x0000, rom_page=0, ram_page=0,
                                  data=rom[:0x4000]),
                      MemoryBlock(addr=0x0000, rom_page=1, ram_page=0,
                                  data=rom[0x4000:]),
                      *blocks]
        fields['memory_blocks'] = blocks

        super().__init__(**fields)


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

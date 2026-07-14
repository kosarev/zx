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
from ._data import MachineSnapshot
from ._data import MemoryBlock
from ._keyboard import KeyboardSnapshot


def load_rom_image(filename: str) -> bytes:
    path = importlib.resources.files('zx').joinpath('roms').joinpath(filename)
    return path.read_bytes()


class Spectrum48Snapshot(MachineSnapshot, format_name=None):
    core: CoreSnapshot
    keyboard: KeyboardSnapshot
    beeper: BeeperSnapshot

    def __init__(self, *, core: CoreSnapshot,
                 keyboard: KeyboardSnapshot,
                 beeper: BeeperSnapshot) -> None:
        super().__init__(core=core, keyboard=keyboard, beeper=beeper)


def get_spectrum_48k_snapshot() -> Spectrum48Snapshot:
    return Spectrum48Snapshot(
        core=CoreSnapshot(
            active=True,
            memory_blocks=[
                MemoryBlock(addr=0x0000, rom_page=0, ram_page=0,
                            data=load_rom_image('Spectrum48.rom'))]),
        beeper=BeeperSnapshot(active=True),
        keyboard=KeyboardSnapshot(active=True))


# The remaining 128K facts, the clock and the paging, still ride the
# core's model parameter; they become core config fields as the 128K
# work proceeds.
def get_spectrum_128k_snapshot() -> MachineSnapshot:
    rom = load_rom_image('Spectrum128.rom')
    stock = get_spectrum_48k_snapshot()
    return stock.updated(core=stock.core.updated(memory_blocks=[
        MemoryBlock(addr=0x0000, rom_page=0, ram_page=0, data=rom[:0x4000]),
        MemoryBlock(addr=0x0000, rom_page=1, ram_page=0,
                    data=rom[0x4000:])]))

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

from ._beeper import BeeperSnapshot
from ._core import CoreSnapshot
from ._data import MachineSnapshot
from ._keyboard import KeyboardSnapshot


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
        core=CoreSnapshot(active=True),
        beeper=BeeperSnapshot(active=True),
        keyboard=KeyboardSnapshot(active=True))

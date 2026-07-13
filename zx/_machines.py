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
from ._data import UnifiedSnapshot
from ._keyboard import KeyboardSnapshot


def get_spectrum_48k_snapshot() -> UnifiedSnapshot:
    return UnifiedSnapshot(
        core=CoreSnapshot(active=True),
        beeper=BeeperSnapshot(active=True),
        keyboard=KeyboardSnapshot(active=True))

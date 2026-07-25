#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

"""Driving a machine's ROM BASIC from code.

The shared scaffolding of the converters that run a private
headless machine through its ROM: boot to the BASIC prompt, type,
and capture the result.
"""

from __future__ import annotations

import typing

from ._core import Core
from ._spectrum48 import Spectrum48CoreSnapshot
from ._spectrum48 import Spectrum48MemoryBlock
from ._spectrum48 import Spectrum48MemorySnapshot
from ._spectrum48 import Spectrum48Snapshot
from ._time import Time

if typing.TYPE_CHECKING:
    from ._emulator import Emulator

# The 48K boot settles at the BASIC prompt well within this many
# frames of 69,888 ticks.
_BOOT_FRAMES = 90
_TICKS_PER_FRAME = 69888


# Runs a freshly constructed 48K machine from power-up to the BASIC
# prompt.
def boot_to_prompt(app: Emulator) -> None:
    core = app.machine.devices['core']
    assert isinstance(core, Core)
    app.run(until=Time(_BOOT_FRAMES * _TICKS_PER_FRAME,
                       ticks_per_second=core.ticks_per_second))


# Captures the machine as a 48K snapshot: the caller knows the
# machine is a 48K, so the captured memory blocks get the 48K
# types.
def capture_spectrum48(core: Core) -> Spectrum48Snapshot:
    captured = core.to_snapshot()
    memory = Spectrum48MemorySnapshot(blocks=[
        Spectrum48MemoryBlock(addr=b.offset, data=b.data)
        for b in (captured.memory.blocks if captured.memory else None)
        or []])
    return Spectrum48Snapshot(
        core=Spectrum48CoreSnapshot(z80=captured.z80, ula=captured.ula,
                                    memory=memory))

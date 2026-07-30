#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

"""What the 48K Spectrum is, as its machine and snapshot types."""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from ._binary import Bytes
    from ._core import Profile
    from ._data import ByteData
    from ._device import Device

from ._beeper import Beeper
from ._beeper import BeeperSnapshot
from ._core import Core
from ._core import CoreSnapshot
from ._core import MemoryBlock
from ._core import MemoryMapping
from ._core import MemorySnapshot
from ._core import ULASnapshot
from ._core import Z80Snapshot
from ._data import HexData
from ._data import MachineSnapshot
from ._keyboard import Keyboard
from ._keyboard import KeyboardSnapshot
from ._machine import Machine
from ._playback import PlaybackPlayer
from ._playback import PlaybackRecorder
from ._resources import RESOURCES
from ._tape import TapePlayer


# The 48K ULA.
class Spectrum48ULASnapshot(ULASnapshot):
    pass


# The 48K's fixed memory mapping: the whole 64K address space,
# one-to-one onto the leading 64K of the internal memory image.
class Spectrum48MemoryMapping(MemoryMapping):
    def get_offset(self, addr: int, size: int) -> int:
        assert addr >= 0 and addr + size <= 0x10000
        return addr


# A block in the 48K's flat address space.
class Spectrum48MemoryBlock(MemoryBlock):
    def __init__(self, *, addr: int, data: Bytes | ByteData) -> None:
        data = HexData.wrap(data)
        offset = Spectrum48MemoryMapping().get_offset(
            addr, len(data.data))
        super().__init__(offset=offset, data=data)

    # The node speaks the 48K vocabulary.
    def to_json(self) -> dict[str, typing.Any]:
        d = super().to_json()
        return {'addr': self.offset, 'data': d['data']}


# The stock 48K ROM at address 0. The type alone determines the
# content, so its node stores nothing.
class Spectrum48ROM(Spectrum48MemoryBlock):
    def __init__(self) -> None:
        rom = (RESOURCES / 'roms' / 'Spectrum48.rom').read_bytes()
        super().__init__(addr=0x0000, data=rom)

    def to_json(self) -> dict[str, typing.Any]:
        return {}


# The 48K's memory: a collection of blocks in the 48K's flat
# address space. The given blocks amend the stock ROM -- a block
# carrying ROM content replaces it.
class Spectrum48MemorySnapshot(MemorySnapshot, image_size=0x10000):
    def __init__(
            self, *,
            blocks: typing.Sequence[Spectrum48MemoryBlock] | None = None,
            ) -> None:
        blocks = list(blocks or [])
        if not any(b.offset < 0x4000 for b in blocks):
            blocks = [Spectrum48ROM(), *blocks]

        super().__init__(image_size=self.image_size, blocks=blocks)

    # Recognise a plain record as the 48K memory: the stock ROM in
    # place and all content within the 64K address space. Anything
    # else stays plain.
    @classmethod
    def _lift(cls, plain: MemorySnapshot) -> MemorySnapshot:
        rom = Spectrum48ROM()
        if not plain.match(Spectrum48MemoryMapping(), 0x0000,
                           rom.data.data):
            return plain

        blocks: list[Spectrum48MemoryBlock] = [rom]
        for block in plain.blocks or []:
            if block.end_offset > 0x10000:
                return plain

            # The ROM node subsumes the content below 0x4000, which
            # match() verified; the rest retypes, split at the ROM
            # boundary.
            if block.end_offset <= rom.end_offset:
                continue
            begin = max(block.offset, rom.end_offset)
            blocks.append(Spectrum48MemoryBlock(
                addr=begin, data=block.data.data[begin - block.offset:]))

        return cls(blocks=blocks)

    # The type fixes the configuration, so the node stores only the
    # blocks.
    def to_json(self) -> dict[str, typing.Any]:
        d = super().to_json()
        return {name: d[name] for name in ('blocks',) if name in d}


# The 48K core: members not specified take their stock values.
class Spectrum48CoreSnapshot(CoreSnapshot):
    ula: Spectrum48ULASnapshot
    memory: Spectrum48MemorySnapshot

    def __init__(self, *,
                 disabled: bool | None = None,
                 z80: Z80Snapshot | None = None,
                 ula: Spectrum48ULASnapshot | None = None,
                 memory: Spectrum48MemorySnapshot | None = None) -> None:
        if ula is None:
            ula = Spectrum48ULASnapshot()
        if memory is None:
            memory = Spectrum48MemorySnapshot()

        super().__init__(disabled=disabled, z80=z80, ula=ula, memory=memory)


class Spectrum48Snapshot(MachineSnapshot):
    core: Spectrum48CoreSnapshot
    keyboard: KeyboardSnapshot
    beeper: BeeperSnapshot

    # Members not specified take their stock values, so constructing
    # with no arguments gives the stock 48K machine.
    def __init__(self, *, core: Spectrum48CoreSnapshot | None = None,
                 keyboard: KeyboardSnapshot | None = None,
                 beeper: BeeperSnapshot | None = None) -> None:
        if core is None:
            core = Spectrum48CoreSnapshot()
        if keyboard is None:
            keyboard = KeyboardSnapshot()
        if beeper is None:
            beeper = BeeperSnapshot()

        super().__init__(core=core, keyboard=keyboard, beeper=beeper)


# The 48K core: the chip family the 48K board wires, expressed as a
# type and paired with its snapshot type, so the model shows in the
# device types rather than in a runtime model field.
class Spectrum48Core(Core):
    def __init__(self, *, disabled: bool = False,
                 profile: Profile | None = None) -> None:
        super().__init__(disabled=disabled, profile=profile,
                         _paging_supported=False,
                         _ticks_per_second=3_500_000,
                         _ticks_per_horizontal_retrace=48,
                         _lines_per_vertical_retrace=24,
                         _contention_base=14335)

    # The capture is typed by construction: the machine is known to
    # be a 48K, so the type is an input, not a discovery. The ROM is
    # stated only where the socket deviates from the class's image.
    # TODO: Store all fields.
    def take_snapshot(self) -> Spectrum48CoreSnapshot:
        blocks = []
        rom = self._read_image(0x0000, 0x4000)
        if rom != Spectrum48ROM().data.data:
            blocks.append(Spectrum48MemoryBlock(addr=0x0000, data=rom))
        blocks.append(Spectrum48MemoryBlock(
            addr=0x4000, data=self._read_image(0x4000, 0xc000)))

        return Spectrum48CoreSnapshot(
            disabled=True if self.disabled else None,
            z80=self._take_z80_snapshot(),
            ula=Spectrum48ULASnapshot(
                ticks_since_int=self.ticks_since_int,
                border_colour=self.border_colour),
            memory=Spectrum48MemorySnapshot(blocks=blocks))


# The standard 48K machine. Every member exists; a None parameter
# means the standard device. The equipment -- the tape player and
# the playback player and recorder -- is machine-side:
# deterministic, on the emulated time axis, its state session
# content.
class Spectrum48(Machine, snapshot_type=Spectrum48Snapshot):
    core: Spectrum48Core
    keyboard: Keyboard
    beeper: Beeper
    tape_player: TapePlayer
    playback_player: PlaybackPlayer
    playback_recorder: PlaybackRecorder

    def __init__(self, core: Spectrum48Core | None = None,
                 keyboard: Keyboard | None = None,
                 beeper: Beeper | None = None,
                 tape_player: TapePlayer | None = None,
                 playback_player: PlaybackPlayer | None = None,
                 playback_recorder: PlaybackRecorder | None = None,
                 profile: Profile | None = None,
                 **extra_devices: Device) -> None:
        if core is None:
            core = Spectrum48Core(profile=profile)
        else:
            # The profile parameterises the standard core.
            assert profile is None

        if keyboard is None:
            keyboard = Keyboard()
        if beeper is None:
            beeper = Beeper()
        if tape_player is None:
            tape_player = TapePlayer()
        if playback_player is None:
            playback_player = PlaybackPlayer()

        # The recorder sits disabled until a feature, such as
        # playback recovery, enables it.
        if playback_recorder is None:
            playback_recorder = PlaybackRecorder(disabled=True)

        super().__init__(core=core,
                         keyboard=keyboard, beeper=beeper,
                         tape_player=tape_player,
                         playback_player=playback_player,
                         playback_recorder=playback_recorder,
                         **extra_devices)

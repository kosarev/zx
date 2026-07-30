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
    from ._device import Device

from ._beeper import Beeper
from ._beeper import BeeperSnapshot
from ._core import Core
from ._core import CoreSnapshot
from ._core import MemorySnapshot
from ._core import ULASnapshot
from ._core import Z80Snapshot
from ._data import ByteData
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


# Tells where the bytes of the given 48K address range live in the
# internal memory image: the whole 64K address space, one-to-one
# onto the leading 64K.
def _image_offset(addr: int, size: int) -> int:
    assert addr >= 0 and addr + size <= 0x10000
    return addr


# The stock 48K ROM. The type alone determines the content, so its
# node stores nothing; known ROM images are represented by types
# like this.
class Spectrum48ROM(HexData):
    def __init__(self) -> None:
        super().__init__(
            (RESOURCES / 'roms' / 'Spectrum48.rom').read_bytes())

    def to_json(self) -> dict[str, str | list[str]]:
        return {}


# The 48K's memory: the full images of the ROM socket and the RAM.
# An unstated ROM means the stock one; an unstated RAM means the
# reset content.
class Spectrum48MemorySnapshot(MemorySnapshot):
    rom: ByteData | None
    ram: ByteData | None

    def __init__(self, *, rom: Bytes | ByteData | None = None,
                 ram: Bytes | ByteData | None = None) -> None:
        if rom is not None:
            rom = HexData.wrap(rom)
            assert len(rom.data) == 0x4000
        if ram is not None:
            ram = HexData.wrap(ram)
            assert len(ram.data) == 0xc000

        super().__init__(rom=rom, ram=ram)


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

    # Reads and writes speak the 48K's flat 64K address space.
    def read(self, addr: int, size: int) -> bytes:
        return self._read_image(_image_offset(addr, size), size)

    def write(self, addr: int, block: bytes) -> None:
        self._write_image(_image_offset(addr, len(block)), block)

    def read8(self, addr: int) -> int:
        return self.read(addr, 1)[0]

    def read16(self, addr: int) -> int:
        return int.from_bytes(self.read(addr, 2), 'little')

    def _install_memory_snapshot(self, memory: MemorySnapshot) -> None:
        assert isinstance(memory, Spectrum48MemorySnapshot)

        rom = memory.rom if memory.rom is not None else Spectrum48ROM()
        self._write_image(0x0000, rom.data)
        if memory.ram is not None:
            self._write_image(0x4000, memory.ram.data)

    # The capture is typed by construction: the machine is known to
    # be a 48K, so the type is an input, not a discovery. The ROM is
    # stated only where the socket deviates from the class's image.
    # TODO: Store all fields.
    def take_snapshot(self) -> Spectrum48CoreSnapshot:
        rom = self._read_image(0x0000, 0x4000)

        return Spectrum48CoreSnapshot(
            disabled=True if self.disabled else None,
            z80=self._take_z80_snapshot(),
            ula=Spectrum48ULASnapshot(
                ticks_since_int=self.ticks_since_int,
                border_colour=self.border_colour),
            memory=Spectrum48MemorySnapshot(
                rom=None if rom == Spectrum48ROM().data else rom,
                ram=self._read_image(0x4000, 0xc000)))


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

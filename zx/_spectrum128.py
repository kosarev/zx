#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

"""What the 128K Spectrum is, as its machine and snapshot types."""

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
from ._error import Error
from ._keyboard import Keyboard
from ._keyboard import KeyboardSnapshot
from ._machine import Machine
from ._playback import PlaybackPlayer
from ._playback import PlaybackRecorder
from ._resources import RESOURCES
from ._tape import TapePlayer


# The 128K ULA. The 0x7FFD latch registers join as volatile fields
# with latch capture.
class Spectrum128ULASnapshot(ULASnapshot):
    pass


# The 128K's memory mapping: rom_page selects the ROM at
# 0x0000-0x3FFF and ram_page the RAM page at 0xC000-0xFFFF;
# 0x4000-0xBFFF always holds ram5 and ram2.
class Spectrum128MemoryMapping(MemoryMapping):
    __PAGE_SIZE = 0x4000

    # Where the 128K's pages sit in the internal memory image. This
    # statement is the published convention, which the C++ side
    # follows.
    __ROM_PAGE_IMAGE_OFFSETS: typing.ClassVar[dict[int, int]] = {
        0: 0 * __PAGE_SIZE,
        1: 4 * __PAGE_SIZE}
    __RAM_PAGE_IMAGE_OFFSETS: typing.ClassVar[dict[int, int]] = {
        5: 1 * __PAGE_SIZE,
        2: 2 * __PAGE_SIZE,
        0: 3 * __PAGE_SIZE,
        1: 5 * __PAGE_SIZE,
        3: 6 * __PAGE_SIZE,
        4: 7 * __PAGE_SIZE,
        6: 8 * __PAGE_SIZE,
        7: 9 * __PAGE_SIZE}

    def __init__(self, *, rom_page: int | None = None,
                 ram_page: int | None = None) -> None:
        self.rom_page = rom_page
        self.ram_page = ram_page

    def get_offset(self, addr: int, size: int) -> int:
        end_addr = addr + size
        assert addr >= 0 and end_addr <= 0x10000

        if addr < 0x4000:
            assert end_addr <= 0x4000
            assert self.rom_page is not None
            return self.__ROM_PAGE_IMAGE_OFFSETS[self.rom_page] + addr

        if addr < 0xc000:
            assert end_addr <= 0xc000
            return addr

        assert self.ram_page is not None
        return self.__RAM_PAGE_IMAGE_OFFSETS[self.ram_page] + (addr - 0xc000)


# A block in the 128K's paged address space: the Z80 address plus
# the page selectors of the mapping the address is meant under.
class Spectrum128MemoryBlock(MemoryBlock):
    def __init__(self, *, addr: int, rom_page: int | None = None,
                 ram_page: int | None = None,
                 data: Bytes | ByteData) -> None:
        data = HexData.wrap(data)
        mapping = Spectrum128MemoryMapping(rom_page=rom_page,
                                           ram_page=ram_page)
        super().__init__(offset=mapping.get_offset(addr, len(data.data)),
                         data=data)
        self.__addr = addr
        self.__rom_page = rom_page
        self.__ram_page = ram_page

    # The node speaks the 128K vocabulary the block was constructed
    # in.
    def to_json(self) -> dict[str, typing.Any]:
        d = super().to_json()

        node: dict[str, typing.Any] = {'addr': self.__addr}
        if self.__rom_page is not None:
            node['rom_page'] = self.__rom_page
        if self.__ram_page is not None:
            node['ram_page'] = self.__ram_page
        node['data'] = d['data']
        return node


# The 128K's memory: a collection of blocks in the 128K's paged
# address space. The given blocks amend the stock ROMs -- blocks
# carrying ROM content replace them.
class Spectrum128MemorySnapshot(MemorySnapshot, image_size=0x28000):
    def __init__(
            self, *,
            blocks: typing.Sequence[Spectrum128MemoryBlock] | None = None,
            ) -> None:
        blocks = list(blocks or [])

        # A block starting in either ROM replaces the stock ROMs.
        # TODO: Replace with ROM recognition over the canonical
        # block list.
        def starts_in_rom(block: Spectrum128MemoryBlock) -> bool:
            ROM_SIZE = 0x4000
            for rom_page in (0, 1):
                rom_offset = Spectrum128MemoryMapping(
                    rom_page=rom_page).get_offset(0x0000, ROM_SIZE)
                if rom_offset <= block.offset < rom_offset + ROM_SIZE:
                    return True
            return False

        if not any(starts_in_rom(b) for b in blocks):
            rom = (RESOURCES / 'roms' / 'Spectrum128.rom').read_bytes()
            blocks = [Spectrum128MemoryBlock(addr=0x0000, rom_page=0,
                                             data=rom[:0x4000]),
                      Spectrum128MemoryBlock(addr=0x0000, rom_page=1,
                                             data=rom[0x4000:]),
                      *blocks]

        super().__init__(image_size=self.image_size, blocks=blocks)

    # The type fixes the configuration, so the node stores only the
    # blocks.
    def to_json(self) -> dict[str, typing.Any]:
        d = super().to_json()
        return {name: d[name] for name in ('blocks',) if name in d}


# The 128K core: members not specified take their stock values. The
# remaining 128K facts, the clock and the paging, still ride the
# core's model parameter; they become core config fields as the 128K
# work proceeds.
class Spectrum128CoreSnapshot(CoreSnapshot):
    ula: Spectrum128ULASnapshot
    memory: Spectrum128MemorySnapshot

    def __init__(self, *,
                 disabled: bool | None = None,
                 z80: Z80Snapshot | None = None,
                 ula: Spectrum128ULASnapshot | None = None,
                 memory: Spectrum128MemorySnapshot | None = None) -> None:
        if ula is None:
            ula = Spectrum128ULASnapshot()
        if memory is None:
            memory = Spectrum128MemorySnapshot()

        super().__init__(disabled=disabled, z80=z80, ula=ula, memory=memory)


class Spectrum128Snapshot(MachineSnapshot):
    core: Spectrum128CoreSnapshot
    keyboard: KeyboardSnapshot
    beeper: BeeperSnapshot

    # Members not specified take their stock values, so constructing
    # with no arguments gives the stock 128K machine.
    def __init__(self, *, core: Spectrum128CoreSnapshot | None = None,
                 keyboard: KeyboardSnapshot | None = None,
                 beeper: BeeperSnapshot | None = None) -> None:
        if core is None:
            core = Spectrum128CoreSnapshot()
        if keyboard is None:
            keyboard = KeyboardSnapshot()
        if beeper is None:
            beeper = BeeperSnapshot()

        super().__init__(core=core, keyboard=keyboard, beeper=beeper)


# The 128K core: the chip family the 128K board wires, expressed as
# a type and paired with its snapshot type, so the model shows in
# the device types rather than in a runtime model field.
class Spectrum128Core(Core):
    def __init__(self, *, disabled: bool = False,
                 profile: Profile | None = None) -> None:
        super().__init__(disabled=disabled, profile=profile,
                         _paging_supported=True,
                         _ticks_per_second=3_546_900,
                         _ticks_per_horizontal_retrace=52,
                         _lines_per_vertical_retrace=23,
                         _contention_base=14361)

    # Reads and writes speak the 128K's paged address space: the Z80
    # address plus the page selection it is meant under.
    # TODO: Default omitted pages to the live 0x7FFD latch once it
    # is marshalled in the state image.
    def read(self, addr: int, size: int, *,
             rom_page: int | None = None,
             ram_page: int | None = None) -> bytes:
        mapping = Spectrum128MemoryMapping(rom_page=rom_page,
                                           ram_page=ram_page)
        return self._read_image(mapping.get_offset(addr, size), size)

    def write(self, addr: int, block: bytes, *,
              rom_page: int | None = None,
              ram_page: int | None = None) -> None:
        mapping = Spectrum128MemoryMapping(rom_page=rom_page,
                                           ram_page=ram_page)
        self._write_image(mapping.get_offset(addr, len(block)), block)

    # TODO: Support 128K capture -- needs the 0x7FFD latch
    # marshalled in the state image.
    def take_snapshot(self) -> Spectrum128CoreSnapshot:
        raise Error('128K capture is not supported yet.',
                    id='128k_capture_not_supported')


# The standard 128K machine. Every member exists; a None parameter
# means the standard device, the equipment included, as on the 48K.
class Spectrum128(Machine, snapshot_type=Spectrum128Snapshot):
    core: Spectrum128Core
    keyboard: Keyboard
    beeper: Beeper
    tape_player: TapePlayer
    playback_player: PlaybackPlayer
    playback_recorder: PlaybackRecorder

    def __init__(self, core: Spectrum128Core | None = None,
                 keyboard: Keyboard | None = None,
                 beeper: Beeper | None = None,
                 tape_player: TapePlayer | None = None,
                 playback_player: PlaybackPlayer | None = None,
                 playback_recorder: PlaybackRecorder | None = None,
                 profile: Profile | None = None,
                 **extra_devices: Device) -> None:
        if core is None:
            core = Spectrum128Core(profile=profile)
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

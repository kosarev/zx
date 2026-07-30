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
    from ._device import Device

from ._beeper import Beeper
from ._beeper import BeeperSnapshot
from ._core import Core
from ._core import CoreSnapshot
from ._core import MemorySnapshot
from ._core import ULASnapshot
from ._core import Z80Snapshot
from ._data import ByteData
from ._data import DataRecord
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


_PAGE_SIZE = 0x4000

# Where the 128K's pages sit in the internal memory image. This
# statement is the published convention, which the C++ side
# follows.
_ROM_PAGE_IMAGE_OFFSETS = {
    0: 0 * _PAGE_SIZE,
    1: 4 * _PAGE_SIZE}
_RAM_PAGE_IMAGE_OFFSETS = {
    5: 1 * _PAGE_SIZE,
    2: 2 * _PAGE_SIZE,
    0: 3 * _PAGE_SIZE,
    1: 5 * _PAGE_SIZE,
    3: 6 * _PAGE_SIZE,
    4: 7 * _PAGE_SIZE,
    6: 8 * _PAGE_SIZE,
    7: 9 * _PAGE_SIZE}


# Tells where the bytes of the given 128K address range live in the
# internal memory image: rom_page selects the ROM at 0x0000-0x3FFF
# and ram_page the RAM page at 0xC000-0xFFFF; 0x4000-0xBFFF always
# holds ram5 and ram2. A range never crosses from one page to
# another; content that would is handled piecewise.
def _image_offset(addr: int, size: int, *,
                  rom_page: int | None = None,
                  ram_page: int | None = None) -> int:
    end_addr = addr + size
    assert addr >= 0 and end_addr <= 0x10000

    if addr < 0x4000:
        assert end_addr <= 0x4000
        assert rom_page is not None
        return _ROM_PAGE_IMAGE_OFFSETS[rom_page] + addr

    if addr < 0xc000:
        assert end_addr <= 0xc000
        return addr

    assert ram_page is not None
    return _RAM_PAGE_IMAGE_OFFSETS[ram_page] + (addr - 0xc000)


# The stock 128K ROM pages: the 128K editor in page 0, the 48K
# BASIC variant in page 1, halves of one resource image. The types
# alone determine the content, so their nodes store nothing.
class Spectrum128ROM0(HexData):
    def __init__(self) -> None:
        super().__init__((RESOURCES / 'roms' /
                          'Spectrum128.rom').read_bytes()[:_PAGE_SIZE])

    def to_json(self) -> dict[str, str | list[str]]:
        return {}


class Spectrum128ROM1(HexData):
    def __init__(self) -> None:
        super().__init__((RESOURCES / 'roms' /
                          'Spectrum128.rom').read_bytes()[_PAGE_SIZE:])

    def to_json(self) -> dict[str, str | list[str]]:
        return {}


# The 128K's memory: the full images of the two ROM pages and the
# eight RAM pages. An unstated ROM page means the stock one; an
# unstated RAM page means the reset content.
class Spectrum128MemorySnapshot(MemorySnapshot, image_size=0x28000):
    rom0: ByteData | None
    rom1: ByteData | None
    ram0: ByteData | None
    ram1: ByteData | None
    ram2: ByteData | None
    ram3: ByteData | None
    ram4: ByteData | None
    ram5: ByteData | None
    ram6: ByteData | None
    ram7: ByteData | None

    def __init__(self, *, rom0: Bytes | ByteData | None = None,
                 rom1: Bytes | ByteData | None = None,
                 ram0: Bytes | ByteData | None = None,
                 ram1: Bytes | ByteData | None = None,
                 ram2: Bytes | ByteData | None = None,
                 ram3: Bytes | ByteData | None = None,
                 ram4: Bytes | ByteData | None = None,
                 ram5: Bytes | ByteData | None = None,
                 ram6: Bytes | ByteData | None = None,
                 ram7: Bytes | ByteData | None = None) -> None:
        pages = {}
        for name, page in (('rom0', rom0), ('rom1', rom1),
                           ('ram0', ram0), ('ram1', ram1),
                           ('ram2', ram2), ('ram3', ram3),
                           ('ram4', ram4), ('ram5', ram5),
                           ('ram6', ram6), ('ram7', ram7)):
            if page is not None:
                page = HexData.wrap(page)
                assert len(page.data) == _PAGE_SIZE
            pages[name] = page

        # The model type states whole page images; the plain base's
        # block vocabulary does not apply, so the fields go straight
        # to DataRecord.
        DataRecord.__init__(self, **pages)


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
        return self._read_image(
            _image_offset(addr, size, rom_page=rom_page,
                          ram_page=ram_page), size)

    def write(self, addr: int, block: bytes, *,
              rom_page: int | None = None,
              ram_page: int | None = None) -> None:
        self._write_image(
            _image_offset(addr, len(block), rom_page=rom_page,
                          ram_page=ram_page), block)

    def _install_memory_snapshot(self, memory: MemorySnapshot) -> None:
        if not isinstance(memory, Spectrum128MemorySnapshot):
            super()._install_memory_snapshot(memory)
            return

        for page_no, rom in enumerate((memory.rom0, memory.rom1)):
            if rom is None:
                rom = Spectrum128ROM0() if page_no == 0 else Spectrum128ROM1()
            self._write_image(_ROM_PAGE_IMAGE_OFFSETS[page_no], rom.data)

        for page_no, ram in enumerate((memory.ram0, memory.ram1,
                                       memory.ram2, memory.ram3,
                                       memory.ram4, memory.ram5,
                                       memory.ram6, memory.ram7)):
            if ram is not None:
                self._write_image(_RAM_PAGE_IMAGE_OFFSETS[page_no], ram.data)

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

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2025 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import numpy
import typing

from ._binary import Bytes
from ._binary import BinaryParser
from ._binary import BinaryWriter
from ._data import DataRecord
from ._data import MachineSnapshot
from ._data import UnifiedSnapshot
from ._error import Error
from ._utils import get_high8
from ._utils import get_low8
from ._utils import make16


class Z80SnapshotV3ExtraHeader(DataRecord, format_name=None):
    last_write_to_port_1ffd: int

    def __init__(self, *, last_write_to_port_1ffd: int = 0):
        super().__init__(last_write_to_port_1ffd=last_write_to_port_1ffd)

    __V3_EXTRA_HEADER = ['B:last_write_to_port_1ffd']

    @classmethod
    def parse_header(cls, parser: BinaryParser) -> 'Z80SnapshotV3ExtraHeader':
        v3_extra_fields = parser.parse(cls.__V3_EXTRA_HEADER)
        return Z80SnapshotV3ExtraHeader(**v3_extra_fields)

    def write(self, writer: BinaryWriter) -> None:
        writer.write(self.__V3_EXTRA_HEADER, **dict(self))


class Z80SnapshotV3Header(DataRecord, format_name=None):
    ticks_count_low: int
    ticks_count_high: int
    spectator_flag: int
    mgt_rom_paged: int
    multiface_rom_paged: int
    memory_at_0000_1fff_is_rom: int
    memory_at_2000_3fff_is_rom: int
    keyboard_mappings: tuple[int, ...]
    keyboard_mapping_keys: tuple[int, ...]
    mgt_type: int
    disciple_inhibit_button_status: int
    disciple_inhibit_flag: int

    v3_extra_header: Z80SnapshotV3ExtraHeader | None

    __V3_HEADER = [
        '<H:ticks_count_low', 'B:ticks_count_high', 'B:spectator_flag',
        'B:mgt_rom_paged', 'B:multiface_rom_paged',
        'B:memory_at_0000_1fff_is_rom', 'B:memory_at_2000_3fff_is_rom',
        '10B:keyboard_mappings', '10B:keyboard_mapping_keys',
        'B:mgt_type', 'B:disciple_inhibit_button_status',
        'B:disciple_inhibit_flag']

    def __init__(
            self, *,
            ticks_count_low: int = 0,
            ticks_count_high: int = 0,
            spectator_flag: int = 0,
            mgt_rom_paged: int = 0,
            multiface_rom_paged: int = 0,
            memory_at_0000_1fff_is_rom: int = 0,
            memory_at_2000_3fff_is_rom: int = 0,
            keyboard_mappings: tuple[int, ...] = (0,) * 10,
            keyboard_mapping_keys: tuple[int, ...] = (0,) * 10,
            mgt_type: int = 0,
            disciple_inhibit_button_status: int = 0,
            disciple_inhibit_flag: int = 0,
            v3_extra_header: Z80SnapshotV3ExtraHeader | None = None):
        super().__init__(
            ticks_count_low=ticks_count_low,
            ticks_count_high=ticks_count_high,
            spectator_flag=spectator_flag,
            mgt_rom_paged=mgt_rom_paged,
            multiface_rom_paged=multiface_rom_paged,
            memory_at_0000_1fff_is_rom=memory_at_0000_1fff_is_rom,
            memory_at_2000_3fff_is_rom=memory_at_2000_3fff_is_rom,
            keyboard_mappings=keyboard_mappings,
            keyboard_mapping_keys=keyboard_mapping_keys,
            mgt_type=mgt_type,
            disciple_inhibit_button_status=disciple_inhibit_button_status,
            disciple_inhibit_flag=disciple_inhibit_flag,
            v3_extra_header=v3_extra_header)

    @classmethod
    def parse_header(cls, parser: BinaryParser) -> 'Z80SnapshotV3Header':
        v3_fields = parser.parse(cls.__V3_HEADER)

        v3_extra_header = None
        if parser:
            v3_extra_header = Z80SnapshotV3ExtraHeader.parse_header(parser)

        return Z80SnapshotV3Header(
            **v3_fields,
            v3_extra_header=v3_extra_header)

    def write(self, writer: BinaryWriter) -> None:
        writer.write(self.__V3_HEADER, **dict(self))

        if self.v3_extra_header is not None:
            self.v3_extra_header.write(writer)


class Z80SnapshotV2Header(DataRecord, format_name=None):
    extra_header_size: int
    pc: int
    hardware_mode: int
    misc1: int
    misc2: int
    flags3: int
    port_fffd_value: int
    sound_chip_regs: tuple[int, ...]

    v3_header: Z80SnapshotV3Header | None

    __V2_HEADER = [
        '<H:pc', 'B:hardware_mode', 'B:misc1', 'B:misc2', 'B:flags3',
        'B:port_fffd_value', '16B:sound_chip_regs']

    def __init__(
            self, *,
            pc: int = 0,
            hardware_mode: int = 0,
            misc1: int = 0,
            misc2: int = 0,
            flags3: int = 0,
            port_fffd_value: int = 0,
            sound_chip_regs: tuple[int, ...] = (0,) * 16,
            v3_header: Z80SnapshotV3Header | None = None):
        super().__init__(
            pc=pc, hardware_mode=hardware_mode,
            misc1=misc1, misc2=misc2, flags3=flags3,
            port_fffd_value=port_fffd_value,
            sound_chip_regs=sound_chip_regs,
            v3_header=v3_header)

    @classmethod
    def parse_header(cls, parser: BinaryParser) -> 'Z80SnapshotV2Header':
        v2_fields = parser.parse(cls.__V2_HEADER)

        v3_header = None
        if parser:
            v3_header = Z80SnapshotV3Header.parse_header(parser)

        return Z80SnapshotV2Header(
            **v2_fields,
            v3_header=v3_header)

    def write(self, writer: BinaryWriter) -> None:
        writer.write(self.__V2_HEADER, **dict(self))

        if self.v3_header is not None:
            self.v3_header.write(writer)


class Z80Snapshot(MachineSnapshot, format_name='Z80'):
    # Some snapshots contain zero pages as well.
    __MEMORY_PAGE_ADDRS = {0: 0x0000, 4: 0x8000, 5: 0xc000, 8: 0x4000}

    a: int
    f: int
    bc: int
    hl: int
    pc: int
    sp: int
    i: int
    r: int
    flags1: int
    de: int
    alt_bc: int
    alt_de: int
    alt_hl: int
    alt_a: int
    alt_f: int
    iy: int
    ix: int
    iff1: bool
    iff2: bool
    flags2: int

    v2_header: Z80SnapshotV2Header | None

    memory_image: Bytes
    memory_blocks: typing.Sequence[tuple[int, int, bytes]]

    def __init__(
            self, *,
            a: int = 0, f: int = 0, bc: int = 0, hl: int = 0,
            pc: int = 0, sp: int = 0, i: int = 0, r: int = 0,
            flags1: int = 0,
            de: int = 0,
            alt_bc: int = 0, alt_de: int = 0, alt_hl: int = 0,
            alt_a: int = 0, alt_f: int = 0,
            iy: int = 0, ix: int = 0,
            iff1: int = 0, iff2: int = 0,
            flags2: int = 0,
            v2_header: Z80SnapshotV2Header | None = None,
            memory_image: Bytes | None = None,
            memory_blocks: (
                typing.Sequence[tuple[int, int, Bytes]] | None) = None):
        if memory_image is not None:
            assert memory_blocks is None
        if memory_blocks is not None:
            assert memory_image is None
        super().__init__(
            a=a, f=f, bc=bc, hl=hl, pc=pc, sp=sp,
            i=i, r=r, flags1=flags1, de=de,
            alt_bc=alt_bc, alt_de=alt_de, alt_hl=alt_hl,
            alt_a=alt_a, alt_f=alt_f,
            iy=iy, ix=ix, iff1=iff1, iff2=iff2, flags2=flags2,
            v2_header=v2_header,
            memory_image=memory_image,
            memory_blocks=memory_blocks)

    @classmethod
    def from_snapshot(cls, snapshot: MachineSnapshot) -> 'Z80Snapshot':
        unified = snapshot.to_unified_snapshot()

        # TODO: The z80 format cannot represent processor states in
        #       the middle of IX- and IY-prefixed instructions, so
        #       such situations need some additional processing.
        # TODO: Check for similar problems with other state attributes.
        # TODO: How do other emulators solve this problem?
        assert (unified.iregp_kind or 'hl') == 'hl'

        flags1 = 0
        flags2 = 0

        # Bit 7 of the stored R value is not signigicant and
        # shall be taken from bit 0 of flags1.
        r = get_low8(unified.ir or 0)
        flags1 |= (r & 0x80) >> 7
        r &= 0x7f

        border_colour = unified.border_colour or 0
        assert 0 <= border_colour <= 7
        flags1 |= border_colour << 1

        int_mode = unified.int_mode or 0
        assert int_mode in [0, 1, 2]  # TODO
        flags2 |= int_mode

        # Build full memory image.
        # TODO: Frobid any data below address 0x4000.
        memory_blocks = []
        if unified.memory_blocks is not None:
            RAM_SIZE = 0x10000
            image: list[None | int] = [None] * RAM_SIZE
            for addr, block in unified.memory_blocks:
                image[addr:addr+len(block)] = list(block)

            PAGE_SIZE = 0x4000
            EMPTY_PAGE = [None] * PAGE_SIZE
            for page_no, addr in cls.__MEMORY_PAGE_ADDRS.items():
                page = image[addr:addr+PAGE_SIZE]
                if page != EMPTY_PAGE:
                    page_image = bytes(0 if b is None else b for b in page)
                    memory_blocks.append((page_no, 0xffff, page_image))

        # https://worldofspectrum.org/faq/reference/z80format.htm
        # The hi T state counter counts up modulo 4. Just after the ULA
        # generates its once-in-every-20-ms interrupt, it is 3, and is
        # increased by one every 5 emulated milliseconds. In these
        # 1/200s intervals, the low T state counter counts down from
        # 17471 to 0 (17726 in 128K modes), which make a total of 69888
        # (70908) T states per frame.
        ticks_per_frame = 69888  # TODO
        quarter_frame = ticks_per_frame // 4
        ticks_since_int = unified.ticks_since_int or 0
        ticks_high = (ticks_since_int // quarter_frame + 3) % 4
        ticks_low = (quarter_frame - 1) - ticks_since_int % quarter_frame

        return Z80Snapshot(
            a=get_high8(unified.af or 0),
            f=get_low8(unified.af or 0),
            bc=unified.bc or 0,
            hl=unified.hl or 0,
            pc=0,
            sp=unified.sp or 0,
            i=get_high8(unified.ir or 0),
            r=get_low8(unified.ir or 0) & 0x7f,
            flags1=flags1,
            de=unified.de or 0,
            alt_bc=unified.alt_bc or 0,
            alt_de=unified.alt_de or 0,
            alt_hl=unified.alt_hl or 0,
            alt_a=get_high8(unified.alt_af or 0),
            alt_f=get_low8(unified.alt_af or 0),
            iy=unified.iy or 0,
            ix=unified.ix or 0,
            iff1=unified.iff1 or 0,
            iff2=unified.iff2 or 0,
            flags2=flags2,
            v2_header=Z80SnapshotV2Header(
                pc=unified.pc or 0,
                v3_header=Z80SnapshotV3Header(
                    ticks_count_low=ticks_low,
                    ticks_count_high=ticks_high,
                    v3_extra_header=Z80SnapshotV3ExtraHeader())),
            memory_blocks=memory_blocks)

    def to_unified_snapshot(self) -> UnifiedSnapshot:
        flags1 = 0x01 if self.flags1 == 0xff else self.flags1

        int_mode = self.flags2 & 0x3
        if int_mode not in [0, 1, 2]:
            raise Error(f'Invalid interrupt mode {int_mode}.')

        ticks_per_frame = 69888  # TODO
        quarter_frame = ticks_per_frame // 4

        # Give the snapshot a chance to execute at least one
        # instruction without firing up an interrupt.
        # TODO: Should this be instead done at installing of the snapshot?
        ticks_since_int = ticks_per_frame - 23

        if self.v2_header is not None:
            v3_header = self.v2_header.v3_header
            if v3_header is not None:
                # https://worldofspectrum.org/faq/reference/z80format.htm
                ticks_high = v3_header.ticks_count_high
                ticks_low = v3_header.ticks_count_low
                ticks_since_int = (
                    (ticks_high - 3) % 4 * quarter_frame +
                    ((quarter_frame - 1) - ticks_low % quarter_frame))

        # Determine machine kind.
        # TODO: Not used currently?
        if self.v2_header is None:
            machine_kind = 'ZX Spectrum 48K'
        else:
            hardware_mode = self.v2_header.hardware_mode
            flags3_bit7 = (self.v2_header.flags3 & 0x80) >> 7
            if hardware_mode == 0 and not flags3_bit7:
                machine_kind = 'ZX Spectrum 48K'
            else:
                raise Error('Unsupported type of emulated machine.',
                            id='unsupported_machine')

        # Handle memory blocks.
        memory_blocks: list[tuple[int, Bytes]] = []
        if self.memory_image is not None:
            assert self.memory_blocks is None

            memory_image = self.memory_image
            compressed = bool(self.flags1 & 0x20)
            if not compressed:
                if len(memory_image) != 48 * 1024:
                    raise Error('Z80 snapshot: memory image is too large.',
                                id='z80_snapshot_memory_image_too_large')
            else:
                if memory_image[-4:] != b'\x00\xed\xed\x00':
                    raise Error('Z80 snapshot: compressed memory image has '
                                'no end marker.',
                                id='z80_snapshot_no_end_marker')
                memory_image = self.__uncompress(memory_image[:-4], 48 * 1024)
            memory_blocks.extend([
                (0x4000, memory_image[0x0000:0x4000]),
                (0x8000, memory_image[0x4000:0x8000]),
                (0xc000, memory_image[0x8000:0xc000])])
        else:
            assert machine_kind == 'ZX Spectrum 48K', machine_kind  # TODO

            BLOCK_SIZE = 16 * 1024
            for page_no, compressed_size, image in self.memory_blocks:
                if compressed_size != 0xffff:
                    assert len(image) == compressed_size
                    image = self.__uncompress(image, BLOCK_SIZE)

                memory_blocks.append((self.__MEMORY_PAGE_ADDRS[page_no],
                                      image))

        return UnifiedSnapshot(
            af=make16(self.a, self.f),
            bc=self.bc,
            de=self.de,
            hl=self.hl,
            ix=self.ix,
            iy=self.iy,
            alt_af=make16(self.alt_a, self.alt_f),
            alt_bc=self.alt_bc,
            alt_de=self.alt_de,
            alt_hl=self.alt_hl,
            pc=self.v2_header.pc if self.v2_header is not None else self.pc,
            sp=self.sp,
            ir=make16(self.i, (self.r & 0x7f) | ((flags1 & 0x1) << 7)),
            iregp_kind='hl',
            iff1=0 if self.iff1 == 0 else 1,
            iff2=0 if self.iff2 == 0 else 1,
            int_mode=int_mode,
            ticks_since_int=ticks_since_int,
            border_colour=(flags1 >> 1) & 0x7,
            memory_blocks=memory_blocks)

    __V1_HEADER = [
        'B:a', 'B:f', '<H:bc', '<H:hl', '<H:pc', '<H:sp', 'B:i', 'B:r',
        'B:flags1', '<H:de', '<H:alt_bc', '<H:alt_de', '<H:alt_hl',
        'B:alt_a', 'B:alt_f', '<H:iy', '<H:ix', 'B:iff1', 'B:iff2', 'B:flags2']

    @classmethod
    def __uncompress(cls, compressed_image: Bytes,
                     uncompressed_size: int) -> Bytes:
        MARKER = b'\xed\xed'
        input = bytes(compressed_image)
        output = bytearray()
        while input:
            a, m, b = input.partition(MARKER)
            output.extend(a)

            if m:
                assert m == MARKER
                if len(b) < 2:
                    raise Error('Corrupted compressed memory block: '
                                'incomplete repetition marker.',
                                id='corrupted_compressed_memory_block')

                count, filler = b[0], b[1:2]
                output.extend(filler * count)
                b = b[2:]

            input = b

        if len(output) != uncompressed_size:
            raise Error('Corrupted compressed memory block: '
                        f'expected {uncompressed_size} bytes, '
                        f'but got {len(output)}.',
                        id='corrupted_compressed_memory_block')

        return bytes(output)

    def __compress(cls, image: Bytes) -> bytes:
        # For every element see if it's equal to the subsequent one.
        input = numpy.frombuffer(image, dtype=numpy.uint8)
        eq = input[:-1] == input[1:]

        # Find indexes where sequences of repeating bytes start and
        # just before they stop.
        indexes, = numpy.where(eq[1:] != eq[:-1])
        indexes = numpy.append(indexes + 1, len(input))

        # Emit the partitions of repeating and non-repeating bytes.
        input_size = len(input)
        output = bytearray()
        p = 0
        ends_with_non_blocked_ed = False
        for i in indexes:
            if p == i:
                continue

            if p == input_size - 1 or not eq[p]:
                output.extend(image[p:i])
                p += i - p
                ends_with_non_blocked_ed = output[-1] == 0xed
                continue

            if ends_with_non_blocked_ed:
                assert image[p] != 0xed
                output.append(image[p])
                p += 1
                ends_with_non_blocked_ed = False

            count = min(i + 1, input_size) - p
            while count:
                chunk = min(count, 0xff)
                if chunk >= 5 or image[p] == 0xed:
                    output.extend((0xed, 0xed, chunk, input[p]))
                    ends_with_non_blocked_ed = False
                else:
                    output.extend(image[p:p+chunk])
                    ends_with_non_blocked_ed = output[-1] == 0xed
                count -= chunk
                p += chunk

        return bytes(output)

    @classmethod
    def __parse_memory_block(
            cls, parser: BinaryParser) -> tuple[int, int, Bytes]:
        compressed_size = parser.parse_field('<H')
        assert isinstance(compressed_size, int)
        page_no = parser.parse_field('B')
        assert isinstance(page_no, int)

        BLOCK_SIZE = 16 * 1024
        size = BLOCK_SIZE if compressed_size == 0xffff else compressed_size
        image = parser.read_bytes(size)

        return page_no, compressed_size, image

    @classmethod
    def parse(cls, filename: str, image: Bytes) -> 'Z80Snapshot':
        # Parse headers.
        parser = BinaryParser(image)
        v1_fields = parser.parse(cls.__V1_HEADER)

        v2_header = None
        if v1_fields['pc'] == 0:
            extra_header_size = parser.parse_field('<H')
            assert isinstance(extra_header_size, int)
            extra_header = parser.read_bytes(extra_header_size)
            extra_parser = BinaryParser(extra_header)
            v2_header = Z80SnapshotV2Header.parse_header(extra_parser)

            if extra_parser:
                raise Error('Z80 snapshot: the extra header is too large.',
                            id='z80_snapshot_extra_header_too_large')

        # Parse memory snapshot.
        memory_image: Bytes | None = None
        memory_blocks: typing.Sequence[tuple[int, int, Bytes]] | None = None
        if v2_header is None:
            memory_image = parser.read_remaining_bytes()
        else:
            memory_blocks = []
            while parser:
                memory_blocks.append(cls.__parse_memory_block(parser))

        return Z80Snapshot(**v1_fields,
                           v2_header=v2_header,
                           memory_image=memory_image,
                           memory_blocks=memory_blocks)

    def encode(self) -> bytes:
        writer = BinaryWriter()
        writer.write(self.__V1_HEADER, **dict(self))

        if self.v2_header is None:
            writer.write_bytes(self.memory_image)
        else:
            extra_writer = BinaryWriter()
            self.v2_header.write(extra_writer)
            extra_header = extra_writer.get_image()

            writer.write_field('<H', len(extra_header))
            writer.write_bytes(extra_header)

            if self.memory_blocks is not None:
                for page_no, compressed_size, block in self.memory_blocks:
                    writer.write_field('<H', compressed_size)
                    writer.write_field('B', page_no)
                    writer.write_bytes(block)

        return writer.get_image()

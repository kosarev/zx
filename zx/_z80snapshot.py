# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from __future__ import annotations

import typing
import collections
from ._binary import Bytes
from ._binary import BinaryParser, BinaryWriter
from ._data import MachineSnapshot
from ._data import UnifiedSnapshot
from ._error import Error
from ._utils import get_high8
from ._utils import get_low8
from ._utils import make16


class Z80Snapshot(MachineSnapshot, format_name='Z80'):
    _MEMORY_PAGE_ADDRS = {4: 0x8000, 5: 0xc000, 8: 0x4000}

    # v1
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

    # v2
    extra_header_size: int
    pc2: int
    hardware_mode: int
    misc1: int
    misc2: int
    flags3: int
    port_fffd_value: int
    sound_chip_regs: tuple[int]

    # v3
    ticks_count_low: int
    ticks_count_high: int
    spectator_flag: int
    mgt_rom_paged: int
    multiface_rom_paged: int
    memory_at_0000_1fff_is_rom: int
    memory_at_2000_3fff_is_rom: int
    keyboard_mappings: tuple[int]
    keyboard_mapping_keys: tuple[int]
    mgt_type: int
    disciple_inhibit_button_status: int
    disciple_inhibit_flag: int

    last_write_to_port_1ffd: int

    memory_image: Bytes
    memory_blocks: list[tuple[int, bytes]]

    def __init__(self, *,
                 a: int = 0, f: int = 0, bc: int = 0, hl: int = 0,
                 pc: int = 0, sp: int = 0, i: int = 0, r: int = 0,
                 flags1: int = 0,
                 de: int = 0,
                 alt_bc: int = 0, alt_de: int = 0, alt_hl: int = 0,
                 alt_a: int = 0, alt_f: int = 0,
                 iy: int = 0, ix: int = 0,
                 iff1: int = 0, iff2: int = 0,
                 flags2: int = 0,
                 extra_header_size: int | None = None,
                 pc2: int | None = None,
                 hardware_mode: int | None = None,
                 misc1: int | None = None,
                 misc2: int | None = None,
                 flags3: int | None = None,
                 port_fffd_value: int | None = None,
                 sound_chip_regs: tuple[int] | None = None,
                 ticks_count_low: int | None = None,
                 ticks_count_high: int | None = None,
                 spectator_flag: int | None = None,
                 mgt_rom_paged: int | None = None,
                 multiface_rom_paged: int | None = None,
                 memory_at_0000_1fff_is_rom: int | None = None,
                 memory_at_2000_3fff_is_rom: int | None = None,
                 keyboard_mappings: tuple[int] | None = None,
                 keyboard_mapping_keys: tuple[bytes] | None = None,
                 mgt_type: int | None = None,
                 disciple_inhibit_button_status: int | None = None,
                 disciple_inhibit_flag: int | None = None,
                 last_write_to_port_1ffd: int | None = None,
                 memory_image: Bytes | None = None,
                 memory_blocks: list[tuple[int, Bytes]] | None = None):
        if memory_image is not None:
            assert memory_blocks is None
            assert len(memory_image) == 48 * 1024
        if memory_blocks is not None:
            assert memory_image is None
        super().__init__(
            a=a, f=f, bc=bc, hl=hl, pc=pc, sp=sp,
            i=i, r=r, flags1=flags1, de=de,
            alt_bc=alt_bc, alt_de=alt_de, alt_hl=alt_hl,
            alt_a=alt_a, alt_f=alt_f,
            iy=iy, ix=ix, iff1=iff1, iff2=iff2, flags2=flags2,
            extra_header_size=extra_header_size,
            pc2=pc2, hardware_mode=hardware_mode,
            misc1=misc1, misc2=misc2, flags3=flags3,
            port_fffd_value=port_fffd_value,
            sound_chip_regs=sound_chip_regs,
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
            last_write_to_port_1ffd=last_write_to_port_1ffd,
            memory_image=memory_image,
            memory_blocks=memory_blocks)

    @classmethod
    def from_snapshot(cls, snapshot: MachineSnapshot) -> Z80Snapshot:
        unified = snapshot.to_unified_snapshot()

        # TODO: The z80 format cannot represent processor states in
        #       the middle of IX- and IY-prefixed instructions, so
        #       such situations need some additional processing.
        # TODO: Check for similar problems with other state attributes.
        # TODO: How do other emulators solve this problem?
        assert (unified.iregp_kind or 'hl') == 'hl'

        # TODO: Null PC is an indicator of presence of extra headers.
        # The PC value would need to be encoded in these headers.
        # TODO: However, it is also possible to have an old-format
        # snapshots with null PC values. We should support these too.
        if unified.pc == 0:
            raise Error('Making snashots with null PC is not supported yet.')

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
        memory_image = bytearray(0x10000)
        if unified.memory_blocks is not None:
            for addr, block in unified.memory_blocks:
                memory_image[addr:addr+len(block)] = block

        return Z80Snapshot(
            a=get_high8(unified.af or 0),
            f=get_low8(unified.af or 0),
            bc=unified.bc or 0,
            hl=unified.hl or 0,
            pc=unified.pc or 0,
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
            memory_image=memory_image[0x4000:])

    def to_unified_snapshot(self) -> UnifiedSnapshot:
        flags1 = 0x01 if self.flags1 == 0xff else self.flags1

        int_mode = self.flags2 & 0x3
        if int_mode not in [0, 1, 2]:
            raise Error(f'Invalid interrupt mode {int_mode}.')

        ticks_per_frame = 69888  # TODO
        quarter_tstates = ticks_per_frame // 4

        # Give the snapshot a chance to execute at least one
        # instruction without firing up an interrupt.
        # TODO: Should this be instead done at installing of the snapshot?
        ticks_since_int = ticks_per_frame - 23

        if self.ticks_count_high is not None:
            ticks_high = self.ticks_count_high
            ticks_low = self.ticks_count_low
            ticks_since_int = (((ticks_high + 1) % 4 + 1) * quarter_tstates -
                               (ticks_low + 1))

        # Determine machine kind.
        # TODO: Not used currently?
        if self.hardware_mode is None:
            machine_kind = 'ZX Spectrum 48K'
        else:
            hardware_mode = self.hardware_mode
            flags3_bit7 = (self.flags3 & 0x80) >> 7
            if hardware_mode == 0 and not flags3_bit7:
                machine_kind = 'ZX Spectrum 48K'
            else:
                raise Error('Unsupported type of emulated machine.',
                            id='unsupported_machine')

        # Handle memory blocks.
        memory_blocks: list[tuple[int, Bytes]] = []
        if self.memory_image is not None:
            assert self.memory_blocks is None
            memory_blocks.append((0x4000, self.memory_image))
        else:
            assert machine_kind == 'ZX Spectrum 48K', machine_kind  # TODO
            for page_no, image in self.memory_blocks:
                memory_blocks.append((self._MEMORY_PAGE_ADDRS[page_no], image))

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
            pc=self.pc2 if self.pc2 is not None else self.pc,
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

    __EXTRA_HEADER_SIZE = [
        '<H:extra_header_size']

    __V2_HEADER = [
        '<H:pc2', 'B:hardware_mode', 'B:misc1', 'B:misc2', 'B:flags3',
        'B:port_fffd_value', '16B:sound_chip_regs']

    __V3_HEADER = [
        '<H:ticks_count_low', 'B:ticks_count_high', 'B:spectator_flag',
        'B:mgt_rom_paged', 'B:multiface_rom_paged',
        'B:memory_at_0000_1fff_is_rom', 'B:memory_at_2000_3fff_is_rom',
        '10B:keyboard_mappings', '10B:keyboard_mapping_keys',
        'B:mgt_type', 'B:disciple_inhibit_button_status',
        'B:disciple_inhibit_flag']

    __V3_EXTRA_HEADER = [
        'B:last_write_to_port_1ffd']

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

    @classmethod
    def __parse_memory_block(cls, parser: BinaryParser) -> tuple[int, bytes]:
        BLOCK_SIZE = 16 * 1024
        compressed_size = parser.parse_field('<H')
        assert isinstance(compressed_size, int)
        page_no = parser.parse_field('B')
        assert isinstance(page_no, int)
        if compressed_size == 0xffff:
            image = parser.read_bytes(BLOCK_SIZE)
        else:
            compressed_image = parser.read_bytes(compressed_size)
            image = cls.__uncompress(compressed_image, BLOCK_SIZE)
        return page_no, image

    @classmethod
    def parse(cls, filename: str, image: Bytes) -> 'Z80Snapshot':
        # Parse headers.
        parser = BinaryParser(image)
        version = 1
        fields = parser.parse(cls.__V1_HEADER)

        if fields['pc'] == 0:
            version = 2
            fields.update(parser.parse(cls.__EXTRA_HEADER_SIZE))

            extra_headers = parser.read_bytes(fields['extra_header_size'])
            extra_parser = BinaryParser(extra_headers)
            fields.update(extra_parser.parse(cls.__V2_HEADER))

            if extra_parser:
                version = 3
                fields.update(extra_parser.parse(cls.__V3_HEADER))

            if extra_parser:
                fields.update(extra_parser.parse(cls.__V3_EXTRA_HEADER))

            if extra_parser:
                raise Error('Too many headers in Z80 snapshot.',
                            id='too_many_z80_snapshot_headers')

        # Parse memory snapshot.
        memory_image: bytes | None = None
        memory_blocks: list[tuple[int, bytes]] | None = None
        if version == 1:
            compressed = bool(fields['flags1'] & 0x20)
            memory_image = parser.read_remaining_bytes()
            if not compressed:
                if len(memory_image) != 48 * 1024:
                    raise Error('The snapshot is too large.')
            else:
                if memory_image[-4:] != b'\x00\xed\xed\x00':
                    raise Error('The compressed memory block does not '
                                'terminate properly.')
                memory_image = cls.__uncompress(memory_image[:-4], 48 * 1024)
        else:
            memory_blocks = []
            while parser:
                memory_blocks.append(cls.__parse_memory_block(parser))

        return Z80Snapshot(**fields,
                           memory_image=memory_image,
                           memory_blocks=memory_blocks)

    def encode(self) -> bytes:
        # Write v1 header.
        # TODO: Support other versions.
        assert self.extra_header_size is None
        writer = BinaryWriter()
        writer.write(
            self.__V1_HEADER,
            a=self.a, f=self.f, bc=self.bc,
            hl=self.hl, pc=self.pc, sp=self.sp,
            i=self.i, r=self.r, flags1=self.flags1, de=self.de,
            alt_bc=self.alt_bc, alt_de=self.alt_de,
            alt_hl=self.alt_hl,
            alt_a=self.alt_a, alt_f=self.alt_f,
            iy=self.iy, ix=self.ix,
            iff1=self.iff1, iff2=self.iff2, flags2=self.flags2)

        # Write memory snapshot.
        writer.write_block(self.memory_image)

        return writer.get_image()

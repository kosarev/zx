# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


from ._binary import BinaryParser, BinaryWriter
import collections
import zx


class UnifiedSnapshot(zx.MachineSnapshot):
    pass


_V1_FORMAT = '1.45'
_V2_FORMAT = '2.x'
_V3_FORMAT = '3.x'

def _get_format_version(fields):
    if 'ticks_count_low' in fields:
        return _V3_FORMAT

    if 'pc2' in fields:
        return _V2_FORMAT

    return _V1_FORMAT


class Z80Snapshot(zx.MachineSnapshot):
    _MEMORY_PAGE_ADDRS = {4: 0x8000, 5: 0xc000, 8: 0x4000}

    def get_unified_snapshot(self):
        # Bit 7 of the stored R value is not significant and
        # shall be taken from bit 0 of flags1.
        flags1 = self['flags1']
        r = (self['r'] & 0x7f) | ((flags1 & 0x1) << 7)

        flags2 = self['flags2']
        int_mode = flags2 & 0x3
        if int_mode not in [0, 1, 2]:
            raise zx.Error('Invalid interrupt mode %d.' % int_mode)

        format_version = _get_format_version(self._fields)

        pc = self['pc'] if format_version == _V1_FORMAT else self['pc2']

        processor_fields = {
            'bc': self['bc'],
            'de': self['de'],
            'hl': self['hl'],
            'af': zx.make16(hi=self['a'], lo=self['f']),
            'ix': self['ix'],
            'iy': self['iy'],
            'alt_bc': self['alt_bc'],
            'alt_de': self['alt_de'],
            'alt_hl': self['alt_hl'],
            'alt_af': zx.make16(hi=self['alt_a'], lo=self['alt_f']),
            'pc': pc,
            'sp': self['sp'],
            'ir': zx.make16(hi=self['i'], lo=r),
            'iff1': 0 if self['iff1'] == 0 else 1,
            'iff2': 0 if self['iff2'] == 0 else 1,
            'int_mode': int_mode }

        ticks_per_frame = 69888  # TODO
        quarter_tstates = ticks_per_frame // 4

        fields = {
            'processor_snapshot': zx.ProcessorSnapshot(processor_fields),
            'border_color': (flags1 >> 1) & 0x7,

            # Give the snapshot a chance to execute at least one
            # instruction without firing up an interrupt.
            'ticks_since_int': ticks_per_frame - 23,
        }

        if 'ticks_count_high' in self:
            ticks_high = self['ticks_count_high']
            ticks_low = self['ticks_count_low']
            ticks_since_int = (((ticks_high + 1) % 4 + 1) * quarter_tstates -
                                   (ticks_low + 1))
            fields['ticks_since_int'] = ticks_since_int

        # Determine machine kind.
        # TODO: Not used currently?
        if format_version == _V1_FORMAT:
            machine_kind = 'ZX Spectrum 48K'
        else:
            hardware_mode = self['hardware_mode']
            flags3 = self['flags3']
            flags3_bit7 = (flags3 & 0x80) >> 7
            if hardware_mode == 0 and not flags3_bit7:
                machine_kind = 'ZX Spectrum 48K'
            else:
                raise zx.Error('Unsupported type of emulated machine.',
                               id='unsupported_machine')

        # Handle memory blocks.
        memory_blocks = fields.setdefault('memory_blocks', [])
        if 'memory_snapshot' in self:
            memory_blocks.append((0x4000, self['memory_snapshot']))
        else:
            assert machine_kind == 'ZX Spectrum 48K', machine_kind  # TODO
            for block in self['memory_blocks']:
                page_no = block['page_no']
                image = block['image']
                memory_blocks.append((self._MEMORY_PAGE_ADDRS[page_no], image))

        return UnifiedSnapshot(Z80SnapshotsFormat, fields)


class Z80SnapshotsFormat(zx.SnapshotsFormat):
    _NAME = 'Z80'

    _PRIMARY_HEADER = [
        'B:a', 'B:f', '<H:bc', '<H:hl', '<H:pc', '<H:sp', 'B:i', 'B:r',
        'B:flags1', '<H:de', '<H:alt_bc', '<H:alt_de', '<H:alt_hl',
        'B:alt_a', 'B:alt_f', '<H:iy', '<H:ix', 'B:iff1', 'B:iff2', 'B:flags2']

    _EXTRA_HEADERS_SIZE_FIELD = [
        '<H:extra_headers_size']

    _EXTRA_HEADER = [
        '<H:pc2', 'B:hardware_mode', 'B:misc1', 'B:misc2', 'B:flags3',
        'B:port_fffd_value', '16B:sound_chip_registers']

    _EXTRA_HEADER2 = [
        '<H:ticks_count_low', 'B:ticks_count_high', 'B:spectator_flag',
        'B:mgt_rom_paged', 'B:multiface_rom_paged',
        'B:memory_at_0000_1fff_is_ram', 'B:memory_at_2000_3fff_is_ram',
        '10B:keyboard_mappings', '10B:keyboard_mappings_keys',
        'B:mgt_type', 'B:disciple_inhibit_button_status',
        'B:disciple_inhibit_flag']

    _EXTRA_HEADER2b = [
        'B:last_write_to_port_1ffd']

    _MEMORY_BLOCK_HEADER = [
        '<H:compressed_size', 'B:page_no']

    _RAW_MEMORY_BLOCK_SIZE_VALUE = 0xffff

    def _uncompress(self, compressed_image, uncompressed_size):
        MARKER = 0xed
        input = list(compressed_image)
        output = []
        while input:
            if len(input) >= 4 and input[0] == MARKER and input[1] == MARKER:
                count = input[2]
                filler = input[3]
                output.extend([filler] * count)
                del input[0:4]
            else:
                output.append(input.pop(0))

        if len(output) != uncompressed_size:
            raise zx.Error('Corrupted compressed memory block.')

        return bytes(output)

    def _parse_memory_block(self, parser):
        BLOCK_SIZE = 16 * 1024
        fields = parser.parse(self._MEMORY_BLOCK_HEADER)
        compressed_size = fields['compressed_size']
        if compressed_size == self._RAW_MEMORY_BLOCK_SIZE_VALUE:
            raw_image = parser.extract_block(BLOCK_SIZE)
        else:
            compressed_image = parser.extract_block(compressed_size)
            raw_image = self._uncompress(compressed_image, BLOCK_SIZE)
        return collections.OrderedDict(page_no=fields['page_no'],
                                       image=raw_image)

    def parse(self, image):
        # Parse headers.
        parser = BinaryParser(image)
        fields = collections.OrderedDict(id='z80_snapshot')
        fields.update(parser.parse(self._PRIMARY_HEADER))

        if fields['pc'] == 0:
            fields.update(parser.parse(self._EXTRA_HEADERS_SIZE_FIELD))

        if 'extra_headers_size' in fields:
            extra_headers = parser.extract_block(fields['extra_headers_size'])
            extra_parser = BinaryParser(extra_headers)
            fields.update(extra_parser.parse(self._EXTRA_HEADER))

            if extra_parser:
                fields.update(extra_parser.parse(self._EXTRA_HEADER2))

            if extra_parser:
                fields.update(extra_parser.parse(self._EXTRA_HEADER2b))

            if extra_parser:
                raise zx.Error('Too many headers in Z80 snapshot.',
                               id='too_many_z80_snapshot_headers')

        # Parse memory snapshot.
        if _get_format_version(fields) == _V1_FORMAT:
            compressed = (fields['flags1'] & 0x20) != 0
            if not compressed:
                if parser.get_rest_size() != 48 * 1024:
                    raise zx.Error('The snapshot is too large.')
                image = parser.extract_rest()
            else:
                image = self._uncompress(parser.extract_rest(),
                                         48 * 1024 + 4)

                # Remove the terminator.
                if image[48 * 1024:] != b'\x00\xed\xed\x00':
                    raise zx.Error('The compressed memory block does not '
                                   'terminate properly.')
                image = image[:48 * 1024]

            fields['memory_snapshot'] = image
        else:
            memory_blocks = fields.setdefault('memory_blocks', [])
            while parser:
                block = self._parse_memory_block(parser)
                memory_blocks.append(block)

        return Z80Snapshot(Z80SnapshotsFormat, fields)

    # TODO: Rework to generate an internal representation of the
    #       format and then generate its binary version.
    def make(self, state):
        # TODO: The z80 format cannot represent processor states in
        #       the middle of IX- and IY-prefixed instructions, so
        #       such situations need some additional processing.
        # TODO: Check for similar problems with other state attributes.
        assert state.get_iregp_kind() == 'hl'

        flags1 = 0
        flags2 = 0

        # Bit 7 of the stored R value is not signigicant and
        # shall be taken from bit 0 of flags1.
        r = state.get_r_reg()
        flags1 |= (r & 0x80) >> 7
        r &= 0x7f

        border_color = state.get_border_color()
        assert 0 <= border_color <= 7
        flags1 |= border_color << 1

        int_mode = state.get_int_mode()
        assert int_mode in [0, 1, 2]  # TODO
        flags2 |= int_mode

        # Write v1 header.
        # TODO: Support other versions.
        writer = BinaryWriter()
        writer.write(
            self._PRIMARY_HEADER,
            a=state.get_a(), f=state.get_f(), bc=state.get_bc(), hl=state.get_hl(),
            pc=state.get_pc(), sp=state.get_sp(), i=state.get_i(), r=r,
            flags1=flags1, de=state.get_de(),
            alt_bc=state.get_alt_bc(), alt_de=state.get_alt_de(),
            alt_hl=state.get_alt_hl(),
            alt_a=state.get_alt_a(), alt_f=state.get_alt_f(),
            iy=state.get_iy(), ix=state.get_ix(),
            iff1=state.get_iff1(), iff2=state.get_iff2(), flags2=flags2)

        # Write memory snapshot.
        writer.write_block(state.get_memory_block(0x4000, size=48 * 1024))

        return writer.get_image()

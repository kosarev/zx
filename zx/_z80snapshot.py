# -*- coding: utf-8 -*-


import struct, zx


MASK16 = 0xffff


def make16(hi, lo):
    return ((hi << 8) | lo) & MASK16


class BinaryParser(object):
    def __init__(self, image):
        self.image = image
        self.pos = 0

    def is_eof(self):
        return self.pos >= len(self.image)

    def parse_field(self, field_format, field_id):
        field_size = struct.calcsize(field_format)
        field_image = self.image[self.pos:self.pos + field_size]
        if len(field_image) < field_size:
            raise zx.Error('Binary image is too short.')

        field_value = struct.unpack(field_format, field_image)
        if len(field_value) == 1:
            field_value = field_value[0]
        # print(field_size, self.pos, field_id, '=', field_value)
        self.pos += field_size
        return field_value

    def parse(self, format):
        res = dict()
        for field_id, field_format in format:
            res[field_id] = self.parse_field(field_format, field_id)
        return res

    def extract_block(self, size):
        begin = self.pos
        self.pos += size
        return self.image[begin:self.pos]


def uncompress_data(compressed_image, size):
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

    # print(res)
    assert len(output) == size, len(output)  # TODO
    return output


def parse_memory_page(parser):
    header = parser.parse([('compressed_length', '<H'),
                           ('page_no', 'B')])

    compressed_length = header['compressed_length']
    if compressed_length == 0xffff:
        assert 0  # TODO: Support uncompressed blocks.
    else:
        compressed_image = parser.extract_block(compressed_length)
        uncompressed_image = uncompress_data(compressed_image, size=0x4000)

    return {'page_no': header['page_no'], 'image': bytes(uncompressed_image)}


def parse_z80_snapshot(image):
    # Parse headers.
    parser = BinaryParser(image)
    version = 1
    v1_header = parser.parse([
        ('a', 'B'), ('f', 'B'), ('bc', '<H'), ('hl', '<H'), ('pc', '<H'),
        ('sp', '<H'), ('i', 'B'), ('r', 'B'), ('flags1', 'B'), ('de', '<H'),
        ('alt_bc', '<H'), ('alt_de', '<H'), ('alt_hl', '<H'), ('alt_a', 'B'),
        ('alt_f', 'B'), ('iy', '<H'), ('ix', '<H'), ('iff1', 'B'),
        ('iff2', 'B'), ('flags2', 'B')])

    additional_header_length = 0
    if v1_header['pc'] == 0:
        version = 2
        additional_header_length = parser.parse_field(
            '<H', 'additional_header_length')
        if additional_header_length < 23:
            raise zx.Error('Additional header is too short: %d bytes.' %
                               additional_header_length)

        v2_header = parser.parse([
            ('pc', '<H'), ('hardware_mode', 'B'), ('misc1', 'B'),
            ('misc2', 'B'), ('flags3', 'B'), ('port_fffd_value', 'B'),
            ('sound_chip_registers', '16B')])

    if additional_header_length > 23:
        assert 0  # TODO: Support v3 headers.

    # Bit 7 of the stored R value is not signigicant and shall be taken from
    # bit 0 of flags1.
    flags1 = v1_header['flags1']
    r = (v1_header['r'] & 0x7f) | ((flags1 & 0x1) << 7)

    flags2 = v1_header['flags2']
    int_mode = flags2 & 0x3
    if int_mode not in [0, 1, 2]:
        raise zx.Error('Invalid interrupt mode %d.' % int_mode)

    processor_state = {
        'id': 'processor_state',
        'bc': v1_header['bc'],
        'de': v1_header['de'],
        'hl': v1_header['hl'],
        'af': make16(v1_header['a'], v1_header['f']),
        'ix': v1_header['ix'],
        'iy': v1_header['iy'],
        'alt_bc': v1_header['alt_bc'],
        'alt_de': v1_header['alt_de'],
        'alt_hl': v1_header['alt_hl'],
        'alt_af': make16(v1_header['alt_a'], v1_header['alt_f']),
        'pc': v1_header['pc'] if version < 2 else v2_header['pc'],
        'sp': v1_header['sp'],
        'ir': make16(v1_header['i'], r),
        'iff1': 0 if v1_header['iff1'] == 0 else 1,
        'iff2': 0 if v1_header['iff2'] == 0 else 1,
        'int_mode': int_mode }

    snapshot = {
        'id': 'snapshot',
        'processor_state': processor_state,
        'border_color': (flags1 >> 1) & 0x7 }

    # Determine machine kind.
    machine_kind = None
    if version == 1:
        machine_kind = 'ZX Spectrum 48K'
    elif version >= 2:
        hardware_mode = v2_header['hardware_mode']
        flags3 = v2_header['flags3']
        flags3_bit7 = (flags3 & 0x80) >> 7
        if hardware_mode == 0 and not flags3_bit7:
            machine_kind = 'ZX Spectrum 48K'

    if machine_kind:
        snapshot['machine_kind'] = machine_kind

    # Parse memory blocks.
    if version == 1:
        compressed = (flags1 & 0x20) != 0
        assert 0  # TODO
    else:
        assert machine_kind == 'ZX Spectrum 48K'  # TODO

        page_addrs = {4: 0x8000, 5: 0xc000, 8: 0x4000}

        memory = []
        snapshot['memory'] = memory
        while not parser.is_eof():
            page = parse_memory_page(parser)
            page_no = page['page_no']
            page_addr = page_addrs[page_no]
            memory.append((page_addr, page['image']))

    # assert parser.is_eof()  # , len(parser.extract_rest())  # , parser.extract_rest()

    return snapshot

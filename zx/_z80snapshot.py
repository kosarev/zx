# -*- coding: utf-8 -*-


from ._binary import BinaryParser, BinaryWriter
import zx


MASK16 = 0xffff


class Z80SnapshotFile(zx.SnapshotFile):
    def __init__(self, image, snapshot):
        # TODO: Remove when the new approach to handling files is in place.
        self._image = image

        self._snapshot = snapshot

    def dump(self):
        print(self._image)


class Z80SnapshotsFormat(zx.SnapshotsFormat):
    def parse(self, image):
        snapshot = zx.parse_z80_snapshot(image)
        return Z80SnapshotFile(image, snapshot)


def make16(hi, lo):
    return ((hi << 8) | lo) & MASK16


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

    processor_snapshot = {
        'id': 'processor_snapshot',
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
        'processor_snapshot': processor_snapshot,
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
        assert machine_kind == 'ZX Spectrum 48K', machine_kind  # TODO

        page_addrs = {4: 0x8000, 5: 0xc000, 8: 0x4000}

        memory = []
        snapshot['memory'] = memory
        while not parser.is_eof():
            page = parse_memory_page(parser)
            page_no = page['page_no']
            page_addr = page_addrs[page_no]
            memory.append((page_addr, page['image']))

    return snapshot


# TODO: The processor state shall be part of the machine state.
# TODO: The memory image shall be part of the machine state.
# TODO: Rework to generate an internal representation of the
#       format and then generate its binary version.
def make_z80_snapshot(processor_state, machine_state, memory_image):
    writer = BinaryWriter()

    # TODO: The z80 format cannot represent processor states in
    #       the middle of IX- and IY-prefixed instructions, so
    #       such situations need some additional processing.
    # TODO: Check for similar problems with other state attributes.
    assert processor_state.get_index_rp_kind() == 'hl'

    flags1 = 0
    flags2 = 0

    # Bit 7 of the stored R value is not signigicant and shall be taken from
    # bit 0 of flags1.
    r = processor_state.get_r_reg()
    flags1 |= (r & 0x80) >> 7
    r &= 0x7f

    border_color = machine_state.get_border_color()
    assert 0 <= border_color <= 7
    flags1 |= border_color << 1

    int_mode = processor_state.get_int_mode()
    assert int_mode in [0, 1, 2]  # TODO
    flags2 |= int_mode

    # Write v1 header.
    # TODO: Support other versions.
    writer.write_fields([
        (processor_state.get_a(), 'B'),
        (processor_state.get_f(), 'B'),
        (processor_state.get_bc(), '<H'),
        (processor_state.get_hl(), '<H'),
        (processor_state.get_pc(), '<H'),
        (processor_state.get_sp(), '<H'),
        (processor_state.get_i(), 'B'),
        (r, 'B'),
        (flags1, 'B'),
        (processor_state.get_de(), '<H'),
        (processor_state.get_alt_bc(), '<H'),
        (processor_state.get_alt_de(), '<H'),
        (processor_state.get_alt_hl(), '<H'),
        (processor_state.get_alt_a(), 'B'),
        (processor_state.get_alt_f(), 'B'),
        (processor_state.get_iy(), '<H'),
        (processor_state.get_ix(), '<H'),
        (processor_state.get_iff1(), 'B'),
        (processor_state.get_iff2(), 'B'),
        (flags2, 'B')
    ])

    # Write memory snapshot.
    writer.write(memory_image)

    return writer.get_image()

# -*- coding: utf-8 -*-


import struct


class ZXError(Exception):
    """Basic exception for the whole ZX module."""


class BinaryParser(object):
    def __init__(self, image):
        self.image = image
        self.pos = 0

    def parse_field(self, field_format, field_id):
        field_size = struct.calcsize(field_format)
        field_image = self.image[self.pos:self.pos + field_size]
        if len(field_image) < field_size:
            raise ZXError('Binary image is too short.')

        field_value = struct.unpack(field_format, field_image)
        if len(field_value) == 1:
            field_value = field_value[0]
        print(field_size, self.pos, field_id, '=', field_value)
        self.pos += field_size
        return field_value

    def parse(self, format):
        res = dict()
        for field_id, field_format in format:
            res[field_id] = self.parse_field(field_format, field_id)
        return res


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

    snapshot = dict()

    return snapshot

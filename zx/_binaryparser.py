# -*- coding: utf-8 -*-


import struct, zx


class BinaryParser(object):
    def __init__(self, image):
        self.image = image
        self.pos = 0

    def is_eof(self):
        return self.pos >= len(self.image)

    def extract_block(self, size):
        begin = self.pos
        self.pos += size
        return self.image[begin:self.pos]

    def extract_rest(self):
        return self.extract_block(len(self.image) - self.pos)

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

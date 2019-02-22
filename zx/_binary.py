# -*- coding: utf-8 -*-


import struct, zx


class BinaryParser(object):
    def __init__(self, image):
        self.image = image
        self.pos = 0

    def get_rest_size(self):
        return len(self.image) - self.pos

    def is_eof(self):
        return self.get_rest_size() == 0

    def __bool__(self):
        return not self.is_eof()

    def extract_block(self, size):
        if size > self.get_rest_size():
            raise zx.Error('Binary image is too short.')

        begin = self.pos
        self.pos += size
        return self.image[begin:self.pos]

    def extract_rest(self):
        return self.extract_block(len(self.image) - self.pos)

    def parse_field(self, format, id):
        size = struct.calcsize(format)
        value = struct.unpack(format, self.extract_block(size))
        if len(value) == 1:
            value = value[0]
        return value

    def parse(self, format):
        res = dict()
        for field in format:
            if isinstance(field, str):
                field_format, field_id = field.split(':', maxsplit=1)
            else:
                # TODO: Remove this branch once all tuple formats
                # are eliminated.
                field_id, field_format = field
            res[field_id] = self.parse_field(field_format, field_id)
        return res


class BinaryWriter(object):
    def __init__(self):
        self._chunks = []

    def write_block(self, block):
        self._chunks.append(block)

    def write(self, format, **values):
        for field in format:
            field_format, field_id = field.split(':', maxsplit=1)
            self.write_block(struct.pack(field_format, values[field_id]))

    def get_image(self):
        return b''.join(self._chunks)

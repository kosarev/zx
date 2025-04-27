# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import typing
import struct
from ._error import Error


Bytes = bytes | bytearray | memoryview


class BinaryParser(object):
    image: Bytes

    def __init__(self, image: Bytes):
        self.image = image
        self.pos = 0

    def get_remaining_size(self) -> int:
        return len(self.image) - self.pos

    def is_eof(self) -> bool:
        return self.get_remaining_size() == 0

    def __bool__(self) -> bool:
        return not self.is_eof()

    def read_bytes(self, size: int) -> Bytes:
        if size > self.get_remaining_size():
            raise Error('Binary image is too short.',
                        id='binary_image_too_short')

        begin = self.pos
        self.pos += size
        return self.image[begin:self.pos]

    def extract_rest(self) -> Bytes:
        return self.read_bytes(len(self.image) - self.pos)

    def parse_field(self, format: str) -> int | str | bytes | tuple[int | str]:
        size = struct.calcsize(format)
        value = struct.unpack(format, self.read_bytes(size))
        if len(value) == 1:
            value = value[0]
        return value

    def parse(self, format: list[str] | list[tuple[str, str]]) -> (
            dict[str, typing.Any]):
        res = dict()
        for field in format:
            if isinstance(field, str):
                field_format, field_id = field.split(':', maxsplit=1)
            else:
                # TODO: Remove this branch once all tuple formats
                # are eliminated.
                field_id, field_format = field
            res[field_id] = self.parse_field(field_format)
        return res


class BinaryWriter(object):
    _chunks: list[Bytes]

    def __init__(self) -> None:
        self._chunks = []

    def write_block(self, block: Bytes) -> None:
        self._chunks.append(block)

    def write(self, format: list[str], **values: typing.Any) -> None:
        for field in format:
            field_format, field_id = field.split(':', maxsplit=1)
            self.write_block(struct.pack(field_format, values[field_id]))

    def get_image(self) -> Bytes:
        return b''.join(self._chunks)

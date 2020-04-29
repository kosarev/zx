# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


from ._binary import BinaryParser
from ._tape import get_block_pulses
import zx


class TAPFile(zx.SoundFile):
    _TICKS_FREQ = 3500000

    def __init__(self, fields):
        zx.SoundFile.__init__(self, TAPFileFormat, fields)

    def get_pulses(self):
        level = False
        blocks = self['blocks']
        for data in blocks:
            # The block itself.
            for pulse in get_block_pulses(data):
                yield (level, pulse)
                level = not level

            # Pause. Skip, if it's the last block.
            if data is not blocks[-1]:
                yield (level, self._TICKS_FREQ)  # 1s.


class TAPFileFormat(zx.SoundFileFormat):
    _NAME = 'TAP'

    def _parse_block(self, parser):
        size = parser.parse_field('<H', 'block_size')
        return parser.extract_block(size)

    def parse(self, image):
        parser = BinaryParser(image)

        # Parse blocks.
        blocks = []
        while not parser.is_eof():
            blocks.append(self._parse_block(parser))

        return TAPFile({'blocks': blocks})

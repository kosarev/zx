# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


from ._binary import BinaryParser
import zx


class TZXFile(zx.Data):
    def __init__(self, fields):
        self._fields = fields


class TZXFileFormat(zx.FileFormat):
    def _parse_standard_speed_data_block(self, parser):
        block = parser.parse([('pause_after_block_in_ms', '<H'),
                              ('data_size', '<H')])
        block.update({'id': '10 (Standard Speed Data Block)',
                      'data': parser.extract_block(block['data_size'])})
        return block

    _BLOCK_PARSERS = {
        0x10: _parse_standard_speed_data_block,
    }

    def _parse_block(self, parser):
        block_id = parser.parse_field('B', 'block_id')
        if block_id not in self._BLOCK_PARSERS:
            raise zx.Error('Unsupported TZX block id %x.' % block_id)

        return self._BLOCK_PARSERS[block_id](self, parser)

    def parse(self, image):
        parser = BinaryParser(image)

        # Parse header.
        header = parser.parse([('signature', '8s'),
                               ('major_revision', 'B'),
                               ('minor_revision', 'B')])
        tzx_signature = b'ZXTape!\x1a'
        if header['signature'] != tzx_signature:
            raise zx.Error('Bad TZX file signature %r; expected %r.' % (
                              header['signature'], tzx_signature))

        # Parse blocks.
        blocks = []
        while not parser.is_eof():
            blocks.append(self._parse_block(parser))

        return TZXFile({**header, 'blocks': blocks})

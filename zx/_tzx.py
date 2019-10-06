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


def get_standard_pilot_pulses(is_header):
    pulse = 2168
    duration = 8063 if is_header else 3223
    for _ in range(duration):
        yield pulse


def get_standard_sync_pulses():
    yield 667
    yield 735


def _get_data_bits(data):
    for byte in data:
        for i in range(8):
            yield (byte & (1 << (7 - i))) != 0


def get_standard_data_pulses(data):
    for bit in _get_data_bits(data):
        pulse = 1710 if bit else 855
        yield pulse
        yield pulse


class TZXFile(zx.SoundFile):
    _TICKS_FREQ = 3500000

    def __init__(self, fields):
        zx.SoundFile.__init__(self, TZXFileFormat, fields)

    def get_pulses(self):
        level = False
        for block in self['blocks']:
            if block['id'] == '10 (Standard Speed Data Block)':
                data = block['data']

                # Generate pilot tone.
                is_header = data[0] < 128
                for pulse in get_standard_pilot_pulses(is_header):
                    yield (level, pulse)
                    level = not level

                # Sync pulses.
                for pulse in get_standard_sync_pulses():
                    yield (level, pulse)
                    level = not level

                # Data.
                for pulse in get_standard_data_pulses(data):
                    yield (level, pulse)
                    level = not level

                # Pause.
                pause_duration = block['pause_after_block_in_ms']

                # Pause blocks of zero duration shall be ignored,
                # and then the output level remains the same.
                if pause_duration == 0:
                    continue

                # At the end of the non-zero-duration pause the
                # output level shall be low.
                if level:
                    # Give the high pulse 1ms of time and drop it.
                    yield (level, self._TICKS_FREQ / 1000)
                    pause_duration -= 1
                    level = not level

                assert not level
                if pause_duration:
                    yield (level, pause_duration * self._TICKS_FREQ / 1000)
            else:
                assert 0, block  # TODO


class TZXFileFormat(zx.SoundFileFormat):
    _NAME = 'TZX'

    def _parse_standard_speed_data_block(self, parser):
        block = parser.parse([('pause_after_block_in_ms', '<H'),
                              ('data_size', '<H')])
        block.update({'id': '10 (Standard Speed Data Block)',
                      'data': parser.extract_block(block['data_size'])})
        del block['data_size']
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

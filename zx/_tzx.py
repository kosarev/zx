# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from ._binary import BinaryParser
from ._data import SoundFile
from ._data import SoundFileFormat
from ._error import Error
from ._tape import (get_block_pulses, get_data_pulses, tag_last_pulse,
                    get_end_pulse)


class TZXFile(SoundFile):
    _TICKS_FREQ = 3500000

    def __init__(self, *, major_revision, minor_revision, blocks):
        SoundFile.__init__(self, TZXFileFormat,
                           major_revision=major_revision,
                           minor_revision=minor_revision,
                           blocks=blocks)

    def _generate_pulses(self):
        level = False
        for block in self.blocks:
            id = block['id']
            if id in ['0x10 (Standard Speed Data Block)',
                      '0x11 (Turbo Speed Data Block)',
                      '0x14 (Pure Data Block)']:
                # The block itself.
                data = block['data']
                if id == '0x10 (Standard Speed Data Block)':
                    pulses = get_block_pulses(data)
                elif id == '0x11 (Turbo Speed Data Block)':
                    pulses = get_block_pulses(
                        data=data,
                        pilot_pulse_len=block['pilot_pulse_len'],
                        first_sync_pulse_len=block['first_sync_pulse_len'],
                        second_sync_pulse_len=block['second_sync_pulse_len'],
                        zero_bit_pulse_len=block['zero_bit_pulse_len'],
                        one_bit_pulse_len=block['one_bit_pulse_len'],
                        pilot_tone_len=block['pilot_tone_len'])
                    # TODO: Should we generate the end pulse here?
                    #       end_pulse_len=...
                elif id == '0x14 (Pure Data Block)':
                    pulses = get_data_pulses(
                        data=data,
                        zero_bit_pulse_len=block['zero_bit_pulse_len'],
                        one_bit_pulse_len=block['one_bit_pulse_len'])
                else:
                    assert 0, id

                for pulse, ids in pulses:
                    yield level, pulse, ids
                    level = not level

                # Pause.
                pause_duration = block['pause_after_block_in_ms']

                # Pause blocks of zero duration shall be ignored,
                # and then the output level remains the same.
                if pause_duration == 0:
                    continue

                # At the end of the non-zero-duration pause the
                # output level shall be low.
                ''' TODO: Despite the specification, this cases
                          tape loading errors.
                if level:
                    # Give the high pulse 1ms of time and drop it.
                    yield level, self._TICKS_FREQ // 1000, ('PAUSE',)
                    pause_duration -= 1
                    level = not level

                assert not level
                '''

                if pause_duration:
                    yield (level, pause_duration * self._TICKS_FREQ // 1000,
                           ('PAUSE',))
            elif id == '0x30 (Text Description)':
                print(block['text'])
            elif id in ['0x32 (Archive Info)', '0x21 (Group Start)',
                        '0x22 (Group End)']:
                pass
            else:
                assert 0, block  # TODO

        # Some codes are sensitive to keeping the existing tape level
        # after the last block. For example, the Ms Pacman TZX at
        # https://www.worldofspectrum.org//pub/sinclair/games/m/Ms.Pac-Man.tzx.zip  # noqa
        # md5sum 67149beea737fb45998fba7472b3f449  Ms Pacman.tzx
        # requires ~15,000 more ticks at the same tape level.
        # It might make no difference for emulators, however it does
        # make a difference when loading WAV files on real machines.
        for pulse, ids in get_end_pulse(50000):
            yield level, pulse, ids

    def get_pulses(self):
        return tag_last_pulse(self._generate_pulses())


class TZXFileFormat(SoundFileFormat, name='TZX'):
    def _parse_standard_speed_data_block(self, parser):
        block = parser.parse([('pause_after_block_in_ms', '<H'),
                              ('data_size', '<H')])
        block.update({'id': '0x10 (Standard Speed Data Block)',
                      'data': parser.extract_block(block['data_size'])})
        del block['data_size']
        return block

    def _parse_turbo_speed_data_block(self, parser):
        block = parser.parse([('pilot_pulse_len', '<H'),
                              ('first_sync_pulse_len', '<H'),
                              ('second_sync_pulse_len', '<H'),
                              ('zero_bit_pulse_len', '<H'),
                              ('one_bit_pulse_len', '<H'),
                              ('pilot_tone_len', '<H'),
                              ('used_bits_in_last_byte', '<B'),
                              ('pause_after_block_in_ms', '<H'),
                              ('data_size_lo', '<H'),
                              ('data_size_hi', '<B')])
        data_size = (block.pop('data_size_hi') * 0x10000 +
                     block.pop('data_size_lo'))
        data_size_in_bits = data_size * 8 + block.pop('used_bits_in_last_byte')
        block.update({'id': '0x11 (Turbo Speed Data Block)',
                      'data_size_in_bits': data_size_in_bits,
                      'data': parser.extract_block(data_size)})
        return block

    def _parse_pure_data_block(self, parser):
        block = parser.parse([('zero_bit_pulse_len', '<H'),
                              ('one_bit_pulse_len', '<H'),
                              ('used_bits_in_last_byte', '<B'),
                              ('pause_after_block_in_ms', '<H'),
                              ('data_size_lo', '<H'),
                              ('data_size_hi', '<B')])
        data_size = (block.pop('data_size_hi') * 0x10000 +
                     block.pop('data_size_lo'))
        data_size_in_bits = data_size * 8 + block.pop('used_bits_in_last_byte')
        block.update({'id': '0x14 (Pure Data Block)',
                      'data_size_in_bits': data_size_in_bits,
                      'data': parser.extract_block(data_size)})
        return block

    def _parse_group_start(self, parser):
        length = parser.parse_field('B', 'name_length')
        name = parser.extract_block(length)
        # print('Group start: %r.' % name)
        return {'id': '0x21 (Group Start)',
                'name': name}

    def _parse_group_end(self, parser):
        # TODO: Check for a matching group start?
        # print('Group end.')
        return {'id': '0x22 (Group End)'}

    def _parse_text_description(self, parser):
        size = parser.parse_field('B', 'text_size')
        text = parser.extract_block(size)
        return {'id': '0x30 (Text Description)',
                'text': text}

    _ARCHIVE_INFO_STRING_IDS = {
        0x00: 'Full title',
        0x01: 'Software house/publisher',
        0x02: 'Author(s)',
        0x03: 'Year of publication',
        0x04: 'Language',
        0x05: 'Game/utility type',
        0x06: 'Price',
        0x07: 'Protection scheme/loader',
        0x08: 'Origin',
        0xFF: 'Comment(s)',
    }

    def _parse_archive_info(self, parser):
        block_size = parser.parse_field('<H', 'block_size')
        num_of_strings = parser.parse_field('B', 'num_of_strings')
        for _ in range(num_of_strings):
            id = parser.parse_field('B', 'id')
            length = parser.parse_field('B', 'length')
            body = parser.extract_block(length)

            if id not in self._ARCHIVE_INFO_STRING_IDS:
                raise Error('Unknown TZX archive info string id 0x%02x.' % id)

            # print('%s: %s' % (self._ARCHIVE_INFO_STRING_IDS[id], body))
        # TODO: Encode all the details.
        return {'id': '0x32 (Archive Info)'}

    _BLOCK_PARSERS = {
        0x10: _parse_standard_speed_data_block,
        0x11: _parse_turbo_speed_data_block,
        0x14: _parse_pure_data_block,
        0x21: _parse_group_start,
        0x22: _parse_group_end,
        0x30: _parse_text_description,
        0x32: _parse_archive_info,
    }

    def _parse_block(self, parser):
        block_id = parser.parse_field('B', 'block_id')
        if block_id not in self._BLOCK_PARSERS:
            raise Error('Unsupported TZX block id 0x%x.' % block_id)

        return self._BLOCK_PARSERS[block_id](self, parser)

    def parse(self, filename, image):
        parser = BinaryParser(image)

        signature = parser.parse_field('8s', 'signature')
        TZX_SIGNATURE = b'ZXTape!\x1a'
        if signature != TZX_SIGNATURE:
            raise Error('Bad TZX file signature %r; expected %r.' % (
                        signature, TZX_SIGNATURE))

        # Parse header.
        header = parser.parse([('major_revision', 'B'),
                               ('minor_revision', 'B')])

        # Parse blocks.
        blocks = []
        while not parser.is_eof():
            blocks.append(self._parse_block(parser))

        return TZXFile(**header, blocks=blocks)

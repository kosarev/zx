# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import typing
from ._binary import Bytes, BinaryParser
from ._data import SoundFile
from ._error import Error
from ._tape import (get_block_pulses, get_data_pulses, tag_last_pulse,
                    get_end_pulse)


class TZXFile(SoundFile, format_name='TZX'):
    _TICKS_FREQ = 3500000

    blocks: list[dict[str, typing.Any]]

    def __init__(self, *, major_revision: int, minor_revision: int,
                 blocks: list[dict[str, typing.Any]]) -> None:
        SoundFile.__init__(self,
                           major_revision=major_revision,
                           minor_revision=minor_revision,
                           blocks=blocks)

    def _generate_pulses(self) -> (
            typing.Iterable[tuple[bool, int, tuple[str, ...]]]):
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

    def get_pulses(self) -> typing.Iterable[tuple[bool, int, tuple[str, ...]]]:
        return tag_last_pulse(self._generate_pulses())

    @classmethod
    def _parse_standard_speed_data_block(
            cls, parser: BinaryParser) -> dict[str, typing.Any]:
        block = parser.parse([('pause_after_block_in_ms', '<H'),
                              ('data_size', '<H')])
        block.update({'id': '0x10 (Standard Speed Data Block)',
                      'data': parser.extract_block(block['data_size'])})
        del block['data_size']
        return block

    @classmethod
    def _parse_turbo_speed_data_block(
            cls, parser: BinaryParser) -> dict[str, typing.Any]:
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

    @classmethod
    def _parse_pure_data_block(
            cls, parser: BinaryParser) -> dict[str, typing.Any]:
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

    @classmethod
    def _parse_group_start(
            cls, parser: BinaryParser) -> dict[str, typing.Any]:
        length = parser.parse_field('B', 'name_length')
        assert isinstance(length, int)
        name = parser.extract_block(length)
        # print('Group start: %r.' % name)
        return {'id': '0x21 (Group Start)',
                'name': name}

    @classmethod
    def _parse_group_end(
            cls, parser: BinaryParser) -> dict[str, typing.Any]:
        # TODO: Check for a matching group start?
        # print('Group end.')
        return {'id': '0x22 (Group End)'}

    @classmethod
    def _parse_text_description(
            cls, parser: BinaryParser) -> dict[str, typing.Any]:
        size = parser.parse_field('B', 'text_size')
        assert isinstance(size, int)
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

    @classmethod
    def _parse_archive_info(
            cls, parser: BinaryParser) -> dict[str, typing.Any]:
        block_size = parser.parse_field('<H', 'block_size')
        num_of_strings = parser.parse_field('B', 'num_of_strings')
        assert isinstance(num_of_strings, int)
        for _ in range(num_of_strings):
            id = parser.parse_field('B', 'id')
            assert isinstance(id, int)
            length = parser.parse_field('B', 'length')
            assert isinstance(length, int)
            body = parser.extract_block(length)

            if id not in cls._ARCHIVE_INFO_STRING_IDS:
                raise Error('Unknown TZX archive info string id 0x%02x.' % id)

            # print('%s: %s' % (cls._ARCHIVE_INFO_STRING_IDS[id], body))
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

    @classmethod
    def _parse_block(cls, parser: BinaryParser) -> dict[str, typing.Any]:
        block_id = parser.parse_field('B', 'block_id')
        assert isinstance(block_id, int)
        if block_id not in cls._BLOCK_PARSERS:
            raise Error('Unsupported TZX block id 0x%x.' % block_id)

        res = cls._BLOCK_PARSERS[block_id].__get__(None, cls)(parser)
        assert isinstance(res, dict)
        return res

    @classmethod
    def parse(cls, filename: str, image: Bytes) -> 'TZXFile':
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
            blocks.append(cls._parse_block(parser))

        return TZXFile(**header, blocks=blocks)

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from __future__ import annotations

import typing

from ._binary import BinaryParser
from ._binary import Bytes
from ._data import ByteData
from ._data import DataRecord
from ._data import HexData
from ._data import SoundFile
from ._error import Error
from ._tape import get_block_pulses
from ._tape import get_data_pulses
from ._tape import get_end_pulse
from ._tape import tag_last_pulse


class TZXBlock(DataRecord, format_name=None):
    pass


class TZXStandardSpeedDataBlock(TZXBlock, format_name=None):
    pause_after_block_in_ms: int
    data: ByteData

    def __init__(self, *, pause_after_block_in_ms: int,
                 data: Bytes | ByteData) -> None:
        super().__init__(pause_after_block_in_ms=pause_after_block_in_ms,
                         data=HexData.wrap(data))


class TZXTurboSpeedDataBlock(TZXBlock, format_name=None):
    pilot_pulse_len: int
    first_sync_pulse_len: int
    second_sync_pulse_len: int
    zero_bit_pulse_len: int
    one_bit_pulse_len: int
    pilot_tone_len: int
    data_size_in_bits: int
    pause_after_block_in_ms: int
    data: ByteData

    def __init__(self, *, pilot_pulse_len: int, first_sync_pulse_len: int,
                 second_sync_pulse_len: int, zero_bit_pulse_len: int,
                 one_bit_pulse_len: int, pilot_tone_len: int,
                 data_size_in_bits: int, pause_after_block_in_ms: int,
                 data: Bytes | ByteData) -> None:
        super().__init__(
            pilot_pulse_len=pilot_pulse_len,
            first_sync_pulse_len=first_sync_pulse_len,
            second_sync_pulse_len=second_sync_pulse_len,
            zero_bit_pulse_len=zero_bit_pulse_len,
            one_bit_pulse_len=one_bit_pulse_len,
            pilot_tone_len=pilot_tone_len,
            data_size_in_bits=data_size_in_bits,
            pause_after_block_in_ms=pause_after_block_in_ms,
            data=HexData.wrap(data))


class TZXPureDataBlock(TZXBlock, format_name=None):
    zero_bit_pulse_len: int
    one_bit_pulse_len: int
    data_size_in_bits: int
    pause_after_block_in_ms: int
    data: ByteData

    def __init__(self, *, zero_bit_pulse_len: int, one_bit_pulse_len: int,
                 data_size_in_bits: int, pause_after_block_in_ms: int,
                 data: Bytes | ByteData) -> None:
        super().__init__(
            zero_bit_pulse_len=zero_bit_pulse_len,
            one_bit_pulse_len=one_bit_pulse_len,
            data_size_in_bits=data_size_in_bits,
            pause_after_block_in_ms=pause_after_block_in_ms,
            data=HexData.wrap(data))


class TZXGroupStart(TZXBlock, format_name=None):
    name: ByteData

    def __init__(self, *, name: Bytes | ByteData) -> None:
        super().__init__(name=HexData.wrap(name))


class TZXGroupEnd(TZXBlock, format_name=None):
    pass


class TZXTextDescription(TZXBlock, format_name=None):
    text: ByteData

    def __init__(self, *, text: Bytes | ByteData) -> None:
        super().__init__(text=HexData.wrap(text))


class TZXArchiveInfo(TZXBlock, format_name=None):
    pass


class TZXFile(SoundFile, format_name='TZX'):
    _TICKS_FREQ = 3500000

    blocks: list[TZXBlock]

    def __init__(self, *, major_revision: int, minor_revision: int,
                 blocks: list[TZXBlock]) -> None:
        SoundFile.__init__(self,
                           major_revision=major_revision,
                           minor_revision=minor_revision,
                           blocks=blocks)

    def _generate_pulses(self) -> (
            typing.Iterable[tuple[bool, int, tuple[str, ...]]]):
        level = False
        for block in self.blocks:
            if isinstance(block, (TZXStandardSpeedDataBlock,
                                  TZXTurboSpeedDataBlock,
                                  TZXPureDataBlock)):
                if isinstance(block, TZXStandardSpeedDataBlock):
                    pulses = get_block_pulses(block.data.data)
                elif isinstance(block, TZXTurboSpeedDataBlock):
                    pulses = get_block_pulses(
                        data=block.data.data,
                        pilot_pulse_len=block.pilot_pulse_len,
                        first_sync_pulse_len=block.first_sync_pulse_len,
                        second_sync_pulse_len=block.second_sync_pulse_len,
                        zero_bit_pulse_len=block.zero_bit_pulse_len,
                        one_bit_pulse_len=block.one_bit_pulse_len,
                        pilot_tone_len=block.pilot_tone_len)
                    # TODO: Should we generate the end pulse here?
                    #       end_pulse_len=...
                else:
                    pulses = get_data_pulses(
                        data=block.data.data,
                        zero_bit_pulse_len=block.zero_bit_pulse_len,
                        one_bit_pulse_len=block.one_bit_pulse_len)

                for pulse, ids in pulses:
                    yield level, pulse, ids
                    level = not level

                # Pause.
                pause_duration = block.pause_after_block_in_ms

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
            elif isinstance(block, TZXTextDescription):
                print(block.text.data)
            elif isinstance(block, (TZXArchiveInfo, TZXGroupStart,
                                    TZXGroupEnd)):
                pass
            else:
                assert 0, block  # TODO

        # Some codes are sensitive to keeping the existing tape level
        # after the last block. For example, the Ms Pacman TZX at
        # https://www.worldofspectrum.org//pub/sinclair/games/m/Ms.Pac-Man.tzx.zip  # noqa: E501
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
            cls, parser: BinaryParser) -> TZXStandardSpeedDataBlock:
        pause_after_block_in_ms = parser.parse_field('<H')
        assert isinstance(pause_after_block_in_ms, int)
        data_size = parser.parse_field('<H')
        assert isinstance(data_size, int)
        return TZXStandardSpeedDataBlock(
            pause_after_block_in_ms=pause_after_block_in_ms,
            data=parser.read_bytes(data_size))

    @classmethod
    def _parse_turbo_speed_data_block(
            cls, parser: BinaryParser) -> TZXTurboSpeedDataBlock:
        fields = parser.parse([('pilot_pulse_len', '<H'),
                               ('first_sync_pulse_len', '<H'),
                               ('second_sync_pulse_len', '<H'),
                               ('zero_bit_pulse_len', '<H'),
                               ('one_bit_pulse_len', '<H'),
                               ('pilot_tone_len', '<H'),
                               ('used_bits_in_last_byte', '<B'),
                               ('pause_after_block_in_ms', '<H'),
                               ('data_size_lo', '<H'),
                               ('data_size_hi', '<B')])
        data_size = (fields.pop('data_size_hi') * 0x10000 +
                     fields.pop('data_size_lo'))
        data_size_in_bits = (data_size * 8 +
                             fields.pop('used_bits_in_last_byte'))
        return TZXTurboSpeedDataBlock(
            **fields,
            data_size_in_bits=data_size_in_bits,
            data=parser.read_bytes(data_size))

    @classmethod
    def _parse_pure_data_block(
            cls, parser: BinaryParser) -> TZXPureDataBlock:
        fields = parser.parse([('zero_bit_pulse_len', '<H'),
                               ('one_bit_pulse_len', '<H'),
                               ('used_bits_in_last_byte', '<B'),
                               ('pause_after_block_in_ms', '<H'),
                               ('data_size_lo', '<H'),
                               ('data_size_hi', '<B')])
        data_size = (fields.pop('data_size_hi') * 0x10000 +
                     fields.pop('data_size_lo'))
        data_size_in_bits = (data_size * 8 +
                             fields.pop('used_bits_in_last_byte'))
        return TZXPureDataBlock(
            **fields,
            data_size_in_bits=data_size_in_bits,
            data=parser.read_bytes(data_size))

    @classmethod
    def _parse_group_start(cls, parser: BinaryParser) -> TZXGroupStart:
        length = parser.parse_field('B')
        assert isinstance(length, int)
        return TZXGroupStart(name=parser.read_bytes(length))

    @classmethod
    def _parse_group_end(cls, parser: BinaryParser) -> TZXGroupEnd:
        return TZXGroupEnd()

    @classmethod
    def _parse_text_description(
            cls, parser: BinaryParser) -> TZXTextDescription:
        size = parser.parse_field('B')
        assert isinstance(size, int)
        return TZXTextDescription(text=parser.read_bytes(size))

    _ARCHIVE_INFO_STRING_IDS: typing.ClassVar[dict[int, str]] = {
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
    def _parse_archive_info(cls, parser: BinaryParser) -> TZXArchiveInfo:
        parser.parse_field('<H')  # block_size
        num_strings = parser.parse_field('B')
        assert isinstance(num_strings, int)
        for _ in range(num_strings):
            id = parser.parse_field('B')
            assert isinstance(id, int)
            length = parser.parse_field('B')
            assert isinstance(length, int)
            parser.read_bytes(length)

            if id not in cls._ARCHIVE_INFO_STRING_IDS:
                raise Error(f'Unknown TZX archive info string id 0x{id:02x}.')

        # TODO: Encode all the details.
        return TZXArchiveInfo()

    _BLOCK_PARSERS: typing.ClassVar[
            dict[int, typing.Callable[..., TZXBlock]]] = {
        0x10: _parse_standard_speed_data_block,
        0x11: _parse_turbo_speed_data_block,
        0x14: _parse_pure_data_block,
        0x21: _parse_group_start,
        0x22: _parse_group_end,
        0x30: _parse_text_description,
        0x32: _parse_archive_info,
    }

    @classmethod
    def _parse_block(cls, parser: BinaryParser) -> TZXBlock:
        block_id = parser.parse_field('B')
        assert isinstance(block_id, int)
        if block_id not in cls._BLOCK_PARSERS:
            raise Error(f'Unsupported TZX block id 0x{block_id:x}.')

        result = cls._BLOCK_PARSERS[block_id].__get__(None, cls)(parser)
        assert isinstance(result, TZXBlock)
        return result

    @classmethod
    def decode(cls, filename: str, image: Bytes) -> TZXFile:
        parser = BinaryParser(image)

        signature = parser.parse_field('8s')
        TZX_SIGNATURE = b'ZXTape!\x1a'
        if signature != TZX_SIGNATURE:
            raise Error(
                f'Bad TZX file signature {signature!r}; '
                f'expected {TZX_SIGNATURE!r}.')

        # Parse header.
        header = parser.parse([('major_revision', 'B'),
                               ('minor_revision', 'B')])

        # Parse blocks.
        blocks = []
        while not parser.is_eof():
            blocks.append(cls._parse_block(parser))

        return TZXFile(**header, blocks=blocks)

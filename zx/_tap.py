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
from ._data import SoundFileFormat
from ._tape import get_block_pulses, tag_last_pulse, get_end_pulse


class TAPFile(SoundFile):
    _TICKS_FREQ = 3500000

    blocks: typing.Sequence[Bytes]

    def __init__(self, *, blocks: typing.Sequence[Bytes]) -> None:
        SoundFile.__init__(self, TAPFileFormat, blocks=blocks)

    # TODO: Produce a typing.Sequence instead of using generators,
    #       once we can represent pulses in a more compact manner.
    def _generate_pulses(self) -> (
            typing.Iterable[tuple[bool, int, tuple[str, ...]]]):
        level = False
        last_block = len(self.blocks) - 1
        for i, data in enumerate(self.blocks):
            # The block itself.
            for pulse, id in get_block_pulses(data):
                yield level, pulse, id
                level = not level

            # End pulse.
            for pulse, id in get_end_pulse():
                yield level, pulse, id
                level = not level

            # Pause. Skip, if it's the last block.
            if i != last_block:
                yield level, self._TICKS_FREQ, ('PAUSE',)  # 1s.

    def get_pulses(self) -> (
            typing.Iterable[tuple[bool, int, tuple[str, ...]]]):
        pulses: typing.Iterable[tuple[bool, int, tuple[str, ...]]] = (
            tag_last_pulse(self._generate_pulses()))
        return pulses


class TAPFileFormat(SoundFileFormat, name='TAP'):
    def _parse_block(self, parser: BinaryParser) -> Bytes:
        size = parser.parse_field('<H', 'block_size')
        assert isinstance(size, int)
        return parser.extract_block(size)

    def parse(self, filename: str, image: Bytes) -> TAPFile:
        parser = BinaryParser(image)

        # Parse blocks.
        blocks = []
        while not parser.is_eof():
            blocks.append(self._parse_block(parser))

        return TAPFile(blocks=blocks)

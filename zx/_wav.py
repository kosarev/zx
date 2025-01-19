# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


import wave
from ._data import SoundFileFormat
from ._error import Error


class WAVFileFormat(SoundFileFormat):
    _NAME = 'WAV'
    _TICKS_FREQ = 3500000

    def parse(self, filename, image):
        # TODO
        raise Error('Parsing of WAV files is not supported yet.')

    def save_from_pulses(self, filename, pulses):
        with wave.open(filename, 'wb') as f:
            f.setnchannels(1)
            f.setsampwidth(1)

            frame_rate = 44100
            f.setframerate(frame_rate)

            LOW = 0
            HIGH = 0xff
            for level, duration, tags in pulses:
                duration = int(duration * frame_rate / self._TICKS_FREQ)
                sample = HIGH if level else LOW
                frame = bytes([sample])
                f.writeframes(frame * duration)

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


import struct
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
            f.setsampwidth(2)

            frame_rate = 44100
            f.setframerate(frame_rate)

            amplitude = 32767
            for level, duration, tags in pulses:
                duration = int(duration * frame_rate / self._TICKS_FREQ)
                sample = -amplitude if level else amplitude
                frame = struct.pack('<h', sample)
                f.writeframes(frame * duration)

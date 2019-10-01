# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


import struct, wave
import zx


class WAVFileFormat(zx.SoundFileFormat):
    _name = 'WAV'

    def save_from_pulses(self, filename, pulses):
        with wave.open(filename, 'wb') as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(44100)
            amplitude = 32767
            for level, duration in pulses:
                sample = -amplitude if level else amplitude
                frame = struct.pack('<h', sample)
                f.writeframes(frame * duration)

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


#!/usr/bin/env python3

import io
import pytest
import wave
import zx


def test_basic() -> None:
    # Create a WAV file image.
    buff = io.BytesIO()
    with wave.open(buff, 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(1)
        f.setframerate(44100)
        f.writeframes(b'\x00\xff' * 1000)
    wav_image = buff.getvalue()

    format = zx._wav.WAVFile
    assert format.FORMAT_NAME == 'WAV'
    wav = format.decode('x.wav', wav_image)

    # Dump.
    assert 'WAVFile' in wav.dumps()

    # Generate pulses.
    tuple(wav.get_pulses())

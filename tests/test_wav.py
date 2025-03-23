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

    format = zx._wav.WAVFileFormat()
    assert format.NAME == 'WAV'
    wav = format.parse('x.wav', wav_image)

    # Dump.
    assert 'WAVFile' in wav.dumps()

    # Generate pulses.
    tuple(wav.get_pulses())

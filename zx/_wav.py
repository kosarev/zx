# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import typing
import io
import wave
from ._binary import Bytes
from ._data import SoundFile, SoundFileFormat
from ._error import Error
from ._tape import tag_last_pulse


class WAVFile(SoundFile):
    __TICKS_FREQ = 3500000  # TODO

    sample_size: int
    num_channels: int
    frame_rate: int
    num_frames: int
    frames: Bytes

    def __init__(self, *, sample_size: int, num_channels: int, frame_rate: int,
                 num_frames: int, frames: Bytes) -> None:
        SoundFile.__init__(self, WAVFileFormat, sample_size=sample_size,
                           num_channels=num_channels, frame_rate=frame_rate,
                           num_frames=num_frames, frames=frames)

    def _generate_pulses(self) -> (
            typing.Iterable[tuple[bool, int, tuple[str, ...]]]):
        num_channels = self.num_channels

        # Get samples as a numpy array.
        import numpy
        sample_size = self.sample_size
        num_frames = self.num_frames
        frames = self.frames
        # 8-bit samples are unsigned and 16-bit ones are signed.
        dtype = {1: numpy.uint8, 2: numpy.int16}[sample_size]
        samples = numpy.frombuffer(frames, dtype, num_frames)

        assert num_channels in (1, 2)
        if num_channels == 2:
            # Combine the channels into one.
            samples = samples.reshape(num_frames // 2, 2)
            samples = samples.mean(axis=1, dtype=dtype)

        # Turn it into an array of low and high levels.
        threshold = {1: 2**(sample_size * 8 - 1), 2: 0}[sample_size]
        samples = numpy.where(samples < threshold, False, True)

        # Find indexes of edge samples.
        edge_indexes = numpy.where(samples[1:] != samples[:-1])[0]

        # Produce pulses.
        rate = self.frame_rate
        level = samples[0]
        tick = 0
        for i in edge_indexes:
            t = int((i + 1) / rate * self.__TICKS_FREQ + 0.5)
            duration = t - tick
            yield level, duration, ('WAV PULSE',)
            level = not level
            tick = t

    def get_pulses(self) -> (
            typing.Iterable[tuple[bool, int, tuple[str, ...]]]):
        return tag_last_pulse(self._generate_pulses())


class WAVFileFormat(SoundFileFormat, name='WAV'):
    _TICKS_FREQ = 3500000  # TODO

    @classmethod
    def parse(cls, filename: str, image: Bytes) -> WAVFile:
        with wave.open(io.BytesIO(image), 'rb') as f:
            num_frames = f.getnframes()
            return WAVFile(
                sample_size=f.getsampwidth(),
                num_channels=f.getnchannels(),
                frame_rate=f.getframerate(),
                num_frames=num_frames,
                frames=f.readframes(num_frames))

    @classmethod
    def save_from_pulses(cls, filename: str,
                         pulses: typing.Iterable[
                             tuple[bool, int, tuple[str, ...]]]) -> None:
        with wave.open(filename, 'wb') as f:
            f.setnchannels(1)
            f.setsampwidth(1)

            frame_rate = 44100
            f.setframerate(frame_rate)

            LOW = 0
            HIGH = 0xff
            for level, duration, tags in pulses:
                duration = int(duration * frame_rate / cls._TICKS_FREQ)
                sample = HIGH if level else LOW
                frame = bytes([sample])
                f.writeframes(frame * duration)

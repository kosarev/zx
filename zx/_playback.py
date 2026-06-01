# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import typing
from ._data import MachineSnapshot
from ._rzx import RZXSnapshot
from ._rzx import RZXCreatorInfo
from ._rzx import RZXFile
from ._rzx import RZXInputRecording

if typing.TYPE_CHECKING:  # TODO
    from ._spectrum import SpectrumState


# TODO: Rework to a time machine interface.
class PlaybackPlayer(object):
    def __init__(self, machine: 'SpectrumState', file: RZXFile) -> None:
        self.__machine = machine

        assert isinstance(file, RZXFile)
        self._recording = file

        self.samples = self.__get_playback_samples()

    def find_recording_info_chunk(self) -> RZXCreatorInfo:
        for chunk in self._recording.chunks:
            if isinstance(chunk, RZXCreatorInfo):
                return chunk
        assert 0  # TODO

    def get_chunks(self) -> list[typing.Any]:
        return self._recording.chunks

    def __get_playback_samples(self) -> typing.Iterable[str | int]:
        # TODO: Have a class describing playback state.
        self.playback_frame_count = 0
        self.playback_chunk: None | RZXInputRecording = None
        self.playback_sample_values: bytes = b''
        self.playback_sample_i = 0

        frame_count = 0
        for chunk_i, chunk in enumerate(self.get_chunks()):
            if isinstance(chunk, RZXSnapshot):
                self.__machine.install_snapshot(chunk.snapshot)
                continue

            if not isinstance(chunk, RZXInputRecording):
                continue

            self.__machine.ticks_since_int = chunk.first_tick

            for frame_i, frame in enumerate(chunk.frames):
                samples = frame.samples.data
                self.__machine.fetches_limit = frame.num_fetches

                yield 'START_OF_FRAME'

                for sample_i, sample in enumerate(samples):
                    # TODO: Have a class describing playback state.
                    self.playback_frame_count = frame_count
                    self.playback_chunk = chunk
                    self.playback_sample_values = samples
                    self.playback_sample_i = sample_i

                    yield sample

                # print('END_OF_FRAME', flush=True)
                yield 'END_OF_FRAME'

                frame_count += 1

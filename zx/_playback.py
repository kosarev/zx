# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2021 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import typing
from ._data import MachineSnapshot
from ._rzx import RZXFile

if typing.TYPE_CHECKING:  # TODO
    from ._emulator import MachineState


# TODO: Rework to a time machine interface.
class PlaybackPlayer(object):
    def __init__(self, machine: 'MachineState', file: RZXFile) -> None:
        self.__machine = machine

        assert isinstance(file, RZXFile)
        self._recording = file

        self.samples = self.__get_playback_samples()

    def find_recording_info_chunk(self) -> dict[str, typing.Any]:
        for chunk in self._recording.chunks:
            if chunk['id'] == 'info':
                return chunk
        assert 0  # TODO

    def get_chunks(self) -> list[dict[str, typing.Any]]:
        return self._recording.chunks

    def __get_playback_samples(self) -> typing.Iterable[str]:
        # TODO: Have a class describing playback state.
        self.playback_frame_count = 0
        self.playback_chunk: None | dict[str, typing.Any] = None
        self.playback_sample_values = []
        self.playback_sample_i = 0

        frame_count = 0
        for chunk_i, chunk in enumerate(self.get_chunks()):
            if isinstance(chunk, MachineSnapshot):
                self.__machine.install_snapshot(chunk)
                continue

            if chunk['id'] != 'port_samples':
                continue

            first_tick = chunk['first_tick']
            assert isinstance(first_tick, int)
            self.__machine.ticks_since_int = first_tick

            frames = chunk['frames']
            assert isinstance(frames, list)
            for frame_i, frame in enumerate(frames):
                num_of_fetches, samples = frame
                # print(num_of_fetches, samples)

                self.__machine.fetches_limit = num_of_fetches
                # print(num_of_fetches, samples, flush=True)

                # print('START_OF_FRAME', flush=True)
                yield 'START_OF_FRAME'

                for sample_i, sample in enumerate(samples):
                    # print(self.fetches_limit)
                    # fetch = num_of_fetches - self.fetches_limit
                    # print('Input at fetch', fetch, 'of', num_of_fetches)
                    # TODO: print('read_port 0x%04x 0x%02x' % (addr, n),
                    #             flush=True)

                    # TODO: Have a class describing playback state.
                    self.playback_frame_count = frame_count
                    self.playback_chunk = chunk
                    self.playback_sample_values = samples
                    self.playback_sample_i = sample_i
                    # print(frame_count, chunk_i, frame_i, sample_i, sample,
                    #       flush=True)

                    yield sample

                # print('END_OF_FRAME', flush=True)
                yield 'END_OF_FRAME'

                frame_count += 1

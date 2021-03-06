# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2021 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.

from ._data import MachineSnapshot
from ._rzx import RZXFile


# TODO: Rework to a time machine interface.
class PlaybackPlayer(object):
    def __init__(self, machine, file):
        self.__machine = machine

        assert isinstance(file, RZXFile)
        self._recording = file

        self.samples = self.__get_playback_samples()

    def find_recording_info_chunk(self):
        for chunk in self._recording['chunks']:
            if chunk['id'] == 'info':
                return chunk
        assert 0  # TODO

    def get_chunks(self):
        return self._recording['chunks']

    def __get_playback_samples(self):
        # TODO: Have a class describing playback state.
        self.playback_frame_count = 0
        self.playback_chunk = 0
        self.playback_sample_values = []
        self.playback_sample_i = 0

        frame_count = 0
        for chunk_i, chunk in enumerate(self.get_chunks()):
            if isinstance(chunk, MachineSnapshot):
                self.__machine.install_snapshot(chunk)
                continue

            if chunk['id'] != 'port_samples':
                continue

            self.__machine.ticks_since_int = chunk['first_tick']

            for frame_i, frame in enumerate(chunk['frames']):
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

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


import collections
from ._binary import BinaryParser, BinaryWriter
from ._data import MachineSnapshot
from ._data import ProcessorSnapshot
from ._data import SnapshotFormat
from ._data import UnifiedSnapshot
from ._utils import _split16


class _SCRSnapshot(MachineSnapshot):
    def get_unified_snapshot(self):
        # The address of the endless loop.
        LOOP_ADDR = 0x8000

        processor_fields = {
            'pc': LOOP_ADDR,
            'iff1': 0,
            'iff2': 0,
        }

        fields = {
            'processor_snapshot': ProcessorSnapshot(processor_fields),
            'border_color': 0,
        }

        memory_blocks = fields.setdefault('memory_blocks', [])
        memory_blocks.append((0x4000, self['dot_patterns']))
        memory_blocks.append((0x4000 + 6144, self['colour_attrs']))

        # LOOP_ADDR: jp LOOP_ADDR
        memory_blocks.append((LOOP_ADDR, b'\xc3' + bytes(_split16(LOOP_ADDR))))

        return UnifiedSnapshot(SCRFileFormat, fields)

    def get_file_image(self):
        return self['dot_patterns'] + self['colour_attrs']


class SCRFileFormat(SnapshotFormat):
    _NAME = 'SCR'

    _FIELDS = ['6144s:dot_patterns', '768s:colour_attrs']

    def parse(self, filename, image):
        parser = BinaryParser(image)
        fields = collections.OrderedDict(id='scr_snapshot')
        fields.update(parser.parse(self._FIELDS))
        return _SCRSnapshot(SCRFileFormat, fields)

    def make_snapshot(self, state):
        screen = state.read(0x4000, 6 * 1024 + 768)
        return self.parse(screen)

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


from ._binary import BinaryParser, BinaryWriter
from ._utils import _split16
import collections
import zx


class _SCRSnapshot(zx._MachineSnapshot):
    def get_unified_snapshot(self):
        # The address of the endless loop.
        LOOP_ADDR = 0x8000

        processor_fields = {
            'pc': LOOP_ADDR,
            'iff1': 0,
            'iff2': 0,
        }

        fields = {
            'processor_snapshot': zx.ProcessorSnapshot(processor_fields),
            'border_color': 0,
        }

        memory_blocks = fields.setdefault('memory_blocks', [])
        memory_blocks.append((0x4000, self['dot_patterns']))
        memory_blocks.append((0x4000 + 6144, self['colour_attrs']))

        # LOOP_ADDR: jp LOOP_ADDR
        memory_blocks.append((LOOP_ADDR, b'\xc3' + bytes(_split16(LOOP_ADDR))))

        return zx._UnifiedSnapshot(_SCRFileFormat, fields)

    def get_file_image(self):
        return self['dot_patterns'] + self['colour_attrs']


class _SCRFileFormat(zx.SnapshotsFormat):
    _NAME = 'SCR'

    _FIELDS = ['6144s:dot_patterns', '768s:colour_attrs']

    def parse(self, image):
        parser = BinaryParser(image)
        fields = collections.OrderedDict(id='scr_snapshot')
        fields.update(parser.parse(self._FIELDS))
        return _SCRSnapshot(_SCRFileFormat, fields)

    def make_snapshot(self, state):
        screen = state.get_memory_block(0x4000, 6 * 1024 + 768)
        return self.parse(screen)

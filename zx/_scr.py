# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import collections
from ._binary import Bytes, BinaryParser, BinaryWriter
from ._data import MachineSnapshot
from ._data import ProcessorSnapshot
from ._data import SnapshotFormat
from ._data import UnifiedSnapshot
from ._machine import MachineState
from ._utils import _split16


class _SCRSnapshot(MachineSnapshot):
    dot_patterns: bytes
    colour_attrs: bytes

    def get_unified_snapshot(self) -> UnifiedSnapshot:
        # The address of the endless loop.
        LOOP_ADDR = 0x8000

        processor_fields = {
            'pc': LOOP_ADDR,
            'iff1': 0,
            'iff2': 0,
        }

        fields = {
            'processor_snapshot': ProcessorSnapshot(**processor_fields),
            'border_color': 0,
        }

        memory_blocks = []
        memory_blocks.append((0x4000, self.dot_patterns))
        memory_blocks.append((0x4000 + 6144, self.colour_attrs))

        # LOOP_ADDR: jp LOOP_ADDR
        memory_blocks.append((LOOP_ADDR, b'\xc3' + bytes(_split16(LOOP_ADDR))))

        return UnifiedSnapshot(SCRFileFormat, **fields,
                               memory_blocks=memory_blocks)

    def get_file_image(self) -> bytes:
        return self.dot_patterns + self.colour_attrs


class SCRFileFormat(SnapshotFormat, name='SCR'):
    _FIELDS = ['6144s:dot_patterns', '768s:colour_attrs']

    def parse(self, filename: str, image: Bytes) -> _SCRSnapshot:
        parser = BinaryParser(image)
        fields = collections.OrderedDict()
        fields.update(parser.parse(self._FIELDS))
        return _SCRSnapshot(SCRFileFormat, **fields)

    def make_snapshot(self, state: MachineState) -> _SCRSnapshot:
        screen = state.read(0x4000, 6 * 1024 + 768)
        return self.parse('<filename>', screen)

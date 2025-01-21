# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


class DataRecord(object):
    def __init__(self, fields):
        self._fields = fields

    def __contains__(self, id):
        return id in self._fields

    def __getitem__(self, id):
        return self._fields[id]

    def __repr__(self):
        return repr(self._fields)

    def __iter__(self):
        for id in self._fields:
            yield id

    def items(self):
        for field in self._fields.items():
            yield field


class File(DataRecord):
    def __init__(self, format, fields):
        self._format = format
        DataRecord.__init__(self, fields)

    def get_format(self):
        return self._format


class FileFormat(object):
    def get_name(self):
        return self._NAME


class ArchiveFileFormat(FileFormat):
    pass


class SoundFile(File):
    pass


class SoundFileFormat(FileFormat):
    pass


class SnapshotFormat(FileFormat):
    pass


class MachineSnapshot(File):
    pass


class UnifiedSnapshot(MachineSnapshot):
    pass


# TODO: Move to the z80 project.
class ProcessorSnapshot(DataRecord):
    pass

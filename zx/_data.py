# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


class DataRecord(object):
    def __init__(self, **fields):
        self.__fields = tuple(fields)
        for id, value in fields.items():
            setattr(self, id, value)

    def __contains__(self, id):
        return id in self.__fields

    def __iter__(self):
        for id in self.__fields:
            yield id, getattr(self, id)

    def dump(self):
        import yaml
        return yaml.dump(self)


class File(DataRecord):
    def __init__(self, format, **fields):
        self._format = format
        DataRecord.__init__(self, **fields)

    def get_format(self):
        return self._format


class FileFormat(object):
    def __init_subclass__(cls, *, name):
        assert name is None or name.isupper()
        cls._NAME = name

    def get_name(self):
        return self._NAME


class ArchiveFileFormat(FileFormat, name=None):
    def __init_subclass__(cls, *, name):
        super().__init_subclass__(name=name)


class SoundFile(File):
    pass


class SoundFileFormat(FileFormat, name=None):
    def __init_subclass__(cls, *, name):
        super().__init_subclass__(name=name)


class SnapshotFormat(FileFormat, name=None):
    def __init_subclass__(cls, *, name):
        super().__init_subclass__(name=name)


class MachineSnapshot(File):
    pass


class UnifiedSnapshot(MachineSnapshot):
    pass


# TODO: Move to the z80 project.
class ProcessorSnapshot(DataRecord):
    pass

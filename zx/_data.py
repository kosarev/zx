# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

from __future__ import annotations

from ._binary import Bytes

import typing
if typing.TYPE_CHECKING:  # TODO
    from ._machine import MachineState


class DataRecord(object):
    def __init__(self, **fields: typing.Any):
        self.__fields = tuple(fields)
        for id, value in fields.items():
            setattr(self, id, value)

    def __contains__(self, id: str) -> bool:
        return id in self.__fields

    def __iter__(self) -> typing.Iterator[tuple[str, typing.Any]]:
        for id in self.__fields:
            yield id, getattr(self, id)

    def to_json(self) -> typing.Any:
        def convert(v: typing.Any) -> typing.Any:
            if isinstance(v, (int, str)):
                return v
            if isinstance(v, bytes):
                return v.decode('latin-1')
            if isinstance(v, (tuple, list)):
                return [convert(e) for e in v]
            if isinstance(v, dict):
                return {id: convert(v) for id, v in v.items()}
            if isinstance(v, DataRecord):
                return v.to_json()
            raise TypeError(f'cannot serialize a {type(v)}')

        return {id: convert(v) for id, v in self}

    def dumps(self) -> str:
        d = dict(type=type(self).__qualname__,
                 creator_tool='https://pypi.org/project/zx',
                 contents=self.to_json())
        import json
        return json.dumps(d, indent=2)


class File(DataRecord):
    def __init__(self, format: type[FileFormat], **fields: typing.Any):
        self._format = format
        DataRecord.__init__(self, **fields)

    def get_format(self) -> type[FileFormat]:
        return self._format


class FileFormat(object):
    _NAME: None | str

    def __init_subclass__(cls, *, name: None | str):
        assert name is None or name.isupper()
        cls._NAME = name

    # TODO: Remove and make the attribute public.
    def get_name(self) -> str:
        assert self._NAME is not None
        return self._NAME

    def parse(self, filename: str, image: Bytes) -> File:
        raise NotImplementedError


class ArchiveFileFormat(FileFormat, name=None):
    def __init_subclass__(cls, *, name: str):
        super().__init_subclass__(name=name)

    def read_files(self, image: Bytes) -> (
            typing.Iterable[tuple[str, Bytes]]):
        raise NotImplementedError


class SoundFile(File):
    def get_pulses(self) -> typing.Iterable[tuple[bool, int, tuple[str, ...]]]:
        raise NotImplementedError


class SoundFileFormat(FileFormat, name=None):
    def __init_subclass__(cls, *, name: str):
        super().__init_subclass__(name=name)

    def save_from_pulses(
            self, filename: str,
            pulses: typing.Iterable[tuple[bool, int,
                                          tuple[str, ...]]]) -> None:
        raise NotImplementedError


class SnapshotFormat(FileFormat, name=None):
    def __init_subclass__(cls, *, name: str):
        super().__init_subclass__(name=name)

    # TODO: Should always return snapshots?
    def make_snapshot(self, state: MachineState) -> bytes | MachineSnapshot:
        raise NotImplementedError


# TODO: Not all machine snapshots are files?
class MachineSnapshot(File):
    # TODO: Rename to to_unified_snapshot()?
    def get_unified_snapshot(self) -> UnifiedSnapshot:
        raise NotImplementedError


# TODO: Move to the z80 project.
class ProcessorSnapshot(DataRecord):
    pass


class UnifiedSnapshot(MachineSnapshot):
    pass

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

from __future__ import annotations

import numpy
import zx

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
                s = v.decode('latin-1')
                a = [s[i:i+0x10] for i in range(0, len(v), 0x10)]
                return a[0] if len(a) == 1 else a
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
                 creator_tool=f'https://pypi.org/project/zx/{zx.__version__}',
                 contents=self.to_json())
        import json
        return json.dumps(d, indent=2)


class File(DataRecord):
    FORMAT_NAME: None | str

    def __init_subclass__(cls, *, format_name: None | str):
        assert format_name is None or format_name.isupper()
        cls.FORMAT_NAME = format_name

    def __init__(self, **fields: typing.Any):
        DataRecord.__init__(self, **fields)

    @classmethod
    def parse(cls, filename: str, image: Bytes) -> 'File':
        raise NotImplementedError


class ArchiveFile(File, format_name=None):
    @classmethod
    def read_files(cls, image: Bytes) -> (
            typing.Iterable[tuple[str, Bytes]]):
        raise NotImplementedError


# TODO: Should derive from DataRecord?
class SoundPulses(object):
    def __init__(self, rate: int,
                 levels: numpy.typing.NDArray[numpy.uint32],
                 ticks: numpy.typing.NDArray[numpy.uint32]) -> None:
        assert len(levels) == len(ticks)
        self.rate, self.levels, self.ticks = rate, levels, ticks


class SoundFile(File, format_name=None):
    def get_pulses(self) -> typing.Iterable[tuple[bool, int, tuple[str, ...]]]:
        raise NotImplementedError

    @classmethod
    def save_from_pulses(
            cls, filename: str,
            pulses: typing.Iterable[tuple[bool, int,
                                          tuple[str, ...]]]) -> None:
        raise NotImplementedError


class SnapshotFile(File, format_name=None):
    @classmethod
    def encode(cls, state: MachineState) -> bytes:
        raise NotImplementedError


# TODO: Not all machine snapshots are files?
class MachineSnapshot(File, format_name=None):
    def to_unified_snapshot(self) -> UnifiedSnapshot:
        raise NotImplementedError


# TODO: Move to the z80 project.
class ProcessorSnapshot(DataRecord):
    pass


class UnifiedSnapshot(MachineSnapshot, format_name=None):
    pass

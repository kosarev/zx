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

    def dump(self) -> str:
        def dump_bytes(b: Bytes) -> str:
            h = b.hex()
            c = ''.join(chr(c) if 0x20 < c < 0x7f else '.' for c in b)
            return f'{h:64}  {c}'

        def to_yaml(n: typing.Any) -> typing.Any:
            if isinstance(n, (int, str)):
                return n
            if isinstance(n, (tuple, list)):
                return [to_yaml(e) for e in n]
            if isinstance(n, (bytes, Bytes)):
                return '\n'.join(dump_bytes(n[i:i+32])
                                 for i in range(0, len(n), 32))
            if isinstance(n, dict):
                # TODO: We should never use dict values.
                return {id: to_yaml(value) for id, value in n.items()}
            if isinstance(n, DataRecord):
                return {type(n).__qualname__:
                        {id: to_yaml(value) for id, value in n}}
            assert 0, type(n)

        # TODO: pyaml seems to either not emit strings in blocks or
        #       produce !!int kind of tags on every number.
        #       Should we just generate the string outselves without
        #       using pyyaml?
        import yaml
        return yaml.safe_dump(to_yaml(self), default_style='|').rstrip()


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

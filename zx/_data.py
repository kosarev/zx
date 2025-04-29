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
import typing
import zx

from ._binary import Bytes


class DataRecord(object):
    FORMAT_NAME: None | str

    def __init_subclass__(cls, *, format_name: None | str):
        assert format_name is None or format_name.isupper()
        cls.FORMAT_NAME = format_name

    def __init__(self, **fields: typing.Any):
        self.__fields = tuple(fields)
        for id, value in fields.items():
            setattr(self, id, value)

    def __contains__(self, id: str) -> bool:
        return id in self.__fields

    def __iter__(self) -> typing.Iterator[tuple[str, typing.Any]]:
        for id in self.__fields:
            value = getattr(self, id)
            if value is not None:
                yield id, value

    @classmethod
    def parse(cls, filename: str, image: Bytes) -> 'DataRecord':
        # TODO: Support parsing dumps.
        raise NotImplementedError

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

        return {id: convert(v) for id, v in self if v is not None}

    def dumps(self) -> str:
        metadata = dict(
            creator_tool=f'https://pypi.org/project/zx/{zx.__version__}')
        d = dict(type=type(self).__qualname__,
                 metadata=metadata)
        d.update(self.to_json())
        import json
        return json.dumps(d, indent=2)


class ArchiveFile(DataRecord, format_name=None):
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


class SoundFile(DataRecord, format_name=None):
    def get_pulses(self) -> typing.Iterable[tuple[bool, int, tuple[str, ...]]]:
        raise NotImplementedError

    @classmethod
    def save_from_pulses(
            cls, filename: str,
            pulses: typing.Iterable[tuple[bool, int,
                                          tuple[str, ...]]]) -> None:
        raise NotImplementedError


class MachineSnapshot(DataRecord, format_name=None):
    @classmethod
    def from_snapshot(cls, snapshot: MachineSnapshot) -> MachineSnapshot:
        raise NotImplementedError

    def to_unified_snapshot(self) -> UnifiedSnapshot:
        raise NotImplementedError

    def encode(self) -> bytes:
        raise NotImplementedError


class UnifiedSnapshot(MachineSnapshot, format_name=None):
    af: int | None
    bc: int | None
    de: int | None
    hl: int | None
    ix: int | None
    iy: int | None
    alt_af: int | None
    alt_bc: int | None
    alt_de: int | None
    alt_hl: int | None
    pc: int | None
    sp: int | None
    ir: int | None
    wz: int | None
    iregp_kind: str | None
    iff1: int | None
    iff2: int | None
    int_mode: int | None
    ticks_since_int: int | None
    border_colour: int | None
    memory_blocks: list[tuple[int, Bytes]] | None

    def __init__(
            self,
            af: int | None = None,
            bc: int | None = None,
            de: int | None = None,
            hl: int | None = None,
            ix: int | None = None,
            iy: int | None = None,
            alt_af: int | None = None,
            alt_bc: int | None = None,
            alt_de: int | None = None,
            alt_hl: int | None = None,
            pc: int | None = None,
            sp: int | None = None,
            ir: int | None = None,
            wz: int | None = None,
            iregp_kind: str | None = None,
            iff1: int | None = None,
            iff2: int | None = None,
            int_mode: int | None = None,
            ticks_since_int: int | None = None,
            border_colour: int | None = None,
            memory_blocks: list[tuple[int, Bytes]] | None = None):
        super().__init__(
            af=af, bc=bc, de=de, hl=hl, ix=ix, iy=iy,
            alt_af=alt_af, alt_bc=alt_bc,
            alt_de=alt_de, alt_hl=alt_hl,
            pc=pc, sp=sp, ir=ir, wz=wz, iregp_kind=iregp_kind,
            iff1=iff1, iff2=iff2, int_mode=int_mode,
            ticks_since_int=ticks_since_int,
            border_colour=border_colour,
            memory_blocks=memory_blocks)

    def to_unified_snapshot(self) -> UnifiedSnapshot:
        return self

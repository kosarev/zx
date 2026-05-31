# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

from __future__ import annotations

import numpy
import typing
import zx

from ._binary import Bytes
from ._error import Error


class DataRecord(object):
    FORMAT_NAME: None | str

    _JSON_TYPES: typing.ClassVar[dict[str, type['DataRecord']]] = {}

    def __init_subclass__(cls, *, format_name: None | str,
                          json_type: bool = False):
        assert format_name is None or format_name.isupper()
        cls.FORMAT_NAME = format_name
        if json_type:
            DataRecord._JSON_TYPES[cls.__name__] = cls

    def __init__(self, **fields: typing.Any):
        self.__fields = tuple(fields)
        for id, value in fields.items():
            setattr(self, id, value)

    def __eq__(self, other: object) -> bool:
        if type(self) is not type(other):
            return False
        assert isinstance(other, DataRecord)
        return list(self) == list(other)

    def __contains__(self, id: str) -> bool:
        return id in self.__fields

    def __iter__(self) -> typing.Iterator[tuple[str, typing.Any]]:
        for id in self.__fields:
            value = getattr(self, id)
            if value is not None:
                yield id, value

    def to_json(self) -> typing.Any:
        def convert(v: typing.Any) -> typing.Any:
            if isinstance(v, (int, str)):
                return v
            if isinstance(v, (list, tuple)):
                return [convert(e) for e in v]
            if isinstance(v, DataRecord):
                return v.to_json()
            raise TypeError(f'cannot serialize a {type(v)}')

        return {id: convert(v) for id, v in self if v is not None}

    # Construct a DataRecord from a full .zx JSON document dict.
    # Reads 'type' to find the registered class, extracts 'metadata',
    # and passes remaining fields to __init__(). Never override this —
    # __init__() and make_from() handle all type conversion.
    @classmethod
    def from_json(cls, d: dict[str, typing.Any]) -> 'DataRecord':
        type_name = d.get('type', '')
        record_cls = cls._JSON_TYPES.get(type_name)
        if record_cls is None:
            raise Error(f"Unknown type {type_name!r}.")
        metadata = d.get('metadata', {})
        fields = {k: v for k, v in d.items()
                  if k not in ('type', 'metadata')}
        # TODO: Pass metadata to the ctor so it can adapt to producer context.
        return record_cls(**fields)

    # Encode to a format-specific binary image.
    def encode(self) -> bytes:
        raise NotImplementedError

    # Decode a format-specific binary image. Counterpart of encode().
    @classmethod
    def decode(cls, filename: str, image: Bytes) -> 'DataRecord':
        raise NotImplementedError

    def dumps(self) -> str:
        import json
        d: dict[str, typing.Any] = {'type': type(self).__name__}
        d['metadata'] = {
            'creator_tool': f'https://pypi.org/project/zx/{zx.__version__}'}
        d.update(self.to_json())
        return json.dumps(d, indent=2)


class SpectrumModel(type):
    _MODELS_BY_CXX_CODES: dict[int, type['SpectrumModel']] = {}

    _CXX_MODEL_CODE: int
    _ROM_FILE_NAME: str
    _TICKS_PER_FRAME: int

    def __init_subclass__(cls, *, cxx_model_code: int, rom_file_name: str,
                          ticks_per_frame: int):
        cls._CXX_MODEL_CODE = cxx_model_code
        SpectrumModel._MODELS_BY_CXX_CODES[cxx_model_code] = cls

        cls._ROM_FILE_NAME = rom_file_name
        cls._TICKS_PER_FRAME = ticks_per_frame


class Spectrum48(SpectrumModel, cxx_model_code=0,
                 rom_file_name='Spectrum48.rom',
                 ticks_per_frame=69888):
    pass


class Spectrum128(SpectrumModel, cxx_model_code=1,
                  rom_file_name='Spectrum128.rom',
                  ticks_per_frame=70908):
    pass


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


class ByteData(DataRecord, format_name=None, json_type=True):
    __CHUNK_SIZE = 32

    Source: typing.ClassVar[typing.TypeAlias] = (
        'ByteData | Bytes | str | list[str]')

    data: bytes

    def __init__(self, data: Bytes):
        super().__init__(data=bytes(data))

    @classmethod
    def make_from(cls, data: Source) -> 'ByteData':
        if isinstance(data, cls):
            return data
        if isinstance(data, (str, list)):
            hex_str = ''.join(data) if isinstance(data, list) else data
            return cls(bytes.fromhex(hex_str))
        return cls(data)

    def to_json(self) -> str | list[str]:
        chunks = [self.data[i:i + self.__CHUNK_SIZE].hex()
                  for i in range(0, len(self.data), self.__CHUNK_SIZE)]
        if not chunks:
            return ''
        return chunks[0] if len(chunks) == 1 else chunks


class MemoryBlock(DataRecord, format_name=None, json_type=True):
    Source: typing.ClassVar[typing.TypeAlias] = (
        'MemoryBlock | dict[str, typing.Any]')

    addr: int
    rom_page: int
    ram_page: int
    data: ByteData

    def __init__(self, *, addr: int, rom_page: int, ram_page: int,
                 data: ByteData.Source):
        super().__init__(addr=addr, rom_page=rom_page,
                         ram_page=ram_page, data=ByteData.make_from(data))

    @classmethod
    def make_from(cls, block: Source) -> 'MemoryBlock':
        if isinstance(block, cls):
            return block
        return cls(**block)


class MachineSnapshot(DataRecord, format_name=None):
    @classmethod
    def from_snapshot(cls, snapshot: MachineSnapshot) -> MachineSnapshot:
        raise NotImplementedError

    def to_unified_snapshot(self) -> UnifiedSnapshot:
        raise NotImplementedError


class UnifiedSnapshot(MachineSnapshot, format_name=None, json_type=True):
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
    memory_blocks: list[MemoryBlock] | None

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
            memory_blocks: typing.Sequence[
                    MemoryBlock.Source] | None = None):
        if memory_blocks is None:
            blocks = None
        else:
            blocks = sorted((MemoryBlock.make_from(b) for b in memory_blocks),
                            key=lambda b: b.addr)

        super().__init__(
            af=af, bc=bc, de=de, hl=hl, ix=ix, iy=iy,
            alt_af=alt_af, alt_bc=alt_bc,
            alt_de=alt_de, alt_hl=alt_hl,
            pc=pc, sp=sp, ir=ir, wz=wz, iregp_kind=iregp_kind,
            iff1=iff1, iff2=iff2, int_mode=int_mode,
            ticks_since_int=ticks_since_int,
            border_colour=border_colour,
            memory_blocks=blocks)

    def to_unified_snapshot(self) -> UnifiedSnapshot:
        return self

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

from __future__ import annotations

import typing

import zx

if typing.TYPE_CHECKING:
    import numpy

    from ._binary import Bytes


class _InlineJSONDict(dict[str, typing.Any]):
    pass


class _InlineJSONList(list[typing.Any]):
    pass


def _write_json(obj: typing.Any, depth: int = 0) -> typing.Iterator[str]:
    import json
    pad = '  ' * depth

    def dict_entry(k: str, v: typing.Any) -> typing.Iterator[str]:
        yield '  ' * (depth + 1) + json.dumps(k) + ': '
        yield from _write_json(v, depth + 1)

    def list_item(e: typing.Any) -> typing.Iterator[str]:
        yield '  ' * (depth + 1)
        yield from _write_json(e, depth + 1)

    def commas(groups: typing.Iterable[typing.Iterator[str]]) -> (
            typing.Iterator[str]):
        prev = None
        for group in groups:
            if prev is not None:
                yield from prev
                yield ',\n'
            prev = group
        if prev is not None:
            yield from prev

    if isinstance(obj, (_InlineJSONDict, _InlineJSONList)):
        yield json.dumps(obj)
    elif isinstance(obj, dict):
        yield '{\n'
        yield from commas(dict_entry(k, v) for k, v in obj.items())
        yield '\n' + pad + '}'
    elif isinstance(obj, list):
        yield '[\n'
        yield from commas(list_item(e) for e in obj)
        yield '\n' + pad + ']'
    else:
        yield json.dumps(obj)


class DataRecord:
    FORMAT_NAME: None | str

    def __init_subclass__(cls, *, format_name: None | str):
        assert format_name is None or format_name.isupper()
        cls.FORMAT_NAME = format_name

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

    # A copy amended with a record of the same type: the other
    # record's fields override this record's, and where both are
    # records of one type themselves, they amend the same way, field
    # by field.
    def amended_with(self, other: typing.Self) -> typing.Self:
        assert type(other) is type(self)

        fields = dict(self)
        for id, value in other:
            base = fields.get(id)
            if isinstance(base, DataRecord) and type(base) is type(value):
                value = base.amended_with(value)
            fields[id] = value

        return type(self)(**fields)

    def to_json(self) -> typing.Any:
        def convert(v: typing.Any) -> typing.Any:
            if isinstance(v, (int, str)):
                return v
            if isinstance(v, tuple):
                return _InlineJSONList(convert(e) for e in v)
            if isinstance(v, list):
                return [convert(e) for e in v]
            if isinstance(v, DataRecord):
                fields = v.to_json()
                # Build with 'type' first to ensure it leads in the output.
                # Use type(fields) to preserve _InlineJSONDict if returned.
                d = type(fields)(type=type(v).__name__)
                d.update(fields)
                return d
            raise TypeError(f'cannot serialize a {type(v)}')

        return {id: convert(v) for id, v in self if v is not None}

    # Construct a DataRecord from a .zx JSON dict. Looks up the class
    # by 'type' via recursive __subclasses__() search, then recursively
    # converts all nested dicts and lists before calling cls(**fields).
    @classmethod
    def from_json(cls, d: dict[str, typing.Any]) -> DataRecord:
        def find(base: type) -> type | None:
            for sub in base.__subclasses__():
                if sub.__name__ == type_name:
                    return sub
                found = find(sub)
                if found:
                    return found
            return None

        def from_value(v: typing.Any) -> typing.Any:
            if isinstance(v, dict) and 'type' in v:
                return DataRecord.from_json(v)
            if isinstance(v, list):
                return [from_value(e) for e in v]
            return v

        type_name = d.get('type', '')
        # TODO: Pass metadata to the ctor so it can adapt to producer context.
        record_cls: type[DataRecord] = find(DataRecord) or DataRecord
        fields = {k: from_value(v) for k, v in d.items()
                  if k not in ('type', 'metadata')}
        return record_cls(**fields)

    # Encode to a format-specific binary image.
    def encode(self) -> bytes:
        raise NotImplementedError

    # Decode a format-specific binary image. Counterpart of encode().
    @classmethod
    def decode(cls, filename: str, image: Bytes) -> DataRecord:
        raise NotImplementedError

    def dumps(self) -> str:
        metadata = Metadata()
        d: dict[str, typing.Any] = {
            'type': type(self).__name__,
            'metadata': {'type': type(metadata).__name__,
                         **metadata.to_json()}}
        d.update(self.to_json())
        return ''.join(_write_json(d))


class Metadata(DataRecord, format_name=None):
    creator_tool: str
    created_at: str

    def __init__(self) -> None:
        import datetime
        super().__init__(
            creator_tool=f'https://pypi.org/project/zx/{zx.__version__}',
            created_at=datetime.datetime.now(datetime.timezone.utc).strftime(
                '%Y-%m-%dT%H:%M:%SZ'))


class SpectrumModel(type):
    _MODELS_BY_CXX_CODES: typing.ClassVar[dict[int, type[SpectrumModel]]] = {}

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
class SoundPulses:
    # A chunk of a pulse stream covering num_ticks ticks, with level
    # transitions at the given offsets within that span. A chunk with
    # no transitions still represents that much sustained level.
    # Levels are on a common 0..1 scale across all emitters.
    def __init__(self, rate: int,
                 levels: numpy.typing.NDArray[numpy.float64],
                 ticks: numpy.typing.NDArray[numpy.uint32],
                 num_ticks: int) -> None:
        assert len(levels) == len(ticks)
        self.rate, self.levels, self.ticks = rate, levels, ticks
        self.num_ticks = num_ticks


# A single AY register write. The tick is the write's position
# within its frame; a null tick means the frame start, which is all
# frame-granular sources know.
class AYWrite(DataRecord, format_name=None):
    tick: int | None
    reg: int
    value: int

    def __init__(self, *, tick: int | None = None, reg: int,
                 value: int) -> None:
        super().__init__(tick=tick, reg=reg, value=value)

    def to_json(self) -> _InlineJSONDict:
        return _InlineJSONDict(super().to_json())


# The register writes of the frame with the given number. Frames
# carry their numbers, so skipped frames need no representation.
class AYFrame(DataRecord, format_name=None):
    frame: int
    writes: list[AYWrite]

    def __init__(self, *, frame: int,
                 writes: list[AYWrite] | None = None) -> None:
        super().__init__(frame=frame,
                         writes=writes if writes is not None else [])


# A representation of AY music, format-specific or unified.
class AYMusic(DataRecord, format_name=None):
    @classmethod
    def from_ay_music(cls, music: AYMusic) -> AYMusic:
        raise NotImplementedError

    def to_unified_ay_stream(self) -> UnifiedAYStream:
        raise NotImplementedError


# The canonical semantic form of AY music: frames of register
# writes. A write of frame k happens at tick k * ticks_per_frame
# plus the write's own within-frame tick. All AY-music formats
# convert to and from this form.
class UnifiedAYStream(AYMusic, format_name=None):
    ticks_per_second: int
    ticks_per_frame: int
    frames: list[AYFrame]

    def __init__(self, *, ticks_per_second: int, ticks_per_frame: int,
                 frames: list[AYFrame] | None = None) -> None:
        super().__init__(ticks_per_second=ticks_per_second,
                         ticks_per_frame=ticks_per_frame,
                         frames=frames if frames is not None else [])

    @classmethod
    def from_ay_music(cls, music: AYMusic) -> UnifiedAYStream:
        return music.to_unified_ay_stream()

    def to_unified_ay_stream(self) -> UnifiedAYStream:
        return self


class SoundFile(DataRecord, format_name=None):
    def get_pulses(self) -> typing.Iterable[tuple[bool, int, tuple[str, ...]]]:
        raise NotImplementedError

    @classmethod
    def save_from_pulses(
            cls, filename: str,
            pulses: typing.Iterable[tuple[bool, int,
                                          tuple[str, ...]]]) -> None:
        raise NotImplementedError


class ByteData(DataRecord, format_name=None):
    data: bytes

    def __init__(self, data: Bytes):
        super().__init__(data=bytes(data))

    def to_json(self) -> typing.Any:
        # Serialisation is handled by encoding-specific subclasses only.
        raise NotImplementedError(
            f'{type(self).__name__} has no JSON serialisation')

    @classmethod
    def from_bytes(cls, data: Bytes) -> ByteData:
        return cls(data)

    @classmethod
    def wrap(cls, data: Bytes | ByteData) -> ByteData:
        return data if isinstance(data, ByteData) else cls.from_bytes(data)


class HexData(ByteData, format_name=None):
    __CHUNK_SIZE = 32

    def __init__(self, data: Bytes | str | list[str]):
        if isinstance(data, (str, list)):
            hex_str = ''.join(data) if isinstance(data, list) else data
            data = bytes.fromhex(hex_str)
        super().__init__(bytes(data))

    def to_json(self) -> dict[str, str | list[str]]:
        chunks = [self.data[i:i + self.__CHUNK_SIZE].hex()
                  for i in range(0, len(self.data), self.__CHUNK_SIZE)]
        if not chunks:
            return {'data': ''}
        return {'data': chunks[0] if len(chunks) == 1 else chunks}


class Latin1Data(ByteData, format_name=None):
    def __init__(self, data: str):
        super().__init__(data.encode('latin-1'))

    @classmethod
    def from_bytes(cls, data: Bytes) -> Latin1Data:
        return cls(bytes(data).decode('latin-1'))

    def to_json(self) -> dict[str, str | list[str]]:
        return {'data': self.data.decode('latin-1')}


# addr is the Z80 address where the block lives. rom_page and ram_page
# select which physical page is mapped there: rom_page applies to
# 0x0000-0x3FFF, ram_page to 0xC000-0xFFFF; 0x4000-0xBFFF maps directly.
class MemoryBlock(DataRecord, format_name=None):
    addr: int
    rom_page: int | None
    ram_page: int | None
    data: ByteData

    @property
    def end_addr(self) -> int:
        return self.addr + len(self.data.data)

    def __init__(self, *, addr: int, rom_page: int | None = None,
                 ram_page: int | None = None,
                 data: Bytes | ByteData):
        super().__init__(addr=addr, rom_page=rom_page,
                         ram_page=ram_page, data=HexData.wrap(data))


class MachineSnapshot(DataRecord, format_name=None):
    @classmethod
    def from_snapshot(cls, snapshot: MachineSnapshot) -> MachineSnapshot:
        raise NotImplementedError

    def to_unified_snapshot(self) -> UnifiedSnapshot:
        raise NotImplementedError


# A device's captured state: what a machine snapshot is composed
# of. Each device type defines its own snapshot type.
class DeviceSnapshot(DataRecord, format_name=None):
    pass


# The native machine snapshot: a composition of per-device
# snapshots, keyed by device id. A device absent from the
# composition is at its canonical reset state.
class UnifiedSnapshot(MachineSnapshot, format_name=None):
    def __init__(self, **devices: DeviceSnapshot):
        super().__init__(**devices)

    @classmethod
    def from_snapshot(cls, snapshot: MachineSnapshot) -> UnifiedSnapshot:
        return snapshot.to_unified_snapshot()

    def encode(self) -> bytes:
        return (self.dumps() + '\n').encode('utf-8')

    def to_unified_snapshot(self) -> UnifiedSnapshot:
        return self


class MachinePlayback(DataRecord, format_name=None):
    def to_unified_playback(self) -> UnifiedPlayback:
        raise NotImplementedError


class UnifiedPlaybackFrame(DataRecord, format_name=None):
    num_fetches: int
    port_samples: ByteData

    def __init__(self, *, num_fetches: int,
                 port_samples: Bytes | ByteData) -> None:
        super().__init__(num_fetches=num_fetches,
                         port_samples=HexData.wrap(port_samples))


class UnifiedPlaybackSegment(DataRecord, format_name=None):
    snapshot: UnifiedSnapshot
    frames: list[UnifiedPlaybackFrame]

    def __init__(self, *, snapshot: UnifiedSnapshot,
                 frames: list[UnifiedPlaybackFrame] | None = None) -> None:
        super().__init__(
            snapshot=snapshot,
            frames=frames if frames is not None else [])


class UnifiedPlayback(MachinePlayback, format_name=None):
    segments: list[UnifiedPlaybackSegment]
    creator: str | None
    creator_major_version: int | None
    creator_minor_version: int | None

    def __init__(self, *,
                 segments: list[UnifiedPlaybackSegment] | None = None,
                 creator: str | None = None,
                 creator_major_version: int | None = None,
                 creator_minor_version: int | None = None) -> None:
        super().__init__(segments=segments if segments is not None else [],
                         creator=creator,
                         creator_major_version=creator_major_version,
                         creator_minor_version=creator_minor_version)

    @property
    def is_spin_v05(self) -> bool:
        return (self.creator == 'SPIN 0.5' and
                self.creator_major_version == 0 and
                self.creator_minor_version == 5)

    def to_unified_playback(self) -> UnifiedPlayback:
        return self

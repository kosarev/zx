# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from __future__ import annotations

import typing
from ._binary import Bytes, BinaryParser, BinaryWriter
from ._data import _InlineJSONDict
from ._data import ByteData
from ._data import DataRecord
from ._data import HexData
from ._data import Latin1Data
from ._data import MachinePlayback
from ._data import MachineSnapshot
from ._data import UnifiedPlayback
from ._data import UnifiedPlaybackFrame
from ._data import UnifiedPlaybackSegment
from ._error import Error
from ._z80snapshot import Z80Snapshot


class RZXChunk(DataRecord, format_name=None):
    pass


class RZXFrame(RZXChunk, format_name=None):
    num_fetches: int
    samples: ByteData

    def __init__(self, *, num_fetches: int,
                 samples: Bytes | ByteData) -> None:
        super().__init__(num_fetches=num_fetches,
                         samples=HexData.wrap(samples))

    @classmethod
    def wrap(cls, frame: 'RZXFrame') -> 'RZXFrame':
        if isinstance(frame, cls):
            return frame
        return cls(num_fetches=frame.num_fetches,
                   samples=frame.samples.data)


class RZXHexFrame(RZXFrame, format_name=None):
    def __init__(self, *, num_fetches: int,
                 samples: Bytes | str) -> None:
        if isinstance(samples, str):
            samples = bytes.fromhex(samples)
        super().__init__(num_fetches=num_fetches, samples=samples)

    def to_json(self) -> _InlineJSONDict:
        return _InlineJSONDict(num_fetches=self.num_fetches,
                               samples=self.samples.data.hex())


class RZXCreatorInfo(RZXChunk, format_name=None):
    creator: ByteData
    creator_major_version: int
    creator_minor_version: int

    def __init__(self, *, creator: Bytes | ByteData,
                 creator_major_version: int,
                 creator_minor_version: int) -> None:
        super().__init__(creator=Latin1Data.wrap(creator),
                         creator_major_version=creator_major_version,
                         creator_minor_version=creator_minor_version)


class RZXInputRecording(RZXChunk, format_name=None):
    first_tick: int
    frames: list[RZXFrame]

    def __init__(self, *, first_tick: int,
                 frames: list[RZXFrame]) -> None:
        super().__init__(first_tick=first_tick,
                         frames=[RZXHexFrame.wrap(f) for f in frames])


class RZXSnapshot(RZXChunk, format_name=None):
    flags: int
    format: ByteData
    snapshot: MachineSnapshot

    def __init__(self, *, flags: int = 0, format: Bytes | ByteData,
                 snapshot: MachineSnapshot) -> None:
        super().__init__(flags=flags, format=Latin1Data.wrap(format),
                         snapshot=snapshot)


def parse_creator_info_block(image: Bytes) -> RZXCreatorInfo:
    parser = BinaryParser(image)
    fields = parser.parse([('creator', '20s'),
                           ('creator_major_version', '<H'),
                           ('creator_minor_version', '<H')])
    return RZXCreatorInfo(**fields)


def parse_snapshot_block(image: Bytes) -> RZXSnapshot:
    parser = BinaryParser(image)
    header = parser.parse([('flags', '<L'),
                           ('filename_extension', '4s'),
                           ('uncompressed_length', '<L')])

    flags = header['flags']
    assert isinstance(flags, int)
    descriptor = bool(flags & 0x1)
    compressed = bool(flags & 0x2)

    # TODO: Support snapshot descriptors.
    if descriptor:
        raise Error('RZX snapshot descriptors are not supported yet.',
                    id='rzx_snapshot_descriptor')

    snapshot_image = parser.read_remaining_bytes()
    if compressed:
        import zlib
        snapshot_image = zlib.decompress(snapshot_image)

    # TODO: Support other snapshot formats.
    filename_extension = header['filename_extension']
    assert isinstance(filename_extension, bytes)
    if filename_extension not in [b'z80\x00', b'Z80\x00']:
        raise Error('Unknown RZX snapshot format %r.' % filename_extension,
                    id='unknown_rzx_snapshot_format')

    snapshot = Z80Snapshot.decode('snapshot.z80', snapshot_image)
    return RZXSnapshot(flags=flags, format=filename_extension,
                       snapshot=snapshot)


def parse_input_recording_block(image: Bytes) -> RZXInputRecording:
    parser = BinaryParser(image)
    header = parser.parse([('num_frames', '<L'),
                           ('reserved', 'B'),
                           ('first_tick', '<L'),
                           ('flags', '<L')])

    flags = header['flags']
    assert isinstance(flags, int)
    protected = bool(flags & 0x1)
    compressed = bool(flags & 0x2)

    assert not protected  # TODO: Support protected samples.

    recording_image = parser.read_remaining_bytes()
    if compressed:
        import zlib
        recording_image = zlib.decompress(recording_image)

    recording_parser = BinaryParser(recording_image)

    NUM_SAMPLES_IN_REPEATED_FRAME = 0xffff
    frames: list[RZXFrame] = []
    while not recording_parser.is_eof():
        recording_header = recording_parser.parse([
            ('num_fetches', '<H'),
            ('num_port_samples', '<H')])

        num_samples = recording_header['num_port_samples']
        assert isinstance(num_samples, int)
        num_fetches = recording_header['num_fetches']
        assert isinstance(num_fetches, int)

        samples: Bytes | ByteData
        if num_samples == NUM_SAMPLES_IN_REPEATED_FRAME:
            # Note that only the input samples are repeated; the
            # number of fetches is as specified in the new frame.
            assert frames  # TODO
            samples = frames[-1].samples
        else:
            samples = recording_parser.read_bytes(num_samples)

        # Ignore empty frames.
        if num_fetches != 0:
            frames.append(RZXFrame(num_fetches=num_fetches,
                                   samples=samples))

    first_tick = header['first_tick']
    assert isinstance(first_tick, int)
    return RZXInputRecording(first_tick=first_tick, frames=frames)


RZX_BLOCK_ID_CREATOR_INFO = 0x10
RZX_BLOCK_ID_SNAPSHOT = 0x30
RZX_BLOCK_ID_INPUT_RECORDING = 0x80


RZX_BLOCK_PARSERS = {
    RZX_BLOCK_ID_CREATOR_INFO: parse_creator_info_block,
    RZX_BLOCK_ID_SNAPSHOT: parse_snapshot_block,
    RZX_BLOCK_ID_INPUT_RECORDING: parse_input_recording_block,
}


def parse_block(parser: BinaryParser) -> typing.Any:
    # Parse block header.
    block = parser.parse([('id', 'B'),
                          ('length', '<L')])

    # Extract block payload image.
    block_length = block['length']
    assert isinstance(block_length, int)
    if block_length < 5:
        raise Error('RZX block length is too small: %d' % block_length)
    payload_size = block_length - 5
    payload_image = parser.read_bytes(payload_size)

    # Parse payload image.
    block_id = block['id']
    assert isinstance(block_id, int)

    # TODO: Handle unknown blocks.
    if block_id not in RZX_BLOCK_PARSERS:
        raise Error('Unsupported RZX block %r.' % block_id,
                    id='unsupported_rzx_block')

    return RZX_BLOCK_PARSERS[block_id](payload_image)


def _parse_rzx(image: Bytes) -> list[RZXChunk]:
    parser = BinaryParser(image)

    # Unpack header.
    header = parser.parse([('signature', '4s'),
                           ('major_revision', 'B'),
                           ('minor_revision', 'B'),
                           ('flags', '<L')])
    rzx_signature = b'RZX!'
    if header['signature'] != rzx_signature:
        raise Error('Bad RZX file signature %r; expected %r.' % (
                        header['signature'], rzx_signature))

    # Unpack blocks.
    chunks: list[RZXChunk] = []
    while not parser.is_eof():
        chunks.append(parse_block(parser))

    return chunks


def make_rzx(chunks: list[RZXChunk]) -> Bytes:
    writer = BinaryWriter()
    signature = b'RZX!'
    major_revision = b'\x00'
    minor_revision = b'\x0c'
    flags = b'\x00\x00\x00\x00'
    writer.write_bytes(signature + major_revision + minor_revision + flags)

    for chunk in chunks:
        chunk_writer = BinaryWriter()
        if isinstance(chunk, RZXCreatorInfo):
            chunk_id = RZX_BLOCK_ID_CREATOR_INFO
            chunk_writer.write(['20s:creator',
                                '<H:creator_major_version',
                                '<H:creator_minor_version'],
                               creator=chunk.creator.data,
                               creator_major_version=(
                                   chunk.creator_major_version),
                               creator_minor_version=(
                                   chunk.creator_minor_version))
        elif isinstance(chunk, RZXSnapshot):
            chunk_id = RZX_BLOCK_ID_SNAPSHOT
            image = chunk.snapshot.encode()
            # TODO: Re-compress if chunk.flags & 0x2.
            chunk_writer.write(['<L:flags', '4s:filename_extension',
                                '<L:uncompressed_length'],
                               flags=chunk.flags & ~0x2,
                               filename_extension=chunk.format.data,
                               uncompressed_length=len(image))
            chunk_writer.write_bytes(image)
        elif isinstance(chunk, RZXInputRecording):
            chunk_id = RZX_BLOCK_ID_INPUT_RECORDING
            chunk_writer.write(['<L:num_frames', 'B:reserved',
                                '<L:first_tick', '<L:flags'],
                               num_frames=len(chunk.frames),
                               reserved=0,
                               first_tick=chunk.first_tick,
                               flags=0)
            for frame in chunk.frames:
                chunk_writer.write(['<H:num_fetches',
                                    '<H:num_port_samples'],
                                   num_fetches=frame.num_fetches,
                                   num_port_samples=len(frame.samples.data))
                chunk_writer.write_bytes(frame.samples.data)
        else:
            assert 0, chunk  # TODO

        writer.write(['B:id', '<L:size'],
                     id=chunk_id, size=len(chunk_writer.get_image()) + 4 + 1)
        writer.write_bytes(chunk_writer.get_image())

    return writer.get_image()


class RZXFile(MachinePlayback, format_name='RZX'):
    chunks: list[RZXChunk]

    def __init__(self, *, chunks: list[RZXChunk]) -> None:
        super().__init__(chunks=chunks)

    def to_unified_playback(self) -> UnifiedPlayback:
        creator = None
        creator_major_version = None
        creator_minor_version = None
        segments = []
        for chunk in self.chunks:
            if isinstance(chunk, RZXCreatorInfo):
                # The creator field is fixed-size; bytes after the first
                # non-printable-ASCII character are undefined, so we
                # truncate there and strip surrounding whitespace.
                creator_bytes = chunk.creator.data
                end = next(
                    (i for i, b in enumerate(creator_bytes)
                     if not (0x20 <= b <= 0x7e)),
                    len(creator_bytes))
                creator = creator_bytes[:end].decode('ascii').strip()
                creator_major_version = chunk.creator_major_version
                creator_minor_version = chunk.creator_minor_version
            elif isinstance(chunk, RZXSnapshot):
                segments.append(UnifiedPlaybackSegment(
                    snapshot=chunk.snapshot.to_unified_snapshot()))
            elif isinstance(chunk, RZXInputRecording):
                if not segments:
                    segments.append(UnifiedPlaybackSegment())
                s = segments[-1]
                s.snapshot.ticks_since_int = chunk.first_tick
                s.frames.extend(
                    UnifiedPlaybackFrame(num_fetches=f.num_fetches,
                                         port_samples=f.samples.data)
                    for f in chunk.frames)
            else:
                raise Error('Unknown RZX chunk: %r.' % chunk,
                            id='unknown_rzx_chunk')
        return UnifiedPlayback(segments=segments, creator=creator,
                               creator_major_version=creator_major_version,
                               creator_minor_version=creator_minor_version)

    @classmethod
    def decode(cls, filename: str, image: Bytes) -> 'RZXFile':
        return RZXFile(chunks=_parse_rzx(image))

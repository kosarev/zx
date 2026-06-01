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
from ._data import ByteData
from ._data import DataRecord
from ._data import HexData
from ._data import Latin1Data
from ._error import Error
from ._z80snapshot import Z80Snapshot


class RZXFrame(DataRecord, format_name=None):
    num_of_fetches: int
    samples: ByteData

    def __init__(self, *, num_of_fetches: int,
                 samples: Bytes | ByteData) -> None:
        super().__init__(num_of_fetches=num_of_fetches,
                         samples=HexData.wrap(samples))

    @classmethod
    def wrap(cls, frame: 'RZXFrame') -> 'RZXFrame':
        if isinstance(frame, cls):
            return frame
        return cls(num_of_fetches=frame.num_of_fetches,
                   samples=frame.samples.data)


class RZXHexFrame(RZXFrame, format_name=None):
    def __init__(self, *, num_of_fetches: int,
                 samples: Bytes | str) -> None:
        if isinstance(samples, str):
            samples = bytes.fromhex(samples)
        super().__init__(num_of_fetches=num_of_fetches, samples=samples)

    def to_json(self) -> dict[str, typing.Any]:
        return {
            'num_of_fetches': self.num_of_fetches,
            'samples': self.samples.data.hex(),
        }


class RZXCreatorInfo(DataRecord, format_name=None):
    creator: ByteData
    creator_major_version: int
    creator_minor_version: int

    def __init__(self, *, creator: Bytes | ByteData,
                 creator_major_version: int,
                 creator_minor_version: int) -> None:
        super().__init__(creator=Latin1Data.wrap(creator),
                         creator_major_version=creator_major_version,
                         creator_minor_version=creator_minor_version)


class RZXInputRecording(DataRecord, format_name=None):
    first_tick: int
    frames: list[RZXFrame]

    def __init__(self, *, first_tick: int,
                 frames: list[RZXFrame]) -> None:
        super().__init__(first_tick=first_tick,
                         frames=[RZXHexFrame.wrap(f) for f in frames])


def parse_creator_info_block(image: Bytes) -> RZXCreatorInfo:
    parser = BinaryParser(image)
    fields = parser.parse([('creator', '20s'),
                           ('creator_major_version', '<H'),
                           ('creator_minor_version', '<H')])
    return RZXCreatorInfo(**fields)


def parse_snapshot_block(image: Bytes) -> Z80Snapshot:
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

    return Z80Snapshot.decode(filename_extension.decode(), snapshot_image)


def parse_input_recording_block(image: Bytes) -> RZXInputRecording:
    parser = BinaryParser(image)
    header = parser.parse([('num_of_frames', '<L'),
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

    NUM_OF_SAMPLES_IN_REPEATED_FRAME = 0xffff
    frames: list[RZXFrame] = []
    while not recording_parser.is_eof():
        recording_header = recording_parser.parse([
            ('num_of_fetches', '<H'),
            ('num_of_port_samples', '<H')])

        num_of_samples = recording_header['num_of_port_samples']
        assert isinstance(num_of_samples, int)
        num_of_fetches = recording_header['num_of_fetches']
        assert isinstance(num_of_fetches, int)

        samples: Bytes | ByteData
        if num_of_samples == NUM_OF_SAMPLES_IN_REPEATED_FRAME:
            # Note that only the input samples are repeated; the
            # number of fetches is as specified in the new frame.
            assert frames  # TODO
            samples = frames[-1].samples
        else:
            samples = recording_parser.read_bytes(num_of_samples)

        # Ignore empty frames.
        if num_of_fetches != 0:
            frames.append(RZXFrame(num_of_fetches=num_of_fetches,
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


def _parse_rzx(image: Bytes) -> list[DataRecord]:
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
    chunks: list[DataRecord] = []
    while not parser.is_eof():
        chunks.append(parse_block(parser))

    return chunks


def make_rzx(chunks: list[DataRecord]) -> Bytes:
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
        elif isinstance(chunk, Z80Snapshot):
            chunk_id = RZX_BLOCK_ID_SNAPSHOT
            image = chunk.encode()
            chunk_writer.write(['<L:flags', '4s:filename_extension',
                                '<L:uncompressed_length'],
                               flags=0,  # Non-descriptor. Not compressed.
                               filename_extension=b'Z80\x00',
                               uncompressed_length=len(image))
            chunk_writer.write_bytes(image)
        elif isinstance(chunk, RZXInputRecording):
            chunk_id = RZX_BLOCK_ID_INPUT_RECORDING
            chunk_writer.write(['<L:num_of_frames', 'B:reserved',
                                '<L:first_tick', '<L:flags'],
                               num_of_frames=len(chunk.frames),
                               reserved=0,
                               first_tick=chunk.first_tick,
                               flags=0)
            for frame in chunk.frames:
                chunk_writer.write(['<H:num_of_fetches',
                                    '<H:num_of_port_samples'],
                                   num_of_fetches=frame.num_of_fetches,
                                   num_of_port_samples=len(frame.samples.data))
                chunk_writer.write_bytes(frame.samples.data)
        else:
            assert 0, chunk  # TODO

        writer.write(['B:id', '<L:size'],
                     id=chunk_id, size=len(chunk_writer.get_image()) + 4 + 1)
        writer.write_bytes(chunk_writer.get_image())

    return writer.get_image()


class RZXFile(DataRecord, format_name='RZX', json_type=True):
    chunks: list[DataRecord]

    def __init__(self, *, chunks: list[DataRecord]) -> None:
        super().__init__(chunks=chunks)

    @classmethod
    def decode(cls, filename: str, image: Bytes) -> 'RZXFile':
        return RZXFile(chunks=_parse_rzx(image))

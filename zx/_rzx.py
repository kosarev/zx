# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import typing
from ._binary import Bytes, BinaryParser, BinaryWriter
from ._data import DataRecord
from ._error import Error
from ._z80snapshot import Z80Snapshot


def parse_creator_info_block(image: Bytes) -> dict[str, typing.Any]:
    parser = BinaryParser(image)
    chunk = parser.parse([('creator', '20s'),
                          ('creator_major_version', '<H'),
                          ('creator_minor_version', '<H')])
    chunk['id'] = 'info'
    return chunk


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

    format = Z80Snapshot
    return format.parse(filename_extension.decode(), snapshot_image)


def parse_input_recording_block(image: Bytes) -> dict[str, typing.Any]:
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
    frames: list[typing.Any] = []
    while not recording_parser.is_eof():
        recording_header = recording_parser.parse([
            ('num_of_fetches', '<H'),
            ('num_of_port_samples', '<H')])

        num_of_samples = recording_header['num_of_port_samples']
        assert isinstance(num_of_samples, int)
        num_of_fetches = recording_header['num_of_fetches']

        if num_of_samples == NUM_OF_SAMPLES_IN_REPEATED_FRAME:
            # Note that only the input samples are repeated; the
            # number of fetches is as specified in the new frame.
            assert frames  # TODO
            prev_samples = frames[-1][1]
            frame = (num_of_fetches, prev_samples)
        else:
            samples = recording_parser.read_bytes(num_of_samples)
            frame = (num_of_fetches, samples)

        # Ignore empty frames.
        if frame[0] != 0:
            frames.append(frame)

    return {'id': 'port_samples',
            'first_tick': header['first_tick'],
            'frames': frames}


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


def _parse_rzx(image: Bytes) -> dict[str, typing.Any]:
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
    chunks = []
    while not parser.is_eof():
        chunks.append(parse_block(parser))

    return {'chunks': chunks}


def make_rzx(recording: dict[str, typing.Any]) -> Bytes:
    # TODO: Turn this into a DataRecord instead.
    # assert recording['id'] == 'input_recording'

    writer = BinaryWriter()
    signature = b'RZX!'
    major_revision = b'\x00'
    minor_revision = b'\x0c'
    flags = b'\x00\x00\x00\x00'
    writer.write_block(signature + major_revision + minor_revision + flags)

    for chunk in recording['chunks']:
        chunk_writer = BinaryWriter()
        id = chunk['id']
        if id == 'info':
            chunk_id = RZX_BLOCK_ID_CREATOR_INFO
            chunk_writer.write(['20s:creator',
                                '<H:creator_major_version',
                                '<H:creator_minor_version'], **chunk)
        elif id == 'snapshot':
            chunk_id = RZX_BLOCK_ID_SNAPSHOT

            image = chunk['image']
            chunk_writer.write(['<L:flags', '4s:filename_extension',
                                '<L:uncompressed_length'],
                               flags=0,  # Non-descriptor. Not compressed.
                               filename_extension=b'Z80\x00',
                               uncompressed_length=len(image))
            chunk_writer.write_block(image)
        elif id == 'port_samples':
            chunk_id = RZX_BLOCK_ID_INPUT_RECORDING

            frames = chunk['frames']
            chunk_writer.write(['<L:num_of_frames', 'B:reserved',
                                '<L:first_tick', '<L:flags'],
                               num_of_frames=len(frames), reserved=0,
                               first_tick=0,  # TODO
                               flags=0,  # Not protected. Not compressed.
                               )

            for num_of_fetches, samples in frames:
                chunk_writer.write(['<H:num_of_fetches',
                                    '<H:num_of_port_samples'],
                                   num_of_fetches=num_of_fetches,
                                   num_of_port_samples=len(samples))
                chunk_writer.write_block(samples)
        else:
            assert 0, (id, list(chunk))  # TODO

        writer.write(['B:id', '<L:size'],
                     id=chunk_id, size=len(chunk_writer.get_image()) + 4 + 1)
        writer.write_block(chunk_writer.get_image())

    return writer.get_image()


class RZXFile(DataRecord, format_name='RZX'):
    chunks: list[dict[str, int | str | dict[str, tuple[int, list[int]]]]]

    def __init__(self, **recording: typing.Any) -> None:
        super().__init__(**recording)

    @classmethod
    def parse(cls, filename: str, image: Bytes) -> 'RZXFile':
        recording = _parse_rzx(image)
        return RZXFile(**recording)

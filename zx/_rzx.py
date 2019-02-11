# -*- coding: utf-8 -*-


from ._binaryparser import BinaryParser
import zx


def parse_creator_info_block(image):
    parser = BinaryParser(image)
    chunk = parser.parse([('creator', '20s'),
                          ('creator_major_version', '<H'),
                          ('creator_minor_version', '<H')])
    chunk['id'] = 'info'
    return chunk


def parse_snapshot_block(image):
    parser = BinaryParser(image)
    header = parser.parse([('flags', '<L'),
                           ('filename_extension', '4s'),
                           ('uncompressed_length', '<L')])

    # TODO: Support other snapshot formats.
    filename_extension = header['filename_extension']
    assert filename_extension in [b'z80\x00', b'Z80\x00'], filename_extension

    flags = header['flags']
    descriptor = bool(flags & 0x1)
    compressed = bool(flags & 0x2)

    assert not descriptor  # TODO: Support snapshot descriptors.
    assert compressed  # TODO: Support uncompressed snapshots.

    import zlib
    snapshot_image = zlib.decompress(parser.extract_rest())

    return zx.parse_z80_snapshot(snapshot_image)


def parse_input_recording_block(image):
    parser = BinaryParser(image)
    header = parser.parse([('num_of_frames', '<L'),
                           ('reserved', 'B'),
                           ('first_tick', '<L'),
                           ('flags', '<L')])

    flags = header['flags']
    protected = bool(flags & 0x1)
    compressed = bool(flags & 0x2)

    assert not protected  # TODO: Support protected samples.
    assert compressed  # TODO: Support uncompressed samples.

    import zlib
    recording_image = zlib.decompress(parser.extract_rest())
    recording_parser = BinaryParser(recording_image)

    NUM_OF_SAMPLES_IN_REPEATED_FRAME = 0xffff
    frames = []
    while not recording_parser.is_eof():
        recording_header = recording_parser.parse([
            ('num_of_fetches', '<H'),
            ('num_of_port_samples', '<H')])

        num_of_samples = recording_header['num_of_port_samples']
        num_of_fetches = recording_header['num_of_fetches']

        if num_of_samples == NUM_OF_SAMPLES_IN_REPEATED_FRAME:
            # Note that only the input samples are repeated; the
            # number of fetches is as specified in the new frame.
            assert frames  # TODO
            prev_samples = frames[-1][1]
            frame = (num_of_fetches, prev_samples)
        else:
            samples = recording_parser.extract_block(num_of_samples)
            samples = bytes(samples)
            frame = (num_of_fetches, samples)

        # print(frame)
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


def parse_block(parser):
    # Parse block header.
    block = parser.parse([('id', 'B'),
                          ('length', '<L')])

    # Extract block payload image.
    block_length = block['length']
    if block_length < 5:
        raise ZXError('RZX block length is too small: %d' % block_length)
    payload_size = block_length - 5
    payload_image = parser.extract_block(payload_size)

    # Parse payload image.
    block_id = block['id']
    # TODO: Handle unknown blocks.
    return RZX_BLOCK_PARSERS[block_id](payload_image)


def parse_rzx(image):
    parser = BinaryParser(image)

    # Unpack header.
    header = parser.parse([('signature', '4s'),
                           ('major_revision', 'B'),
                           ('minor_revision', 'B'),
                           ('flags', '<L')])
    rzx_signature = b'RZX!'
    if header['signature'] != rzx_signature:
        raise zx.Error('Bad RZX file signature %r; expected %r.' % (
                          header['signature'], rzx_signature))

    # Unpack blocks.
    chunks = []
    while not parser.is_eof():
        chunks.append(parse_block(parser))

    return {'id': 'input_recording', 'chunks': chunks}

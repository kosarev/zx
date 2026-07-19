#!/usr/bin/env python3

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

from __future__ import annotations

import json

import pytest

from zx._ay import AYFile
from zx._data import DataRecord
from zx._error import Error
from zx._file import parse_file_image


def be(value: int) -> bytes:
    return bytes(((value >> 8) & 0xff, value & 0xff))


def rel(pos: int, target: int) -> bytes:
    return be((target - pos) & 0xffff)


# A minimal well-formed file: one song, one block, with a padding
# byte before the song name, laid out in file order.
AUTHOR = 0x14
MISC = 0x17
SONGS = 0x19
PAD = 0x1d
NAME = 0x1e
DATA = 0x23
POINTS = 0x31
ADDRESSES = 0x37
BLOCK_DATA = 0x3f

IMAGE = (
    b'ZXAYEMUL' + bytes((1, 2)) + be(0) +
    rel(12, AUTHOR) + rel(14, MISC) + bytes((0, 0)) + rel(18, SONGS) +
    b'Au\x00' +
    b'M\x00' +
    rel(SONGS, NAME) + rel(SONGS + 2, DATA) +
    b'\x00' +
    b'Song\x00' +
    bytes((0, 1, 2, 3)) + be(0x0102) + be(3) + bytes((0, 0)) +
    rel(DATA + 10, POINTS) + rel(DATA + 12, ADDRESSES) +
    be(0xc000) + be(0x8000) + be(0) +
    be(0x8000) + be(3) + rel(ADDRESSES + 4, BLOCK_DATA) + be(0) +
    b'\xaa\xbb\xcc')


def test_detection_and_roundtrip() -> None:
    ay = parse_file_image('x.ay', IMAGE)
    assert isinstance(ay, AYFile)
    assert ay.encode() == IMAGE
    assert 'AYFile' in ay.dumps()


def test_parsed_fields() -> None:
    ay = AYFile.decode('x.ay', IMAGE)

    assert ay.file_version == 1
    assert ay.player_version == 2
    assert ay.author == 'Au'
    assert ay.misc == 'M'
    assert ay.first_song == 0

    song, = ay.songs
    assert song.name == 'Song'
    assert (song.a_amiga_channel_number, song.b_amiga_channel_number,
            song.c_amiga_channel_number,
            song.noise_amiga_channel_number) == (0, 1, 2, 3)
    assert song.frames_per_song == 0x0102
    assert song.frames_per_fade_out == 3
    assert song.z80_regs_value == 0
    assert song.sp == 0xc000
    assert song.init_addr == 0x8000
    assert song.int_addr == 0

    block, = song.blocks
    assert block.address == 0x8000
    assert block.length is None
    assert block.stated_length == 3
    assert block.data.data == b'\xaa\xbb\xcc'

    # The padding byte is a gap: referenced by nothing, but kept.
    gap, = ay.gaps
    assert gap.offset == PAD
    assert gap.data.data == b'\x00'


def test_json_roundtrip() -> None:
    ay = AYFile.decode('x.ay', IMAGE)
    again = DataRecord.from_json(json.loads(ay.dumps()))
    assert isinstance(again, AYFile)
    assert again.encode() == IMAGE


def test_shared_terminator() -> None:
    # Rippers overlap structures: here the points structure starts
    # at the block-list terminator, sharing its zero word as the
    # stack value.
    songs = 0x14
    name = 0x18
    data = 0x1a
    addresses = 0x28
    points = addresses + 6
    block_data = points + 6

    image = (
        b'ZXAYEMUL' + bytes((0, 0)) + be(0) +
        be(0) + be(0) + bytes((0, 0)) + rel(18, songs) +
        rel(songs, name) + rel(songs + 2, data) +
        b'S\x00' +
        bytes((0, 1, 2, 3)) + be(1) + be(0) + bytes((0, 0)) +
        rel(data + 10, points) + rel(data + 12, addresses) +
        be(0x8000) + be(1) + rel(addresses + 4, block_data) +
        be(0) + be(0x8000) + be(0) +
        b'\xee')

    ay = AYFile.decode('x.ay', image)
    song, = ay.songs
    assert song.entry_points_offset == points
    assert song.sp == 0
    assert song.init_addr == 0x8000
    assert ay.author is None
    assert ay.misc is None
    assert not ay.gaps
    assert ay.encode() == image


def test_truncated_block_data() -> None:
    # A stated block length running past the end of the file: the
    # block keeps the stated length and the bytes present.
    image = bytearray(IMAGE)
    image[ADDRESSES + 2:ADDRESSES + 4] = be(100)

    ay = AYFile.decode('x.ay', bytes(image))
    block, = ay.songs[0].blocks
    assert block.length == 100
    assert block.data.data == b'\xaa\xbb\xcc'
    assert ay.encode() == bytes(image)


def test_errors() -> None:
    with pytest.raises(Error) as e:
        AYFile.decode('x.ay', b'not an ay file')
    assert e.value.id == 'not_an_ay_file'

    with pytest.raises(Error) as e:
        AYFile.decode('x.ay', b'ZXAYAMAD' + IMAGE[8:])
    assert e.value.id == 'unsupported_ay_type'

    # An out-of-range pointer.
    image = bytearray(IMAGE)
    image[18:20] = be(0x7000)
    with pytest.raises(Error) as e:
        AYFile.decode('x.ay', bytes(image))
    assert e.value.id == 'bad_ay_file'

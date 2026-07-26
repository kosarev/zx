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

import zx
from zx._ay import AYFile
from zx._ay import AYFileBlock
from zx._ay import AYFileSong
from zx._ay8910 import AY8910
from zx._ay8910 import AY8910Snapshot
from zx._beeper import Beeper
from zx._beeper import BeeperSnapshot
from zx._data import DataRecord
from zx._emulator import Emulator
from zx._emulator import Machine
from zx._error import Error
from zx._file import parse_file_image
from zx._spectrum48 import Spectrum48CoreSnapshot
from zx._spectrum48 import Spectrum48MemoryMapping


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


def _make_song(*, init_addr: int = 0x8000, int_addr: int = 0,
               sp: int = 0, z80_regs_value: int = 0,
               blocks: list[AYFileBlock] | None = None) -> AYFileSong:
    return AYFileSong(
        name_offset=0, name='S', data_offset=0,
        a_amiga_channel_number=0, b_amiga_channel_number=1,
        c_amiga_channel_number=2, noise_amiga_channel_number=3,
        frames_per_song=0, frames_per_fade_out=0,
        z80_regs_value=z80_regs_value,
        entry_points_offset=0, sp=sp,
        init_addr=init_addr, int_addr=int_addr,
        blocks_offset=0, blocks=blocks if blocks is not None else [])


def test_to_machine_snapshot() -> None:
    # The song converts to a snapshot of the player machine: the
    # canonical fill, the launch stub, the song's blocks and the
    # register seeds, with the AY as a machine member.
    ay = AYFile.decode('x.ay', IMAGE)
    song, = ay.songs
    snapshot = ay.to_machine_snapshot(song)

    members = dict(snapshot)
    assert isinstance(members['ay'], AY8910Snapshot)
    assert isinstance(members['beeper'], BeeperSnapshot)

    core = members['core']
    assert isinstance(core, Spectrum48CoreSnapshot)

    z80 = core.z80
    assert z80 is not None
    assert (z80.af, z80.bc, z80.de, z80.hl) == (0, 0, 0, 0)
    assert (z80.ix, z80.iy) == (0, 0)
    assert (z80.alt_af, z80.alt_bc, z80.alt_de, z80.alt_hl) == (0, 0, 0, 0)
    assert (z80.pc, z80.sp) == (0x0000, 0xc000)

    # No play routine: the loop runs in IM 2 and 0x0038 keeps the
    # spec's EI over the fill's RET.
    assert z80.int_mode == 2

    memory = core.memory
    mapping = Spectrum48MemoryMapping()
    assert memory.match(mapping, 0x0000,
                        bytes((0xcd, 0x00, 0x80,      # CALL 0x8000
                               0xfb, 0x76,            # EI; HALT
                               0x18, 0xfc,            # JR $-2
                               0xc9)))                # the fill
    assert memory.match(mapping, 0x0038, b'\xfb\xc9')
    assert memory.match(mapping, 0x00ff, b'\xc9\xff\xff')
    assert memory.match(mapping, 0x3fff, b'\xff\x00\x00')
    assert memory.match(mapping, 0x8000, b'\xaa\xbb\xcc\x00')


def test_to_machine_snapshot_play_routine_and_seeds() -> None:
    # A play routine turns the 0x0038 handler into a call to it and
    # the loop runs in IM 1; the register seeds land in every pair.
    ay = AYFile(songs_offset=0, songs=[])
    song = _make_song(int_addr=0x9000, sp=0xfff0, z80_regs_value=0x1234,
                      blocks=[AYFileBlock(address=0x8000, data_offset=0,
                                          data=b'\xee')])
    snapshot = ay.to_machine_snapshot(song)

    core = dict(snapshot)['core']
    assert isinstance(core, Spectrum48CoreSnapshot)

    z80 = core.z80
    assert z80 is not None
    assert (z80.af, z80.bc, z80.de, z80.hl) == (0x1234,) * 4
    assert (z80.ix, z80.iy) == (0x1234, 0x1234)
    assert (z80.alt_af, z80.alt_bc,
            z80.alt_de, z80.alt_hl) == (0x1234,) * 4
    assert z80.sp == 0xfff0
    assert z80.int_mode == 1

    mapping = Spectrum48MemoryMapping()
    assert core.memory.match(mapping, 0x0038,
                             bytes((0xcd, 0x00, 0x90,  # CALL 0x9000
                                    0xc9)))            # the fill


def test_to_machine_snapshot_block_placement() -> None:
    # Blocks land over the fill and the stub, and content past the
    # top of memory is dropped. A zero init address means the first
    # block's address.
    ay = AYFile(songs_offset=0, songs=[])
    song = _make_song(
        init_addr=0,
        blocks=[AYFileBlock(address=0x0005, data_offset=0,
                            data=b'\x11\x22'),
                AYFileBlock(address=0xfffe, data_offset=0,
                            data=b'\x33\x44\x55\x66')])
    snapshot = ay.to_machine_snapshot(song)

    core = dict(snapshot)['core']
    assert isinstance(core, Spectrum48CoreSnapshot)
    z80 = core.z80
    assert z80 is not None

    mapping = Spectrum48MemoryMapping()
    assert core.memory.match(mapping, 0x0000,
                             bytes((0xcd, 0x05, 0x00,  # CALL 0x0005
                                    0xfb, 0x76,
                                    0x11, 0x22)))
    assert core.memory.match(mapping, 0xfffe, b'\x33\x44')


def test_converted_song_plays() -> None:
    # The player machine runs a converted song end to end: the stub
    # calls init once, and the IM 1 handler calls the play routine
    # on every interrupt.
    init = bytes((
        0x3e, 0x5a,        # LD A, 0x5a
        0x32, 0x00, 0xc0,  # LD (0xc000), A
        0xc9))             # RET
    play = bytes((
        0x21, 0x01, 0xc0,  # LD HL, 0xc001
        0x34,              # INC (HL)
        0xc9))             # RET

    ay = AYFile(songs_offset=0, songs=[])
    song = _make_song(
        init_addr=0x8000, int_addr=0x9000, sp=0xfff0,
        blocks=[AYFileBlock(address=0x8000, data_offset=0, data=init),
                AYFileBlock(address=0x9000, data_offset=0, data=play)])

    with Emulator(machine=Machine.bare(core=zx.Core(), ay=AY8910(),
                                       beeper=Beeper(),
                                       snapshot=ay.to_machine_snapshot(song)),
                  environment=[]) as app:
        app.run(duration=0.1)

        core = app.machine.devices['core']
        assert isinstance(core, zx.Core)
        mapping = Spectrum48MemoryMapping()
        assert core.read8(mapping, 0xc000) == 0x5a
        assert core.read8(mapping, 0xc001) >= 3


def test_to_machine_snapshot_no_entry() -> None:
    # A song with no init address and no blocks has nothing to run.
    ay = AYFile(songs_offset=0, songs=[])
    with pytest.raises(Error) as e:
        ay.to_machine_snapshot(_make_song(init_addr=0))
    assert e.value.id == 'bad_ay_file'


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

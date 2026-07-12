#!/usr/bin/env python3

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import pathlib

import pytest

import zx
from zx._error import Error
from zx._file import parse_file_image
from zx._psg import PSGEnd
from zx._psg import PSGFile
from zx._psg import PSGNextFrame
from zx._psg import PSGSkipFrames
from zx._psg import PSGWrite

TICKS_PER_FRAME = 70908

IMAGE = (b'PSG\x1a' + bytes(12) +
         bytes([0xff,
                0x00, 0x5c,
                0x01, 0x04,
                0xff, 0xff,
                0x08, 0x0f,
                0xfe, 0x02,
                0x07, 0x38,
                0xfd]))


def test_detection_and_roundtrip() -> None:
    psg = parse_file_image('x.psg', IMAGE)
    assert isinstance(psg, PSGFile)
    assert psg.version == 0
    assert psg.frequency == 0
    assert psg.encode() == IMAGE
    assert 'PSGFile' in psg.dumps()


def test_parsed_commands() -> None:
    psg = PSGFile.decode('x.psg', IMAGE)

    # One record per wire command, encoding choices preserved.
    assert psg.commands == [
        PSGNextFrame(),
        PSGWrite(reg=0, value=0x5c),
        PSGWrite(reg=1, value=0x04),
        PSGNextFrame(),
        PSGNextFrame(),
        PSGWrite(reg=8, value=0x0f),
        PSGSkipFrames(count=2),
        PSGWrite(reg=7, value=0x38),
        PSGEnd()]


def test_construct_from_commands() -> None:
    psg = PSGFile(commands=[
        PSGWrite(reg=13, value=8),
        PSGSkipFrames(count=1),
        PSGWrite(reg=0, value=1),
        PSGEnd()])
    assert psg.encode() == (b'PSG\x1a' + bytes(12) +
                            bytes([0x0d, 0x08, 0xfe, 0x01,
                                   0x00, 0x01, 0xfd]))


def test_to_unified_ay_stream() -> None:
    stream = PSGFile.decode('x.psg', IMAGE).to_unified_ay_stream()
    assert stream.ticks_per_second == 3546900
    assert stream.ticks_per_frame == TICKS_PER_FRAME

    # Each next-frame command opens the next frame; the skip command
    # skips four times its count.
    assert [(f.frame, [(w.reg, w.value) for w in f.writes])
            for f in stream.frames] == [
        (1, [(0, 0x5c), (1, 0x04)]),
        (3, [(8, 0x0f)]),
        (11, [(7, 0x38)])]


def test_declared_frequency() -> None:
    image = b'PSG\x1a\x0a\x3c' + bytes(10) + bytes([0xff, 0x00, 0x01])
    psg = PSGFile.decode('x.psg', image)
    assert psg.version == 10
    assert psg.frequency == 60
    assert psg.encode() == image

    # 3,546,900 / 60 = 59,115 ticks per frame, exactly.
    stream = psg.to_unified_ay_stream()
    assert stream.ticks_per_frame == 59115
    assert [(f.frame, [(w.reg, w.value) for w in f.writes])
            for f in stream.frames] == [(1, [(0, 1)])]


def test_trailing_bytes() -> None:
    image = IMAGE + b'junk'
    psg = PSGFile.decode('x.psg', image)
    assert psg.trailing is not None
    assert psg.trailing.data == b'junk'
    assert psg.encode() == image


def test_bad_stream() -> None:
    image = b'PSG\x1a' + bytes(12) + bytes([0x20])
    with pytest.raises(Error):
        PSGFile.decode('x.psg', image)

    with pytest.raises(Error):
        PSGFile.decode('x.psg', b'not a psg')


def test_convert_to_zx(tmp_path: pathlib.Path) -> None:
    src = tmp_path / 'x.psg'
    src.write_bytes(IMAGE)
    dest = tmp_path / 'x.zx'

    zx._main.convert_file(str(src), str(dest))
    assert 'PSGFile' in dest.read_text()


def test_unify_to_zx(tmp_path: pathlib.Path) -> None:
    src = tmp_path / 'x.psg'
    src.write_bytes(IMAGE)
    dest = tmp_path / 'x.zx'

    zx._main.unify([str(src), str(dest)])
    text = dest.read_text()
    assert 'UnifiedAYStream' in text
    assert 'AYWrite' in text

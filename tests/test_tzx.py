# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


#!/usr/bin/env python3

import zx
import pytest


def test_basic() -> None:
    # Parse a TZX file.
    image = (b'ZXTape!\x1a\x01\r\x10\xe8\x03\x13\x00\x00\x03123.tzx   '
             b'\x03\x00\x00\x00\x00\x80\xc8\x10\xe8\x03\x05\x00\xff'
             b'\x01\x02\x03\xff')
    format = zx._tzx.TZXFile
    assert format.FORMAT_NAME == 'TZX'
    tzx = format.decode('123.tzx', image)

    # Generate pulses.
    tuple(tzx.get_pulses())

    # Dump.
    assert 'TZXFile' in tzx.dumps()

#!/usr/bin/env python3

import zx
import pytest


def test_basic():
    # Create a TAP file object.
    zx._tap.TAPFile(blocks=[b'abc', b'def'])

    # Parse a TAP file.
    data = b'123'
    block = len(data).to_bytes(2, 'little') + data
    format = zx._tap.TAPFileFormat()
    assert format._NAME == 'TAP'
    tap = format.parse('file.tap', block)

    # Generate pulses.
    tuple(tap.get_pulses())

    # Dump.
    assert 'zx._tap.TAPFile' in tap.dump()

#!/usr/bin/env python3

import zx


def test_basic() -> None:
    # Create an emulator instance.
    with zx.Emulator(speed_factor=None) as mach:
        pass

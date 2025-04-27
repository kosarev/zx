#!/usr/bin/env python3

import zx


def test_basic() -> None:
    # Create an emulator instance.
    with zx.Spectrum(headless=True) as mach:
        pass

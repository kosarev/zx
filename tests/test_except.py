#!/usr/bin/env python3

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import zx


def test_exceptions() -> None:
    e = zx.EmulatorException('reason')
    assert isinstance(e, Exception)
    assert e.args == ('reason',)
    assert e.reason == 'reason'

    assert isinstance(zx.EmulationExit(), zx.EmulatorException)

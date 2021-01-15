# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2021 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


import unittest


class test_exceptions(unittest.TestCase):
    def runTest(self):
        import zx

        e = zx.EmulatorException('reason')
        assert isinstance(e, Exception)
        assert e.args == ('reason',), e.args
        assert e.reason == 'reason', e.args

        e = zx.EmulationExit()
        assert isinstance(e, zx.EmulatorException)

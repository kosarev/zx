# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import gc
import unittest


''' XFAIL
class test_spectrum48_rom(unittest.TestCase):
    def runTest(self):
        import zx
        rom = zx.get_rom_image('ZX Spectrum 48K')
        assert type(rom) is bytes
        assert len(rom) == 0x4000
        assert rom.startswith(b'\xf3\xaf\x11\xff')
'''


if __name__ == '__main__':
    unittest.main()

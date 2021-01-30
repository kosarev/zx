# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


import gc
import unittest


''' XFAIL
class test_create(unittest.TestCase):
    def runTest(self):
        import zx
        mach = zx.Spectrum48()
        del mach


class test_derive(unittest.TestCase):
    def runTest(self):
        import zx
        class speccy(zx.Spectrum48):
            pass
        mach = speccy()
        del mach


class test_get_memory(unittest.TestCase):
    def runTest(self):
        import zx
        mach = zx.Spectrum48()
        mem = mach.get_memory()
        assert len(mem) == 0x10000
        assert mem[0] == 0xf3, '0x%x' % mem[0]
        mem[0] += 1
        assert mem[0] == 0xf4, '0x%x' % mem[0]


class test_render_frame(unittest.TestCase):
    def runTest(self):
        import zx
        mach = zx.Spectrum48()
        data = mach.render_screen()
        assert len(data) == 49280


class test_get_frame_pixels(unittest.TestCase):
    def runTest(self):
        import zx
        mach = zx.Spectrum48()
        mach.render_screen()
        pixels = mach.get_frame_pixels()
        assert len(pixels) == 394240


class test_execute_frame(unittest.TestCase):
    def runTest(self):
        import zx
        mach = zx.Spectrum48()

        mem = mach.get_memory()
        mem[0:2] = bytearray([0x18, 0x100 - 2])  # jr $

        mach.run()


class test_keyboard(unittest.TestCase):
    def runTest(self):
        import zx
        info = zx.KEYS_INFO
        assert info['3']['number'] == 2
        assert info['N']['halfrow_number'] == 7
        assert info['H']['pos_in_halfrow'] == 0
        assert info['C']['is_leftside'] == True
        assert info['E']['is_rightside'] == False
        assert info['R']['address_line'] == 10
        assert info['5']['port_bit'] == 4
'''


if __name__ == '__main__':
    unittest.main()

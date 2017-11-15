# -*- coding: utf-8 -*-

import gc, unittest


class test_create(unittest.TestCase):
    def runTest(self):
        import zx.emulator
        mach = zx.emulator.Spectrum48()
        del mach


class test_derive(unittest.TestCase):
    def runTest(self):
        import zx.emulator
        class speccy(zx.emulator.Spectrum48):
            pass
        mach = speccy()
        del mach


class test_get_memory(unittest.TestCase):
    def runTest(self):
        import zx.emulator
        mach = zx.emulator.Spectrum48()
        mem = mach.get_memory()
        assert len(mem) == 0x10000
        assert mem[0] == 0x01, mem[0]
        mem[0] += 1
        assert mem[0] == 0x02, mem[0]


class test_render_frame(unittest.TestCase):
    def runTest(self):
        import zx.emulator
        mach = zx.emulator.Spectrum48()
        data = mach.render_frame()
        assert len(data) == 49280


class test_get_frame_pixels(unittest.TestCase):
    def runTest(self):
        import zx.emulator
        mach = zx.emulator.Spectrum48()
        mach.render_frame()
        pixels = mach.get_frame_pixels()
        assert len(pixels) == 394240


class test_execute_frame(unittest.TestCase):
    def runTest(self):
        import zx.emulator
        mach = zx.emulator.Spectrum48()

        mem = mach.get_memory()
        mem[0:2] = bytearray([0x18, 0x100 - 2])  # jr $

        mach.execute_frame()


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


if __name__ == '__main__':
    unittest.main()

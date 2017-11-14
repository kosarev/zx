# -*- coding: utf-8 -*-

import gc, unittest


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
        assert mem[0] == 0x01, mem[0]
        mem[0] += 1
        assert mem[0] == 0x02, mem[0]


class test_render_frame(unittest.TestCase):
    def runTest(self):
        import zx
        mach = zx.Spectrum48()
        data = mach.render_frame()
        assert len(data) == 49280


if __name__ == '__main__':
    unittest.main()

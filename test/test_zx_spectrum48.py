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


if __name__ == '__main__':
    unittest.main()

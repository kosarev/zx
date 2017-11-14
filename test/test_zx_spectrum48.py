# -*- coding: utf-8 -*-

import unittest


class test_create(unittest.TestCase):
    def runTest(self):
        import zx
        mach = zx.Spectrum48()


class test_derive(unittest.TestCase):
    def runTest(self):
        import zx
        class speccy(zx.Spectrum48):
            pass


if __name__ == '__main__':
    unittest.main()

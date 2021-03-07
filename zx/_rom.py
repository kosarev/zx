# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


import os
import pkg_resources

def _get_resource_path(path):
    return pkg_resources.resource_filename('zx', path)


def load_rom_image(filename):
    path = os.path.join('roms', filename)
    with open(_get_resource_path(path), mode='rb') as f:
        return f.read()

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


import io
import zipfile
import zx


class ZIPFileFormat(zx.ArchiveFileFormat):
    _NAME = 'ZIP'

    def read_files(self, image):
        file = io.BytesIO(image)
        with zipfile.ZipFile(file, 'r') as zf:
            for name in zf.namelist():
                with zf.open(name) as mf:
                    yield name, mf.read()

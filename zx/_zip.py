# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import typing
import io
import zipfile
import zx
from ._binary import Bytes
from ._data import ArchiveFileFormat


class ZIPFileFormat(ArchiveFileFormat, name='ZIP'):
    def read_files(self, image: Bytes) -> (
            typing.Iterable[tuple[str, Bytes]]):
        file = io.BytesIO(image)
        with zipfile.ZipFile(file, 'r') as zf:
            for name in zf.namelist():
                with zf.open(name) as mf:
                    yield name, mf.read()

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import os
import tempfile
from ._data import File
from ._data import FileFormat
from ._error import Error


class ZXBasicCompilerProgram(File):
    pass


class ZXBasicCompilerSourceFormat(FileFormat):
    _NAME = 'ZXB'

    def parse(self, filename, image):
        try:
            import zxb
        except ModuleNotFoundError:
            raise Error('The ZX Basic compiler does not seem to be installed.')

        fields = {}

        class Emitter(zxb.CodeEmitter):
            def emit(self, **args):
                fields.update(args)

        with tempfile.TemporaryDirectory() as dir:
            path = os.path.join(dir, filename)
            with open(path, 'wb') as f:
                f.write(image)

            status = zxb.main(args=[path], emitter=Emitter())
            if status:
                raise Error('ZX Basic compiler returned %d.' % status)

        fields['program_bytes'] = bytes(fields['program_bytes'])

        return ZXBasicCompilerProgram(ZXBasicCompilerSourceFormat, fields)

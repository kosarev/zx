# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import typing
import os
import tempfile
from ._binary import Bytes
from ._data import File
from ._data import FileFormat
from ._error import Error


class ZXBasicCompilerProgram(File):
    entry_point: int
    program_bytes: bytes


class ZXBasicCompilerSourceFormat(FileFormat, name='ZXB'):
    @classmethod
    def parse(cls, filename: str,
              image: Bytes) -> ZXBasicCompilerProgram:
        try:
            import zxb  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            raise Error('The ZX Basic compiler does not seem to be installed.')

        fields: dict[str, typing.Any] = {}

        assert 0  # TODO
        '''
        class Emitter(zxb.CodeEmitter):  # type: ignore[misc]
            def emit(self, **args: typing.Any) -> None:
                fields.update(args)

        with tempfile.TemporaryDirectory() as dir:
            path = os.path.join(dir, filename)
            with open(path, 'wb') as f:
                f.write(image)

            status = zxb.main(args=[path], emitter=Emitter())
            if status:
                raise Error('ZX Basic compiler returned %d.' % status)

        fields['program_bytes'] = bytes(fields['program_bytes'])
        '''

        return ZXBasicCompilerProgram(ZXBasicCompilerSourceFormat, **fields)

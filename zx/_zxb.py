#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import os
import tempfile
import typing

from ._binary import Bytes
from ._data import DataRecord
from ._error import Error


class ZXBasicCompilerProgram(DataRecord, format_name='ZXB'):
    entry_point: int
    program_bytes: bytes

    @classmethod
    def parse(cls, filename: str,
              image: Bytes) -> 'ZXBasicCompilerProgram':
        try:
            from src.zxbc import CodeEmitter  # type: ignore[attr-defined]
            from src.zxbc import main as zxb_main  # type: ignore[attr-defined]
        except ModuleNotFoundError:
            raise Error('The ZX Basic compiler does not seem to be installed.')

        fields: dict[str, typing.Any] = {}

        class Emitter(CodeEmitter):  # type: ignore[misc]
            def emit(self,
                     output_filename: str,
                     program_name: str,
                     loader_bytes: bytearray,
                     entry_point: typing.Any,
                     program_bytes: typing.Any,
                     aux_bin_blocks: typing.Any,
                     aux_headless_bin_blocks: typing.Any) -> None:
                fields['entry_point'] = entry_point
                fields['program_bytes'] = bytes(program_bytes)

        with tempfile.TemporaryDirectory() as dir:
            path = os.path.join(dir, filename)
            with open(path, 'wb') as f:
                f.write(image)

            status = zxb_main(args=[path], emitter=Emitter())
            if status:
                raise Error(f'ZX Basic compiler returned {status}.')

        return ZXBasicCompilerProgram(**fields)

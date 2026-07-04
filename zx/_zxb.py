#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

from __future__ import annotations

import pathlib
import tempfile
import typing

from ._data import DataRecord
from ._error import Error

if typing.TYPE_CHECKING:
    from ._binary import Bytes


class ZXBasicCompilerProgram(DataRecord, format_name='ZXB'):
    entry_point: int
    program_bytes: bytes

    @classmethod
    def decode(cls, filename: str,
               image: Bytes) -> ZXBasicCompilerProgram:
        try:
            # The ZX Basic compiler is optional and untyped; mypy is told
            # to treat src.zxbc as Any in .mypy.ini, so no per-line ignore
            # is needed here.
            from src.zxbc import CodeEmitter
            from src.zxbc import main as zxb_main
        except ModuleNotFoundError:
            raise Error(
                'The ZX Basic compiler does not seem to be installed.'
            ) from None

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
            path = pathlib.Path(dir) / filename
            with path.open('wb') as f:
                f.write(image)

            status = zxb_main(args=[str(path)], emitter=Emitter())
            if status:
                raise Error(f'ZX Basic compiler returned {status}.')

        return ZXBasicCompilerProgram(**fields)

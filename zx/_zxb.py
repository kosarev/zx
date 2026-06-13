#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import pathlib
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
            # The optional ZX Basic compiler has no type information, and
            # mypy reports a different error code for it depending on the
            # Python version and whether it is installed (attr-defined /
            # import-untyped / import-not-found), so a blanket ignore is
            # the only one correct everywhere. PGH003 is waived for this
            # file in .ruff.toml accordingly.
            from src.zxbc import CodeEmitter  # type: ignore
            from src.zxbc import main as zxb_main  # type: ignore
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

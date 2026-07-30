#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

from __future__ import annotations

import contextlib
import pathlib
import tempfile
import typing

from ._basic import StopAtBreakpoint
from ._basic import boot_to_prompt
from ._basic import capture_spectrum48
from ._data import ByteData
from ._data import HexData
from ._data import MachineSnapshot
from ._data import MachineSnapshotFile
from ._device import GetEmulationTime
from ._error import Error
from ._except import EmulationExit
from ._spectrum48 import Spectrum48
from ._time import Time

if typing.TYPE_CHECKING:
    from ._binary import Bytes


# A compiled program denotes a machine poised to execute it, so this
# file converts to a machine snapshot.
class ZXBasicCompilerProgram(MachineSnapshotFile, format_name='ZXB'):
    entry_point: int
    program_bytes: ByteData

    def __init__(self, *, entry_point: int,
                 program_bytes: Bytes | ByteData) -> None:
        super().__init__(entry_point=entry_point,
                         program_bytes=HexData.wrap(program_bytes))

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

    # Runs a private machine through the ROM boot and the BASIC
    # loading sequence, capturing at the program's entry point, so
    # the snapshot carries the genuine context a compiled program
    # may assume: the system variables, the interrupt mode, the USR
    # call frame.
    def to_machine_snapshot(self) -> MachineSnapshot:
        # The Emulator itself loads files, so file modules sit below
        # it in the import order and take it at conversion time.
        from ._emulator import Emulator

        machine = Spectrum48()
        with Emulator(machine=machine, headless=True,
                      extra_environment=[StopAtBreakpoint()]) as app:
            core = machine.core

            boot_to_prompt(app)

            # CLEAR <entry_point>
            app.generate_key_strokes('X', self.entry_point, 'ENTER')

            core.write(self.entry_point, self.program_bytes.data)
            core.set_breakpoint(self.entry_point)

            # RANDOMIZE USR <entry_point> -- the program may start,
            # ending the run, before the strokes run out.
            time = GetEmulationTime()
            app.notify(time)
            assert time.floor is not None
            deadline = time.floor + Time(10, ticks_per_second=1)
            with contextlib.suppress(EmulationExit):
                app.generate_key_strokes('T', 'CS+SS', 'L',
                                         self.entry_point, 'ENTER')
                app.run(until=deadline)

            if core.pc != self.entry_point:
                raise Error('The compiled program did not start.')

            return capture_spectrum48(core)

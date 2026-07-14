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

from ._core import Core
from ._core import RunEvents
from ._data import MachineSnapshot
from ._data import SnapshotFile
from ._device import Dispatcher
from ._error import Error
from ._keyboard import Keyboard
from ._keyboard import make_key_strokes
from ._machines import get_spectrum_48k_snapshot
from ._time import Time

if typing.TYPE_CHECKING:
    from ._binary import Bytes


# A compiled program denotes a machine poised to execute it, so this
# file converts to a machine snapshot.
class ZXBasicCompilerProgram(SnapshotFile, format_name='ZXB'):
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

    # Runs a private machine through the ROM boot and the BASIC
    # loading sequence, capturing at the program's entry point, so
    # the snapshot carries the genuine context a compiled program
    # may assume: the system variables, the interrupt mode, the USR
    # call frame.
    def to_machine_snapshot(self) -> MachineSnapshot:
        stock = get_spectrum_48k_snapshot()

        core = Core()
        core.install_snapshot(stock.core)
        keyboard = Keyboard(active=True)
        devices = Dispatcher([core, keyboard])

        hit_entry_point = False

        def run_step() -> RunEvents:
            nonlocal hit_entry_point
            events = RunEvents(core._run(devices))
            if RunEvents.BREAKPOINT_HIT in events:
                hit_entry_point = True
            return events

        def current_time() -> Time:
            return Time(core.tick_count,
                        ticks_per_second=core.model._TICKS_PER_FRAME * 50)

        def type_keys(*keys: int | str) -> None:
            strokes = make_key_strokes(*keys, start=current_time())
            for stroke in strokes:
                devices.notify(stroke)

            while not hit_entry_point and current_time() < strokes[-1].time:
                run_step()

        # Boot to the BASIC prompt.
        frames = 0
        while frames < 90:
            if RunEvents.END_OF_FRAME in run_step():
                frames += 1

        # CLEAR <entry_point>
        type_keys('X', self.entry_point, 'ENTER')

        core.write(self.entry_point, self.program_bytes)
        core.set_breakpoint(self.entry_point)

        # RANDOMIZE USR <entry_point>
        type_keys('T', 'CS+SS', 'L', self.entry_point, 'ENTER')

        for _ in range(500):
            if hit_entry_point:
                break
            run_step()
        else:
            raise Error('The compiled program did not start.')

        assert core.pc == self.entry_point
        return stock.updated(
            core=stock.core.updated(**dict(core.to_snapshot())))


import typing

import numpy
import numpy.typing

from ._device import Dispatcher

class _CoreBase:
    def _get_state_view(self) -> memoryview:
        ...

    def render_screen(self) -> None:
        ...

    def get_frame_pixels(self) -> memoryview:
        ...

    def drain_port_writes(self) -> bytes:
        ...

    def _get_deferred_port_read_tick(self) -> int | None:
        ...

    def _clear_port_read_samples(self) -> None:
        ...

    def _add_port_read_samples(
            self, core_resolution_tick: int, device_resolution: int,
            device_resolution_tick_remainder: int,
            addr_mask: int, addr_value: int, num_ticks: int,
            entries: numpy.typing.NDArray[numpy.uint64]) -> None:
        ...

    def mark_addrs(self, addr: int, size: int, marks: int) -> None:
        ...

    def set_on_input_callback(
            self,
            callback: typing.Callable[[int, Dispatcher], int | None]) -> (
            typing.Callable[[int, Dispatcher], int | None]):
        ...

    def set_on_output_callback(self,
                               callback: typing.Callable[[int, int],
                                                         None]) -> (
            typing.Callable[[int, int], None]):
        ...

    def _run(self, devices: Dispatcher) -> int:
        ...

    def _step_over_breakpoint(self, devices: Dispatcher) -> int:
        ...

    def on_handle_active_int(self) -> None:
        ...

    def _reset(self) -> None:
        ...

    def _reset_roms(self) -> None:
        ...

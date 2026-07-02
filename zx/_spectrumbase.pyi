
import typing

from ._device import Dispatcher

class _SpectrumBase:
    def _get_state_view(self) -> memoryview:
        ...

    def render_screen(self) -> None:
        ...

    def get_frame_pixels(self) -> memoryview:
        ...

    def drain_port_writes(self) -> bytes:
        ...

    def mark_addrs(self, addr: int, size: int, marks: int) -> None:
        ...

    def set_on_input_callback(
            self,
            callback: typing.Callable[[int, Dispatcher], int | None]) -> (
            typing.Callable[[int, Dispatcher], int | None]):
        ...

    def set_on_output_callback(self,
                               callback: typing.Callable[[int], None]) -> (
            typing.Callable[[int], None]):
        ...

    def _run(self, devices: Dispatcher) -> int:
        ...

    def on_handle_active_int(self) -> None:
        ...

    def on_reset(self) -> None:
        ...

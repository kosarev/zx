
import typing

class _Spectrum48Base:
    def _get_state_view(self) -> memoryview:
        ...

    def render_screen(self) -> None:
        ...

    def get_frame_pixels(self) -> memoryview:
        ...

    def get_port_writes(self) -> memoryview:
        ...

    def mark_addrs(self, addr: int, size: int, marks: int) -> None:
        ...

    def set_on_input_callback(self, callback: typing.Callable[[int], int]) -> (
            typing.Callable[[int], int]):
        ...

    def set_on_output_callback(self,
                               callback: typing.Callable[[int], None]) -> (
            typing.Callable[[int], None]):
        ...

    def _run(self) -> int:
        ...

    def on_handle_active_int(self) -> None:
        ...

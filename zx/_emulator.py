#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import pathlib
import types
import typing

from ._beeper import Beeper
from ._data import MachinePlayback
from ._data import MachineSnapshot
from ._data import SoundFile
from ._data import SpectrumModel
from ._device import DestroyEmulator
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import GetEmulationTime
from ._device import GetHoldState
from ._device import InitEmulator
from ._device import IsTapePlayerPaused
from ._device import IsTapePlayerStopped
from ._device import KeyStroke
from ._device import LoadFile
from ._device import LoadTape
from ._device import PauseUnpauseTape
from ._device import ResetEmulator
from ._device import RunQuantum
from ._device import SaveSnapshot
from ._device import SetFastForward
from ._device import StartPlayback
from ._device import ToggleTapePause
from ._error import Error
from ._file import parse_file
from ._keyboard import KEYS
from ._keyboard import Keyboard
from ._playback import PlaybackPlayer
from ._playback import PlaybackRecorder
from ._screen import ScreenWindow
from ._sound import SDLSound
from ._spectrum import Profile
from ._spectrum import Spectrum
from ._tape import TapePlayer
from ._z80snapshot import Z80Snapshot
from ._zxb import ZXBasicCompilerProgram


# A Dispatcher that also lets the Emulator act on owner events
# (LoadFile etc.) raised by a device.
class _OwnerDispatcher(Dispatcher):
    def __init__(self, devices: list[Device], emulator: 'Emulator') -> None:
        super().__init__(devices)
        self.__emulator = emulator

    def notify(self, event: DeviceEvent) -> None:
        super().notify(event)

        emulator = self.__emulator
        if isinstance(event, LoadFile):
            emulator._load_file(event.filename)
        elif isinstance(event, SaveSnapshot):
            emulator._save_snapshot_file(Z80Snapshot, event.filename)
        elif isinstance(event, ToggleTapePause):
            emulator._toggle_tape_pause()


# The top-level container: owns the device set, the run loop and the
# lifecycle, and assumes no single CPU/core. Not a dispatcher itself --
# it makes a temporary Dispatcher over its devices to dispatch.
class Emulator:
    """The emulator: a container of devices driven by a run loop.

    Construct one - optionally headless (no window or sound) or for a
    specific model - then load a snapshot or tape and run it. It is a
    context manager and releases its resources on exit.
    """

    def __init__(self, *,
                 model: type[SpectrumModel] | None = None,
                 core: Spectrum | None = None,
                 screen: Device | None = None,
                 keyboard: Device | None = None,
                 beeper: Device | None = None,
                 sound_device: Device | None = None,
                 headless: bool = False,
                 devices: list[Device] | None = None,
                 playback_player: PlaybackPlayer | None = None,
                 playback_recorder: PlaybackRecorder | None = None,
                 extra_devices: list[Device] | None = None,
                 profile: Profile | None = None):
        if devices is None:
            if core is None:
                core = Spectrum(model=model, profile=profile)
            model = core.model

            if keyboard is None:
                keyboard = Keyboard()
            if beeper is None:
                beeper = Beeper(model)

            devices = [core, TapePlayer(model), keyboard, beeper,
                       playback_player or PlaybackPlayer(),
                       playback_recorder or PlaybackRecorder()]

            if not headless:
                if screen is None:
                    screen = ScreenWindow(core.FRAME_SIZE)
                if sound_device is None:
                    sound_device = SDLSound(model)

                devices.extend([screen, sound_device])

            # The caller's extra devices come last -- typically the
            # end-user tool layer adding environment-coupling agents
            # (e.g. a settings-persistence manager), kept out of the
            # default set so an API- or test-built emulator stays
            # hermetic.
            if extra_devices is not None:
                devices.extend(extra_devices)
        elif core is None:
            core = next((d for d in devices if isinstance(d, Spectrum)), None)

        self.__core = core
        self.devices = list(devices)

    # The orchestration drives a single core (the common case); a device
    # set without one cannot be run or loaded into.
    def __require_core(self) -> Spectrum:
        assert self.__core is not None, (
            'this device set has no core to run or load into')
        return self.__core

    def __enter__(self) -> 'Emulator':
        self.notify(InitEmulator())
        return self

    def __exit__(self, xtype: None | type[BaseException],
                 value: None | BaseException,
                 traceback: None | types.TracebackType) -> None:
        self.notify(DestroyEmulator())

    def run(self, duration: None | float = None,
            fast_forward: bool = False) -> None:
        end_time = None
        if duration is not None:
            end_time = self.__emulation_time() + duration

        if fast_forward:
            self.notify(SetFastForward(True))
        try:
            while end_time is None or self.__emulation_time() < end_time:
                self.__run_quantum()
        finally:
            if fast_forward:
                self.notify(SetFastForward(False))

    # One iteration of the run loop: evaluate the hold once and broadcast
    # it (so devices never re-query), and unless held, advance the core
    # by a quantum. The broadcast is unconditional -- every device sees
    # RunQuantum each iteration, held or not; the held check only skips
    # advancing the core.
    # TODO: With more than one core this advances each of them; for now
    # there is a single core.
    def __run_quantum(self) -> None:
        hold = GetHoldState()
        self.notify(hold)

        self.notify(RunQuantum(held=hold.held, wake_in=hold.wake_in))

        if hold.held:
            return

        dispatcher = _OwnerDispatcher(self.devices, self)
        self.__require_core().run_quantum(dispatcher)

    def __emulation_time(self) -> float:
        event = GetEmulationTime()
        self.notify(event)
        return event.time.get()

    def reset(self) -> None:
        self.notify(ResetEmulator())

    def reset_and_wait(self) -> None:
        self.__require_core().pc = 0x0000
        self.run(duration=1.8, fast_forward=True)

    def __translate_key_strokes(self, keys: typing.Iterable[int | str]) -> (
            typing.Iterator[str]):
        for key in keys:
            if isinstance(key, int):
                yield from str(key)
            else:
                yield key

    def generate_key_strokes(self, *keys: int | str) -> None:
        for key in self.__translate_key_strokes(keys):
            strokes = key.split('+')

            for id in strokes:
                self.notify(KeyStroke(KEYS[id].ID, pressed=True))
                self.run(duration=0.1, fast_forward=True)

            for id in reversed(strokes):
                self.notify(KeyStroke(KEYS[id].ID, pressed=False))
                self.run(duration=0.1, fast_forward=True)

    def _is_tape_paused(self) -> bool:
        tape_state = IsTapePlayerPaused()
        self.notify(tape_state)
        return tape_state.paused

    def __pause_tape(self, is_paused: bool = True) -> None:
        self.notify(PauseUnpauseTape(is_paused))

    def __unpause_tape(self) -> None:
        self.__pause_tape(is_paused=False)

    def _toggle_tape_pause(self) -> None:
        self.__pause_tape(not self._is_tape_paused())

    def __load_tape_to_player(self, file: SoundFile) -> None:
        self.notify(LoadTape(file))
        self.__pause_tape()

    def __is_end_of_tape(self) -> bool:
        tape_state = IsTapePlayerStopped()
        self.notify(tape_state)
        return tape_state.stopped

    def load_tape(self, filename: str) -> None:
        tape = parse_file(filename)
        if not isinstance(tape, SoundFile):
            raise Error(f'{filename!r} does not seem to be a tape file.')

        # Let the initialization complete.
        self.reset_and_wait()

        # Type in 'LOAD ""'.
        self.generate_key_strokes('J', 'SS+P', 'SS+P', 'ENTER')

        # Load and run the tape.
        self.__load_tape_to_player(tape)
        self.__unpause_tape()

        # Run until the player reports the tape finished; the player
        # raises StopQuantum at the exact end, so each quantum stops
        # there and this check sees it promptly.
        self.notify(SetFastForward(True))
        try:
            while not self.__is_end_of_tape():
                self.__run_quantum()
        finally:
            self.notify(SetFastForward(False))

    def _load_input_recording(self, file: MachinePlayback) -> None:
        self.notify(StartPlayback(file.to_unified_playback()))

    def __load_zx_basic_compiler_program(
            self, file: ZXBasicCompilerProgram) -> None:
        self.reset_and_wait()

        # CLEAR <entry_point>
        entry_point = file.entry_point
        self.generate_key_strokes('X', entry_point, 'ENTER')

        self.__require_core().write(entry_point, file.program_bytes)

        # RANDOMIZE USR <entry_point>
        self.generate_key_strokes('T', 'CS+SS', 'L', entry_point, 'ENTER')

    def _load_file(self, filename: str) -> None:
        file = parse_file(filename)

        self.notify(ResetEmulator())

        if isinstance(file, MachineSnapshot):
            self.__require_core().install_snapshot(file)
        elif isinstance(file, MachinePlayback):
            self._load_input_recording(file)
        elif isinstance(file, SoundFile):
            self.__load_tape_to_player(file)
        elif isinstance(file, ZXBasicCompilerProgram):
            self.__load_zx_basic_compiler_program(file)
        else:
            raise Error(f"Don't know how to load file {filename!r}.")

    def _run_file(self, filename: str, *, fast_forward: bool = False) -> None:
        self._load_file(filename)
        self.run(fast_forward=fast_forward)

    def _save_snapshot_file(self, format: type[MachineSnapshot],
                            filename: str) -> None:
        with pathlib.Path(filename).open('wb') as f:
            f.write(format.from_snapshot(
                self.__require_core().to_snapshot()).encode())

    def notify(self, event: DeviceEvent) -> None:
        dispatcher = _OwnerDispatcher(self.devices, self)
        dispatcher.notify(event)

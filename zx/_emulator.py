#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

"""An emulator is a flat set of devices exchanging events on one bus.

Devices are independent peers. No device calls another; a device
reacts to events and radiates facts. Every fact carries what it needs
to be understood on its own -- its time, its resolution, its source.

Devices have one of two roles. A machine device is a constituent of
an emulated machine -- the box itself -- and is reconstructed from
the machine's saved state on load. An environment device is part of
the machine's surroundings: emulated equipment on the desk (a tape
player, an input recorder) or a channel of the real host (a window,
the sound output). Environment devices are carried over across
loads. The sides differ in membership and lifecycle, not in
emulatedness: emulated environment equipment lives on the exact
time axis just as the machine does.

A machine is a named group of machine devices sharing one bus scope
-- one address space, one set of port lines. Gather events (a port
read) are answered within their machine; the event space stays
flat, so a device may observe across machines (a lock-step
comparator), and one emulator may hold several machines (#38).

Devices radiate streams -- video, sound, tape signal, presentable
state. Environment devices connect streams to the machines and the
real host: presenting or consuming them (a window, the sound
output) or originating them (a tape player feeding the tape signal,
a line-in capture). Which device serves which stream, and how, is
environment configuration. A second window is a new channel, not a
new machine.

Time is one shared axis of exact points. Devices advance in rounds
toward an absolute time limit, each by its own decision, stopping at
its own natural boundaries; the floor -- the time every device has
crossed -- is the only global clock fact. Wallclock never mixes with
emulated time; pacing lives in the channels.

State is three artefacts: a machine's state (the content, as
differences from the canonical reset state), the environment
configuration (equipment, channels, subscriptions, preferences),
and the session -- their composition, plus history. Loading a
machine state rebuilds its machine devices under an untouched
environment (#40). Machine state reproduces the machine; with the
environment configuration it reproduces the whole session;
non-determinism enters only through live channels of the real host.

The Emulator is the composition root: it owns the set, runs the round
loop, and answers questions about the whole -- nothing else. It is
not a device, and it never nests.
"""

import pathlib
import types

from ._beeper import Beeper
from ._core import Core
from ._core import Profile
from ._data import MachinePlayback
from ._data import MachineSnapshot
from ._data import SoundFile
from ._data import SpectrumModel
from ._data import UnifiedSnapshot
from ._device import DestroyEmulator
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import GetEmulationTime
from ._device import GetHoldState
from ._device import GetQuantumTimeLimit
from ._device import InitEmulator
from ._device import IsTapePlayerPaused
from ._device import IsTapePlayerStopped
from ._device import LoadFile
from ._device import LoadTape
from ._device import PauseUnpauseTape
from ._device import ResetEmulator
from ._device import RunQuantum
from ._device import SaveSnapshot
from ._device import SetFastForward
from ._device import StartPlayback
from ._device import TimeAdvanced
from ._device import ToggleTapePause
from ._error import Error
from ._file import parse_file
from ._keyboard import Keyboard
from ._keyboard import make_key_strokes
from ._playback import PlaybackPlayer
from ._playback import PlaybackRecorder
from ._screen import ScreenWindow
from ._sound import SDLSound
from ._tape import TapePlayer
from ._time import Time
from ._z80snapshot import Z80Snapshot
from ._zxb import ZXBasicCompilerProgram


# A Dispatcher that also passes every event to the Emulator, after
# all the devices have seen it.
class _EmulatorDispatcher(Dispatcher):
    def __init__(self, devices: list[Device], emulator: 'Emulator') -> None:
        super().__init__(devices)
        self.__emulator = emulator

    def notify(self, event: DeviceEvent) -> None:
        super().notify(event)
        self.__emulator._on_event(event)


class Emulator:
    """Owns the machine and environment devices and runs them. It is a
    context manager that releases its resources on exit.

    The devices are independent peers, unaware of the Emulator or each
    other, and communicate only by sending events to a Dispatcher, which
    passes each event to every device. The Emulator makes a Dispatcher for
    each operation and then drops it. This is also where it acts on events
    that ask it to do something, such as LoadFile asking it to load a file.
    """

    def __init__(self, *,
                 model: type[SpectrumModel] | None = None,
                 core: Core | None = None,
                 screen: Device | None = None,
                 keyboard: Device | None = None,
                 beeper: Device | None = None,
                 sound_device: Device | None = None,
                 playback_player: PlaybackPlayer | None = None,
                 playback_recorder: PlaybackRecorder | None = None,
                 profile: Profile | None = None,
                 headless: bool = False,
                 machine: list[Device] | None = None,
                 environment: list[Device] | None = None,
                 extra_environment: list[Device] | None = None):
        if machine is None:
            if core is None:
                core = Core(model=model, profile=profile)

            if keyboard is None:
                keyboard = Keyboard()
            if beeper is None:
                beeper = Beeper()

            machine = [core, keyboard, beeper]
        elif core is None:
            core = next((d for d in machine if isinstance(d, Core)), None)

        if environment is None:
            environment = [TapePlayer(),
                           playback_player or PlaybackPlayer(),
                           playback_recorder or PlaybackRecorder()]
            if not headless:
                if screen is None:
                    screen = ScreenWindow(Core.FRAME_SIZE)
                if sound_device is None:
                    sound_device = SDLSound()

                environment.extend([screen, sound_device])

        # The caller's extra environment devices come last --
        # typically the end-user tool layer adding host-coupling
        # agents (e.g. a settings-persistence manager), kept out of
        # the default set so an API- or test-built emulator stays
        # hermetic.
        environment = list(environment)
        if extra_environment is not None:
            environment.extend(extra_environment)

        self.__core = core
        self.machine = list(machine)
        self.environment = environment

        # The time all devices have advanced to, and the earliest
        # time none has reached yet.
        self.__advanced_floor = Time(0, ticks_per_second=1)
        self.__advanced_ceiling = Time(0, ticks_per_second=1)

    # All the devices, the machine first, as one dispatch audience.
    @property
    def devices(self) -> list[Device]:
        return self.machine + self.environment

    # The orchestration drives a single core (the common case); a device
    # set without one cannot be run or loaded into.
    def __require_core(self) -> Core:
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

    # Runs for the given duration in emulated seconds, or until the
    # floor reaches the given time, or indefinitely.
    def run(self, duration: None | float = None,
            fast_forward: bool = False,
            until: None | Time = None) -> None:
        assert duration is None or until is None

        end_time = None
        if duration is not None:
            end_time = self.__emulation_time() + duration

        if fast_forward:
            self.notify(SetFastForward(True))
        try:
            while ((end_time is None or
                    self.__emulation_time() < end_time) and
                   (until is None or self.__advanced_floor < until)):
                self.__run_quantum()
        finally:
            if fast_forward:
                self.notify(SetFastForward(False))

    # One round of the run loop: evaluate the hold once and broadcast
    # RunQuantum -- every device sees it each round, held or not.
    # When held the round is bookkeeping only; otherwise the round's
    # time limit rides on the event and devices advance on it, each
    # budgeting from its own position in time.
    # TODO: Handle deferred port reads (RETRY_INPUT) by retrying; add
    # converge-to-T rollback; drive more than one core.
    def __run_quantum(self) -> None:
        hold = GetHoldState()
        self.notify(hold)

        if hold.held:
            self.notify(RunQuantum(held=True, wake_in=hold.wake_in))
            return

        # Ask by what time this round should stop.
        limit = GetQuantumTimeLimit()
        self.notify(limit)

        run = RunQuantum(wake_in=hold.wake_in,
                         stop_after=limit.stop_after_time)
        self.notify(run)
        assert run.advanced_floor is not None
        self.__advanced_floor = run.advanced_floor
        assert run.advanced_ceiling is not None
        self.__advanced_ceiling = run.advanced_ceiling

        # TimeAdvanced goes last: all facts about the elapsed span
        # of time are published by the time its dispatch completes.
        self.notify(TimeAdvanced(run.advanced_floor))

    # Handles the events that concern the Emulator itself, after all
    # the devices have seen them.
    def _on_event(self, event: DeviceEvent) -> None:
        if isinstance(event, GetEmulationTime):
            # Reflects facts about the whole set: the time all
            # devices have advanced to and the earliest time none
            # has reached yet.
            event.floor = self.__advanced_floor
            event.ceiling = self.__advanced_ceiling
        elif isinstance(event, LoadFile):
            self._load_file(event.filename)
        elif isinstance(event, SaveSnapshot):
            self._save_snapshot_file(Z80Snapshot, event.filename)
        elif isinstance(event, ToggleTapePause):
            self._toggle_tape_pause()

    def __emulation_time(self) -> float:
        event = GetEmulationTime()
        self.notify(event)
        assert event.floor is not None
        return event.floor.to_float_seconds()

    def reset(self) -> None:
        self.notify(ResetEmulator())

    def reset_and_wait(self) -> None:
        self.__require_core().pc = 0x0000
        self.run(duration=1.8, fast_forward=True)

    def generate_key_strokes(self, *keys: int | str) -> None:
        # The sequence starts at the earliest time no device has
        # reached yet, then the machine runs past its end.
        strokes = make_key_strokes(*keys, start=self.__advanced_ceiling)
        for stroke in strokes:
            self.notify(stroke)

        if strokes:
            self.run(until=strokes[-1].time, fast_forward=True)

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

    # Builds machine devices from a machine snapshot: one device per
    # slice, plus a default device of every machine member type the
    # snapshot does not mention -- at its canonical reset state, per
    # the reset-delta principle.
    def __make_machine(self, snapshot: MachineSnapshot) -> list[Device]:
        devices = [Device.from_snapshot(device_snapshot)
                   for _, device_snapshot in snapshot.to_unified_snapshot()]

        for member in Core, Keyboard, Beeper:
            if not any(isinstance(d, member) for d in devices):
                devices.append(member())

        return devices

    # Loading a machine state recreates the machine devices; the
    # environment persists. The new machine starts its own timeline.
    def _load_snapshot(self, snapshot: MachineSnapshot) -> None:
        self.notify(ResetEmulator())

        self.machine = self.__make_machine(snapshot)
        self.__core = next(
            (d for d in self.machine if isinstance(d, Core)), None)
        self.__advanced_floor = Time(0, ticks_per_second=1)
        self.__advanced_ceiling = Time(0, ticks_per_second=1)

    def _load_file(self, filename: str) -> None:
        file = parse_file(filename)

        if isinstance(file, MachineSnapshot):
            self._load_snapshot(file)
            return

        self.notify(ResetEmulator())

        if isinstance(file, MachinePlayback):
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

    # The machine's state: a slice per machine device that has state
    # to capture, keyed by device id -- the type name in lower case.
    def __make_machine_snapshot(self) -> UnifiedSnapshot:
        return UnifiedSnapshot(**{
            type(d).__name__.lower(): snapshot
            for d in self.machine
            if (snapshot := d.to_snapshot()) is not None})

    def _save_snapshot_file(self, format: type[MachineSnapshot],
                            filename: str) -> None:
        with pathlib.Path(filename).open('wb') as f:
            f.write(format.from_snapshot(
                self.__make_machine_snapshot()).encode())

    def notify(self, event: DeviceEvent) -> None:
        dispatcher = _EmulatorDispatcher(self.devices, self)
        dispatcher.notify(event)

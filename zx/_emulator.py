# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import types
import typing

from ._beeper import Beeper
from ._data import SpectrumModel
from ._device import DestroyEmulator
from ._device import Device
from ._device import Dispatcher
from ._device import GetEmulationTime
from ._device import GetHoldState
from ._device import InitEmulator
from ._device import RunQuantum
from ._device import SetFastForward
from ._keyboard import Keyboard
from ._playback import PlaybackPlayer
from ._playback import PlaybackRecorder
from ._screen import ScreenWindow
from ._sound import SDLSound
from ._spectrum import Profile
from ._spectrum import Spectrum
from ._tape import TapePlayer


# The top-level container: it IS the dispatcher through which devices
# reach each other, and it owns the device set, the run loop and the
# lifecycle. It makes no assumption that there is exactly one CPU/core
# -- it just holds a set of devices, one or more of which may be a
# Spectrum (or a core of another kind).
#
# A device is handed this object as the `devices` parameter of on_event,
# but typed there as a plain Dispatcher, so its own code can only use the
# Dispatcher interface; and it never finds the Emulator among the
# iterated devices (the Emulator is not in its own device list). So a
# device cannot accidentally reach up and orchestrate the container --
# only a deliberate defiance of the declared type could, which is no
# different from any encapsulation in Python.
class Emulator(Dispatcher):
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

        self.__dispatcher = Dispatcher(devices)

        # The core needs the live dispatcher for its run loop and its
        # C-side callbacks (port reads, breakpoints); a device may hold
        # the dispatcher it is part of.
        if self.__core is not None:
            self.__core.devices = self.__dispatcher

    @property
    def devices(self) -> Dispatcher:
        return self.__dispatcher

    # TODO: This accessor exists only because the run loop and
    # orchestration are temporarily delegated to a single Spectrum core;
    # it goes away once they move into the Emulator.
    def __require_core(self) -> Spectrum:
        assert self.__core is not None, (
            'orchestration is delegated to a Spectrum core, but this '
            'device set has none')
        return self.__core

    def __enter__(self) -> 'Emulator':
        self.__dispatcher.notify(InitEmulator())
        return self

    def __exit__(self, xtype: None | type[BaseException],
                 value: None | BaseException,
                 traceback: None | types.TracebackType) -> None:
        self.__dispatcher.notify(DestroyEmulator())

    def run(self, duration: None | float = None,
            fast_forward: bool = False) -> None:
        end_time = None
        if duration is not None:
            end_time = self.__emulation_time() + duration

        if fast_forward:
            self.__dispatcher.notify(SetFastForward(True))
        try:
            while end_time is None or self.__emulation_time() < end_time:
                self.__run_quantum()
        finally:
            if fast_forward:
                self.__dispatcher.notify(SetFastForward(False))

    # One iteration of the run loop: evaluate the hold once and broadcast
    # it (so devices never re-query), and unless held, advance the core
    # by a quantum. The broadcast is unconditional -- every device sees
    # RunQuantum each iteration, held or not; the held check only skips
    # advancing the core.
    # TODO: With more than one core this advances each of them; for now
    # there is a single core.
    def __run_quantum(self) -> None:
        hold = GetHoldState()
        self.__dispatcher.notify(hold)

        self.__dispatcher.notify(RunQuantum(held=hold.held,
                                            wake_in=hold.wake_in))

        if hold.held:
            return

        self.__require_core().run_quantum(self.__dispatcher)

    def __emulation_time(self) -> float:
        event = GetEmulationTime()
        self.__dispatcher.notify(event)
        return event.time.get()

    # TODO: The orchestration below still lives on the core and is
    # delegated to here; it moves into the Emulator in later steps of
    # the split.
    def reset(self) -> None:
        self.__require_core().reset()

    def reset_and_wait(self) -> None:
        self.__require_core().reset_and_wait()

    def generate_key_strokes(self, *keys: int | str) -> None:
        self.__require_core().generate_key_strokes(*keys)

    def load_tape(self, filename: str) -> None:
        self.__require_core().load_tape(filename)

    def _load_file(self, filename: str) -> None:
        self.__require_core()._load_file(filename)

    def _run_file(self, filename: str, *, fast_forward: bool = False) -> None:
        self.__require_core()._run_file(filename, fast_forward=fast_forward)

    def _load_input_recording(self, playback: typing.Any) -> None:
        self.__require_core()._load_input_recording(playback)

    def _save_snapshot_file(self, format: typing.Any, filename: str) -> None:
        self.__require_core()._save_snapshot_file(format, filename)

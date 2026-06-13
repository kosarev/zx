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
from ._device import InitEmulator
from ._keyboard import Keyboard
from ._playback import PlaybackPlayer
from ._playback import PlaybackRecorder
from ._screen import ScreenWindow
from ._sound import SDLSound
from ._spectrum import Profile
from ._spectrum import Spectrum
from ._tape import TapePlayer


# The top-level container: it owns the device set, the dispatcher
# through which devices reach each other, and the lifecycle. It makes
# no assumption that there is exactly one CPU/core -- it just holds a
# set of devices, one or more of which may be a Spectrum (or a core of
# another kind). Devices are handed the Dispatcher, never the Emulator,
# so a device structurally cannot reach up and orchestrate the
# container.
class Emulator(object):
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

    # TODO: The run loop and orchestration still live on the core and
    # are delegated to here; they move into the Emulator in later steps
    # of the split (the run loop becoming the RunQuantum broadcast each
    # core answers).
    def run(self, duration: None | float = None,
            fast_forward: bool = False) -> None:
        self.__require_core().run(duration=duration, fast_forward=fast_forward)

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

    @property
    def paused(self) -> bool:
        return self.__require_core().paused

    @paused.setter
    def paused(self, value: bool) -> None:
        self.__require_core().paused = value

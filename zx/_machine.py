#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from __future__ import annotations

import typing

from ._beeper import Beeper
from ._core import Core
from ._core import Profile
from ._keyboard import Keyboard
from ._spectrum48 import Spectrum48Snapshot

if typing.TYPE_CHECKING:
    from ._data import MachineSnapshotFile
    from ._data import SpectrumModel
    from ._device import Device


# Marks device parameters where no device is given, telling 'use the
# default device' (DEFAULT) from 'no device' (None).
class Default:
    pass


DEFAULT = Default()


# The machine's devices, keyed by their ids -- the same ids that key
# the device snapshots of machine snapshot compositions. The standard
# members default to constructed devices, so a bare Machine() is the
# standard Spectrum machine; None means the machine has no such
# member.
class Machine:
    def __init__(self, core: Device | Default | None = DEFAULT,
                 keyboard: Device | Default | None = DEFAULT,
                 beeper: Device | Default | None = DEFAULT,
                 model: type[SpectrumModel] | None = None,
                 profile: Profile | None = None,
                 snapshot: MachineSnapshotFile | Default | None = DEFAULT,
                 **extra_devices: Device) -> None:
        if isinstance(core, Default):
            core = Core(model=model, profile=profile)
        else:
            # The model and profile parameterise the default core.
            assert model is None and profile is None

        # The machine's state defaults to the stock 48K snapshot;
        # None means nothing to install, the reset state.
        # TODO: Find a way to install snapshots using Machine, maybe
        # via its own on_event(), and drop this field.
        if isinstance(snapshot, Default):
            snapshot = Spectrum48Snapshot()
        self._snapshot = snapshot
        if isinstance(keyboard, Default):
            keyboard = Keyboard()
        if isinstance(beeper, Default):
            beeper = Beeper()

        devices = {'core': core, 'keyboard': keyboard, 'beeper': beeper}
        devices.update(extra_devices)

        self.devices: dict[str, Device] = {
            device_id: device for device_id, device in devices.items()
            if device is not None}

    # A machine of exactly the given devices, no standard members
    # implied -- for rigs such as the AY-only player machine. Standard
    # members the caller does not give are stated to be None, as is
    # the snapshot unless one is given.
    @classmethod
    def bare(cls, snapshot: MachineSnapshotFile | None = None,
             **devices: Device) -> Machine:
        return cls(core=devices.pop('core', None),
                   keyboard=devices.pop('keyboard', None),
                   beeper=devices.pop('beeper', None),
                   model=None, profile=None, snapshot=snapshot,
                   **devices)

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from __future__ import annotations

import typing

from ._device import Dispatcher
from ._device import InstallDeviceSnapshot
from ._error import Error

if typing.TYPE_CHECKING:
    from ._data import MachineSnapshotFile
    from ._device import Device


# The machine's devices, keyed by their ids -- the same ids that key
# the device snapshots of machine snapshot compositions. Every
# machine is an instance of a machine class (Spectrum48,
# AY8910Machine) that fixes its snapshot type and constructs its
# standard members; Machine is the base carrying the machinery.
#
# Creating a machine and installing a snapshot are distinct
# operations: construction defines the set, and any state arrives
# by an install into the constructed machine.
class Machine:
    # The type of the machine's snapshots.
    SNAPSHOT_TYPE: typing.ClassVar[type[MachineSnapshotFile] | None] = None

    # A machine class and its snapshot type pair one-to-one: the
    # snapshot type is the machine's persisted identity, so every
    # machine class states its own.
    def __init_subclass__(
            cls, *,
            snapshot_type: type[MachineSnapshotFile]) -> None:
        cls.SNAPSHOT_TYPE = snapshot_type

    def __init__(self, **devices: Device) -> None:
        if self.SNAPSHOT_TYPE is None:
            raise TypeError(
                'Machine is a base class; construct a machine class '
                'such as Spectrum48')

        self.devices: dict[str, Device] = dict(devices)

        # Every device is also a field named by its id, so
        # machine.core is machine.devices['core']. The machine
        # classes declare the types of their fixed members.
        for id, device in self.devices.items():
            if id in dir(self):
                raise ValueError(
                    f'device id {id!r} clashes with an existing attribute')
            setattr(self, id, device)

        # A machine constructs at its canonical state: the class's
        # empty stock snapshot, installed locally -- the definition
        # realised, not observable history, so no event radiates
        # beyond the machine's own devices.
        self._install_snapshot(self.SNAPSHOT_TYPE())

    # Installing a machine snapshot means every mentioned device
    # assumes exactly the state its device snapshot describes.
    # Devices the snapshot does not mention keep their state:
    # formats are mute about devices such as the tape player, and
    # muteness is not a statement, so a .z80 load must not touch the
    # mounted tape.
    def _install_snapshot(self, snapshot: MachineSnapshotFile) -> None:
        device_snapshots = dict(snapshot.to_machine_snapshot())

        # A device snapshot addressing no machine device is an
        # error.
        for id in device_snapshots:
            if id not in self.devices:
                raise Error(
                    f"The snapshot addresses a device '{id}' that is "
                    f'not in the machine.',
                    id='unknown_device_in_snapshot')

        dispatcher = Dispatcher(devices_by_id=self.devices)
        for id, device_snapshot in device_snapshots.items():
            dispatcher.notify(InstallDeviceSnapshot(device_snapshot),
                              device=id)

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from ._data import MachineSnapshotFile
    from ._device import Device


# The machine's devices, keyed by their ids -- the same ids that key
# the device snapshots of machine snapshot compositions. A plain
# Machine is a machine of exactly the given devices -- the form for
# rigs such as the AY-only player machine. The model classes
# (Spectrum48, Spectrum128) fix their snapshot types, construct
# their standard members and default their states to the stock
# snapshots.
class Machine:
    # The type of the machine's snapshots; None where the machine
    # type does not fix one.
    SNAPSHOT_TYPE: typing.ClassVar[type[MachineSnapshotFile] | None] = None

    def __init_subclass__(
            cls, *,
            snapshot_type: type[MachineSnapshotFile] | None = None) -> None:
        if snapshot_type is not None:
            cls.SNAPSHOT_TYPE = snapshot_type

    def __init__(self, snapshot: MachineSnapshotFile | None = None,
                 **devices: Device) -> None:
        # The machine's state to install; None means nothing to
        # install, the reset state.
        # TODO: Find a way to install snapshots using Machine, maybe
        # via its own on_event(), and drop this field.
        self._snapshot = snapshot

        self.devices: dict[str, Device] = dict(devices)

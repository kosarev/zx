#!/usr/bin/env python3

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

from __future__ import annotations

# TODO: Remove unused imports.
import enum
import itertools
import typing

import numpy

if typing.TYPE_CHECKING:
    from ._binary import Bytes

from ._corebase import _CoreBase
from ._data import ByteData
from ._data import DataRecord
from ._data import DeviceSnapshot
from ._data import HexData
from ._data import MachinePlayback
from ._device import BreakpointHit
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import EndOfFrame
from ._device import FetchesLimitHit
from ._device import GetEmulationPauseState
from ._device import GetFramePixels
from ._device import GetHoldState
from ._device import InstallDeviceSnapshot
from ._device import NewPortReads
from ._device import NewPortWrites
from ._device import OutputFrame
from ._device import PauseStateUpdated
from ._device import ResetEmulator
from ._device import RunQuantum
from ._device import SetBreakpoint
from ._device import SetFetchesLimit
from ._device import StartPlayback
from ._device import StopPlayback
from ._device import StopQuantum
from ._device import ToggleEmulationPause
from ._except import EmulationExit
from ._keyboard import KeyStroke
from ._time import Time


# Mirrors the composed events mask of the machine in zx.h: the z80
# library's executor claims the low bits, our extension follows.
class RunEvents(enum.IntFlag):
    NO_EVENTS = 0
    BREAKPOINT_HIT = 1 << 0
    RETRY_INPUT = 1 << 1
    END_OF_FRAME = 1 << 2
    TICKS_LIMIT_HIT = 1 << 3
    FETCHES_LIMIT_HIT = 1 << 4
    STOP_REQUESTED = 1 << 5


# The Z80 chip's state. Null fields mean the canonical reset values.
class Z80Snapshot(DataRecord):
    af: int | None
    bc: int | None
    de: int | None
    hl: int | None
    ix: int | None
    iy: int | None
    alt_af: int | None
    alt_bc: int | None
    alt_de: int | None
    alt_hl: int | None
    pc: int | None
    sp: int | None
    ir: int | None
    wz: int | None
    iregp_kind: str | None
    iff1: int | None
    iff2: int | None
    int_mode: int | None

    def __init__(
            self, *,
            af: int | None = None,
            bc: int | None = None,
            de: int | None = None,
            hl: int | None = None,
            ix: int | None = None,
            iy: int | None = None,
            alt_af: int | None = None,
            alt_bc: int | None = None,
            alt_de: int | None = None,
            alt_hl: int | None = None,
            pc: int | None = None,
            sp: int | None = None,
            ir: int | None = None,
            wz: int | None = None,
            iregp_kind: str | None = None,
            iff1: int | None = None,
            iff2: int | None = None,
            int_mode: int | None = None):
        super().__init__(
            af=af, bc=bc, de=de, hl=hl, ix=ix, iy=iy,
            alt_af=alt_af, alt_bc=alt_bc,
            alt_de=alt_de, alt_hl=alt_hl,
            pc=pc, sp=sp, ir=ir, wz=wz, iregp_kind=iregp_kind,
            iff1=iff1, iff2=iff2, int_mode=int_mode)


# The ULA chip's state.
class ULASnapshot(DataRecord):
    ticks_since_int: int | None
    border_colour: int | None

    def __init__(
            self, *,
            ticks_since_int: int | None = None,
            border_colour: int | None = None):
        super().__init__(
            ticks_since_int=ticks_since_int,
            border_colour=border_colour)


# A concrete selection of memory pages within the machine's
# address space. Reads and writes performed with a given mapping
# work as if that selection of pages was in effect.
class MemoryMapping:
    # Tells where the bytes of the given address range live in the
    # internal memory image. A range never crosses from one page to
    # another; content that would is handled piecewise.
    def get_offset(self, addr: int, size: int) -> int:
        raise NotImplementedError


# A block of memory content: data at an offset of the contiguous
# memory image.
class MemoryBlock(DataRecord):
    offset: int
    data: ByteData

    @property
    def end_offset(self) -> int:
        return self.offset + len(self.data.data)

    def __init__(self, *, offset: int, data: Bytes | ByteData):
        super().__init__(offset=offset, data=HexData.wrap(data))


# The memory chips' state: the contents as blocks, and the total
# size of the machine's memory as its configuration. A model
# subclass fixes the configuration as a class keyword, which the
# base records as a class attribute. Null fields mean the canonical
# reset values.
class MemorySnapshot(DataRecord):
    image_size: int | None
    blocks: list[MemoryBlock] | None

    def __init_subclass__(cls, *, image_size: int,
                          **kwargs: typing.Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.image_size = image_size

    def __init__(
            self, *, image_size: int | None = None,
            blocks: typing.Sequence[MemoryBlock] | None = None):
        if blocks is not None:
            blocks = sorted(blocks, key=lambda b: b.offset)

            # Blocks never overlap, so their order carries no
            # meaning and sorting them loses nothing.
            for a, b in itertools.pairwise(blocks):
                assert a.end_offset <= b.offset

        super().__init__(image_size=image_size, blocks=blocks)

    # Tells whether the memory holds the given content at the given
    # address, acting as if the given mapping was applied. A byte no
    # block states matches nothing.
    def match(self, mapping: MemoryMapping, addr: int,
              content: Bytes) -> bool:
        content = bytes(content)
        offset = mapping.get_offset(addr, len(content))
        end_offset = offset + len(content)

        pos = offset
        for block in self.blocks or []:
            if block.end_offset <= pos:
                continue
            if pos >= end_offset:
                break
            if block.offset > pos:
                return False

            stop = min(end_offset, block.end_offset)
            if (block.data.data[pos - block.offset:stop - block.offset] !=
                    content[pos - offset:stop - offset]):
                return False
            pos = stop

        return pos == end_offset


# The core device's slice of a machine snapshot. Null fields mean
# the canonical reset values.
class CoreSnapshot(DeviceSnapshot):
    disabled: bool | None
    z80: Z80Snapshot | None
    ula: ULASnapshot | None
    memory: MemorySnapshot | None

    def __init__(
            self,
            disabled: bool | None = None,
            z80: Z80Snapshot | None = None,
            ula: ULASnapshot | None = None,
            memory: MemorySnapshot | None = None):
        super().__init__(
            disabled=disabled,
            z80=z80,
            ula=ula,
            memory=memory)


class StateParser:
    def __init__(self, image: memoryview) -> None:
        self.__image = image
        self.__pos = 0

    @property
    def parsed_image(self) -> memoryview:
        return self.__image[:self.__pos]

    def read_bytes(self, size: int) -> memoryview:
        block = self.__image[self.__pos:self.__pos + size]
        self.__pos += size
        assert len(block) == size
        return block

    def parse8(self) -> memoryview:
        return self.read_bytes(1)

    def parse16(self) -> memoryview:
        return self.read_bytes(2)

    def parse32(self) -> memoryview:
        return self.read_bytes(4)

    def parse64(self) -> memoryview:
        return self.read_bytes(8)


class Z80State:
    def __init__(self, image: memoryview) -> None:
        p = StateParser(image)
        self.__bc = p.parse16()
        self.__de = p.parse16()
        self.__hl = p.parse16()
        self.__af = p.parse16()
        self.__ix = p.parse16()
        self.__iy = p.parse16()
        self.__alt_bc = p.parse16()
        self.__alt_de = p.parse16()
        self.__alt_hl = p.parse16()
        self.__alt_af = p.parse16()
        self.__pc = p.parse16()
        self.__sp = p.parse16()
        self.__ir = p.parse16()
        self.__wz = p.parse16()
        self.__iff1 = p.parse8()
        self.__iff2 = p.parse8()
        self.__int_mode = p.parse8()
        self.__iregp_kind = p.parse8()

    # TODO: Use a mix-in from the z80 module to implement these?
    # TODO: Add accessors for all the 8-bit registers.
    @property
    def bc(self) -> int:
        return int.from_bytes(self.__bc, 'little')

    @bc.setter
    def bc(self, value: int) -> None:
        self.__bc[:] = value.to_bytes(2, 'little')

    @property
    def de(self) -> int:
        return int.from_bytes(self.__de, 'little')

    @de.setter
    def de(self, value: int) -> None:
        self.__de[:] = value.to_bytes(2, 'little')

    @property
    def hl(self) -> int:
        return int.from_bytes(self.__hl, 'little')

    @hl.setter
    def hl(self, value: int) -> None:
        self.__hl[:] = value.to_bytes(2, 'little')

    @property
    def af(self) -> int:
        return int.from_bytes(self.__af, 'little')

    @af.setter
    def af(self, value: int) -> None:
        self.__af[:] = value.to_bytes(2, 'little')

    @property
    def a(self) -> int:
        return self.__af[1]

    @a.setter
    def a(self, value: int) -> None:
        self.__af[1] = value

    @property
    def f(self) -> int:
        return self.__af[0]

    @property
    def ix(self) -> int:
        return int.from_bytes(self.__ix, 'little')

    @ix.setter
    def ix(self, value: int) -> None:
        self.__ix[:] = value.to_bytes(2, 'little')

    @property
    def iy(self) -> int:
        return int.from_bytes(self.__iy, 'little')

    @iy.setter
    def iy(self, value: int) -> None:
        self.__iy[:] = value.to_bytes(2, 'little')

    @property
    def alt_bc(self) -> int:
        return int.from_bytes(self.__alt_bc, 'little')

    @alt_bc.setter
    def alt_bc(self, value: int) -> None:
        self.__alt_bc[:] = value.to_bytes(2, 'little')

    @property
    def alt_de(self) -> int:
        return int.from_bytes(self.__alt_de, 'little')

    @alt_de.setter
    def alt_de(self, value: int) -> None:
        self.__alt_de[:] = value.to_bytes(2, 'little')

    @property
    def alt_hl(self) -> int:
        return int.from_bytes(self.__alt_hl, 'little')

    @alt_hl.setter
    def alt_hl(self, value: int) -> None:
        self.__alt_hl[:] = value.to_bytes(2, 'little')

    @property
    def alt_af(self) -> int:
        return int.from_bytes(self.__alt_af, 'little')

    @alt_af.setter
    def alt_af(self, value: int) -> None:
        self.__alt_af[:] = value.to_bytes(2, 'little')

    @property
    def alt_a(self) -> int:
        return self.__alt_af[1]

    @property
    def alt_f(self) -> int:
        return self.__alt_af[0]

    @property
    def pc(self) -> int:
        return int.from_bytes(self.__pc, 'little')

    @pc.setter
    def pc(self, value: int) -> None:
        self.__pc[:] = value.to_bytes(2, 'little')

    @property
    def sp(self) -> int:
        return int.from_bytes(self.__sp, 'little')

    @sp.setter
    def sp(self, value: int) -> None:
        self.__sp[:] = value.to_bytes(2, 'little')

    @property
    def ir(self) -> int:
        return int.from_bytes(self.__ir, 'little')

    @ir.setter
    def ir(self, value: int) -> None:
        self.__ir[:] = value.to_bytes(2, 'little')

    @property
    def i(self) -> int:
        return self.__ir[1]

    @property
    def r(self) -> int:
        return self.__ir[0]

    @property
    def iff1(self) -> int:
        return bool(self.__iff1[0])

    @iff1.setter
    def iff1(self, value: int) -> None:
        self.__iff1[0] = value

    @property
    def iff2(self) -> int:
        return bool(self.__iff2[0])

    @iff2.setter
    def iff2(self, value: int) -> None:
        self.__iff2[0] = value

    @property
    def int_mode(self) -> int:
        return self.__int_mode[0]

    @int_mode.setter
    def int_mode(self, value: int) -> None:
        self.__int_mode[0] = value

    @property
    def iregp_kind(self) -> str:
        n = self.__iregp_kind[0]
        return {0: 'hl', 1: 'ix', 2: 'iy'}[n]

    @iregp_kind.setter
    def iregp_kind(self, value: str) -> None:
        n = {'hl': 0, 'ix': 1, 'iy': 2}[value]
        self.__iregp_kind[0] = n


class CoreState(Z80State):
    __PAGE_SIZE = 0x4000

    def __init__(self, image: memoryview) -> None:
        p = StateParser(image)

        self.z80_image = p.read_bytes(32)
        Z80State.__init__(self, self.z80_image)

        self.__ticks_since_int = p.parse32()
        self.__tick_count = p.parse64()
        self.__m1_fetches_to_stop = p.parse32()
        self.__ticks_to_stop = p.parse32()
        self.__events = p.parse32()
        self.__int_suppressed = p.parse8()
        self.__int_after_ei_allowed = p.parse8()
        self.__border_colour = p.parse8()
        self.__trace_enabled = p.parse8()
        self.__paging_supported = p.parse8()
        # Three padding bytes.
        p.parse8()
        p.parse8()
        p.parse8()

        self.__ticks_per_second = p.parse32()
        self.__ticks_per_horizontal_retrace = p.parse32()
        self.__lines_per_vertical_retrace = p.parse32()
        self.__contention_base = p.parse32()

        self.__memory = p.read_bytes(10 * self.__PAGE_SIZE)

    @property
    def suppress_interrupts(self) -> bool:
        return bool(self.__int_suppressed[0])

    @suppress_interrupts.setter
    def suppress_interrupts(self, suppress: bool) -> None:
        self.__int_suppressed[0] = int(suppress)

    @property
    def allow_int_after_ei(self) -> bool:
        return bool(self.__int_after_ei_allowed[0])

    @allow_int_after_ei.setter
    def allow_int_after_ei(self, allow: bool) -> None:
        self.__int_after_ei_allowed[0] = int(allow)

    # The number of M1 fetches left before the run stops between
    # instructions (raising fetches_limit_hit); counts down as the
    # machine executes. Null means no limit.
    @property
    def m1_fetches_to_stop(self) -> int:
        return int.from_bytes(self.__m1_fetches_to_stop, 'little')

    @m1_fetches_to_stop.setter
    def m1_fetches_to_stop(self, fetches: int) -> None:
        self.__m1_fetches_to_stop[:] = fetches.to_bytes(4, 'little')

    # The number of ticks left before the run stops between
    # instructions (raising ticks_limit_hit), without ending the
    # frame; counts down as the machine executes. Null means no
    # limit. Set per quantum to cap how far a quantum advances,
    # e.g. for sub-frame quanta at slow speeds.
    @property
    def ticks_to_stop(self) -> int:
        return int.from_bytes(self.__ticks_to_stop, 'little')

    @ticks_to_stop.setter
    def ticks_to_stop(self, ticks: int) -> None:
        self.__ticks_to_stop[:] = ticks.to_bytes(4, 'little')

    # TODO: Can we do without this?
    def get_events(self) -> int:
        return int.from_bytes(self.__events, 'little')

    # TODO: Can we do without this?
    def set_events(self, events: int) -> None:
        self.__events[:] = events.to_bytes(4, 'little')

    # TODO: Can we do without this?
    def raise_events(self, events: int) -> None:
        self.set_events(self.get_events() | events)

    @property
    def ticks_since_int(self) -> int:
        return int.from_bytes(self.__ticks_since_int, 'little')

    @ticks_since_int.setter
    def ticks_since_int(self, ticks: int) -> None:
        self.__ticks_since_int[:] = ticks.to_bytes(4, 'little')

    # The number of ticks since the machine creation. Free-running
    # and 64-bit, so it never wraps in any realistic run.
    @property
    def tick_count(self) -> int:
        return int.from_bytes(self.__tick_count, 'little')

    # The CPU clock, in Hz.
    @property
    def ticks_per_second(self) -> int:
        return int.from_bytes(self.__ticks_per_second, 'little')

    @ticks_per_second.setter
    def ticks_per_second(self, value: int) -> None:
        self.__ticks_per_second[:] = value.to_bytes(4, 'little')

    @property
    def ticks_per_horizontal_retrace(self) -> int:
        return int.from_bytes(self.__ticks_per_horizontal_retrace, 'little')

    @ticks_per_horizontal_retrace.setter
    def ticks_per_horizontal_retrace(self, value: int) -> None:
        self.__ticks_per_horizontal_retrace[:] = value.to_bytes(4, 'little')

    @property
    def lines_per_vertical_retrace(self) -> int:
        return int.from_bytes(self.__lines_per_vertical_retrace, 'little')

    @lines_per_vertical_retrace.setter
    def lines_per_vertical_retrace(self, value: int) -> None:
        self.__lines_per_vertical_retrace[:] = value.to_bytes(4, 'little')

    # The tick, counted from the start of INT, at which contention
    # first applies, one tick before the top-left screen pixel.
    @property
    def contention_base(self) -> int:
        return int.from_bytes(self.__contention_base, 'little')

    @contention_base.setter
    def contention_base(self, value: int) -> None:
        self.__contention_base[:] = value.to_bytes(4, 'little')

    @property
    def border_colour(self) -> int:
        return self.__border_colour[0]

    @border_colour.setter
    def border_colour(self, value: int) -> None:
        self.__border_colour[0] = value

    ''' TODO
    def enable_trace(self, enable=True):
        self.set('trace_enabled', int(enable))
    '''

    # Whether the board wires the 0x7FFD paging circuit: the model
    # core classes state it, the C++ port-write handler reads it.
    @property
    def _paging_supported(self) -> bool:
        return bool(self.__paging_supported[0])

    @_paging_supported.setter
    def _paging_supported(self, value: bool) -> None:
        self.__paging_supported[0] = int(value)

    def _read_image(self, offset: int, size: int) -> bytes:
        assert offset + size <= len(self.__memory)
        return bytes(self.__memory[offset:offset + size])

    def _write_image(self, offset: int, block: bytes) -> None:
        assert offset + len(block) <= len(self.__memory)
        self.__memory[offset:offset + len(block)] = block

    # Reads and writes at machine addresses act as if the given
    # mapping was applied to the machine.
    def read(self, mapping: MemoryMapping, addr: int,
             size: int) -> bytes:
        return self._read_image(mapping.get_offset(addr, size), size)

    def write(self, mapping: MemoryMapping, addr: int,
              block: bytes) -> None:
        self._write_image(mapping.get_offset(addr, len(block)), block)

    def read8(self, mapping: MemoryMapping, addr: int) -> int:
        return self.read(mapping, addr, 1)[0]

    def read16(self, mapping: MemoryMapping, addr: int) -> int:
        return int.from_bytes(self.read(mapping, addr, 2), 'little')


# Stores information about the running code.
class Profile:
    def __init__(self) -> None:
        # Per instance: a class-level default would be shared by all
        # profiles.
        self._annots: dict[int, str] = {}

    def add_instr_addr(self, addr: int) -> None:
        self._annots[addr] = 'instr'

    def __iter__(self) -> typing.Iterable[tuple[int, str]]:
        for addr in sorted(self._annots):
            yield addr, self._annots[addr]


class Core(_CoreBase, CoreState, Device):
    """The CPU, memory and ULA of an emulated machine, as one device.

    Holds their state and steps the emulation. Construct it directly
    only for low-level use, otherwise let Emulator create it.
    """

    # Memory marks.
    __NO_MARKS = 0
    __BREAKPOINT_MARK = 1 << 0

    FRAME_SIZE = 48 + 256 + 48, 48 + 192 + 40

    __profile: Profile | None
    __playback: MachinePlayback | None

    def __init__(self, *,
                 disabled: bool = False,
                 profile: Profile | None = None,
                 _paging_supported: bool,
                 _ticks_per_second: int,
                 _ticks_per_horizontal_retrace: int,
                 _lines_per_vertical_retrace: int,
                 _contention_base: int):
        CoreState.__init__(self, self._get_state_view())
        Device.__init__(self, disabled=disabled)

        # The wiring the model core classes state.
        self._paging_supported = _paging_supported
        self.ticks_per_second = _ticks_per_second
        self.ticks_per_horizontal_retrace = _ticks_per_horizontal_retrace
        self.lines_per_vertical_retrace = _lines_per_vertical_retrace
        self.contention_base = _contention_base

        self.frame_count = 0

        # The moment of the read that deferred, ending the current
        # quantum; None while no read has deferred.
        self.__deferred_read_time: Time | None = None

        self.__playback: MachinePlayback | None = None

        self.__profile = profile
        if self.__profile:
            self.set_breakpoints(0, 0x10000)

        self.__paused = False

    # Capture belongs to the model core classes, which know their
    # machine and produce their typed snapshots; a bare Core states
    # nothing to capture.

    def install_snapshot(self, snapshot: CoreSnapshot) -> None:
        # A snapshot describes the difference from the canonical reset
        # state, so installing one resets first: whatever the snapshot
        # does not mention, the ROMs included, stays at reset. The
        # wiring is the core class's, untouched by installs.
        self._reset()
        self._reset_roms()
        self.disabled = False

        for field, value in snapshot:
            if field in ('z80', 'ula'):
                for chip_field, chip_value in value:
                    setattr(self, chip_field, chip_value)
            elif field == 'memory':
                for block in value.blocks or []:
                    self._write_image(block.offset, block.data.data)
            else:
                setattr(self, field, value)

    def __current_time(self) -> Time:
        return Time(self.tick_count,
                    ticks_per_second=self.ticks_per_second)

    # Loads the C++-side sample table from the published stream:
    # this device's copy of it. Each series' ticks, counted on its
    # device's own timeline, become offsets from tick 0 -- the last
    # device-resolution tick at or before the floor -- with the
    # samples before the floor pruned to the one stating the value
    # in effect at it. The exact arbitrary-precision arithmetic all
    # happens here; the C++ side only compares quantum-bounded
    # differences.
    def __load_port_read_samples(self, event: NewPortReads) -> None:
        self._clear_port_read_samples()

        core_resolution = self.ticks_per_second
        floor = event.time
        floor_core_tick = (floor.count * core_resolution //
                           floor.ticks_per_second)

        for series in event.series:
            device_resolution = series.ticks_per_second
            tick0, remainder = divmod(
                floor_core_tick * device_resolution, core_resolution)

            if len(series.ticks) == 0:
                self._add_port_read_samples(
                    floor_core_tick, device_resolution, remainder,
                    series.addr_mask, series.addr_value, 0,
                    numpy.zeros(0, dtype=numpy.uint64))
                continue

            # The sample in effect at the floor is the last one at
            # or before it; earlier history means nothing this
            # quantum. A sample tick s lies at or before the floor
            # exactly when s * floor_resolution does not exceed
            # floor_count * device_resolution, so the last such
            # sample is the last with s at or under the quotient.
            # Its tick clamps back to tick 0, which lies at or
            # before the floor too, and no read falls in between.
            latest = (floor.count * device_resolution //
                      floor.ticks_per_second)
            first = int(numpy.searchsorted(
                series.ticks, latest, side='right')) - 1
            assert first >= 0, 'the value at the floor must be stated'

            ticks = series.ticks[first:].copy()
            ticks[0] = tick0
            entries = ((ticks - numpy.uint64(tick0)) << numpy.uint64(8) |
                       series.values[first:])

            num_ticks = series.end_tick - tick0
            assert num_ticks > 0, 'the coverage must reach the floor'
            self._add_port_read_samples(
                floor_core_tick, device_resolution, remainder,
                series.addr_mask, series.addr_value, num_ticks, entries)

    # TODO: Brush up and re-enable. A content device must not
    # write files or know file formats; this belongs to a
    # recoverer or the tool layer.
    # def __save_crash_rzx(self, player: PlaybackPlayer, state: CoreState,
    #                      chunk_i: int, frame_i: int) -> None:
    #     snapshot = Z80File.from_snapshot(state.to_snapshot()).encode()
    #
    #     assert 0  # TODO
    #     crash_recording = {
    #         'chunks': [
    #             player.find_recording_info_chunk(),
    #             {
    #                 'id': 'snapshot',
    #                 'image': snapshot,
    #             },
    #             {
    #                 'id': 'port_samples',
    #                 'first_tick': 0,
    #                 # TODO
    #                 # 'frames':
    #                 # recording['chunks'][chunk_i]['frames'][frame_i:],
    #             },
    #         ],
    #     }
    #
    #     with pathlib.Path('__crash.z80').open('wb') as f:
    #         f.write(snapshot)
    #
    #     with pathlib.Path('__crash.rzx').open('wb') as f:
    #         f.write(make_rzx(crash_recording))

    def __on_end_of_frame(self, devices: Dispatcher) -> None:
        # TODO: Can we translate the screen chunks into pixels
        # on the Python side using numpy?
        self.render_screen()

        if self.__playback is not None:
            self.on_handle_active_int()

        # TODO: Count the executed reads on the C++ side and report
        # them here, for the recorder's frames; reads resolved from
        # samples never enter Python.
        devices.notify(OutputFrame(
            pixels=self.get_frame_pixels(),
            port_reads=bytearray()))

        self.frame_count += 1

    def __enter_playback_mode(self, playback: MachinePlayback) -> None:
        self.__playback = playback
        # Interrupts are supposed to be controlled by the recording.
        self.suppress_interrupts = True
        self.allow_int_after_ei = True

    # TODO: Double-underscore or make public.
    def _quit_playback_mode(self) -> None:
        self.__playback = None
        self.suppress_interrupts = False
        self.allow_int_after_ei = False

    # Advances the core by one quantum, to the quantum's time limit
    # if any, otherwise to the frame end as before.
    def __advance(self, devices: Dispatcher,
                  stop_after: Time | None) -> None:
        if stop_after is None:
            self.ticks_to_stop = 0
        else:
            # Count down to the whole tick enclosing the requested
            # time; the run then stops at the first instruction
            # boundary at or after it.
            front = self.__current_time()
            remaining = stop_after - front
            budget = ((remaining.count * front.ticks_per_second +
                       remaining.ticks_per_second - 1) //
                      remaining.ticks_per_second)
            assert budget > 0
            self.ticks_to_stop = budget

        events = RunEvents(self._run(devices))

        if RunEvents.RETRY_INPUT in events:
            tick = self._get_deferred_port_read_tick()
            if tick is not None:
                self.__deferred_read_time = Time(
                    tick, ticks_per_second=self.ticks_per_second)

        # The run traps at a marked instruction without executing it,
        # so running again would just trap there anew. Report the
        # breakpoint and step over, unless a handler moved PC away.
        if RunEvents.BREAKPOINT_HIT in events:
            pc = self.pc
            self.on_breakpoint(devices)
            if self.pc == pc:
                events |= RunEvents(self._step_over_breakpoint(devices))

        now = self.__current_time()

        writes = numpy.frombuffer(self.drain_port_writes(),
                                  dtype=numpy.uint64)
        if len(writes):
            devices.notify(NewPortWrites(now, writes))

        if self.__playback is not None:
            if RunEvents.FETCHES_LIMIT_HIT in events:
                devices.notify(FetchesLimitHit())
        elif RunEvents.END_OF_FRAME in events:
            devices.notify(EndOfFrame())

    def stop(self) -> None:
        raise EmulationExit()

    @property
    def paused(self) -> bool:
        return self.__paused

    def __set_paused(self, value: bool, devices: Dispatcher) -> None:
        self.__paused = value
        devices.notify(PauseStateUpdated())

    def set_breakpoints(self, addr: int, size: int) -> None:
        self.mark_addrs(addr, size, self.__BREAKPOINT_MARK)

    def set_breakpoint(self, addr: int) -> None:
        self.set_breakpoints(addr, 1)

    def on_breakpoint(self, devices: Dispatcher) -> None:
        if self.__profile:
            self.__profile.add_instr_addr(self.pc)

        devices.notify(BreakpointHit())

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if isinstance(event, InstallDeviceSnapshot):
            snapshot = event.snapshot
            assert isinstance(snapshot, CoreSnapshot)
            self.install_snapshot(snapshot)
            return

        # A disabled core is indistinguishable from an absent one:
        # it runs no quanta and answers no queries.
        if self.disabled:
            return

        if isinstance(event, GetEmulationPauseState):
            event.paused |= self.paused
        elif isinstance(event, GetHoldState):
            # User pause holds with no deadline: only input can
            # change the answer.
            if self.paused:
                event.hold()
        elif isinstance(event, RunQuantum):
            if not event.held:
                self.__deferred_read_time = None
                self.__advance(devices, event.stop_after)

                # A quantum ended by a deferred read has its
                # position at the read's moment: the first moment
                # whose value the core lacks. The current time
                # reads the aborted instruction's start instead,
                # the counters being rewound for the retry; the
                # ticks before the read are deterministic replay.
                position = self.__deferred_read_time
                if position is None:
                    position = self.__current_time()
                else:
                    event.report_deferred_port_read(position)
                event.advanced_to(position)
        elif isinstance(event, NewPortReads):
            self.__load_port_read_samples(event)
        elif isinstance(event, GetFramePixels):
            # The core has already rendered the screen up to the
            # current tick on returning control, so this is current.
            event.pixels = self.get_frame_pixels()
        elif isinstance(event, KeyStroke):
            self.__set_paused(False, devices)
            devices.notify(StopPlayback())
        elif isinstance(event, EndOfFrame):
            self.__on_end_of_frame(devices)
        elif isinstance(event, SetBreakpoint):
            self.set_breakpoint(event.addr)
        elif isinstance(event, SetFetchesLimit):
            self.m1_fetches_to_stop = event.num_fetches
        elif isinstance(event, StopQuantum):
            self.raise_events(RunEvents.STOP_REQUESTED)
        elif isinstance(event, StartPlayback):
            self.__enter_playback_mode(event.playback)
        elif isinstance(event, StopPlayback):
            self._quit_playback_mode()
        elif isinstance(event, ResetEmulator):
            # The reset does not touch the ROMs: whatever is in the
            # socket stays, a snapshot-installed image included.
            self._reset()
        elif isinstance(event, ToggleEmulationPause):
            self.__set_paused(not self.paused, devices)

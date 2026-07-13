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
import typing

import numpy

from ._corebase import _CoreBase
from ._data import DeviceSnapshot
from ._data import MemoryBlock
from ._data import Spectrum48
from ._data import SpectrumModel
from ._data import UnifiedPlayback
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
from ._device import NewPortWrites
from ._device import OutputFrame
from ._device import PauseStateUpdated
from ._device import ReadPort
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
from ._rom import load_rom_image
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


# The core device's slice of a machine snapshot. Null fields mean
# the canonical reset values.
class CoreSnapshot(DeviceSnapshot, format_name=None):
    active: bool | None
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
    ticks_since_int: int | None
    border_colour: int | None
    memory_blocks: list[MemoryBlock] | None

    def __init__(
            self,
            active: bool | None = None,
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
            int_mode: int | None = None,
            ticks_since_int: int | None = None,
            border_colour: int | None = None,
            memory_blocks: typing.Sequence[MemoryBlock] | None = None):
        if memory_blocks is None:
            blocks = None
        else:
            blocks = sorted(memory_blocks, key=lambda b: b.addr)

        super().__init__(
            active=active,
            af=af, bc=bc, de=de, hl=hl, ix=ix, iy=iy,
            alt_af=alt_af, alt_bc=alt_bc,
            alt_de=alt_de, alt_hl=alt_hl,
            pc=pc, sp=sp, ir=ir, wz=wz, iregp_kind=iregp_kind,
            iff1=iff1, iff2=iff2, int_mode=int_mode,
            ticks_since_int=ticks_since_int,
            border_colour=border_colour,
            memory_blocks=blocks)


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

    __ROM_PAGE_IMAGE_OFFSETS: typing.ClassVar[dict[int, int]] = {
        0: 0 * __PAGE_SIZE,
        1: 4 * __PAGE_SIZE}

    __RAM_PAGE_IMAGE_OFFSETS: typing.ClassVar[dict[int, int]] = {
        5: 1 * __PAGE_SIZE,
        2: 2 * __PAGE_SIZE,
        0: 3 * __PAGE_SIZE,
        1: 5 * __PAGE_SIZE,
        3: 6 * __PAGE_SIZE,
        4: 7 * __PAGE_SIZE,
        6: 8 * __PAGE_SIZE,
        7: 9 * __PAGE_SIZE}

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
        self.__model = p.parse8()
        # Three padding bytes.
        p.parse8()
        p.parse8()
        p.parse8()

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

    @property
    def model(self) -> type[SpectrumModel]:
        return SpectrumModel._MODELS_BY_CXX_CODES[self.__model[0]]

    @model.setter
    def model(self, model: type[SpectrumModel]) -> None:
        self.__model[0] = model._CXX_MODEL_CODE

    def read(self, addr: int, size: int) -> bytes:
        assert addr + size <= 0x10000  # TODO
        return bytes(self.__memory[addr:addr + size])

    def write(self, addr: int, block: bytes, *,
              rom_page: int | None = None,
              ram_page: int | None = None) -> None:
        assert addr + len(block) <= 0x10000  # TODO
        while block:
            next_page_addr = (addr // self.__PAGE_SIZE + 1) * self.__PAGE_SIZE
            chunk = block[:next_page_addr - addr]

            if addr < 0x4000:
                # TODO: Write to the current ROM otherwise.
                assert rom_page is not None
                offset = self.__ROM_PAGE_IMAGE_OFFSETS[rom_page]
            elif addr < 0xc000:
                offset = addr
            else:
                # TODO: Write to the current RAM otherwise.
                assert ram_page is not None
                offset = self.__RAM_PAGE_IMAGE_OFFSETS[ram_page]

            self.__memory[offset:offset + len(chunk)] = chunk

            addr += len(chunk)
            block = block[len(chunk):]

    def read8(self, addr: int) -> int:
        return self.read(addr, 1)[0]

    def read16(self, addr: int) -> int:
        return int.from_bytes(self.read(addr, 2), 'little')


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


class Core(_CoreBase, CoreState, Device, snapshot_type=CoreSnapshot):
    """The CPU, memory and ULA of an emulated machine, as one device.

    Holds their state and steps the emulation. Construct it directly
    only for low-level use, otherwise let Emulator create it.
    """

    @classmethod
    def from_snapshot(cls, snapshot: DeviceSnapshot) -> Core:
        assert isinstance(snapshot, CoreSnapshot)
        core = cls()
        core.install_snapshot(snapshot)
        return core

    # Memory marks.
    __NO_MARKS = 0
    __BREAKPOINT_MARK = 1 << 0

    FRAME_SIZE = 48 + 256 + 48, 48 + 192 + 40

    __profile: None | Profile
    __playback: UnifiedPlayback | None

    def __init__(self, *,
                 active: bool = False,
                 model: type[SpectrumModel] | None = None,
                 profile: Profile | None = None):
        CoreState.__init__(self, self._get_state_view())
        Device.__init__(self, active=active)

        self.model = model if model is not None else Spectrum48

        self.__install_rom()

        self.frame_count = 0

        self.set_on_input_callback(self.__on_input)

        self.__port_reads = bytearray()

        self.__playback: UnifiedPlayback | None = None

        self.__profile = profile
        if self.__profile:
            self.set_breakpoints(0, 0x10000)

        self.__paused = False

    def __install_rom(self) -> None:
        PAGE_SIZE = 0x4000
        rom = load_rom_image(self.model._ROM_FILE_NAME)
        assert len(rom) >= PAGE_SIZE
        self.write(0x0000, rom[:PAGE_SIZE], rom_page=0)
        if len(rom) > PAGE_SIZE:
            assert len(rom) == 2 * PAGE_SIZE
            self.write(0x0000, rom[PAGE_SIZE:], rom_page=1)

    def to_snapshot(self) -> CoreSnapshot:
        # TODO: Store all fields.
        assert self.model is Spectrum48  # TODO: Support 128K.
        return CoreSnapshot(
            active=True if self.active else None,
            af=self.af, bc=self.bc, de=self.de, hl=self.hl,
            ix=self.ix, iy=self.iy,
            alt_af=self.alt_af, alt_bc=self.alt_bc,
            alt_de=self.alt_de, alt_hl=self.alt_hl,
            pc=self.pc, sp=self.sp, ir=self.ir,
            # TODO: wz=self.wz,
            iff1=self.iff1, iff2=self.iff2, int_mode=self.int_mode,
            iregp_kind=self.iregp_kind,
            memory_blocks=[MemoryBlock(addr=0x4000, rom_page=0, ram_page=0,
                                       data=self.read(0x4000, 0xc000))],
            ticks_since_int=self.ticks_since_int,
            border_colour=self.border_colour)

    def install_snapshot(self, snapshot: CoreSnapshot) -> None:
        # A snapshot describes the difference from the canonical reset
        # state, so installing one resets first: whatever the snapshot
        # does not mention stays at reset.
        self.on_reset()
        self.__install_rom()
        self.active = False

        for field, value in snapshot:
            if field == 'memory_blocks':
                for block in value:
                    self.write(block.addr, block.data.data,
                               rom_page=block.rom_page,
                               ram_page=block.ram_page)
            else:
                setattr(self, field, value)

    def __current_time(self) -> Time:
        return Time(self.tick_count,
                    ticks_per_second=self.model._TICKS_PER_FRAME * 50)

    def __on_input(self, addr: int, devices: Dispatcher) -> int | None:
        # The core makes port accesses with tick_count reading the
        # 0-based number of the tick the data crosses the bus during,
        # so the current time is the exact sampling moment.
        read_port = ReadPort(addr, self.__current_time())
        devices.notify(read_port)
        v = read_port.value
        if v is not None:
            self.__port_reads.append(v)
        return v

    # TODO: Brush up and re-enable. A content device must not
    # write files or know file formats; this belongs to a
    # recoverer or the tool layer.
    # def __save_crash_rzx(self, player: PlaybackPlayer, state: CoreState,
    #                      chunk_i: int, frame_i: int) -> None:
    #     snapshot = Z80Snapshot.from_snapshot(state.to_snapshot()).encode()
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

        devices.notify(OutputFrame(
            pixels=self.get_frame_pixels(),
            port_reads=self.__port_reads))
        self.__port_reads.clear()

        self.frame_count += 1

    def __enter_playback_mode(self, playback: UnifiedPlayback) -> None:
        self.__playback = playback
        # Interrupts are supposed to be controlled by the recording.
        self.suppress_interrupts = True
        self.allow_int_after_ei = True

    # TODO: Double-underscore or make public.
    def _quit_playback_mode(self) -> None:
        self.__playback = None
        self.suppress_interrupts = False
        self.allow_int_after_ei = False

    # Advances the core by one quantum, to the round's time limit if
    # any, otherwise to the frame end as before.
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

        # An inactive core is indistinguishable from an absent one:
        # it runs no quanta and answers no queries.
        if not self.active:
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
                self.__advance(devices, event.stop_after)
                event.advanced_to(self.__current_time())
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
            self.on_reset()
            self.__install_rom()
        elif isinstance(event, ToggleEmulationPause):
            self.__set_paused(not self.paused, devices)

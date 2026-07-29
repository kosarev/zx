#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from __future__ import annotations

import math
import typing

import numpy

from ._data import DeviceSnapshot
from ._data import PortReadSeries
from ._data import SoundPulses
from ._device import CollectPortReads
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import InstallDeviceSnapshot
from ._device import NewPortWrites
from ._device import NewSoundPulses
from ._device import ResetEmulator
from ._device import RunQuantum
from ._device import TimeAdvanced
from ._time import Time

if typing.TYPE_CHECKING:
    from ._data import AYStream


# The AY-3-8910 register write as a stamped fact: the chip vocabulary,
# with the port decoding left to the machine side. Values are stored
# as written; consumers mask off the significant bits. Writes are
# events, not states: rewriting the envelope shape register restarts
# the envelope even with an unchanged value.
class AY8910RegisterWrite(DeviceEvent):
    def __init__(self, reg: int, value: int, time: Time):
        self.reg = reg
        self.value = value
        self.time = time


# The 17-bit LFSR of the noise generator produces a fixed periodic
# bit sequence; precompute it once and then noise is indexing.
def _make_noise_bits() -> numpy.typing.NDArray[numpy.uint8]:
    bits = numpy.empty(131071, dtype=numpy.uint8)
    rng = 1
    for i in range(len(bits)):
        bits[i] = rng & 1
        rng = (rng >> 1) | ((((rng >> 0) ^ (rng >> 3)) & 1) << 16)
    return bits


# The chip's output levels for volumes 0-15, normalised.
_DAC = numpy.array([
    0.0, 0.00999, 0.01445, 0.02105,
    0.03070, 0.04554, 0.06449, 0.10736,
    0.12658, 0.20228, 0.24145, 0.30662,
    0.42906, 0.50441, 0.72940, 1.0])


class AY8910Snapshot(DeviceSnapshot):
    disabled: bool | None

    def __init__(self, *, disabled: bool | None = None) -> None:
        super().__init__(disabled=disabled)


class AY8910(Device):
    """The AY-3-8910 sound generator.

    The synthesiser is a pure function of a stamped register-write
    stream: it publishes, on TimeAdvanced, a SoundPulses chunk per
    channel covering the elapsed span — the chip has three outputs,
    and combining them is the mixer's business, like any other
    emitters'. The internal grid is the generator step of 8 chip
    clocks: a tone flips every period count of it, noise and the
    envelope move every second count of theirs. The chip runs its
    own clock, and stamps of any timeline place against its grid by
    exact integer arithmetic, so any machine's clock may drive the
    bus. A write takes effect at the following step boundary.

    The stream has two producers. The chip's own bus interface
    decodes the machine's stamped port writes: the board's gates
    only look at A15, A14 and A1, so writes to the 0xFFFD pattern
    latch the register address and writes to the 0xBFFD pattern
    write the addressed register, mirrors included. Players bypass
    the bus interface and drive the stream directly with
    AY8910RegisterWrite events.
    """

    # The chip clock, in Hz: the 128K's wiring and the .ay player
    # convention. It becomes an AY configuration field when a
    # machine that wires a different clock arrives (CPC rips run
    # the chip at 1 MHz).
    _CLOCK = 1_773_450

    # Chip clocks per generator step.
    _CLOCKS_PER_STEP = 8

    _noise_bits: typing.ClassVar[
        numpy.typing.NDArray[numpy.uint8] | None] = None

    def __init__(self, *, disabled: bool = False) -> None:
        super().__init__(disabled=disabled)

        if AY8910._noise_bits is None:
            AY8910._noise_bits = _make_noise_bits()

        self.__published_up_to: Time | None = None
        self.__pending: list[AY8910RegisterWrite] = []
        self.__reset_state()

    def to_snapshot(self) -> AY8910Snapshot | None:
        # A disabled AY is indistinguishable from an absent one, so
        # there is nothing to capture.
        if self.disabled:
            return None

        return AY8910Snapshot()

    def __reset_state(self) -> None:
        self.__regs = [0] * 16

        # The bus interface's register-address latch. It stores the
        # full written byte: a value with the high nibble set
        # deselects the chip (the nibble is a chip address for
        # multi-AY buses).
        self.__selected_register = 0

        # Generators run as down-counters: the steps remaining to the
        # next flip/shift/ramp move, reloaded with the period on
        # expiry only, so a period write never re-times the move
        # already in flight.
        self.__tone_steps_to_flip = [1, 1, 1]
        self.__tone_out = [0, 0, 0]

        self.__noise_steps_to_shift = 1
        self.__noise_pos = 0

        self.__env_steps_to_move = 1
        self.__env_idx = 0

        # The levels the current chunks open at, per channel.
        self.__current_levels = [0.0, 0.0, 0.0]

    # The first generator-step boundary at or after the given
    # moment, as a step index. Steps count 8 chip clocks each from
    # tick 0, so the boundary of step s falls at s * 8 / _CLOCK
    # seconds, and a stamp of any resolution places against the
    # boundaries by exact integer arithmetic.
    def __step_at_or_after(self, time: Time) -> int:
        ticks = time.count * self._CLOCK
        step = time.ticks_per_second * self._CLOCKS_PER_STEP
        return -(-ticks // step)

    def __tone_period(self, channel: int) -> int:
        fine = self.__regs[channel * 2]
        coarse = self.__regs[channel * 2 + 1]
        return max(((coarse & 0x0f) << 8) | (fine & 0xff), 1)

    def __noise_period(self) -> int:
        # The noise generator shifts every 16 * NP chip clocks.
        return max(self.__regs[6] & 0x1f, 1) * 2

    def __env_period(self) -> int:
        # An envelope volume step lasts 16 * EP chip clocks.
        return max(((self.__regs[12] & 0xff) << 8) |
                   (self.__regs[11] & 0xff), 1) * 2

    # The envelope volume indices for the given envelope step
    # indices, per the shape register.
    def __env_values(self, idx: numpy.typing.NDArray[numpy.int64]) -> (
            numpy.typing.NDArray[numpy.int64]):
        shape = self.__regs[13] & 0x0f
        continue_ = bool(shape & 8)
        attack = bool(shape & 4)
        alternate = bool(shape & 2)
        hold = bool(shape & 1)

        if not continue_:
            ramp = idx if attack else 15 - idx
            return numpy.where(idx < 16, ramp, 0)

        if hold:
            ramp = idx if attack else 15 - idx
            hold_value = 15 if attack ^ alternate else 0
            return numpy.where(idx < 16, ramp, hold_value)

        j = idx % 16
        ramp = j if attack else 15 - j
        if alternate:
            odd_cycle = (idx // 16) & 1
            ramp = numpy.where(odd_cycle == 1, 15 - j, j) if attack else \
                numpy.where(odd_cycle == 1, j, 15 - j)
        return ramp

    # The number of generator moves within the next count steps,
    # per step, for a down-counter with the given steps remaining to
    # the next move and the given reload period, and its state after
    # the count steps.
    @staticmethod
    def __count_moves(steps: numpy.typing.NDArray[numpy.int64],
                      count: int, remaining: int, period: int) -> (
            tuple[numpy.typing.NDArray[numpy.int64], int, int]):
        moves = numpy.where(steps >= remaining,
                            (steps - remaining) // period + 1, 0)
        total = int(moves[-1]) if count else 0
        if count >= remaining:
            remaining += ((count - remaining) // period + 1) * period
        remaining -= count
        return moves, total, remaining

    # Synthesise the output levels of the given number of steps, per
    # channel, advancing the generator state.
    def __render_steps(self, count: int) -> (
            list[numpy.typing.NDArray[numpy.float64]]):
        steps = numpy.arange(1, count + 1, dtype=numpy.int64)
        mixer = self.__regs[7]

        noise_bits = AY8910._noise_bits
        assert noise_bits is not None
        shifts, total_shifts, self.__noise_steps_to_shift = (
            self.__count_moves(steps, count, self.__noise_steps_to_shift,
                               self.__noise_period()))
        noise = noise_bits[(self.__noise_pos + shifts) % len(noise_bits)]
        self.__noise_pos = int((self.__noise_pos + total_shifts) %
                               len(noise_bits))

        # The envelope runs whether or not any channel listens.
        moves, total_moves, self.__env_steps_to_move = (
            self.__count_moves(steps, count, self.__env_steps_to_move,
                               self.__env_period()))
        env = _DAC[self.__env_values(self.__env_idx + moves)]
        self.__env_idx += total_moves

        outputs = []
        for channel in range(3):
            flips, total_flips, self.__tone_steps_to_flip[channel] = (
                self.__count_moves(steps, count,
                                   self.__tone_steps_to_flip[channel],
                                   self.__tone_period(channel)))
            tone = self.__tone_out[channel] ^ (flips & 1)
            self.__tone_out[channel] ^= total_flips & 1

            bit = numpy.ones(count, dtype=numpy.int64)
            if not mixer & (1 << channel):
                bit &= tone
            if not mixer & (8 << channel):
                bit &= noise

            # Centre each channel's square wave at zero, so changes
            # of note and volume shift no DC level.
            volume_reg = self.__regs[8 + channel]
            amplitude = (env if volume_reg & 0x10 else
                         _DAC[volume_reg & 0x0f]) / 2
            outputs.append(numpy.where(bit == 1, amplitude, -amplitude))

        return outputs

    def __apply_write(self, write: AY8910RegisterWrite) -> None:
        reg = write.reg & 0x0f
        self.__regs[reg] = write.value & 0xff

        # A write of the shape register restarts the envelope.
        if reg == 13:
            self.__env_idx = 0
            self.__env_steps_to_move = self.__env_period()

    def __publish(self, stamp: Time, dispatcher: Dispatcher) -> None:
        published_up_to = self.__published_up_to
        self.__published_up_to = stamp

        # Resynchronise after construction or reset: no sound is
        # rendered for the span, but the writes still shape the
        # register state.
        if published_up_to is None:
            for write in self.__pending:
                self.__apply_write(write)
            self.__pending.clear()
            return

        # The chunk's resolution: fine enough to place the span ends
        # and the step boundaries exactly. For streams stamped on
        # the 128K clock this is the stamp resolution itself.
        rate = math.lcm(published_up_to.ticks_per_second,
                        stamp.ticks_per_second, self._CLOCK)
        begin = published_up_to.count * (
            rate // published_up_to.ticks_per_second)
        num_ticks = stamp.count * (rate // stamp.ticks_per_second) - begin
        if num_ticks == 0:
            return
        assert num_ticks <= 0xffffffff

        ticks_per_step = self._CLOCKS_PER_STEP * (rate // self._CLOCK)

        # The steps whose boundaries land within the span; levels are
        # constant within a step, so these are the only possible
        # transition points.
        first_step = self.__step_at_or_after(published_up_to)
        end_step = self.__step_at_or_after(stamp)

        writes, self.__pending = self.__pending, []

        level_chunks: list[list[numpy.typing.NDArray[numpy.float64]]] = []
        step = first_step
        for write in writes:
            effect_step = min(max(self.__step_at_or_after(write.time),
                                  step), end_step)
            if effect_step > step:
                level_chunks.append(
                    self.__render_steps(effect_step - step))
                step = effect_step
            self.__apply_write(write)
        if end_step > step:
            level_chunks.append(self.__render_steps(end_step - step))

        for channel in range(3):
            if level_chunks:
                levels = numpy.concatenate(
                    [c[channel] for c in level_chunks])
            else:
                levels = numpy.zeros(0, dtype=numpy.float64)

            # Keep only the transitions.
            opening_level = self.__current_levels[channel]
            previous = numpy.empty(len(levels), dtype=numpy.float64)
            previous[0:1] = opening_level
            previous[1:] = levels[:-1]
            changed = levels != previous
            if len(levels):
                self.__current_levels[channel] = float(levels[-1])

            steps = first_step + numpy.nonzero(changed)[0]
            ticks = (steps * ticks_per_step - begin).astype(numpy.uint32)
            transition_levels = levels[changed]

            # A chunk defines its level over its whole span: open it
            # at the carried level.
            if len(ticks) == 0 or ticks[0] != 0:
                ticks = numpy.insert(ticks, 0, 0)
                transition_levels = numpy.insert(transition_levels, 0,
                                                 opening_level)

            pulses = SoundPulses(rate, transition_levels, ticks,
                                 num_ticks=num_ticks)
            dispatcher.notify(NewSoundPulses(pulses))

    def __install_snapshot(self, s: DeviceSnapshot) -> None:
        assert isinstance(s, AY8910Snapshot)

        # Whatever the snapshot does not mention is at reset.
        self.__published_up_to = None
        self.__pending.clear()
        self.__reset_state()

        self.disabled = s.disabled is True

    def __add_write(self, write: AY8910RegisterWrite) -> None:
        assert (not self.__pending or
                not (write.time < self.__pending[-1].time))
        self.__pending.append(write)

    # The bus interface's write side: decode the machine's stamped
    # port writes into register writes on the pending stream.
    # Reading a register returns its implemented bits, the rest
    # driven low.
    __REGISTER_READ_MASKS = (0xff, 0x0f, 0xff, 0x0f, 0xff, 0x0f, 0x1f,
                             0xff, 0x1f, 0x1f, 0x1f, 0xff, 0xff, 0x0f)

    # Supplies the selected register's value at the floor, covering
    # one tick: the value holds only until a write no one can
    # foretell, so any later read defers, moves the floor here and
    # is answered then -- register reads are rare, so the stops are
    # cheap. A deselected chip, or one with an unimplemented
    # register selected, drives nothing: reads of the port then
    # resolve to the open-bus 0xff with no series at all.
    def __supply_register_value(self, event: CollectPortReads) -> None:
        if self.__selected_register >= len(self.__REGISTER_READ_MASKS):
            return

        value = (self.__regs[self.__selected_register] &
                 self.__REGISTER_READ_MASKS[self.__selected_register])
        floor_tick = event.floor.count
        event.supply(PortReadSeries(
            addr_mask=0xc002, addr_value=0xc000,
            ticks_per_second=event.floor.ticks_per_second,
            ticks=numpy.array([floor_tick], dtype=numpy.uint64),
            values=numpy.array([value], dtype=numpy.uint64),
            end_tick=floor_tick + 1))

    def __on_port_writes(self, event: NewPortWrites) -> None:
        # Prefilter with the board's two patterns, so writes to
        # other devices' ports cost no per-write work.
        masked = event.writes & numpy.uint64(0xc002)
        ops = event.writes[(masked == numpy.uint64(0xc000)) |
                           (masked == numpy.uint64(0x8000))]

        for op in ops:
            addr = int(op) & 0xffff
            value = (int(op) >> 16) & 0xff

            if addr & 0xc002 == 0xc000:
                self.__selected_register = value
            elif self.__selected_register < 16:
                # The per-write 32-bit stamps wrap; rebase against
                # the event's closing time.
                end = event.time.count
                tick = end - ((end - (int(op) >> 32)) & 0xffffffff)
                self.__add_write(AY8910RegisterWrite(
                    self.__selected_register, value,
                    Time(tick,
                         ticks_per_second=event.time.ticks_per_second)))

    def on_event(self, event: DeviceEvent, dispatcher: Dispatcher) -> None:
        if isinstance(event, InstallDeviceSnapshot):
            self.__install_snapshot(event.snapshot)
            return

        # A disabled AY is indistinguishable from an absent one: it
        # publishes no sound.
        if self.disabled:
            return

        if isinstance(event, ResetEmulator):
            self.__published_up_to = None
            self.__pending.clear()
            self.__reset_state()
        elif isinstance(event, AY8910RegisterWrite):
            self.__add_write(event)
        elif isinstance(event, NewPortWrites):
            self.__on_port_writes(event)
        elif isinstance(event, CollectPortReads):
            self.__supply_register_value(event)
        elif isinstance(event, TimeAdvanced):
            self.__publish(event.time, dispatcher)


class AYPlayer(Device):
    """Plays an AY stream: desk equipment that walks the
    frames and emits their writes as stamped AY8910RegisterWrite events.

    With no core present it is also the round loop's runner: it
    advances towards the requested stop time by its own decision and
    reports the position reached.
    """

    def __init__(self, stream: AYStream) -> None:
        self.__rate = stream.ticks_per_second

        # The stream flattened to stamped writes, in time order.
        self.__writes: list[tuple[int, int, int]] = []
        for frame in stream.frames:
            for write in frame.writes:
                tick = (frame.frame * stream.ticks_per_frame +
                        (write.tick if write.tick is not None else 0))
                assert (not self.__writes or
                        tick >= self.__writes[-1][0])
                self.__writes.append((tick, write.reg, write.value))
        self.__num_emitted = 0

        # The first uncommitted tick.
        self.__position = 0

        # How far to advance per round when no stop time is asked.
        self.__ticks_per_quantum = self.__rate // 50

    # The moment right after the last write.
    def get_end_time(self) -> Time:
        end = self.__writes[-1][0] + 1 if self.__writes else 0
        return Time(end, ticks_per_second=self.__rate)

    def __advance(self, stop_after: Time | None,
                  devices: Dispatcher) -> Time:
        if stop_after is None:
            target = self.__position + self.__ticks_per_quantum
        else:
            # The first own tick at or after the requested time.
            target = max(-(-stop_after.count * self.__rate //
                           stop_after.ticks_per_second),
                         self.__position)

        while (self.__num_emitted < len(self.__writes) and
               self.__writes[self.__num_emitted][0] < target):
            tick, reg, value = self.__writes[self.__num_emitted]
            devices.notify(AY8910RegisterWrite(
                reg, value, Time(tick, ticks_per_second=self.__rate)))
            self.__num_emitted += 1

        self.__position = target
        return Time(target, ticks_per_second=self.__rate)

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if isinstance(event, RunQuantum) and not event.held:
            event.advanced_to(self.__advance(event.stop_after, devices))

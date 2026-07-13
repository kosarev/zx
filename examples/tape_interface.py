#!/usr/bin/env python3

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2025-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

# A simple program that creates an instance of the emulator, initiates
# saving a Basic program and measures and decodes generated tape impulses.

import numpy

import zx

# Change to see the emulator screen.
HEADLESS = True


class DurationSet:
    def __init__(self):
        self.__sum = 0
        self.count = 0
        self.min = float('+inf')
        self.max = float('-inf')

    def add(self, duration):
        self.__sum += duration
        self.count += 1
        self.min = min(self.min, duration)
        self.max = max(self.max, duration)

    @property
    def average(self):
        return self.__sum / self.count if self.count > 0 else 0


# A device watching the machine's port writes: the MIC bit drives the
# tape output, and the per-write tick stamps measure the impulses
# exactly.
class TapeInterfaceMeter(zx.Device):
    def __init__(self):
        super().__init__()
        self.reporting = False

        self.__last_level = 1
        self.__last_level_tick = 0
        self.__last_half_period_level = 1
        self.__last_half_period_durations = DurationSet()

        self.__bits = []

    def on_event(self, event, devices):
        if isinstance(event, zx.NewPortWrites):
            self.__on_port_writes(event.writes)

    def __on_port_writes(self, writes):
        # Filter writes to the 0xfe port. Each write packs the port
        # address, the written value and the write's tick stamp.
        writes = writes[writes & numpy.uint64(0xff) == numpy.uint64(0xfe)]
        for write in writes:
            value = int(write >> numpy.uint64(16)) & 0xff
            tick = int(write >> numpy.uint64(32))
            self.__on_output(value, tick)

    def __on_output(self, value, tick):
        level = (value >> 3) & 1
        if self.__last_level == level:
            return

        # The stamps are 32-bit and wrap.
        duration = (tick - self.__last_level_tick) & 0xffffffff

        half_period_count = self.__last_half_period_durations.count
        average_duration = self.__last_half_period_durations.average
        DURATION_TOLERANCE = 10
        if abs(average_duration - duration) > DURATION_TOLERANCE:
            if self.reporting:
                if half_period_count == 1:
                    print(f'Beginning level {self.__last_half_period_level}, '
                          f'{half_period_count} half-period '
                          f'of {average_duration:.0f} ticks.')
                else:
                    print(f'Beginning level {self.__last_half_period_level}, '
                          f'{half_period_count} half-periods '
                          f'of ~{average_duration:.1f} '
                          f'({self.__last_half_period_durations.min}-'
                          f'{self.__last_half_period_durations.max}) '
                          f'ticks each.')

                    if abs(average_duration - 855) < DURATION_TOLERANCE:
                        self.__bits.extend([0] * (half_period_count // 2))
                    elif abs(average_duration - 1710) < DURATION_TOLERANCE:
                        self.__bits.extend([1] * (half_period_count // 2))
                    else:
                        self.__bits = []

                    while len(self.__bits) >= 8:
                        byte = int(''.join(str(b) for b in self.__bits[:8]), 2)
                        text = f'{byte:08b} = {byte:#04x}'
                        if 0x20 <= byte < 0x80:
                            text += f" '{chr(byte)}'"
                        print(text)
                        self.__bits[:8] = []

            self.__last_half_period_level = level
            self.__last_half_period_durations = DurationSet()

        self.__last_half_period_durations.add(duration)

        self.__last_level = level
        self.__last_level_tick = tick


def main():
    meter = TapeInterfaceMeter()
    with zx.Emulator(headless=HEADLESS,
                     extra_environment=[meter]) as app:
        # Boot to the BASIC prompt.
        app.run(duration=3)

        # 10 SAVE "x"
        # RUN
        app.generate_key_strokes(
            10, 'S', 'SS+P', *'BASIC', 'SS+P', 'ENTER',
            'R', 'ENTER')

        # <ENTER key stroke to start tape>
        meter.reporting = True
        app.generate_key_strokes('ENTER')

        # Run for a while and report some tape half-periods.
        app.run(duration=10)


if __name__ == '__main__':
    main()

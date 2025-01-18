#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2025 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import zx

# Change to see the emulator screen.
SHOW_SCREEN = False


class DurationSet(object):
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


class MySpectrum48(zx.Emulator):
    def __init__(self):
        super().__init__(speed_factor=1 if SHOW_SCREEN else None)
        self.set_on_output_callback(self.__on_output)

        self.__report = False
        self.__last_ear_level = 1
        self.__last_ear_level_tick = 0
        self.__last_half_period_level = 1
        self.__last_half_period_durations = DurationSet()

    def __on_output(self, addr, value):
        if addr & 0xff != 0xfe:
            return

        ear_level = (value >> 3) & 1
        if self.__last_ear_level == ear_level:
            return

        TICKS_PER_FRAME = 69888  # TODO
        tick = self.frame_count * TICKS_PER_FRAME + self.ticks_since_int
        duration = tick - self.__last_ear_level_tick

        half_period_count = self.__last_half_period_durations.count
        average_duration = self.__last_half_period_durations.average
        duration_delta = abs(average_duration - duration)
        DURATION_TOLERANCE = 10
        if duration_delta > DURATION_TOLERANCE:
            if self.__report:
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

            self.__last_half_period_level = ear_level
            self.__last_half_period_durations = DurationSet()

        self.__last_half_period_durations.add(duration)

        self.__last_ear_level = ear_level
        self.__last_ear_level_tick = tick

    def measure_tape_interface_parameters(self):
        self.reset_and_wait()

        # 10 SAVE "x"
        # RUN
        self.generate_key_strokes(
            10, 'S', 'SS+P', *'BASIC', 'SS+P', 'ENTER',
            'R', 'ENTER')

        # <ENTER key stroke to start tape>
        self.__report = True
        self.generate_key_strokes('ENTER')

        # Run for 5 seconds and report some tape half-periods.
        super().run(duration=10)


def main():
    with MySpectrum48() as app:
        app.measure_tape_interface_parameters()


if __name__ == "__main__":
    main()

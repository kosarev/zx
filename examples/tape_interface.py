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


class MySpectrum48(zx.Emulator):
    def __init__(self):
        super().__init__(speed_factor=1 if SHOW_SCREEN else None)
        self.set_on_output_callback(self.__on_output)

        self.__report = False
        self.__last_ear_level = 1
        self.__last_ear_level_tick = 0
        self.__last_half_period_level = 1
        self.__last_half_period_duration = 0
        self.__last_half_period_count = 0

    def __on_output(self, addr, value):
        if addr & 0xff != 0xfe:
            return

        ear_level = (value >> 3) & 1
        if self.__last_ear_level == ear_level:
            return

        TICKS_PER_FRAME = 69888  # TODO
        tick = self.frame_count * TICKS_PER_FRAME + self.ticks_since_int
        duration = tick - self.__last_ear_level_tick

        if self.__last_half_period_duration == duration:
            self.__last_half_period_count += 1
        else:
            if self.__report:
                print(f'Beginning level {self.__last_ear_level}, '
                      f'{self.__last_half_period_count} half-period(s) '
                      f'of {self.__last_half_period_duration} ticks each.')

            self.__last_half_period_level = ear_level
            self.__last_half_period_duration = duration
            self.__last_half_period_count = 1

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
        super().run(duration=5)


def main():
    with MySpectrum48() as app:
        app.measure_tape_interface_parameters()


if __name__ == "__main__":
    main()

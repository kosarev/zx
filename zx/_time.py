#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

from __future__ import annotations

import math
import time


# A point in emulated time: an integer count of ticks at a resolution
# of ticks_per_second ticks a second.
# Exact; to_float_seconds() is for presentation boundaries only.
class Time:
    def __init__(self, count: int, *, ticks_per_second: int) -> None:
        self.count = count
        self.ticks_per_second = ticks_per_second

    def __lt__(self, other: Time) -> bool:
        return (self.count * other.ticks_per_second <
                other.count * self.ticks_per_second)

    def __le__(self, other: Time) -> bool:
        return (self.count * other.ticks_per_second <=
                other.count * self.ticks_per_second)

    # Results take the resolution that represents both operands
    # exactly.
    def __add__(self, other: Time) -> Time:
        rate = math.lcm(self.ticks_per_second, other.ticks_per_second)
        return Time(self.count * (rate // self.ticks_per_second) +
                    other.count * (rate // other.ticks_per_second),
                    ticks_per_second=rate)

    def __sub__(self, other: Time) -> Time:
        rate = math.lcm(self.ticks_per_second, other.ticks_per_second)
        return Time(self.count * (rate // self.ticks_per_second) -
                    other.count * (rate // other.ticks_per_second),
                    ticks_per_second=rate)

    def to_float_seconds(self) -> float:
        return self.count / self.ticks_per_second


def get_timestamp() -> float:
    # TODO: We can use this since Python 3.7.
    # return time.time_ns() / (10 ** 9)
    return time.time()


def get_elapsed_time(timestamp: float) -> float:
    return get_timestamp() - timestamp

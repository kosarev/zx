#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import time


# A point in emulated time: an integer count of ticks at a resolution
# of ticks_per_second ticks a second.
# Exact; to_float_seconds() is for presentation boundaries only.
class Time:
    def __init__(self, count: int, *, ticks_per_second: int) -> None:
        self.count = count
        self.ticks_per_second = ticks_per_second

    def advance(self, ticks: int) -> None:
        self.count += ticks

    def to_float_seconds(self) -> float:
        return self.count / self.ticks_per_second


def get_timestamp() -> float:
    # TODO: We can use this since Python 3.7.
    # return time.time_ns() / (10 ** 9)
    return time.time()


def get_elapsed_time(timestamp: float) -> float:
    return get_timestamp() - timestamp

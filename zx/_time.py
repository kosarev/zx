# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import time


class Time(object):
    def __init__(self):
        self._seconds = 0

    def get(self):
        return self._seconds

    def advance(self, s):
        self._seconds += s


def get_timestamp():
    # TODO: We can use this since Python 3.7.
    # return time.time_ns() / (10 ** 9)
    return time.time()


def get_elapsed_time(timestamp):
    return get_timestamp() - timestamp

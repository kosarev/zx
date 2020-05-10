# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


class Error(Exception):
    """Basic exception for the whole ZX module."""
    def __init__(self, reason, id=None):
        super().__init__(reason)

        if id:
            self.id = id

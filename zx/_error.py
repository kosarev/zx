# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.

from ._except import EmulatorException


class Error(EmulatorException):
    """Basic exception for the whole ZX module."""
    def __init__(self, reason, id=None):
        super().__init__(reason)

        if id:
            self.id = id


USER_ERRORS = Error, IOError


def verbalize_error(e):
    if isinstance(e, Error):
        reason, = e.args
        args = [reason]
    elif isinstance(e, IOError):
        code, reason = e.args
        args = ['%s (code %s).' % (reason, code)]
        if isinstance(e, FileNotFoundError):
            args.insert(0, e.filename)
    else:
        args = [type(e).__name__] + ['%s' % x for x in e.args]
    return ': '.join(args)

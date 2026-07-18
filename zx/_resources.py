#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

"""The package's bundled data files (ROMs, fonts)."""

import importlib.resources

RESOURCES = importlib.resources.files('zx')

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import json

from ._binary import Bytes
from ._data import DataRecord
from ._error import Error


class ZXFile(DataRecord, format_name='ZX'):

    # Decode a .zx JSON file into the DataRecord type named by its
    # top-level 'type' field. Only allowlisted types are accepted.
    @classmethod
    def decode(cls, filename: str, image: Bytes) -> DataRecord:
        try:
            d = json.loads(bytes(image).decode('utf-8'))
        except (ValueError, UnicodeDecodeError) as e:
            raise Error(f"Cannot parse '{filename}' as a .zx file: {e}.")
        return DataRecord.from_json(d)

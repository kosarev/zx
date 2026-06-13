#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import pathlib
import typing

from ._binary import Bytes
from ._data import ArchiveFile
from ._data import DataRecord
from ._error import Error
from ._rzx import RZXFile
from ._scr import _SCRSnapshot
from ._sna import SNASnapshot
from ._tap import TAPFile
from ._tzx import TZXFile
from ._wav import WAVFile
from ._z80snapshot import Z80Snapshot
from ._zip import ZIPFile
from ._zx import ZXFile
from ._zxb import ZXBasicCompilerProgram


def _open_file_or_url(path: str) -> typing.Any:
    if path.startswith(('http:', 'https:', 'ftp:')):
        import urllib.error
        import urllib.request
        try:
            HEADERS = {
                'User-Agent': 'Mozilla/5.0 (Windows; U; Windows NT 5.1; '
                              'en-US; rv:1.9.0.7) Gecko/2009021910 '
                              'Firefox/3.0.7',
            }
            req = urllib.request.Request(path, headers=HEADERS)
            return urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            raise Error(
                f'Cannot read remote file: {e.reason}, code {e.code}.')

    return pathlib.Path(path).open('rb')


def detect_file_format(image: None | Bytes,
                       filename_extension: str) -> None | type[DataRecord]:
    KNOWN_FORMATS = [
        ('.zx', None, ZXFile),
        ('.zxb', None, ZXBasicCompilerProgram),
        ('.rzx', b'RZX!', RZXFile),
        ('.scr', None, _SCRSnapshot),
        ('.tap', None, TAPFile),
        ('.tzx', b'ZXTape!', TZXFile),
        ('.wav', b'RIFF', WAVFile),
        ('.sna', None, SNASnapshot),
        ('.z80', None, Z80Snapshot),
        ('.zip', b'PK\x03\x04', ZIPFile),
    ]

    filename_extension = filename_extension.lower()

    # First, try formats without signatures.
    for ext, signature, format in KNOWN_FORMATS:
        if not signature and filename_extension == ext:
            return format

    # Then, look at the signature.
    if image:
        for ext, signature, format in KNOWN_FORMATS:
            if signature and image[:len(signature)] == signature:
                return format

    # Finally, just try to guess by the given extension.
    for ext, signature, format in KNOWN_FORMATS:
        if filename_extension == ext:
            return format

    return None


def _parse_archive(format: type[ArchiveFile], image: Bytes) -> (
        list[tuple[str, type[DataRecord], Bytes]]):
    candidates: list[tuple[str, type[DataRecord], Bytes]] = []
    for member_name, member_image in format.read_files(image):
        ext = pathlib.Path(member_name).suffix
        member_format = detect_file_format(member_image, ext)

        if not member_format:
            continue

        # Recursively parse member archives.
        if issubclass(member_format, ArchiveFile):
            candidates.extend(_parse_archive(member_format, member_image))
            continue

        candidates.append((member_name, member_format, member_image))

    return candidates


def parse_file_image(filename: str, image: Bytes) -> DataRecord:
    ext = pathlib.Path(filename).suffix
    format = detect_file_format(image, ext)
    if not format:
        raise Error(f"Cannot determine the format of file '{filename}'.")

    if issubclass(format, ArchiveFile):
        candidates = _parse_archive(format, image)
        if len(candidates) == 0:
            raise Error(f'No files of known formats in archive {filename!r}.')

        if len(candidates) > 1:
            names = ', '.join(repr(n) for n, f, im in candidates)
            raise Error(
                f'More than one file of a known format in '
                f'archive {filename!r}: {names}.')

        filename, format, image = candidates[0]

    return format.decode(filename, image)


def parse_file(filename: str) -> DataRecord:
    with _open_file_or_url(filename) as f:
        image = f.read()

    return parse_file_image(filename, image)

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import os
from ._data import ArchiveFileFormat
from ._error import Error
from ._rzx import RZXFileFormat
from ._scr import SCRFileFormat
from ._tap import TAPFileFormat
from ._tzx import TZXFileFormat
from ._wav import WAVFileFormat
from ._z80snapshot import Z80SnapshotFormat
from ._zip import ZIPFileFormat
from ._zxb import ZXBasicCompilerSourceFormat


def _open_file_or_url(path):
    if path.startswith(('http:', 'https:', 'ftp:')):
        import urllib.request
        import urllib.error
        try:
            HEADERS = {
                'User-Agent': 'Mozilla/5.0 (Windows; U; Windows NT 5.1; '
                              'en-US; rv:1.9.0.7) Gecko/2009021910 '
                              'Firefox/3.0.7',
            }
            req = urllib.request.Request(path, headers=HEADERS)
            return urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            raise Error('Cannot read remote file: %s, code %d.' % (
                            e.reason, e.code))

    return open(path, 'rb')


def detect_file_format(image, filename_extension):
    KNOWN_FORMATS = [
        ('.zxb', None, ZXBasicCompilerSourceFormat),
        ('.rzx', b'RZX!', RZXFileFormat),
        ('.scr', None, SCRFileFormat),
        ('.tap', None, TAPFileFormat),
        ('.tzx', b'ZXTape!', TZXFileFormat),
        ('.wav', b'RIFF', WAVFileFormat),
        ('.z80', None, Z80SnapshotFormat),
        ('.zip', b'PK\x03\x04', ZIPFileFormat),
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


def _parse_archive(format, image):
    candidates = []
    for member_name, member_image in format().read_files(image):
        base, ext = os.path.splitext(member_name)
        member_format = detect_file_format(member_image, ext)

        if not member_format:
            continue

        # Recursively parse member archives.
        if issubclass(member_format, ArchiveFileFormat):
            candidates.extend(_parse_archive(member_format, member_image))
            continue

        candidates.append((member_name, member_format, member_image))

    return candidates


def _parse_file_image(filename, image):
    base, ext = os.path.splitext(filename)
    format = detect_file_format(image, ext)
    if not format:
        raise Error('Cannot determine the format of file %r.' % filename)

    if issubclass(format, ArchiveFileFormat):
        candidates = _parse_archive(format, image)
        if len(candidates) == 0:
            raise Error('No files of known formats in archive %r.' %
                        filename)

        if len(candidates) > 1:
            raise Error(
                'More than one file of a known format in archive %r: %s.' % (
                    filename, ', '.join(repr(n) for n, f, im in candidates)))

        filename, format, image = candidates[0]

    return format().parse(filename, image)


def parse_file(filename):
    with _open_file_or_url(filename) as f:
        image = f.read()

    return _parse_file_image(filename, image)

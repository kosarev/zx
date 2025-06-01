#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2025 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import typing
import collections
import os
import sys

from ._binary import Bytes
from ._data import ArchiveFile
from ._data import DataRecord
from ._data import MachineSnapshot
from ._data import SoundFile
from ._error import Error
from ._error import USER_ERRORS
from ._error import verbalize_error
from ._except import EmulationExit
from ._file import detect_file_format
from ._file import parse_file
from ._file import parse_file_image
from ._rzx import make_rzx
from ._rzx import RZXFile
from ._spectrum import Profile
from ._spectrum import Spectrum
from ._spectrum import Spectrum48
from ._spectrum import Spectrum128


def pop_argument(args: list[str], error: str) -> str:
    if not args:
        raise Error(error)
    return args.pop(0)


def pop_option(args: list[str], option: str) -> bool:
    if args[0:1] != [option]:
        return False
    args.pop(0)
    return True


def handle_extra_arguments(args: list[str]) -> None:
    if args:
        raise Error('Extra argument %r.' % args[0])


def run(args: list[str]) -> None:
    model = Spectrum128 if pop_option(args, '--128') else Spectrum48

    filename = None
    if args:
        filename = args.pop(0)
        handle_extra_arguments(args)

    with Spectrum(model=model) as app:
        if filename:
            app._load_file(filename)
        app.run()


def profile(args: list[str]) -> None:
    file_to_run = pop_argument(args, "The file to run is not specified.")
    profile_filename = pop_argument(args, "The profile filename is not "
                                          "specified.")
    handle_extra_arguments(args)

    profile = Profile()
    with Spectrum(profile=profile) as app:
        app._load_file(file_to_run)
        app.run()

    # TODO: Amend profile data by reading them out first instead
    # of overwriting.
    with open(profile_filename, 'wt') as f:
        # TODO: mypy false positive.
        for addr, annot in profile:  # type: ignore[attr-defined]
            print('@0x%04x %s' % (addr, annot), file=f)


def dump(args: list[str]) -> None:
    if not args:
        raise Error('The file to dump is not specified.')

    filename = args.pop(0)
    handle_extra_arguments(args)

    print(parse_file(filename).dumps())


def looks_like_filename(s: str) -> bool:
    return '.' in s


def usage() -> None:
    print('Usage:')
    print('  zx [run] [--128] [<file>]')
    print('  zx [convert] <from-file> <to-filename>')
    print('  zx profile <file-to-run> <profile-filename>')
    print('  zx dump <file>')
    print('  zx help')
    sys.exit()


def test_file(filename: str, batch_mode: bool) -> None:
    def move(dest_dir: str) -> None:
        os.makedirs(dest_dir, exist_ok=True)

        # Make sure the destination filename is unique.
        dest_filename = filename
        while True:
            dest_path = os.path.join(dest_dir, dest_filename)
            if not os.path.exists(dest_path):
                break

            dest_filename, ext = os.path.splitext(dest_filename)
            r = dest_filename.rsplit('--', maxsplit=1)
            if len(r) == 1:
                dest_filename = r[0] + '--2'
            else:
                dest_filename = (r[0] + '--' + str(int(r[1]) + 1))

            dest_filename = dest_filename + ext

        os.rename(filename, dest_path)
        print('%r moved to %r' % (filename, dest_dir))

    def match_bytes(b1: Bytes, b2: Bytes, path: str) -> None:
        if b1 == b2:
            return

        mismatch_count = None
        for i, (c1, c2) in enumerate(zip(b1, b2)):
            mismatch = c1 != c2
            print(f'{i} {c1:02x} {c2:02x}', '*' if mismatch else '')
            if mismatch_count is None:
                if mismatch:
                    mismatch_count = 10
            else:
                if mismatch_count == 0:
                    assert 0
                else:
                    mismatch_count -= 1

        assert 0

    def match(a: typing.Any, b: typing.Any, path: str = '') -> None:
        if isinstance(a, bytearray):
            a = bytes(a)
        if isinstance(b, bytearray):
            b = bytes(b)

        if type(a) is not type(b):
            assert 0, (type(a), type(b))

        if isinstance(a, (int, str)):
            assert a == b, (path, a, b)
        elif isinstance(a, bytes):
            match_bytes(a, b, path)
        elif isinstance(a, (tuple, list)):
            for i, (ea, eb) in enumerate(zip(a, b)):
                match(ea, eb, f'{path}.{type(a).__qualname__}[{i}]')
        elif isinstance(a, DataRecord):
            for (na, va), (nb, vb) in zip(a, b):
                assert na == nb
                match(va, vb, f'{path}.{na}')
        else:
            assert 0, type(a)

    try:
        print(repr(filename))

        with open(filename, 'rb') as f:
            image = f.read()
        file = parse_file_image(filename, image)

        if isinstance(file, MachineSnapshot):
            match(image, file.encode())

            unified = file.to_unified_snapshot()
            unified2 = type(file).from_snapshot(unified).to_unified_snapshot()
            match(unified, unified2)
        elif isinstance(file, RZXFile):
            with Spectrum(headless=True) as app:
                app._run_file(filename)
        else:
            raise Error(f"Don't know how to test {file}",
                        id='not_testable')
    except EmulationExit as e:
        pass
    except Exception as e:
        if not batch_mode:
            raise

        id = 'exception_raised'
        if isinstance(e, Error):
            id = e.id if e.id is not None else 'error_without_id'
        move(id)
        return

    if batch_mode:
        move('passed')


def test(args: list[str]) -> None:
    batch_mode = False
    for arg in args:
        if arg == '--batch':
            batch_mode = True
            continue

        test_file(arg, batch_mode)


def fast_forward(args: list[str]) -> None:
    for filename in args:
        with Spectrum() as app:
            app._run_file(filename, fast_forward=True)


def _convert_tape_to_snapshot(src: DataRecord, src_filename: str,
                              src_format: type[DataRecord],
                              dest_filename: str,
                              dest_format: type[DataRecord]) -> None:
    assert issubclass(src_format, SoundFile), src_format
    assert issubclass(dest_format, MachineSnapshot), dest_format

    with Spectrum(headless=True) as app:
        app.load_tape(src_filename)
        app._save_snapshot_file(dest_format, dest_filename)


def _convert_tape_to_tape(src: DataRecord, src_filename: str,
                          src_format: type[DataRecord],
                          dest_filename: str,
                          dest_format: type[DataRecord]) -> None:
    assert isinstance(src, SoundFile)
    assert issubclass(src_format, SoundFile), src_format
    assert issubclass(dest_format, SoundFile), dest_format
    dest_format.save_from_pulses(dest_filename, src.get_pulses())


def _convert_snapshot_to_snapshot(src: DataRecord,
                                  src_filename: str,
                                  src_format: type[DataRecord],
                                  dest_filename: str,
                                  dest_format: type[DataRecord]) -> None:
    assert issubclass(src_format, MachineSnapshot), src_format
    assert issubclass(dest_format, MachineSnapshot), dest_format

    with Spectrum(headless=True) as app:
        app._load_file(src_filename)
        app._save_snapshot_file(dest_format, dest_filename)


def convert_file(src_filename: str, dest_filename: str) -> None:
    src = parse_file(src_filename)
    src_format = type(src)
    # print(src, '->', dest_filename)

    _, dest_ext = os.path.splitext(dest_filename)
    dest_format = detect_file_format(image=None, filename_extension=dest_ext)
    if not dest_format:
        raise Error('Cannot determine the format of file %r.' % (
                        dest_filename))

    CONVERTERS: list[tuple[
            type[DataRecord], type[DataRecord],
            typing.Callable[[DataRecord, str, type[DataRecord],
                             str, type[DataRecord]], None]]] = [
        (SoundFile, SoundFile,
         _convert_tape_to_tape),
        (SoundFile, MachineSnapshot,
         _convert_tape_to_snapshot),
        (MachineSnapshot, MachineSnapshot,
         _convert_snapshot_to_snapshot),
    ]

    for sf, df, conv in CONVERTERS:
        if issubclass(src_format, sf) and issubclass(dest_format, df):
            conv(src, src_filename, src_format, dest_filename, dest_format)
            return

    raise Error("Don't know how to convert from %s to %s files." % (
                src_format.FORMAT_NAME,
                dest_format.FORMAT_NAME))


def convert(args: list[str]) -> None:
    if not args:
        raise Error('The file to convert from is not specified.')
    src_filename = args.pop(0)

    if not args:
        raise Error('The file to convert to is not specified.')
    dest_filename = args.pop(0)

    handle_extra_arguments(args)

    convert_file(src_filename, dest_filename)


def handle_command_line(args: list[str]) -> None:
    # Guess the command by the arguments.
    if (not args or
            args[0].startswith('--') or
            len(args) == 1 and looks_like_filename(args[0])):
        run(args)
        return

    if (len(args) == 2 and looks_like_filename(args[0]) and
            looks_like_filename(args[1])):
        convert(args)
        return

    # Handle an explicitly specified command.
    command = args[0]
    if command in ['help', '-help', '--help',
                   '-h', '-?',
                   '/h', '/help']:
        usage()
        return

    COMMANDS = {
        'convert': convert,
        'dump': dump,
        'profile': profile,
        'run': run,

        # TODO: Hidden commands for internal use.
        '__test': test,
        '__ff': fast_forward,
    }

    if command not in COMMANDS:
        raise Error('Unknown command %r.' % command)

    COMMANDS[command](args[1:])


def main(args: None | list[str] = None) -> None:
    if args is None:
        args = sys.argv[1:]

    try:
        handle_command_line(args)
    except EmulationExit:
        pass
    except USER_ERRORS as e:
        sys.exit('zx: %s' % verbalize_error(e))


if __name__ == "__main__":
    # import cProfile
    # cProfile.run('main()')
    main()

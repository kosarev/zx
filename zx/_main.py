#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import typing
import collections
import os
import sys
from ._data import ArchiveFileFormat
from ._data import SnapshotFormat
from ._data import SoundFileFormat
from ._data import SoundFile
from ._data import FileFormat
from ._data import File
from ._data import MachineSnapshot
from ._emulator import Emulator
from ._emulator import Profile
from ._error import Error
from ._error import USER_ERRORS
from ._error import verbalize_error
from ._except import EmulationExit
from ._file import detect_file_format
from ._file import parse_file
from ._rzx import make_rzx
from ._rzx import RZXFile


def pop_argument(args: list[str], error: str) -> str:
    if not args:
        raise Error(error)
    return args.pop(0)


def handle_extra_arguments(args: list[str]) -> None:
    if args:
        raise Error('Extra argument %r.' % args[0])


def run(args: list[str]) -> None:
    filename = None
    if args:
        filename = args.pop(0)
        handle_extra_arguments(args)

    with Emulator() as app:
        if filename:
            app._load_file(filename)
        app.run()


def profile(args: list[str]) -> None:
    file_to_run = pop_argument(args, "The file to run is not specified.")
    profile_filename = pop_argument(args, "The profile filename is not "
                                          "specified.")
    handle_extra_arguments(args)

    profile = Profile()
    with Emulator(profile=profile) as app:
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
    print('  zx [run] [<file>]')
    print('  zx [convert] <from-file> <to-filename>')
    print('  zx profile <file-to-run> <profile-filename>')
    print('  zx dump <file>')
    print('  zx help')
    sys.exit()


def test_file(filename: str) -> bool:
    print('%r' % filename)

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

    with Emulator(speed_factor=None) as app:
        try:
            app._run_file(filename)
            move('passed')
        except Error as e:
            move(e.id)
        except Exception as e:
            # TODO: Refine.
            return False

    return True


def test(args: list[str]) -> None:
    for filename in args:
        if not test_file(filename):
            break


def fastforward(args: list[str]) -> None:
    for filename in args:
        with Emulator(speed_factor=0) as app:
            app._run_file(filename)


def _convert_tape_to_snapshot(src: File, src_filename: str,
                              src_format: type[FileFormat],
                              dest_filename: str,
                              dest_format: type[FileFormat]) -> None:
    assert issubclass(src_format, SoundFileFormat), src_format
    assert issubclass(dest_format, SnapshotFormat), dest_format

    with Emulator(speed_factor=None) as app:
        app.load_tape(src_filename)
        app._save_snapshot_file(dest_format, dest_filename)


def _convert_tape_to_tape(src: File, src_filename: str,
                          src_format: type[FileFormat],
                          dest_filename: str,
                          dest_format: type[FileFormat]) -> None:
    assert isinstance(src, SoundFile)
    assert issubclass(src_format, SoundFileFormat), src_format
    assert issubclass(dest_format, SoundFileFormat), dest_format
    dest_format().save_from_pulses(dest_filename, src.get_pulses())


def _convert_snapshot_to_snapshot(src: File,
                                  src_filename: str,
                                  src_format: type[FileFormat],
                                  dest_filename: str,
                                  dest_format: type[FileFormat]) -> None:
    assert issubclass(src_format, SnapshotFormat), src_format
    assert issubclass(dest_format, SnapshotFormat), dest_format

    with Emulator(speed_factor=None) as app:
        app._load_file(src_filename)
        app._save_snapshot_file(dest_format, dest_filename)


def convert_file(src_filename: str, dest_filename: str) -> None:
    src = parse_file(src_filename)
    src_format = src.get_format()
    # print(src, '->', dest_filename)

    _, dest_ext = os.path.splitext(dest_filename)
    dest_format = detect_file_format(image=None, filename_extension=dest_ext)
    if not dest_format:
        raise Error('Cannot determine the format of file %r.' % (
                        dest_filename))

    CONVERTERS: list[tuple[
            type[FileFormat], type[FileFormat],
            typing.Callable[[File, str, type[FileFormat],
                             str, type[FileFormat]], None]]] = [
        (SoundFileFormat, SoundFileFormat,
         _convert_tape_to_tape),
        (SoundFileFormat, SnapshotFormat,
         _convert_tape_to_snapshot),
        (SnapshotFormat, SnapshotFormat,
         _convert_snapshot_to_snapshot),
    ]

    for sf, df, conv in CONVERTERS:
        if issubclass(src_format, sf) and issubclass(dest_format, df):
            conv(src, src_filename, src_format, dest_filename, dest_format)
            return

    raise Error("Don't know how to convert from %s to %s files." % (
                src_format().get_name(),
                dest_format().get_name()))


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
        '__ff': fastforward,
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

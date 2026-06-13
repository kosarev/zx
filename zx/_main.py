#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import typing
import collections
import functools
import multiprocessing
import os
import platformdirs
import sys

from ._binary import Bytes
from ._data import ArchiveFile
from ._data import DataRecord
from ._data import MachinePlayback
from ._data import MachineSnapshot
from ._data import SoundFile
from ._data import Spectrum128
from ._error import Error
from ._error import USER_ERRORS
from ._error import verbalize_error
from ._device import BreakpointHit
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import FetchesLimitHit
from ._playback import PlaybackPlayer
from ._playback import PlaybackRecorder
from ._settings import GlobalSettingsManager
from ._except import EmulationExit
from ._file import detect_file_format
from ._file import parse_file
from ._file import parse_file_image
from ._zx import ZXFile
from ._rzx import make_rzx
from ._rzx import RZXFile
from ._emulator import Emulator
from ._spectrum import Profile
from ._spectrum import Spectrum
from ._data import UnifiedPlayback
from ._data import UnifiedSnapshot


def get_config_dir() -> str:
    path = str(platformdirs.user_config_dir('zx'))
    os.makedirs(path, exist_ok=True)
    return path


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
    model = None
    if pop_option(args, '--128'):
        model = Spectrum128

    filename = None
    if args:
        filename = args.pop(0)
        handle_extra_arguments(args)

    session_snapshot = os.path.join(get_config_dir(), 'session.zx')
    settings_file = os.path.join(get_config_dir(), 'settings.json')

    with Emulator(model=model, extra_devices=[
            GlobalSettingsManager(settings_file)]) as app:
        if filename:
            app._load_file(filename)
        elif os.path.exists(session_snapshot):
            app._load_file(session_snapshot)
        try:
            app.run()
        except EmulationExit:
            pass
        app._save_snapshot_file(UnifiedSnapshot, session_snapshot)


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
    print('  zx [run] [--128] [<file>]')
    print('  zx [convert] <from-file> <to-filename>')
    print('  zx profile <file-to-run> <profile-filename>')
    print('  zx dump <file>')
    print('  zx help')
    sys.exit()


def test_file(filename: str, batch_mode: bool,
              parallel_mode: bool = False) -> None:
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
        if not parallel_mode:
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
            with Emulator(headless=True) as app:
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
    parallel_mode = False
    filenames = []
    for arg in args:
        if arg == '--batch':
            batch_mode = True
            continue

        if arg == '--parallel':
            parallel_mode = True
            continue

        filenames.append(arg)

    if not parallel_mode:
        for filename in filenames:
            test_file(filename, batch_mode)
        return

    worker = functools.partial(test_file, batch_mode=batch_mode,
                               parallel_mode=True)
    with multiprocessing.Pool() as pool:
        for _ in pool.imap_unordered(worker, filenames):
            pass


# TODO: Extract playback recovery into _playback_recovery.py and
# eventually promote it to a public playback_recovery submodule.
# TODO: Wire on-the-fly recovery into _load_input_recording() so
# non-conforming recordings (e.g., SPIN v0.5 ones) are corrected
# before they reach the player.
class _PlaybackRecoverer(Spectrum):
    def __init__(self, *,
                 playback_player: PlaybackPlayer | None = None) -> None:
        self._player = playback_player or PlaybackPlayer()
        self._recorder = PlaybackRecorder(active=True)
        super().__init__()

    # The recording is loaded here, not in __init__, because the player
    # device only receives StartPlayback once the Emulator has assembled
    # the device set and handed this core the live dispatcher.
    def recover(self, playback: MachinePlayback) -> UnifiedPlayback:
        self._load_input_recording(playback)
        try:
            self.run()
        except EmulationExit:
            pass
        return self._recorder.make_playback()

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if isinstance(event, FetchesLimitHit):
            # Some emulators, e.g., SPIN, may store an interrupt point in
            # the middle of a IX- or IY-prefixed instruction, so we
            # continue until such instruction, if any, is completed.
            if self.iregp_kind != 'hl':
                self.fetches_limit = 1

        super().on_event(event, devices)


class _SPINPlaybackPlayer(PlaybackPlayer):
    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        # Yield to _SPINPlaybackRecoverer when the trailing IN correction
        # is pending; otherwise PlaybackPlayer raises too_many_input_samples.
        if isinstance(event, FetchesLimitHit) and self.has_remaining_samples:
            return
        super().on_event(event, devices)


class _SPINPlaybackRecoverer(_PlaybackRecoverer):
    def __init__(self) -> None:
        super().__init__(playback_player=_SPINPlaybackPlayer())

        # The bytes-saving ROM procedure needs special processing.
        self.set_breakpoint(0x04d4)

        # TODO: SPIN v0.5 alters ROM to implement fast tape loading
        # (writes 0xf5 at 0x1f47), which affects recorded RZX files.
        # No known recording relies on the patch so far, so it is not
        # applied; we'll get back to it when investigating non-working
        # RZX files. When a reproducer is found, apply the patch here
        # and, once the recorder exists, capture the ROM difference as
        # a MemoryBlock(addr=0x1f47, rom_page=0, ...) in the key-frame
        # snapshots, so that the recovered playback carries its own
        # ROM difference and plays on a strictly conforming emulator
        # with no quirk knowledge.

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if isinstance(event, BreakpointHit):
            # SPIN v0.5 skips the bytes-saving ROM procedure in fast save mode.
            if self.pc == 0x04d4:
                sp = self.sp
                self.pc = self.read16(sp)
                self.sp = sp + 2

        if isinstance(event, FetchesLimitHit):
            # SPIN v0.5 doesn't update the fetch counter if the last
            # instruction in a frame is IN.
            if self._player.has_remaining_samples:
                self.fetches_limit = 1

        super().on_event(event, devices)


def recover_playback(playback: MachinePlayback) -> UnifiedPlayback:
    unified = playback.to_unified_playback()
    recoverer: _PlaybackRecoverer = (
        _SPINPlaybackRecoverer() if unified.is_spin_v05
        else _PlaybackRecoverer())
    with Emulator(core=recoverer, headless=True,
                  playback_player=recoverer._player,
                  playback_recorder=recoverer._recorder):
        return recoverer.recover(playback)


def recover_file(filename: str) -> None:
    file = parse_file(filename)
    if not isinstance(file, MachinePlayback):
        raise Error(f"Don't know how to recover {file.FORMAT_NAME}; "
                    f'a playback is expected.',
                    id='not_recoverable')

    recover_playback(file)


def recover(args: list[str]) -> None:
    for filename in args:
        recover_file(filename)


def fast_forward(args: list[str]) -> None:
    for filename in args:
        with Emulator() as app:
            app._run_file(filename, fast_forward=True)


def _convert_tape_to_snapshot(src: DataRecord, src_filename: str,
                              src_format: type[DataRecord],
                              dest_filename: str,
                              dest_format: type[DataRecord]) -> None:
    assert issubclass(src_format, SoundFile), src_format
    assert issubclass(dest_format, MachineSnapshot), dest_format

    with Emulator(headless=True) as app:
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


def _convert_any_to_zx(src: DataRecord,
                       src_filename: str,
                       src_format: type[DataRecord],
                       dest_filename: str,
                       dest_format: type[DataRecord]) -> None:
    with open(dest_filename, 'wb') as f:
        # Use Unix line endings regardless of platform for consistency.
        f.write((src.dumps() + '\n').encode('utf-8'))


def _convert_snapshot_to_snapshot(src: DataRecord,
                                  src_filename: str,
                                  src_format: type[DataRecord],
                                  dest_filename: str,
                                  dest_format: type[DataRecord]) -> None:
    assert issubclass(src_format, MachineSnapshot), src_format
    assert issubclass(dest_format, MachineSnapshot), dest_format

    with Emulator(headless=True) as app:
        app._load_file(src_filename)
        app._save_snapshot_file(dest_format, dest_filename)


def convert_file(src_filename: str, dest_filename: str) -> None:
    src = parse_file(src_filename)
    src_format = type(src)
    # print(src, '->', dest_filename)

    _, dest_ext = os.path.splitext(dest_filename)
    dest_format = detect_file_format(image=None, filename_extension=dest_ext)
    if not dest_format:
        raise Error("Cannot determine the format of file '%s'." % (
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
        (DataRecord, ZXFile, _convert_any_to_zx),
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

        'recover': recover,

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

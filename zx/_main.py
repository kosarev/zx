#!/usr/bin/env python3

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import contextlib
import functools
import multiprocessing
import pathlib
import sys
import time
import typing

import platformdirs

from ._ay import AY
from ._ay import AYPlayer
from ._binary import Bytes
from ._core import Core
from ._core import Profile
from ._core import RunEvents
from ._data import AYMusicFile
from ._data import AYStream
from ._data import DataRecord
from ._data import MachinePlayback
from ._data import MachineSnapshot
from ._data import PlaybackFile
from ._data import SnapshotFile
from ._data import SoundFile
from ._data import Spectrum128
from ._device import BreakpointHit
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import FetchesLimitHit
from ._device import IsTapePlayerStopped
from ._device import LoadTape
from ._device import PauseUnpauseTape
from ._device import RunQuantum
from ._emulator import Emulator
from ._emulator import Machine
from ._error import USER_ERRORS
from ._error import Error
from ._error import verbalize_error
from ._except import EmulationExit
from ._file import detect_file_format
from ._file import parse_file
from ._file import parse_file_image
from ._keyboard import Keyboard
from ._keyboard import make_key_strokes
from ._machines import get_spectrum_48k_snapshot
from ._playback import PlaybackPlayer
from ._playback import PlaybackRecorder
from ._rzx import RZXFile
from ._settings import GlobalSettingsManager
from ._sound import SDLSound
from ._tape import TapePlayer
from ._time import Time
from ._zx import ZXFile


def get_config_dir() -> pathlib.Path:
    path = pathlib.Path(platformdirs.user_config_dir('zx'))
    path.mkdir(parents=True, exist_ok=True)
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
        raise Error(f'Extra argument {args[0]!r}.')


# Waits out held rounds, keeping the process idle: the player
# session has no interactive channel to do the waiting the way the
# screen does it in the GUI.
class _HoldWaiter(Device):
    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if isinstance(event, RunQuantum) and event.held:
            time.sleep(min(event.wake_in or 0.05, 0.05))


# Plays an AY music stream: a session of the AY chip alone, driven
# by the stream player, with no Spectrum machine involved.
def _play_ay_stream(stream: AYStream) -> None:
    player = AYPlayer(stream)

    # A large device buffer rides out the late audio-thread wakeups
    # of an idle process; the queued-audio target must exceed the
    # buffer, or every pull of the audio thread drains the queue dry.
    # A player has no latency concern anyway.
    sound = SDLSound(num_buffer_samples=4096, latency_ms=200)

    with Emulator(machine=Machine(ay=AY(active=True)),
                  environment=[player, _HoldWaiter(), sound]) as app:
        # Give the last notes a second to ring out.
        tail = Time(stream.ticks_per_second,
                    ticks_per_second=stream.ticks_per_second)
        with contextlib.suppress(EmulationExit):
            app.run(until=player.get_end_time() + tail)


def run(args: list[str]) -> None:
    model = None
    if pop_option(args, '--128'):
        model = Spectrum128

    filename = None
    if args:
        filename = args.pop(0)
        handle_extra_arguments(args)

    file = None
    if filename:
        file = parse_file(filename)
        if isinstance(file, AYMusicFile):
            _play_ay_stream(file.to_ay_stream())
            return

    session_snapshot = get_config_dir() / 'session.zx'
    settings_file = get_config_dir() / 'settings.json'

    with Emulator(model=model, extra_environment=[
            GlobalSettingsManager(settings_file)]) as app:
        if file is not None:
            app._load(file)
        elif session_snapshot.exists():
            try:
                app._load_file(str(session_snapshot))
            except Exception as e:
                raise Error(
                    f"Cannot load the session file '{session_snapshot}': "
                    f'{e} If it was saved by an older version of zx, '
                    f'delete it.') from e
        with contextlib.suppress(EmulationExit):
            app.run()
        app._save_snapshot_file(MachineSnapshot, str(session_snapshot))


def profile(args: list[str]) -> None:
    file_to_run = pop_argument(args, 'The file to run is not specified.')
    profile_filename = pop_argument(args, 'The profile filename is not '
                                          'specified.')
    handle_extra_arguments(args)

    profile = Profile()
    with Emulator(profile=profile) as app:
        app._load_file(file_to_run)
        app.run()

    # TODO: Amend profile data by reading them out first instead
    # of overwriting.
    with pathlib.Path(profile_filename).open('w') as f:
        # TODO: mypy false positive.
        for addr, annot in profile:  # type: ignore[attr-defined]
            print(f'@0x{addr:04x} {annot}', file=f)


def dump(args: list[str]) -> None:
    if not args:
        raise Error('The file to dump is not specified.')

    filename = args.pop(0)
    handle_extra_arguments(args)

    print(parse_file(filename).dumps())


# Converts the given file to its unified representation and writes
# it out as a .zx file.
def unify(args: list[str]) -> None:
    if not args:
        raise Error('The file to unify is not specified.')
    src_filename = args.pop(0)

    if not args:
        raise Error('The file to write to is not specified.')
    dest_filename = args.pop(0)

    handle_extra_arguments(args)

    file = parse_file(src_filename)
    if isinstance(file, SnapshotFile):
        unified: DataRecord = file.to_machine_snapshot()
    elif isinstance(file, PlaybackFile):
        unified = file.to_machine_playback()
    elif isinstance(file, AYMusicFile):
        unified = file.to_ay_stream()
    else:
        raise Error(f"Don't know how to unify {type(file).FORMAT_NAME} "
                    f'files.', id='not_unifiable')

    with pathlib.Path(dest_filename).open('wb') as f:
        # Use Unix line endings regardless of platform for consistency.
        f.write((unified.dumps() + '\n').encode('utf-8'))


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
        pathlib.Path(dest_dir).mkdir(parents=True, exist_ok=True)

        # Make sure the destination filename is unique.
        dest_filename = filename
        while True:
            dest_path = pathlib.Path(dest_dir) / dest_filename
            if not dest_path.exists():
                break

            stem = pathlib.Path(dest_filename)
            ext = stem.suffix
            dest_filename = str(stem.with_suffix(''))
            r = dest_filename.rsplit('--', maxsplit=1)
            if len(r) == 1:
                dest_filename = r[0] + '--2'
            else:
                dest_filename = (r[0] + '--' + str(int(r[1]) + 1))

            dest_filename = dest_filename + ext

        pathlib.Path(filename).rename(dest_path)
        print(f'{filename!r} moved to {dest_dir!r}')

    def match_bytes(b1: Bytes, b2: Bytes, path: str) -> None:
        if b1 == b2:
            return

        mismatch_count = None
        for i, (c1, c2) in enumerate(zip(b1, b2, strict=False)):
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
            for i, (ea, eb) in enumerate(zip(a, b, strict=False)):
                match(ea, eb, f'{path}.{type(a).__qualname__}[{i}]')
        elif isinstance(a, DataRecord):
            for (na, va), (nb, vb) in zip(a, b, strict=False):
                assert na == nb
                match(va, vb, f'{path}.{na}')
        else:
            assert 0, type(a)

    try:
        if not parallel_mode:
            print(repr(filename))

        with pathlib.Path(filename).open('rb') as f:
            image = f.read()
        file = parse_file_image(filename, image)

        if isinstance(file, SnapshotFile):
            match(image, file.encode())

            unified = file.to_machine_snapshot()
            unified2 = type(file).from_snapshot(unified).to_machine_snapshot()
            match(unified, unified2)
        elif isinstance(file, AYMusicFile):
            match(image, file.encode())

            stream = file.to_ay_stream()
            stream2 = type(file).from_ay_music(stream).to_ay_stream()
            match(stream, stream2)
        elif isinstance(file, RZXFile):
            with Emulator(headless=True) as app:
                app._run_file(filename)
        else:
            raise Error(f"Don't know how to test {file}",
                        id='not_testable')
    except EmulationExit:
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
class _PlaybackRecoverer(Core):
    def __init__(self, *,
                 playback_player: PlaybackPlayer | None = None) -> None:
        self._player = playback_player or PlaybackPlayer()
        self._recorder = PlaybackRecorder(active=True)
        super().__init__()

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        # Some emulators, e.g., SPIN, may store an interrupt point in
        # the middle of a IX- or IY-prefixed instruction, so we
        # continue until such instruction, if any, is completed.
        if isinstance(event, FetchesLimitHit) and self.iregp_kind != 'hl':
            self.m1_fetches_to_stop = 1

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
        # SPIN v0.5 skips the bytes-saving ROM procedure in fast save mode.
        if isinstance(event, BreakpointHit) and self.pc == 0x04d4:
            sp = self.sp
            self.pc = self.read16(sp)
            self.sp = sp + 2

        # SPIN v0.5 doesn't update the fetch counter if the last
        # instruction in a frame is IN.
        if (isinstance(event, FetchesLimitHit) and
                self._player.has_remaining_samples):
            self.m1_fetches_to_stop = 1

        super().on_event(event, devices)


def recover_playback(playback: PlaybackFile) -> MachinePlayback:
    unified = playback.to_machine_playback()
    recoverer: _PlaybackRecoverer = (
        _SPINPlaybackRecoverer() if unified.is_spin_v05
        else _PlaybackRecoverer())
    # The recording is loaded after the Emulator has assembled the
    # device set, so the player receives StartPlayback.
    with Emulator(core=recoverer, headless=True,
                  playback_player=recoverer._player,
                  playback_recorder=recoverer._recorder) as emu:
        emu._load_input_recording(playback)
        with contextlib.suppress(EmulationExit):
            emu.run()
        return recoverer._recorder.make_playback()


def recover_file(filename: str) -> None:
    file = parse_file(filename)
    if not isinstance(file, PlaybackFile):
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


# Runs a private machine through the ROM's own loading process --
# boot, type LOAD "", play the tape to its end -- and saves the
# machine that results.
def _convert_tape_to_snapshot(src: DataRecord, src_filename: str,
                              dest_filename: str,
                              dest_format: type[DataRecord]) -> None:
    assert isinstance(src, SoundFile)
    assert issubclass(dest_format, SnapshotFile), dest_format

    core = Core()
    devices = Dispatcher([core, Keyboard(active=True), TapePlayer()])

    def current_time() -> Time:
        return Time(core.tick_count,
                    ticks_per_second=core.model._TICKS_PER_FRAME * 50)

    # Boot to the BASIC prompt.
    frames = 0
    while frames < 90:
        if RunEvents.END_OF_FRAME in RunEvents(core._run(devices)):
            frames += 1

    # LOAD ""
    strokes = make_key_strokes('J', 'SS+P', 'SS+P', 'ENTER',
                               start=current_time())
    for stroke in strokes:
        devices.notify(stroke)
    while current_time() < strokes[-1].time:
        core._run(devices)

    devices.notify(LoadTape(src))
    devices.notify(PauseUnpauseTape(False))

    while True:
        core._run(devices)

        stopped = IsTapePlayerStopped()
        devices.notify(stopped)
        if stopped.stopped:
            break

    snapshot = MachineSnapshot(core=core.to_snapshot())
    snapshot = get_spectrum_48k_snapshot().amended_with(snapshot)
    with pathlib.Path(dest_filename).open('wb') as f:
        f.write(dest_format.from_snapshot(snapshot).encode())


def _convert_tape_to_tape(src: DataRecord, src_filename: str,
                          dest_filename: str,
                          dest_format: type[DataRecord]) -> None:
    assert isinstance(src, SoundFile)
    assert issubclass(dest_format, SoundFile), dest_format
    dest_format.save_from_pulses(dest_filename, src.get_pulses())


def _convert_any_to_zx(src: DataRecord,
                       src_filename: str,
                       dest_filename: str,
                       dest_format: type[DataRecord]) -> None:
    with pathlib.Path(dest_filename).open('wb') as f:
        # Use Unix line endings regardless of platform for consistency.
        f.write((src.dumps() + '\n').encode('utf-8'))


def _convert_ay_music(src: DataRecord,
                      src_filename: str,
                      dest_filename: str,
                      dest_format: type[DataRecord]) -> None:
    assert isinstance(src, AYMusicFile)
    assert issubclass(dest_format, AYMusicFile), dest_format

    with pathlib.Path(dest_filename).open('wb') as f:
        f.write(dest_format.from_ay_music(src).encode())


def _convert_snapshot_to_snapshot(src: DataRecord,
                                  src_filename: str,
                                  dest_filename: str,
                                  dest_format: type[DataRecord]) -> None:
    assert isinstance(src, SnapshotFile)
    assert issubclass(dest_format, SnapshotFile), dest_format

    with Emulator(headless=True) as app:
        app._load_snapshot(src)
        app._save_snapshot_file(dest_format, dest_filename)


def convert_file(src_filename: str, dest_filename: str) -> None:
    src = parse_file(src_filename)
    src_format = type(src)
    # print(src, '->', dest_filename)

    dest_ext = pathlib.Path(dest_filename).suffix
    dest_format = detect_file_format(image=None, filename_extension=dest_ext)
    if not dest_format:
        raise Error(f"Cannot determine the format of file '{dest_filename}'.")

    CONVERTERS: list[tuple[
            type[DataRecord], type[DataRecord],
            typing.Callable[[DataRecord, str,
                             str, type[DataRecord]], None]]] = [
        (SoundFile, SoundFile,
         _convert_tape_to_tape),
        (SoundFile, SnapshotFile,
         _convert_tape_to_snapshot),
        (SnapshotFile, SnapshotFile,
         _convert_snapshot_to_snapshot),
        (AYMusicFile, AYMusicFile, _convert_ay_music),
        (DataRecord, ZXFile, _convert_any_to_zx),
    ]

    for sf, df, conv in CONVERTERS:
        if issubclass(src_format, sf) and issubclass(dest_format, df):
            conv(src, src_filename, dest_filename, dest_format)
            return

    raise Error(
        f"Don't know how to convert from {src_format.FORMAT_NAME} "
        f"to {dest_format.FORMAT_NAME} files.")


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
            (len(args) == 1 and looks_like_filename(args[0]))):
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
        '__unify': unify,
    }

    if command not in COMMANDS:
        raise Error(f'Unknown command {command!r}.')

    COMMANDS[command](args[1:])


def main(args: None | list[str] = None) -> None:
    """The ``zx`` command-line entry point.

    Parses ``args`` (defaulting to ``sys.argv[1:]``) and runs the
    requested command - run a file, convert between formats, dump, etc.
    User errors are reported and exit the process.
    """
    if args is None:
        args = sys.argv[1:]

    try:
        handle_command_line(args)
    except EmulationExit:
        pass
    except USER_ERRORS as e:
        sys.exit(f'zx: {verbalize_error(e)}')


if __name__ == '__main__':
    # import cProfile
    # cProfile.run('main()')
    main()

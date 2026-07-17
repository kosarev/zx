#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

from __future__ import annotations

import typing

from ._data import AYFrame
from ._data import AYMusicFile
from ._data import AYStream
from ._data import AYWrite
from ._data import ByteData
from ._data import DataRecord
from ._data import HexData
from ._data import _InlineJSONDict
from ._error import Error

if typing.TYPE_CHECKING:
    from ._binary import Bytes

# A PSG frame is one interrupt of the recording machine. With no
# frequency declared it is a 70,908-tick 128K frame, the authentic
# 50.02 Hz cadence.
_TICKS_PER_FRAME = 70908
_TICKS_PER_SECOND = 3546900

_SIGNATURE = b'PSG\x1a'


# A command of a PSG stream, one record per wire token, so the
# stream is reproduced byte-exactly by construction.
class PSGCommand(DataRecord):
    def encode_command(self) -> bytes:
        raise NotImplementedError


# A register write within the current frame.
class PSGWrite(PSGCommand):
    reg: int
    value: int

    def __init__(self, *, reg: int, value: int) -> None:
        super().__init__(reg=reg, value=value)

    def to_json(self) -> _InlineJSONDict:
        return _InlineJSONDict(reg=self.reg, value=self.value)

    def encode_command(self) -> bytes:
        return bytes((self.reg, self.value))


# The 0xff command: the next frame begins.
class PSGNextFrame(PSGCommand):
    def __init__(self) -> None:
        super().__init__()

    def to_json(self) -> _InlineJSONDict:
        return _InlineJSONDict()

    def encode_command(self) -> bytes:
        return b'\xff'


# The 0xfe command: skips four times the count of frames.
class PSGSkipFrames(PSGCommand):
    count: int

    def __init__(self, *, count: int) -> None:
        super().__init__(count=count)

    def to_json(self) -> _InlineJSONDict:
        return _InlineJSONDict(count=self.count)

    def encode_command(self) -> bytes:
        return bytes((0xfe, self.count))

    @property
    def num_frames(self) -> int:
        return self.count * 4


# The 0xfd command: the end of the stream.
class PSGEnd(PSGCommand):
    def __init__(self) -> None:
        super().__init__()

    def to_json(self) -> _InlineJSONDict:
        return _InlineJSONDict()

    def encode_command(self) -> bytes:
        return b'\xfd'


def _parse_commands(image: Bytes) -> list[PSGCommand]:
    commands: list[PSGCommand] = []

    i = 0
    while i < len(image):
        command = image[i]
        i += 1

        if command == 0xfd:
            commands.append(PSGEnd())
            break
        elif command == 0xff:
            commands.append(PSGNextFrame())
        elif command == 0xfe:
            if i >= len(image):
                raise Error('Truncated skip command in PSG stream.',
                            id='bad_psg_stream')
            commands.append(PSGSkipFrames(count=image[i]))
            i += 1
        elif command < 0x10:
            if i >= len(image):
                raise Error('Truncated write command in PSG stream.',
                            id='bad_psg_stream')
            commands.append(PSGWrite(reg=command, value=image[i]))
            i += 1
        else:
            raise Error(
                f'Unknown command 0x{command:02x} in PSG stream.',
                id='bad_psg_stream')

    return commands


# Frame-granular AY register dumps: the signature, a version byte, an
# interrupt frequency in Hz (0 means the default), ten reserved
# bytes, then the command stream, represented as one record per wire
# command. Bytes following an end-of-stream command, if any, are
# kept apart.
class PSGFile(AYMusicFile, format_name='PSG'):
    version: int
    frequency: int
    reserved: ByteData
    commands: list[PSGCommand]
    trailing: ByteData | None

    def __init__(self, *, version: int = 0, frequency: int = 0,
                 reserved: Bytes | ByteData = bytes(10),
                 commands: list[PSGCommand] | None = None,
                 trailing: Bytes | ByteData | None = None) -> None:
        super().__init__(
            version=version, frequency=frequency,
            reserved=HexData.wrap(reserved),
            commands=commands if commands is not None else [],
            trailing=HexData.wrap(trailing) if trailing is not None
            else None)

    @classmethod
    def from_ay_music(cls, music: AYMusicFile) -> PSGFile:
        stream = music.to_ay_stream()
        if stream.ticks_per_second != _TICKS_PER_SECOND:
            raise Error('Cannot represent the AY stream as PSG: '
                        f'unsupported rate {stream.ticks_per_second}.',
                        id='bad_psg_rate')
        if stream.ticks_per_frame == _TICKS_PER_FRAME:
            frequency = 0
        elif _TICKS_PER_SECOND % stream.ticks_per_frame == 0:
            frequency = _TICKS_PER_SECOND // stream.ticks_per_frame
        else:
            raise Error('Cannot represent the AY stream as PSG: '
                        f'unsupported frame of {stream.ticks_per_frame} '
                        f'ticks.', id='bad_psg_rate')

        commands: list[PSGCommand] = []
        frame = 0
        for f in stream.frames:
            gap = f.frame - frame
            while gap >= 4:
                count = min(gap // 4, 0xff)
                commands.append(PSGSkipFrames(count=count))
                gap -= count * 4
            commands.extend(PSGNextFrame() for _ in range(gap))
            frame = f.frame

            # PSG is frame-granular: within-frame write positions
            # are not representable and quantise to the frame start.
            commands.extend(PSGWrite(reg=w.reg, value=w.value)
                            for w in f.writes)
        commands.append(PSGEnd())

        return cls(version=10 if frequency else 0, frequency=frequency,
                   commands=commands)

    @classmethod
    def decode(cls, filename: str, image: Bytes) -> PSGFile:
        if image[:len(_SIGNATURE)] != _SIGNATURE:
            raise Error(f'{filename!r} is not a PSG file.',
                        id='not_a_psg_file')

        commands = _parse_commands(image[16:])
        consumed = 16 + sum(len(c.encode_command()) for c in commands)
        trailing = bytes(image[consumed:])

        return cls(version=image[4], frequency=image[5],
                   reserved=bytes(image[6:16]),
                   commands=commands,
                   trailing=trailing if trailing else None)

    def encode(self) -> bytes:
        return (_SIGNATURE + bytes([self.version, self.frequency]) +
                self.reserved.data +
                b''.join(c.encode_command() for c in self.commands) +
                (self.trailing.data if self.trailing is not None else b''))

    def to_ay_stream(self) -> AYStream:
        # A declared frequency gives the exact frame spacing; the
        # default is the 128K machine frame.
        if self.frequency == 0:
            ticks_per_frame = _TICKS_PER_FRAME
        else:
            if _TICKS_PER_SECOND % self.frequency != 0:
                raise Error(
                    f'Unsupported PSG frequency {self.frequency} Hz.',
                    id='bad_psg_frequency')
            ticks_per_frame = _TICKS_PER_SECOND // self.frequency

        frames: list[AYFrame] = []
        frame = 0
        for command in self.commands:
            if isinstance(command, PSGNextFrame):
                frame += 1
            elif isinstance(command, PSGSkipFrames):
                frame += command.num_frames
            elif isinstance(command, PSGWrite):
                if not frames or frames[-1].frame != frame:
                    frames.append(AYFrame(frame=frame))
                frames[-1].writes.append(AYWrite(reg=command.reg,
                                                 value=command.value))
            elif isinstance(command, PSGEnd):
                break

        return AYStream(ticks_per_second=_TICKS_PER_SECOND,
                        ticks_per_frame=ticks_per_frame,
                        frames=frames)

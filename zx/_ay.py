#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

from __future__ import annotations

import typing

from ._data import ByteData
from ._data import DataRecord
from ._data import HexData
from ._error import Error

if typing.TYPE_CHECKING:
    from ._binary import Bytes

_SIGNATURE = b'ZXAY'
_EMUL_TYPE = b'EMUL'


# The wire vocabulary of ZXAYEMUL: big-endian words, and pointers
# stored as signed 16-bit offsets relative to their own position,
# with 0 meaning null. Records keep pointer targets as absolute
# file offsets, so encoding recomputes the relative values.
# The reader also records every byte it serves, so once parsing is
# done, the bytes nothing read are known: the file's gaps.
class _Reader:
    def __init__(self, filename: str, image: bytes) -> None:
        self.filename = filename
        self.image = image
        self.__was_read = bytearray(len(image))

    def error(self, reason: str) -> Error:
        return Error(f'Malformed AY file {self.filename!r}: {reason}.',
                     id='bad_ay_file')

    def bytes_at(self, pos: int, size: int) -> bytes:
        assert size >= 0
        if pos < 0 or pos + size > len(self.image):
            raise self.error(f'{size} byte(s) at position {pos} fall '
                             f'outside the file')

        self.__was_read[pos:pos + size] = b'\x01' * size
        return self.image[pos:pos + size]

    # Bytes at the position, stopping short at the end of the file.
    def bytes_at_up_to(self, pos: int, size: int) -> bytes:
        return self.bytes_at(
            pos, min(size, max(len(self.image) - pos, 0)))

    def byte(self, pos: int) -> int:
        return self.bytes_at(pos, 1)[0]

    def word(self, pos: int) -> int:
        return int.from_bytes(self.bytes_at(pos, 2), 'big')

    def signed_word(self, pos: int) -> int:
        return int.from_bytes(self.bytes_at(pos, 2), 'big', signed=True)

    # Reading at the returned position is what validates it. A null
    # pointer means the field is absent.
    def pointer_or_null(self, pos: int) -> int | None:
        offset = self.signed_word(pos)
        if offset == 0:
            return None
        return pos + offset

    def pointer(self, pos: int, error: str) -> int:
        target = self.pointer_or_null(pos)
        if target is None:
            raise self.error(error)
        return target

    # The NUL-terminated string at the position, its terminator
    # consumed as part of it.
    def string(self, pos: int) -> str:
        end = self.image.find(b'\x00', pos)
        if end < 0:
            raise self.error(f'unterminated string at position {pos}')
        return self.bytes_at(pos, end - pos + 1)[:-1].decode('latin-1')

    def string_or_null(self, pos: int | None) -> str | None:
        if pos is None:
            return None
        return self.string(pos)

    # The runs of bytes no read has consumed, as (position, bytes).
    def gaps(self) -> list[tuple[int, bytes]]:
        runs = []
        begin = None
        for pos in range(len(self.image) + 1):
            if pos < len(self.image) and not self.__was_read[pos]:
                if begin is None:
                    begin = pos
            elif begin is not None:
                runs.append((begin, self.image[begin:pos]))
                begin = None
        return runs


# Assembles the encoded image from structures written field by
# field, each structure at its stated offset. Pointers encode
# relative to the position they are written at, mirroring the read
# side. Structures may legitimately share bytes (a ripper can
# overlap a block-list terminator with a points structure, say), so
# overlaps are allowed but must agree.
class _Writer:
    def __init__(self) -> None:
        self.__pieces: list[tuple[int, bytes]] = []
        self.__pos = 0

    # Continue writing at the given position.
    def seek(self, pos: int) -> None:
        self.__pos = pos

    def write_bytes(self, data: bytes) -> None:
        self.__pieces.append((self.__pos, data))
        self.__pos += len(data)

    def write_byte(self, value: int) -> None:
        self.write_bytes(bytes((value,)))

    def write_word(self, value: int) -> None:
        self.write_bytes(value.to_bytes(2, 'big'))

    # A pointer to the target, relative to the pointer's own
    # position; null for None.
    def write_pointer(self, target: int | None) -> None:
        offset = 0 if target is None else target - self.__pos
        self.write_bytes(offset.to_bytes(2, 'big', signed=True))

    def write_string(self, text: str) -> None:
        self.write_bytes(text.encode('latin-1') + b'\x00')

    def get_image(self) -> bytes:
        size = max((offset + len(data)
                    for offset, data in self.__pieces), default=0)
        image = bytearray(size)
        written = bytearray(size)

        for offset, data in self.__pieces:
            for i, b in enumerate(data, start=offset):
                assert not written[i] or image[i] == b, (
                    f'conflicting bytes at offset {i}')
                image[i] = b
                written[i] = 1

        assert all(written), 'bytes not covered by any structure'
        return bytes(image)


# A memory block: code or data the player loads at the given
# address. The stated length is kept apart from the data only when
# the file promises more bytes than it holds, which real files do.
class AYFileBlock(DataRecord):
    address: int
    length: int | None
    data_offset: int
    data: ByteData

    def __init__(self, *, address: int, length: int | None = None,
                 data_offset: int, data: Bytes | ByteData) -> None:
        super().__init__(address=address, length=length,
                         data_offset=data_offset, data=HexData.wrap(data))

    @property
    def stated_length(self) -> int:
        return self.length if self.length is not None else len(self.data.data)


class AYFileSong(DataRecord):
    name_offset: int
    name: str
    data_offset: int

    # The numbers of the Amiga audio channels playing the AY
    # channels and the noise, from the format's Amiga origin.
    # Spectrum players ignore them.
    a_amiga_channel_number: int
    b_amiga_channel_number: int
    c_amiga_channel_number: int
    noise_amiga_channel_number: int

    # The playing time and the fade-out that follows it, in 50 Hz
    # interrupt frames. Zero frames per song means no limit.
    frames_per_song: int
    frames_per_fade_out: int

    # The value the player loads into every Z80 register pair (AF,
    # BC, DE, HL, IX, IY and the shadow set) before calling
    # init_addr, so rips cannot depend on leftover register
    # contents.
    z80_regs_value: int

    entry_points_offset: int
    sp: int

    # The song set-up routine, called once; zero means the first
    # block's address.
    init_addr: int

    # The routine called on each 50 Hz interrupt; zero means the
    # code drives itself: init never returns, or installs an IM 2
    # handler.
    int_addr: int

    blocks_offset: int
    blocks: list[AYFileBlock]

    def __init__(self, *, name_offset: int, name: str, data_offset: int,
                 a_amiga_channel_number: int, b_amiga_channel_number: int,
                 c_amiga_channel_number: int,
                 noise_amiga_channel_number: int,
                 frames_per_song: int, frames_per_fade_out: int,
                 z80_regs_value: int,
                 entry_points_offset: int, sp: int,
                 init_addr: int, int_addr: int,
                 blocks_offset: int,
                 blocks: list[AYFileBlock]) -> None:
        super().__init__(
            name_offset=name_offset, name=name, data_offset=data_offset,
            a_amiga_channel_number=a_amiga_channel_number,
            b_amiga_channel_number=b_amiga_channel_number,
            c_amiga_channel_number=c_amiga_channel_number,
            noise_amiga_channel_number=noise_amiga_channel_number,
            frames_per_song=frames_per_song,
            frames_per_fade_out=frames_per_fade_out,
            z80_regs_value=z80_regs_value,
            entry_points_offset=entry_points_offset, sp=sp,
            init_addr=init_addr, int_addr=int_addr,
            blocks_offset=blocks_offset, blocks=blocks)


# A run of bytes no structure references: alignment padding, hidden
# ripper credits. Kept so no information in the original file is
# lost.
class AYFileGap(DataRecord):
    offset: int
    data: ByteData

    def __init__(self, *, offset: int, data: Bytes | ByteData) -> None:
        super().__init__(offset=offset, data=HexData.wrap(data))


# The .ay (ZXAYEMUL) format: a library of per-song code capsules,
# each a set of memory blocks with entry points, played by emulating
# the code.
#
# The file is a graph of structures linked by self-relative
# pointers, laid out at the ripper's whim: structures can share
# bytes and strings, and stray bytes can sit between them. Each
# record therefore keeps its file offset as ordinary wire content,
# and encoding places every structure back where it was, giving
# byte-exact reproduction of any parsed file.
class AYFile(DataRecord, format_name='AY'):
    file_version: int
    player_version: int
    author_offset: int | None
    author: str | None
    misc_offset: int | None
    misc: str | None
    first_song: int
    songs_offset: int
    songs: list[AYFileSong]
    gaps: list[AYFileGap]

    def __init__(self, *, file_version: int = 0, player_version: int = 0,
                 author_offset: int | None = None,
                 author: str | None = None,
                 misc_offset: int | None = None,
                 misc: str | None = None,
                 first_song: int = 0, songs_offset: int,
                 songs: list[AYFileSong],
                 gaps: list[AYFileGap] | None = None) -> None:
        super().__init__(
            file_version=file_version, player_version=player_version,
            author_offset=author_offset, author=author,
            misc_offset=misc_offset, misc=misc,
            first_song=first_song, songs_offset=songs_offset,
            songs=songs, gaps=gaps if gaps is not None else [])

    @classmethod
    def decode(cls, filename: str, image: Bytes) -> AYFile:
        r = _Reader(filename, bytes(image))
        if r.bytes_at_up_to(0, 4) != _SIGNATURE:
            raise Error(f'{filename!r} is not an AY file.',
                        id='not_an_ay_file')
        if r.bytes_at_up_to(4, 4) != _EMUL_TYPE:
            type_tag = r.bytes_at_up_to(4, 4).decode('latin-1', 'replace')
            raise Error(f'{filename!r} is an AY container of '
                        f'unsupported type {type_tag!r}.',
                        id='unsupported_ay_type')

        file_version = r.byte(8)
        player_version = r.byte(9)
        if r.word(10) != 0:
            raise r.error('special player structures are not supported')

        author_offset = r.pointer_or_null(12)
        misc_offset = r.pointer_or_null(14)
        author = r.string_or_null(author_offset)
        misc = r.string_or_null(misc_offset)

        num_songs = r.byte(16) + 1
        first_song = r.byte(17)
        songs_offset = r.pointer(18, 'null songs pointer')

        songs = []
        for i in range(num_songs):
            entry = songs_offset + i * 4

            name_offset = r.pointer(entry, 'null song name pointer')
            name = r.string(name_offset)

            data = r.pointer(entry + 2, 'null song data pointer')
            entry_points = r.pointer(data + 10,
                                     'null entry points pointer')
            blocks_offset = r.pointer(data + 12,
                                      'null block list pointer')

            blocks = []
            pos = blocks_offset
            while r.word(pos) != 0:
                length = r.word(pos + 2)
                data_offset = r.pointer(pos + 4,
                                        'null block data pointer')

                # Real files state block lengths running past the
                # end of the file; the block holds the bytes present.
                block_data = r.bytes_at_up_to(data_offset, length)

                blocks.append(AYFileBlock(
                    address=r.word(pos),
                    length=length if length != len(block_data) else None,
                    data_offset=data_offset, data=block_data))
                pos += 6

            songs.append(AYFileSong(
                name_offset=name_offset, name=name, data_offset=data,
                a_amiga_channel_number=r.byte(data),
                b_amiga_channel_number=r.byte(data + 1),
                c_amiga_channel_number=r.byte(data + 2),
                noise_amiga_channel_number=r.byte(data + 3),
                frames_per_song=r.word(data + 4),
                frames_per_fade_out=r.word(data + 6),
                z80_regs_value=r.word(data + 8),
                entry_points_offset=entry_points,
                sp=r.word(entry_points),
                init_addr=r.word(entry_points + 2),
                int_addr=r.word(entry_points + 4),
                blocks_offset=blocks_offset, blocks=blocks))

        gaps = [AYFileGap(offset=offset, data=data)
                for offset, data in r.gaps()]

        return cls(
            file_version=file_version, player_version=player_version,
            author_offset=author_offset, author=author,
            misc_offset=misc_offset, misc=misc,
            first_song=first_song, songs_offset=songs_offset,
            songs=songs, gaps=gaps)

    def encode(self) -> bytes:
        w = _Writer()

        w.write_bytes(_SIGNATURE + _EMUL_TYPE)
        w.write_byte(self.file_version)
        w.write_byte(self.player_version)
        w.write_word(0)
        w.write_pointer(self.author_offset)
        w.write_pointer(self.misc_offset)
        w.write_byte(len(self.songs) - 1)
        w.write_byte(self.first_song)
        w.write_pointer(self.songs_offset)

        if self.author_offset is not None:
            assert self.author is not None
            w.seek(self.author_offset)
            w.write_string(self.author)
        if self.misc_offset is not None:
            assert self.misc is not None
            w.seek(self.misc_offset)
            w.write_string(self.misc)

        for i, song in enumerate(self.songs):
            w.seek(self.songs_offset + i * 4)
            w.write_pointer(song.name_offset)
            w.write_pointer(song.data_offset)

            w.seek(song.name_offset)
            w.write_string(song.name)

            w.seek(song.data_offset)
            w.write_byte(song.a_amiga_channel_number)
            w.write_byte(song.b_amiga_channel_number)
            w.write_byte(song.c_amiga_channel_number)
            w.write_byte(song.noise_amiga_channel_number)
            w.write_word(song.frames_per_song)
            w.write_word(song.frames_per_fade_out)
            w.write_word(song.z80_regs_value)
            w.write_pointer(song.entry_points_offset)
            w.write_pointer(song.blocks_offset)

            w.seek(song.entry_points_offset)
            w.write_word(song.sp)
            w.write_word(song.init_addr)
            w.write_word(song.int_addr)

            w.seek(song.blocks_offset)
            for block in song.blocks:
                w.write_word(block.address)
                w.write_word(block.stated_length)
                w.write_pointer(block.data_offset)
            w.write_word(0)

            for block in song.blocks:
                w.seek(block.data_offset)
                w.write_bytes(block.data.data)

        for gap in self.gaps:
            w.seek(gap.offset)
            w.write_bytes(gap.data.data)

        return w.get_image()

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import zx


def test_basic() -> None:
    # Create a Z80 snapshot.
    mach = zx.Spectrum()
    mach.pc = 0x0001  # TODO: Null PC is not supported yet.
    HL = 0x1234
    mach.hl = HL
    format = zx._z80snapshot.Z80Snapshot
    assert format.FORMAT_NAME == 'Z80'
    image = format.from_snapshot(mach.to_snapshot()).encode()
    assert len(image) == 49248
    assert image[4:6] == HL.to_bytes(2, 'little')

    # Parse it back and check.
    snap = format.decode('x.z80', image)
    assert snap.hl == HL

    # Dump the parsed snapshot.
    assert 'Z80Snapshot' in snap.dumps()

    # Produce and dump unified snapshot.
    uni = snap.to_unified_snapshot()
    assert 'UnifiedSnapshot' in uni.dumps()


# Z80Snapshot stores compressed memory literally -- decode() never
# decompresses, it just preserves the original bytes. encode() writes
# them back unchanged. Only to_unified_snapshot() decompresses, for
# semantic use. This confirms binary-exact roundtripping works even for
# compressed snapshots, without any re-compression logic.
def test_compressed_v1_roundtrip() -> None:
    def make_image() -> bytes:
        # V1 .z80 with flags1 bit 5 set (compression enabled).
        # Memory: 384 x \xed\xed\x80\x00 = 128 zeros each = 49152 bytes.
        writer = zx._binary.BinaryWriter()
        for field, value in [
                ('B', 0),       # a
                ('B', 0),       # f
                ('<H', 0),      # bc
                ('<H', 0),      # hl
                ('<H', 0x0001),  # pc (non-zero = V1)
                ('<H', 0xffff),  # sp
                ('B', 0),       # i
                ('B', 0),       # r
                ('B', 0x20),    # flags1 (bit 5 = compressed)
                ('<H', 0),      # de
                ('<H', 0),      # alt_bc
                ('<H', 0),      # alt_de
                ('<H', 0),      # alt_hl
                ('B', 0),       # alt_a
                ('B', 0),       # alt_f
                ('<H', 0),      # iy
                ('<H', 0),      # ix
                ('B', 0),       # iff1
                ('B', 0),       # iff2
                ('B', 0)]:      # flags2
            writer.write_field(field, value)
        writer.write_bytes(b'\xed\xed\x80\x00' * 384 + b'\x00\xed\xed\x00')
        return writer.get_image()

    image = make_image()
    snap = zx._z80snapshot.Z80Snapshot.decode('test.z80', image)
    # This currently fails because encode() doesn't re-compress.
    assert snap.encode() == image, 'Compressed V1 .z80 roundtrip broken'

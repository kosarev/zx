
/*  ZX Spectrum Emulator.

    Copyright (C) 2017 Ivan Kosarev.
    ivan@kosarev.info

    Published under the MIT license.
*/

#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "z80/z80.h"

using z80::least_u8;
using z80::fast_u16;

namespace zx {

class spectrum_48 : public z80::instructions_decoder<spectrum_48>,
                    public z80::processor<spectrum_48> {
public:
    typedef processor<spectrum_48> processor;
    typedef uint_fast32_t ticks_type;

    spectrum_48()
        : ticks(0)
    {}

    void tick(unsigned t) { ticks += t; }

    ticks_type get_ticks() const { return ticks; }

    least_u8 &at(fast_u16 addr) {
        assert(addr < image_size);
        return image[addr];
    }

private:
    ticks_type ticks;

    static const z80::size_type image_size = 0x10000;  // 64K bytes.
    least_u8 image[image_size];
};

}  // namespace zx

namespace {

#if defined(__GNUC__) || defined(__clang__)
# define LIKE_PRINTF(format, args) \
      __attribute__((__format__(__printf__, format, args)))
#else
# define LIKE_PRINTF(format, args) /* nothing */
#endif

const char program_name[] = "zx";

[[noreturn]] LIKE_PRINTF(1, 0)
void verror(const char *format, va_list args) {
    std::fprintf(stderr, "%s: ", program_name);
    std::vfprintf(stderr, format, args);
    std::fprintf(stderr, "\n");
    exit(EXIT_FAILURE);
}

[[noreturn]] LIKE_PRINTF(1, 2)
void error(const char *format, ...) {
    va_list args;
    va_start(args, format);
    verror(format, args);
    va_end(args);
}

void load_rom(zx::spectrum_48 &mach, const char *filename) {
    FILE *f = std::fopen(filename, "rb");
    if(!f)
        error("cannot open ROM file '%s': %s",
              filename, std::strerror(errno));
    static const std::size_t rom_size = 16384;  // 16K
    least_u8 rom[rom_size + 1];
    std::size_t read_size = std::fread(rom, /* size= */ 1, rom_size + 1, f);
    if(ferror(f))
        error("cannot read ROM file '%s': %s",
              filename, std::strerror(errno));
    if(read_size < rom_size)
        error("ROM file '%s' is too short", filename);
    if(read_size > rom_size)
        error("ROM file '%s' is too large", filename);
    if(std::fclose(f) != 0)
        error("cannot close ROM file '%s': %s",
              filename, std::strerror(errno));

    for(fast_u16 i = 0; i != rom_size; ++i)
        mach.at(i) = rom[i];
}

}  // anonymous namespace

int main() {
    zx::spectrum_48 mach;
    load_rom(mach, "/usr/share/spectrum-roms/48.rom");

    while(mach.get_ticks() < 4) {
        std::printf("%5u %04x\n", static_cast<unsigned>(mach.get_ticks()),
                    static_cast<unsigned>(mach.get_pc()));
        mach.step();
    }
}

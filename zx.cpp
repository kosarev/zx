
/*  ZX Spectrum Emulator.

    Copyright (C) 2017 Ivan Kosarev.
    ivan@kosarev.info

    Published under the MIT license.
*/

#include "z80/z80.h"

namespace zx {

using z80::least_u8;
using z80::fast_u16;

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

int main() {
    zx::spectrum_48 mach;
}

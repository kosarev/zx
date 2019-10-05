
/*  ZX Spectrum Emulator.
    https://github.com/kosarev/zx

    Copyright (C) 2017-2019 Ivan Kosarev.
    ivan@kosarev.info

    Published under the MIT license.
*/

#include "zx.h"

namespace zx {

spectrum48::~spectrum48()
{}

fast_u8 spectrum48::on_input(fast_u16 addr) {
    z80::unused(addr);
    return 0xbf;
}

}  // namespace zx


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

#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/Xos.h>
#include <X11/Xatom.h>

#include "z80/z80.h"

using z80::least_u8;
using z80::fast_u16;

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

void set_window_manager_hints(Display *display, const char *pclass,
                              const char *argv[], int argc,
                              Window window,
                              unsigned width, unsigned height,
                              const char *title, Pixmap pixmap) {
    ::XTextProperty window_name, icon_name;
    if(!::XStringListToTextProperty(const_cast<char**>(&title), 1,
                                    &window_name) ||
            !::XStringListToTextProperty(const_cast<char**>(&title), 1,
                                         &icon_name))
        error("not enough memory");

    ::XSizeHints size_hints;
    size_hints.flags = PPosition | PSize | PMinSize | PMaxSize;
    size_hints.min_width = static_cast<int>(width);
    size_hints.min_height = static_cast<int>(height);
    size_hints.max_width = static_cast<int>(width);
    size_hints.max_height = static_cast<int>(height);

    ::XWMHints wm_hints;
    wm_hints.flags = AllHints;
    wm_hints.initial_state = NormalState;
    wm_hints.input = True;
    wm_hints.icon_pixmap = pixmap;

    ::XClassHint class_hint;
    class_hint.res_name = const_cast<char*>(argv[0]);
    class_hint.res_class = const_cast<char*>(pclass);

    ::XSetWMProperties(display, window, &window_name, &icon_name,
                       const_cast<char**>(argv), argc,
                       &size_hints, &wm_hints, &class_hint);
}

}  // anonymous namespace

namespace zx {

class spectrum_48 : public z80::processor<spectrum_48> {
public:
    typedef processor<spectrum_48> base;
    typedef uint_fast32_t ticks_type;

    spectrum_48()
        : ticks(0)
    {}

    void tick(unsigned t) { ticks += t; }

    ticks_type get_ticks() const { return ticks; }

    least_u8 &on_access(fast_u16 addr) {
        assert(addr < image_size);
        return image[addr];
    }

    void load_rom(const char *filename);

private:
    ticks_type ticks;

    static const z80::size_type image_size = 0x10000;  // 64K bytes.
    least_u8 image[image_size];
};

void spectrum_48::load_rom(const char *filename) {
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
        on_access(i) = rom[i];
}

template<typename M>
class x11_emulator {
public:
    typedef M machine;

    x11_emulator(machine &mach)
        : mach(mach), pixels(nullptr), display(nullptr), image(nullptr), gc()
    {}

    void create(int argc, const char *argv[]) {
        assert(!pixels);
        pixels = static_cast<pixel_type*>(std::malloc(pixels_size));
        if(!pixels)
            error("not enough memory");

        assert(!display);
        display = ::XOpenDisplay(nullptr);
        if(!display)
            error("cannot connect to the X server");

        int screen_number = DefaultScreen(display);
        auto screen_width = static_cast<unsigned>(
            DisplayWidth(display, screen_number));
        auto screen_height = static_cast<unsigned>(
            DisplayHeight(display, screen_number));

        ::Window window = ::XCreateSimpleWindow(
            display, RootWindow(display, screen_number),
            (screen_width - window_width) / 2,
            (screen_height - window_height) / 2,
            window_width, window_height, 0,
            BlackPixel(display, screen_number),
            WhitePixel(display, screen_number));

        ::set_window_manager_hints(
            display, "ivan@kosarev.info/ZXEmulatorWindowClass", argv, argc,
            window, window_width, window_height,
            "ZX Spectrum Emulator", 0);

        ::XSelectInput(display, window, KeyReleaseMask | ButtonReleaseMask);
        ::XMapWindow(display, window);

        image = ::XCreateImage(
            display, DefaultVisual(display, DefaultScreen(display)),
            /* depth= */ 24, ZPixmap, /* offset= */ 0,
            reinterpret_cast<char*>(pixels), window_width, window_height,
            /* line_pad= */ 8, /* bytes_per_line= */ 0);
        (void) image;  // TODO

        gc = ::XCreateGC(display, window, 0, nullptr);

        // Set protocol for the WM_DELETE_WINDOW message.
        ::Atom wm_protocols_atom = ::XInternAtom(display, "WM_PROTOCOLS", False);
        ::Atom wm_delete_window_atom = ::XInternAtom(display, "WM_DELETE_WINDOW",
                                                     False);
        if((wm_protocols_atom != None) && (wm_delete_window_atom != None))
            ::XSetWMProtocols(display, window, &wm_delete_window_atom, 1);
    }

    void destroy() {
        ::XFreeGC(display, gc);
        ::XFlush(display);

        // Also releases the pixels.
        XDestroyImage(image);

        ::XCloseDisplay(display);
    }

private:
    static const unsigned window_width = 256;
    static const unsigned window_height = 192;

    typedef uint32_t pixel_type;
    static const std::size_t num_of_pixels = window_width * window_height;
    static const std::size_t pixels_size = sizeof(pixel_type) * num_of_pixels;

    machine &mach;
    pixel_type *pixels;
    Display *display;
    ::XImage *image;
    ::GC gc;
};

}  // namespace zx

int main(int argc, const char *argv[]) {
    zx::spectrum_48 mach;
    mach.load_rom("/usr/share/spectrum-roms/48.rom");

    if(argc == 2 && std::strcmp(argv[1], "test") == 0) {
        while(mach.get_ticks() < 1000) {
            std::fprintf(stderr,
                         "%5u %04x\n", static_cast<unsigned>(mach.get_ticks()),
                         static_cast<unsigned>(mach.get_pc()));
            std::fflush(stderr);
            mach.step();
        }
        std::fprintf(stderr, "%5u\n", static_cast<unsigned>(mach.get_ticks()));
        return EXIT_SUCCESS;
    }

    zx::x11_emulator<zx::spectrum_48> emu(mach);
    emu.create(argc, argv);

    ::usleep(1000000);

    emu.destroy();
}


/*  ZX Spectrum Emulator.

    Copyright (C) 2017 Ivan Kosarev.
    ivan@kosarev.info

    Published under the MIT license.
*/

#include <cerrno>
#include <cstring>

#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/Xos.h>
#include <X11/Xatom.h>

#include "zx.h"

using z80::least_u8;
using z80::fast_u8;
using z80::fast_u16;

namespace {

template<typename T>
constexpr T div_ceil(T a, T b) {
    return (a + b - 1) / b;
}

template<typename T>
constexpr bool is_multiple_of(T a, T b) {
    return b != 0 && a % b == 0;
}

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

template<typename M>
class x11_emulator : public M {
public:
    typedef M machine;

    x11_emulator()
        : window_pixels(nullptr), display(nullptr), window(), image(nullptr),
          gc()
    {}

    void create(int argc, const char *argv[]) {
        assert(!window_pixels);
        window_pixels = static_cast<window_pixels_type*>(
            std::malloc(sizeof(window_pixels_type)));
        if(!window_pixels)
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

        window = ::XCreateSimpleWindow(
            display, RootWindow(display, screen_number),
            (screen_width - window_width) / 2,
            (screen_height - window_height) / 2,
            window_width, window_height, 0,
            BlackPixel(display, screen_number),
            BlackPixel(display, screen_number));

        ::XTextProperty window_name, icon_name;
        const char *title = "ZX Spectrum Emulator";
        if(!::XStringListToTextProperty(const_cast<char**>(&title), 1,
                                        &window_name) ||
                !::XStringListToTextProperty(const_cast<char**>(&title), 1,
                                             &icon_name))
            error("not enough memory");

        ::XSizeHints size_hints;
        size_hints.flags = PPosition | PSize | PMinSize | PMaxSize;
        size_hints.min_width = static_cast<int>(window_width);
        size_hints.min_height = static_cast<int>(window_height);
        size_hints.max_width = static_cast<int>(window_width);
        size_hints.max_height = static_cast<int>(window_height);

        ::XWMHints wm_hints;
        wm_hints.flags = AllHints;
        wm_hints.initial_state = NormalState;
        wm_hints.input = True;
        wm_hints.icon_pixmap = 0;

        const char pclass[] = "ivan@kosarev.info/ZXEmulatorWindowClass";
        ::XClassHint class_hint;
        class_hint.res_name = const_cast<char*>(argv[0]);
        class_hint.res_class = const_cast<char*>(pclass);

        ::XSetWMProperties(display, window, &window_name, &icon_name,
                           const_cast<char**>(argv), argc,
                           &size_hints, &wm_hints, &class_hint);

        ::XSelectInput(display, window, KeyReleaseMask | ButtonReleaseMask);
        ::XMapWindow(display, window);

        image = ::XCreateImage(
            display, DefaultVisual(display, DefaultScreen(display)),
            /* depth= */ 24, ZPixmap, /* offset= */ 0,
            reinterpret_cast<char*>(window_pixels),
            window_width, window_height,
            /* line_pad= */ 8, /* bytes_per_line= */ 0);

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

    void process_frame() {
        ::usleep(20000);

        // Draw the previously rendered frame.
        update_window();

        // Execute instructions for the next frame.
        machine::execute_frame();

        // Render the next frame.
        render_frame();
    }

    void load_rom(const char *filename) {
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
            machine::on_access(i) = rom[i];
    }

private:
    static const auto window_width = machine::frame_width;
    static const auto window_height = machine::frame_height;

    typedef typename machine::pixel_type window_pixel;
    typedef typename machine::pixels_buffer_type window_pixels_type;

    void update_window() {
        ::XPutImage(display, window, gc, image, 0, 0, 0, 0,
                    window_width, window_height);
    }

    void render_frame() {
        machine::render_frame();
        machine::get_frame_pixels(*window_pixels);
    }

    window_pixels_type *window_pixels;
    Display *display;
    ::Window window;
    ::XImage *image;
    ::GC gc;
};

}  // anonymous namespace

int main(int argc, const char *argv[]) {
    x11_emulator<zx::spectrum48> emu;
    emu.load_rom("/usr/share/spectrum-roms/48.rom");

    if(argc == 2 && std::strcmp(argv[1], "test") == 0) {
        while(emu.get_ticks() < 1000) {
            std::fprintf(stderr,
                         "%5u %04x\n", static_cast<unsigned>(emu.get_ticks()),
                         static_cast<unsigned>(emu.get_pc()));
            std::fflush(stderr);
            emu.step();
        }
        std::fprintf(stderr, "%5u\n", static_cast<unsigned>(emu.get_ticks()));
        return EXIT_SUCCESS;
    }

    emu.create(argc, argv);

    for(unsigned i = 0; i < 300; ++i)
        emu.process_frame();

    emu.destroy();
}

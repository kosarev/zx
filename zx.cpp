
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

template<typename T>
T non_constexpr() {
    return T();
}

template<typename T>
constexpr T div_exact(T a, T b) {
    return a % b == 0 ? a / b : non_constexpr<T>();
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

}  // anonymous namespace

namespace zx {

class spectrum_48 : public z80::processor<spectrum_48> {
public:
    typedef processor<spectrum_48> base;
    typedef uint_fast32_t ticks_type;

    spectrum_48()
            : ticks(0) {
        uint_fast32_t rnd = 0xde347a01;
        for(auto &cell : image) {
            cell = static_cast<least_u8>(rnd);
            rnd = (rnd * 0x74392cef) ^ (rnd >> 16);
        }
    }

    void tick(unsigned t) { ticks += t; }

    ticks_type get_ticks() const { return ticks; }

    least_u8 &on_access(fast_u16 addr) {
        assert(addr < image_size);
        return image[addr];
    }

    void load_rom(const char *filename);

protected:
    // Four bits per frame pixel in brightness:grb format.
    static const unsigned bits_per_frame_pixel = 4;

    static const unsigned brightness_bit = 3;
    static const unsigned green_bit = 2;
    static const unsigned red_bit = 1;
    static const unsigned blue_bit = 0;

    static const unsigned brightness_mask = 1u << brightness_bit;
    static const unsigned green_mask = 1u << green_bit;
    static const unsigned red_mask = 1u << red_bit;
    static const unsigned blue_mask = 1u << blue_bit;

    // Eight frame pixels per chunk. The leftmost pixel occupies the most
    // significant bits.
    static const unsigned frame_pixels_per_chunk = 8;

    // The type of frame chunks.
    static const unsigned frame_chunk_width = 32;
    static_assert(
        bits_per_frame_pixel * frame_pixels_per_chunk <= frame_chunk_width,
        "The frame chunk width is too small!");
    typedef uint_least32_t frame_chunk;

    // The dimensions of the viewable area.
    // TODO: Support the NTSC geometry.
    static const unsigned screen_width = 256;
    static const unsigned screen_height = 192;
    static const unsigned border_width = 48;
    static const unsigned top_border_height = 48;
    static const unsigned bottom_border_height = 40;

    static const unsigned frame_width =
        border_width + screen_width + border_width;
    static const unsigned frame_height =
        top_border_height + screen_height + bottom_border_height;

    // We want screen, border and frame widths be multiples of chunk widths to
    // simplify the processing code and to benefit from aligned memory accesses.
    static const unsigned chunks_per_border_width =
        div_exact(border_width, frame_pixels_per_chunk);
    static const unsigned chunks_per_screen_line =
        div_exact(screen_width, frame_pixels_per_chunk);
    static const unsigned chunks_per_frame_line =
        div_exact(frame_width, frame_pixels_per_chunk);

    frame_chunk frame_chunks[frame_height][chunks_per_frame_line];

    void render_frame() {
        static_assert(bits_per_frame_pixel == 4,
                      "Unsupported frame pixel format!");
        static_assert(frame_pixels_per_chunk == 8,
                      "Unsupported frame chunk format!");

        const unsigned black = 0;
        const unsigned white = red_mask | green_mask | blue_mask;
        const frame_chunk white_chunk = 0x11111111 * white;

        // Render the top border area.
        unsigned i = 0;
        for(; i != top_border_height; ++i) {
            frame_chunk *line = frame_chunks[i];
            for(unsigned j = 0; j != chunks_per_frame_line; ++j)
                line[j] = white_chunk;
        }

        // Render the screen area.
        fast_u16 line_addr = 0x4000;
        for(; i != top_border_height + screen_height; ++i) {
            frame_chunk *line = frame_chunks[i];

            // Left border.
            unsigned j = 0;
            for(; j != chunks_per_border_width; ++j)
                line[j] = white_chunk;

            // Screen.
            fast_u16 addr = line_addr;
            for(; j != chunks_per_border_width + chunks_per_screen_line; ++j) {
                fast_u8 b = on_access(addr);
                uint_fast32_t c = 0;
                c |= (b & 0x80) ? black : white; c <<= 4;
                c |= (b & 0x40) ? black : white; c <<= 4;
                c |= (b & 0x20) ? black : white; c <<= 4;
                c |= (b & 0x10) ? black : white; c <<= 4;
                c |= (b & 0x08) ? black : white; c <<= 4;
                c |= (b & 0x04) ? black : white; c <<= 4;
                c |= (b & 0x02) ? black : white; c <<= 4;
                c |= (b & 0x01) ? black : white;
                line[j] = static_cast<frame_chunk>(c);
                ++addr;
            }

            // Right border.
            for(; j != chunks_per_frame_line; ++j)
                line[j] = white_chunk;

            // Move to next line.
            if(((line_addr += 0x0100) & 0x700) == 0) {
                line_addr += 0x20;
                line_addr -= (line_addr & 0xff) < 0x20 ? 0x100 : 0x800;
            }
        }

        // Render the bottom border area.
        for(; i != frame_height; ++i) {
            frame_chunk *line = frame_chunks[i];
            for(unsigned j = 0; j != chunks_per_frame_line; ++j)
                line[j] = white_chunk;
        }
    }

    void execute_frame() {
        const ticks_type ticks_per_frame = 69888;
        while(ticks < ticks_per_frame)
            step();
        ticks -= ticks_per_frame;
    }

    ticks_type ticks;

private:
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

private:
    static const unsigned window_scale = 2;
    static const auto window_width = machine::frame_width * window_scale;
    static const auto window_height = machine::frame_height * window_scale;

    typedef uint32_t window_pixel;
    typedef window_pixel window_pixels_type[window_height][window_width];

    void update_window() {
        ::XPutImage(display, window, gc, image, 0, 0, 0, 0,
                    window_width, window_height);
    }

    window_pixel translate_color(unsigned c) {
        uint_fast32_t r = 0;
        r |= (c & machine::red_mask)   << (16 - machine::red_bit);
        r |= (c & machine::green_mask) << (8 - machine::green_bit);
        r |= (c & machine::blue_mask)  << (0 - machine::blue_bit);

        // TODO: Use the real coefficients.
        r *= (c & machine::brightness_mask) ? 0xff : 0xcc;

        return static_cast<window_pixel>(r);
    }

    void render_frame() {
        machine::render_frame();

        static_assert(window_scale == 2, "Unsupported window scale!");
        static_assert(is_multiple_of(window_width,
                                     machine::frame_pixels_per_chunk),
                      "Fractional number of chunks per line is not supported!");
        static_assert(machine::bits_per_frame_pixel == 4,
                      "Unsupported frame pixel format!");
        static_assert(machine::frame_pixels_per_chunk == 8,
                      "Unsupported frame chunk format!");
        window_pixel *pixels = **window_pixels;
        std::size_t p = 0;
        for(const auto &frame_line : machine::frame_chunks) {
            window_pixel *line = &pixels[p];
            for(auto chunk : frame_line) {
                window_pixel c;
                c = translate_color((chunk >> 28) & 0xf);
                pixels[p++] = c;
                pixels[p++] = c;
                c = translate_color((chunk >> 24) & 0xf);
                pixels[p++] = c;
                pixels[p++] = c;
                c = translate_color((chunk >> 20) & 0xf);
                pixels[p++] = c;
                pixels[p++] = c;
                c = translate_color((chunk >> 16) & 0xf);
                pixels[p++] = c;
                pixels[p++] = c;
                c = translate_color((chunk >> 12) & 0xf);
                pixels[p++] = c;
                pixels[p++] = c;
                c = translate_color((chunk >>  8) & 0xf);
                pixels[p++] = c;
                pixels[p++] = c;
                c = translate_color((chunk >>  4) & 0xf);
                pixels[p++] = c;
                pixels[p++] = c;
                c = translate_color((chunk >>  0) & 0xf);
                pixels[p++] = c;
                pixels[p++] = c;
            }

            // Duplicate the last line.
            std::memcpy(line + window_width, line,
                        sizeof(window_pixel[window_width]));
            p += window_width;
        }
    }

    window_pixels_type *window_pixels;
    Display *display;
    ::Window window;
    ::XImage *image;
    ::GC gc;
};

}  // namespace zx

int main(int argc, const char *argv[]) {
    if(argc == 2 && std::strcmp(argv[1], "test") == 0) {
        zx::spectrum_48 mach;
        mach.load_rom("/usr/share/spectrum-roms/48.rom");

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

    zx::x11_emulator<zx::spectrum_48> emu;
    emu.load_rom("/usr/share/spectrum-roms/48.rom");
    emu.create(argc, argv);

    for(unsigned i = 0; i < 300; ++i)
        emu.process_frame();

    emu.destroy();
}

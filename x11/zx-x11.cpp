
/*  ZX Spectrum Emulator.
    https://github.com/kosarev/zx

    Copyright (C) 2017-2019 Ivan Kosarev.
    ivan@kosarev.info

    Published under the MIT license.
*/

#include <cerrno>
#include <cstdarg>
#include <cstring>

#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/Xos.h>
#include <X11/Xatom.h>
#include <X11/XKBlib.h>

#include "../zx.h"

using z80::least_u8;
using z80::fast_u8;
using z80::fast_u16;

namespace {

#if 0  // TODO: Unused.
template<typename T>
constexpr T div_ceil(T a, T b) {
    return (a + b - 1) / b;
}
#endif

#if 0  // TODO: Unused.
template<typename T>
constexpr bool is_multiple_of(T a, T b) {
    return b != 0 && a % b == 0;
}
#endif

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
          gc(), done(false),
          keyboard_state{0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff}
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

        ::XSelectInput(display, window, KeyPressMask | KeyReleaseMask);
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
        wm_delete_window_atom = ::XInternAtom(display, "WM_DELETE_WINDOW",
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

    unsigned translate_spectrum_key(::KeySym key) {
        switch(key)  {
        // 1st line.
        case XK_1: return spectrum_key_1;
        case XK_2: return spectrum_key_2;
        case XK_3: return spectrum_key_3;
        case XK_4: return spectrum_key_4;
        case XK_5: return spectrum_key_5;
        case XK_6: return spectrum_key_6;
        case XK_7: return spectrum_key_7;
        case XK_8: return spectrum_key_8;
        case XK_9: return spectrum_key_9;
        case XK_0: return spectrum_key_0;

        // 2nd line.
        case XK_q: return spectrum_key_q;
        case XK_w: return spectrum_key_w;
        case XK_e: return spectrum_key_e;
        case XK_r: return spectrum_key_r;
        case XK_t: return spectrum_key_t;
        case XK_y: return spectrum_key_y;
        case XK_u: return spectrum_key_u;
        case XK_i: return spectrum_key_i;
        case XK_o: return spectrum_key_o;
        case XK_p: return spectrum_key_p;

        // 3rd line.
        case XK_a: return spectrum_key_a;
        case XK_s: return spectrum_key_s;
        case XK_d: return spectrum_key_d;
        case XK_f: return spectrum_key_f;
        case XK_g: return spectrum_key_g;
        case XK_h: return spectrum_key_h;
        case XK_j: return spectrum_key_j;
        case XK_k: return spectrum_key_k;
        case XK_l: return spectrum_key_l;
        case XK_Return: return spectrum_key_enter;

        // 4th line.
        case XK_Shift_L: return spectrum_key_caps_shift;
        case XK_z: return spectrum_key_z;
        case XK_x: return spectrum_key_x;
        case XK_c: return spectrum_key_c;
        case XK_v: return spectrum_key_v;
        case XK_b: return spectrum_key_b;
        case XK_n: return spectrum_key_n;
        case XK_m: return spectrum_key_m;
        case XK_Shift_R: return spectrum_key_symbol_shift;
        case XK_space: return spectrum_key_break_space;
        }
        return 0;
    }

    void handle_spectrum_key(unsigned key, bool pressed) {
        unsigned port_no = (key & 0xf);
        assert(port_no >= 8 && port_no <= 15);

        unsigned bit_no = (key >> 4);
        assert(bit_no >= 0 && bit_no <= 4);

        least_u8 &port = keyboard_state[port_no - 8];
        fast_u8 mask = 1u << bit_no;
        if(pressed)
            port = static_cast<least_u8>(port & ~mask);
        else
            port = static_cast<least_u8>(port | mask);
    }

    void handle_keyboard_events() {
        ::XEvent event;
        if(!XCheckMaskEvent(display, KeyPressMask | KeyReleaseMask, &event))
            return;

        bool pressed = (event.type == KeyPress);
        auto key_code = static_cast<::KeyCode>(event.xkey.keycode);
        ::KeySym key = ::XkbKeycodeToKeysym(display, key_code,
                                            /* group= */ 0, /* level= */ 0);

        if(pressed && key == XK_F10) {
            done = true;
            return;
        }

        if(unsigned spectrum_key = translate_spectrum_key(key))
            handle_spectrum_key(spectrum_key, pressed);
    }

    void handle_events() {
        // Check if the Close Button on the window caption is pressed.
        ::XEvent event;
        if(::XCheckTypedWindowEvent(display, window, ClientMessage, &event)) {
            if(static_cast<::Atom>(event.xclient.data.l[0]) ==
                   wm_delete_window_atom) {
                done = true;
                return;
            }
        }

        handle_keyboard_events();
    }

    bool process_frame() {
        ::usleep(20000);

        // Draw the previously rendered frame.
        update_window();

        // Execute instructions for the next frame.
        machine::run();

        // Render the next frame.
        render_frame();

        // Handle events of the windowing system.
        handle_events();

        return !done;
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
            machine::set_memory_byte(i, rom[i]);
    }

private:
    static const auto window_width = machine::frame_width;
    static const auto window_height = machine::frame_height;

    typedef typename machine::pixel_type window_pixel;
    typedef typename machine::pixels_buffer_type window_pixels_type;

    // Keyboard codes.
    // 1st line.
    static const unsigned spectrum_key_1 = 0x0b;
    static const unsigned spectrum_key_2 = 0x1b;
    static const unsigned spectrum_key_3 = 0x2b;
    static const unsigned spectrum_key_4 = 0x3b;
    static const unsigned spectrum_key_5 = 0x4b;
    static const unsigned spectrum_key_6 = 0x4c;
    static const unsigned spectrum_key_7 = 0x3c;
    static const unsigned spectrum_key_8 = 0x2c;
    static const unsigned spectrum_key_9 = 0x1c;
    static const unsigned spectrum_key_0 = 0x0c;

    // 2nd line.
    static const unsigned spectrum_key_q = 0x0a;
    static const unsigned spectrum_key_w = 0x1a;
    static const unsigned spectrum_key_e = 0x2a;
    static const unsigned spectrum_key_r = 0x3a;
    static const unsigned spectrum_key_t = 0x4a;
    static const unsigned spectrum_key_y = 0x4d;
    static const unsigned spectrum_key_u = 0x3d;
    static const unsigned spectrum_key_i = 0x2d;
    static const unsigned spectrum_key_o = 0x1d;
    static const unsigned spectrum_key_p = 0x0d;

    // 3rd line.
    static const unsigned spectrum_key_a = 0x09;
    static const unsigned spectrum_key_s = 0x19;
    static const unsigned spectrum_key_d = 0x29;
    static const unsigned spectrum_key_f = 0x39;
    static const unsigned spectrum_key_g = 0x49;
    static const unsigned spectrum_key_h = 0x4e;
    static const unsigned spectrum_key_j = 0x3e;
    static const unsigned spectrum_key_k = 0x2e;
    static const unsigned spectrum_key_l = 0x1e;
    static const unsigned spectrum_key_enter = 0x0e;

    // 4th line.
    static const unsigned spectrum_key_caps_shift = 0x08;
    static const unsigned spectrum_key_z = 0x18;
    static const unsigned spectrum_key_x = 0x28;
    static const unsigned spectrum_key_c = 0x38;
    static const unsigned spectrum_key_v = 0x48;
    static const unsigned spectrum_key_b = 0x4f;
    static const unsigned spectrum_key_n = 0x3f;
    static const unsigned spectrum_key_m = 0x2f;
    static const unsigned spectrum_key_symbol_shift = 0x1f;
    static const unsigned spectrum_key_break_space = 0x0f;

    fast_u8 on_input(fast_u16 addr) override {
        fast_u8 n = 0xbf;  // TODO
        if(!(addr & 1)) {
            // Scan keyboard.
            if(!(addr & (1u << 8))) n &= keyboard_state[0];
            if(!(addr & (1u << 9))) n &= keyboard_state[1];
            if(!(addr & (1u << 10))) n &= keyboard_state[2];
            if(!(addr & (1u << 11))) n &= keyboard_state[3];
            if(!(addr & (1u << 12))) n &= keyboard_state[4];
            if(!(addr & (1u << 13))) n &= keyboard_state[5];
            if(!(addr & (1u << 14))) n &= keyboard_state[6];
            if(!(addr & (1u << 15))) n &= keyboard_state[7];
        }
        return n;
    }

    void update_window() {
        ::XPutImage(display, window, gc, image, 0, 0, 0, 0,
                    window_width, window_height);
    }

    void render_frame() {
        machine::x_render_frame();
        machine::get_frame_pixels(*window_pixels);
    }

    window_pixels_type *window_pixels;
    Display *display;
    ::Window window;
    ::XImage *image;
    ::GC gc;
    ::Atom wm_delete_window_atom;

    bool done;

    static const unsigned num_of_keyboard_ports = 8;
    typedef least_u8 keyboard_state_type[num_of_keyboard_ports];
    keyboard_state_type keyboard_state;
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
            emu.on_step();
        }
        std::fprintf(stderr, "%5u\n", static_cast<unsigned>(emu.get_ticks()));
        return EXIT_SUCCESS;
    }

    emu.create(argc, argv);

    while(emu.process_frame()) {}

    emu.destroy();
}


/*  ZX Spectrum Emulator.

    Copyright (C) 2017-2019 Ivan Kosarev.
    ivan@kosarev.info

    Published under the MIT license.
*/

#include <algorithm>

#include "z80/z80.h"

namespace zx {

using z80::fast_u8;
using z80::fast_u16;
using z80::least_u8;
using z80::least_u16;
using z80::unreachable;

typedef uint_fast32_t fast_u32;

template<typename T>
T non_constexpr() {
    return T();
}

template<typename T>
constexpr T div_exact(T a, T b) {
    return a % b == 0 ? a / b : non_constexpr<T>();
}

template<typename T>
constexpr bool is_multiple_of(T a, T b) {
    return b != 0 && a % b == 0;
}

typedef fast_u32 events_mask;
const events_mask no_events         = 0;
const events_mask machine_stopped   = 1u << 0;  // TODO: Eliminate.
const events_mask end_of_frame      = 1u << 1;
const events_mask ticks_limit_hit   = 1u << 2;
const events_mask fetches_limit_hit = 1u << 3;
const events_mask custom_event      = 1u << 31;

class spectrum48 : public z80::processor<spectrum48> {
public:
    typedef processor<spectrum48> base;
    typedef fast_u32 ticks_type;

    spectrum48() {
        uint_fast32_t rnd = 0xde347a01;
        for(auto &cell : memory_image) {
            cell = static_cast<least_u8>(rnd);
            rnd = (rnd * 0x74392cef) ^ (rnd >> 16);
        }
    }

    virtual ~spectrum48();

    events_mask get_events() const { return events; }

    void stop() { events |= machine_stopped; }

    void tick(unsigned t) {
        ticks_since_int += t;

        // Handle stopping by hitting a specified number of ticks.
        if(ticks_to_stop) {
            if(ticks_to_stop > t) {
                ticks_to_stop -= t;
            } else {
                ticks_to_stop = 0;
                events |= ticks_limit_hit;
            }
        }
    }

    ticks_type get_ticks() const { return ticks_since_int; }

    void set_memory_byte(fast_u16 addr, fast_u8 n) {
        assert(addr < memory_image_size);
        memory_image[addr] = static_cast<least_u8>(n);
    }

    fast_u8 on_read_access(fast_u16 addr) {
        assert(addr < memory_image_size);
        return memory_image[addr];
    }

    void on_write_access(fast_u16 addr, fast_u8 n) {
        // Do not alter ROM.
        if(addr >= 0x4000)
            set_memory_byte(addr, n);
    }

    void handle_contention() {
        const ticks_type cont_base = 14335;
        if(ticks_since_int < cont_base)
            return;

        const ticks_type ticks_per_line = 224;
        if(ticks_since_int >= cont_base + screen_height * ticks_per_line)
            return;

        ticks_type ticks_since_new_line =
            (ticks_since_int - cont_base) % ticks_per_line;
        const unsigned pixels_per_tick = 2;
        if(ticks_since_new_line >= screen_width / pixels_per_tick)
            return;

        unsigned ticks_since_new_ula_cycle = ticks_since_new_line % 8;
        unsigned delay = ticks_since_new_ula_cycle == 7 ?
            0 : 6 - ticks_since_new_ula_cycle;
        tick(delay);
    }

    void handle_memory_contention(fast_u16 addr) {
        if(addr >= 0x4000 && addr < 0x8000)
            handle_contention();
    }

    fast_u8 on_fetch_cycle(fast_u16 addr, bool m1 = true) {
        // Handle stopping by hitting a specified number of fetches.
        // TODO: Rename fetches_to_stop -> m1_fetches_to_stop.
        if(m1 && fetches_to_stop && --fetches_to_stop == 0)
            events |= fetches_limit_hit;

        handle_memory_contention(addr);
        return base::on_fetch_cycle(addr, m1);
    }

    fast_u8 on_read_cycle(fast_u16 addr, unsigned ticks) {
        assert(ticks == 3);
        handle_memory_contention(addr);
        return base::on_read_cycle(addr, ticks);
    }

    void on_write_cycle(fast_u16 addr, fast_u8 n, unsigned ticks) {
        // assert(addr >= 0x4000);  // TODO
        assert(ticks == 3);
        handle_memory_contention(addr);
        base::on_write_cycle(addr, n, ticks);
    }

    void handle_contention_tick(fast_u16 addr) {
        handle_memory_contention(addr);
        tick(1);
    }

    fast_u8 on_4t_read_cycle(fast_u16 addr) {
        fast_u8 n = on_read_cycle(addr, /* ticks= */ 3);
        handle_contention_tick(addr);
        return n;
    }

    fast_u8 on_5t_read_cycle(fast_u16 addr) {
        fast_u8 n = on_read_cycle(addr, /* ticks= */ 3);
        handle_contention_tick(addr);
        handle_contention_tick(addr);
        return n;
    }

    void on_5t_write_cycle(fast_u16 addr, fast_u8 n) {
        on_write_cycle(addr, n, /* ticks= */ 3);
        handle_contention_tick(addr);
        handle_contention_tick(addr);
    }

    void handle_port_contention(fast_u16 addr) {
        if(addr < 0x4000 || addr >= 0x8000)  {
            if((addr & 1) == 0) {
                tick(1);
                handle_contention();
                tick(3);
            } else {
                tick(4);
            }
        } else {
            if((addr & 1) == 0) {
                handle_contention();
                tick(1);
                handle_contention();
                tick(3);
            } else {
                handle_contention();
                tick(1);
                handle_contention();
                tick(1);
                handle_contention();
                tick(1);
                handle_contention();
                tick(1);
            }
        }
    }

    fast_u8 on_input_cycle(fast_u16 addr) {
        handle_port_contention(addr);
        fast_u8 n = on_input(addr);

#if defined(TRACE) && TRACE
        create_trace();
        fprintf(trace_file, "read_port %04x %02x\n",
                unsigned(addr), unsigned(n));
        fflush(trace_file);
#endif

        return n;
    }

    virtual fast_u8 on_input(fast_u16 addr);

    void on_output_cycle(fast_u16 addr, fast_u8 n) {
        if((addr & 0xff) == 0xfe)
            border_color = n & 0x7;

        handle_port_contention(addr);
    }

    void on_set_addr_bus(fast_u16 addr) {
        addr_bus_value = addr;
    }

    void on_3t_exec_cycle() {
        handle_contention_tick(addr_bus_value);
        handle_contention_tick(addr_bus_value);
        handle_contention_tick(addr_bus_value);
    }

    void on_4t_exec_cycle() {
        handle_contention_tick(addr_bus_value);
        handle_contention_tick(addr_bus_value);
        handle_contention_tick(addr_bus_value);
        handle_contention_tick(addr_bus_value);
    }

    void on_5t_exec_cycle() {
        handle_contention_tick(addr_bus_value);
        handle_contention_tick(addr_bus_value);
        handle_contention_tick(addr_bus_value);
        handle_contention_tick(addr_bus_value);
        handle_contention_tick(addr_bus_value);
    }

    void disable_int_on_ei() {
        if(!allow_int_after_ei)
            base::disable_int_on_ei();
    }

    static const z80::size_type memory_image_size = 0x10000;  // 64K bytes.
    typedef least_u8 memory_image_type[memory_image_size];

    memory_image_type &get_memory() { return memory_image; }

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

    typedef frame_chunk frame_chunks_type[frame_height][chunks_per_frame_line];

    const frame_chunks_type &get_frame_chunks() { return frame_chunks; }

    void render_frame() {
        static_assert(bits_per_frame_pixel == 4,
                      "Unsupported frame pixel format!");
        static_assert(frame_pixels_per_chunk == 8,
                      "Unsupported frame chunk format!");

        const unsigned black = 0;
        const unsigned white = red_mask | green_mask | blue_mask;

        frame_chunk border_chunk = 0x11111111 * border_color;

        // Render the top border area.
        unsigned i = 0;
        for(; i != top_border_height; ++i) {
            frame_chunk *line = frame_chunks[i];
            for(unsigned j = 0; j != chunks_per_frame_line; ++j)
                line[j] = border_chunk;
        }

        // Render the screen area.
        fast_u16 line_addr = 0x4000;
        for(; i != top_border_height + screen_height; ++i) {
            frame_chunk *line = frame_chunks[i];

            // Left border.
            unsigned j = 0;
            for(; j != chunks_per_border_width; ++j)
                line[j] = border_chunk;

            // Screen.
            fast_u16 addr = line_addr;
            for(; j != chunks_per_border_width + chunks_per_screen_line; ++j) {
                fast_u8 b = on_read_access(addr);
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
                line[j] = border_chunk;

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
                line[j] = border_chunk;
        }
    }

    typedef uint_least32_t pixel_type;
    typedef pixel_type pixels_buffer_type[frame_height][frame_width];
    static const std::size_t pixels_buffer_size = sizeof(pixels_buffer_type);

    void get_frame_pixels(pixels_buffer_type &buffer) {
        static_assert(is_multiple_of(frame_width, frame_pixels_per_chunk),
                      "Fractional number of chunks per line is not supported!");
        static_assert(bits_per_frame_pixel == 4,
                      "Unsupported frame pixel format!");
        static_assert(frame_pixels_per_chunk == 8,
                      "Unsupported frame chunk format!");
        pixel_type *pixels = *buffer;
        std::size_t p = 0;
        for(const auto &frame_line : frame_chunks) {
            for(auto chunk : frame_line) {
                pixels[p++] = translate_color((chunk >> 28) & 0xf);
                pixels[p++] = translate_color((chunk >> 24) & 0xf);
                pixels[p++] = translate_color((chunk >> 20) & 0xf);
                pixels[p++] = translate_color((chunk >> 16) & 0xf);
                pixels[p++] = translate_color((chunk >> 12) & 0xf);
                pixels[p++] = translate_color((chunk >>  8) & 0xf);
                pixels[p++] = translate_color((chunk >>  4) & 0xf);
                pixels[p++] = translate_color((chunk >>  0) & 0xf);
            }
        }
    }

    events_mask run() {
        // Normalize the ticks-since-int counter.
        const ticks_type ticks_per_frame = 69888;
        ticks_since_int %= ticks_per_frame;

        // Reset events.
        events = no_events;

        // The active-int period needs special processing.
        if(!suppressed_int) {
            const ticks_type ticks_per_active_int = 32;
            while(!events && ticks_since_int < ticks_per_active_int) {
                handle_active_int();
                step();
            }
        }

        // Execute the rest of instructions in the frame.
        while(!events && ticks_since_int < ticks_per_frame)
            step();

        // Signal end-of-frame, if it's the case.
        if(ticks_since_int >= ticks_per_frame)
            events |= end_of_frame;

        return events;
    }

#if defined(TRACE) && TRACE
    FILE *trace_file = nullptr;

    void create_trace() {
        if(!trace_file)
            trace_file = fopen("zx_trace", "w");
    }

    void trace() {
        create_trace();

        if(trace_file && get_index_rp_kind() == z80::index_regp::hl) {
            fast_u16 pc = get_pc();
            fprintf(trace_file,
                    "PC:%04x AF:%04x BC:%04x DE:%04x HL:%04x IX:%04x IY:%04x SP:%04x MEMPTR:%04x IR:%04x %02x%02x%02x%02x%02x%02x%02x%02x\n",
                    static_cast<unsigned>(pc),
                    static_cast<unsigned>(get_af()),
                    static_cast<unsigned>(get_bc()),
                    static_cast<unsigned>(get_de()),
                    static_cast<unsigned>(get_hl()),
                    static_cast<unsigned>(get_ix()),
                    static_cast<unsigned>(get_iy()),
                    static_cast<unsigned>(get_sp()),
                    static_cast<unsigned>(get_memptr()),
                    static_cast<unsigned>(get_ir()),
                    static_cast<unsigned>(on_read_access((pc + 0) & 0xffff)),
                    static_cast<unsigned>(on_read_access((pc + 1) & 0xffff)),
                    static_cast<unsigned>(on_read_access((pc + 2) & 0xffff)),
                    static_cast<unsigned>(on_read_access((pc + 3) & 0xffff)),
                    static_cast<unsigned>(on_read_access((pc + 4) & 0xffff)),
                    static_cast<unsigned>(on_read_access((pc + 5) & 0xffff)),
                    static_cast<unsigned>(on_read_access((pc + 6) & 0xffff)),
                    static_cast<unsigned>(on_read_access((pc + 7) & 0xffff)));
            fflush(trace_file);
        }
    }

    void on_step() {
        trace();
        base::on_step();
    }

    bool handle_active_int() {
        trace();

        fprintf(trace_file, "int() to consider\n");
        fflush(trace_file);

        bool int_initiated = base::handle_active_int();
        if(trace_file) {
            if(int_initiated) {
                fprintf(trace_file, "int() accepted\n");
            } else {
                fprintf(trace_file, "int() skipped (int_disabled=%u, iff1=%u)\n",
                        is_int_disabled(), get_iff1());
            }
        }
        return int_initiated;
    }
#endif  // TRACE

protected:
    pixel_type translate_color(unsigned c) {
        uint_fast32_t r = 0;
        r |= (c & red_mask)   << (16 - red_bit);
        r |= (c & green_mask) << (8 - green_bit);
        r |= (c & blue_mask)  << (0 - blue_bit);

        // TODO: Use the real coefficients.
        r *= (c & brightness_mask) ? 0xff : 0xcc;

        return static_cast<pixel_type>(r);
    }

    events_mask events = no_events;

    ticks_type ticks_since_int = 0;
    ticks_type ticks_to_stop = 0;    // Null means no limit.
    ticks_type fetches_to_stop = 0;  // Null means no limit.

    fast_u16 addr_bus_value = 0;
    unsigned border_color = 0;

    // True if interrupts shall not be initiated at the beginning
    // of frames.
    bool suppressed_int = false;

    // True if interrupt can occur after EI instruction. Some
    // emulators such as SPIN allow that, so we should be able to
    // do the same to support RZX files produced by them.
    bool allow_int_after_ei = false;

private:
    frame_chunks_type frame_chunks;
    memory_image_type memory_image;
};

}  // namespace zx

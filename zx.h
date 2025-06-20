
/*  ZX Spectrum Emulator.
    https://github.com/kosarev/zx

    Copyright (C) 2017-2025 Ivan Kosarev.
    mail@ivankosarev.com

    Published under the MIT license.
*/

#include <algorithm>

#include "z80/z80.h"

namespace zx {

using z80::fast_u8;
using z80::fast_u16;
using z80::fast_u32;
using z80::least_u8;
using z80::least_u16;

using z80::unreachable;
using z80::make16;
using z80::mask16;
using z80::inc16;
using z80::dec16;

template<typename T>
T non_constexpr() {
    return T();
}

template<typename T>
constexpr T div_exact(T a, T b) {
    return a % b == 0 ? a / b : non_constexpr<T>();
}

template<typename T>
constexpr T div_ceil(T a, T b) {
    return (a + b - 1) / b;
}


template<typename T>
constexpr bool is_multiple_of(T a, T b) {
    return b != 0 && a % b == 0;
}

template<typename T>
constexpr bool round_up(T a, T b) {
    return div_ceil(a, b) * b;
}

typedef fast_u32 events_mask;
const events_mask no_events         = 0;
const events_mask machine_stopped   = 1u << 0;  // TODO: Eliminate.
const events_mask end_of_frame      = 1u << 1;
const events_mask ticks_limit_hit   = 1u << 2;
const events_mask fetches_limit_hit = 1u << 3;
const events_mask breakpoint_hit    = 1u << 4;
const events_mask custom_event      = 1u << 31;

typedef fast_u8 memory_marks;
const memory_marks no_marks           = 0;
const memory_marks breakpoint_mark    = 1u << 0;
const memory_marks visited_instr_mark = 1u << 7;

enum class spectrum_model {
    spectrum_48,
    spectrum_128,
};

#if defined(_MSC_VER)
#pragma pack(push, 1)
class memory_image {
#else
class __attribute__((packed)) memory_image {
#endif
public:
    enum page : unsigned {
        // 48K model memory map.
        rom0,
        ram5,
        ram2,
        ram0,

        // 128K model extra pages.
        rom1,
        ram1,
        ram3,
        ram4,
        ram6,
        ram7,
    };

    memory_image() {}

    void reset() {
        uint_fast32_t rnd = 0xde347a01;
        for(auto &b : bytes) {
            b = static_cast<least_u8>(rnd);
            rnd = (rnd * 0x74392cef) ^ (rnd >> 16);
        }
    }

    fast_u8 read(fast_u16 addr, page rom, page ram) const {
        return bytes[get_offset(addr, rom, ram)];
    }

    void write(fast_u16 addr, fast_u8 n, page rom, page ram) {
        bytes[get_offset(addr, rom, ram)] = static_cast<least_u8>(n);
    }

    static page get_ram_page(unsigned n) {
        assert(n < 8);
        static const page pages[8] = {ram0, ram1, ram2, ram3,
                                      ram4, ram5, ram6, ram7};
        return pages[n];
    }

    static page get_rom_page(unsigned n) {
        assert(n < 2);
        static const page pages[2] = {rom0, rom1};
        return pages[n];
    }

private:
    static constexpr unsigned page_size = 0x4000;
    static constexpr unsigned num_pages = ram7 + 1;

    // TODO: Support cases where only 48K memory is needed.
    static constexpr fast_u32 image_size =
        static_cast<fast_u32>(page_size) * num_pages;

    static fast_u16 get_offset(fast_u16 addr, page rom, page ram) {
        assert(addr < z80::address_space_size);
        assert(rom == rom0 || rom == rom1);
        assert(ram != rom0 && ram != rom1);

        if (addr < 0x4000)
            return rom * page_size + addr;

        if (addr < 0xc000)
            return addr;

        return ram * page_size + addr % page_size;
    }

    least_u8 bytes[image_size];
};
#if defined(_MSC_VER)
#pragma pack(pop)
#endif

class disassembler : public z80::z80_disasm<disassembler> {
public:
    typedef z80::z80_disasm<disassembler> base;

    disassembler(fast_u16 addr, memory_image::page rom_page,
                 memory_image::page ram_page, const memory_image &memory)
        : addr(addr), rom_page(rom_page), ram_page(ram_page), memory(memory)
    {}

    void on_emit(const char *out) {
        std::snprintf(output_buff, max_output_buff_size, "%s", out);
    }

    fast_u8 on_read_next_byte() {
        fast_u8 n = memory.read(mask16(addr), rom_page, ram_page);
        addr = inc16(addr);
        return n;
    }

    fast_u16 on_get_last_read_addr() const {
        return dec16(addr);
    }

    const char *on_disassemble() {
        // Skip prefixes.
        base::on_disassemble();
        while(get_iregp_kind() != z80::iregp::hl)
            base::on_disassemble();
        return output_buff;
    }

private:
    fast_u16 addr;
    memory_image::page rom_page;
    memory_image::page ram_page;
    const memory_image &memory;

    static const std::size_t max_output_buff_size = 32;
    char output_buff[max_output_buff_size];
};

template<typename D>
class spectrum : public z80::z80_cpu<D> {
public:
    typedef z80::z80_cpu<D> base;
    typedef fast_u32 ticks_type;

    spectrum() {
        on_reset_memory();
    }

    events_mask get_events() const { return events; }

    void stop() { events |= machine_stopped; }

    void on_tick(unsigned t) {
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

    void on_reset_memory() {
        self().on_get_memory().reset();
    }

    fast_u8 on_read(fast_u16 addr) {
        return self().on_get_memory().read(addr, rom_page, ram_page);
    }

    void on_write(fast_u16 addr, fast_u8 n) {
        // Do not alter ROM.
        if(addr >= 0x4000)
            self().on_get_memory().write(addr, n, rom_page, ram_page);
    }

    ticks_type get_cont_base() const {
        // TODO: We sample ~INT during the last tick of the
        // previous instruction, so we add 1 to the contention
        // base to compensate that.
        switch (self().on_get_model()) {
        case spectrum_model::spectrum_48:
            return 14335 + 1;
        case spectrum_model::spectrum_128:
            return 14361 + 1;  // TODO: Correct?
        }
        unreachable("Unknown Spectrum model.");
    }

    void handle_contention() {
        ticks_type cont_base = get_cont_base();
        ticks_type ticks_per_line = get_ticks_per_line();

        if(ticks_since_int < cont_base)
            return;

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
        on_tick(delay);
    }

    void handle_memory_contention(fast_u16 addr) {
        if(addr >= 0x4000 && addr < 0x8000)
            handle_contention();
    }

    fast_u8 on_fetch_cycle() {
        handle_memory_contention(self().get_pc());
        return base::on_fetch_cycle();
    }

    fast_u8 on_m1_fetch_cycle() {
        // Handle stopping by hitting a specified number of fetches.
        // TODO: Rename fetches_to_stop -> m1_fetches_to_stop.
        if(fetches_to_stop && --fetches_to_stop == 0)
            events |= fetches_limit_hit;

        return base::on_m1_fetch_cycle();
    }

#if 0  // TODO
    fast_u8 on_m1_fetch_cycle() {
        fast_u8 n = self().on_fetch_cycle();
        self().on_inc_r_reg();
        return n;
    }
#endif

    fast_u8 on_read_cycle(fast_u16 addr) {
        handle_memory_contention(addr);
        return base::on_read_cycle(addr);
    }

    void on_write_cycle(fast_u16 addr, fast_u8 n) {
        // TODO: Render to (current_tick + 1) and then update
        // the byte as the new value is sampled at
        // the 2nd tick of the output cycle.
        // TODO: The "+ 1" thing is still wrong as there may
        // be contentions in the middle.
        render_screen_to_tick(get_ticks() + 1);

        handle_memory_contention(addr);
        base::on_write_cycle(addr, n);
    }

    void handle_contention_tick() {
        handle_memory_contention(addr_bus_value);
        on_tick(1);
    }

    void on_read_cycle_extra_1t() {
        handle_contention_tick();
    }

    void on_read_cycle_extra_2t() {
        handle_contention_tick();
        handle_contention_tick();
    }

    void on_write_cycle_extra_2t() {
        handle_contention_tick();
        handle_contention_tick();
    }

    void handle_port_contention(fast_u16 addr) {
        if(addr < 0x4000 || addr >= 0x8000) {
            if((addr & 1) == 0) {
                on_tick(1);
                handle_contention();
                on_tick(3);
            } else {
                on_tick(4);
            }
        } else {
            if((addr & 1) == 0) {
                handle_contention();
                on_tick(1);
                handle_contention();
                on_tick(3);
            } else {
                handle_contention();
                on_tick(1);
                handle_contention();
                on_tick(1);
                handle_contention();
                on_tick(1);
                handle_contention();
                on_tick(1);
            }
        }
    }

    fast_u8 on_input_cycle(fast_u16 addr) {
        handle_port_contention(addr);
        fast_u8 n = self().on_input(addr);

        if(FILE *trace = get_trace_file()) {
            std::fprintf(trace, "read_port %04x %02x\n",
                         static_cast<unsigned>(addr),
                         static_cast<unsigned>(n));
            std::fflush(trace);
        }

        return n;
    }

    bool is_marked_addr(fast_u16 addr, memory_marks marks) const {
        return (memory_marks[mask16(addr)] & marks) != 0;
    }

    bool is_breakpoint_addr(fast_u16 addr) const {
        return is_marked_addr(addr, breakpoint_mark);
    }

    void mark_addr(fast_u16 addr, memory_marks marks) {
        addr = mask16(addr);
        memory_marks[addr] = static_cast<least_u8>(memory_marks[addr] | marks);
    }

    void mark_addrs(fast_u16 addr, fast_u16 size, memory_marks marks) {
        for(fast_u16 i = 0; i != size; ++i)
            mark_addr(addr + i, marks);
    }

    void on_set_pc(fast_u16 pc) {
        // Catch breakpoints.
        if(is_breakpoint_addr(pc))
            events |= breakpoint_hit;

        base::on_set_pc(pc);
    }

    fast_u8 on_input(fast_u16 addr) {
        z80::unused(addr);
        return 0xbf;
    }

    void on_output_cycle(fast_u16 addr, fast_u8 n) {
        if(FILE *trace = get_trace_file()) {
            std::fprintf(trace, "write_port %04x %02x\n",
                         static_cast<unsigned>(addr),
                         static_cast<unsigned>(n));
            std::fflush(trace);
        }

        self().on_output(addr, n);

        ticks_type t = get_ticks();
        if((addr & 0xff) == 0xfe) {
            // TODO: Render to (current_tick + 1) and then update
            // the border colour as the new value is sampled at
            // the 2nd tick of the output cycle.
            // TODO: The "+ 1" thing is still wrong as there may
            // be contentions in the middle.
            render_screen_to_tick(t + 1);
            border_colour = n & 0x7;
        }

        // Handle the 0x7ffd port.
        // https://worldofspectrum.org/faq/reference/128kreference.htm
        if(self().on_get_model() == spectrum_model::spectrum_128 &&
               (addr & 0x8002) == 0 && !ignore_7ffd_port_writes) {
            unsigned ram_page_n = n & 7;
            ram_page = memory_image::get_ram_page(ram_page_n);

            unsigned rom_page_n = (n >> 4) & 1;
            rom_page = memory_image::get_rom_page(rom_page_n);

            ignore_7ffd_port_writes = n & 0x20;

            shadow_screen = n & 8;

            if(FILE *trace = get_trace_file()) {
                std::fprintf(trace,
                             "ram %d, rom %d, ignore_writes %d, screen %d\n",
                             static_cast<int>(ram_page_n),
                             static_cast<int>(rom_page_n),
                             static_cast<int>(ignore_7ffd_port_writes),
                             static_cast<int>(shadow_screen));
                std::fflush(trace);
            }
        }

        if(num_port_writes < max_num_port_writes) {
            uint_least64_t v = 0;
            v |= static_cast<uint_least64_t>(addr) << 0;
            v |= static_cast<uint_least64_t>(n) << 16;
            v |= static_cast<uint_least64_t>(t) << 32;
            port_writes[num_port_writes++] = v;
        }

        handle_port_contention(addr);
    }

    void on_set_addr_bus(fast_u16 addr) {
        addr_bus_value = addr;
    }

    void on_3t_exec_cycle() {
        handle_contention_tick();
        handle_contention_tick();
        handle_contention_tick();
    }

    void on_4t_exec_cycle() {
        handle_contention_tick();
        handle_contention_tick();
        handle_contention_tick();
        handle_contention_tick();
    }

    void on_5t_exec_cycle() {
        handle_contention_tick();
        handle_contention_tick();
        handle_contention_tick();
        handle_contention_tick();
        handle_contention_tick();
    }

    void disable_int_on_ei() {
        if(!int_after_ei_allowed)
            base::disable_int_on_ei();
    }

    static constexpr ticks_type max_ticks_per_frame = 70908;

    ticks_type get_ticks_per_frame() const {
        switch (self().on_get_model()) {
        case spectrum_model::spectrum_48:
            static_assert(max_ticks_per_frame >= 69888,
                          "max_ticks_per_frame too small!");
            return 69888;
        case spectrum_model::spectrum_128:
            static_assert(max_ticks_per_frame >= 70908,
                          "max_ticks_per_frame too small!");
            return 70908;
        }
        unreachable("Unknown Spectrum model.");
    }

    ticks_type get_ticks_per_line() const {
        switch (self().on_get_model()) {
        case spectrum_model::spectrum_48:
            return 224;
        case spectrum_model::spectrum_128:
            return 228;
        }
        unreachable("Unknown Spectrum model.");
    }

    static const ticks_type ticks_per_active_int = 32;

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
    static const unsigned pixels_per_frame_chunk = 8;

    // The type of frame chunks.
    static const unsigned frame_chunk_width = 32;
    static_assert(
        bits_per_frame_pixel * pixels_per_frame_chunk <= frame_chunk_width,
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
        div_exact(border_width, pixels_per_frame_chunk);
    static const unsigned chunks_per_screen_line =
        div_exact(screen_width, pixels_per_frame_chunk);
    static const unsigned chunks_per_frame_line =
        div_exact(frame_width, pixels_per_frame_chunk);

    typedef frame_chunk screen_chunks_type[frame_height][chunks_per_frame_line];

    const screen_chunks_type &get_screen_chunks() const {
        return screen_chunks;
    }

    static const unsigned
        ticks_per_shortest_out_instr = 11;  // OUT (n), A  f(4) r(3) o(4)
    static const unsigned max_num_port_writes =
        div_ceil<ticks_type>(max_ticks_per_frame,
                             ticks_per_shortest_out_instr);
    using port_writes_type = uint_least64_t[max_num_port_writes];

    unsigned get_num_port_writes() const { return num_port_writes; }
    const port_writes_type &get_port_writes() const { return port_writes; }

    // TODO: Name the constants.
    // TODO: private
    void start_new_frame() {
        ticks_since_int %= get_ticks_per_frame();
        render_tick = 0;

        ++frame_counter;
        if(frame_counter % 16 == 0)
            flash_mask ^= 0xffff;

        num_port_writes = 0;
    }

    // TODO: private
    static fast_u16 get_pixel_pattern_offset(unsigned frame_line,
                                             unsigned pixel_in_line) {
        assert(frame_line >= 64);
        assert(frame_line < 64 + screen_height);
        assert(pixel_in_line >= border_width);
        assert(pixel_in_line < border_width + screen_width);

        fast_u32 offset = 0;

        // Adjust the address according to the third of the
        // screen.
        unsigned line = frame_line - 64;
        offset += 0x800 * (line / 64);
        line %= 64;

        // See which character line it is.
        offset += 0x20 * (line / 8);
        line %= 8;

        // Then, adjust according to the pixel line within the
        // character line.
        offset += 0x100 * line;

        // Finally, apply the offset in line.
        offset += (pixel_in_line - border_width) / 8;

        return offset;
    }

    // TODO: private
    static fast_u16 get_colour_attrs_offset(unsigned frame_line,
                                            unsigned pixel_in_line) {
        assert(frame_line >= 64);
        assert(frame_line < 64 + screen_height);
        assert(pixel_in_line >= border_width);
        assert(pixel_in_line < border_width + screen_width);

        fast_u16 offset = 0;

        unsigned line = frame_line - 64;
        offset += 0x20 * (line / 8);

        offset += (pixel_in_line - border_width) / 8;

        return offset;
    }

    // TODO: Name the constants.
    // TODO: Optimize.
    void render_screen_to_tick(ticks_type end_tick) {
        static_assert(bits_per_frame_pixel == 4,
                      "Unsupported frame pixel format!");
        static_assert(pixels_per_frame_chunk == 8,
                      "Unsupported frame chunk format!");

        constexpr memory_image::page rom0 = memory_image::rom0;
        constexpr memory_image::page ram5 = memory_image::ram5;
        constexpr memory_image::page ram7 = memory_image::ram7;
        memory_image::page screen_page = shadow_screen ? ram7 : ram5;

        constexpr fast_u16 screen_addr = 0xc000;
        constexpr fast_u16 screen_attr_addr = screen_addr + 0x1800;

        const memory_image &memory = self().on_get_memory();

        ticks_type ticks_per_line = get_ticks_per_line();

        // TODO: Render the border by whole chunks when possible.
        while(render_tick < end_tick) {
            // The tick since the beam was at the imaginary
            // beginning (the top left corner) of the frame.
            ticks_type frame_tick = render_tick + border_width / 2 - 8 / 2;  // TODO

            // Latch screen area bytes. Note that the first time
            // we do that when the beam is outside of the screen
            // area.
            auto frame_line = static_cast<unsigned>(frame_tick / ticks_per_line);
            auto pixel_in_line = static_cast<unsigned>(frame_tick % ticks_per_line) * 2;
            bool is_screen_latching_area =
                frame_line >= 64 &&
                frame_line < 64 + screen_height &&
                pixel_in_line >= border_width - 8 &&
                pixel_in_line < border_width + screen_width - 8;
            if(is_screen_latching_area &&
                    (render_tick - frame_line * ticks_per_line) % 8 == 0) {
                fast_u16 pattern_addr = screen_addr +
                    get_pixel_pattern_offset(frame_line, pixel_in_line + 8);
                // TODO
                // printf("%d -> 0x%04x\n", (int) render_tick, (unsigned) addr);
                fast_u8 pattern_hi =
                    memory.read(pattern_addr + 0, rom0, screen_page);
                fast_u8 pattern_lo =
                    memory.read(pattern_addr + 1, rom0, screen_page);
                latched_pixel_pattern = make16(pattern_hi, pattern_lo);

                fast_u16 attr_addr = screen_attr_addr +
                    get_colour_attrs_offset(frame_line, pixel_in_line + 8);
                fast_u8 attr_hi =
                    memory.read(attr_addr + 0, rom0, screen_page);
                fast_u8 attr_lo =
                    memory.read(attr_addr + 1, rom0, screen_page);
                latched_colour_attrs = make16(attr_hi, attr_lo);
            }

            // Render the screen area.
            const unsigned top_hidden_lines = 64 - top_border_height;
            bool is_screen_area = frame_line >= 64 &&
                                  frame_line < 64 + screen_height &&
                                  pixel_in_line >= border_width &&
                                  pixel_in_line < border_width + screen_width;
            if(is_screen_area) {
                // TODO: Support rendering by whole chunks for
                //       better performance.

                unsigned chunk_index = pixel_in_line / pixels_per_frame_chunk;
                unsigned pixel_in_chunk = pixel_in_line % pixels_per_frame_chunk;

                unsigned screen_line = frame_line - top_hidden_lines;
                frame_chunk *line_chunks = screen_chunks[screen_line];
                frame_chunk *chunk = &line_chunks[chunk_index];

                unsigned pixel_in_cycle = (pixel_in_line - border_width) % 16;
                if(pixel_in_cycle == 0) {
                    latched_pixel_pattern2 = latched_pixel_pattern;
                    latched_colour_attrs2 = latched_colour_attrs;
                }

                auto attr = static_cast<unsigned>(latched_colour_attrs2 >> ((15 - pixel_in_cycle) / 8 * 8));
                unsigned brightness = attr >> (6 - brightness_bit) & brightness_mask;
                unsigned ink_colour = ((attr >> 0) & 0x7) | brightness;
                unsigned paper_colour = ((attr >> 3) & 0x7) | brightness;

                // TODO: We can compute the whole chunk as soon
                //       as we read the bytes. And then just
                //       apply them here.
                unsigned pixels_value = 0;
                fast_u16 pattern = latched_pixel_pattern2;
                if((attr & 0x80) != 0)
                    pattern ^= flash_mask;
                pixels_value |= (pattern & ((1u << 15) >> pixel_in_cycle)) != 0 ?
                    (ink_colour << 28) : (paper_colour << 28);
                pixels_value |= (pattern & ((1u << 14) >> pixel_in_cycle)) != 0 ?
                    (ink_colour << 24) : (paper_colour << 24);
                pixels_value >>= pixel_in_chunk * 4;

                // printf("%d, pixel_in_cycle %d\n", (int) render_tick, (int) pixel_in_cycle);

                unsigned pixels_mask = 0xff000000 >> (pixel_in_chunk * 4);

                *chunk = (*chunk & ~pixels_mask) | pixels_value;

                ++render_tick;
                continue;
            }

            // Render the border area.
            // TODO: We can simply initialize the render tick
            //       with the first visible tick value and stop
            //       the rendering loop at the last visible tick.
            //       Just don't forget about latching.
            bool is_visible_area =
                frame_line >= top_hidden_lines &&
                frame_line < 64 + screen_height + bottom_border_height &&
                pixel_in_line < frame_width;
            if(is_visible_area) {
                if(render_tick % 4 == 0)
                    latched_border_colour = border_colour;

                unsigned chunk_index = pixel_in_line / pixels_per_frame_chunk;
                unsigned pixel_in_chunk = pixel_in_line % pixels_per_frame_chunk;

                // TODO: Support rendering by whole chunks for
                //       better performance.
                unsigned screen_line = frame_line - top_hidden_lines;
                frame_chunk *line_chunks = screen_chunks[screen_line];
                frame_chunk *chunk = &line_chunks[chunk_index];
                unsigned pixels_value = (0x11000000 * latched_border_colour) >> (pixel_in_chunk * 4);
                unsigned pixels_mask = 0xff000000 >> (pixel_in_chunk * 4);
                *chunk = (*chunk & ~pixels_mask) | pixels_value;

                ++render_tick;
                continue;
            }

            ++render_tick;
        }
    }

    // TODO: Move to the private section.
    unsigned frame_counter = 0;
    ticks_type render_tick = 0;
    unsigned latched_border_colour = 0;
    fast_u16 latched_pixel_pattern = 0;
    fast_u16 latched_colour_attrs = 0;
    fast_u16 latched_pixel_pattern2 = 0;
    fast_u16 latched_colour_attrs2 = 0;
    fast_u16 flash_mask = 0;

    void render_screen() {
        render_screen_to_tick(get_ticks_per_frame());
    }

    typedef uint_least32_t pixel_type;
    typedef pixel_type pixels_buffer_type[frame_height][frame_width];
    static const std::size_t pixels_buffer_size = sizeof(pixels_buffer_type);

    void get_frame_pixels(pixels_buffer_type &buffer) {
        static_assert(is_multiple_of(frame_width, pixels_per_frame_chunk),
                      "Fractional number of chunks per line is not supported!");
        static_assert(bits_per_frame_pixel == 4,
                      "Unsupported frame pixel format!");
        static_assert(pixels_per_frame_chunk == 8,
                      "Unsupported frame chunk format!");
        pixel_type *pixels = *buffer;
        std::size_t p = 0;
        for(const auto &screen_line : screen_chunks) {
            for(auto chunk : screen_line) {
                pixels[p++] = translate_colour((chunk >> 28) & 0xf);
                pixels[p++] = translate_colour((chunk >> 24) & 0xf);
                pixels[p++] = translate_colour((chunk >> 20) & 0xf);
                pixels[p++] = translate_colour((chunk >> 16) & 0xf);
                pixels[p++] = translate_colour((chunk >> 12) & 0xf);
                pixels[p++] = translate_colour((chunk >>  8) & 0xf);
                pixels[p++] = translate_colour((chunk >>  4) & 0xf);
                pixels[p++] = translate_colour((chunk >>  0) & 0xf);
            }
        }
    }

    events_mask run() {
        // Normalize the ticks-since-int counter.
        ticks_type ticks_per_frame = get_ticks_per_frame();
        if (ticks_since_int >= ticks_per_frame)
            start_new_frame();

        // Reset events.
        events = no_events;

        // Execute instructions that fit the current frame.
        while(!events && ticks_since_int < ticks_per_frame) {
            if(!int_suppressed) {
                // ~INT is sampled during the last tick of the
                // previous instruction, so we have to see
                // whether ~INT was active during that last tick
                // and not the current tick.
                ticks_type previous_tick = ticks_since_int - 1;
                if(previous_tick < ticks_per_active_int)
                    on_handle_active_int();
            }

            on_step();
        }

        // Signal end-of-frame, if it's the case.
        if(ticks_since_int >= ticks_per_frame)
            events |= end_of_frame;

        return events;
    }

    FILE *get_trace_file() {
        if(!trace_enabled)
            return nullptr;

        static FILE *trace = nullptr;
        if(!trace)
            trace = std::fopen("zx_trace", "w");

        return trace;
    }

    void trace_state() {
        FILE *trace = get_trace_file();
        if(!trace)
            return;

        if(self().get_iregp_kind() != z80::iregp::hl)
            return;

        fast_u16 pc = self().get_pc();
        bool new_rom_instr =
            pc < 0x4000 && !is_marked_addr(pc, visited_instr_mark);

        disassembler disasm(pc, rom_page, ram_page, self().on_get_memory());
        std::fprintf(trace,
            "%7u "
            "PC:%04x AF:%04x BC:%04x DE:%04x HL:%04x IX:%04x IY:%04x "
            "SP:%04x WZ:%04x IR:%04x iff1:%u "
            "%02x%02x%02x%02x%02x%02x%02x%02x %s%s\n",
            static_cast<unsigned>(ticks_since_int),
            static_cast<unsigned>(pc),
            static_cast<unsigned>(self().get_af()),
            static_cast<unsigned>(self().get_bc()),
            static_cast<unsigned>(self().get_de()),
            static_cast<unsigned>(self().get_hl()),
            static_cast<unsigned>(self().get_ix()),
            static_cast<unsigned>(self().get_iy()),
            static_cast<unsigned>(self().get_sp()),
            static_cast<unsigned>(self().get_wz()),
            static_cast<unsigned>(self().get_ir()),
            static_cast<unsigned>(self().get_iff1()),
            static_cast<unsigned>(on_read((pc + 0) & 0xffff)),
            static_cast<unsigned>(on_read((pc + 1) & 0xffff)),
            static_cast<unsigned>(on_read((pc + 2) & 0xffff)),
            static_cast<unsigned>(on_read((pc + 3) & 0xffff)),
            static_cast<unsigned>(on_read((pc + 4) & 0xffff)),
            static_cast<unsigned>(on_read((pc + 5) & 0xffff)),
            static_cast<unsigned>(on_read((pc + 6) & 0xffff)),
            static_cast<unsigned>(on_read((pc + 7) & 0xffff)),
            disasm.on_disassemble(), new_rom_instr ? " [new]" : "");
        std::fflush(trace);
    }

    void on_step() {
        trace_state();
        mark_addr(self().get_pc(), visited_instr_mark);
        base::on_step();
    }

    bool on_handle_active_int() {
        bool int_initiated = base::on_handle_active_int();
        if(FILE *trace = get_trace_file()) {
            if(int_initiated) {
                std::fprintf(trace, "INT accepted\n");
            } else {
                std::fprintf(trace, "INT ignored (int_disabled=%u, iff1=%u)\n",
                             self().is_int_disabled(), self().get_iff1());
            }
            std::fflush(trace);
        }
        return int_initiated;
    }

protected:
    using base::self;

    pixel_type translate_colour(unsigned c) {
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
    unsigned border_colour = 0;

    // True if interrupts shall not be initiated at the beginning
    // of frames.
    bool int_suppressed = false;

    // True if interrupt can occur after EI instruction. Some
    // emulators such as SPIN allow that, so we should be able to
    // do the same to support RZX files produced by them.
    bool int_after_ei_allowed = false;

    bool trace_enabled = false;

private:
    memory_image::page rom_page = memory_image::rom0;
    memory_image::page ram_page = memory_image::ram0;

    bool ignore_7ffd_port_writes = false;

    bool shadow_screen = false;

    screen_chunks_type screen_chunks;

    unsigned num_port_writes = 0;
    port_writes_type port_writes;

    least_u8 memory_marks[z80::address_space_size] = {};
};

}  // namespace zx

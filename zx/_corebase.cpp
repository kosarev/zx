
/*  ZX Spectrum Emulation Module for Python.
    https://github.com/kosarev/zx

    Copyright (C) 2017-2026 Ivan Kosarev.
    mail@ivankosarev.com

    Published under the MIT license.
*/

#include <Python.h>

#include <new>

#include "../zx.h"

namespace {

using zx::fast_u8;
using zx::fast_u16;
using zx::least_u8;
using zx::least_u16;
using zx::unreachable;

typedef uint_least32_t least_u32;
typedef uint_least64_t least_u64;
typedef uint_fast64_t fast_u64;

class decref_guard {
public:
    decref_guard(PyObject *object)
        : object(object)
    {}

    ~decref_guard() {
        Py_XDECREF(object);
    }

private:
    PyObject *object;
};

namespace Core {

#if defined(_MSC_VER)
#pragma pack(push, 1)
struct processor_state {
#else
struct __attribute__((packed)) processor_state {
#endif
    least_u16 bc;
    least_u16 de;
    least_u16 hl;
    least_u16 af;
    least_u16 ix;
    least_u16 iy;

    least_u16 alt_bc;
    least_u16 alt_de;
    least_u16 alt_hl;
    least_u16 alt_af;

    least_u16 pc;
    least_u16 sp;
    least_u16 ir;
    least_u16 wz;

    least_u8 iff1;
    least_u8 iff2;
    least_u8 int_mode;
    least_u8 index_rp_kind;
};
#if defined(_MSC_VER)
#pragma pack(pop)
#endif

// The configuration part of the core state: the facts that survive
// a plain reset and return to these canonical defaults on
// _reset_config().
#if defined(_MSC_VER)
#pragma pack(push, 1)
struct core_config {
#else
struct __attribute__((packed)) core_config {
#endif
    // The CPU clock, in Hz.
    least_u32 ticks_per_second = 3500000;

    least_u32 ticks_per_horizontal_retrace = 48;
    least_u32 lines_per_vertical_retrace = 24;

    // The tick, counted from the start of INT, at which contention
    // first applies, one tick before the top-left screen pixel.
    least_u32 contention_base = 14335;
};
#if defined(_MSC_VER)
#pragma pack(pop)
#endif

#if defined(_MSC_VER)
#pragma pack(push, 1)
struct machine_state {
#else
struct __attribute__((packed)) machine_state {
#endif
    processor_state proc;

    least_u32 ticks_since_int = 0;
    uint_least64_t tick_count = 0;
    least_u32 m1_fetches_to_stop = 0;
    least_u32 ticks_to_stop = 0;
    least_u32 events = 0;
    least_u8 int_suppressed = false;
    least_u8 int_after_ei_allowed = false;
    least_u8 border_colour = 7;
    least_u8 trace_enabled = false;
    least_u8 model = static_cast<least_u8>(zx::spectrum_model::spectrum_48);
    least_u8 padding1;
    least_u8 padding2;
    least_u8 padding3;

    core_config config;

    zx::memory_image memory;
};
#if defined(_MSC_VER)
#pragma pack(pop)
#endif

// A series of port-read samples supplied for the current quantum:
// the value a device drives on the input lines of the port
// addresses matching the series' address pattern, as a function of
// time. Like SoundPulses, each entry states the value driven since
// the entry's tick; the series covers num_ticks ticks from tick 0
// and must state its value from tick 0 on, explicitly spanning its
// whole range -- no values carry over between quanta. 1s in a
// value are the bits the device does not drive.
//
// Ticks count in the device's own resolution, device_resolution
// ticks a second. Tick 0 is the last device-resolution tick at or
// before the floor the quantum starts at; reads never precede the
// floor, so every read falls at or after tick 0. Each sample is
// one 64-bit word in the entries buffer: the value in the low 8
// bits and the tick in the rest.
//
// Reads happen at core ticks, so their moments and the entries'
// compare in the common resolution of
// core_resolution * device_resolution ticks a second, with
// core_resolution being the core's ticks per second.
// core_resolution_tick is the floor's core tick, and
// device_resolution_tick_remainder is how far the floor lies past
// tick 0, in the common resolution. The compared differences are
// bounded by the quantum span, and both resolutions must be
// physical ones, each under 2^32 ticks a second -- never rates
// produced by mixing different-resolution Time values -- so the
// products fit unsigned 64-bit integers; arbitrary-precision
// arithmetic stays on the Python side.
struct port_read_series {
    least_u64 core_resolution_tick;
    least_u64 device_resolution;
    least_u64 device_resolution_tick_remainder;
    least_u16 addr_mask;
    least_u16 addr_value;
    least_u64 num_ticks;
    Py_buffer entries;

    // The entry whose value is currently driven. Within a run,
    // reads never go back in time, so this only advances as the
    // reads progress through the quantum.
    unsigned current_entry;
};

class machine_emulator : public zx::spectrum<machine_emulator> {
public:
    typedef zx::spectrum<machine_emulator> base;

    machine_emulator() {
        retrieve_state();
    }

    ~machine_emulator() {
        clear_port_read_samples();
    }

    machine_state &get_machine_state() {
        return state;
    }

    void retrieve_state() {
        state.proc = get_processor_state();

        state.ticks_since_int = ticks_since_int;
        state.tick_count = tick_count;
        state.m1_fetches_to_stop = m1_fetches_to_stop;
        state.ticks_to_stop = ticks_to_stop;
        state.events = events;
        state.int_suppressed = int_suppressed;
        state.int_after_ei_allowed = int_after_ei_allowed;
        state.border_colour = border_colour;
        state.trace_enabled = trace_enabled;
    }

    void install_state() {
        set_processor_state(state.proc);

        ticks_since_int = state.ticks_since_int;
        tick_count = state.tick_count;
        m1_fetches_to_stop = state.m1_fetches_to_stop;
        ticks_to_stop = state.ticks_to_stop;
        events = state.events;
        int_suppressed = state.int_suppressed;
        int_after_ei_allowed = state.int_after_ei_allowed;
        border_colour = state.border_colour;
        trace_enabled = state.trace_enabled;
    }

    pixels_buffer_type &get_frame_pixels() {
        base::get_frame_pixels(pixels);
        return pixels;
    }

    events_mask::type run(PyObject *dispatcher) {
        // Hold the dispatcher for the duration of the run so the Python
        // callbacks invoked from the C core (e.g. on input) can be
        // passed it; the Python side never stores it. Cleared on
        // return.
        run_dispatcher = dispatcher;

        install_state();
        events_mask::type events = base::run();

        // Bring the rendered screen up to the current tick before
        // handing control back, so the Python side always sees the
        // screen state as of this moment — mid-frame returns (e.g. a
        // sub-frame tick limit) included. Forward-only, so it composes
        // with the rest of the frame's rendering.
        render_screen_to_tick(get_ticks());

        retrieve_state();

        run_dispatcher = nullptr;
        return events;
    }

    // Executes the instruction a breakpoint trapped at, following the
    // same conventions as run().
    events_mask::type step_over_breakpoint(PyObject *dispatcher) {
        run_dispatcher = dispatcher;

        install_state();
        events_mask::type events = base::on_step_over_breakpoint();
        render_screen_to_tick(get_ticks());
        retrieve_state();

        run_dispatcher = nullptr;
        return events;
    }

    bool on_handle_active_int() {
        install_state();
        bool int_initiated = base::on_handle_active_int();
        retrieve_state();
        return int_initiated;
    }

    PyObject *set_on_input_callback(PyObject *callback) {
        PyObject *old_callback = on_input_callback;
        on_input_callback = callback;
        return old_callback;
    }

    PyObject *set_on_output_callback(PyObject *callback) {
        PyObject *old_callback = on_output_callback;
        on_output_callback = callback;
        return old_callback;
    }

    // The samples live for one quantum: the caller replaces them
    // wholesale each quantum -- clear, then add each series whole.
    void clear_port_read_samples() {
        for(unsigned i = 0; i != num_port_read_series; ++i)
            PyBuffer_Release(&port_read_series_list[i].entries);
        num_port_read_series = 0;
    }

    // Takes ownership of the entries buffer. Returns false when
    // there is no room for another series.
    bool add_port_read_samples(fast_u64 core_resolution_tick,
                               fast_u64 device_resolution,
                               fast_u64 device_resolution_tick_remainder,
                               fast_u16 addr_mask,
                               fast_u16 addr_value,
                               fast_u64 num_ticks,
                               const Py_buffer &entries) {
        if(num_port_read_series == max_num_port_read_series)
            return false;

        port_read_series &series =
            port_read_series_list[num_port_read_series++];
        series.core_resolution_tick = core_resolution_tick;
        series.device_resolution = device_resolution;
        series.device_resolution_tick_remainder =
            device_resolution_tick_remainder;
        series.addr_mask = static_cast<least_u16>(addr_mask);
        series.addr_value = static_cast<least_u16>(addr_value);
        series.num_ticks = num_ticks;
        series.entries = entries;
        series.current_entry = 0;
        return true;
    }

protected:
    Core::processor_state get_processor_state() {
        Core::processor_state state;

        state.bc = get_bc();
        state.de = get_de();
        state.hl = get_hl();
        state.af = get_af();
        state.ix = get_ix();
        state.iy = get_iy();

        state.alt_bc = get_alt_bc();
        state.alt_de = get_alt_de();
        state.alt_hl = get_alt_hl();
        state.alt_af = get_alt_af();

        state.pc = get_pc();
        state.sp = get_sp();
        state.ir = get_ir();
        state.wz = get_wz();

        state.iff1 = get_iff1() ? 1 : 0;
        state.iff2 = get_iff2() ? 1 : 0;
        state.int_mode = get_int_mode();
        state.index_rp_kind = static_cast<least_u8>(get_iregp_kind());

        return state;
    }

    void set_processor_state(const Core::processor_state &state) {
        set_bc(state.bc);
        set_de(state.de);
        set_hl(state.hl);
        set_af(state.af);
        set_ix(state.ix);
        set_iy(state.iy);

        set_alt_bc(state.alt_bc);
        set_alt_de(state.alt_de);
        set_alt_hl(state.alt_hl);
        set_alt_af(state.alt_af);

        set_pc(state.pc);
        set_sp(state.sp);
        set_ir(state.ir);
        set_wz(state.wz);

        set_iff1(state.iff1);
        set_iff2(state.iff2);
        set_int_mode(state.int_mode);
        set_iregp_kind(static_cast<z80::iregp>(state.index_rp_kind));
    }

public:
    zx::spectrum_model on_get_model() const {
        return static_cast<zx::spectrum_model>(state.model);
    }

    ticks_type on_get_ticks_per_horizontal_retrace() const {
        return state.config.ticks_per_horizontal_retrace;
    }

    ticks_type on_get_lines_per_vertical_retrace() const {
        return state.config.lines_per_vertical_retrace;
    }

    ticks_type on_get_contention_base() const {
        return state.config.contention_base;
    }

    zx::memory_image &on_get_memory() {
        return state.memory;
    }

private:
    // Answers a read of the given port from the samples supplied
    // for this quantum. The samples either cover the read's moment
    // or they do not. Covered means every series whose pattern
    // matches the address has a sample for the moment; the value
    // is then the AND of those samples -- input lines pulled high
    // unless a sample drives them low, so 0xff where no series
    // drives them, no series matching at all included. Not covered
    // -- a matching series with no sample for the moment, an empty
    // one included -- means the read cannot be resolved from the
    // samples, and this returns false.
    bool sample_port_read(fast_u16 addr, fast_u8 &value) {
        value = 0xff;
        for(unsigned i = 0; i != num_port_read_series; ++i) {
            port_read_series &series = port_read_series_list[i];
            if((addr & series.addr_mask) != series.addr_value)
                continue;

            // The read's moment in the common resolution, measured
            // from tick 0 like the remainder and the entry ticks.
            fast_u64 delta = tick_count - series.core_resolution_tick;
            fast_u64 read_time =
                series.device_resolution_tick_remainder +
                    delta * series.device_resolution;
            fast_u64 core_resolution = state.config.ticks_per_second;

            // An empty series has num_ticks 0 and so covers no
            // moment at all.
            if(read_time >= series.num_ticks * core_resolution)
                return false;

            // The value driven at the read is the last entry's
            // whose tick is at or before it. Reads never go back
            // in time within a run, so resume from the entry
            // currently in effect.
            const auto *entries = static_cast<const least_u64*>(
                series.entries.buf);
            auto num_entries = static_cast<unsigned>(
                series.entries.len /
                    static_cast<Py_ssize_t>(sizeof(least_u64)));
            while(series.current_entry + 1 != num_entries) {
                fast_u64 next_entry_time =
                    (entries[series.current_entry + 1] >> 8) *
                        core_resolution;
                if(next_entry_time > read_time)
                    break;

                ++series.current_entry;
            }

            value &= static_cast<fast_u8>(
                entries[series.current_entry] & 0xff);
        }
        return true;
    }

public:
    fast_u8 on_input(fast_u16 addr) {
        // Answer from the samples supplied for this quantum, if any
        // cover this read; with no covering sample the read falls
        // through to the callback below.
        fast_u8 sampled;
        if(sample_port_read(addr, sampled))
            return sampled;

        const fast_u8 default_value = 0xbf;
        if(!on_input_callback)
            return default_value;

        // on_input only fires during a run(), which always sets the
        // dispatcher.
        assert(run_dispatcher);
        PyObject *arg = Py_BuildValue("(iO)", addr, run_dispatcher);
        decref_guard arg_guard(arg);

        retrieve_state();
        PyObject *result = PyObject_CallObject(on_input_callback, arg);
        decref_guard result_guard(result);
        install_state();

        // On errors, abort the input instruction just like on a
        // deferred read, so nothing is committed on a value that
        // never existed; the pending exception then propagates on
        // the end of the run.
        if(!result)
            return z80::retry_input;

        // None means the value is not known yet, aborting the input
        // instruction to be retried later.
        if(result == Py_None)
            return z80::retry_input;

        if(!PyLong_Check(result)) {
            PyErr_SetString(PyExc_TypeError, "returning value must be integer");
            return z80::retry_input;
        }

        return z80::mask8(PyLong_AsUnsignedLong(result));
    }

    void on_output(fast_u16 addr, fast_u8 value) {
        if(!on_output_callback)
            return;

        PyObject *args = Py_BuildValue("(i,i)", addr, value);
        decref_guard arg_guard(args);

        retrieve_state();
        PyObject *result = PyObject_CallObject(on_output_callback, args);
        decref_guard result_guard(result);
        install_state();

        // On errors, stop the run so the pending exception can
        // propagate on its end. Unlike an input, the write cannot be
        // aborted: it is already committed to the devices.
        if(!result)
            events |= events_mask::stop_requested;
    }

private:
    machine_state state;
    pixels_buffer_type pixels;
    PyObject *on_input_callback = nullptr;
    PyObject *on_output_callback = nullptr;

    static const unsigned max_num_port_read_series = 64;
    unsigned num_port_read_series = 0;
    port_read_series port_read_series_list[max_num_port_read_series];

    // The dispatcher of the current run, set only while run() is on the
    // stack, passed to the Python callbacks invoked from the core.
    PyObject *run_dispatcher = nullptr;
};

struct object_instance {
    PyObject_HEAD
    machine_emulator emulator;
};

static inline object_instance *cast_object(PyObject *p) {
    return reinterpret_cast<object_instance*>(p);
}

static inline machine_emulator &cast_emulator(PyObject *p) {
    return cast_object(p)->emulator;
}

PyObject *get_state_view(PyObject *self, PyObject *args) {
    auto &state = cast_emulator(self).get_machine_state();
    return PyMemoryView_FromMemory(reinterpret_cast<char*>(&state),
                                   sizeof(state), PyBUF_WRITE);
}

PyObject *render_screen(PyObject *self, PyObject *args) {
    auto &emulator = cast_emulator(self);
    emulator.render_screen();

    const auto &screen_chunks = emulator.get_screen_chunks();
    return PyMemoryView_FromMemory(
        const_cast<char*>(reinterpret_cast<const char*>(&screen_chunks)),
        sizeof(screen_chunks), PyBUF_READ);
}

static PyObject *get_frame_pixels(PyObject *self, PyObject *args) {
    auto &pixels = cast_emulator(self).get_frame_pixels();
    return PyMemoryView_FromMemory(reinterpret_cast<char*>(pixels),
                                   sizeof(pixels), PyBUF_READ);
}

static PyObject *drain_port_writes(PyObject *self, PyObject *args) {
    auto &emulator = cast_emulator(self);
    auto &writes = emulator.get_port_writes();
    PyObject *result = PyBytes_FromStringAndSize(
        reinterpret_cast<const char*>(writes),
        sizeof(*writes) * emulator.get_num_port_writes());
    emulator.clear_port_writes();
    return result;
}

static PyObject *clear_port_read_samples(PyObject *self, PyObject *args) {
    cast_emulator(self).clear_port_read_samples();
    Py_RETURN_NONE;
}

static PyObject *add_port_read_samples(PyObject *self, PyObject *args) {
    unsigned long long core_resolution_tick;
    unsigned long long device_resolution;
    unsigned long long device_resolution_tick_remainder;
    unsigned addr_mask, addr_value;
    unsigned long long num_ticks;
    Py_buffer entries;
    if(!PyArg_ParseTuple(args, "KKKIIKy*", &core_resolution_tick,
                         &device_resolution,
                         &device_resolution_tick_remainder,
                         &addr_mask, &addr_value, &num_ticks, &entries))
        return nullptr;

    if(device_resolution == 0 || device_resolution >> 32 != 0) {
        PyBuffer_Release(&entries);
        PyErr_SetString(PyExc_ValueError,
                        "the resolution must be positive and fit "
                        "32 bits");
        return nullptr;
    }

    if(addr_mask > 0xffff || addr_value > 0xffff) {
        PyBuffer_Release(&entries);
        PyErr_SetString(PyExc_ValueError,
                        "the address pattern must be 16-bit");
        return nullptr;
    }

    if(entries.len % static_cast<Py_ssize_t>(sizeof(least_u64)) != 0) {
        PyBuffer_Release(&entries);
        PyErr_SetString(PyExc_ValueError,
                        "entries must be 64-bit words");
        return nullptr;
    }

    if(entries.len != 0 &&
            static_cast<const least_u64*>(entries.buf)[0] >> 8 != 0) {
        PyBuffer_Release(&entries);
        PyErr_SetString(PyExc_ValueError,
                        "the first entry must be at tick 0");
        return nullptr;
    }

    // An empty series must not claim to cover any ticks: it has no
    // values to state for them.
    if(entries.len == 0 && num_ticks != 0) {
        PyBuffer_Release(&entries);
        PyErr_SetString(PyExc_ValueError,
                        "an empty series must have zero num_ticks");
        return nullptr;
    }

    if(!cast_emulator(self).add_port_read_samples(
            core_resolution_tick, device_resolution,
            device_resolution_tick_remainder,
            addr_mask, addr_value, num_ticks, entries)) {
        PyBuffer_Release(&entries);
        PyErr_SetString(PyExc_ValueError, "too many port-read series");
        return nullptr;
    }

    Py_RETURN_NONE;
}

static PyObject *mark_addrs(PyObject *self, PyObject *args) {
    unsigned addr, size, marks;
    if(!PyArg_ParseTuple(args, "III", &addr, &size, &marks))
        return nullptr;

    cast_emulator(self).mark_addrs(addr, size, marks);
    Py_RETURN_NONE;
}

static PyObject *set_on_input_callback(PyObject *self, PyObject *args) {
    PyObject *new_callback;
    if(!PyArg_ParseTuple(args, "O:set_callback", &new_callback))
        return nullptr;

    if(!PyCallable_Check(new_callback)) {
        PyErr_SetString(PyExc_TypeError, "parameter must be callable");
        return nullptr;
    }

    auto &emulator = cast_emulator(self);
    PyObject *old_callback = emulator.set_on_input_callback(new_callback);
    Py_XINCREF(new_callback);
    Py_XDECREF(old_callback);
    Py_RETURN_NONE;
}

static PyObject *set_on_output_callback(PyObject *self, PyObject *args) {
    PyObject *new_callback;
    if(!PyArg_ParseTuple(args, "O:set_callback", &new_callback))
        return nullptr;

    if(!PyCallable_Check(new_callback)) {
        PyErr_SetString(PyExc_TypeError, "parameter must be callable");
        return nullptr;
    }

    auto &emulator = cast_emulator(self);
    PyObject *old_callback = emulator.set_on_output_callback(new_callback);
    Py_XINCREF(new_callback);
    Py_XDECREF(old_callback);
    Py_RETURN_NONE;
}

PyObject *run(PyObject *self, PyObject *args) {
    auto &emulator = cast_emulator(self);
    PyObject *dispatcher;
    if(!PyArg_ParseTuple(args, "O", &dispatcher))
        return nullptr;
    machine_emulator::events_mask::type events = emulator.run(dispatcher);
    if(PyErr_Occurred())
        return nullptr;
    return Py_BuildValue("i", events);
}

PyObject *step_over_breakpoint(PyObject *self, PyObject *args) {
    auto &emulator = cast_emulator(self);
    PyObject *dispatcher;
    if(!PyArg_ParseTuple(args, "O", &dispatcher))
        return nullptr;
    machine_emulator::events_mask::type events =
        emulator.step_over_breakpoint(dispatcher);
    if(PyErr_Occurred())
        return nullptr;
    return Py_BuildValue("i", events);
}

PyObject *on_handle_active_int(PyObject *self, PyObject *args) {
    bool int_initiated = cast_emulator(self).on_handle_active_int();
    return PyBool_FromLong(int_initiated);
}

PyObject *on_reset(PyObject *self, PyObject *args) {
    auto &emulator = cast_emulator(self);
    emulator.install_state();
    emulator.on_reset();
    emulator.retrieve_state();
    Py_RETURN_NONE;
}

PyObject *reset_config(PyObject *self, PyObject *args) {
    auto &emulator = cast_emulator(self);

    // The configuration and the memory image are parts of the state
    // shared with the Python side directly, so no state marshalling
    // is needed. The ROM pages are configuration too: their content
    // is snapshot data, not reset's responsibility.
    emulator.get_machine_state().config = core_config();
    emulator.on_get_memory().reset_roms();
    Py_RETURN_NONE;
}

PyMethodDef methods[] = {
    {"_get_state_view", get_state_view, METH_NOARGS,
     "Return a MemoryView object that exposes the internal state of the "
     "emulated machine."},
    {"render_screen", render_screen, METH_NOARGS,
     "Render current screen frame and return a MemoryView object that exposes "
     "a buffer that contains rendered data."},
    {"get_frame_pixels", get_frame_pixels, METH_NOARGS,
     "Convert rendered frame into an internally allocated array of RGB24 pixels "
     "and return a MemoryView object that exposes that array."},
    {"drain_port_writes", drain_port_writes, METH_NOARGS,
     "Return the accumulated port writes as a bytes object and clear "
     "the buffer."},
    {"_clear_port_read_samples", clear_port_read_samples, METH_NOARGS,
     "Discard all supplied port-read sample series."},
    {"_add_port_read_samples", add_port_read_samples, METH_VARARGS,
     "Add a series of port-read samples supplied for the current "
     "quantum."},
    {"mark_addrs", mark_addrs, METH_VARARGS,
     "Mark a range of memory bytes as ones that require custom "
     "processing on reading, writing or executing them."},
    {"set_on_input_callback", set_on_input_callback, METH_VARARGS,
     "Set a callback function handling reading from ports."},
    {"set_on_output_callback", set_on_output_callback, METH_VARARGS,
     "Set a callback function handling writing to ports."},
    {"_run", run, METH_VARARGS,
     "Run emulator until one or several events are signalled."},
    {"_step_over_breakpoint", step_over_breakpoint, METH_VARARGS,
     "Execute the instruction a breakpoint trapped at."},
    {"on_handle_active_int", on_handle_active_int, METH_NOARGS,
     "Attempts to initiate a masked interrupt."},
    {"_reset", on_reset, METH_NOARGS,
     "Perform a hard reset of the emulated machine."},
    {"_reset_config", reset_config, METH_NOARGS,
     "Return the core configuration, the ROM pages included, to "
     "the canonical reset defaults."},
    { nullptr }  // Sentinel.
};

PyObject *object_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    if(!PyArg_ParseTuple(args, ":_CoreBase.__new__"))
        return nullptr;

    auto *self = cast_object(type->tp_alloc(type, /* nitems= */ 0));
    if(!self)
      return nullptr;

    auto &emulator = self->emulator;
    ::new(&emulator) machine_emulator();
    return &self->ob_base;
}

void object_dealloc(PyObject *self) {
    auto &object = *cast_object(self);
    object.emulator.~machine_emulator();
    Py_TYPE(self)->tp_free(self);
}

static PyTypeObject type_object = {
    PyVarObject_HEAD_INIT(&PyType_Type, 0)
    "zx._corebase._CoreBase",
                                // tp_name
    sizeof(object_instance),    // tp_basicsize
    0,                          // tp_itemsize
    object_dealloc,             // tp_dealloc
    0,                          // tp_print
    0,                          // tp_getattr
    0,                          // tp_setattr
    0,                          // tp_reserved
    0,                          // tp_repr
    0,                          // tp_as_number
    0,                          // tp_as_sequence
    0,                          // tp_as_mapping
    0,                          // tp_hash
    0,                          // tp_call
    0,                          // tp_str
    0,                          // tp_getattro
    0,                          // tp_setattro
    0,                          // tp_as_buffer
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
                                // tp_flags
    "ZX Spectrum Emulator",     // tp_doc
    0,                          // tp_traverse
    0,                          // tp_clear
    0,                          // tp_richcompare
    0,                          // tp_weaklistoffset
    0,                          // tp_iter
    0,                          // tp_iternext
    methods,                    // tp_methods
    nullptr,                    // tp_members
    0,                          // tp_getset
    0,                          // tp_base
    0,                          // tp_dict
    0,                          // tp_descr_get
    0,                          // tp_descr_set
    0,                          // tp_dictoffset
    0,                          // tp_init
    0,                          // tp_alloc
    object_new,                 // tp_new
    0,                          // tp_free
    0,                          // tp_is_gc
    0,                          // tp_bases
    0,                          // tp_mro
    0,                          // tp_cache
    0,                          // tp_subclasses
    0,                          // tp_weaklist
    0,                          // tp_del
    0,                          // tp_version_tag
    0,                          // tp_finalize
};

}  // namespace Core

static PyModuleDef module = {
    PyModuleDef_HEAD_INIT,      // m_base
    "zx._corebase",             // m_name
    "ZX Spectrum Emulation Module",
                                // m_doc
    -1,                         // m_size
    nullptr,                    // m_methods
    nullptr,                    // m_slots
    nullptr,                    // m_traverse
    nullptr,                    // m_clear
    nullptr,                    // m_free
};

}  // anonymous namespace

extern "C" PyMODINIT_FUNC PyInit__corebase(void) {
    PyObject *m = PyModule_Create(&module);
    if(!m)
        return nullptr;

    if(PyType_Ready(&Core::type_object) < 0)
        return nullptr;
    Py_INCREF(&Core::type_object);

    // TODO: Check the returning value.
    PyModule_AddObject(m, "_CoreBase",
                       &Core::type_object.ob_base.ob_base);
    return m;
}

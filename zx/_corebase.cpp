
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
using zx::events_mask;

typedef uint_least32_t least_u32;

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

    zx::memory_image memory;
};
#if defined(_MSC_VER)
#pragma pack(pop)
#endif

class machine_emulator : public zx::spectrum<machine_emulator> {
public:
    typedef zx::spectrum<machine_emulator> base;

    machine_emulator() {
        retrieve_state();
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

    zx::memory_image &on_get_memory() {
        return state.memory;
    }

    fast_u8 on_input(fast_u16 addr) {
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
    events_mask::type events = emulator.run(dispatcher);
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
    emulator.on_reset();
    emulator.retrieve_state();
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
    {"mark_addrs", mark_addrs, METH_VARARGS,
     "Mark a range of memory bytes as ones that require custom "
     "processing on reading, writing or executing them."},
    {"set_on_input_callback", set_on_input_callback, METH_VARARGS,
     "Set a callback function handling reading from ports."},
    {"set_on_output_callback", set_on_output_callback, METH_VARARGS,
     "Set a callback function handling writing to ports."},
    {"_run", run, METH_VARARGS,
     "Run emulator until one or several events are signalled."},
    {"on_handle_active_int", on_handle_active_int, METH_NOARGS,
     "Attempts to initiate a masked interrupt."},
    {"on_reset", on_reset, METH_NOARGS,
     "Perform a hard reset of the emulated machine."},
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

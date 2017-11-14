
/*  PyZX - Python bindings for the ZX Spectrum Emulator.

    Copyright (C) 2017 Ivan Kosarev.
    ivan@kosarev.info

    Published under the MIT license.
*/

#include <Python.h>

#include <new>

#include "zx.h"

struct Spectrum48_object {
    PyObject_HEAD
    zx::spectrum48 emulator;
};

static PyObject *Spectrum48_new(PyTypeObject *type, PyObject *args,
                                PyObject *kwds) {
    auto *self = reinterpret_cast<Spectrum48_object*>(
        type->tp_alloc(type, /* nitems= */ 0));
    if(!self)
      return nullptr;

    ::new(&self->emulator) zx::spectrum48();
    return &self->ob_base;
}

static PyTypeObject Spectrum48_type = {
    PyVarObject_HEAD_INIT(&PyType_Type, 0)
    "zx.Spectrum48",            // tp_name
    sizeof(Spectrum48_object),  // tp_basicsize
    0,                          // tp_itemsize
    0,                          // tp_dealloc
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
    Py_TPFLAGS_DEFAULT |        // tp_flags
         Py_TPFLAGS_BASETYPE,
    "ZX Spectrum 48K Emulator", // tp_doc
    0,                          // tp_traverse
    0,                          // tp_clear
    0,                          // tp_richcompare
    0,                          // tp_weaklistoffset
    0,                          // tp_iter
    0,                          // tp_iternext
    0,                          // tp_methods
    nullptr,                    // tp_members
    0,                          // tp_getset
    0,                          // tp_base
    0,                          // tp_dict
    0,                          // tp_descr_get
    0,                          // tp_descr_set
    0,                          // tp_dictoffset
    0,                          // tp_init
    0,                          // tp_alloc
    Spectrum48_new,             // tp_new
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

static PyModuleDef zx_module = {
    PyModuleDef_HEAD_INIT,      // m_base
    "zx",                       // m_name
    "ZX Spectrum Emulator",     // m_doc
    -1,                         // m_size
    nullptr,                    // m_methods
    nullptr,                    // m_slots
    nullptr,                    // m_traverse
    nullptr,                    // m_clear
    nullptr,                    // m_free
};

extern "C" PyMODINIT_FUNC PyInit_zx(void) {
    if(PyType_Ready(&Spectrum48_type) < 0)
        return nullptr;

    PyObject *m = PyModule_Create(&zx_module);
    if(!m)
        return nullptr;

    Py_INCREF(&Spectrum48_type);
    PyModule_AddObject(m, "Spectrum48", &Spectrum48_type.ob_base.ob_base);
    return m;
}

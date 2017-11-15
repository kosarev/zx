#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import distutils.sysconfig, os
# from distutils.core import Extension
from setuptools import Extension, setup


ZX_MAJOR_VERSION = 0
ZX_MINOR_VERSION = 1
ZX_PATCH_VERSION = 2


# Work around the problem with the warning about '-Wstrict-prototypes'.
# https://bugs.python.org/issue1222585
config_vars = distutils.sysconfig.get_config_vars()
opt_to_remove = '-Wstrict-prototypes'
for var in ['OPT']:
    if var in config_vars:
        opts = config_vars[var].split()
        if opt_to_remove in opts:
            opts.remove(opt_to_remove)
    config_vars[var] = ' '.join(opts)


zx_emulator_module = Extension(
    name='zx.emulator',
    define_macros=[('ZX_MAJOR_VERSION', '%d' % ZX_MAJOR_VERSION),
                   ('ZX_MINOR_VERSION', '%d' % ZX_MINOR_VERSION),
                   ('ZX_PATCH_VERSION', '%d' % ZX_PATCH_VERSION)],
    extra_compile_args=['-std=c++11', '-Wall', '-fno-exceptions', '-fno-rtti'],
    sources=['zx/zx-emulator-module.cpp'],
    language='c++')


# TODO: Update the URL once we have a published documentation.
# TODO: Do we have a name for the emulator?
setup(name='zx',
      version='%d.%d.%d' % (ZX_MAJOR_VERSION, ZX_MINOR_VERSION,
                            ZX_PATCH_VERSION),
      description='ZX Spectrum Emulator',
      # TODO: long_description=...
      author='Ivan Kosarev',
      author_email='ivan@kosarev.info',
      url='https://github.com/kosarev/zx/',
      ext_modules=[zx_emulator_module],
      packages=['zx'],
      classifiers=[
          'Development Status :: 1 - Planning',
          'Environment :: X11 Applications :: GTK',
          'Intended Audience :: Developers',
          'Intended Audience :: Education',
          'Intended Audience :: End Users/Desktop',
          'License :: OSI Approved :: MIT License',
          'Operating System :: OS Independent',
          'Programming Language :: C++',
          # TODO: Are we going to support Python 2?
          # TODO: Specific versions?
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: Implementation :: CPython',
          'Topic :: Games/Entertainment',
          'Topic :: Software Development',
          'Topic :: Software Development :: Libraries',
          'Topic :: System :: Emulators',
      ],
      # TODO: license=...
      # TODO: Respect other parameters.
      )

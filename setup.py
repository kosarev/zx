#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import inspect
import os
from setuptools import Extension, setup


here = os.path.abspath(os.path.dirname(inspect.getsource(lambda: 0)))

with open(os.path.join(here, 'zx/__init__.py')) as f:
    s, = [s for s in f.readlines() if '__version__' in s]
    s, eq, v = s.split()
    assert s == '__version__' and eq == '='
    assert v[0] == '\'' and v[-1] == '\''
    v = v[1:-1].split('.')
    ZX_MAJOR_VERSION = int(v[0])
    ZX_MINOR_VERSION = int(v[1])
    ZX_PATCH_VERSION = int(v[2])
    version = f'{ZX_MAJOR_VERSION}.{ZX_MINOR_VERSION}.{ZX_PATCH_VERSION}'

with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()


zx_emulatorbase_module = Extension(
    name='zx._emulatorbase',
    extra_compile_args=['-std=c++11', '-Wall', '-fno-exceptions', '-fno-rtti',
                        '-O3',
                        '-UNDEBUG',  # TODO
                        ],
    sources=['zx/_emulatorbase.cpp'],
    language='c++')


# TODO: Update the URL once we have a published documentation.
# TODO: Do we have a name for the emulator?
setup(name='zx',
      version=version,
      description='ZX Spectrum Emulator in Python and C++',
      long_description=long_description,
      long_description_content_type='text/markdown',
      author='Ivan Kosarev',
      author_email='mail@ivankosarev.com',
      url='https://github.com/kosarev/zx/',
      ext_modules=[zx_emulatorbase_module],
      packages=['zx'],
      install_requires=[
          'pycairo',
          'pygobject==3.50.0',
          'numpy',
          'sounddevice',
          'evdev; platform_system=="Linux"',
      ],
      extras_require={
          ':"linux" in sys_platform': [
              'evdev',
          ],
      },
      package_data={'zx': ['roms/*', 'py.typed']},
      entry_points={
          'console_scripts': [
              'zx = zx:main',
          ],
      },
      classifiers=[
          'Development Status :: 2 - Pre-Alpha',
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
      license='MIT',
      # TODO: Respect other parameters.
      )

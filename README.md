# zx
ZX Spectrum emulation framework in Python and C++

[![CI](https://github.com/kosarev/zx/actions/workflows/python-package.yml/badge.svg)](https://github.com/kosarev/zx/actions/workflows/python-package.yml)
[![PyPI](https://img.shields.io/pypi/v/zx)](https://pypi.org/project/zx/)
[![Python](https://img.shields.io/pypi/pyversions/zx?v=2)](https://pypi.org/project/zx/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/kosarev/zx/blob/master/LICENSE)

![Elven](https://raw.githubusercontent.com/kosarev/zx/master/screenshots/elven.png "Elven Warrior")

[More screenshots](https://github.com/kosarev/zx/tree/master/screenshots)


### Features
* Designed to be suitable for research and development purposes
  such as unattended testing of Spectrum software, timing
  analysis, etc.
* Meant to be easy to customize and re-use via Python interfaces.
* Fast and accurate emulation.
* Supported formats: snapshots (`.z80`, `.sna`), tapes (`.tap`, `.tzx`, `.wav`),
  playbacks (`.rzx`), screenshots (`.scr`),
  [ZX Basic](https://github.com/boriel/zxbasic) sources (`.zxb`),
  archives (`.zip`).
* Based on the fast and flexible
  [Z80 emulator](https://github.com/kosarev/z80).


### Development status

* Platforms: Linux and Windows (via SDL2).
* General status: working pre-alpha.
* Supported machines: 48K only for now.
* Display: multi-colour effects,
  [accurate timings](https://github.com/kosarev/zx/blob/master/test/screen_timing).
* Sound: EAR beeper and tape output supported.
* Tape: TAP and TZX formats supported as well as conversion to WAV.
* Snapshots: Z80.
* Playback recordings: RZX.
* Joystick: D-Pad mapped to cursor keys, supported via SDL.


### Installation and running

Install from PyPI (pre-built wheels for Linux and Windows, source for other platforms):
```shell
$ pip install zx
```

Standalone executables for Linux x86\_64 and Windows x64 are available on the
[Releases page](https://github.com/kosarev/zx/releases).

For the current development version:
```shell
$ pip install git+https://github.com/kosarev/zx
```

Local development setup:
```shell
$ git clone --recursive https://github.com/kosarev/zx
$ cd zx
$ pip install --editable .
```

Running:
```shell
$ zx
```

Press `ESC` or `F1` to open the main menu.


### Running snapshots, recordings and tapes

```shell
$ zx elven.z80
```

```shell
$ zx exolon.rzx
```

```shell
$ zx https://www.worldofspectrum.org/pub/sinclair/games/e/EricTheFloaters.tzx.zip
```


### Reference papers

* [Screen timings](https://github.com/kosarev/zx/blob/master/test/screen_timing/SCREEN_TIMING.md)

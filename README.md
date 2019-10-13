[![Build Status](https://travis-ci.org/kosarev/zx.svg?branch=master)](https://travis-ci.org/kosarev/zx)

# zx
ZX Spectrum Emulator written in a mix of Python and C++.


### Features
* Fast and accurate emulation.
* Designed to be suitable for research and development purposes
  such as unattended testing of Spectrum software, timing
  analysis, etc.
* Meant to be easy to customize and re-use via Python interfaces.
* Based on the fast and flexible
  [Z80 emulator](https://github.com/kosarev/z80).


### Installation and running

```shell
pip install zx
```

```shell
zx
```


### Control keys

`F1` Show help.

`F4` Load tape file.

`F6` Pause/unpause tape.

`F10` Quit.


### Running snapshots, recordings and tapes

```shell
zx elven.z80
```

```shell
zx exolon.rzx
```

```shell
zx eric.tap
```


### Converting tape files to the WAV format

```shell
zx jack.tzx jack.wav
```

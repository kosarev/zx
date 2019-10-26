[![Build Status](https://travis-ci.org/kosarev/zx.svg?branch=master)](https://travis-ci.org/kosarev/zx)

# zx
ZX Spectrum Emulator written in a mix of Python and C++.

![Elven](https://raw.githubusercontent.com/kosarev/zx/master/screenshots/elven.png "Elven Warrior")

[More screenshots](https://github.com/kosarev/zx/tree/master/screenshots)


### Features
* Designed to be suitable for research and development purposes
  such as unattended testing of Spectrum software, timing
  analysis, etc.
* Meant to be easy to customize and re-use via Python interfaces.
* Fast and accurate emulation.
* Based on the fast and flexible
  [Z80 emulator](https://github.com/kosarev/z80).


### Development status

* General status: working pre-alpha.
* Supported machines: 48K only for now.
* Display: multi-colour effects,
  [accurate timings](https://github.com/kosarev/zx/blob/master/test/screen_timing/SCREEN_TIMING.md).
* Sound: not supported yet.
* Tape: TAP and TZX formats supported as well as conversion to WAV.
* Snapshots: Z80.
* Playback recordings: RZX.


### Installation and running

```shell
$ pip install zx
```

```shell
$ zx
```


### Controls

`F1` displays help.

`F2` is to save snapshot.

`F3` is to load snapshot or tape file.

`F6` pauses/unpauses tape.

`F10` and `ESC` quit the emulator.

`PAUSE` and mouse click pause/unpause emulation or RZX playback.

Any Spectrum key stroke unpauses emulation and leaves the RZX
playback mode back to the regular emulation mode.


### Running snapshots, recordings and tapes

```shell
$ zx elven.z80
```

```shell
$ zx exolon.rzx
```

```shell
$ zx eric.tap
```


### Converting tape files to the WAV format

```shell
$ zx jack.tzx jack.wav
```


### Dumping files

```shell
$ zx dump rick.z80
OrderedDict([('id', 'z80_snapshot'), ('a', 213), ('f', 66), ...
```

On the `dump` command, **zx** parses the specified file (that can
be of any supported format) in the form of raw Python data.


### Reference papers

* [Screen timings](https://github.com/kosarev/zx/blob/master/test/screen_timing/SCREEN_TIMING.md)

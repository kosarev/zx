[![Build Status](https://travis-ci.org/kosarev/zx.svg?branch=master)](https://travis-ci.org/kosarev/zx)

# zx
ZX Spectrum Emulator written in a mix of Python and C++.

[[Screenshots](screenshots/README.md)]


### Features
* Designed to be suitable for research and development purposes
  such as unattended testing of Spectrum software, timing
  analysis, etc.
* Meant to be easy to customize and re-use via Python interfaces.
* Fast and accurate emulation.
* Based on the fast and flexible
  [Z80 emulator](https://github.com/kosarev/z80).


### Development status

* Supported machines: 48K only for now.
* Display: multi-colour effects, accurate timings.
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


### Control keys

`F1` Show help.

`F2` Save snapshot.

`F3` Load tape file.

`F6` Pause/unpause tape.

`F10` Quit.

`PAUSE` Pause/unpause emulation.


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

* [Screen timings](test/screen_timing/SCREEN_TIMING.md)

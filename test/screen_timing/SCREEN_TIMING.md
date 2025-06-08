
## The base tick

The first two pixels of the screen area are displayed at CPU tick
64 * 224 + 4 = 14340.

The 64 is the number of scanlines before the screen area begins (the top
border) and 224 is the number of CPU ticks per scanline.

All ticks are since ~INT becomes active, with the first tick since
active ~INT being 0.


## Border timing

The border colour value is latched and the first two pixels of
the corresponding 8-pixel border chunk are displayed at every
tick that is a multiple of 4.

Note that Z80 writes ports at T2 of the output cycle.
This means to take effect the output cycle shall be started at
least one tick ahead of the moment when the new border colour
value is supposed to be latched.


## Pixel pattern and colour attribute timing

The first two bytes of the screen area at addresses 0x4000 and
0x4001 and the first two bytes of the colour attribute area at
addresses 0x5800 and 0x5801 are latched during the first memory
contention cycle at ticks 14336-14341.

Similarly to output cycles, memory write cycles actually write
the value at T2, so such cycles too have to come at least one
tick ahead of the latching moment.

The four bytes read are then displayed during ticks 14340-14347
as a chunk of 16 pixels.

Then at tick 14348 subsequent four bytes are read and another
chunk of 16 pixels is displayed on the screen.


## Display, memory contention and ULA reads (floating bus) cycles

| Tick   | Contention       | ULA read | Screen area pixels                |
| ------ | ---------------- | -------- | --------------------------------- |
| 14,336 | 6 (until 13,342) | -        | -                                 |
| 14,337 | 5 (until 13,342) | -        | -                                 |
| 14,338 | 4 (until 13,342) | 0x4000   | -                                 |
| 14,339 | 3 (until 13,342) | 0x5800   | -                                 |
| 14,340 | 2 (until 13,342) | 0x4001   | 0b11000000 from 0x4000 and 0x5800 |
| 14,341 | 1 (until 13,342) | 0x5801   | 0b00110000 from 0x4000 and 0x5800 |
| 14,342 | -                | -        | 0b00001100 from 0x4000 and 0x5800 |
| 14,343 | -                | -        | 0b00000011 from 0x4000 and 0x5800 |
| 14,344 | 6 (until 14,350) | -        | 0b11000000 from 0x4001 and 0x5801 |
| 14,345 | 5 (until 14,350) | -        | 0b00110000 from 0x4001 and 0x5801 |
| 14,346 | 4 (until 14,350) | 0x4002   | 0b00001100 from 0x4001 and 0x5801 |
| 14,347 | 3 (until 14,350) | 0x5802   | 0b00000011 from 0x4001 and 0x5801 |
| 14,348 | 2 (until 14,350) | 0x4003   | 0b11000000 from 0x4002 and 0x5802 |
| 14,349 | 1 (until 14,350) | 0x5803   | 0b00110000 from 0x4002 and 0x5802 |
| 14,350 | -                | -        | 0b00001100 from 0x4002 and 0x5802 |
| 14,351 | -                | -        | 0b00000011 from 0x4002 and 0x5802 |


## Tests

* [TAP file](https://github.com/kosarev/zx/blob/master/test/screen_timing/screen_timing_early.tap), for early timing machines
* [TAP file](https://github.com/kosarev/zx/blob/master/test/screen_timing/screen_timing_late.tap), for late timing machines
* The [script](https://github.com/kosarev/zx/blob/master/test/screen_timing/generate_drawing.py) used to generate the test source code.

## Expected output

![Expected output](https://raw.githubusercontent.com/kosarev/zx/master/test/screen_timing/screenshot.png "Expected ouput")


## References

* The relevant discussion on the WoS site:
  https://www.worldofspectrum.org/forums/discussion/comment/957356/#Comment_957356

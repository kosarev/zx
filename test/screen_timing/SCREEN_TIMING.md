
## The base tick

The first two pixels of the screen area are displayed at CPU tick
64 * 224 + 4 = 14340.


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

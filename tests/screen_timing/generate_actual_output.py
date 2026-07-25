#!/usr/bin/env python3

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

# Runs the screen-timing test tape on a bare machine and saves the
# area of interest -- the top-left corner with the border stripes
# and the diagonal, cropped and magnified to the geometry of
# expected_output.png -- as actual_output.png, together with a
# side-by-side comparison against the expected output as
# comparison.png.

import contextlib
import pathlib
import sys

import numpy
import PIL.Image

import zx
from zx._basic import StopAtTapeEnd
from zx._basic import boot_to_prompt
from zx._core import Core
from zx._device import GetEmulationTime
from zx._device import LoadTape
from zx._device import PauseUnpauseTape
from zx._except import EmulationExit
from zx._file import parse_file
from zx._time import Time

# The 48K frame, in ticks.
_TICKS_PER_FRAME = 69888


def main() -> None:
    tape_filename = (sys.argv[1] if len(sys.argv) > 1
                     else 'screen_timing_early.tap')

    with zx.Emulator(headless=True,
                     extra_environment=[StopAtTapeEnd()]) as app:
        core = app.machine.devices['core']
        assert isinstance(core, Core)

        boot_to_prompt(app)

        # LOAD ""
        app.generate_key_strokes('J', 'SS+P', 'SS+P', 'ENTER')

        app.notify(LoadTape(parse_file(tape_filename)))
        app.notify(PauseUnpauseTape(False))

        with contextlib.suppress(EmulationExit):
            app.run()

        # The loaded program waits for a key before starting the
        # drawing loop.
        app.generate_key_strokes('ENTER')

        # Let the drawing loop calibrate against ~INT and settle.
        # The drawn pattern repeats identically every frame by
        # then, so where within a frame the capture lands does not
        # matter.
        time = GetEmulationTime()
        app.notify(time)
        assert time.floor is not None
        app.run(until=time.floor + Time(
            100 * _TICKS_PER_FRAME,
            ticks_per_second=core.ticks_per_second))

        pixels = numpy.frombuffer(core.get_frame_pixels(),
                                  dtype=numpy.uint32).copy()

    width, height = Core.FRAME_SIZE
    pixels = pixels.reshape(height, width)

    rgb = numpy.empty((height, width, 3), dtype=numpy.uint8)
    rgb[..., 0] = (pixels >> 16) & 0xff
    rgb[..., 1] = (pixels >> 8) & 0xff
    rgb[..., 2] = pixels & 0xff

    image = PIL.Image.fromarray(rgb, 'RGB')

    # Match expected_output.png: 6x pixels, the crop covering the
    # stripes on the top border and the top-left of the screen area.
    SCALE = 6
    CROP_X, CROP_Y, CROP_SIZE = 18, 24, 63
    image = image.crop((CROP_X, CROP_Y,
                        CROP_X + CROP_SIZE, CROP_Y + CROP_SIZE))
    image = image.resize((CROP_SIZE * SCALE, CROP_SIZE * SCALE),
                         PIL.Image.NEAREST)

    here = pathlib.Path(__file__).parent

    dest = here / 'actual_output.png'
    image.save(dest)
    print(f'{dest}')

    # Expected on the left, actual on the right.
    expected = PIL.Image.open(here / 'expected_output.png')
    GAP = 10
    comparison = PIL.Image.new(
        'RGB',
        (expected.width + GAP + image.width,
         max(expected.height, image.height)),
        (255, 255, 255))
    comparison.paste(expected, (0, 0))
    comparison.paste(image, (expected.width + GAP, 0))

    dest = here / 'comparison.png'
    comparison.save(dest)
    print(f'{dest}')


if __name__ == '__main__':
    main()

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

import pathlib
import sys

import numpy
import PIL.Image

from zx._core import Core
from zx._core import RunEvents
from zx._device import Dispatcher
from zx._device import IsTapePlayerStopped
from zx._device import LoadTape
from zx._device import PauseUnpauseTape
from zx._file import parse_file
from zx._keyboard import Keyboard
from zx._keyboard import make_key_strokes
from zx._machines import Spectrum48CoreSnapshot
from zx._tape import TapePlayer
from zx._time import Time


def main() -> None:
    tape_filename = (sys.argv[1] if len(sys.argv) > 1
                     else 'screen_timing_early.tap')

    core = Core()
    core.install_snapshot(Spectrum48CoreSnapshot())
    devices = Dispatcher([core, Keyboard(active=True), TapePlayer()])

    def current_time() -> Time:
        return Time(core.tick_count,
                    ticks_per_second=core.model._TICKS_PER_FRAME * 50)

    def run_frames(count: int) -> None:
        frames = 0
        while frames < count:
            if RunEvents.END_OF_FRAME in RunEvents(core._run(devices)):
                frames += 1

    def type_keys(*keys: int | str) -> None:
        strokes = make_key_strokes(*keys, start=current_time())
        for stroke in strokes:
            devices.notify(stroke)
        while current_time() < strokes[-1].time:
            core._run(devices)

    # Boot to the BASIC prompt.
    run_frames(90)

    # LOAD ""
    type_keys('J', 'SS+P', 'SS+P', 'ENTER')

    devices.notify(LoadTape(parse_file(tape_filename)))
    devices.notify(PauseUnpauseTape(False))

    while True:
        core._run(devices)

        stopped = IsTapePlayerStopped()
        devices.notify(stopped)
        if stopped.stopped:
            break

    # The loaded program waits for a key before starting the drawing
    # loop.
    type_keys('ENTER')

    # Let the drawing loop calibrate against ~INT and settle, then
    # capture at the end of a fully rendered frame.
    run_frames(100)

    width, height = Core.FRAME_SIZE
    pixels = numpy.frombuffer(core.get_frame_pixels(), dtype=numpy.uint32)
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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


import sys


class Reg(object):
    def __init__(self, name):
        self.name = name


class RegPair(object):
    def __init__(self, name):
        self.name = name


A = Reg('a')
B = Reg('b')
C = Reg('c')
D = Reg('d')
E = Reg('e')
H = Reg('h')
L = Reg('l')
R = Reg('r')

BC = RegPair('bc')
DE = RegPair('de')
HL = RegPair('hl')


class Command:
    pass


class Load(Command):
    def __init__(self, reg, value):
        self.reg = reg
        self.value = value


class OutA(Command):
    def __init__(self, x, y):
        self.beam_pos = x, y


class WriteAtHL(Command):
    def __init__(self, reg):
        self.reg = reg


class WriteScreenAtHL(Command):
    def __init__(self, x, y, reg):
        self.beam_pos = x, y
        self.reg = reg


class drawing_generator(object):
    SCREEN_WIDTH = 256
    SCREEN_HEIGHT = 192
    TICKS_PER_LINE = 224
    PIXELS_PER_TICK = 2

    def __init__(self, is_late_timings=False):
        self.is_late_timings = is_late_timings
        self._lines = []
        self._label = 0
        self._tick = 38

    def add_line(self, line):
        # print(line)
        self._lines.append(line)

    def add_label(self):
        n = self._label
        self._label += 1
        return 'l%d' % n

    def add_instr(self, instr, ticks):
        if type(ticks) is not list:
            ticks = [ticks]
        self.add_line('    %-24s; %5d  %5s' % (
            instr, self._tick, ' + '.join('%d' % x for x in ticks)))
        self._tick += sum(ticks)

    def generate_load(self, load):
        if isinstance(load.reg, RegPair):
            self.add_instr('ld %s, 0x%04x' % (load.reg.name, load.value), 10)
        else:
            self.add_instr('ld %s, 0x%02x' % (load.reg.name, load.value), 7)

    def generate_out_a(self, out):
        self.move_to_beam_pos(out.beam_pos, ticks_to_reserve=7)
        self.add_instr('out (0xfe), a', 11)

    def generate_write_at_hl(self, write):
        delay = self.get_memory_contention_delay(self._tick + 4)
        self.add_instr('ld (hl), %s' % write.reg.name, [7, delay])

    def generate_write_screen_at_hl(self, write):
        self.move_to_beam_pos(write.beam_pos, ticks_to_reserve=4)
        self.generate_write_at_hl(write)

    _COMMAND_GENERATORS = {
        Load: generate_load,
        OutA: generate_out_a,
        WriteAtHL: generate_write_at_hl,
        WriteScreenAtHL: generate_write_screen_at_hl,
    }

    def generate_command(self, command):
        self._COMMAND_GENERATORS[type(command)](self, command)

    def _get_reg_pair_clobbers(self, clobbers):
        if B in clobbers and C in clobbers:
            yield BC

        if D in clobbers and E in clobbers:
            yield DE

        if H in clobbers and L in clobbers:
            yield HL

    # TODO: Test and optimize.
    def generate_delay(self, delay, clobbers=[], step=0):
        while delay:
            # print('delay:', delay)
            if (delay < 4 or delay == 5) and step:
                delay += step
                continue

            if delay == 4:
                self.add_instr('nop', 4)
                break

            if delay == 6:
                done = False
                for rp in self._get_reg_pair_clobbers(clobbers):
                    self.add_instr('inc %s' % rp.name, 6)
                    done = True
                    break

                if done:
                    break

                if step:
                    delay += step
                    continue

                assert 0, ('No register pair to clobber to generate a '
                           'delay of %d ticks!' % delay)

            if delay == 7:
                self.add_instr('or 0', 7)
                break

            if delay == 9:
                # TODO: Other options are:
                #  ld a, r
                #  ld a, i
                #  ld i, a
                if R in clobbers:
                    self.add_instr('ld r, a', 9)
                    break
                elif step:
                    delay += step
                    continue
                else:
                    assert 0, ('Need to clobber the register R to generate a '
                               'delay of %d ticks!' % delay)

            if delay == 10:
                label = self.add_label();
                self.add_instr('jp %s' % label, 10)
                self.add_line(label + ':')
                break

            if delay == 13:
                # TODO: 13 = 4 + 9, where the 9 needs a clobber.
                assert 0

            NON_CLOBBERING_PATTERNS = {
                # TODO: Add the missing values.
                8: [4, 4],
                11: [4, 7],
                12: [4, 4, 4],
                14: [7, 7],
                15: [4, 4, 7],
                16: [4, 4, 4, 4],
                17: [7, 10],
                18: [4, 7, 7],
                19: [4, 4, 4, 7],
                20: [4, 4, 4, 4, 4],
                21: [7, 7, 7],
                22: [4, 4, 7, 7],
                23: [4, 4, 4, 4, 7],
                24: [4, 4, 4, 4, 4, 4],
                25: [4, 7, 7, 7],
                26: [4, 4, 4, 7, 7],
                27: [4, 4, 4, 4, 4, 7],
                28: [4, 4, 4, 4, 4, 4, 4],
                29: [4, 4, 7, 7, 7],
                30: [4, 4, 4, 4, 7, 7],
                31: [4, 4, 4, 4, 4, 4, 7],
            }

            if delay in NON_CLOBBERING_PATTERNS:
                pattern = NON_CLOBBERING_PATTERNS[delay]
                assert sum(pattern) == delay
                for d in pattern:
                    self.generate_delay(d)
                break

            # TODO: Use djnz loops when they are a good fit.
            LOOP_THRESHOLD = 2 * 16 + 7 - 5
            if delay >= LOOP_THRESHOLD:
                assert clobbers, 'No clobber register for a delay loop!'
                clobber = clobbers[0]

                n = (delay - 7 + 5) // 16 - 1
                n = min(n, 0xff)  # TODO: Support longer loops.
                assert n > 0

                self.add_instr('ld %s, %d' % (clobber.name, n), 7)
                delay -= 7

                label = self.add_label()
                ticks = n * 16 - 5
                self.add_line('%-28s; %5d  %5d' % (
                    label + ':', self._tick, ticks))
                self.add_line('    %-24s;        %5d' % (
                    'dec %s' % clobber.name, 4))
                self.add_line('    %-24s;        %5s' % (
                    'jr nz, %s' % label, '7 + 5'))

                self._tick += ticks
                delay -= ticks

                # Make sure the remaining delay won't cause us
                # trouble.
                assert (delay >= LOOP_THRESHOLD or
                        delay in NON_CLOBBERING_PATTERNS), delay
                continue

            assert 0, "Don't know how to generate a delay of %d ticks!" % delay

    def move_to_tick(self, tick, clobbers=[], step=0):
        assert tick >= self._tick
        self.generate_delay(tick - self._tick, clobbers, step)

    def align_tick(self, div, rem):
        aligned_tick = (self._tick + (div - rem - 1)) // div * div + rem
        self.move_to_tick(aligned_tick, clobbers=[A, B, C, R], step=div)

    def align_end_tick(self):
        self.align_tick(4, 1)

    def move_to_beam_pos(self, pos, ticks_to_reserve):
        BASE_TICK = 64 * self.TICKS_PER_LINE + 8 // 2
        if self.is_late_timings:
            BASE_TICK += 1
        x, y = pos
        target_tick = (BASE_TICK + y * self.TICKS_PER_LINE + x // 2 -
                       ticks_to_reserve)
        self.move_to_tick(target_tick, clobbers=[B])

    def get_memory_contention_delay(self, tick):
        # TODO: We sample ~INT during the last tick of the
        # previous instruction, so we add 1 to the contention
        # base to compensate that.
        CONT_BASE = 14335 + 1
        if self.is_late_timings:
            CONT_BASE += 1
        if tick < CONT_BASE:
            return 0

        if tick >= CONT_BASE + self.SCREEN_HEIGHT * self.TICKS_PER_LINE:
            return 0

        ticks_since_new_line = (tick - CONT_BASE) % self.TICKS_PER_LINE
        if ticks_since_new_line >= self.SCREEN_WIDTH / self.PIXELS_PER_TICK:
            return 0

        ticks_since_new_ula_cycle = ticks_since_new_line % 8
        delay = (0 if ticks_since_new_ula_cycle == 7 else
                 6 - ticks_since_new_ula_cycle)

        return delay

    def generate(self, *commands):
        for command in commands:
            self.generate_command(command)

        self.align_end_tick()

        self.add_line('    %-24s; %5d' % ('', self._tick))

    def emit_source(self):
        for line in self._lines:
            print(line)


is_late_timings = len(sys.argv) > 1 and sys.argv[1] == 'late_timings'

g = drawing_generator(is_late_timings)
g.generate(
    # Let the border be (mostly) yellow.
    Load(A, 6), OutA(0, -60),

    # Use the spare time to prepare the screen and attributes areas.
    Load(A, 0x00),
    Load(HL, 0x4000), WriteAtHL(A),
    Load(A, 0xff),
    Load(HL, 0x4001), WriteAtHL(A),
    Load(HL, 0x4002), WriteAtHL(A),

    Load(HL, 0x4100), WriteAtHL(A),
    Load(HL, 0x4101), WriteAtHL(A),
    Load(HL, 0x4102), WriteAtHL(A),

    Load(HL, 0x4200), WriteAtHL(A),
    Load(A, 0x00),
    Load(HL, 0x4201), WriteAtHL(A),
    Load(A, 0xff),
    Load(HL, 0x4202), WriteAtHL(A),

    Load(HL, 0x4300), WriteAtHL(A),
    Load(HL, 0x4301), WriteAtHL(A),
    Load(HL, 0x4302), WriteAtHL(A),

    Load(HL, 0x4400), WriteAtHL(A),
    Load(HL, 0x4401), WriteAtHL(A),
    Load(A, 0x00),
    Load(HL, 0x4402), WriteAtHL(A),

    Load(A, 0xff),
    Load(HL, 0x4500), WriteAtHL(A),
    Load(HL, 0x4501), WriteAtHL(A),
    Load(HL, 0x4502), WriteAtHL(A),

    Load(A, 0xff),
    Load(HL, 0x5820), WriteAtHL(A),
    Load(HL, 0x5841), WriteAtHL(A),
    Load(HL, 0x5862), WriteAtHL(A),

    # Draw eight colour lines, each line starting one tick later
    # and via that make the moment when the border value is
    # latched be visible.
    Load(A, 0), OutA(-16, -16),
    Load(A, 5), OutA(-14, -14),
    Load(A, 2), OutA(-12, -12),
    Load(A, 4), OutA(-10, -10),

    # This black line starts one chunk later.
    Load(A, 0), OutA(-8, -8),
    Load(A, 5), OutA(-6, -6),
    Load(A, 2), OutA(-4, -4),
    Load(A, 4), OutA(-2, -2),

    # Continue the frame with yellow border again.
    Load(A, 0), OutA(256 - 2, -1),
    Load(A, 6), OutA(256 + 64, -1),

    # This write is early enough to clear the chunk of pixels
    # before it is latched.
    Load(A, 0xff),
    Load(HL, 0x4000), WriteScreenAtHL(-10, 0, A),

    # But this one is too late.
    Load(A, 0x00),
    Load(HL, 0x4100), WriteScreenAtHL(-8, 1, A),

    # Similarly, for the second chunk in line, this is early
    # enough to clear it.
    Load(A, 0xff),
    Load(HL, 0x4201), WriteScreenAtHL(-18, 2, A),

    # But this is again too late. Meaning both the adjacent
    # chunks are latched during the same ULA delay.
    Load(A, 0x00),
    Load(HL, 0x4301), WriteScreenAtHL(-8, 3, A),

    # Now let's see when the third chunk is latched so we know
    # the length of the 16-pixel cycles.
    Load(A, 0xff),
    Load(HL, 0x4402), WriteScreenAtHL(6, 4, A),

    Load(A, 0x00),
    Load(HL, 0x4502), WriteScreenAtHL(8, 5, A),

    # Now write some attribute bytes. This write is early enough
    # to colour the attribute square with black before it's
    # latched the first time.
    Load(A, 0x00),
    Load(HL, 0x5820), WriteScreenAtHL(-10, 8, A),

    # This write is too late, so it should remain invisible.
    Load(A, 0x6d),
    WriteScreenAtHL(-8, 12, A),

    # Make sure the rest of the square is black.
    Load(A, 0x00),
    WriteScreenAtHL(128, 12, A),

    # Do the same with the 2nd attribute byte in line.
    Load(A, 0x00),
    Load(HL, 0x5841), WriteScreenAtHL(-10, 16, A),

    Load(A, 0x6d),
    WriteScreenAtHL(-8, 20, A),

    Load(A, 0x00),
    WriteScreenAtHL(128, 20, A),

    # Do it once again for the 3rd attribute byte in line.
    Load(A, 0x00),
    Load(HL, 0x5862), WriteScreenAtHL(6, 24, A),

    Load(A, 0x6d),
    WriteScreenAtHL(8, 28, A),

    Load(A, 0x00),
    WriteScreenAtHL(128, 28, A),
)
g.emit_source()

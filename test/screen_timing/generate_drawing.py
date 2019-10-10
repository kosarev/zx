#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


class Reg(object):
    def __init__(self, name, is_reg_pair=False):
        self.name = name


class RegPair(Reg):
    def __init__(self, name):
        super().__init__(name, is_reg_pair=True)


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


class drawing_generator(object):
    def __init__(self):
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
        self.add_line('    %-24s; %5d  %5d' % (instr, self._tick, ticks))
        self._tick += ticks

    def generate_load(self, load):
        if isinstance(load.reg, RegPair):
            self.add_instr('ld %s, 0x%04x' % (load.reg.name, load.value), 10)
        else:
            self.add_instr('ld %s, 0x%02x' % (load.reg.name, load.value), 7)

    def generate_out_a(self, out):
        self.move_to_beam_pos(out.beam_pos, ticks_to_reserve=7)
        self.add_instr('out (0xfe), a', 11)

    _COMMAND_GENERATORS = {
        Load: generate_load,
        OutA: generate_out_a,
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
                assert 0  # TODO: 'jp nn'

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
                20: [4, 4, 4, 4, 4],
                22: [4, 4, 7, 7],
                26: [4, 4, 4, 7, 7],
                28: [7, 7, 7, 7],
                29: [4, 4, 7, 7, 7],
                30: [4, 4, 4, 4, 7, 7],
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

                label = self.add_label();
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
        BASE_TICK = 64 * 224 + 8 // 2
        x, y = pos
        target_tick = BASE_TICK + y * 224 + x // 2 - ticks_to_reserve
        self.move_to_tick(target_tick, clobbers=[B])

    def generate(self, *commands):
        for command in commands:
            self.generate_command(command)

        self.align_end_tick()

        self.add_line('    %-24s; %5d' % ('', self._tick))

    def emit_source(self):
        for line in self._lines:
            print(line)


g = drawing_generator()
g.generate(
    Load(A, 6), OutA(0, -60),

    Load(A, 0), OutA(-16, -16),
    Load(A, 5), OutA(-14, -14),
    Load(A, 2), OutA(-12, -12),
    Load(A, 4), OutA(-10, -10),

    Load(A, 0), OutA(-8, -8),
    Load(A, 5), OutA(-6, -6),
    Load(A, 2), OutA(-4, -4),
    Load(A, 4), OutA(-2, -2),

    Load(A, 0), OutA(256 - 2, -1),
    Load(A, 6), OutA(256 + 64, -1),

    Load(A, 0xff),
    Load(HL, 0x4000),
    # WriteAtHL(0, 0, A),
)
g.emit_source()

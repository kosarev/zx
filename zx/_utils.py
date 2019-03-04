# -*- coding: utf-8 -*-


MASK16 = 0xffff


def make16(hi, lo):
    return ((hi << 8) | lo) & MASK16

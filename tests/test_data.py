#!/usr/bin/env python3

import zx
import pytest


def test_basic():
    assert list(zx._data.DataRecord({})) == []

    d = zx._data.DataRecord(dict(a=5))
    assert d['a'] == 5
    assert list(d) == ['a']
    assert list(d.items()) == [('a', 5)]

# -*- coding: utf-8 -*-

KEYS_INFO = dict()

# Generate layout-related information.
layout = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
          'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P',
          'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'ENTER',
          'CAPS SHIFT', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', 'SYMBOL SHIFT',
          'BREAK SPACE']
for n, key in enumerate(layout):
    k = KEYS_INFO.setdefault(key, dict())
    k['number'] = n  # Left to right, then top to bottom.
    k['halfrow_number'] = n // 5
    k['pos_in_halfrow'] = n % 5
    k['is_leftside'] = k['halfrow_number'] % 2 == 0
    k['is_rightside'] = not k['is_leftside']

# Compute port address lines and bit positions.
for key, k in KEYS_INFO.items():
    if k['is_leftside']:
        k['address_line'] = 11 - k['halfrow_number'] // 2
        k['port_bit'] = k['pos_in_halfrow']
    else:
        k['address_line'] = k['halfrow_number'] // 2 + 12
        k['port_bit'] = 4 - k['pos_in_halfrow']

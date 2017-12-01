# -*- coding: utf-8 -*-

KEYS_INFO = dict()

# Generate layout-related information.
layout = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
          'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P',
          'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'ENTER',
          'CAPS SHIFT', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', 'SYMBOL SHIFT',
          'BREAK SPACE']
for n, id in enumerate(layout):
    key = KEYS_INFO.setdefault(id, dict())
    key['id'] = id
    key['number'] = n  # Left to right, then top to bottom.
    key['halfrow_number'] = n // 5
    key['pos_in_halfrow'] = n % 5
    key['is_leftside'] = key['halfrow_number'] % 2 == 0
    key['is_rightside'] = not key['is_leftside']

# Compute port address lines and bit positions.
for id, key in KEYS_INFO.items():
    if key['is_leftside']:
        key['address_line'] = 11 - key['halfrow_number'] // 2
        key['port_bit'] = key['pos_in_halfrow']
    else:
        key['address_line'] = key['halfrow_number'] // 2 + 12
        key['port_bit'] = 4 - key['pos_in_halfrow']

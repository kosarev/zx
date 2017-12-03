# -*- coding: utf-8 -*-


import os


def load_image(name):
    current_dir = os.path.dirname(__file__)
    filename = os.path.join(current_dir, 'roms', name + '.rom')
    with open(filename, mode='rb') as f:
        return f.read()


def get_rom_image(machine_kind):
    return load_image(machine_kind)

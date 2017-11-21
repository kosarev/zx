# -*- coding: utf-8 -*-


import os


def load_image(name):
    current_dir = os.path.dirname(__file__)
    filename = os.path.join(current_dir, 'roms', name + '.rom')
    with open(filename, mode='rb') as f:
        return f.read()


def get_spectrum48_rom_image():
    return load_image('48')

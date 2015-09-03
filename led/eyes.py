#!/usr/bin/python

import time
import datetime
from Adafruit_8x8 import EightByEight

class EyeChanger():
    def __init__(self):
        self.grid = EightByEight(address=0x70)
        self.pixels = {}
        
    def eye_data(self, name, pixels):
        self.pixels[name] = pixels

    def show_eye(self, name):
        p = self.pixels[name]
        self.grid.clear()
        i = 0
        for x in range(0, 8):
            for y in range(0, 8):
                if p[i] == '1':
                    self.grid.setPixel(x, y)
                i = i + 1

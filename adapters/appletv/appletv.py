#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

from sofabase import sofabase
from sofabase import adapterbase
import devices


import asyncio
from pyatv import helpers

@asyncio.coroutine
def print_what_is_playing(atv):
    playing = yield from atv.metadata.playing()
    print('Currently playing:')
    print(playing)

helpers.auto_connect(print_what_is_playing)

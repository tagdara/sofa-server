import asyncio
from pyatv import helpers

@asyncio.coroutine
def print_what_is_playing(atv):
    playing = yield from atv.metadata.playing()
    print('Currently playing:')
    print(playing)

helpers.auto_connect(print_what_is_playing)

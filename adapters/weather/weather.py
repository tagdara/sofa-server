#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

from sofabase import sofabase
from sofabase import adapterbase
import devices



import math
import random
from collections import namedtuple
import requests
import json

import datetime
import dateutil.parser
import asyncio
import aiohttp

class weatherPull():
    
    def __init__(self, log, dataset=None):
        self.log=log
        self.dataset=dataset
        self.configinfo=self.dataset.config
        self.lastcheck=None
        self.log.info('weatherpuller')
    
    async def getLocationWeather(self, location, locationdata):
        try:
            self.apikey=""
            url="https://api.darksky.net/forecast/%s/%s,%s" % (self.dataset.config['apikey'], locationdata['lat'], locationdata['lng'])
            self.log.info('URL: %s' % url)
            async with aiohttp.ClientSession() as client:
                response=await client.get(url)
                data=await response.read()
                forecast=json.loads(data.decode())
                if forecast:
                    forecast['lastcheck']=datetime.datetime.now()
                return forecast
        except:
            self.log.error('Error getting weather', exc_info=True)
            return None

    
    async def update(self):
        
        print('Updating weather')
        result={}
        
        checkstart=datetime.datetime.now()
        for location in self.dataset.config['locations']:
            try:
                self.log.info('Getting ready to check %s' % location)
                #some_datetime_obj = dateutil.parser.parse(datetime_str)
                if 'lastcheck' not in self.dataset.config['locations'][location]:
                    result[location]=await self.getLocationWeather(location, self.configinfo['locations'][location])
                elif (checkstart-dateutil.parser.parse(self.configinfo['lastcheck'])).seconds>self.configinfo['timepoll']:
                    result[location]=await self.getLocationWeather(location, self.configinfo['locations'][location])
                else:
                    self.log.info('Weather was recently downloaded for %s' % location)
            except:
                self.log.info('Could not compare previous run time for %s.  Getting new data' % location, exc_info=True)
                result[location]=await self.getLocationWeather(location, self.configinfo['locations'][location])

        return result


class weather(sofabase):

    class adapterProcess():
    
        def __init__(self, log=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.data=self.dataset.data
            self.log=log
            self.notify=notify
            self.weatherchecker=weatherPull(self.log, self.dataset)
            self.loop = asyncio.new_event_loop()

            
        def start(self):
            self.log.info('Starting weather')
            
            self.data=self.loop.run_until_complete(self.weatherchecker.update())
            self.log.info(self.data)
            self.loop.run_forever()
            
        def command(self, category, item, data):
            
            return None
        
        def get(self, category, item=None):
            
            try:
                self.log.info('Request: %s %s' % (category,item))
                if not item:
                    return self.data[category]
                else:
                    return self.data[category][item]
            except:
                self.log.error('Error handing data request: %s.%s' % (category, item), exc_info=True)
                return {}


if __name__ == '__main__':
    adapter=weather(port=9088)
    adapter.start()
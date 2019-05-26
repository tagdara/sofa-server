#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

from sofabase import sofabase
from sofabase import adapterbase
import devices


import datetime
import time
import os
import math
import random
import json
import aiohttp
import asyncio
import base64
from PIL import Image
import io
import shutil

import concurrent.futures

class unifivideo(sofabase):

    class adapterProcess():

        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.log=log
            self.notify=notify
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            
            
        async def start(self):
            try:
                self.log.info('.. Starting UnifiVideo')
                self.log.info('%s' % self.dataset.config)
                await self.dataset.ingest({'camera': self.dataset.config['cameras']})
            except:
                self.log.error('Error getting camera list', exc_info=True)

        async def addSmartDevice(self, path):
            
            try:
                self.log.info('path: %s' % path)
                if path.split("/")[1]=="camera":
                    return self.addCamera(path.split("/")[2])

            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False


        def addCamera(self, deviceid):

            nativeObject=self.dataset.nativeDevices['camera'][deviceid]
            if nativeObject['name'] not in self.dataset.devices:
                return self.dataset.addDevice(nativeObject['name'], devices.simpleCamera('unifivideo/camera/%s' % deviceid, nativeObject['name']))
           
            return False


        async def virtualThumbnail(self, path, client=None):
            
            try:
                playerObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath("/"+path))

                url="https://%s:%s/api/2.0/snapshot/camera/%s?force=true&width=640&apiKey=%s" % (self.dataset.config['nvr'], self.dataset.config['snapshot_port'], playerObject['id'], self.dataset.config['api_key'])
                #self.log.info('URL: %s' % url)
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as client:
                    try:
                        async with client.get(url) as response:
                            result=await response.read()
                            return result

                    except asyncio.CancelledError:
                        self.log.warn('asyncio Couldnt get thumbnail image for %s (cancelled)' % path)
                        return None

                    except concurrent.futures._base.CancelledError:
                        self.log.warn('concurrent Couldnt get thumbnail image for %s (cancelled)' % path)
                        return None
            except:
                self.log.error('Couldnt get thumbnail image for %s' % path, exc_info=True)

        async def virtualImage(self, path, client=None):
            
            pass
            
            try:
                #self.log.info('Virtual image path: %s' % path)
 
                playerObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath("/"+path))

                url="https://%s:%s/api/2.0/snapshot/camera/%s?force=true&apiKey=%s" % (self.dataset.config['nvr'], self.dataset.config['snapshot_port'], playerObject['id'], self.dataset.config['api_key'])
                #self.log.info('URL: %s' % url)
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as client:
                    async with client.get(url) as response:
                        result=await response.read()
                        return result

            except asyncio.CancelledError:
                self.log.warn('asyncio Couldnt get image for %s (cancelled)' % path)
                return None

            except concurrent.futures._base.CancelledError:
                self.log.warn('concurrent Couldnt get image for %s (cancelled)' % path)
                return None

            except:
                self.log.error('Couldnt get image for %s' % playerObject, exc_info=True)
                #return {'name':playerObject['name'], 'id':playerObject['speaker']['uid'], 'image':""}
                

        async def virtualList(self, itempath, query={}):
            
            pass

if __name__ == '__main__':
    adapter=unifivideo(name='unifivideo')
    adapter.start()
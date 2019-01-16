#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

from sofabase import sofabase
from sofabase import adapterbase
import devices

import os
import math
import random
import json
import aiohttp
import base64
from PIL import Image
import io
import cv2
import asyncio
import concurrent.futures
import datetime

class amcrest(sofabase):

    class adapterProcess():

        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.streams={}
            self.dataset.data['camera']={}
            self.log=log
            self.notify=notify
            self.lastframe={}
            self.lastrequest={}
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            
        async def start(self):
            self.log.info('.. Starting amcrest')
            await self.dataset.ingest({'camera': self.dataset.config['cameras']})
            await self.pollcameras()

        async def stopcamera(self, camera):

            try:
                self.streams[camera].release
                del self.streams[camera]
                self.log.info('Camera %s disconnected' % camera)
            except:
                self.log.error('Error setting up camera %s' % camera, exc_info=True)


        async def startcamera(self, camera):

            try:
                cameras=self.dataset.config['cameras']
                url='rtsp://%s:%s@%s?subtype=1' % (cameras[camera]['username'],cameras[camera]['password'],cameras[camera]['address'])
                self.streams[camera] = cv2.VideoCapture(url)
                self.streams[camera].set(cv2.CAP_PROP_BUFFERSIZE, 3)
                self.streams[camera].grab()
                self.log.info('Camera %s connected: %s' % (camera,url))
            except:
                self.log.error('Error setting up camera %s' % camera, exc_info=True)

        async def pollcameras(self):        
            
            while True:
                for camstream in self.streams:
                    if (datetime.datetime.now()-self.lastrequest[camstream]).seconds>5:
                        await self.stopcamera(camstream)
                        break
                    else:
                        self.streams[camstream].grab()
                await asyncio.sleep(.5)


        async def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="camera":
                    return self.addCamera(path.split("/")[2])

            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False


        def addCamera(self, deviceid):
            
            nativeObject=self.dataset.data['camera'][deviceid]
            if nativeObject['name'] not in self.dataset.devices:
                return self.dataset.addDevice(nativeObject['name'], devices.simpleCamera('amcrest/camera/%s' % deviceid, nativeObject['name']))
           
            return False


        async def virtualThumbnail(self, path, client=None):
            
            try:
                camstream=path.split('/')[1]
                self.lastrequest[camstream]=datetime.datetime.now()
                if camstream not in self.streams:
                    await self.startcamera(camstream)
                ret, frame=self.streams[camstream].retrieve()
                playerObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath("/"+path))
                jpg=cv2.imencode('.jpg', frame)[1].tostring()
                #self.log.info('Return image')
                return jpg
            except:
                self.log.error('Couldnt get thumbnail image for %s' % path, exc_info=True)
                #return {'name':playerObject['name'], 'id':playerObject['speaker']['uid'], 'image':""}


        async def virtualImage(self, path, client=None):
            
            try:
                camstream=path.split('/')[1]
                self.lastrequest[camstream]=datetime.datetime.now()
                if camstream not in self.streams:
                    await self.startcamera(camstream)
                ret, frame=self.streams[camstream].retrieve()
                playerObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath("/"+path))
                jpg=cv2.imencode('.jpg', frame)[1].tostring()

                return jpg
            except:
                self.log.error('Couldnt get thumbnail image for %s' % path, exc_info=True)
                #return {'name':playerObject['name'], 'id':playerObject['speaker']['uid'], 'image':""}
                

if __name__ == '__main__':
    adapter=amcrest(name='amcrest')
    adapter.start()
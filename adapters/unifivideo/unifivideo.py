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
import uuid

import concurrent.futures

class unifivideo(sofabase):
    
    class EndpointHealth(devices.EndpointHealth):

        @property            
        def connectivity(self):
            return 'OK'
    
    class MotionSensor(devices.MotionSensor):

        @property            
        def detectionState(self):
            return 'NOT_DETECTED'

    class CameraStreamController(devices.CameraStreamController):

        @property
        def cameraStreamConfigurations(self):
            return [
                    {
                        "protocols": ["HLS"], 
                        "resolutions": [{"width":1280, "height":720}], 
                        "authorizationTypes": ["BASIC"], 
                        "videoCodecs": ["H264"], 
                        "audioCodecs": ["AAC"] 
                    }
                ]

        @property
        def cameraStreams(self):
            return [
                {
                    "uri": "https://%s:%s/hls/%s.m3u8" % (self.adapter.dataset.config['nginx_hls_hostname'],self.adapter.dataset.config['nginx_hls_port'], self.deviceid),
                    "expirationTime": (datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)).isoformat()[:-10]+"Z",
                    "idleTimeoutSeconds": 30,
                    "protocol": "HLS",
                    "resolution": {
                        "width": 1280,
                        "height": 720
                    },
                    "authorizationType": "BASIC",
                    "videoCodec": "H264",
                    "audioCodec": "AAC"                
                }
                ]
                
        def imageUri(self, res='low', width=640):
            if res=='low':
                return "https://%s/thumbnail/unifivideo/%s" % (self.adapter.dataset.config['nginx_hls_hostname'], self.deviceid )
            # This is the real one but we should not use this instead use the brokered image since it may not be reachable by clients
            #return "https://%s:%s/api/2.0/snapshot/camera/%s?force=true&apiKey=%s" % (self.adapter.dataset.config['nvr'], self.adapter.dataset.config['snapshot_port'], self.deviceid, self.adapter.dataset.config['api_key'])
            return "https://%s/image/unifivideo/%s?width=%s" % (self.adapter.dataset.config['nginx_hls_hostname'], self.deviceid, width )

        async def InitializeCameraStreams(self, payload, correlationToken=''):
            try:
                for config in payload['cameraStreams']:
                    width=config['resolution']['width']
                    if config['resolution']['width']<1280:
                        res='low'
                    else:
                        res='high'
                        
                return {
                    "event": {
                        "header": {
                            "name":"Response",
                            "payloadVersion": self.device.payloadVersion,
                            "messageId":str(uuid.uuid1()),
                            "namespace":self.device.namespace,
                            "correlationToken":correlationToken
                        },
                        "endpoint": {
                            "endpointId": self.device.endpointId
                        }
                    },
                    "payload": { "cameraStreams": self.cameraStreams, "imageUri":self.imageUri(res, width) }
                }
            except:
                self.log.error('!! Error during Initialize Camera Streams', exc_info=True)
                return None


                
    class adapterProcess():

        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.log=log
            self.dataset.nativeDevices['camera']={}
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
                device=devices.alexaDevice('unifivideo/camera/%s' % nativeObject['id'], nativeObject['name'], displayCategories=['CAMERA'], adapter=self)
                device.CameraStreamController=unifivideo.CameraStreamController(device=device)
                device.EndpointHealth=unifivideo.EndpointHealth(device=device)
                return self.dataset.newaddDevice(device)
            return False


        async def virtualThumbnail(self, path, client=None):
            
            try:
                url="https://%s:%s/api/2.0/snapshot/camera/%s?force=true&width=640&apiKey=%s" % (self.dataset.config['nvr'], self.dataset.config['snapshot_port'], path, self.dataset.config['api_key'])
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
            except TimeoutError:
                self.log.error('Couldnt get thumbnail image for %s (timeout)' % path)
                return None
            except ConnectionRefusedError:
                self.log.error('Couldnt get thumbnail image for %s (connection refused)' % path)
                return None
            except:
                self.log.error('Couldnt get thumbnail image for %s' % path, exc_info=True)
                return None

        async def virtualImage(self, path, client=None):
            
            try:
                url="https://%s:%s/api/2.0/snapshot/camera/%s?force=true&apiKey=%s" % (self.dataset.config['nvr'], self.dataset.config['snapshot_port'], path, self.dataset.config['api_key'])
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
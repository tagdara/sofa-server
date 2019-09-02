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
import json
import asyncio
import aiohttp


class post(sofabase):

    class EndpointHealth(devices.EndpointHealth):

        @property            
        def connectivity(self):
            return 'OK'

    class PowerController(devices.PowerController):

        @property            
        def powerState(self):
            return "ON" if self.nativeObject['status'] else "OFF"

        async def TurnOn(self, correlationToken='', **kwargs):
            try:
                response=await self.adapter.executeGet(self.deviceid, 'on')
                return await self.dataset.generateResponse(self.device.endpointId, correlationToken)    
            except:
                self.adapter.log.error('!! Error during TurnOn', exc_info=True)
        
        async def TurnOff(self, correlationToken='', **kwargs):
            try:
                response=await self.adapter.executeGet(self.deviceid, 'off')
                return await self.dataset.generateResponse(self.device.endpointId, correlationToken)    
            except:
                self.adapter.log.error('!! Error during TurnOff', exc_info=True)
    
    class adapterProcess(adapterbase):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.dataset.nativeDevices['target']={}
            self.log=log
            self.notify=notify
            self.polltime=5

            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            
        async def start(self):
            self.targets=self.loadJSON('posttargets')
            for target in self.targets:
                await self.dataset.ingest({"target": { target : self.targets[target] }})
            self.log.info('.. Starting post')


        # Adapter Overlays that will be called from dataset
        def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="target":
                    return self.addSmartPost(path.split("/")[2])

            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False


        async def addSmartPost(self, deviceid):
            
            nativeObject=self.dataset.nativeDevices['target'][deviceid]
            if nativeObject['name'] not in self.dataset.localDevices:
                device=devices.alexaDevice('post/target/%s' % deviceid, nativeObject['name'], displayCategories=['OTHER'], adapter=self)
                device.PowerController=post.PowerController(device=device)
                device.EndpointHealth=post.EndpointHealth(device=device)
                return self.dataset.newaddDevice(device)

            return False

        async def executePost(self, target, command, data=""):
            
            try:
                url=self.targets[target][command]
                headers = { "Content-type": "text/xml" }
                async with aiohttp.ClientSession() as client:
                    response=await client.post(url, data=data, headers=headers)
                    result=await response.read()
                    result=json.loads(result.decode())
                    self.log.info('Post result: %s' % result)
                    return result
                
                self.log.warn('.! No Result returned')            
                return {}
    
            except:
                self.log.error("Error requesting state for %s" % endpointId,exc_info=True)
                return {}

        async def executeGet(self, target, command):
            
            try:
                url=self.targets[target][command]
                async with aiohttp.ClientSession() as client:
                    async with client.get(url) as response:
                        status=response.status
                        result=await response.text()
                
                if result:
                    await self.dataset.ingest({"target": { target : { "status": command=="on" }}})
                    self.log.info('.. Get result: %s' % result)
                    return result
                    
                self.log.warn('.! No Result returned')            
                return {}
    
            except:
                self.log.error("Error requesting state for %s" % target, exc_info=True)
                return {}



if __name__ == '__main__':
    adapter=post(name='post')
    adapter.start()

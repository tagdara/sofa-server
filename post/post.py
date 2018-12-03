#!/usr/bin/python3

import sys
sys.path.append('/opt/beta')

from sofabase import sofabase
from sofabase import adapterbase
import devices

import math
import random
import json
import asyncio
import aiohttp


class post(sofabase):
    
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
            self.targets=self.loadJSON('/opt/beta/config/posttargets.json')
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
                return self.dataset.addDevice(nativeObject['name'], devices.basicDevice('post/target/%s' % deviceid, nativeObject['name'], native=nativeObject))
            
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



        async def processDirective(self, endpointId, controller, command, payload, correlationToken='', cookie={}):

            try:
                device=endpointId.split(":")[2]

                if controller=="PowerController":
                    if command=='TurnOn':
                        response=await self.executeGet(device, 'on')
                    elif command=='TurnOff':
                        response=await self.executeGet(device, 'off')

                response=await self.dataset.generateResponse(endpointId, correlationToken)    
                return response
            except:
                self.log.error('Error executing state change.', exc_info=True)


        def virtualControllers(self, itempath):

            try:
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                self.log.debug('Checking object for controllers: %s' % nativeObject)
                
                try:
                    detail=itempath.split("/",3)[3]
                except:
                    detail=""

                controllerlist={}
                if detail=="on" or detail=="":
                    controllerlist["PowerController"]=["powerState"]

                return controllerlist
            except KeyError:
                pass
            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)


        def virtualControllerProperty(self, nativeObj, controllerProp):
            
            try:
                if controllerProp=='powerState':
                    return "ON" if nativeObj['status'] else "OFF"
                else:
                    self.log.info('Unknown controller property mapping: %s' % controllerProp)
                    return {}
            except:
                self.log.error('Error converting virtual controller property: %s %s' % (controllerProp, nativeObj), exc_info=True)
                
                


if __name__ == '__main__':
    adapter=post(port=8103, adaptername='post', isAsync=True)
    adapter.start()

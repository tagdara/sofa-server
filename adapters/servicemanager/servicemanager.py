#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

from sofabase import sofabase
from sofabase import adapterbase
from sofacollector import SofaCollector

import devices

import math
import random
from collections import namedtuple

import json
import asyncio
import aiohttp
import subprocess

class servicemanager(sofabase):
    
    class adapterProcess(SofaCollector.collectorAdapter):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.log=log
            self.notify=notify
            self.polltime=30
            self.loop=loop
            self.dataset.nativeDevices['adapters']={}
            
        async def start(self):
            self.log.info('.. Starting adapter')
            await self.poll_loop()
            
        async def poll_loop(self):
            while True:
                try:
                    #self.log.info("Polling data")
                    await self.adapter_checker()
                    await asyncio.sleep(self.polltime)
                except:
                    self.log.error('Error polling for data', exc_info=True)
                    
        # Utility Functions
        
        async def adapter_checker(self):
            
            try:
                workingadapters=self.dataset.config['adapters']
                for adapter in workingadapters:
                    adapterstate={"state":{}, "service":{}, "rest": {}}
                    if adapter in self.dataset.adapters:
                        #self.log.info('Checking adapter: %s / %s' % (adapter, self.dataset.adapters[adapter]))
                        adapterstate['state']=await self.get_adapter_status(adapter)
                        #self.log.info('Status: %s' % status)
                        adapterstate['service']=await self.get_service_status(adapter)
                        adapterstate['rest']=self.dataset.adapters[adapter]
                    else:
                        self.log.info('Adapter not discovered yet: %s' % adapter)
                        
                    await self.dataset.ingest({'adapters': { adapter : adapterstate}})
                    
            except:
                self.log.error('Error listing adapters', exc_info=True)
        
        async def virtualAddAdapter(self, adapter, adapterdata):
            
            try:
                self.log.info('Getting discovered adapter status for %s' % adapter)
                adapterstate=await self.get_adapter_status(adapter)
                adapterstate['service']=await self.get_service_status(adapter)
                adapterstate['rest']=self.dataset.adapters[adapter]
                await self.dataset.ingest({'adapters': { adapter : adapterstate}})
            except:
                self.log.info('Error getting adapter status after discovery: %s' % adapter, exc_info=True)

        async def virtualUpdateAdapter(self, adapter, adapterdata):
            
            try:
                self.log.info('Getting updated adapter status for %s' % adapter)
                await self.get_adapter_status(adapter)
            except:
                self.log.info('Error updating adapter status after discovery: %s' % adapter, exc_info=True)

        # Adapter Overlays that will be called from dataset
        async def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="adapters":
                    return await self.addSmartAdapter(path.split("/")[2])

            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False

        async def addSmartAdapter(self, deviceid):
            
            nativeObject=self.dataset.nativeDevices['adapters'][deviceid]
            if deviceid not in self.dataset.localDevices:
                return self.dataset.addDevice(deviceid, devices.smartAdapter('servicemanager/adapters/%s' % deviceid, deviceid, native=nativeObject))
            
            return False

        
        async def get_adapter_status(self, adaptername):
            
            try:
                url = 'http://%s:%s/status' % (self.dataset.adapters[adaptername]['address'], self.dataset.adapters[adaptername]['port'])
                async with aiohttp.ClientSession() as client:
                    async with client.get(url) as response:
                        result=await response.read()
                        return json.loads(result.decode())
                        
            except aiohttp.client_exceptions.ClientConnectorError:
                self.log.warn('Connection error trying to get status for adapter %s at %s' % (adaptername, url))
                return {}
            except aiohttp.client_exceptions.ClientOSError:
                self.log.warn('Connection error trying to get status for adapter %s at %s' % (adaptername, url))
                return {}

            except:
                self.log.error('Error getting status for adapter %s at %s' % (adaptername, url), exc_info=True)
                return {}
                
        async def get_service_status(self, adaptername):
            
            try:
                keep=['WatchdogTimestamp', 'ExecMainStartTimestamp', 'LoadState', 'Result', 'ExecMainPID','ActiveState', 'SubState']
                
                key_value = subprocess.check_output(["systemctl", "show", "sofa-%s" % adaptername], universal_newlines=True).split('\n')
                json_dict = {}
                for entry in key_value:
                    kv = entry.split("=", 1)
                    if len(kv) == 2:
                        if kv[0] in keep:
                            json_dict[kv[0]] = kv[1]
                return json_dict        
            except:
                self.log.error('Error getting adapter service status', exc_info=True)
                return {}
                
            
        async def adapterRestartHandler(self, adaptername):
            
            try:
                stdoutdata = subprocess.getoutput("/opt/sofa-server/svc %s" % adaptername)
    
            except:
                self.log.error('Error restarting adapter', exc_info=True)


        def getNativeFromEndpointId(self, endpointId):
            
            try:
                return endpointId.split(":")[2]
            except:
                return False
                
        async def processDirective(self, endpointId, controller, command, payload, correlationToken='', cookie={}):

            try:
                device=endpointId.split(":")[2]
                nativeCommand=None

                if nativeCommand:
                    response=await self.dataset.generateResponse(endpointId, correlationToken)
                    return response
                    
                return None
                    
            except:
                self.log.error('Error executing state change.', exc_info=True)


        def virtualControllers(self, itempath):

            try:
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                
                try:
                    detail=itempath.split("/",3)[3]
                except:
                    detail=""

                controllerlist={}

                return controllerlist
            except KeyError:
                pass
            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)
     
            
        def virtualControllerProperty(self, nativeObj, controllerProp):
            
            try:
                return {}

            except:
                self.log.error('Error converting virtual controller property: %s %s' % (controllerProp, nativeObj), exc_info=True)
                
        async def virtualList(self, itempath, query={}):

            try:
                if itempath=="adapters":
                    return self.dataset.nativeDevices
                return {}

            except:
                self.log.error('Error getting virtual list for %s' % itempath, exc_info=True)
                return {}


if __name__ == '__main__':
    adapter=servicemanager(name='servicemanager')
    adapter.start()

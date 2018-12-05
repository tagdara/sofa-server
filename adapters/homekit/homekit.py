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
import asyncio
import aiohttp
import logging
import pickle

import pyhap.util as util
#from pyhap.accessories.TemperatureSensor import TemperatureSensor
from pyhap.accessory import Accessory
from pyhap.accessory import Bridge
from pyhap.accessory_driver import AccessoryDriver
import pyhap.const
import pyhap.loader as loader

import random
import time
import datetime
import os
import functools
import concurrent.futures

class SofaAccessory(Accessory):
    
    async def convertAccessoryCommand(self, data):
            
        try:
            device=self.dataset.data['devices'][data['name']]

            command={"directive": {
                            "endpoint": {
                                "scope": {"type": "BearerToken"}, 
                                "endpointId": device['endpointId'],
                                "cookie": device["cookie"]
                            },
                            'header': {
                                'messageId': 'ef3ab784-1768-4179-8c88-2aa6987ce669',
                                'payloadVersion': '3',
                            }, 
                            'payload': {}
                        }
            }

            if data['characteristic']=='On':
                command['directive']['header']['namespace']='PowerController'
                if data['value']:
                    command['directive']['header']['name']="TurnOn"
                else:
                    command['directive']['header']['name']="TurnOff"

            elif data['characteristic']=='Brightness':
                command['directive']['header']['namespace']='BrightnessController'
                command['directive']['header']['name']="SetBrightness"
                command['directive']['payload']={'brightness': int(data['value'])}
                
            return command
                
        except:
            self.log.error('Error converting command: %s' % data, exc_info=True)


    async def sendCommand(self, data):
            
        try:
            command=await self.convertAccessoryCommand(data)
            cookie=command['directive']['endpoint']['cookie']
            url = '%s%s' % (self.dataset.adapters[cookie['adapter']]['url'], cookie['path'])
            headers = { "Content-type": "text/xml" }
            async with aiohttp.ClientSession() as client:
                response=await client.post(url, data=json.dumps(command), headers=headers)
                result=await response.read()
                return result
        except:
            self.log.error("send command error",exc_info=True)      
            return {}




class LightBulb(SofaAccessory):

    category = pyhap.const.CATEGORY_LIGHTBULB
    

    def __init__(self, *args, dataset=None, **kwargs):
        
        self.dataset=dataset
        self.log = logging.getLogger('homekit')
        super().__init__(*args, **kwargs)
        serv_light = self.add_preload_service('Lightbulb',chars=["Name", "On", "Brightness"])
        self.char_on = serv_light.configure_char('On', setter_callback=self.set_On)
        self.char_brightness = serv_light.configure_char("Brightness", setter_callback = self.set_Brightness)

    def __getstate__(self):
        """Return the state of this instance, less the server and server thread.
        Also add the server address. All this is because we cannot pickle such
        objects and to allow to recover the server using the address.
        """
        state = dict(super(LightBulb, self).__getstate__())
        state["adapter"] = None
        state["log"] = None
        return state


    def __setstate__(self, state):
        
        self.__dict__.update(state)


    def set_On(self, value):
        
        try:
            self.log.info('Sending OnOff command: %s' % {"id":self.aid, "name":self.display_name, "characteristic":"On", "value":value} )
            asyncio.run_coroutine_threadsafe(self.sendCommand({"id":self.aid, "name":self.display_name, "characteristic":"On", "value":value}), loop=self.event_loop)
        except:
            self.log.error('Error in setbulb', exc_info=True)
            self.log.error(self.__dict__)


    def set_Brightness(self, value):
        
        try:
            asyncio.run_coroutine_threadsafe(self.sendCommand({"id":self.aid, "name":self.display_name, "characteristic":"Brightness", "value":value}), loop=self.event_loop)
        except:
            self.log.error('Error in setbright', exc_info=True)


    def stop(self):
        super(LightBulb, self).stop()



class TemperatureSensor(SofaAccessory):

    category = pyhap.const.CATEGORY_SENSOR

    def __init__(self, *args,  dataset=None,  **kwargs):

        self.dataset=dataset        
        self.log = logging.getLogger('homekit')     
        super().__init__(*args, **kwargs)
        serv_temp = self.add_preload_service('TemperatureSensor')
        #self.char_temp = serv_temp.configure_char('CurrentTemperature', setter_callback = self.set_Temperature)

    def __getstate__(self):
        """Return the state of this instance, less the server and server thread.
        Also add the server address. All this is because we cannot pickle such
        objects and to allow to recover the server using the address.
        """
        state = dict(super(TemperatureSensor, self).__getstate__())
        state["adapter"] = None
        state["log"] = None
        return state

    def run(self):
        pass

  
class Speaker(SofaAccessory):

    #category = pyhap.const.CATEGORY_SPEAKER

    def __init__(self, *args,  dataset=None,  **kwargs):

        self.dataset=dataset        
        self.log = logging.getLogger('homekit')     
        super().__init__(*args, **kwargs)
        serv_speaker = self.add_preload_service('Speaker')
        #self.char_temp = serv_temp.configure_char('CurrentTemperature', setter_callback = self.set_Temperature)

    def __getstate__(self):
        """Return the state of this instance, less the server and server thread.
        Also add the server address. All this is because we cannot pickle such
        objects and to allow to recover the server using the address.
        """
        state = dict(super(Speaker, self).__getstate__())
        state["adapter"] = None
        state["log"] = None
        return state

    def run(self):
        pass





class homekit(sofabase):

    class adapterProcess(adapterbase):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None,  **kwargs):
            self.dataset=dataset
            self.data=self.dataset.data
            self.log=log
            self.notify=notify
            self.polltime=5
            self.persistfile='/opt/beta/homekit/homekit.pickle'

            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            self.addExtraLogs()


        async def start(self):
            self.log.info('Starting homekit')
            self.dataset.ingest({'accessorymap': self.loadJSON('/opt/beta/homekit/accessorymap.json')})
            self.accloop=asyncio.new_event_loop()
            self.getAccessorySet()
            self.driver = AccessoryDriver(self.acc, 51826, persist_file=self.persistfile, loop=self.accloop)

            try:
                await self.getDiscoveryAdapters()
            except:
                self.log.info('Error with disco',exc_info=True)
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5,)
            asyncio.ensure_future(self.loop.run_in_executor(self.executor, self.driver.start,))
            self.log.info('Driver started')
 
 
        def getAccessorySet(self):
            
            try:
                self.log.info('Loading persistence file if it exists')
                self.loadFromPersist(self.persistfile)
                self.acc=None
        
                if not self.acc:
                    self.log.info('No persistence file, creating Bridge instance')
                    address = ("", 51111)
                    self.acc = Bridge(address=address, display_name="Sofa Bridge", pincode=b"203-23-999")
                else:
                    self.log.info('Loaded persistence file')
            except:
                self.log.error('Error accessory startup Data', exc_info=True)
        

        def addExtraLogs(self):
        
            self.accessory_logger = logging.getLogger('pyhap.accessory_driver')
            self.accessory_logger.addHandler(self.log.handlers[0])
            self.accessory_logger.setLevel(logging.DEBUG)
        
            self.accessory_driver_logger = logging.getLogger('pyhap.accessory_driver')
            self.accessory_driver_logger.addHandler(self.log.handlers[0])
            self.accessory_driver_logger.setLevel(logging.DEBUG)

            self.hap_server_logger = logging.getLogger('pyhap.hap_server')
            self.hap_server_logger.addHandler(self.log.handlers[0])
            self.hap_server_logger.setLevel(logging.DEBUG)
        
            self.log.setLevel(logging.DEBUG)        


        async def getDiscoveryAdapters(self):
            
            try:
                self.log.info('Discovering adapters')
                await self.notify('sofa','{"op":"discover"}')
                await asyncio.sleep(self.polltime)
                await self.discoverAllAdapterDevices()
                self.log.info('Discovered adapters')
            except:
                self.log.error('Error Getting Discovery Adapters', exc_info=True)
            

        async def pollDiscoveryAdapters(self):
            
            while timepoll:
                try:
                    await self.getDiscoveryAdapters()
                    await asyncio.sleep(self.polltime)
                except:
                    self.log.error('Error Polling Adapters', exc_info=True)

            
        def loadFromPersist(self, persistfile):
        
            try:
                if os.path.exists(persistfile):
                    with open(persistfile, "rb") as f:
                        self.acc = pickle.load(f)
                        self.log.info('Loaded data from persistence file: %s' % os.path.realpath(f.name))
                else:
                    self.acc=None
            except:
                self.log.error('Error loading cached data', exc_info=True)
                self.acc = None
    
             
        async def discoverAllAdapterDevices(self):
            
            for adapter in self.dataset.adapters:
                if adapter!="homekit":
                    try:
                        discoveryData=await self.discoverAdapterDevices(self.dataset.adapters[adapter]['url'])
                        await self.updateDeviceList(adapter, discoveryData)
                        await self.addSofaToAccessories(adapter, discoveryData)
                    except:
                        self.log.error('error getting adapter discover info',exc_info=True)
 
 
        async def discoverAdapterDevices(self, url):
            
            try:
                async with aiohttp.ClientSession() as client:
                    response=await client.get('%s/discovery' % url)
                    result=await response.read()
                    return json.loads(result.decode())
            except:
                self.log.error('Error discovering adapter devices: %s' % url, exc_info=True)
                return {}


        async def updateDeviceList(self, adapter, objlist):
            
            for obj in objlist:
                try:
                    self.dataset.ingest({"devices": { objlist[obj]['friendlyName'] :objlist[obj] }})
                except:
                    self.log.error('Error updating device list: %s' % objlist[obj],exc_info=True)
            

        async def updateAccessoryMap(self, adapter, objlist):
            
            for accid, acc in self.acc.accessories:
                self.dataset.ingest({"accessories": { acc.display_name : { "id":accid, "path": objlist}}})
             
             
        async def addSofaToAccessories(self, adapter, objlist):
            
            try:
                self.dataset.ingest({"accessorymap" : {v.display_name:k for k, v in self.acc.accessories.items()}})
                maxaid=7
                for item in self.dataset.data['accessorymap']:
                    if self.dataset.data['accessorymap'][item]>maxaid:
                        maxaid=self.dataset.data['accessorymap'][item]
                maxaid=maxaid+1

                for obj in objlist:
                    try:
                        if self.dataset.data['accessorymap'][objlist[obj]['friendlyName']] in self.acc.accessories.items():
                            self.log.info('Device already exists in accessories: %s ' % objlist[obj]['friendlyName'])
                            continue
                        else:
                            deviceaid=self.dataset.data['accessorymap'][objlist[obj]['friendlyName']]
                    except:
                        deviceaid=maxaid
                        maxaid=maxaid+1
                        self.log.warn('Item not in accessories: %s' % objlist[obj]['friendlyName'])
                    
                    try:
                        if 'LIGHT' in objlist[obj]['displayCategories']:
                            hkobj = LightBulb(objlist[obj]['friendlyName'], dataset=self.dataset, aid=deviceaid)
                            self.acc.add_accessory(hkobj)
                        elif 'THERMOSTAT' in objlist[obj]['displayCategories']:
                            hkobj = TemperatureSensor(objlist[obj]['friendlyName'], dataset=self.dataset, aid=deviceaid)
                            self.acc.add_accessory(hkobj)
                        elif 'SPEAKER' in objlist[obj]['displayCategories']:
                            hkobj = Speaker(objlist[obj]['friendlyName'], dataset=self.dataset, aid=deviceaid)
                            self.acc.add_accessory(hkobj)
                        else:
                            self.log.info('Unknown Accessory Type: %s' % objlist[obj]['displayCategories'])
                            continue
                        self.dataset.ingest({"accessorymap" : {v.display_name:k for k, v in self.acc.accessories.items()}})
                        await self.dataset.requestReportState(self.dataset.data['devices'][objlist[obj]['friendlyName']]['endpointId'])
                        #self.log.info('Added %s/%s: %s' % (objlist[obj]['friendlyName'], self.acc.accessories[self.dataset.data['accessorymap'][objlist[obj]['friendlyName']]].aid, self.acc.accessories[self.dataset.data['accessorymap'][objlist[obj]['friendlyName']]]))
                        self.acc.set_driver(self.driver) # without this, IOS clients do not get notifications
                    except:                
                        self.log.error('Error',exc_info=True)        

                self.saveJSON('/opt/beta/homekit/accessorymap.json', self.dataset.data['accessorymap'])
            except:
                self.log.error('Error AddSofaToAccessories', exc_info=True)


        async def handleStateReport(self, message):
            thisaid=self.getAccessoryFromEndpointId(message['event']['endpoint']['endpointId'])
            for prop in message['context']['properties']:
                self.log.info('Property: %s %s = %s' % (prop['namespace'], prop['name'], prop['value']))
                if prop['name']=='brightness':
                    self.setCharacteristic(thisaid, 'Lightbulb', 'Brightness', prop['value'])
                elif prop['name']=='powerState':
                    if prop['value']=='ON':
                        self.setCharacteristic(thisaid, 'Lightbulb', 'On', True)
                    elif prop['value']=='OFF':
                        self.setCharacteristic(thisaid, 'Lightbulb', 'On', False)
                elif prop['name']=='temperature':
                    self.setCharacteristic(thisaid, 'TemperatureSensor', 'CurrentTemperature', prop['value'])
            

        def getAccessoryFromEndpointId(self, endpointId):
            try:
                for dev in self.dataset.data['devices']:
                    if self.dataset.data['devices'][dev]['endpointId']==endpointId:
                        thisfn=self.dataset.data['devices'][dev]['friendlyName']
                        thisdev=self.dataset.data['accessorymap'][thisfn]
                        #thisacc=self.acc.accessories[thisdev]
                        return thisdev
                self.log.warn('No accessory found for endpointId: %s' % endpointId)
                return None
            except:
                self.log.error('Error trying to get accessory for id: %s' % endpointId, exc_info=True)

            

        def setCharacteristic(self, aid, service, char, newval):
            
            try:
                targetdev=self.acc.accessories[aid]
            except:
                self.log.error('Error getting homekit device: %s' % aid, exc_info=True)
                return False
        
            try:
                targetService=targetdev.get_service(service)
            except:
                self.log.error('Error getting service %s on homekit device: %s' % (service, aid), exc_info=True)
                return False
        
            try:
                targetChar=targetService.get_characteristic(char)
            except:
                self.log.error('Error getting characteristic %s on service %s on homekit device: %s' % (char, service, aid), exc_info=True)
                return False
            
            try:
                if char=='CurrentTemperature':
                    self.log.info('Newval: %s' % newval)
                    newval=int((newval['value'] - 32) / 1.8)
                #targetChar.set_value(newval, should_callback=False)
                targetChar.value=newval
                targetChar.notify()
                #self.log.info('Did it to: %s %s %s' % (targetdev, targetService,targetChar ))
                return True
            except:
                self.log.error('Error setting value %s on characteristic %s on service %s on homekit device: %s' % (newval, char, service, aid), exc_info=True)
                return False



if __name__ == '__main__':
    adapter=homekit(port=9011, adaptername='homekit', isAsync=True)
    adapter.start()
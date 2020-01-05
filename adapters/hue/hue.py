#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'../../base'))

from sofabase import sofabase
from sofabase import adapterbase
import devices
import definitions

import math
import random
from collections import namedtuple

import json
from huecolor import ColorHelper, colorConverter
from ahue import Bridge, QhueException, create_new_username
import asyncio
import aiohttp

class hue(sofabase):

    class EndpointHealth(devices.EndpointHealth):

        @property            
        def connectivity(self):
            return 'OK' if self.nativeObject['state']['reachable'] else "UNREACHABLE"

    class PowerController(devices.PowerController):

        @property            
        def powerState(self):
            if not self.nativeObject['state']['reachable']:
                return "OFF"
            return "ON" if self.nativeObject['state']['on'] else "OFF"

        async def TurnOn(self, correlationToken='', **kwargs):
            try:
                response=await self.adapter.setHueLight(self.deviceid, { 'on':True })
                await self.adapter.dataset.ingest(response)
                return self.device.Response(correlationToken)
            except:
                self.adapter.log.error('!! Error during TurnOn', exc_info=True)
        
        async def TurnOff(self, correlationToken='', **kwargs):

            try:
                response=await self.adapter.setHueLight(self.deviceid, { 'on':False })
                await self.adapter.dataset.ingest(response)
                return self.device.Response(correlationToken)
            except:
                self.adapter.log.error('!! Error during TurnOff', exc_info=True)
                
    class BrightnessController(devices.BrightnessController):

        @property            
        def brightness(self):
            return int((float(self.nativeObject['state']['bri'])/254)*100)
        
        async def SetBrightness(self, payload, correlationToken='', **kwargs):

            try:
                if int(payload['brightness'])>0:
                    nativeCommand={'on': True, 'bri': self.adapter.percentage(int(payload['brightness']), 255) }
                else:
                    nativeCommand= {'on': False }
                response=await self.adapter.setHueLight(self.deviceid, nativeCommand)
                await self.adapter.dataset.ingest(response)
                return self.device.Response(correlationToken)
 
            except:
                self.adapter.log.error('!! Error setting brightness', exc_info=True)

    class ColorController(devices.ColorController):

        @property            
        def color(self):
            # The real values are based on this {"bri":int(hsbdata['brightness']*255), "sat":int(hsbdata['saturation']*255), "hue":int((hsbdata['hue']/360)*65536)}
            return {"hue":round((int(self.nativeObject['state']["hue"])/65536)*360,1), "saturation":round(int(self.nativeObject['state']["sat"])/255,4), "brightness":round(int(self.nativeObject['state']["bri"])/255,4) }

        async def SetColor(self, payload, correlationToken='', **kwargs):
 
            try:
                if type(payload['color']) is not dict:
                    payloadColor=json.loads(payload['color'])
                else:
                    payloadColor=payload['color']
                nativeCommand={'on':True, 'transitiontime': 1, "bri": int(float(payloadColor['brightness'])*255), "sat": int(float(payloadColor['saturation'])*255), "hue": int((float(payloadColor['hue'])/360)*65536) }
                response=await self.adapter.setHueLight(self.deviceid, nativeCommand)
                await self.adapter.dataset.ingest(response)
                return self.device.Response(correlationToken)

            except:
                self.adapter.log.error('!! Error setting color', exc_info=True)

    class ColorTemperatureController(devices.ColorTemperatureController):

        @property            
        def colorTemperatureInKelvin(self):
            # Hue CT value uses "mireds" which is roughly 1,000,000/ct = Kelvin
            # Here we are reducing the range and then multiplying to round into hundreds
            return int(10000/float(self.nativeObject['state']['ct']))*100

        async def SetColorTemperature(self, payload, correlationToken='', **kwargs):
 
            try:
                # back from CtiK to Mireds for Alexa>Hue
                nativeCommand={'ct' : int(1000000/float(payload['colorTemperatureInKelvin'])) }               
                response=await self.adapter.setHueLight(self.deviceid, nativeCommand)
                await self.adapter.dataset.ingest(response)
                return self.device.Response(correlationToken)
            except:
                self.adapter.log.error('!! Error setting color temperature', exc_info=True)

    
    class adapterProcess(adapterbase):
        
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.hueColor=colorConverter()
            self.dataset=dataset
            self.dataset.nativeDevices['lights']={}
            self.definitions=definitions.Definitions
            self.log=log
            self.notify=notify
            self.polltime=5
            self.loop=loop
            self.inuse=False
            
        async def start(self):
            self.log.info('.. Starting hue')
            self.bridge = Bridge(self.dataset.config['address'], self.dataset.config['user'])
            await self.pollHueBridge()
            
        async def pollHueBridge(self):
            while True:
                try:
                    #self.log.info("Polling bridge data")
                    await self.getHueBridgeData('all')
                except:
                    self.log.error('Error fetching Hue Bridge Data', exc_info=True)
                
                await asyncio.sleep(self.polltime)
                    

        async def getHueBridgeData(self, category='all', device=None):
            
            try:
                #self.log.info('Polling %s' % category)
                changes=[]
                if category=="all":
                    alldata=await self.getHueAll()
                    if alldata:
                        changes=await self.dataset.ingest({'lights':alldata['lights'], 'sensors':alldata['sensors'], 'groups':alldata['groups']}, mergeReplace=True)
                elif category=="lights":
                    changes=await self.dataset.ingest({'lights': await self.getHueLights(device)}, mergeReplace=True)
                elif category=="groups":
                    await self.dataset.ingest({'groups': await self.getHueGroups()}, mergeReplace=True)
                elif category=="sensors":
                    await self.dataset.ingest({'sensors':await self.getHueSensors()}, mergeReplace=True)
                    
                return changes

            except:
                self.log.error('Error fetching Hue Bridge Data', exc_info=True)
                return {}


        def percentage(self, percent, whole):
            return int((percent * whole) / 100.0)


        def get(self, category, item):
            try:
                if category=='lights':
                    return self.getHueLights(item)
            except:
                self.log.error('Error handing data request: %s.%s' % (category, item))
                return {}


        async def getHueLights(self, light=None):
            
            try:
                if light:
                    try:
                        return { light : await self.bridge.lights[light]() }
                    except:
                        for cachelight in self.dataset.nativeDevices['lights']:
                            try:
                                if self.dataset.nativeDevices['lights'][cachelight]['name']==light:
                                    return self.bridge.lights[cachelight]()
                            except:
                                pass
                        self.log.info('Could not find light: %s' % light)
                        return None
                else:
                    #self.log.info('Lights: %s' % json.dumps(self.bridge.lights()))
                    return await self.bridge.lights()
            except aiohttp.client_exceptions.ClientConnectorError:
                self.log.error("Error getting hue config. (Failed to connect to hub)")
                
            except:
                self.log.error("Error getting hue config.",exc_info=True)
                return {}

        async def getHueAll(self):
            try:
                return await self.bridge()
            except aiohttp.client_exceptions.ClientConnectorError:
                self.log.error("!! Error connecting to hue bridge.")
                return {}
            except aiohttp.client_exceptions.ServerDisconnectedError:
                self.log.error("!! Error - hue bridge disconnected while retrieving data.")
                return {}

            except:
                self.log.error("Error getting hue data.",exc_info=True)
                return {}

        async def getHueGroups(self):
            try:
                return await self.bridge.groups()
            except:
                self.log.error("Error getting hue config.",exc_info=True)
                return {}

                
        async def getHueSensors(self):
            try:
                return await self.bridge.sensors()
            except:
                self.log.error("Error getting hue config.",exc_info=True)
                return {}


        async def getHueConfig(self):
            try:
                bridgeconfig=await self.bridge.config()
                # removing items that would spam updates
                del bridgeconfig['whitelist']
                del bridgeconfig['UTC']
                del bridgeconfig['localtime']
                
                return bridgeconfig
            except:
                self.log.error("Error getting hue config.",exc_info=True)
                return {}

        # Set Commands

        async def setHueLight(self, light, data):
        
            try:
                while self.inuse:
                    await asyncio.sleep(.02)
                    
                if light not in self.dataset.nativeDevices['lights']:
                    for alight in self.dataset.nativeDevices['lights']:
                        if self.dataset.nativeDevices['lights'][alight]['name']==light:
                            light=alight
                            break
                        
                self.inuse=True
                response=await self.bridge.lights[int(light)].state(**data)
                #self.log.info('response: %s' % response)
                state={}
                for item in response:
                    if 'success' in item:
                        for successitem in item['success']:
                            prop=successitem.split('/')[4]
                            if prop!='transitiontime':
                                state[prop]=item['success'][successitem]
                
                result={'lights': { light : {'state':state }}}
                #result=await self.getHueBridgeData(category='lights', device=int(light))

                self.inuse=False
                return result

            except:
                self.log.info("Error setting hue light: %s %s" % (light, data),exc_info=True)
                self.inuse=False
                return {}


        # Utility Functions

        async def createHueGroup(self,groupname,lights):
            try:
                huedata=await self.bridge.groups(**{"name":groupname, "lights":lights, "http_method":"post"})
            except:
                self.log.error("Error creating group.",exc_info=True)

        async def deleteHueGroup(self,groupname):
            try:
                huedata=await self.bridge.groups[groupname](**{"http_method":"delete"})
            except:
                self.log.error("Error deleting group.",exc_info=True)
                
        # Adapter Overlays that will be called from dataset
        async def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="lights":
                    nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(path))
                    if nativeObject['name'] not in self.dataset.localDevices: 
                        return await self.addSmartLight(path.split("/")[2])
            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False

        async def addSmartLight(self, deviceid):
            
            try:
                nativeObject=self.dataset.nativeDevices['lights'][deviceid]
                device=devices.alexaDevice('hue/lights/%s' % deviceid, nativeObject['name'], displayCategories=['LIGHT'], manufacturerName="Philips Hue", modelName=nativeObject['type'], adapter=self)
                device.PowerController=hue.PowerController(device=device)
                device.EndpointHealth=hue.EndpointHealth(device=device)
                device.StateController=devices.StateController(device=device)
                if nativeObject["type"] in ["Color temperature light", "Extended color light", "Color light"]:
                    device.BrightnessController=hue.BrightnessController(device=device)
                if nativeObject["type"] in ["Color temperature light", "Extended color light"]:
                    device.ColorTemperatureController=hue.ColorTemperatureController(device=device)
                if nativeObject["type"] in ["Extended color light", "Color light"]:
                    device.ColorController=hue.ColorController(device=device)

                return self.dataset.newaddDevice(device)
            except:
                self.log.error('Error in AddSmartLight %s' % deviceid, exc_info=True)
                

if __name__ == '__main__':
    adapter=hue(name='hue')
    adapter.start()

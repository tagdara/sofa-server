#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

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

class hue(sofabase):
    
    class adapterProcess(adapterbase):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.hueColor=colorConverter()
            self.dataset=dataset
            self.dataset.nativeDevices['lights']={}
            self.definitions=definitions.Definitions
            self.bridgeAddress=self.dataset.config['address']
            self.hueUser=self.dataset.config['user']
            self.log=log
            self.notify=notify
            self.polltime=5
            self.loop=loop
            self.inuse=False
            
        async def start(self):
            self.log.info('.. Starting hue')
            #self.hueUser=await self.createHueUser()
            self.bridge = Bridge(self.bridgeAddress, self.hueUser)
            await self.pollHueBridge()
            
        async def pollHueBridge(self):
            while True:
                try:
                    #self.log.info("Polling bridge data")
                    await self.getHueBridgeData('all')
                    await asyncio.sleep(self.polltime)
                except:
                    self.log.error('Error fetching Hue Bridge Data', exc_info=True)


        async def getHueBridgeData(self, category='all', device=None):
            
            #self.log.info('Polling %s' % category)
            changes=[]
            if category=="all":
                alldata=await self.getHueAll()
                changes=await self.dataset.ingest({'lights':alldata['lights'], 'sensors':alldata['sensors'], 'groups':alldata['groups']})
            elif category=="lights":
                changes=await self.dataset.ingest({'lights': await self.getHueLights(device)})
            elif category=="groups":
                await self.dataset.ingest({'groups': await self.getHueGroups()})
            elif category=="sensors":
                await self.dataset.ingest({'sensors':await self.getHueSensors()})
                
            return changes


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
            except:
                self.log.error("Error getting hue config.",exc_info=True)
                return {}

        async def getHueAll(self):
            try:
                return await self.bridge()
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
                    await asyncio.sleep(.1)
                    
                if light not in self.dataset.nativeDevices['lights']:
                    for alight in self.dataset.nativeDevices['lights']:
                        if self.dataset.nativeDevices['lights'][alight]['name']==light:
                            light=alight
                            break
                        
                self.inuse=True
                await self.bridge.lights[int(light)].state(**data)
                result=await self.getHueBridgeData(category='lights', device=int(light))
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
                
        async def createHueUser(self):

            try:
                newuser=await create_new_username(self.bridgeAddress, devicetype="Sofa")
                self.log.info('New user: %s' % newuser)
                return newuser
            except:
                self.log.error("Error creating user.",exc_info=True)
                return ""

            #b = Bridge(self.bridgeAddress)  # No username yet
            #await b(devicetype="Sofa", username="sofa", http_method="post")


        # Adapter Overlays that will be called from dataset
        def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="lights":
                    self.log.info('device path: %s' % path)
                    return self.addSmartLight(path.split("/")[2])

            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False


        async def addSmartLight(self, deviceid):
            
            nativeObject=self.dataset.nativeDevices['lights'][deviceid]
            if nativeObject['name'] not in self.dataset.localDevices:
                if nativeObject["type"] in ["Extended color light"]:
                    return self.dataset.addDevice(nativeObject['name'], devices.colorLight('hue/lights/%s' % deviceid, nativeObject['name'], native=nativeObject))
                elif nativeObject["type"] in ["Color temperature light"]:
                    return self.dataset.addDevice(nativeObject['name'], devices.tunableLight('hue/lights/%s' % deviceid, nativeObject['name'], native=nativeObject))
            
            return False


        def updateSmartDevice(self, itempath, value):

            try:
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                self.log.debug('Checking object for controllers: %s' % nativeObject)
                
                try:
                    detail=itempath.split("/",3)[3]
                except:
                    detail=""

                controllerlist={}
                if nativeObject["type"] in ["Extended color light"]:
                    if detail=="state/on" or detail=="":
                        controllerlist["PowerController"]=["powerState"]
                    if detail=="state/bri" or detail=="":
                        controllerlist["BrightnessController"]=["brightness"]
                    if detail=="state/xy/0" or detail=="":
                        controllerlist["ColorController"]=["color"]
                elif nativeObject["type"] in ["Color temperature light"]:
                    if detail=="state/on" or detail=="":
                        controllerlist["PowerController"]=["powerState"]
                    if detail=="state/bri" or detail=="":
                        controllerlist["BrightnessController"]=["brightness"]
                    if detail=="state/ct" or detail=="":
                        controllerlist["ColorTemperatureController"]=["colorTemperatureInKelvin"]
                        
                return controllerlist
            except KeyError:
                pass
            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)
                
        def getNativeFromEndpointId(self, endpointId):
            
            try:
                return endpointId.split(":")[2]
            except:
                return False
                
        async def processDirective(self, endpointId, controller, command, payload, correlationToken='', cookie={}):

            try:
                device=endpointId.split(":")[2]
                nativeCommand={}
                

                if controller=="PowerController":
                    if command=='TurnOn':
                        nativeCommand['on']=True
                    elif command=='TurnOff':
                        nativeCommand['on']=False
                elif controller=="BrightnessController":
                    if command=="SetBrightness":
                        if int(payload['brightness'])>0:
                            nativeCommand['on']=True
                            nativeCommand['bri']=self.percentage(int(payload['brightness']), 255)
                        else:
                            nativeCommand['on']=False
                elif controller=="ColorController":
                    if command=="SetColor":
                        self.log.info('Setcolor with HSB: %s' % payload)
                        if type(payload['color']) is not dict:
                            payloadColor=json.loads(payload['color'])
                            self.log.info('Fixed payload color: %s' % payloadColor)
                        else:
                            payloadColor=payload['color']
                        nativeCommand["bri"]=int(float(payloadColor['brightness'])*255)
                        nativeCommand["sat"]=int(float(payloadColor['saturation'])*255)
                        nativeCommand["hue"]=int((float(payloadColor['hue'])/360)*65536)
                        nativeCommand["transitiontime"]=1
                        nativeCommand['on']=True

                        #nativeCommand['bri']=self.percentage(int(payload['brightness']), 255)

                elif controller=="ColorTemperatureController":
                    if command=="SetColorTemperature":
                        # back from CtiK to Mireds for Alexa>Hue
                        self.log.info('Payload: %s' % payload)
                        nativeCommand['ct']=int(1000000/float(payload['colorTemperatureInKelvin']))
               
                if nativeCommand:
                    await self.setHueLight(device, nativeCommand)
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
                if nativeObject["type"] in ["Extended color light"]:
                    if detail=="state/on" or detail=="":
                        controllerlist["PowerController"]=["powerState"]
                    if detail=="state/bri" or detail=="":
                        controllerlist["BrightnessController"]=["brightness"]
                    if detail=="state/xy/0" or detail=="":
                        controllerlist["ColorController"]=["color"]
                    if detail=="state/ct" or detail=="":
                        controllerlist["ColorTemperatureController"]=["colorTemperatureInKelvin"]

                elif nativeObject["type"] in ["Color temperature light"]:
                    if detail=="state/on" or detail=="":
                        controllerlist["PowerController"]=["powerState"]
                    if detail=="state/bri" or detail=="":
                        controllerlist["BrightnessController"]=["brightness"]
                    if detail=="state/ct" or detail=="":
                        controllerlist["ColorTemperatureController"]=["colorTemperatureInKelvin"]
                        
                return controllerlist
            except KeyError:
                pass
            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)

        def virtualControllerValue(self, controllerProp, value):

            try:
                if controllerProp=='SetBrightness':
                    return { "bri":int((float(value)/100)*254)}
                elif controllerProp=='TurnOn':
                    return {"power":True}
                elif controllerProp=='TurnOff':
                    return {"power":False}
            except:
                self.log.error('Error converting value',exc_info=True)
                    
            
        def virtualControllerProperty(self, nativeObj, controllerProp):
            
            try:
                if controllerProp=='brightness':
                    int((float(nativeObj['state']['bri'])/254)*100)
                    return int((float(nativeObj['state']['bri'])/254)*100)
                    
                elif controllerProp=='powerState':
                    return "ON" if nativeObj['state']['on'] else "OFF"

                elif controllerProp=='colorTemperatureInKelvin':
                    # Hue CT value uses "mireds" which is roughly 1,000,000/ct = Kelvin
                    # Here we are reducing the range and then multiplying to round into hundreds
                    return int(10000/float(nativeObj['state']['ct']))*100

                elif controllerProp=='color':
                    # The real values are based on this {"bri":int(hsbdata['brightness']*255), "sat":int(hsbdata['saturation']*255), "hue":int((hsbdata['hue']/360)*65536)}
                    return {"hue":round((int(nativeObj['state']["hue"])/65536)*360,1), "saturation":round(int(nativeObj['state']["sat"])/255,4), "brightness":round(int(nativeObj['state']["bri"])/255,4) }
                    #return self.hueColor.xy_to_hex(nativeObj['state']['xy'][0], nativeObj['state']['xy'][1], nativeObj['state']['bri'])
                else:
                    self.log.info('Unknown controller property mapping: %s' % controllerProp)
                    return {}
            except:
                self.log.error('Error converting virtual controller property: %s %s' % (controllerProp, nativeObj), exc_info=True)
                
                


if __name__ == '__main__':
    adapter=hue(name='hue')
    adapter.start()

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
import requests
import json
import asyncio
import aiohttp
import base64
import uuid

from libpurecoollink.dyson import DysonAccount
from libpurecoollink.const import FanSpeed, FanMode, NightMode, Oscillation, FanState, StandbyMonitoring, QualityTarget, ResetFilter, HeatMode, FocusMode, HeatTarget
from libpurecoollink.dyson_pure_state import DysonPureHotCoolState, DysonPureCoolState, DysonEnvironmentalSensorState
        
class dyson(sofabase):

    class adapterProcess(adapterbase):
    
        def __init__(self, log=None, dataset=None, notify=None, request=None, loop=None, **kwargs):
            self.dataset=dataset
            self.log=log
            self.notify=notify
            self.account = DysonAccount(self.dataset.config['user'],self.dataset.config['password'],self.dataset.config['region'])
            self.dataset.nativeDevices['fan']={}
            self.pendingChanges=[]
            self.inUse=False
            self.backlog=[]
            self.polltime=30
            self.logged_in=False
            self.connected=False
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            asyncio.set_event_loop(self.loop)
                
                
        async def connect_dyson(self):
        
            return self.account.login()
            
        def ktof(self,kelvin):
        
            return ((9/5) * (kelvin - 273) + 32)
            
        def on_message(self, msg):
            
            try:
                self.pendingChanges=[]
                newstate={}
                allprops=['humidity','temperature','dust','sleep_timer',"fan_mode", "fan_state", "night_mode", "speed", "oscillation", "filter_life", "quality_target", "standby_monitoring", "tilt", "focus_mode", "heat_mode", "heat_target", "heat_state"]
                props=filter(lambda a: not a.startswith('_'), dir(msg))
                for prop in props:
                    if prop in allprops:
                        newstate[prop]=getattr(msg,prop)
                        if prop=='temperature':
                            # Since Alexa API thermostats can only handle full degrees, this rounds the temp off 
                            # to prevent mid-degree temperature updates and prevents general spam on the bus
                            newstate[prop]=int(newstate[prop])
                #self.log.info('New State: %s' % newstate)
                asyncio.ensure_future(self.dataset.ingest({'fan': {self.dyson_devices[0].name+" fan": { "state": newstate} }}), loop=self.loop)
            except:
                self.log.error('Error handling message: %s' % msg, exc_info=True)
            
        async def start(self):
            
            self.log.info('Starting Dyson')
            try:
                await self.keep_logged_in()
            except:
                self.log.error('Error', exc_info=True)
                self.logged_in=False

        async def connect_dyson(self):
            try:
                if not self.logged_in:
                    self.logged_in=self.account.login()
                    if self.logged_in:
                        self.dyson_devices = self.account.devices()
                        self.log.info('Devices: %s' % self.dyson_devices)
                        for device in self.dyson_devices:
                            devconfig={}
                            settings=["serial","active","name","version","auto_update","new_version_available","product_type","network_device"]
                            for setting in settings:
                                if setting=="name":
                                    devconfig[setting]=getattr(device,setting)+" fan"
                                else:
                                    devconfig[setting]=getattr(device,setting)
                            if 'device_address' in self.dataset.config:
                                self.connected = device.connect(self.dataset.config["device_address"]) 
                            else:
                                self.connected = device.auto_connect() # uses mdns to find the device

                            if self.connected:
                                self.dyson_devices[0].add_message_listener(self.on_message)
                                devconfig['state']=await self.getFanProperties(self.dyson_devices[0])
                                await self.dataset.ingest({'fan': {device.name+" fan": devconfig}})
            except:
                self.log.error('Error', exc_info=True)

        async def keep_logged_in(self):
            
            while True:
                try:
                    if not self.logged_in:
                        await self.connect_dyson()
                    await asyncio.sleep(self.polltime)
                except:
                    self.log.error('Error fetching Hue Bridge Data', exc_info=True)
                    self.logged_in=False

        async def setDyson(self, device, command):
            #devices[0].set_configuration(heat_mode=HeatMode.HEAT_ON, heat_target=HeatTarget.fahrenheit(80), fan_speed=FanSpeed.FAN_SPEED_5)
            #self.dyson_devices[0].set_configuration(heat_mode=HeatMode.HEAT_OFF, fan_mode=FanMode.FAN, fan_speed=FanSpeed.FAN_SPEED_2)
            
            try:
                qid=uuid.uuid1()
                if self.inUse:
                    myturn=False
                    self.backlog.append(qid)
                    self.log.info('Holding change %s due to interface in use: %s' % (qid, command))
                    try:
                        while not myturn:
                            if not self.inUse and self.backlog[0]==qid:
                                myturn=True
                                self.backlog.remove(qid)
                            else:
                                await asyncio.sleep(.1)
                    except:
                        self.log.info('Something failed with backlog checking', exc_info=True)
                self.inUse=True
                self.log.info('Setting configuration %s : %s' %  (qid, command))
                self.dyson_devices[0].set_configuration(**command)
            except:
                self.log.error('Error setting config', exc_info=True)

        def percentage(self, percent, whole):
            return int((percent * whole) / 100.0)


        async def addSmartDevice(self, path):
        
            try:
                deviceid=path.split("/")[2]    
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(path))
                if nativeObject['name'] not in self.dataset.localDevices:
                    if nativeObject["product_type"]=="455":
                        return self.dataset.addDevice(nativeObject['name'], devices.smartThermostatSpeedFan('dyson/fan/%s' % deviceid, nativeObject['name'], supportedModes=["AUTO", "HEAT", "COOL", "OFF"] ))
            
            except:
                self.log.error('Error adding smart device', exc_info=True)
            
            return False
            
        async def getFanProperties(self, device):
        
            try:
                dev=self.dyson_devices[0]
                devstate={}
                rawstate=self.dyson_devices[0].state
                envstate=self.dyson_devices[0]._environmental_state

                settings=["fan_mode", "fan_state", "night_mode", "speed", "oscillation", "filter_life", "quality_target", "standby_monitoring", "tilt", "focus_mode", "heat_mode", "heat_target", "heat_state"]
                for setting in settings:
                    devstate[setting]=getattr(self.dyson_devices[0].state,setting)
                                
                settings=['humidity','temperature','dust','sleep_timer']
                for setting in settings:                            
                    devstate[setting]=getattr(envstate,setting)
                    
                return devstate
            except:
                self.log.error('Error getting Fan properties', exc_info=True)
                return {}
                
        async def processDirective(self, endpointId, controller, command, payload, correlationToken='', cookie={}):

            try:
                device=endpointId.split(":")[2]
                nativeCommand={}
                
                if controller=="PowerController":
                    if command=='TurnOn':
                        nativeCommand['fan_mode']=FanMode.FAN
                    elif command=='TurnOff':
                        nativeCommand['fan_mode']=FanMode.OFF

                elif controller=="PowerLevelController":
                    if command=="SetPowerLevel":
                        self.log.info('Fanspeed: %s' % FanSpeed)
                        if payload['powerLevel']=='AUTO':
                            fanspeed='AUTO'
                            nativeCommand['fan_mode']=FanMode.AUTO
                        else:
                            fanspeed=str(int(payload['powerLevel'])//10)
                            if fanspeed=='0':
                                fanspeed='1'
                            nativeCommand['fan_mode']=FanMode.FAN
                            nativeCommand['fan_speed']=getattr(FanSpeed, 'FAN_SPEED_%s' % fanspeed)
 

                elif controller=="ThermostatController":
                    if command=="SetThermostatMode":
                        if payload['thermostatMode']['value']=='AUTO':
                            nativeCommand['fan_mode']=FanMode.AUTO
                            nativeCommand['heat_mode']=HeatMode.HEAT_OFF
                        if payload['thermostatMode']['value']=='HEAT':
                            nativeCommand['fan_mode']=FanMode.FAN
                            nativeCommand['heat_mode']=HeatMode.HEAT_ON
                        elif payload['thermostatMode']['value']=='FAN':
                            nativeCommand['fan_mode']=FanMode.FAN
                            nativeCommand['heat_mode']=HeatMode.HEAT_OFF
                        elif payload['thermostatMode']['value']=='COOL':
                            nativeCommand['fan_mode']=FanMode.FAN
                            nativeCommand['heat_mode']=HeatMode.HEAT_OFF
                        elif payload['thermostatMode']['value']=='OFF':
                            nativeCommand['fan_mode']=FanMode.OFF
                    if command=="SetTargetTemperature":
                        #nativeCommand['heat_mode']=HeatMode.HEAT_ON
                        nativeCommand['heat_target']=HeatTarget.fahrenheit(int(payload['targetSetpoint']['value']))

                if nativeCommand:
                    await self.setDyson(device, nativeCommand)
                    await self.waitPendingChange(device)
                    updatedProperties=await self.getFanProperties(device)
                    await self.dataset.ingest({'fan': { device: {'state':updatedProperties}}})
                    return await self.dataset.generateResponse(endpointId, correlationToken, controller=controller)
                else:
                    self.log.info('Could not find a command for: %s %s %s %s' % (device, controller, command, payload) )
                    return {}

            except:
                self.log.error('Error executing state change.', exc_info=True)


        async def waitPendingChange(self, device):
        
            if device not in self.pendingChanges:
                self.pendingChanges.append(device)

            count=0
            while device in self.pendingChanges and count<30:
                #self.log.info('Waiting for update... %s %s' % (device, self.subscription.pendingChanges))
                await asyncio.sleep(.1)
                count=count+1
            self.inUse=False
            return True

  
        def virtualControllers(self, itempath):
            
            try:
                itempart=itempath.split("/",3)
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                try:
                    detail=itempath.split("/",3)[3]
                except:
                    detail=""

                controllerlist={}
                
                if nativeObject["product_type"]=="455":
                    if detail=="state/temperature" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist,'TemperatureSensor','temperature')
                    if detail=="state/heat_mode" or detail=="state/fan_mode" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist,"ThermostatController","thermostatMode")
                    if detail=='state/heat_target' or detail=="":
                        controllerlist=self.addControllerProps(controllerlist,"ThermostatController","targetSetpoint")
                    if detail=="state/fan_state" or detail=="state/speed" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist,"PowerLevelController","powerLevel")
                
                return controllerlist
            except KeyError:
                pass
            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)

        
        def virtualControllerProperty(self, nativeObj, controllerProp):
            
            try:
                if controllerProp=='temperature':
                    return int(self.ktof(int(nativeObj['state']['temperature'])))
                
                elif controllerProp=='targetSetpoint':
                    return int(self.ktof(int(nativeObj['state']['heat_target'])/10))
                
                elif controllerProp=='powerLevel':
                    if nativeObj['state']['speed']=='AUTO':
                        return 50 # this is such a hack but need to find a way to get actual speed since alexa api powerlevel is an int
                    return int(nativeObj['state']['speed'])*10
                    
                elif controllerProp=='thermostatMode':
                    if nativeObj['state']['fan_mode']=="AUTO":
                        return "AUTO"
                    if nativeObj['state']['fan_mode']=='OFF':
                        return "OFF"
                    if nativeObj['state']['heat_mode']=='OFF':
                        return "COOL"
                        
                    self.log.info('Returning heat where fan mode is %s and heat mode is %s' % (nativeObj['state']['fan_mode'],nativeObj['state']['heat_mode']))
                    return 'HEAT'

                else:
                    self.log.info('Unknown controller property mapping: %s' % controllerProp)
                    return {}
            except:
                self.log.error('Error converting virtual controller property: %s %s' % (controllerProp, nativeObj), exc_info=True)


if __name__ == '__main__':
    adapter=dyson(name="dyson")
    adapter.start()
    

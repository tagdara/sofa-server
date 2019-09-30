#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))
from sofacollector import SofaCollector

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
import signal

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
import uuid


class SofaAccessory(Accessory):
    def __init__(self, driver, device, adapter=None, chars=[], props={}, aid=None, **kwargs):
        
        self.driver=driver
        self.adapter=adapter
        self.log=self.adapter.log
        self.loop=self.adapter.loop
        self.device=device
        if 'endpointId' in device:
            self.endpointId=device['endpointId']
            self.remoteadapter=self.endpointId.split(':')[0]
            self.props=props
            super().__init__(self.driver, self.device['friendlyName'], aid=aid)
            self.add_chars()
            self.reachable=True
        else:
            self.log.info('!! WARNING - Legacy device cant be added: %s' % device)

    def __setstate__(self, state):
        self.__dict__.update(state)

    def prop_connectivity(self, value):
        try:
            if value['value']=='UNREACHABLE':
                self.reachable=False
                if getattr(self,'char_On'):
                    self.char_On.set_value(False)
            else:
                self.reachable=True
        except:
            self.log.error('!! error setting connectivity', exc_info=True)
            
    async def createDirective(self, namespace, name, payload={} ):
    
        try:
            return { "directive": {
                            "endpoint": {
                                "scope": {"type": "BearerToken"}, 
                                "endpointId": self.endpointId,
                                "cookie": {}
                            },
                            'header': {
                                'namespace': namespace,
                                'name': name,
                                'messageId': str(uuid.uuid1()),
                                'correlationToken': str(uuid.uuid1()),
                                'payloadVersion': '3',
                            }, 
                            'payload': payload
                    }}
        except:
            self.log.error('!! Error creating directive: %s %s %s' % (namespace, name, payload), exc_info=True)
            return {}
    
    async def sendDirective(self, namespace, name, payload={}):
            
        try:
            self.adapterUrl=self.adapter.dataset.adapters[self.remoteadapter]['url']
            directive=await self.createDirective(namespace, name, payload)
            self.log.info('>> sending %s.%s.%s=%s' % (self.endpointId, namespace, name, payload))
            headers = { "Content-type": "text/xml" }
            async with aiohttp.ClientSession() as client:
                response=await client.post(self.adapterUrl, data=json.dumps(directive), headers=headers)
                result=await response.read()
                self.log.info('<< response %s' % result)
                return result
        except:
            self.log.error("!! send command error",exc_info=True)      
            return {}

class LightBulb(SofaAccessory):

    category = pyhap.const.CATEGORY_LIGHTBULB
    
    def add_chars(self):
        try:
            if self.isColor():
                serv_light = self.add_preload_service('Lightbulb', chars=["Name", "On", "Brightness", "Hue", "Saturation"])
                self.char_Hue=serv_light.configure_char('Hue', setter_callback = self.set_Hue)
                self.char_Saturation=serv_light.configure_char('Saturation', setter_callback = self.set_Saturation)
            else:
                serv_light = self.add_preload_service('Lightbulb',chars=["Name", "On", "Brightness"])
            self.char_On = serv_light.configure_char('On', setter_callback=self.set_On)
            self.char_Brightness = serv_light.configure_char("Brightness", setter_callback = self.set_Brightness)
        except:
            self.log.error("!! error adding characteristics", exc_info=True)      

    def set_On(self, value):
        try:
            if value:
                asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.PowerController','TurnOn'), loop=self.loop)
            else:
                asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.PowerController','TurnOff'), loop=self.loop)
        except:
            self.log.error('!! Error in set_On: %s' % self.__dict__, exc_info=True)

    def set_Brightness(self, value):
        try:
            asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.BrightnessController',"SetBrightness", { 'brightness': int(value) }), loop=self.loop)
        except:
            self.log.error('Error in setbright', exc_info=True)

    def set_Hue(self, value):
        try:
            pass
            #self.log.info('Not Sending Hue change as saturation follows: %s' % colorval )
            #asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.ColorController',"SetColor", {'color': {"hue": self.char_Hue.value, "saturation": self.char_Saturation.value/100, "brightness": self.char_Brightness.value/100 }})
        except:
            self.log.error('Error in set hue', exc_info=True)

    def set_Saturation(self, value):
        try:
            asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.ColorController',"SetColor", {'color': {"hue": self.char_Hue.value, "saturation": value/100, "brightness": self.char_Brightness.value/100 }}), loop=self.loop)
        except:
            self.log.error('Error in set sat', exc_info=True)

    def isColor(self):
            
        try:
            #self.log.info('Device: %s' % device)
            for prop in self.device['capabilities']:
                if prop['interface']=="Alexa.ColorController":
                    return True
            return False
        except:
            self.log.error('Error determining if light has color capabilities', exc_info=True)
            return False
            
    def prop_brightness(self, value):
        try:
            if self.reachable:
                self.char_Brightness.set_value(value)
            else:
                self.char_Brightness.set_value(0)
        except:
            self.log.error('!! error setting brightness', exc_info=True)
                
    def prop_powerState(self, value):
        try:
            if self.reachable and value=='ON':
                self.char_On.set_value(True)
            else:
                self.char_On.set_value(False)
        except:
            self.log.error('!! error setting power state', exc_info=True)

    def prop_color(self, value):
        try:
            if self.reachable:
                self.char_Hue.set_value(value['hue'])
                self.char_Hue.set_value(value['saturation']*100)
                self.char_Brightness.set_value(value['brightness']*100)
        except:
            self.log.error('!! error setting color', exc_info=True)


class Switch(SofaAccessory):

    category = pyhap.const.CATEGORY_SWITCH

    def add_chars(self):
        try:
            serv_switch = self.add_preload_service('Switch')
            self.char_On = serv_switch.configure_char('On', setter_callback=self.set_On)
        except:
            self.log.error("!! error adding characteristics", exc_info=True)      

    def set_On(self, value):
        try:
            if value:
                asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.PowerController','TurnOn'), loop=self.loop)
            else:
                asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.PowerController','TurnOff'), loop=self.loop)
        except:
            self.log.error('!! Error in set_On: %s' % self.__dict__, exc_info=True)

    def prop_powerState(self, value):
        try:
            if self.reachable and value=='ON':
                self.char_On.set_value(True)
            else:
                self.char_On.set_value(False)
        except:
            self.log.error('!! error setting power state', exc_info=True)
            

class TemperatureSensor(SofaAccessory):

    category = pyhap.const.CATEGORY_SENSOR

    def add_chars(self):
        try:
            serv_temp = self.add_preload_service('TemperatureSensor')
            self.char_temp = serv_temp.configure_char('CurrentTemperature')
        except:
            self.log.error("!! error adding characteristics", exc_info=True)      

    def prop_temperature(self, value):
        try:
            if value['scale']=='FAHRENHEIT':
                self.char_temp.set_value((int(value['value'])-32) * 5.0 / 9.0)
            else:
                self.char_temp.set_value(value['value'])
        except:
            self.log.error('!! error setting temperature', exc_info=True)

  

class OldTelevision(SofaAccessory):

    category = pyhap.const.CATEGORY_TELEVISION
    
    def add_chars(self):
        try:
            tv_service = self.add_preload_service('Television', ['Name','ConfiguredName','Active','ActiveIdentifier','RemoteKey', 'SleepDiscoveryMode'])
            serv_tv = self.add_preload_service('Television', chars=['Active', 'ActiveIdentifier', 'ConfiguredName', 'SleepDiscoveryMode', 'RemoteKey'])
            serv_tvspeaker = self.add_preload_service('TelevisionSpeaker', chars=['Mute', 'Volume', 'VolumeSelector'])
            self.char_Active = serv_tv.configure_char('Active', setter_callback=self.set_active)
            self.activeidentifier = serv_tv.configure_char('ActiveIdentifier', setter_callback=self.set_activeidentifier)
            self.configuredname = serv_tv.configure_char('ConfiguredName')
            self.sleepdiscoverymode = serv_tv.configure_char('SleepDiscoveryMode', setter_callback=self.set_sleepdiscoverymode)
            self.remotekey = serv_tv.configure_char('RemoteKey', setter_callback=self.set_remotekey)
            
            self.char_mute = serv_tvspeaker.configure_char('Mute', setter_callback=self.set_mute)
            self.char_volume = serv_tvspeaker.configure_char('Volume', setter_callback=self.set_volume)
            self.char_volumeselector = serv_tvspeaker.configure_char('VolumeSelector', setter_callback=self.set_volumeselector)
        
            self.configuredname.set_value('TV')
            self.sleepdiscoverymode.set_value(1)
            self.set_primary_service(serv_tv)
        except:
            self.log.error("!! error adding characteristics", exc_info=True)  

    def set_activeidentifier(self, value):
        self.log.info("TV Active Identifier: %s", value)

    def set_active(self, value):
        try:
            if value:
                asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.PowerController','TurnOn'), loop=self.loop)
            else:
                asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.PowerController','TurnOff'), loop=self.loop)
        except:
            self.log.error('Error in set TV Active OnOff', exc_info=True)

    def set_sleepdiscoverymode(self, value):
        self.log.info("TV sleep discovery mode : %s", value)

    def set_remotekey(self, value):
        try:
            vals={4:'CursorUp', 5:'CursorDown', 6:'CursorLeft', 7:'CursorRight', 8: 'DpadCenter', 9: 'Exit', 15: 'Home'}
            asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.RemoteController', 'PressRemoteButton', { 'buttonName': vals[value] }))
        except:
            self.log.error('Error in set TV Active OnOff', exc_info=True)

    def set_mute(self, value):
        self.log.info("TV set_mute : %s", value)

    def set_volume(self, value):
        self.log.info("TV set_volume : %s", value)

    def set_volumeselector(self, value):
        self.log.info("TV set_volumeselector : %s", value)

    def prop_powerState(self, value):
        try:
            if self.reachable and value=='ON':
                self.char_Active.set_value(True)
            else:
                self.char_Active.set_value(False)
        except:
            self.log.error('!! error setting power state', exc_info=True)
            
    def prop_volume(self, value):
        try:
            if self.reachable:
                self.char_volume.set_value(value)
        except:
            self.log.error('!! error setting volume', exc_info=True)

class Television(SofaAccessory):

    category = pyhap.const.CATEGORY_TELEVISION
    
    def add_chars(self):
        try:
            self.tv_service = self.add_preload_service('Television', ['Name','ConfiguredName','Active','ActiveIdentifier','RemoteKey', 'SleepDiscoveryMode'])
            self.Active = self.tv_service.configure_char('Active', value=0, setter_callback=self.set_active)
            self.ActiveIdentifier = self.tv_service.configure_char('ActiveIdentifier', value=1, setter_callback=self.set_activeidentifier)
            self.RemoteKey = self.tv_service.configure_char('RemoteKey', setter_callback=self.set_remotekey)
            self.Name = self.tv_service.configure_char('Name', value=self.device['friendlyName'])
            self.ConfiguredName = self.tv_service.configure_char('ConfiguredName', value=self.device['friendlyName'])
            self.SleepDiscoveryMode = self.tv_service.configure_char('SleepDiscoveryMode', value=1, setter_callback=self.set_sleepdiscoverymode)

            for prop in self.device['capabilities']:
                if prop['interface']=="Alexa.InputController":
                    for idx, tvinput in enumerate(prop['inputs']):
                        input_source = self.add_preload_service('InputSource', ['Name', 'Identifier'])
                        input_source.configure_char('Name', value=tvinput['name'])
                        input_source.configure_char('Identifier', value=idx + 1)
                        # TODO: implement persistence for ConfiguredName
                        input_source.configure_char('ConfiguredName', value=tvinput['name'])
                        input_source.configure_char('InputSourceType', value=3) # why 3? Figure out the types
                        input_source.configure_char('IsConfigured', value=1)
                        input_source.configure_char('CurrentVisibilityState', value=0)
                        self.tv_service.add_linked_service(input_source)

            self.tv_speaker_service = self.add_preload_service('TelevisionSpeaker', chars=['Active', 'Mute', 'VolumeControlType', 'VolumeSelector'])
            self.tv_speaker_service.configure_char('Active', value=1)

            self.tv_speaker_service.configure_char('VolumeControlType', value=1)
            self.tv_speaker_service.configure_char('Mute', setter_callback=self.set_mute)
            self.VolumeSelector=self.tv_speaker_service.configure_char('VolumeSelector', setter_callback=self.set_VolumeSelector)
        except:
            self.log.error("!! error adding characteristics", exc_info=True)  

    def set_activeidentifier(self, value):
        self.log.info("TV Active Identifier: %s", value)

    def set_active(self, value):
        try:
            if value:
                asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.PowerController','TurnOn'), loop=self.loop)
            else:
                asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.PowerController','TurnOff'), loop=self.loop)
        except:
            self.log.error('Error in set TV Active OnOff', exc_info=True)

    def set_sleepdiscoverymode(self, value):
        self.log.info("TV sleep discovery mode : %s", value)

    def set_remotekey(self, value):
        try:
            vals={4:'CursorUp', 5:'CursorDown', 6:'CursorLeft', 7:'CursorRight', 8: 'DpadCenter', 9: 'Exit', 15: 'Home'}
            asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.RemoteController', 'PressRemoteButton', { 'buttonName': vals[value] }))
        except:
            self.log.error('Error in set TV Active OnOff', exc_info=True)

    def set_mute(self, value):
        self.log.info("TV set_mute : %s", value)

    def set_volume(self, value):
        self.log.info("TV set_volume : %s", value)

    def set_VolumeSelector(self, value):
        self.log.info("TV set_volumeselector : %s", value)

    def prop_powerState(self, value):
        try:
            if self.reachable and value=='ON':
                self.Active.set_value(True)
            else:
                self.Active.set_value(False)
        except:
            self.log.error('!! error setting power state', exc_info=True)
            
    def prop_volume(self, value):
        try:
            if self.reachable:
                self.VolumeSelector.set_value(value)
        except:
            self.log.error('!! error setting volume', exc_info=True)


        
class Thermostat(SofaAccessory):

    category = pyhap.const.CATEGORY_THERMOSTAT

    def add_chars(self):
        try:
            serv_temp = self.add_preload_service('Thermostat')
            self.char_temp = serv_temp.configure_char('CurrentTemperature')
            self.char_TargetHeatingCoolingState = serv_temp.configure_char('TargetHeatingCoolingState',setter_callback=self.set_TargetHeatingCoolingState)
            self.char_CurrentHeatingCoolingState = serv_temp.configure_char('CurrentHeatingCoolingState',setter_callback=self.set_CurrentHeatingCoolingState)
            ttprops={}
            if 'TargetTemperature' in self.props:
                ttprops=self.props['TargetTemperature']
            self.char_TargetTemperature = serv_temp.configure_char('TargetTemperature', setter_callback=self.set_TargetTemperature, properties=ttprops)
        except:
            self.log.error("!! error adding characteristics", exc_info=True)  

    def set_TargetTemperature(self, value):
        try:
            asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.ThermostatController', "SetTargetSetpoint", {'temperature': value }), loop=self.loop)
        except:
            self.log.error('!! Error in set target temp', exc_info=True)

    def set_TargetHeatingCoolingState(self, value):
        try:
            vals=['OFF','HEAT']
            asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.ThermostatController',"SetThermostatMode", {'thermostatMode': {'value': vals[value] } }), loop=self.loop)
        except:
            self.log.error('!! Error in set thermostate mode', exc_info=True)

    def set_CurrentHeatingCoolingState(self, value):
        try:
            vals=['OFF','HEAT']
            asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.ThermostatController',"SetThermostatMode", {'thermostatMode': {'value': vals[value] } }), loop=self.loop)

        except:
            self.log.error('!! Error in set thermostate current mode', exc_info=True)

    def prop_temperature(self, value):
        try:
            if value['scale']=='FAHRENHEIT':
                self.char_temp.set_value((int(value['value'])-32) * 5.0 / 9.0)
            else:
                self.char_temp.set_value(value['value'])
        except:
            self.log.error('!! error setting temperature', exc_info=True)

    def prop_targetSetpoint(self, value):
        try:
            if value['scale']=='FAHRENHEIT':
                self.char_TargetTemperature.set_value((int(value['value'])-32) * 5.0 / 9.0)
            else:
                self.char_TargetTemperature.set_value(value['value'])
        except:
            self.log.error('!! error setting targetSetpoint', exc_info=True)

    def prop_upperSetpoint(self, value):
        try:
            if value['scale']=='FAHRENHEIT':
                self.char_TargetTemperature.set_value((int(value['value'])-32) * 5.0 / 9.0)
            else:
                self.char_TargetTemperature.set_value(value['value'])
        except:
            self.log.error('!! error setting upperSetpoint', exc_info=True)

    def prop_thermostatMode(self, value):
        try:
            modes={"AUTO": 3, "COOL": 2, "HEAT": 1, "OFF": 0 }
            self.char_TargetHeatingCoolingState.set_value(modes[value])
            if value=='AUTO': 
                self.char_CurrentHeatingCoolingState.set_value(2)
            else:
                self.char_CurrentHeatingCoolingState.set_value(modes[value])
        except:
            self.log.error('!! error setting thermostatMode', exc_info=True)


            
class ContactSensor(SofaAccessory):

    category = pyhap.const.CATEGORY_SENSOR

    def add_chars(self):
        try:
            serv_temp = self.add_preload_service('ContactSensor')
            self.char_state = serv_temp.configure_char('ContactSensorState')
        except:
            self.log.error("!! error adding characteristics", exc_info=True)  

    def prop_detectionState(self, value):
        try:
            if value=='DETECTED':
                self.char_state.set_value(1)
            else:
                self.char_state.set_value(0)
        except:
            self.log.error('!! error setting detectionState', exc_info=True)



class Doorbell(SofaAccessory):

    category = pyhap.const.CATEGORY_OTHER

    def add_chars(self):
        try:
            serv_Doorbell = self.add_preload_service('Doorbell')
            self.pse_state = serv_Doorbell.configure_char('ProgrammableSwitchEvent')
        except:
            self.log.error("!! error adding characteristics", exc_info=True)  

  
class Speaker(SofaAccessory):

    #category = pyhap.const.CATEGORY_SPEAKER

    def add_chars(self):
        try:
            serv_speaker = self.add_preload_service('Speaker', chars=["Name", "Volume", "Mute"])
            self.char_mute = serv_speaker.configure_char('Mute', setter_callback=self.set_Mute)
            self.char_volume = serv_speaker.configure_char("Volume", setter_callback = self.set_Volume)
        except:
            self.log.error("!! error adding characteristics", exc_info=True)  

    def set_Volume(self, value):
        
        try:
            asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.SpeakerController', "SetVolume", {'volume': int(value)}), loop=self.loop)
        except:
            self.log.error('!! Error in set_volume', exc_info=True)

    def set_Mute(self, value):
        try:
            asyncio.run_coroutine_threadsafe(self.sendDirective('Alexa.SpeakerController', "SetMute", {'mute': value }), loop=self.loop)
        except:
            self.log.error('!! Error in set_mute', exc_info=True)


class homekit(sofabase):

    class adapterProcess(SofaCollector.collectorAdapter):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, executor=None,  **kwargs):
            self.dataset=dataset
            self.log=log
            self.notify=notify
            self.polltime=5
            self.maxaid=8
            self.persistfile=self.dataset.config['pickle_file']
            self.accessorymap=self.dataset.config['accessory_map']
            self.executor=executor
            self.skip=['savedState', 'colorTemperatureInKelvin', 'pressState', 'onLevel', 'powerLevel', 'input']
            
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            self.addExtraLogs()


        async def start(self):
            
            try:
                self.log.info('Starting homekit')
                await self.dataset.ingest({'accessorymap': self.loadJSON(self.dataset.config['accessory_map'])})
                #self.log.info('Known devices: %s' % self.dataset.nativeDevices['accessorymap'])
                self.getNewAid()
                self.accloop=asyncio.new_event_loop()
                self.driver = AccessoryDriver(port=self.dataset.config['accessory_port'], persist_file='/opt/sofa-server/config/accessory.state', pincode=self.dataset.config['pin_code'].encode('utf-8'))

                self.buildBridge()
                self.driver.add_accessory(accessory=self.bridge)
                await self.saveAidMap()
                self.log.info('PIN: %s' % self.driver.state.pincode)
                signal.signal(signal.SIGTERM, self.driver.signal_handler)
                self.executor.submit(self.driver.start)
                self.log.info('Accessory Bridge Driver started')
            except:
                self.log.error('Error during startup', exc_info=True)
                
        async def stop(self):
            
            try:
                self.log.info('Stopping Accessory Bridge Driver')
                self.driver.stop()
            except:
                self.log.error('Error stopping Accessory Bridge Driver', exc_info=True)
        
        def service_stop(self):
            
            try:
                self.log.info('!. Stopping Accessory Bridge Driver')
                self.driver.stop()
            except:
                self.log.error('!! Error stopping Accessory Bridge Driver', exc_info=True)

 
        def buildBridge(self):
            
            try:
                self.bridge = Bridge(self.driver, 'Bridge')
                for devname in self.dataset.nativeDevices['accessorymap']:
                    newdev=None
                    device=None
                    accitem=self.dataset.nativeDevices['accessorymap'][devname]
                    if 'device' in accitem:
                        device=accitem['device']
                    
                    props={}
                    chars={}
                    if 'props' in accitem:
                        props=accitem['props']

                    if 'chars' in device:
                        chars=accitem['chars']

                    if accitem['services'][0]=='Lightbulb':
                        newdev=LightBulb(self.driver, device, adapter=self, aid=accitem['id'], props=props, chars=chars)
                    elif accitem['services'][0]=='TemperatureSensor':
                        newdev=TemperatureSensor(self.driver, device, adapter=self, aid=accitem['id'], props=props, chars=chars)
                    elif accitem['services'][0]=='Thermostat':
                        newdev=Thermostat(self.driver, device, adapter=self, aid=accitem['id'], props=props, chars=chars)
                    elif accitem['services'][0]=='ContactSensor':
                        newdev=ContactSensor(self.driver, device, adapter=self, aid=accitem['id'], props=props, chars=chars)
                    elif accitem['services'][0]=='Doorbell':
                        newdev=Doorbell(self.driver, device, adapter=self, aid=accitem['id'], props=props, chars=chars)
                    elif accitem['services'][0]=='Switch':
                        newdev=Switch(self.driver, device, adapter=self, aid=accitem['id'], props=props, chars=chars)
                    elif accitem['services'][0]=='Television':
                        newdev=Television(self.driver, device, adapter=self, aid=accitem['id'], props=props, chars=chars)
                    elif accitem['services'][0]=='Speaker':
                        pass
                        # Speakers are not really supported at this point
                        #newdev=Speaker(self.driver, device, adapter=self, aid=device['id'], props=props, chars=chars)
                        
                    if newdev:
                        self.bridge.add_accessory(newdev)
                        self.log.info('Added accessory: %s %s' % (accitem['services'][0], newdev))
                    else:
                        self.log.info('.! Did not add bridge device %s' % accitem)
            except:
                self.log.error('Error during bridge building', exc_info=True)

        def getNewAid(self):
            
            try:
                self.maxaid=self.maxaid+1
                for dev in self.dataset.nativeDevices['accessorymap']:
                    if 'id' not in self.dataset.nativeDevices['accessorymap'][dev]:
                        self.dataset.nativeDevices['accessorymap'][dev]={'id': self.dataset.nativeDevices['accessorymap'][dev] }
                    if self.dataset.nativeDevices['accessorymap'][dev]['id']>=self.maxaid:
                        self.maxaid=self.dataset.nativeDevices['accessorymap'][dev]['id']+1
                return self.maxaid
            except:
                self.log.error('Error during getMaxAid', exc_info=True)
                return None
                
                    
                
        def getAccessorySet(self):
            
            try:
                self.log.info('Loading persistence file if it exists')
                self.loadFromPersist(self.persistfile)
                self.acc=None
        
                if not self.acc:
                    self.log.info('No persistence file, creating Bridge instance')
                    address = ("", self.dataset.config['bridge_port'])
                    #self.acc = Bridge(address=address, display_name=self.dataset.config['display_name'], pincode=self.dataset.config['pin_code'])
                    self.acc = Bridge(address=address, display_name=self.dataset.config['display_name'])

                else:
                    self.log.info('Loaded persistence file')
            except:
                self.log.error('Error accessory startup Data', exc_info=True)


        async def saveAidMap(self):
            
            try:
                accmap={}
                #self.log.info('Bridge Acc: %s' % self.bridge.accessories)
                for acc in self.bridge.accessories:
                    svcs=[]
                    chars=[]
                    props={}
                    for svc in self.bridge.accessories[acc].services:
                        if svc.display_name not in ['AccessoryInformation']:
                            svcs.append(svc.display_name)
                            for char in svc.characteristics:
                                chars.append(char.display_name)
                                props[char.display_name]=char.properties
                    try:    
                        accmap[self.bridge.accessories[acc].display_name]={'id': acc, 'services': svcs, 'chars': chars, 'props':props, 'device':self.bridge.accessories[acc].device }
                    except:
                        self.log.info('TS', exc_info=True)
                #self.log.info('am: %s' % accmap)
                await self.dataset.ingest({"accessorymap": accmap})
                self.saveJSON(self.dataset.config['accessory_map'], accmap)
            except:
                self.log.error('Error in virt aid', exc_info=True)
                
        async def virtualAddDevice(self, devname, device):
        
            try:
                if device['displayCategories'][0] not in ['DEVICE', 'TEMPERATURE_SENSOR', 'THERMOSTAT', 'LIGHT', 'CONTACT_SENSOR', 'TV']:
                    return False
                    
                if device['friendlyName'] in self.dataset.nativeDevices['accessorymap']:
                    if self.dataset.nativeDevices['accessorymap'][device['friendlyName']]['device']['endpointId']!=device['endpointId']:
                        self.log.info('Fixing changed endpointId for %s from %s to %s' % (device['friendlyName'], self.dataset.nativeDevices['accessorymap'][device['friendlyName']]['endpointId'], device['endpointId']))
                        self.dataset.nativeDevices['accessorymap'][device['friendlyName']]['device']=device                 
                        self.saveJSON(self.dataset.config['accessory_map'], self.dataset.nativeDevices['accessorymap'])
                    response=await self.dataset.requestReportState(device['endpointId'])
                    #self.log.info('Already know about: %s' % device['friendlyName'])
                    return True
                else: 
                    self.log.info('%s not in %s' % (device['friendlyName'], self.dataset.nativeDevices['accessorymap'].keys()))
                    
                newdev=None
                aid=None
                aid=self.getNewAid()
                    
                if aid==None:
                    self.log.error('Error - could not get aid for device')
                    return False
                
                props={}
                if device['displayCategories'][0]=='THERMOSTAT':
                    try:
                        for cap in device['Capabilities']:
                            if cap['interface']=='Alexa.ThermostatController':
                                if 'configuration' in cap:
                                    if 'supportedRange' in cap['configuration']:
                                        props['minValue']=(int(cap['configuration']['supportedRange'][0])-32) * 5.0 / 9.0
                                        props['maxValue']=(int(cap['configuration']['supportedRange'][1])-32) * 5.0 / 9.0
                    except KeyError:
                        self.log.warn('!. %s does not have Capabilities: %s' % (device['friendlyName'], device))
                    except:
                        self.log.error('Error getting props', exc_info=True)
                    newdev=Thermostat(self.driver, device, adapter=self, aid=aid, props=props)
                elif device['displayCategories'][0]=='TEMPERATURE_SENSOR':
                    newdev=TemperatureSensor(self.driver, device, adapter=self, aid=aid, props=props)
                elif device['displayCategories'][0]=='LIGHT':
                    newdev=LightBulb(self.driver, device, adapter=self, aid=aid)

                elif device['displayCategories'][0]=='CONTACT_SENSOR':
                    newdev=ContactSensor(self.driver, device, adapter=self, aid=aid, props=props)

                elif device['displayCategories'][0]=='RECEIVER':
                    # not supported at this time in the Home app
                    #newdev=Speaker(self.driver, device, adapter=self, aid=aid, props=props)
                    pass

                elif device['displayCategories'][0]=='DOORBELL':
                    newdev=Doorbell(self.driver, device, adapter=self, aid=aid, props=props)

                elif device['displayCategories'][0]=='DEVICE':
                    newdev=Switch(self.driver, device, adapter=self, aid=aid, props=props)

                elif device['displayCategories'][0]=='TV':
                    newdev=Television(self.driver, device, adapter=self, aid=aid, props=props)

                if newdev:
                    self.log.info('++ New Homekit Device: %s - %s %s' % (aid, device['friendlyName'], device))
                    self.bridge.add_accessory(newdev)
                    response=await self.dataset.requestReportState(device['endpointId'])
                    await self.saveAidMap()
                    #self.driver.config_changed()
            except:
                self.log.error('Error in virt add', exc_info=True)
 
    

        def addExtraLogs(self):
            
            pass
        
            #self.accessory_logger = logging.getLogger('pyhap.accessory_driver')
            #self.accessory_logger.addHandler(self.log.handlers[0])
            #self.accessory_logger.setLevel(logging.DEBUG)
        
            #self.accessory_driver_logger = logging.getLogger('pyhap.accessory_driver')
            #self.accessory_driver_logger.addHandler(self.log.handlers[0])
            #self.accessory_driver_logger.setLevel(logging.DEBUG)

            #self.hap_server_logger = logging.getLogger('pyhap.hap_server')
            #self.hap_server_logger.addHandler(self.log.handlers[0])
            #self.hap_server_logger.setLevel(logging.DEBUG)
        
            #self.log.setLevel(logging.DEBUG)        


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
         
         
        async def updateAccessoryMap(self, adapter, objlist):
            
            for accid, acc in self.acc.accessories:
                self.dataset.ingest({"accessorymap": { acc.display_name : { "id":accid, "path": objlist}}})
             
        async def virtualEventHandler(self, event, source, deviceId, message):
            
            try:
                if event=='DoorbellPress':
                    self.log.info('Doorbell Press: %s %s' % (deviceId, message))
                    acc=self.getAccessoryFromEndpointId(deviceId)
                    if not acc:
                        return None
                    acc.pse_state.set_value(0)

                else:
                    self.log.info('Unknown event: %s %s %s' % (event, deviceId, message))
            except:
                self.log.error('Error in virtual event handler: %s %s %s' % (event, deviceId, message), exc_info=True)
             

        async def virtualChangeHandler(self, deviceId, prop):
            
            try:
                acc=self.getAccessoryFromEndpointId(deviceId)
                if not acc or prop['name'] in self.skip:
                    return None
                
                try:
                    getattr(acc, 'prop_%s' % prop['name'])(prop['value'])
                except AttributeError:
                    self.log.info('.. No property setter for %s on %s' % (prop['name'], deviceId))
                except:
                    self.log.error('Error getting property setter: %s %s' % (prop['name'], deviceId), exc_info=True)

            except:
                self.log.error('Error in virtual change handler: %s %s' % (deviceId, change), exc_info=True)


        async def handleStateReport(self, message):
            
            try:
                deviceId=message['event']['endpoint']['endpointId']
                acc=self.getAccessoryFromEndpointId(deviceId)
                if not acc:
                    return None
                for prop in message['context']['properties']:
                    if prop['name'] in self.skip:
                        continue
                    try:
                        getattr(acc, 'prop_%s' % prop['name'])(prop['value'])
                    except AttributeError:
                        self.log.info('.. No property setter for %s on %s' % (prop['name'], deviceId))
                    except:
                        self.log.error('Error getting property setter: %s %s' % (prop['name'], deviceId), exc_info=True)
            except:
                self.log.error('Error in virtual state report handler: %s %s ' % (message, acc), exc_info=True)

        def getAccessoryFromEndpointId(self, endpointId):
            try:
                for dev in self.dataset.devices:
                    if self.dataset.devices[dev]['endpointId']==endpointId:
                        thisfn=self.dataset.devices[dev]['friendlyName']
                        for acc in self.bridge.accessories:
                            if self.bridge.accessories[acc].display_name==thisfn:
                                #self.log.info('Acc: %s' % self.bridge.accessories[acc])
                                return self.bridge.accessories[acc]
                        #thisdev=self.dataset.data['accessorymap'][thisfn]
                        #thisacc=self.acc.accessories[thisdev]
                        #return thisdev
                return None
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
                    # has to be in celsius
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
    adapter=homekit(name='homekit')
    adapter.start()
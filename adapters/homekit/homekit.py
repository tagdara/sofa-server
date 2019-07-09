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
    
    async def convertAccessoryCommand(self, data):
            
        try:
            #device=self.dataset.data['devices'][data['name']]

            command={"directive": {
                            "endpoint": {
                                "scope": {"type": "BearerToken"}, 
                                "endpointId": data['endpointId'],
                                "cookie": {}
                            },
                            'header': {
                                'messageId': str(uuid.uuid1()),
                                'correlationToken': str(uuid.uuid1()),
                                'payloadVersion': '3',
                            }, 
                            'payload': {}
                        }
            }

            if data['characteristic']=='On':
                command['directive']['header']['namespace']='Alexa.PowerController'
                if data['value']:
                    command['directive']['header']['name']="TurnOn"
                else:
                    command['directive']['header']['name']="TurnOff"

            elif data['characteristic']=='Brightness':
                command['directive']['header']['namespace']='Alexa.BrightnessController'
                command['directive']['header']['name']="SetBrightness"
                command['directive']['payload']={'brightness': int(data['value'])}

            elif data['characteristic']=='Hue':
                command['directive']['header']['namespace']='Alexa.ColorController'
                command['directive']['header']['name']="SetColor"
                command['directive']['payload']={'color': data['value'] }

            elif data['characteristic']=='Saturation':
                command['directive']['header']['namespace']='Alexa.ColorController'
                command['directive']['header']['name']="SetColor"
                command['directive']['payload']={'color': data['value'] }

            elif data['characteristic']=='Volume':
                command['directive']['header']['namespace']='Alexa.SpeakerController'
                command['directive']['header']['name']="SetVolume"
                command['directive']['payload']={'volume': int(data['value'])}

            elif data['characteristic']=='TargetHeatingCoolingState':
                command['directive']['header']['namespace']='Alexa.ThermostatController'
                command['directive']['header']['name']="SetThermostatMode"
                vals=['OFF','HEAT']
                command['directive']['payload']={'thermostatMode': {'value': vals[data['value']]}}

            elif data['characteristic']=='CurrentHeatingCoolingState':
                command['directive']['header']['namespace']='Alexa.ThermostatController'
                command['directive']['header']['name']="SetThermostatMode"
                vals=['OFF','HEAT']
                command['directive']['payload']={'thermostatMode': {'value': vals[data['value']]}}


            elif data['characteristic']=='Temperature':
                command['directive']['header']['namespace']='Alexa.ThermostatController'
                command['directive']['header']['name']="SetTargetSetpoint"
                command['directive']['payload']={'temperature': vals[data['value']]}

                
            return command
                
        except:
            self.log.error('Error converting command: %s' % data, exc_info=True)


    async def sendCommand(self, data):
            
        try:
            command=await self.convertAccessoryCommand(data)
            headers = { "Content-type": "text/xml" }
            async with aiohttp.ClientSession() as client:
                response=await client.post(self.adapterUrl, data=json.dumps(command), headers=headers)
                result=await response.read()
                return result
        except:
            self.log.error("send command error",exc_info=True)      
            return {}




class LightBulb(SofaAccessory):

    category = pyhap.const.CATEGORY_LIGHTBULB
    
    def __init__(self, *args, endpointId=None, adapterUrl='', loop=None, color=False, **kwargs):
        
        self.event_loop=loop
        self.endpointId=endpointId
        self.adapterUrl=adapterUrl
        self.color=color
        self.log = logging.getLogger('homekit')
        super().__init__(*args, **kwargs)
        if self.color:
            serv_light = self.add_preload_service('Lightbulb',chars=["Name", "On", "Brightness", "Hue", "Saturation"])
            self.char_hue=serv_light.configure_char('Hue', setter_callback = self.set_Hue)
            self.char_sat=serv_light.configure_char('Saturation', setter_callback = self.set_Saturation)
        else:
            serv_light = self.add_preload_service('Lightbulb',chars=["Name", "On", "Brightness"])
        self.char_on = serv_light.configure_char('On', setter_callback=self.set_On)
        self.char_brightness = serv_light.configure_char("Brightness", setter_callback = self.set_Brightness)
        self.reachable=True


    def __setstate__(self, state):
        self.__dict__.update(state)


    def set_On(self, value):
        
        try:
            self.log.info('Sending OnOff command: %s' % {"id":self.aid, "name":self.display_name, "characteristic":"On", "value":value} )
            asyncio.run_coroutine_threadsafe(self.sendCommand({"endpointId":self.endpointId, "name":self.display_name, "characteristic":"On", "value":value}), loop=self.event_loop)

        except:
            self.log.error('Error in setbulb', exc_info=True)
            self.log.error(self.__dict__)


    def set_Brightness(self, value):
        
        try:
            asyncio.run_coroutine_threadsafe(self.sendCommand({"endpointId":self.endpointId, "name":self.display_name, "characteristic":"Brightness", "value":value}), loop=self.event_loop)
            #asyncio.run_coroutine_threadsafe(self.sendCommand({"id":self.aid, "name":self.display_name, "characteristic":"Brightness", "value":value}), loop=self.event_loop)
        except:
            self.log.error('Error in setbright', exc_info=True)

    def set_Hue(self, value):
        
        try:
            colorval={"hue": self.char_hue.value, "saturation": self.char_sat.value/100, "brightness": self.char_brightness.value/100}
            asyncio.run_coroutine_threadsafe(self.sendCommand({"endpointId":self.endpointId, "name":self.display_name, "characteristic":"Hue", "value":colorval}), loop=self.event_loop)
        except:
            self.log.error('Error in set hue', exc_info=True)

    def set_Saturation(self, value):
        
        try:
            colorval={"hue": self.char_hue.value, "saturation": self.char_sat.value/100, "brightness": self.char_brightness.value/100}
            asyncio.run_coroutine_threadsafe(self.sendCommand({"endpointId":self.endpointId, "name":self.display_name, "characteristic":"Hue", "value":colorval}), loop=self.event_loop)
        except:
            self.log.error('Error in set sat', exc_info=True)



    async def stop(self):
        await super(LightBulb, self).stop()

class Switch(SofaAccessory):

    category = pyhap.const.CATEGORY_SWITCH
    
    def __init__(self, *args, endpointId=None, adapterUrl='', loop=None, **kwargs):
        
        self.event_loop=loop
        self.endpointId=endpointId
        self.adapterUrl=adapterUrl
        self.log = logging.getLogger('homekit')
        super().__init__(*args, **kwargs)
        serv_switch = self.add_preload_service('Switch')
        self.char_on = serv_switch.configure_char('On', setter_callback=self.set_On)
        self.reachable=True

    def __setstate__(self, state):
        self.__dict__.update(state)


    def set_On(self, value):
        
        try:
            self.log.info('Sending OnOff command: %s' % {"id":self.aid, "name":self.display_name, "characteristic":"On", "value":value} )
            asyncio.run_coroutine_threadsafe(self.sendCommand({"endpointId":self.endpointId, "name":self.display_name, "characteristic":"On", "value":value}), loop=self.event_loop)

        except:
            self.log.error('Error in set on', exc_info=True)
            self.log.error(self.__dict__)


    async def stop(self):
        await super(Switch, self).stop()

class TemperatureSensor(SofaAccessory):

    category = pyhap.const.CATEGORY_SENSOR

    def __init__(self, *args, endpointId=None, adapterUrl='', loop=None, **kwargs):
        
        self.event_loop=loop
        self.endpointId=endpointId
        self.adapterUrl=adapterUrl
        self.log = logging.getLogger('homekit')     
        super().__init__(*args, **kwargs)
        serv_temp = self.add_preload_service('TemperatureSensor')
        #self.char_temp = serv_temp.configure_char('CurrentTemperature', setter_callback = self.set_Temperature)
        self.char_temp = serv_temp.configure_char('CurrentTemperature')

    def run(self):
        pass
    
class Thermostat(SofaAccessory):

    category = pyhap.const.CATEGORY_THERMOSTAT

    def __init__(self, *args, endpointId=None, adapterUrl='', loop=None, **kwargs):
        
        self.event_loop=loop
        self.endpointId=endpointId
        self.adapterUrl=adapterUrl
        self.log = logging.getLogger('homekit')     
        super().__init__(*args, **kwargs)
        serv_temp = self.add_preload_service('Thermostat')
        #chars=['Name', 'CurrentTemperature', 'TargetTemperature', 'TargetHeatingCoolingState', 'CurrentHeatingCoolingState'])

        #self.char_temp = serv_temp.configure_char('CurrentTemperature', setter_callback = self.set_Temperature)
        self.char_temp = serv_temp.configure_char('CurrentTemperature')
        self.char_TargetHeatingCoolingState = serv_temp.configure_char('TargetHeatingCoolingState',setter_callback=self.set_TargetHeatingCoolingState)
        self.char_CurrentHeatingCoolingState = serv_temp.configure_char('CurrentHeatingCoolingState',setter_callback=self.set_CurrentHeatingCoolingState)

        self.char_TargetTemperature = serv_temp.configure_char('TargetTemperature', setter_callback=self.set_TargetTemperature)

    def __setstate__(self, state):
        self.__dict__.update(state)

    def set_TargetTemperature(self, value):
        
        try:
            self.log.info('Sending thermostat temperature command: %s' % {"id":self.aid, "name":self.display_name, "characteristic":"TargetTemperature", "value":value} )
            asyncio.run_coroutine_threadsafe(self.sendCommand({"endpointId":self.endpointId, "name":self.display_name, "characteristic":"TargetTemperature", "value":value}), loop=self.event_loop)

        except:
            self.log.error('Error in set target temp', exc_info=True)
            self.log.error(self.__dict__)

    def set_TargetHeatingCoolingState(self, value):
        
        try:
            self.log.info('Sending thermostat mode command: %s' % {"id":self.aid, "name":self.display_name, "characteristic":"TargetHeatingCoolingState", "value":value} )
            asyncio.run_coroutine_threadsafe(self.sendCommand({"endpointId":self.endpointId, "name":self.display_name, "characteristic":"TargetHeatingCoolingState", "value":value}), loop=self.event_loop)

        except:
            self.log.error('Error in set thermostate mode', exc_info=True)
            self.log.error(self.__dict__)

    def set_CurrentHeatingCoolingState(self, value):
        
        try:
            self.log.info('Sending thermostat mode command: %s' % {"id":self.aid, "name":self.display_name, "characteristic":"CurrentHeatingCoolingState", "value":value} )
            asyncio.run_coroutine_threadsafe(self.sendCommand({"endpointId":self.endpointId, "name":self.display_name, "characteristic":"CurrentHeatingCoolingState", "value":value}), loop=self.event_loop)

        except:
            self.log.error('Error in set thermostate mode', exc_info=True)
            self.log.error(self.__dict__)

    def run(self):
        pass

class ContactSensor(SofaAccessory):

    category = pyhap.const.CATEGORY_SENSOR

    def __init__(self, *args, endpointId=None, adapterUrl='', loop=None, **kwargs):
        
        self.event_loop=loop
        self.endpointId=endpointId
        self.adapterUrl=adapterUrl
        self.log = logging.getLogger('homekit')     
        super().__init__(*args, **kwargs)
        serv_temp = self.add_preload_service('ContactSensor')
        self.char_state = serv_temp.configure_char('ContactSensorState')

    def run(self):
        pass

class Doorbell(SofaAccessory):

    category = pyhap.const.CATEGORY_OTHER

    def __init__(self, *args, endpointId=None, adapterUrl='', loop=None, **kwargs):
        
        self.event_loop=loop
        self.endpointId=endpointId
        self.adapterUrl=adapterUrl
        self.log = logging.getLogger('homekit')     
        super().__init__(*args, **kwargs)
        serv_temp = self.add_preload_service('Doorbell')
        self.pse_state = serv_temp.configure_char('ProgrammableSwitchEvent')

    def run(self):
        pass

  
class Speaker(SofaAccessory):

    #category = pyhap.const.CATEGORY_SPEAKER

    def __init__(self, *args, endpointId=None, adapterUrl='', loop=None, **kwargs):

        self.event_loop=loop
        self.endpointId=endpointId
        self.adapterUrl=adapterUrl
        self.log = logging.getLogger('homekit')     
        super().__init__(*args, **kwargs)
        serv_speaker = self.add_preload_service('Speaker', chars=["Name", "Volume", "Mute"])
        #self.char_temp = serv_temp.configure_char('CurrentTemperature', setter_callback = self.set_Temperature)
        self.char_mute = serv_speaker.configure_char('Mute', setter_callback=self.set_Mute)
        self.char_volume = serv_speaker.configure_char("Volume", setter_callback = self.set_Volume)

    def __getstate__(self):

        state = dict(super(Speaker, self).__getstate__())
        return state

    def run(self):
        pass

    def set_Volume(self, value):
        
        try:
            asyncio.run_coroutine_threadsafe(self.sendCommand({"endpointId":self.endpointId, "name":self.display_name, "characteristic":"Volume", "value":value}), loop=self.event_loop)
            #asyncio.run_coroutine_threadsafe(self.sendCommand({"id":self.aid, "name":self.display_name, "characteristic":"Brightness", "value":value}), loop=self.event_loop)
        except:
            self.log.error('Error in setvol', exc_info=True)

    def set_Mute(self, value):
        
        try:
            self.log.info('Sending Mute command: %s' % {"id":self.aid, "name":self.display_name, "characteristic":"Mute", "value":value} )
            asyncio.run_coroutine_threadsafe(self.sendCommand({"endpointId":self.endpointId, "name":self.display_name, "characteristic":"Mute", "value":value}), loop=self.event_loop)

        except:
            self.log.error('Error in setmute', exc_info=True)
            self.log.error(self.__dict__)



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

 
        def buildBridge(self):
            
            try:
                self.bridge = Bridge(self.driver, 'Bridge')
                for devname in self.dataset.nativeDevices['accessorymap']:
                    newdev=None
                    dev=self.dataset.nativeDevices['accessorymap'][devname]
                    if dev['services'][0]=='Lightbulb':
                        if 'color' in dev:
                            newdev=LightBulb(self.driver, devname, endpointId=dev['endpointId'], adapterUrl=dev['adapterUrl'], loop=self.loop, color=dev['color'], aid=dev['id'])
                        else:
                            newdev=LightBulb(self.driver, devname, endpointId=dev['endpointId'], adapterUrl=dev['adapterUrl'], loop=self.loop, aid=dev['id'])
                            
                        self.bridge.add_accessory(newdev)
                    elif dev['services'][0]=='TemperatureSensor':
                        newdev=TemperatureSensor(self.driver, devname, endpointId=dev['endpointId'], adapterUrl=dev['adapterUrl'], loop=self.loop, aid=dev['id'])
                        self.bridge.add_accessory(newdev)
                    elif dev['services'][0]=='Thermostat':
                        newdev=Thermostat(self.driver, devname, endpointId=dev['endpointId'], adapterUrl=dev['adapterUrl'], loop=self.loop, aid=dev['id'])
                        self.bridge.add_accessory(newdev)

                    elif dev['services'][0]=='ContactSensor':
                        newdev=ContactSensor(self.driver, devname, endpointId=dev['endpointId'], adapterUrl=dev['adapterUrl'], loop=self.loop, aid=dev['id'])
                        self.bridge.add_accessory(newdev)
                    elif dev['services'][0]=='Doorbell':
                        newdev=Doorbell(self.driver, devname, endpointId=dev['endpointId'], adapterUrl=dev['adapterUrl'], loop=self.loop, aid=dev['id'])
                        self.bridge.add_accessory(newdev)
                    elif dev['services'][0]=='Switch':
                        newdev=Switch(self.driver, devname, endpointId=dev['endpointId'], adapterUrl=dev['adapterUrl'], loop=self.loop, aid=dev['id'])
                        self.bridge.add_accessory(newdev)

                        
                    # Speakers are not really supported at this point
                    #elif dev['services'][0]=='Speaker':
                    #    newdev=Speaker(self.driver, devname, endpointId=dev['endpointId'], adapterUrl=dev['adapterUrl'], loop=self.loop, aid=dev['id'])
                    #    self.bridge.add_accessory(newdev)

                    else:
                        self.log.info('XXXXX Did not add %s' % dev)
                        
                    if newdev:
                        self.log.info('Added accessory: %s %s' % (dev['services'][0], newdev))
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
                    for svc in self.bridge.accessories[acc].services:
                        if svc.display_name not in ['AccessoryInformation']:
                            svcs.append(svc.display_name)
                    try:    
                        accmap[self.bridge.accessories[acc].display_name]={'id': acc, 'services': svcs, 'adapterUrl': self.bridge.accessories[acc].adapterUrl, 'endpointId':self.bridge.accessories[acc].endpointId }
                    except:
                        self.log.info('TS')
                #self.log.info('am: %s' % accmap)
                await self.dataset.ingest({"accessorymap": accmap})
                self.saveJSON(self.dataset.config['accessory_map'], accmap)
            except:
                self.log.error('Error in virt aid', exc_info=True)
                

        async def virtualAddDevice(self, devname, device):
        
            try:
                if device['displayCategories'][0] not in ['DEVICE', 'TEMPERATURE_SENSOR', 'THERMOSTAT', 'LIGHT', 'CONTACT_SENSOR', 'DOORBELL']:
                    return False
                
                if device['friendlyName'] in self.dataset.nativeDevices['accessorymap']:
                    if self.dataset.nativeDevices['accessorymap'][device['friendlyName']]['endpointId']!=device['endpointId']:
                        self.log.info('Fixing changed endpointId for %s from %s to %s' % (device['friendlyName'], self.dataset.nativeDevices['accessorymap'][device['friendlyName']]['endpointId'], device['endpointId']))
                        self.dataset.nativeDevices['accessorymap'][device['friendlyName']]['endpointId']=device['endpointId']                        
                        self.saveJSON(self.dataset.config['accessory_map'], self.dataset.nativeDevices['accessorymap'])
                    response=await self.dataset.requestReportState(device['endpointId'])
                    #self.log.info('Already know about: %s' % device['friendlyName'])
                    return True
                else: 
                    self.log.info('%s not in %s' % (device['friendlyName'], self.dataset.nativeDevices['accessorymap'].keys()))
                    
                newdev=None
                aid=None
                devicename=device['friendlyName']
                endpointId=device['endpointId']
                adapter=endpointId.split(':')[0]
                adapterUrl=self.dataset.adapters[adapter]['url']
                
                aid=self.getNewAid()
                    
                if aid==None:
                    self.log.error('Error - could not get aid for device')
                    return False

                if device['displayCategories'][0]=='THERMOSTAT':
                    newdev=Thermostat(self.driver, devicename, endpointId=endpointId, adapterUrl=adapterUrl, loop=self.loop, aid=aid)

                elif device['displayCategories'][0]=='TEMPERATURE_SENSOR':
                    newdev=TemperatureSensor(self.driver, devicename, endpointId=endpointId, adapterUrl=adapterUrl, loop=self.loop, aid=aid)

                elif device['displayCategories'][0]=='LIGHT':
                    self.log.info('Light: %s' % device)
                    newdev=LightBulb(self.driver, devicename, endpointId=endpointId, adapterUrl=adapterUrl, loop=self.loop, aid=aid, color=False)

                elif device['displayCategories'][0]=='CONTACT_SENSOR':
                    newdev=ContactSensor(self.driver, devicename, endpointId=endpointId, adapterUrl=adapterUrl, loop=self.loop, aid=aid)

                elif device['displayCategories'][0]=='RECEIVER':
                    newdev=Speaker(self.driver, devicename, endpointId=endpointId, adapterUrl=adapterUrl, loop=self.loop, aid=aid)

                elif device['displayCategories'][0]=='DOORBELL':
                    newdev=Doorbell(self.driver, devicename, endpointId=endpointId, adapterUrl=adapterUrl, loop=self.loop, aid=aid)

                elif device['displayCategories'][0]=='DEVICE':
                    newdev=Switch(self.driver, devicename, endpointId=endpointId, adapterUrl=adapterUrl, loop=self.loop, aid=aid)


                if newdev:
                    self.log.info('++ New Homekit Device: %s - %s %s' % (aid, devicename, device))
                    self.bridge.add_accessory(newdev)
                    response=await self.dataset.requestReportState(endpointId)
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
                if not acc:
                    return None

                #self.log.info('.. Changed %s/%s %s = %s' % (deviceId, prop['namespace'], prop['name'], prop['value']))
                if prop['name']=='brightness':
                    if acc.reachable:
                    #self.setCharacteristic(thisaid, 'Lightbulb', 'Brightness', prop['value'])
                        acc.char_brightness.set_value(prop['value'])
                    else:
                        acc.char_brightness.set_value(0)
                    #acc.char_temp.set_value(prop['value']['value'])
                elif prop['name']=='volume':
                    #self.setCharacteristic(thisaid, 'Lightbulb', 'Brightness', prop['value'])
                    acc.char_volume.set_value(prop['value'])
                    #acc.char_temp.set_value(prop['value']['value'])

                elif prop['name']=='detectionState':
                    #self.setCharacteristic(thisaid, 'Lightbulb', 'Brightness', prop['value'])
                    if prop['value']=='DETECTED':
                        acc.char_state.set_value(1)
                    else:
                        acc.char_state.set_value(0)
                        
                elif prop['name']=='connectivity':
                    if prop['value']['value']=='UNREACHABLE':
                        acc.reachable=False
                        acc.char_on.set_value(False)
                    else:
                        acc.reachable=True

                elif prop['name']=='powerState':
                    if prop['value']=='ON':
                        if acc.reachable:
                            acc.char_on.set_value(True)
                        else:
                            acc.char_on.set_value(False)
                        #self.setCharacteristic(thisaid, 'Lightbulb', 'On', True)
                    elif prop['value']=='OFF':
                        acc.char_on.set_value(False)
                        #self.setCharacteristic(thisaid, 'Lightbulb', 'On', False)
                elif prop['name']=='temperature':
                    #self.setCharacteristic(thisaid, 'TemperatureSensor', 'CurrentTemperature', prop['value'])
                    if prop['value']['scale']=='FAHRENHEIT':
                        acc.char_temp.set_value((int(prop['value']['value'])-32) * 5.0 / 9.0)
                    else:
                        acc.char_temp.set_value(prop['value']['value'])
                        
                elif prop['name']=='targetSetpoint' or prop['name']=='upperSetpoint':
                    #self.setCharacteristic(thisaid, 'TemperatureSensor', 'CurrentTemperature', prop['value'])
                    if prop['value']['scale']=='FAHRENHEIT':
                        acc.char_temp.set_value((int(prop['value']['value'])-32) * 5.0 / 9.0)
                    else:
                        acc.char_temp.set_value(prop['value']['value'])

                elif prop['name']=='thermostatMode':
                    modes={"AUTO": 3, "COOL": 2, "HEAT": 1, "OFF": 0 }
                    acc.char_TargetHeatingCoolingState.set_value(modes[prop['value']])
                    if prop['value']=='AUTO': 
                        acc.char_CurrentHeatingCoolingState.set_value(2)
                    else:
                        acc.char_CurrentHeatingCoolingState.set_value(modes[prop['value']])
                
            except:
                self.log.error('Error in virtual change handler: %s %s' % (deviceId, change), exc_info=True)


        async def handleStateReport(self, message):
            #thisaid=self.getAccessoryFromEndpointId(message['event']['endpoint']['endpointId'])
            deviceId=message['event']['endpoint']['endpointId']
            acc=self.getAccessoryFromEndpointId(deviceId)
            
            if not acc:
                return None
                
            for prop in message['context']['properties']:
                #self.log.info('Property: %s %s = %s' % (prop['namespace'], prop['name'], prop['value']))
                if prop['name']=='brightness':
                    #self.setCharacteristic(thisaid, 'Lightbulb', 'Brightness', prop['value'])
                    acc.char_brightness.set_value(prop['value'])
                    #acc.char_temp.set_value(prop['value']['value'])
                elif prop['name']=='volume':
                    #self.setCharacteristic(thisaid, 'Lightbulb', 'Brightness', prop['value'])
                    acc.char_volume.set_value(prop['value'])
                    #acc.char_temp.set_value(prop['value']['value'])

                elif prop['name']=='connectivity':
                    #self.log.info('%s is %s' % (deviceId,prop['value']))
                    if prop['value']['value']=='UNREACHABLE':
                        #self.log.info('%s is unreachable' % deviceId)
                        acc.reachable=False
                        acc.char_on.set_value(False)
                    else:
                        acc.reachable=True

                elif prop['name']=='powerState':
                    if getattr(acc, "char_on", None):
                        if prop['value']=='ON':
                            acc.char_on.set_value(True)
                            #self.setCharacteristic(thisaid, 'Lightbulb', 'On', True)
                        elif prop['value']=='OFF':
                            acc.char_on.set_value(False)
                            #self.setCharacteristic(thisaid, 'Lightbulb', 'On', False)
                elif prop['name']=='temperature':
                    #self.setCharacteristic(thisaid, 'TemperatureSensor', 'CurrentTemperature', prop['value'])
                    if prop['value']['scale']=='FAHRENHEIT':
                        acc.char_temp.set_value((int(prop['value']['value'])-32) * 5.0 / 9.0)
                    else:
                        acc.char_temp.set_value(prop['value']['value'])
                        
                elif prop['name']=='targetSetpoint' or prop['name']=='upperSetpoint':
                    if prop['value']['scale']=='FAHRENHEIT':
                        acc.char_TargetTemperature.set_value((int(prop['value']['value'])-32) * 5.0 / 9.0)
                    else:
                        acc.char_TargetTemperature.set_value(prop['value']['value'])

                elif prop['name']=='thermostatMode':
                    modes={"AUTO": 3, "COOL": 2, "HEAT": 1, "OFF": 0 }
                    acc.char_TargetHeatingCoolingState.set_value(modes[prop['value']])
                    if prop['value']=='AUTO': 
                        acc.char_CurrentHeatingCoolingState.set_value(2)
                    else:
                        acc.char_CurrentHeatingCoolingState.set_value(modes[prop['value']])
                    


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
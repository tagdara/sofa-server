#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'../../base'))

from sofabase import sofabase
from sofabase import adapterbase
import devices
#import definitions

import shelve
import datetime
import time

import json
import pyecobee
from pyecobee import *
import pytz

import asyncio

class ecobee(sofabase):
    
    class ecobee_connect():
        
        def __init__(self, log=None, db=None, name='', apikey=''):
            self.log=log
            self.shelfdb=db
            self.thermostat_name=name
            self.apikey=apikey
            self.authFail=False

        def setup(self):
        
            try:
                pyecobee_db = shelve.open(self.shelfdb, protocol=2)
                self.ecobee_service = pyecobee_db[self.thermostat_name]
            except KeyError:
                application_key = self.apikey
                self.ecobee_service = EcobeeService(thermostat_name=self.thermostat_name, application_key=application_key)
            finally:
                pyecobee_db.close()
    
            if not self.ecobee_service.authorization_token:
                self.authorize(self.ecobee_service)
            else:
                self.log.info('Token: %s' % self.ecobee_service.authorization_token)
    
            if not self.ecobee_service.access_token or self.authFail:
                self.request_tokens()
    
            now_utc = datetime.datetime.now(pytz.utc)
            self.log.info('now: %s vs exp: %s or %s' % (now_utc,self.ecobee_service.refresh_token_expires_on, self.ecobee_service.access_token_expires_on))
            if now_utc > self.ecobee_service.refresh_token_expires_on:
                self.authorize(self.ecobee_service)
                self.request_tokens()
            elif now_utc > self.ecobee_service.access_token_expires_on:
                token_response = self.refresh_tokens()
               
            return self.ecobee_service

        def persist_to_shelf(self, file_name, ecobee_service):
            pyecobee_db = shelve.open(file_name, protocol=2)
            pyecobee_db[ecobee_service.thermostat_name] = ecobee_service
            pyecobee_db.close()
    
    
        def refresh_tokens(self):
            token_response = self.ecobee_service.refresh_tokens()
            self.log.info('Ecobee Token refreshed')
            self.log.debug('TokenResponse returned from ecobee_service.refresh_tokens():\n{0}'.format(token_response.pretty_format()))
            self.persist_to_shelf(self.shelfdb, self.ecobee_service)
            
        def check_tokens(self):
            
            try:
                now_utc = datetime.datetime.now(pytz.utc)
                if now_utc > self.ecobee_service.refresh_token_expires_on:
                    self.log.info('now: %s vs exp: %s or %s' % (now_utc,self.ecobee_service.refresh_token_expires_on, self.ecobee_service.access_token_expires_on))
                    self.authorize(self.ecobee_service)
                    self.request_tokens()
                elif now_utc > self.ecobee_service.access_token_expires_on:
                    self.log.info('now: %s vs exp: %s or %s' % (now_utc,self.ecobee_service.refresh_token_expires_on, self.ecobee_service.access_token_expires_on))
                    token_response = self.refresh_tokens()                
            except:
                self.log.info('Error checking tokens', exc_info=True)


        def request_tokens(self):
            try:
                token_response = self.ecobee_service.request_tokens()
                self.log.info('TokenResponse returned from ecobee_service.request_tokens():\n{0}'.format(token_response.pretty_format()))
                self.persist_to_shelf(self.shelfdb, self.ecobee_service)
            except:
                self.log.info('Error requesting tokens', exc_info=True)
                try:
                    self.authorize(self.ecobee_service)
                    self.request_tokens()
                except:
                    self.log.info('Failed to re-authorize', exc_info=True)

    
        def authorize(self, ecobee_service):
            authorize_response = ecobee_service.authorize()
            self.log.info('AuthorizeResponse returned from ecobee_service.authorize():\n{0}'.format(authorize_response.pretty_format()))
    
            self.persist_to_shelf(self.shelfdb, ecobee_service)
    
            self.log.info('Please goto ecobee.com, login to the web portal and click on the settings tab. Ensure the My '
                    'Apps widget is enabled. If it is not click on the My Apps option in the menu on the left. In the '
                    'My Apps widget paste "{0}" and in the textbox labelled "Enter your 4 digit pin to '
                    'install your third party app" and then click "Install App". The next screen will display any '
                    'permissions the app requires and will ask you to click "Authorize" to add the application.\n\n'
                    'After completing this step please hit "Enter" to continue.'.format(
            authorize_response.ecobee_pin))
    
        def props(self, et):
            return {s: getattr(et, s) for s in et.__slots__ if hasattr(et, s)}
        
        def updateThermostat(self):
            
            try:
                self.check_tokens()
                
                selection = Selection(selection_type=SelectionType.REGISTERED.value, selection_match='', include_alerts=True,
                              include_device=True, include_electricity=True, include_equipment_status=True,
                              include_events=True, include_extended_runtime=True, include_house_details=True,
                              include_location=True, include_management=True, include_notification_settings=True,
                              include_oem_cfg=False, include_privacy=False, include_program=True, include_reminders=True,
                              include_runtime=True, include_security_settings=False, include_sensors=True,
                              include_settings=True, include_technician=True, include_utility=True, include_version=True,
                              include_weather=True)
        
                thermostat_response = self.ecobee_service.request_thermostats(selection)
                #self.log.info(thermostat_response.pretty_format())
                #assert thermostat_response.status.code == 0, 'Failure while executing request_thermostats:\n{0}'.format(thermostat_response.pretty_format()) 
                stats=dict()
                sensors=dict()
                for therm in thermostat_response.thermostat_list:
                    tstat=dict()
                    tstat['name']=therm.name
                    tstat['brand']=therm.brand
                    tstat['type']="thermostat"
                    tstat['equipment_status']=therm.equipment_status
                    #et=therm.extended_runtime
                    tstat['runtime']=self.smoothData(self.props(therm.runtime))
                    stats[str(therm.identifier)]=tstat
                    
                    #self.log.info('therm: %s ' % dir(therm))
                    
                    for rsensor in therm.remote_sensors:
                        if rsensor.code!=None:  # it's none on full thermostats
                            sensor=dict()
                            sensor['name']=rsensor.name
                            sensor['code']=rsensor.code
                            sensor['type']="sensor"
                            for cap in rsensor.capability:
                                if cap.type=="temperature":
                                    if cap.value=="unknown":
                                        #self.log.info('Rsensor has unknown: %s' % rsensor.capability)
                                        sensor['temperature']=70
                                    else:
                                        sensor['temperature']=int(int(cap.value)/10)
                                elif cap.type=="occupancy":
                                    sensor['occupancy']=cap.value
                            sensors[sensor['code']]=sensor
                        
                    result={ "thermostat": stats, "sensor": sensors}
                    
                return result
            except:
                self.log.error('Error updating thermostat data', exc_info=True)
                return {}
            
        def smoothData(self, data):
            
            temperatureValues=['_desired_cool', '_desired_heat', '_actual_temperature', '_desired_cool_range', '_desired_heat_range']
    
            output={}
            for item in data:
                if item in temperatureValues:
                    if type(data[item])==list:
                        output[item.strip('_')]=[]
                        for litem in data[item]:
                            output[item.strip('_')].append(litem/10)
                    else:
                        output[item.strip('_')]=data[item]/10
                else:
                    output[item.strip('_')]=data[item]
            
            return output

            
    
    class adapterProcess(adapterbase):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.dataset.nativeDevices['thermostat']={}
            self.dataset.nativeDevices['sensor']={}
            #self.definitions=definitions.Definitions
            self.log=log
            self.notify=notify
            self.polltime=self.dataset.config['pollinterval']

            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            
        async def start(self):
            self.log.info('.. Starting ecobee')
            self.ecobee=ecobee.ecobee_connect(log=self.log, db=self.dataset.config['db'], name=self.dataset.config['name'], apikey=self.dataset.config['apikey'])
            self.ecobee.setup()
            await self.pollEcobee()

            
        async def pollEcobee(self):
            exit=False
            while not exit:
                try:
                    #self.log.info("Polling bridge data")
                    data=self.ecobee.updateThermostat()
                    if data:
                        await self.dataset.ingest(data)

                except pyecobee.exceptions.EcobeeApiException:
                    self.ecobee.refresh_tokens()

                except KeyboardInterrupt:
                    exit=True
                    break
                except:
                    self.log.error('Error fetching Ecobee Data', exc_info=True)
                
                await asyncio.sleep(self.polltime)


        def percentage(self, percent, whole):
            return int((percent * whole) / 100.0)

        # Adapter Overlays that will be called from dataset
        def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="thermostat":
                    return self.addSmartThermostat(path.split("/")[2])
                elif path.split("/")[1]=="sensor":
                    return self.addSimpleThermostat(path.split("/")[2])
 
                else:
                    self.log.info('Unknown smart device: %s' % path)

            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False


        async def addSmartThermostat(self, deviceid):
            
            nativeObject=self.dataset.nativeDevices['thermostat'][deviceid]
            if nativeObject['name'] not in self.dataset.localDevices:
                if nativeObject["brand"]=="ecobee":
                    return self.dataset.addDevice(nativeObject['name'], devices.dualThermostat('ecobee/thermostat/%s' % deviceid, nativeObject['name'], supportedModes=["AUTO", "HEAT", "COOL", "OFF"] ))
            return False


        async def addSimpleThermostat(self, deviceid):
            
            nativeObject=self.dataset.nativeDevices['sensor'][deviceid]
            if nativeObject['name'] not in self.dataset.localDevices:
                if nativeObject["type"]=="sensor":
                    return self.dataset.addDevice(nativeObject['name'], devices.TemperatureSensorDevice('ecobee/sensor/%s' % deviceid, nativeObject['name']))

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
                if nativeObject["type"]=="sensor":
                    if detail=="temperature" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist,"TemperatureSensor","temperature")
                
                elif nativeObject["type"]=="thermostat":
                    if detail=="runtime/actual_temperature" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist,"TemperatureSensor","temperature")
                    if detail=="runtime/desired_heat" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist,"ThermostatController","lowerSetpoint")
                    if detail=="runtime/desired_cool" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist,"ThermostatController","upperSetpoint")

                    if detail=="runtime/desired_fan_mode" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist,"ThermostatController","thermostatMode")
                        
                return controllerlist
            except KeyError:
                pass
            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)


            
        def virtualControllerProperty(self, nativeObj, controllerProp):
            
            try:
                
                if controllerProp=='temperature':
                    if nativeObj['type']=='sensor':
                        return int(nativeObj['temperature'])
                    else:
                        return int(nativeObj['runtime']['actual_temperature'])
                    
                elif controllerProp=='targetSetpoint':
                    if int(nativeObj['runtime']['actual_temperature'])<int(nativeObj['runtime']['desired_cool']):
                        return int(nativeObj['runtime']['desired_heat'])
                    else:
                        return int(nativeObj['runtime']['desired_cool'])

                elif controllerProp=='lowerSetpoint':
                    return int(nativeObj['runtime']['desired_heat'])

                elif controllerProp=='upperSetpoint':
                    return int(nativeObj['runtime']['desired_cool'])
               
                elif controllerProp=='thermostatMode':
                    return nativeObj['runtime']['desired_fan_mode'].upper()

                else:
                    self.log.info('Unknown controller property mapping: %s' % controllerProp)
                    return {}
            except:
                self.log.error('Error converting virtual controller property: %s %s' % (controllerProp, nativeObj), exc_info=True)



if __name__ == '__main__':
    adapter=ecobee(name='ecobee')
    adapter.start()

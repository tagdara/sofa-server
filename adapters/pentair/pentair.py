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

import findGateway
import doQuery
from constants import me

class pentair(sofabase):
    
    class adapterProcess(adapterbase):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.dataset.nativeDevices['pentair']={}
            self.dataset.nativeDevices['circuits']={}
            self.dataset.nativeDevices['bodies']={}
            #self.bridgeAddress=self.dataset.config['address']
            self.log=log
            self.notify=notify
            self.polltime=10
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            
        async def start(self):
            try:
                self.log.info('.. Starting pentair')
                #await self.pollHueBridge()
                if await self.connectPentair():
                    self.poolquery=doQuery.doquery(self.log, self.gatewayIP, self.gatewayPort)
                    config=self.poolquery.startPentair()
                    await self.dataset.ingest(json.loads(json.dumps(config)))
                    await self.pollPentair()
            except:
                self.log.error('Error getting Pentair data', exc_info=True)

        async def updatePentair(self):
            try:
                #self.log.info("Polling bridge data")
                pooldata=self.poolquery.advancedQueryGateway()
                await self.dataset.ingest(json.loads(json.dumps(pooldata)))
            except:
                self.log.error('Error fetching Pool Data', exc_info=True)
                 
            
        async def pollPentair(self):
            while True:
                try:
                    await self.updatePentair()
                    await asyncio.sleep(self.polltime)
                except:
                    self.log.error('Error fetching Hue Bridge Data', exc_info=True)
                    
        async def connectPentair(self):
            try:
                verbose=False
                self.gatewayIP, self.gatewayPort, gatewayType, gatewaySubtype, gatewayName, okchk = findGateway.findGateway(verbose)
                return True
            except:
                self.log.error('Erroring finding gateway', exc_info=True)
                return False
                
        async def getScreenLogicData(self):
            try:
                if (self.gatewayIP):
                    self.poolquery.checkPentair()
            except:
                self.log.error('Error in getScreenLogicData', exc_info=True)


        # Adapter Overlays that will be called from dataset
        async def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="airtemp":
                    return await self.addSimpleThermostat("airtemp","Outdoor Temperature")
                if path.split("/")[2]=="pool":
                    return await self.addSmartThermostat("pool","Pool Temperature")
                if path.split("/")[2]=="spa":
                    return await self.addSmartThermostat("spa","Spa Temperature")
                    
                if path.split("/")[1]=='circuits' and len(path.split("/"))>3:
                    #self.log.info('P: %s' % path.split('/'))
                    circuitfunction=self.dataset.nativeDevices['circuits'][path.split('/')[2]]['function']
                    circuitid=path.split('/')[2]
                    circuitname=self.dataset.nativeDevices['circuits'][circuitid]['name']
                    if circuitfunction == 16:
                        #self.log.info('Active Circuit: %s' % circuitid )
                        return await self.addColorLight(circuitid, circuitname)
                        #return await self.add
                    if circuitfunction == 7:
                        #self.log.info('Active Circuit: %s' % circuitid )
                        return await self.addSimpleLight(circuitid, circuitname)
                        #return await self.add
                        
                #self.log.info('Did not add device for %s' % path)
                return False

            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False


        async def addSmartThermostat(self, deviceid, devicename):
        
            if devicename not in self.dataset.localDevices:
                return self.dataset.addDevice(devicename, devices.smartThermostat('pentair/bodies/%s' % deviceid, devicename, supportedModes=["AUTO", "HEAT", "OFF"] ))
            
            return False

        async def addSimpleThermostat(self, deviceid, devicename):
            
            if devicename not in self.dataset.localDevices:
                return self.dataset.addDevice(devicename, devices.TemperatureSensorDevice('pentair/bodies/%s' % deviceid, devicename))

            return False

        async def addSimpleLight(self, deviceid, devicename):
            
            if devicename not in self.dataset.localDevices:
                return self.dataset.addDevice(devicename, devices.simpleLight('pentair/circuits/%s' % deviceid, devicename))

            return False

        async def addColorLight(self, deviceid, devicename):
            
            if devicename not in self.dataset.localDevices:
                
                # I clearly built a colorPoolLight device definition for some reason, but those changes were
                # lost during a github fetch conflict. This should really use some less specific definition.
                #return self.dataset.addDevice(devicename, devices.colorPoolLight('pentair/circuits/%s' % deviceid, devicename))
                return self.dataset.addDevice(devicename, devices.colorOnlyLight('pentair/circuits/%s' % deviceid, devicename))

            return False


        def find_circuit(self, circuitname):
            
            try:
                for circuit in self.dataset.nativeDevices['circuits']:
                    if self.dataset.nativeDevices['circuits'][circuit]['name'].lower()==circuitname.lower():
                        circuitid=self.dataset.nativeDevices['circuits'][circuit]['id']
                        return self.dataset.nativeDevices['circuits'][circuit]
                return None
            except:
                self.log.error('Error finding circuit for %s' % circuitname, exc_info=True)


        async def processDirective(self, endpointId, controller, command, payload, correlationToken='', cookie={}):

            try:
                device=endpointId.split(":")[2]
                nativeCommand={}
                updatedelay=1
                if controller=="PowerController":
                    if command=='TurnOn':
                        nativeCommand['on']=True
                        circuitid=self.dataset.nativeDevices['circuits'][device]['id']
                        self.poolquery.sendButtonPress(int(circuitid),1)
                    elif command=='TurnOff':
                        circuitid=self.dataset.nativeDevices['circuits'][device]['id']

                        nativeCommand['on']=False
                        self.poolquery.sendButtonPress(int(circuitid),0)

                elif controller=="BrightnessController":
                    if int(payload['brightness'])>0:
                        nativeCommand['on']=True
                        circuitid=self.dataset.nativeDevices['circuits'][device]['id']
                        self.poolquery.sendButtonPress(int(circuitid),1)
                    else:
                        circuitid=self.dataset.nativeDevices['circuits'][device]['id']
                        nativeCommand['on']=False
                        self.poolquery.sendButtonPress(int(circuitid),0)
  
                        
                elif controller=="ColorController":
                    if command=='SetColor':
                        newcolor=self.hueToPentairColor(int(float(payload['color']['hue'])))
                        nativeCommand['color']=newcolor
                        self.poolquery.sendColorLightsCommand(newcolor)
                        updatedelay=5
                        
                elif controller=="ThermostatController":
                    if command=='SetThermostatMode':
                        circuitid=self.find_circuit(endpointId.split(':')[2])['id']
                        self.log.info('Circuit ID for %s is %s' % (endpointId, circuitid))
                        if payload['thermostatMode']['value']=='OFF':
                            nativeCommand['on']=False
                            self.poolquery.sendButtonPress(int(circuitid),0)
                        else:
                            nativeCommand['on']=True
                            self.poolquery.sendButtonPress(int(circuitid),1)
                        updatedelay=5

                if nativeCommand:
                    await asyncio.sleep(updatedelay)
                    await self.updatePentair()
                self.log.info('Endpoint: %s / command: %s' % (device, nativeCommand))
                    
            except:
                self.log.error('Error executing state change.', exc_info=True)


        def virtualControllers(self, itempath):

            try:
                self.log.info('Getting controllers for %s' % itempath)
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                #self.log.debug('Checking object for controllers: %s' % nativeObject)
                
                try:
                    detail=itempath.split("/",2)[2]
                except:
                    detail=""
                    
                self.log.info('Detail: %s' % detail)
                controllerlist={}

                if detail in ['spa', 'pool','airtemp', 'pool/currentTemp', 'spa/currentTemp' ]:
                    controllerlist=self.addControllerProps(controllerlist, "TemperatureSensor","temperature")

                if detail in ['spa', 'pool']:
                    controllerlist=self.addControllerProps(controllerlist,"ThermostatController","targetSetpoint")
                    controllerlist=self.addControllerProps(controllerlist,"ThermostatController","thermostatMode")

                    
                if itempath.split("/")[1]=='circuits':
                    if nativeObject['function']==16:
                        controllerlist['PowerController']=['powerState']
                        controllerlist["ColorController"]=["color"]
                    if nativeObject['function']==7:
                        controllerlist['PowerController']=['powerState']
                        
                return controllerlist
            except KeyError:
                pass
            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)


        def virtualControllerProperty(self, nativeObj, controllerProp):
            
            try:
                #self.log.info('vcp: %s %s' % (controllerProp, nativeObj))
                if controllerProp=='temperature':
                    if type(nativeObj)==int:
                        return nativeObj
                    if nativeObj['bodyType']==1 and nativeObj['heatStatus']==0:
                        return self.dataset.nativeDevices['bodies']['pool']['currentTemp']
                    else:
                        return nativeObj['currentTemp']  

                if controllerProp=='thermostatMode':
                    circuit=None
                    if nativeObj['bodyType']==0:
                        circuit=self.find_circuit('pool')
                    if nativeObj['bodyType']==1:
                        circuit=self.find_circuit('spa')
                    self.log.info('Circuit: %s' % circuit)
                    if circuit:
                        if circuit['state']==0:
                            return 'OFF'
                    
                        if nativeObj['heatStatus']==0:
                            return 'AUTO'
                        if nativeObj['heatStatus']==1:
                            return 'HEAT'

                    return 'OFF'

                if controllerProp=='targetSetpoint':
                    return nativeObj['setPoint']
                        
                if controllerProp=='powerState':
                    if nativeObj['function']==16 or nativeObj['function']==7:
                        if nativeObj['state']==0:
                            return 'OFF'
                        else:
                            return 'ON'
                            
                if controllerProp=='color':
                    if nativeObj['function']==16:
                        if nativeObj['color_set']==0:
                            return { "hue": 180, "saturation": 0.75, "brightness": 0}
                        else:
                            return { "hue": 180, "saturation": 0.75, "brightness": 1}
                   

                else:
                    self.log.info('Unknown controller property mapping: %s' % controllerProp)
                    return {}
            except:
                self.log.error('Error converting virtual controller property: %s %s' % (controllerProp, nativeObj), exc_info=True)

        def hueToPentairColor(self, hue):
            
            try:
                colors={ 
                    "Red":      {"hue": 0, "pentair":15},
                    "Green":    {"hue": 120, "pentair":14},
                    "White":    {"hue": 180, "pentair":16},
                    "Blue":     {"hue": 240, "pentair":13},
                    "Magenta":  {"hue": 300, "pentair":17},
                }
                
                delta=180
                currentcolor=16
                currentcolorname='White'
                for color in colors:
                    if abs(hue-colors[color]['hue'])<delta:
                        delta=abs(hue-colors[color]['hue'])
                        currentcolor=colors[color]['pentair']
                        currentcolorname=color
                        
                self.log.info('Returning %s for %s with delta %s ' % (currentcolorname, hue, delta))
                return currentcolor
                
            except:
                self.log.error('Error', exc_info=True)

        def pentairColorToHue(self, pentaircolor):
            
            try:
                colors={ 
                    "Red":      {"hue": 0, "pentair":15},
                    "Green":    {"hue": 120, "pentair":14},
                    "White":    {"hue": 180, "pentair":16},
                    "Blue":     {"hue": 240, "pentair":13},
                    "Magenta":  {"hue": 300, "pentair":17},
                }
                
                delta=180
                currentcolor=16
                currentcolorname='White'
                for color in colors:
                    if abs(pentair-colors[color]['hue'])<delta:
                        delta=abs(hue-colors[color]['hue'])
                        currentcolor=colors[color]['pentair']
                        currentcolorname=color
                        
                self.log.info('Returning %s for %s with delta %s ' % (currentcolorname, hue, delta))
                return currentcolor
                
            except:
                self.log.error('Error', exc_info=True)

            
                    
                

if __name__ == '__main__':
    adapter=pentair(name='pentair')
    adapter.start()

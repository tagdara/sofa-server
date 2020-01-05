#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'../../base'))

from sofabase import sofabase
from sofabase import adapterbase
import devices
import math
import random
import json
import asyncio

import sys
import socket
import struct
import ipaddress
from constants import me

#import findGateway
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
            self.circuits=self.dataset.config['circuits']
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
                try:
                    # This is a little bit of a hack to make display work properly.  Since the spa temp only updates
                    # when the heater is on, we overwrite the temp with the pool temp 
                    if pooldata['bodies']['spa']['heatStatus']==0:
                        pooldata['bodies']['spa']['currentTemp']=pooldata['bodies']['pool']['currentTemp']
                    # We also want to get the external air temp but it doesn't make sense as a root level item so
                    # promoting it into bodies as a workaround simplifies that data
                    pooldata['bodies']['air']={ "bodyType":2, "heatStatus": 0, "currentTemp":pooldata['airtemp'] }
                
                except:
                    pass
                changes=await self.dataset.ingest(json.loads(json.dumps(pooldata)))
                if changes:
                    self.log.info('Changes: %s' % changes)
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
                self.gatewayIP, self.gatewayPort, gatewayType, gatewaySubtype, gatewayName, okchk = self.findGateway(verbose)
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


        def findGateway(self, verbose):
            # these are only for the datagram so keep them here instead of "constants.py"
            bcast = "255.255.255.255"
            port  = 1444
            wantchk = 2
            addressfamily = socket.AF_INET
        
            # no idea why this datastructure... it works.
            data  = struct.pack('<bbbbbbbb', 1,0,0,0, 0,0,0,0)
            # Create a UDP socket
            try:
                udpSock = socket.socket(addressfamily, socket.SOCK_DGRAM)
            except:
                sys.stderr.write("ERROR: {}: socket.socket boarked.\n".format(me))
                sys.exit(1)
        
            # Get ready to broadcast
            try:
                udpSock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except:
                sys.stderr.write("ERROR: {}: udpSock.setsockopt boarked.\n".format(me))
                sys.exit(2)
        
            # send the datagram
            if(verbose):
                print("Broadcasting for pentair systems...")
            try:
                udpSock.sendto(data, (bcast, port))
            except:
                sys.stderr.write("ERROR: {}: udpSock.sendto boarked.\n".format(me))
                sys.exit(3)
        
            # listen for a gateway responding
            if(verbose):
                print("Waiting for a response...")
            try:
                data, server = udpSock.recvfrom(4096)
            except:
                sys.stderr.write("ERROR: {}: udpSock.recvfrom boarked.\n".format(me))
                sys.exit(4)
            try:
                udpSock.close()
            except:
                # not sure we really need to exit if we can't close the socket...
                sys.stderr.write("ERROR: {}: udpSock.close boarked.\n".format(me))
                sys.exit(5)
        
            # "server" is ip_address:port that we got a response from. 
            # not sure what happens if we have to gateways on a subnet. havoc i suppose.
            if(verbose):
                system, port = server
                print("INFO: {}: Received a response from {}:{}".format(me(), system, port))
        
            # the format here is a little different than the documentation. 
            # the response I get back includes the gateway's name in the form of "Pentair: AB-CD-EF"
            expectedfmt = "<I4BH2B"
            paddedfmt = expectedfmt + str(len(data)-struct.calcsize(expectedfmt)) + "s"
            try:
                chk, ip1, ip2, ip3, ip4, gatewayPort, gatewayType, gatewaySubtype, gatewayName = struct.unpack(paddedfmt, data)
            except struct.error as err:
                print("ERROR: {}: received unpackable data from the gateway: \"{}\"".format(me, err))
                sys.exit(6)
        
            okchk = (chk == wantchk)
        
            if(not okchk):
                # not sure that I need to exit if "chk" isn't what we wanted.
                sys.stderr.write("ERROR: {}: Incorrect checksum. Wanted '{}', got '{}'\n".format(me, wantchk, chk))
                #sys.exit(7)
        
            # make sure we got a good IP address
            receivedIP = "{}.{}.{}.{}".format(str(ip1), str(ip2), str(ip3), str(ip4))
            try:
                gatewayIP = str(ipaddress.ip_address(receivedIP))
            except ValueError as err:
                print("ERROR: {}: got an invalid IP address from the gateway:\n  \"{}\"".format(me, err))
                sys.exit(8)
            except NameError as err:
                print("ERROR: {}: received garbage from the gateway:\n  \"{}\"".format(me, err))
                sys.exit(9)
            except:
                print("ERROR: {}: Couldn't get an IP address for the gateway.".format(me, err))
                sys.exit(10)
          
            if(verbose):
                print("gatewayIP: '{}'".format(gatewayIP))
                print("gatewayPort: '{}'".format(gatewayPort))
                print("gatewayType: '{}'".format(gatewayType))
                print("gatewaySubtype: '{}'".format(gatewaySubtype))
                print("gatewayName: '{}'".format(gatewayName.decode("utf-8")))
        
            return gatewayIP, gatewayPort, gatewayType, gatewaySubtype, gatewayName, okchk



        # Adapter Overlays that will be called from dataset
        async def addSmartDevice(self, path):
            
            try:
                if path.split("/")[2]=="air":
                    return await self.addSimpleThermostat("air","Outdoor Temperature")
                if path.split("/")[2]=="pool":
                    return await self.addSmartThermostat("pool","Pool Temperature")
                if path.split("/")[2]=="spa":
                    return await self.addSmartThermostat("spa","Spa Temperature")
                    
                if path.split("/")[1]=='circuits' and len(path.split("/"))>3:
                    #self.log.info('P: %s' % path.split('/'))
                    circuitfunction=self.dataset.nativeDevices['circuits'][path.split('/')[2]]['function']
                    circuitid=path.split('/')[2]
                    circuitname=self.dataset.nativeDevices['circuits'][circuitid]['name']
                    if circuitfunction == 2:
                        return await self.addBasicDevice(circuitid,'Pool Pump')
                    if circuitfunction == 1:
                        return await self.addBasicDevice(circuitid,'Spa Jets')
                    if circuitname=='Cleaner':
                        return await self.addBasicDevice(circuitid,'Pool Cleaner')
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


        async def addSmartThermostat(self, deviceid, devicename, supportedRange=[80,104]):
        
            if devicename not in self.dataset.localDevices:
                return self.dataset.addDevice(devicename, devices.smartThermostat('pentair/bodies/%s' % deviceid, devicename, supportedRange=supportedRange, supportedModes=["HEAT", "OFF"] ))
            
            return False

        async def addSimpleThermostat(self, deviceid, devicename):
            
            if devicename not in self.dataset.localDevices:
                return self.dataset.addDevice(devicename, devices.TemperatureSensorDevice('pentair/bodies/%s' % deviceid, devicename))

            return False

        async def addSimpleLight(self, deviceid, devicename):
            
            if devicename not in self.dataset.localDevices:
                return self.dataset.addDevice(devicename, devices.simpleLight('pentair/circuits/%s' % deviceid, devicename))

            return False

        async def addBasicDevice(self, deviceid, devicename):
            
            if devicename not in self.dataset.localDevices:
                return self.dataset.addDevice(devicename, devices.basicDevice('pentair/circuits/%s' % deviceid, devicename))

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

                elif controller=="BrightnessController-DoNotRun":
                    
                    # Skipping processing for brightness at this point.  In all cases where the 
                    # power state changes, a power command should also be received.
                    # this should reduce the risk of flapping on the very slow pentair lights
                    
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
                    
                    response=await self.dataset.generateResponse(endpointId, correlationToken)
                    return response
                self.log.info('Endpoint: %s / command: %s' % (device, nativeCommand))
                    
            except:
                self.log.error('Error executing state change.', exc_info=True)


        def virtualControllers(self, itempath):

            try:
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                #self.log.debug('Checking object for controllers: %s' % nativeObject)
                
                try:
                    detail=itempath.split("/",2)[2]
                except:
                    detail=""
                    
                try:
                    subdetail=itempath.split("/",3)[3]
                except:
                    subdetail=""
                    
                controllerlist={}
                
                #self.log.info('Checking state for: %s %s - %s' % (detail, subdetail, itempath))

                if detail in ['spa', 'pool', 'air'] or subdetail in [ 'currentTemp' ]:
                    controllerlist=self.addControllerProps(controllerlist, "TemperatureSensor","temperature")

                if detail in ['spa', 'pool'] or subdetail in ['heatMode', 'heatStatus', 'setPoint']:
                    controllerlist=self.addControllerProps(controllerlist,"ThermostatController","targetSetpoint")
                    controllerlist=self.addControllerProps(controllerlist,"ThermostatController","thermostatMode")
                    
                if itempath.split("/")[1]=='circuits':
                    if nativeObject['function']==16:
                        controllerlist['PowerController']=['powerState']
                        controllerlist["ColorController"]=["color"]
                    if nativeObject['function'] in [0, 1, 2, 7]:
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
                    return nativeObj['currentTemp']  

                if controllerProp=='thermostatMode':
                    circuit=None
                    if nativeObj['bodyType']==0:
                        circuit=self.find_circuit('pool')
                    if nativeObj['bodyType']==1:
                        circuit=self.find_circuit('spa')
                    #self.log.info('Circuit: %s' % circuit)

                    if nativeObj['heatMode']==0:
                        return 'OFF'
                    if nativeObj['heatMode']==3:
                        return 'HEAT'

                    return 'OFF'

                if controllerProp=='targetSetpoint':
                    return nativeObj['setPoint']
                        
                if controllerProp=='powerState':
                    if nativeObj['function'] in [0,1,2,7,16]:
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

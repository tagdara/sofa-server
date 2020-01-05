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
import requests
import json
import asyncio
import definitions
import time


class Client(asyncio.Protocol):

    def __init__(self, loop=None, log=None, notify=None, dataset=None, **kwargs):
        self.is_open = False
        self.loop = loop
        self.log=log
        self.last_message = ""
        self.definitions=definitions.elkDefinitions
        self.sendQueue=[]
        self.notify=notify
        self.dataset=dataset
        self.lastcommand=""
        self.controllerMap=dict()
        
        # populate base dataset to eliminate oddly formatted adds
        self.dataset.nativeDevices={"zone": {}, "output": {}, "task": {}}
        

    def connection_made(self, transport):
        
        try:
            self.sockname = transport.get_extra_info("sockname")
            self.transport = transport
            self.is_open = True
        except:
            self.log.error('Connection made but something went wrong.', exc_info=True)
            
        try:
            self.programmingMode=False
            self.log.info('Sending initial request')
            self.requestRealTimeClock()
            self.requestZoneDefinitionReport()
            self.requestZoneStatusReport()
            self.requestLogData(count=5)
            self.requestOutputs()
            self.requestTasks()
            self.checkSendQueue()
        except:
            self.log.error('Error sending request', exc_info=True)
        
    def connection_lost(self, exc):
        self.is_open = False
        self.loop.stop()

    def data_received(self, data):
        
        try:
            asyncio.ensure_future(self.processElkCommand(self.getElkCommand(data.decode()), data.decode()))
            self.checkSendQueue()
        except:
            self.log.error('Error processing received data: %s' % data, exc_info=True)

    def queueForSend(self, data):
        
        self.sendQueue.append(data)
            

    def checkSendQueue(self):
        
        try:
            if (len(self.sendQueue)>0):
                if self.programmingMode==False:
                    self.lastcommand=self.sendQueue.pop(0)
                self.send(self.lastcommand)

        except:
            self.log.error('Error bumping elk queue',exc_info=True)
            

    def send(self, data):
        
        try:
            self.transport.write(data.encode())
            #self.log.info('> elk  %s' % data.replace('\n', ' ').replace('\r', ''))
        except:
            self.log.error('Error on send', exc_info=True)


    def getElkCommand(self, data):

        try:
            #Check to see if this is a formatted command or a custom text screen.
            try:
                elkdl=int(data[0:2],16)
            except ValueError:
                #self.log.warn('Custom text instead of command: %s' % data)
                return "Custom"
                
            data=data[2:elkdl+2]
            elkCommandCode=data[0:2]
            if elkCommandCode in self.definitions.elkCommands:
                return self.definitions.elkCommands[elkCommandCode]
            else:
                return "Custom"
        except:
            self.log.error("Error determining Elk Command code from: %s" % data, exc_info=True)
            return "Custom"        

    def computechecksum(self,cmd):
        asctot=0
        for ch in cmd:
            asctot=asctot+ord(ch)
            cc2=hex(((~ asctot)+1) & 255)
        return str(cc2)[2:].upper()

        
    async def processElkCommand(self, command, data):
        
        if command=="ELKRP connected":
            if not self.programmingMode:
                self.log.info('Elk RP Programming mode is active.  Command deferred for retry: %s' % self.lastcommand)
                self.programmingMode=True
            time.sleep(1)
            return False
            
        self.programmingMode=False
        
        if command=="Zone status report data":  #ZS
            await self.dataset.ingest(self.zoneStatusReport(data))
            for zone in self.dataset.nativeDevices['zone']:
                self.requestZoneStringDescription(zone)

        elif command=='Reply temperature data': #LW
            await self.replyTemperatureData(data)
        
        elif command=="Keypad key change update": #KC
            #This transmission update option transmits the updated status whenever it 
            # changes and is enabled by setting the location TRUE in the M1 Control Global Programming Location 40. 
            pass
            
        elif command=="Control output status report data": #CS
            try:
                await self.dataset.ingest(self.controlOutputStatusReport(data))
            except:
                self.log.info("Error: %s" % command, exc_info=True)
           
        elif command=="Text string description report data": #SD
            try:
                await self.dataset.ingest(self.zoneTextStringDescriptionReport(data))
            except:
                self.log.info('Error getting and merging zone string data', exc_info=True)

        elif command=="Zone change update": #ZC
            try:
                await self.dataset.ingest(self.zoneChangeUpdate(data))
            except:
                self.log.info('Error getting Zone Change Update', exc_info=True)
                
        elif command=="Temperature report data": #ST
                await self.dataset.ingest(self.temperatureReport(data))

        elif command=="Zone definition report data": #ZD
            try:
                zonedata=await self.zoneDefinitionReport(data)
            except:
                self.log.info('Error getting Zone Change Update', exc_info=True)
        
        elif command=="Request Ethernet test":
            self.log.debug('Ethernet heartbeat')
        
        elif command=="Control output change update": #CC
            try:
                outputdata=await self.outputChangeUpdate(data)
            except:
                self.log.info('Error getting Output Change Update', exc_info=True)
        
        else:
            self.log.info('elk %s > %s' % (command, data.replace('\n', ' ').replace('\r', '')))


    def requestLogData(self,count=5):
        
        for i in range (1,count+1):
            # get log data
            elklogreq="09ld"+str(i).zfill(3)+"00"
            elklogreq=elklogreq+self.computechecksum(elklogreq)
            self.queueForSend(elklogreq+"\r\n")
        
    def requestOutputs(self):
        for i in range (1,65):
            # get output string descriptions
            elklogreq="0Bsd04"+str(i).zfill(3)+"00"
            elklogreq=elklogreq+self.computechecksum(elklogreq)
            self.queueForSend(elklogreq+"\r\n")
        self.queueForSend("06cs0064\r\n")

    def requestTasks(self):
        for i in range (1,33):
            # get task string descriptions
            elklogreq="0Bsd05"+str(i).zfill(3)+"00"
            elklogreq=elklogreq+self.computechecksum(elklogreq)
            self.queueForSend(elklogreq+"\r\n")

    def requestRealTimeClock(self):
        self.queueForSend("06rr0056\r\n")

    def requestZoneStatusReport(self):
        self.queueForSend("06zs004D\r\n")


    def requestZoneDefinitionReport(self):
        self.queueForSend("06zd005C\r\n")
        self.queueForSend("06lw0057\r\n")

    def requestZoneStringDescription(self, zone):
        # Text string description report data
        elkrequest="0Bsd00%s00" % str(int(zone)).zfill(3)
        elkrequest=elkrequest+self.computechecksum(elkrequest)
        self.queueForSend(elkrequest+"\r\n")

    def clipElkData(self, data):
        try:
            elkdl=int(data[0:2],16)
            data=data[2:elkdl+2]
            return data
        except:
            self.log.error("Error clipping Elk Data",exc_info=True)
            return ""


    async def replyTemperatureData(self, data):
        # Reply Temperature Data (LW).  Result of lw command, allows automation 
        # equipment to request the temperatures from zone 
        # temperature sensors and keypad temperatures in one ASCII packet.
        data=self.clipElkData(data)
        try:
            tempzones=data[2:-4]
            for i in range (16,32):
                thistemp=int(tempzones[i*3:i*3+3])-60
                if thistemp > -60:
                    await self.dataset.ingest({'zone': { str(i-15): {'temperature':thistemp}}})
                    
        except:
            self.log.error("replyTemperatureData Error",exc_info=True)


    def controlOutputStatusReport(self,data):
        # Output status report
        
        # D6CSD..00CC(CR-LF)
        # The control panel sends this message in response to a Control Output Status 
        # Request. The data portion of this message is 208 characters long, one character for 
        # each output in order. The value will be: 0 (Off), 1 (On).
        # Example: With control output 1 off, output 2 on, output 3 and output 4 off, the 
        # message would begin D6CS0100...
        
        data=self.clipElkData(data)
        outputs={}
        try:
            elkoutputs=data[2:-4]
            for i,elkcstate in enumerate(elkoutputs):
                if str(int(i+1)) in self.dataset.nativeDevices['output']:
                    if elkcstate=="0":
                        outputs[str(int(i+1))]={'status':'Off'}
                    else:
                        outputs[str(int(i+1))]={'status':'On'}
            return {'output': outputs}
        except:
            self.log.error("controlOutputStatusReport Error", exc_info=True)
            return {}


    def temperatureReport(self,data):
        # Reply With Requested Temperature. This is a result of an 'st' command
        try:
            data=self.clipElkData(data)
            typeid=str(data[2])

            tempzone=data[3:5]
            tempval=data[5:8]
            
            if typeid=='0':
                temptype='Temperature Probe'
                tempval=int(tempval)-60
            elif typeid=='1':
                temptype='Keypad'
            elif typeid=='2':
                temptype='Thermostat'
            else:
                temptype='Unknown'

            elkrequest="0Bsd00"+str(tempzone).zfill(3)+"00"
            elkrequest=elkrequest+self.computechecksum(elkrequest)
            self.queueForSend(elkrequest+"\r\n")
            tempzone=tempzone.lstrip('0')
            return {'zone': { tempzone: {"temperature": tempval}}}
        except:
            self.log.error("temperatureReport Error",exc_info=True)
            return {}

        

    def zoneTextStringDescriptionReport(self, data):

        # ASCII String Text Descriptions stored in device
        try:
            data=self.clipElkData(data)
            if str(int(data[4:7]))!='0': # Eliminates the edge case where if an item hasnt been found yet it returns 0 and blank
                return {self.definitions.zoneStringDescriptions[str(int(data[2:4]))]: { str(int(data[4:7])): {'name': data[7:23].strip() }}}

            return {}
        except:
            self.log.error("textStringDescriptionReport Error",exc_info=True)
            return {}

        
    def zoneChangeUpdate(self, data):
        # Zone Change update, triggered when a zone's status changes
        
        try:
            data=self.clipElkData(data)
            return {'zone': { str(int(data[2:5])).lstrip('0'): {'status':self.definitions.zoneStates[data[5:6]]}}}

        except:
            self.log.error("zoneChangeUpdate Error",exc_info=True)
            return {}


    def zoneStatusReport(self, data):
        # Zone status report
        # The control panel sends this message in response to a Zone Status Request. The data portion of 
        # this message is 208 characters long, one character for each zone in order. Each character is the sum 
        # of all applicable status values, expressed in hexadecimal, using ASCII characters 0-9 and A-F. 

        data=self.clipElkData(data)

        zones=dict()
        try:
            datazones=data[2:-4]
            for i, datazonestatus in enumerate(datazones):
                if (datazonestatus!='0' and i<208):
                    zones[str(int(i+1))]={'status': self.definitions.zoneStates[datazonestatus]}
                    #self.dataset.ingest({'zone': { str(int(i+1)): {'status': self.definitions.zoneStates[datazonestatus]}}})
                    #zones[str(int(i+1))]={ "status": self.definitions.zoneStates[datazonestatus]}
            self.log.info('Zone status report: %s/ %s' % (datazones,zones))
            return {'zone': zones}
        except:
            self.log.error("zoneStatusReport Error",exc_info=True)


    async def zoneDefinitionReport(self,data): # ZD
        # Zone definition report data
        # Array of all 208 zones with the zone definition. Subtract 
        # 48 decimal or 0x30 hex from each array element to get the 
        # zone definition number, or use translation based on ASCII

        data=self.clipElkData(data)

        try:
            elkzones=data[2:-4]
            for i,zone in enumerate(elkzones):
                if (zone!='0' and i<208):
                    if int(i+1) in self.dataset.config['motion_zones']:
                        mode='motion'
                    elif int(i+1) in self.dataset.config['doorbells']:
                        mode='doorbell'
                    else:
                        mode='contact'
                    await self.dataset.ingest({'zone': { str(int(i+1)): {'mode': mode, 'zonetype': self.definitions.zoneDefinitionTypes[zone] }}})
                    
        except:
            self.log.error("zoneDefinitionReport Error",exc_info=True)

    async def outputChangeUpdate(self,data): # CC
        # 0A – Length as ASCII hex
        # CC – Zone Change Message Command
        # ZZZ – Output Number, 1 based
        # S – Output State, 0 = OFF, 1 = ON
        # 00 – future use
        # CC – Checksum

        data=self.clipElkData(data)

        try:
            elkoutput=data[2:5]
            outputstate=data[5]
            if data[5]=='0':
                outputstate='Off'
            else:
                outputstate='On'
            await self.dataset.ingest({'output': { str(int(elkoutput)): {'status': outputstate }}})
        except:
            self.log.error("outputChangeUpdate",exc_info=True)


        
        
class elkm1(sofabase):

    class EndpointHealth(devices.EndpointHealth):

        @property            
        def connectivity(self):
            #stubbed out but should reflect whether the panel is connected or not
            return 'OK'

    class ContactSensor(devices.ContactSensor):

        @property            
        def detectionState(self):
            #stubbed out but should reflect whether the panel is connected or not
            if self.nativeObject['status']=='Normal':
                return 'NOT_DETECTED'
            elif self.nativeObject['status']=='Violated':
                return 'DETECTED'

    class MotionSensor(devices.MotionSensor):

        @property            
        def detectionState(self):
            #stubbed out but should reflect whether the panel is connected or not
            if self.nativeObject['status']=='Normal':
                return 'NOT_DETECTED'
            elif self.nativeObject['status']=='Violated':
                return 'DETECTED'

    class TemperatureSensor(devices.TemperatureSensor):

        @property            
        def temperature(self):
            return self.nativeObject['temperature']

    class ButtonController(devices.ButtonController):

        @property            
        def pressState(self):
            if 'status' not in self.nativeObject:
                return 'OFF'
                
            elif self.nativeObject['status']=="Off":
                return 'OFF'
            else:
                return 'ON'

        async def Press(self, payload, correlationToken='', **kwargs):
            try:
                devicetype=self.device.endpointId.split(":")[1]
                if devicetype=='task':
                    await self.adapter.triggerTask(self.deviceid)
                elif devicetype=='output':
                    await self.adapter.triggerOutput(self.deviceid)
                response=await self.adapter.dataset.generateResponse(self.device.endpointId, correlationToken)
            except:
                self.log.error('!! Error during Press', exc_info=True)
                return None
                
        async def Hold(self, payload, correlationToken='', **kwargs):
            try:
                devicetype=self.device.endpointId.split(":")[1]
                if devicetype=='output':
                    await self.adapter.triggerOutput(self.deviceid, payload['duration'])
                response=await self.adapter.dataset.generateResponse(self.device.endpointId, correlationToken)
            except:
                self.log.error('!! Error during Press', exc_info=True)
                return None
                
        async def Release(self, correlationToken='', **kwargs):
            try:
                devicetype=self.device.endpointId.split(":")[1]
                if devicetype=='output':
                    await self.adapter.releaseOutput(self.deviceid)
                response=await self.adapter.dataset.generateResponse(self.device.endpointId, correlationToken)
            except:
                self.log.error('!! Error during Press', exc_info=True)
                return None


    class adapterProcess(adapterbase):
    
        def __init__(self, log=None, dataset=None, notify=None, loop=None, **kwargs):
            self.dataset=dataset
            self.config=self.dataset.config
            self.log=log
            self.definitions=definitions.elkDefinitions
            self.notify=notify
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            
            
        async def start(self):

            try:
                self.elkClient = Client(loop=self.loop, log=self.log, notify=self.notify, dataset=self.dataset)
                await self.loop.create_connection(lambda: self.elkClient, self.config["elk_address"], self.config["elk_port"])

            except:
                self.log.error('Error', exc_info=True)

        async def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="zone":
                    return self.addSmartZone(path.split("/")[2])
                elif path.split("/")[1] in ["task","output"]:
                    return self.addSmartButton(path.split("/")[2],path.split("/")[1])
            except:
                self.log.error('Error defining smart device', exc_info=True)


        def addSmartZone(self, deviceid):
            
            try:
                nativeObject=self.dataset.nativeDevices['zone'][deviceid]
                if 'name' not in nativeObject:
                    #self.log.info('Name info not present for %s' % deviceid)
                    return False
                if nativeObject['name'] not in self.dataset.localDevices:
                    if nativeObject["zonetype"].find("Temperature")>-1:
                        device=devices.alexaDevice('elk/zone/%s' % deviceid, nativeObject['name'], displayCategories=['TEMPERATURE_SENSOR'], adapter=self)
                        device.TemperatureSensor=elkm1.TemperatureSensor(device=device)
                        device.EndpointHealth=elkm1.EndpointHealth(device=device)
                        return self.dataset.newaddDevice(device)
                    elif nativeObject["zonetype"].find("Burglar")==0 or nativeObject["zonetype"].find("Non Alarm")==0:
                        if nativeObject["mode"]=="motion":
                            description='Elk Motion Sensor'
                            if nativeObject['name'] in self.dataset.config['automation']:
                                description+=' (Automation)'
                            device=devices.alexaDevice('elk/zone/%s' % deviceid, nativeObject['name'], displayCategories=['MOTION_SENSOR'], adapter=self, description=description)
                            device.MotionSensor=elkm1.MotionSensor(device=device)
                            device.EndpointHealth=elkm1.EndpointHealth(device=device)
                            return self.dataset.newaddDevice(device)
                        if nativeObject["mode"]=="doorbell":
                            device=devices.alexaDevice('elk/zone/%s' % deviceid, nativeObject['name'], displayCategories=['DOORBELL'], adapter=self, )
                            device._noAlexaInterface=True # Quirks mode shit for doorbell should probably be moved up into flexdevice def
                            device.DoorbellEventSource=devices.DoorbellEventSource(device=device)
                            return self.dataset.newaddDevice(device)
                        else:
                            description='Contact Sensor'
                            if nativeObject['name'] in self.dataset.config['automation']:
                                description+=' (Automation)'
                            device=devices.alexaDevice('elk/zone/%s' % deviceid, nativeObject['name'], displayCategories=['CONTACT_SENSOR'], adapter=self, description=description)
                            device.ContactSensor=elkm1.ContactSensor(device=device)
                            device.EndpointHealth=elkm1.EndpointHealth(device=device)
                            return self.dataset.newaddDevice(device)
                    else:
                        self.log.info('Zonetype no match for %s' % nativeObject['zonetype'])
                        
                return False

            except:
                self.log.error('Error adding Smart Zone  %s' % deviceid, exc_info=True)

        def addSmartButton(self, deviceid, buttontype):
            
            try:
                nativeObject=self.dataset.nativeDevices[buttontype][deviceid]
                #if 'name' not in nativeObject:
                if 'name' not in nativeObject or 'status' not in nativeObject:
                    #self.log.info('Name info not present for %s' % deviceid)
                    return False
                if nativeObject['name'] not in self.dataset.localDevices:
                    device=devices.alexaDevice('elk/%s/%s' % (buttontype,deviceid), nativeObject['name'], displayCategories=['BUTTON'], adapter=self)
                    device.ButtonController=elkm1.ButtonController(device=device)
                    device.EndpointHealth=elkm1.EndpointHealth(device=device)
                    return self.dataset.newaddDevice(device)
            except:
                self.log.error('Error adding Smart Button %s' % deviceid, exc_info=True)


        def virtualEventSource(self, itempath, item):
            try:
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))

                if "mode" in nativeObject:
                    if nativeObject["mode"]=="doorbell":
                        if item['value']=='Violated':
                            device=self.dataset.getDeviceFromPath(itempath)
                            if hasattr(device, "DoorbellEventSource"):
                                return device.DoorbellEventSource.press()
                            else:
                                self.log.info('Device does not seem to have a DoorbellEventSource: %s' % device.__dict__, exc_info=True)
                        
                    #self.log.info('Item: %s' % item)
            except:
                self.log.error('Error accessing virtual event source for %s' % nativeObject, exc_info=True)
  

        async def triggerTask(self, taskname):
            
            try:
                for task in self.dataset.nativeDevices['task']:
                    if self.dataset.nativeDevices['task'][task]['name']==taskname:
                        elkcmd="09tn"+task.zfill(3)+"00"
                        elkcmd=elkcmd+self.elkClient.computechecksum(elkcmd)
                        self.elkClient.queueForSend(elkcmd+"\r\n")
                        self.elkClient.checkSendQueue()    
                        break
            except:
                self.log.error('Error with triggerTask', exc_info=True)
        

        async def releaseOutput(self, outputId):
            
            # Control Output off (cf)
            # 09cfDDD00CC(CR-LF)
            # Example: turn off Control Output 2: 09cf00200DC(CR-LF )
            
            try:
                elkcmd="09cf"+outputId.zfill(3)+"00"
                elkcmd=elkcmd+self.elkClient.computechecksum(elkcmd)
                self.elkClient.queueForSend(elkcmd+"\r\n")
                self.elkClient.checkSendQueue()    
            except:
                self.log.error('Error with releasing Output: %s %s' (outputId,duration), exc_info=True)
 
        async def triggerOutput(self, outputId, duration=1):
            
            # 0EcnDDDTTTTT00CC(CR-LF)
            # Example: turn on Control Output 1 for 10 seconds: 0Ecn0010001000D8(CR-LF )
            
            try:
                elkcmd="0Ecn"+outputId.zfill(3)+str(duration).zfill(5)+"00"
                elkcmd=elkcmd+self.elkClient.computechecksum(elkcmd)
                self.elkClient.queueForSend(elkcmd+"\r\n")
                self.elkClient.checkSendQueue()    
            except:
                self.log.error('Error with trigger Output: %s %s' (outputId,duration), exc_info=True)
 

if __name__ == '__main__':
    adapter=elkm1(name="elk")
    adapter.start()
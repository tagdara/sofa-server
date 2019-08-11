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
import time
import datetime
import asyncio

import json
from alarmdecoder import AlarmDecoder
from alarmdecoder.devices import SerialDevice


class alarmd(sofabase):

    class adapterProcess(adapterbase):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.log=log
            self.notify=notify
            self.polltime=5
            self.watchdogTime=20

            self.faultedZones=[]
            self.dataset.nativeDevices['zones']={}

            self.lastMessageTime=datetime.datetime.now()
            self.lastMessage='Adapter Start'
            self.foundZones=[]
            self.panelOpen=False
            self.panelConnecting=False

            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop

        async def start(self):
            
            try:
                asyncio.set_event_loop(self.loop)
                self.log.info('Config: %s' % self.dataset.config)
                self.SERIAL_DEVICE = self.dataset.config["device"]
                self.BAUDRATE = self.dataset.config["baudrate"]
                self.createSerialDevice()
                #self.log.info('.. starting serial connection: %s at %s' % (self.SERIAL_DEVICE, self.BAUDRATE))
                self.connectPanel()
                await self.watchdog()
                
            except:
                self.log.error('Error starting alarmd', exc_info=True)
                
        def createSerialDevice(self):
            
            self.device = AlarmDecoder(SerialDevice(interface=self.SERIAL_DEVICE))
            # Set up an event handler and open the device
            self.device.on_message += self.handle_message
            self.device.on_open += self.handle_open
            self.device.on_close += self.handle_close
            self.device.on_zone_fault += self.handle_zone_fault
            self.device.on_zone_restore += self.handle_zone_restore
            self.device.on_rfx_message += self.handle_rfx
            #self.log.info('Self device is now: %s' % self.device)
            
        def destroySerialDevice(self):
            
            self.device=None
            #self.log.info('Self device is now: %s' % self.device)
        
        def connectPanel(self):
            try:
                if not self.panelConnecting:
                    self.panelConnecting=True
                    self.log.info('.. starting serial connection: %s at %s' % (self.SERIAL_DEVICE, self.BAUDRATE))
                    self.device.open(baudrate=self.BAUDRATE)
                    #self.log.info('Device state: %s' % self.device.__dict__)
            except:
                self.log.error('Error connecting to panel', exc_info=True)
            

        def disconnectPanel(self):

            try:
                self.log.info('Disconnecting from panel')
                self.device.close()
            except:
                self.log.error('Error disconnecting from panel', exc_info=True)
                
        def reconnectPanel(self):

            try:
                if not self.panelConnecting:
                    self.device.close()
                    self.destroySerialDevice()
                    self.createSerialDevice()
                    #self.disconnectPanel()
                    self.connectPanel()
            except:
                self.log.error('Error reconnecting to panel', exc_info=True)
                
        
        async def watchdog(self):
        
            while True:
                try:
                    delta = datetime.datetime.now()-self.lastMessageTime

                    
                    if not self.panelOpen and not self.panelConnecting:
                        self.log.warn('!! Watchdog found panel is no longer connected.  Attempting reconnect.')
                        self.lastMessageTime=datetime.datetime.now()
                        self.reconnectPanel()
                    
                    elif delta.seconds>self.watchdogTime and not self.panelConnecting:
                        self.log.warn('!! WARNING: %s seconds have elapses since last message from the panel: %s' % (delta, self.lastMessage))
                        self.lastMessageTime=datetime.datetime.now()
                        self.reconnectPanel()
                    
                    else:
                        self.log.debug('!! Last message: %s seconds ago: %s' % (delta, self.lastMessage))
                    #self.log.info("Polling bridge data")
                    await asyncio.sleep(self.watchdogTime)
                except:
                    self.log.error('Error with watchdog', exc_info=True)
           
            
        def compareZoneChanges(self, oldfaults, newfaults, message=''):
            
            try:
                for zone in newfaults:
                    #if zone not in self.foundZones:
                    #    self.foundZones.append(zone)
                    if zone not in oldfaults:
                        if str(zone) in self.dataset.config['zones']:
                            if self.dataset.config['zones'][str(zone)]['type']=='motion':
                                self.log.info('!! %s (%s) triggered  %s' % (self.dataset.config['zones'][str(zone)]['name'], zone, message))   
                            else:
                                self.log.info('!! %s (%s) now open  %s' % (self.dataset.config['zones'][str(zone)]['name'], zone, message))
                        else:
                            self.log.info('!! %s now open' % zone)

                for zone in oldfaults:
                    if zone not in newfaults:
                        if str(zone) in self.dataset.config['zones']:
                            if self.dataset.config['zones'][str(zone)]['type']!='motion':
                                self.log.info('.! %s (%s) now closed  %s' % (self.dataset.config['zones'][str(zone)]['name'], zone, message))
                            else:
                               self.log.debug('.! %s (%s) now reset  %s' % (self.dataset.config['zones'][str(zone)]['name'], zone, message))
                        else:
                            self.log.info('.! %s now closed  %s' % (zone, message))
            except:
                self.log.error('Error comparing Zone changes', exc_info=True)
        
        def handle_open(self, sender):
            
            self.log.info('.. Panel Connection Opened')
            self.lastMessageTime=datetime.datetime.now()
            self.lastMessage='Panel connected'
            self.panelOpen=True
            self.panelConnecting=False

        def handle_close(self, sender):
            
            self.log.info('!! Panel Connection Closed')
            self.lastMessageTime=datetime.datetime.now()
            self.lastMessage='Panel closed'

            self.panelOpen=False
            self.panelConnecting=False

        def handle_zone_fault(self, device, zone):
            
            self.log.debug('Zone Fault: %s %s ' % (zone, device._zonetracker.__dict__))

        def handle_zone_restore(self, device, zone):
            
            self.log.debug('Zone Restore: %s %s ' % (zone, device._zonetracker.__dict__))

        def handle_rfx(self, device, message):
            # some rf devices dont send fault when the system is not armed
            # this may be the key to some of the sloppy zone state tracking
            try:
                #self.log.info('RFX: %s %s %s %s' % (message.serial_number, (True in message.loop), message.loop, message.__dict__))
                found=False
                for dev in self.dataset.config['zones']:
                    if 'address' in self.dataset.config['zones'][dev] and self.dataset.config['zones'][dev]['address']==message.serial_number:
                        found=True
                        if 'loop' in self.dataset.config['zones'][dev]:
                            loopid=self.dataset.config['zones'][dev]['loop']
                        else:
                            loopid=0
                        if message.loop[loopid]:
                            zonestate=False
                            self.log.info('.. rfx %s open' % self.dataset.config['zones'][dev]['name'])
                        else:
                            zonestate=True
                            self.log.info('.. rfx %s closed' % self.dataset.config['zones'][dev]['name'])
                        asyncio.ensure_future(self.dataset.ingest({"zones": { dev : {**self.dataset.config['zones'][dev], **{'status': zonestate}} }}), loop=self.loop)                        

                if not found:
                    self.log.info('.. rfx %s unknown device %s %s' % (message.serial_number, message.loop, message.__dict__))
                
            except:
                self.log.error('Error with rfx', exc_info=True)


        def handle_message(self, sender, message):
            # Handles message events from the AlarmDecoder.

            try:
                self.lastMessage=message
                #self.log.info('Message: %s' % message)
                self.lastMessageTime=datetime.datetime.now()
                #self.log.info('faulted: %s %s' % (self.faultedZones, sender._zonetracker._zones_faulted))
                if self.faultedZones!=sender._zonetracker._zones_faulted:
                    fzones=[]
                    self.compareZoneChanges(self.faultedZones, list(sender._zonetracker._zones_faulted), message)
                    for zone in sender._zonetracker._zones_faulted:
                        if str(zone) in self.dataset.config['zones']:
                            fzones.append('%s (%s)' % (self.dataset.config['zones'][str(zone)]['name'], zone))
                        else:
                            fzones.append(zone)
                    self.log.debug('!! Faulted zones: %s' % fzones)
                    for zone in self.dataset.config['zones']:
                        #self.log.info('Checking zone %s (%s)' % (zone, self.dataset.nativeDevices['zones'][zone]))
                        zonestate=int(zone) not in sender._zonetracker._zones_faulted
                        asyncio.ensure_future(self.dataset.ingest({"zones": { zone : {**self.dataset.config['zones'][zone], **{'status': zonestate}} }}), loop=self.loop)                        
                    
                    self.faultedZones=list(sender._zonetracker._zones_faulted)
                #self.lastmessage=message.raw
            except:
                self.log.error('Error handling message', exc_info=True)


        def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="zones":
                    return self.addZone(path.split("/")[2])
                    
                else:
                    self.log.info('No known device type for %s' % path)

            except:
                self.log.error('Error defining smart device: %s' % path, exc_info=True)
                return None


        async def addZone(self, deviceid):
            
            nativeObject=self.dataset.nativeDevices['zones'][deviceid]
            if nativeObject['name'] not in self.dataset.devices:
                if nativeObject["type"] in ["contact"]:
                    return self.dataset.addDevice(nativeObject['name'], devices.ContactSensorDevice('alarmd/zones/%s' % deviceid, nativeObject['name']))
                    #return self.dataset.addDevice(nativeObject['name'], devices.simpleZone('alarmd/zones/%s' % deviceid, nativeObject['name']))
                elif nativeObject["type"] in ["motion"]:
                    #return self.dataset.addDevice(nativeObject['name'], devices.simpleZone('alarmd/zones/%s' % deviceid, nativeObject['name']))
                    return self.dataset.addDevice(nativeObject['name'], devices.MotionSensorDevice('alarmd/zones/%s' % deviceid, nativeObject['name']))            
            return False


        def virtualControllers(self, itempath):

            try:
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                self.log.debug('Checking object for controllers: %s' % nativeObject)
                
                try:
                    detail=itempath.split("/",3)[3]
                except:
                    detail=""
                    
                controllerlist={}
                #if detail=="":
                #    controllerlist["ZoneSensor"]=["position","type"]
                ##else:
 
                if nativeObject["type"]=="motion":
                    if detail=="status" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist,"MotionSensor","detectionState")
                elif nativeObject["type"]=="contact":
                    if detail=="status" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist,"ContactSensor","detectionState")

                return controllerlist
            except:
                self.log.error('Error getting virtual controller types for %s' % nativeObj, exc_info=True)
                    

        def virtualControllerProperty(self, nativeObj, controllerProp):
            
            try:
                if controllerProp=='detectionState':
                    if nativeObj['status']:
                        return 'NOT_DETECTED'
                    else:
                        return 'DETECTED'


                if controllerProp=='position':
                    if nativeObj['status']:
                        return 'closed'
                    else:
                        return 'open'
                        
                if controllerProp=='type':
                    if nativeObj['intrusion']:
                        return 'Alarm'
                    else:
                        return 'Automation'

                else:
                    self.log.info('Unknown controller property mapping: %s' % controllerProp)
                    return {}
            except:
                self.log.error('Error converting virtual controller property: %s %s' % (controllerProp, nativeObj), exc_info=True)



if __name__ == '__main__':
    adapter=alarmd(name='alarmd')
    adapter.start()

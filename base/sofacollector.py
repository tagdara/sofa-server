import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))

from sofabase import sofabase
from sofabase import adapterbase

import asyncio
import aiohttp
from aiohttp import web
import concurrent.futures
import logging
import sys
import time
import json
import collections
import copy
import datetime
import uuid
import devices
import dpath

class SofaCollector(sofabase):

    # This is a variant of sofabase that listens for other adapters and collects information.  Generally this would be used for
    # UI, Logic, or other modules where state tracking of devices is important
        
    class collectorAdapter(adapterbase):

        @property
        def collector(self):
            return True

        @property
        def collector_categories(self):
            return ['ALL']

        async def discoverAdapterDevices(self, url):
            
            try:
                async with aiohttp.ClientSession() as client:
                    response=await client.get('%s/discovery' % url)
                    result=await response.read()
                    return json.loads(result.decode())
                    
            except aiohttp.client_exceptions.ClientConnectorError:
                self.log.warn('Error discovering adapter devices - adapter not ready: %s' % url)
            except:
                self.log.error('Error discovering adapter devices: %s' % url, exc_info=True)
                return {}
    
        def getDeviceByfriendlyName(self, friendlyName):
        
            for device in self.dataset.devices:
                if self.dataset.devices[device]['friendlyName']==friendlyName:
                    return self.dataset.devices[device]
                
            return None
        
        def getfriendlyNamebyendpointId(self, endpointId):
        
            for device in self.dataset.devices:
                if self.dataset.devices[device]['endpointId']==endpointId:
                    return self.dataset.devices[device]['friendlyName']
                
            return None
            
        def getDeviceByEndpointId(self, endpointId):
            
            for device in self.dataset.devices:
                if self.dataset.devices[device]['endpointId']==endpointId:
                    return self.dataset.devices[device]
                
            return None
            
        def getObjectsByDisplayCategory(self, category):
            
            devicelist=[]
            for device in self.dataset.devices:
                try:
                    if category.upper() in self.dataset.devices[device].displayCategories:
                        devicelist.append(self.dataset.devices[device])
                    else:
                        self.log.info('%s not in %s' % (category.upper(), self.dataset.devices[device].displayCategories))
                except:
                    self.log.error('%s not?' % category.upper(), exc_info=True)
                
            return devicelist

        def shortLogChange(self, changereport):
            
            try:
                shortchange=changereport['event']['endpoint']['endpointId']
                for change in changereport['payload']['change']['properties']:
                    shortchange+=(' %s.%s=%s' % (change['namespace'].split('.')[1], change['name'], change['value']))
                return shortchange
            except:
                #self.log.error('Error with shortchange', exc_info=True)
                return changereport
                

        async def scrubDevicesOnStartup(self, adaptername):
            
            try:
                dead_devs=[]
                for dev in self.dataset.devices:
                    if dev.startswith("%s:" % adaptername):
                        dead_devs.append(dev)
                
                for dev in dead_devs:
                    del self.dataset.devices[dev]
                    self.log.debug('.. removing device on adapter restart: %s' % dev)
            
            except:
                self.log.error('Error scrubbing devices on adapter restart', exc_info=True)


        async def handleAddOrUpdateReport(self, message):

            try:
                devlist=message['event']['payload']['endpoints']
                if devlist:
                    await self.updateDeviceList(devlist)
                    eplist=[]
                    for dev in devlist:
                        eplist.append(dev['endpointId'])

                    stateReports=await self.dataset.requestReportStates(eplist)
                    #eplist=[]
                    #for dev in devlist:
                    #    eplist.append(dev['friendlyName'])
                        #self.log.info('++ device added from mqtt: %s' % eplist)
                    #    stateReport=await self.dataset.requestReportState(dev['endpointId'], cookie={"adapter": self.dataset.adaptername})
                        #self.log.info('++ device updated from mqtt: %s' % stateReport)

            except:
                self.log.error('Error handling AddorUpdate: %s' % message , exc_info=True)

        async def updateDeviceList(self, objlist):
            
            for obj in objlist:
                try:
                    self.dataset.devices[obj['endpointId']]=obj
                    #self.dataset.devices[obj['friendlyName']]=obj
                    if hasattr(self, "virtualAddDevice"):
                        await self.virtualAddDevice(obj['endpointId'], obj)
                        #await self.virtualAddDevice(obj['friendlyName'], obj)

                except:
                    self.log.error('Error updating device list: %s' % objlist[obj],exc_info=True)


        async def handleStateReport(self, message):
            
            #self.log.info('.. handleStateReport - Is this still needed? %s' % message)
            pass

        async def handleResponse(self, message):
            
            #self.log.info('.. handleChangeReport - Is this still needed? %s' % message)
            try:
                if not message:
                    return {}

                if 'log_change_reports' in self.dataset.config:
                    if self.dataset.config['log_change_reports']==True:
                        self.log.info('Response Prop: %s' % message)
                if 'context' in message and 'properties' in message['context']:
                    # Certain responses like the CameraStream do not include context
                    for prop in message['context']['properties']:
                        if hasattr(self, "virtualChangeHandler"):
                            # This is mostly just for logic but other adapters could hook this eventually
                            await self.virtualChangeHandler(message['event']['endpoint']['endpointId'], prop)
            except:
                self.log.error('Error processing Change Report', exc_info=True)

        async def handleAlexaEvent(self, message):
            
            try:
                self.log.info('Event detected: %s' % message)
                eventtype=message['event']['header']['name']
                endpointId=message['event']['endpoint']['endpointId']
                source=message['event']['header']['namespace'].split('.')[1]
                if hasattr(self, "virtualEventHandler"):
                    #self.log.info('Adapter has virtualeventhandler')
                    await self.virtualEventHandler(eventtype, source, endpointId, message)
            except:
                self.log.error('Error handling Alexa Event', exc_info=True)

        async def handleDeleteReport(self, message):
            
            try:
                if not message:
                    return {}
                    
                if 'event' not in message or 'payload' not in message['event']:
                    self.log.error('Error: invalid delete report - has no event or event/payload: %s' % message)
                    return {}
                    
                self.log.info('<< Delete Report: %s' % message)
                        
                for prop in message['event']['payload']['endpoints']:
                    if prop['endpointId'] in self.dataset.devices:
                        #self.log.info('-- Removing device: %s %s' % (prop['endpointId'], self.dataset.devices[prop['endpointId']]))
                        del self.dataset.devices[prop['endpointId']]
                    if hasattr(self, "virtualDeleteHandler"):
                        await self.virtualDeleteHandler(prop['endpointId'])
            except:
                self.log.error('Error handing deletereport: %s' % message, exc_info=True)


        async def handleChangeReport(self, message):
            
            try:
                if 'log_change_reports' in self.dataset.config:
                    if self.dataset.config['log_change_reports']==True:
                        self.log.info('.. Change Report Prop: %s' % self.shortLogChange(message))
                        
                for prop in message['event']['payload']['change']['properties']:
                    if hasattr(self, "virtualChangeHandler"):
                        # This is mostly just for logic but other adapters could hook this eventually
                        await self.virtualChangeHandler(message['event']['endpoint']['endpointId'], prop)
            except:
                self.log.error('Error processing Change Report', exc_info=True)
                return {}
                
                
        async def sendAlexaCommand(self, command, controller, endpointId, payload={}, cookie={}, trigger={}):
            
            try:
                header={"name": command, "namespace":"Alexa." + controller, "payloadVersion":"3", "messageId": str(uuid.uuid1()), "correlationToken": str(uuid.uuid1())}
                endpoint={"endpointId": endpointId, "cookie": cookie, "scope":{ "type":"BearerToken", "token":"access-token-from-skill" }}
                data={"directive": {"header": header, "endpoint": endpoint, "payload": payload }}
                report=await self.dataset.sendDirectiveToAdapter(data)
                return report
            except:
                self.log.error('Error executing Alexa Command: %s %s %s %s' % (command, controller, endpointId, payload), exc_info=True)
                return {}


        async def process_event(self, message, source=None):
            
            # Only Collector modules should need to handle Event messages
            try:
                if 'event' in message:
                    try:
                        if message['event']['endpoint']['endpointId'].split(":")[0]==self.dataset.adaptername:
                            return False
                    except KeyError:
                        pass

                    if 'correlationToken' in message['event']['header']:
                        try:
                            if message['event']['header']['correlationToken'] in self.pendingRequests:
                                self.pendingResponses[message['event']['header']['correlationToken']]=message
                                self.pendingRequests.remove(message['event']['header']['correlationToken'])
                        except:
                            self.log.error('Error handling a correlation token response: %s ' % message, exc_info=True)
    
                    elif message['event']['header']['name']=='DoorbellPress':
                        if hasattr(self, "handleAlexaEvent"):
                            await self.handleAlexaEvent(message)
                
                    elif message['event']['header']['name']=='StateReport':
                        if hasattr(self, "handleStateReport"):
                            await self.handleStateReport(message)
    
                    elif message['event']['header']['name']=='ChangeReport':
                        if hasattr(self, "handleChangeReport"):
                            await self.handleChangeReport(message)
    
                    elif message['event']['header']['name']=='DeleteReport':
                        if hasattr(self, "handleDeleteReport"):
                            await self.handleDeleteReport(message)
                    
                    elif message['event']['header']['name']=='AddOrUpdateReport':
                        if hasattr(self, "handleAddOrUpdateReport"):
                            await self.handleAddOrUpdateReport(message)

                    else:
                        self.log.info('Message type not processed: %s' % message['event']['header']['name'])
                    
            except:
                self.log.error('Error processing MQTT Message', exc_info=True)




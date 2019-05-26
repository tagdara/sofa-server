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
                
        async def handleAdapterAnnouncement(self, adapterdata, patch=[]):
            
            for adapter in adapterdata:
                try:
                    if patch:
                        devlist={}
                        for change in patch:
                            if change['op']=='add':
                                self.log.info('.. mqtt adapter discovered: %s (%s)' % (adapter, adapterdata[adapter]['url']))
                                if hasattr(self, "virtualAddAdapter"):
                                    await self.virtualAddAdapter(adapter, adapterdata[adapter])
                                devlist=await self.discoverAdapterDevices(adapterdata[adapter]['url'])
                                break
                            elif change['path']=='/%s/startup' % adapter:
                                self.log.info('.. mqtt adapter %s startup time change. Scanning for new devices' % adapter)
                                if hasattr(self, "virtualUpdateAdapter"):
                                    await self.virtualUpdateAdapter(adapter, adapterdata[adapter])
                                devlist=await self.discoverAdapterDevices(adapterdata[adapter]['url'])
                                break
                                
                        if devlist:
                            eplist=[]
                            for dev in devlist:
                                eplist.append(dev['friendlyName'])
                            self.log.info('++ devices added from %s: %s' % (adapter, eplist))
                            await self.updateDeviceList(devlist)
                except:
                    self.log.error('Error handling announcement: %s ' % adapterdata[adapter], exc_info=True)

        async def handleAddOrUpdateReport(self, devlist):

            try:
                if devlist:
                    await self.updateDeviceList(devlist)
                    eplist=[]
                    for dev in devlist:
                        eplist.append(dev['friendlyName'])
                        #self.log.info('++ device added from mqtt: %s' % eplist)
                        stateReport=await self.dataset.requestReportState(dev['endpointId'])
                        #self.log.info('++ device updated from mqtt: %s' % stateReport)

            except:
                self.log.error('Error handling AddorUpdate: %s' % objlist , exc_info=True)

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
        
        async def oldhandleStateReport(self, message):
            
            try:
                #self.log.info('Received State Report: %s' % message['event']['endpoint']['endpointId'])
                if self.dataset.getDeviceByEndpointId(message['event']['endpoint']['endpointId']):
                    self.log.debug('Props: %s' % message['context']['properties'])
                    for prop in message['context']['properties']:
                        devname=self.getDeviceByEndpointId(message['event']['endpoint']['endpointId'])['friendlyName']
                        field="discovery/%s/%s/%s" % (devname, prop['namespace'].split(".")[1], prop['name'])
                        self.log.debug('Field: %s' % field)
                        if self.dataset.getObjectFromPath(field, self.dataset.data['cache'])!={}:
                        #if field in self.dataset.data['cache']:
                            dpath.util.set(self.dataset.data, "cache/%s" % field, prop['value'])
                        else:
                            self.log.debug('%s was not in %s' % (field, self.dataset.data['cache']))

            except:
                self.log.error('Error updating from state report: %s' % message, exc_info=True)
        
        async def handleResponse(self, message):
            
            #self.log.info('.. handleChangeReport - Is this still needed? %s' % message)
            try:
                if not message:
                    return {}

                if 'log_change_reports' in self.dataset.config:
                    if self.dataset.config['log_change_reports']==True:
                        self.log.info('Response Prop: %s' % message)
                if 'properties' in message['context']:     
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


        async def oldhandleResponse(self, message):
            try:
                if not message:
                    return None

                device=self.getDeviceByEndpointId(message['event']['endpoint']['endpointId'])
                
                # I'm no longer sure what this was designed to do, maybe create the shor
                for prop in message['context']['properties']:
                    field="discovery/%s/%s/%s" % (message['event']['endpoint']['cookie']['name'], prop['namespace'].split(".")[1], prop['name'])
                    self.log.debug('Field: %s' % field)
                    if self.dataset.getObjectFromPath(field, self.dataset.data['cache'])!={}:
                        dpath.util.set(self.dataset.data, "cache/%s" % field, prop['value'])
                    else:
                        self.log.debug('%s was not in %s' % (field, self.dataset.data['cache']))
                        
                self.log.info('dataset data is now: %s' % self.dataset.data)
            except:
                self.log.error('Error updating from state report', exc_info=True)


        async def handleChangeReport(self, message):
            
            try:
                if not message:
                    return {}
                    
                # if 'log_change_reports' in self.dataset.config:
                #    if self.dataset.config['log_change_reports']==True:
                #        self.log.info('.. ChangeReport: %s' % message)
                
                if 'payload' in message:
                    self.log.error('Error: adapter generating malformed changereports for %s and should be upgraded.' % message['event']['endpoint']['endpointId'])
                    return {}
                    
                if 'event' not in message or 'payload' not in message['event']:
                    self.log.error('Error: invalid change report - has no event or event/payload: %s' % message)
                    return {}
                    
                if 'change' not in message['event']['payload']:
                    self.log.error('Error: invalid change report - %s has no changes' % message['event']['endpoint']['endpointId'])
                    return {}
                    
                if 'log_change_reports' in self.dataset.config:
                    if self.dataset.config['log_change_reports']==True:
                        self.log.info('Change Report Prop: %s' % self.shortLogChange(message))
                        
                for prop in message['event']['payload']['change']['properties']:
                    if hasattr(self, "virtualChangeHandler"):
                        # This is mostly just for logic but other adapters could hook this eventually
                        await self.virtualChangeHandler(message['event']['endpoint']['endpointId'], prop)
            except:
                self.log.error('Error processing Change Report', exc_info=True)

        async def oldhandleChangeReport(self, message):
            
            try:
                if not message:
                    return None
                if 'log_change_reports' in self.dataset.config:
                    if self.dataset.config['log_change_reports']==True:
                        self.log.info('Change Report: %s' % self.shortLogChange(message))
                device=self.getDeviceByEndpointId(message['event']['endpoint']['endpointId'])

                if not device:
                    self.log.info('Did not find %s in %s' % (message['event']['endpoint']['endpointId'], self.dataset.devices))
                    return None
                
                #self.log.info('Received Change Report: %s %s' % (device['friendlyName'], message))
                try:
                    for prop in message['payload']['change']['properties']:
                        field="discovery/%s/%s/%s" % (device['friendlyName'], prop['namespace'].split(".")[1], prop['name'])
                        if self.dataset.getObjectFromPath(field, self.dataset.data['cache'])!={}:
                            dpath.util.set(self.dataset.data, "cache/%s" % field, prop['value'])
                        else:
                            self.log.debug('%s was not in %s' % (field, self.dataset.data['cache']))
                        
                        if hasattr(self, "virtualChangeHandler"):
                            await self.virtualChangeHandler(device['friendlyName'], prop)
                except KeyError:
                    pass
                        
                # these should be unchanged but send em all right now to make sure
                for prop in message['context']['properties']:
                    field="discovery/%s/%s/%s" % (device['friendlyName'], prop['namespace'].split(".")[1], prop['name'])
                    self.log.debug('Field: %s' % field)
                    if self.dataset.getObjectFromPath(field, self.dataset.data['cache'])!={}:
                        dpath.util.set(self.dataset.data, "cache/%s" % field, prop['value'])
                    else:
                        self.log.debug('%s was not in %s' % (field, self.dataset.data['cache']))
                        
                            
            except:
                self.log.error('Error updating from state report', exc_info=True)

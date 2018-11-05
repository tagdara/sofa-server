#!/usr/bin/python3

import sys
sys.path.append('/opt/beta')

from sofabase import sofabase
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

    class collectorAdapter():
    
        async def discoverAdapterDevices(self, url):
            
            try:
                async with aiohttp.ClientSession() as client:
                    response=await client.get('%s/discovery' % url)
                    result=await response.read()
                    return json.loads(result.decode())
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
                
        async def handleAdapterAnnouncement(self, adapterdata, patch=[]):
            
            for adapter in adapterdata:
                try:
                    if patch:
                        devlist={}
                        for change in patch:
                            if change['op']=='add':
                                self.log.info('.. mqtt adapter discovered: %s (%s)' % (adapter, adapterdata[adapter]['url']))
                                devlist=await self.discoverAdapterDevices(adapterdata[adapter]['url'])
                                break
                            elif change['path']=='/%s/startup' % adapter:
                                self.log.info('.. mqtt adapter %s startup time change. Scanning for new devices' % adapter)
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
                    self.dataset.devices[obj['friendlyName']]=obj
                except:
                    self.log.error('Error updating device list: %s' % objlist[obj],exc_info=True)


        async def handleStateReport(self, message):
            
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


        async def handleChangeReport(self, message):
            
            try:
                if not message:
                    return None
                #self.log.info('Change Report: %s' % message)
                device=self.getDeviceByEndpointId(message['event']['endpoint']['endpointId'])

                if not device:
                    self.log.info('Did not find %s in %s' % (message['event']['endpoint']['endpointId'], self.dataset.devices))
                    return None
                
                #self.log.info('Received Change Report: %s %s' % (device['friendlyName'], message))

                for prop in message['payload']['change']['properties']:
                    field="discovery/%s/%s/%s" % (device['friendlyName'], prop['namespace'].split(".")[1], prop['name'])
                    if self.dataset.getObjectFromPath(field, self.dataset.data['cache'])!={}:
                        dpath.util.set(self.dataset.data, "cache/%s" % field, prop['value'])
                    else:
                        self.log.debug('%s was not in %s' % (field, self.dataset.data['cache']))
                        
                    if hasattr(self, "virtualChangeHandler"):
                        await self.virtualChangeHandler(device['friendlyName'], prop)
                        
                # these should be unchanged but send em all right now to make sure
                for prop in message['context']['properties']:
                    field="discovery/%s/%s/%s" % (message['event']['endpoint']['cookie']['name'], prop['namespace'].split(".")[1], prop['name'])
                    self.log.debug('Field: %s' % field)
                    if self.dataset.getObjectFromPath(field, self.dataset.data['cache'])!={}:
                        dpath.util.set(self.dataset.data, "cache/%s" % field, prop['value'])
                    else:
                        self.log.debug('%s was not in %s' % (field, self.dataset.data['cache']))
                        
                            
            except:
                self.log.error('Error updating from state report', exc_info=True)

                
        async def deprecated_handleSofaChanges(self, message):

            try:
                # Get the existing value to see if the key is already there
                existvalue=self.dataset.getObjectFromPath('/cache/%s' % message["path"])
                self.log.debug('Updating field in cache:  %s to %s' % (message['path'], message['value']))
                dpath.util.set(self.dataset.data, 'cache/%s' % message["path"], message["value"])
                await self.uiServer.wsBroadcast(json.dumps([message]))
            except KeyError:
                # Data not needed for clients if it hasn't already been requested
                #self.log.warn('Data not needed for clients: %s' % message['path'])
                pass
            
            except:
                self.log.error('Error handling Sofa Change: %s' % message, exc_info=True)

import asyncio
import aiohttp
from aiohttp import web
import concurrent.futures
import logging
import sys
import time
import json
import urllib.request
import collections
import jsonpatch
import copy
import dpath
import datetime
import uuid
import functools
import devices

import inspect

class sofaDataset():
        
    def __init__(self, log=None, adaptername="sofa", loop=None):
        self.startupTime=datetime.datetime.now()
        self.adaptername=adaptername
        self.data=collections.defaultdict(dict)
        self.localDevices={}
        self.nativeDevices={}
        self.devices={}
        self.adapters={}
        self.listdata={}
        self.controllers={}
        self.log=log
        self.loop=loop
        self.mqtt={}
        self.nodevices=[]

    def getDeviceFromPath(self, path):
            
        try:
            smartDevice=self.getDeviceByEndpointId("%s%s" % (self.adaptername, self.getObjectPath(path).replace("/",":")))
            return smartDevice
        except:
            self.log.error('Could not find device for path: %s' % path, exc_info=True)
            return None
   

    def getObjectPath(self, path):
            
        try:
            return "/%s/%s" % (path.split("/")[1], path.split("/")[2])
        except IndexError:
            return None
                
            
    def getObjectFromPath(self, path, data=None, trynames=False):
            
        try:
            if not path:
                return {}
                
            if not data:
                data=self.nativeDevices
                    

            for part in path.split("/")[1:]:
                try:
                    data=data[part]
                except (TypeError, KeyError):
                    if trynames:
                        result=None
                        for item in data:
                            try:
                                if data[item]['name']==part:
                                    result=data[item]
                            except:
                                pass
                                
                            try:
                                if item['friendlyName']==part:
                                    result=item
                            except:
                                pass
                                
                            try:
                                if item['endpointId']==part:
                                    result=item
                            except:
                                pass

                            try:
                                if 'interface' in item:
                                    self.log.info('Item interface: %s' % item['interface'])
                                if item['interface']==part:
                                    result=item['properties']['supported']
                            except:
                                pass

                                
                            if result:
                                self.log.info('Found match: %s %s' % (part, data))
                                break
                                
                        if not result:
                            return {}
                        data=result
                                
            return data
        
        except:
            self.log.error('Error getting object from path: %s' % path, exc_info=True)
            return {}


    def discovery(self):
    
        # respond to discovery with list of local devices
            
        disco=[]
        for dev in self.localDevices:
            disco.append(self.localDevices[dev].discoverResponse)
        return disco


    def addDevice(self, name, obj):
            
        # add a smart device from the devices object set to the local device list
            
        try:
            self.localDevices[name]=obj
            self.log.info('++ Added %s %s (%s)' % (obj.__class__.__name__, name, obj.endpointId))
            return self.localDevices[name]
        except:
            self.log.error('Error adding device: %s %s' % (name, obj))
            return False
            

    def getAllDevices(self):
    
        # return list of all local devices for this adapter
            
        devicelist=[]
        self.log.info('Local devices: %s' % self.localDevices.keys())
        for device in self.localDevices:
            devicelist.append(self.localDevices[device])
               
        return devicelist


    async def getList(self, listname, query={}):
        
        try:
            if listname in self.listdata:
                return self.listdata[listname]
            elif hasattr(self.adapter, "virtualList"):
                return await self.adapter.virtualList(listname, query)
            else:
                return {}
        except:
            self.log.error('Error getting list for: %s %s' % (listname))
            return {}
             

    def listIngest(self, listname, data):
    
        try:
            self.listdata[listname]=data
        except:
            self.log.error('Error ingesting list data: %s %s' % (listname, data), exc_info=true)

    def getDeviceByEndpointId(self, endpointId):
            
        for device in self.localDevices:
            if self.localDevices[device].endpointId==endpointId:
                return self.localDevices[device]
                
        return None
    
    def getDeviceByfriendlyName(self, friendlyName):
            
        for device in self.localDevices:
            if self.localDevices[device].friendlyName==friendlyName:
                return self.localDevices[device]
                
        return None


    def getObjectsByDisplayCategory(self, category):
            
        devicelist=[]
        for device in self.localDevices:
            try:
                if category.upper() in self.localDevices[device].displayCategories:
                    devicelist.append(self.localDevices[device])
            except:
                pass
                
        return devicelist


    async def getCategory(self, category):
            
        if category in self.data:
            return self.data[category]
        elif hasattr(self.adapter, "virtualCategory"):
            return await self.adapter.virtualCategory(category)
        else:
            return {}


    async def register(self, adapterdata):
            
        try:
            self.oldadapters = copy.deepcopy(self.adapters)
            dpath.util.merge(self.adapters, adapterdata, flags=dpath.util.MERGE_REPLACE)
            patch = jsonpatch.JsonPatch.from_diff(self.oldadapters, self.adapters)
            if hasattr(self.adapter, "handleAdapterAnnouncement"):
                #await self.adapter.handleAdapterAnnouncement(list(patch))
                await self.adapter.handleAdapterAnnouncement(adapterdata, list(patch))

        except:
            self.log.error('Error registering adapter to dataset: %s' % (adapterdata), exc_info=True)
             
    def nested_set(self, dic, keys, value):
        for key in keys[:-1]:
            dic = dic.setdefault(key, {})
        dic[keys[-1]] = value     
        
        
    async def updateObjectProperties(self, nativeObject, updateprops):
    
        try:
            # This takes a set of updated properties and applies them to the object
            # without deleting any props that were not referenced or changed.
            newprops=[]
            for i, oldprop in enumerate(nativeObject['state']):
                for prop in updateprops:
                    if oldprop['name']==prop['name']:
                        if oldprop['value']!=prop['value']:
                            nativeObject['state'][i]=prop
        
        except:
            self.log.error('Error updating properties', exc_info=True)
                            

    async def ingest(self, data, notify=True, overwriteLevel=None, returnChangeReport=True):
        
        try:
            # Take a copy of the existing data dictionary, use dpath to merge the updated content with the old, 
            # and then use jsonpatch to find the differences and report them.  Olddata retains the previous state
            # in case it is needed.
            self.oldNativeDevices = copy.deepcopy(self.nativeDevices)
            if overwriteLevel:
                self.nested_set(self.nativeDevices, overwriteLevel.split('/'), data )
            else:
                dpath.util.merge(self.nativeDevices, data, flags=dpath.util.MERGE_REPLACE)
            patch = jsonpatch.JsonPatch.from_diff(self.oldNativeDevices, self.nativeDevices)
            
            if patch:
                #self.log.info('Patch: %s' % patch)
                return await self.updateDevicesFromPatch(patch)
            return {}
                
        except:
            self.log.error('Error ingesting new data to dataset: %s' % data, exc_info=True)
            return {}

                
    async def updateDevicesFromPatch(self,data):
            
        try:
            updates=[]
            # Check to see if this is a new smart device that has not been added yet
            for item in data:
                if len(item['path'].split('/'))>2: # ignore root level adds
                    newDevice=False
                    update=None
                    if item['op']=='add':
                        if hasattr(self.adapter, "addSmartDevice"):
                            newDevice=await self.adapter.addSmartDevice(item['path'])
                            if newDevice:
                                update=await self.updateDeviceState(self.getObjectPath(item['path']), newDevice=newDevice, patch=item)
                                if update:
                                    self.log.info('new device update: %s' % update)
                                    updates.append(update)
                    else:
                        if hasattr(self.adapter, "virtualEventSource"):
                            event=self.adapter.virtualEventSource(item['path'], item)
                            if event:
                                self.log.info('[> mqtt event: %s' % event, exc_info=True)
                                await self.notify('sofa/updates',json.dumps(event))


                        update=await self.updateDeviceState(item['path'], newDevice=False, patch=item)
                        if update:
                            updates.append(update)
            return updates
        except:
            self.log.error('Error with controllermap: %s ' % item['path'], exc_info=True)

                      
    async def updateDeviceState(self, path, controllers={}, newDevice=False, correlationToken=None, patch=""):

        try:
            nativeObject=self.getObjectFromPath(self.getObjectPath(path))
            smartDevice=self.getDeviceByEndpointId("%s%s" % (self.adaptername, self.getObjectPath(path).replace("/",":")))

            if not smartDevice:
                if path not in self.nodevices:
                    self.log.info(".? No device for %s%s" % (self.adaptername, self.getObjectPath(path).replace("/",":")))
                    self.nodevices.append(path)
                # This device does not exist yet.  Some adapters may update out of order, and this change will be picked up
                # when the device is created.  This has the side effect of indicating when an adapter is putting up possible
                # devices that sofa is not handling, and might spam the logs.
                return False
            
            if not controllers:
                if hasattr(self.adapter, "virtualControllers"):
                    controllers=self.adapter.virtualControllers(path)
            
            unchanged=[]

            changecontrollers = copy.deepcopy(controllers)            
            for controller in changecontrollers:
                #self.log.info('Change in controller: %s %s' % (controller, controllers[controller]))
                for prop in changecontrollers[controller]:
                    try:
                        smartController=getattr(smartDevice,controller)
                        smartProp=getattr(smartController, prop)
                        try:
                            setattr(smartController, prop, self.adapter.virtualControllerProperty(nativeObject, prop))
                        except AttributeError:
                            self.log.warn('Not a settable property: %s/%s' % (controller, prop))
                        newProp=getattr(smartController, prop)
                        if newProp==smartProp:
                            self.log.debug("Property didn't change: %s.%s" % (controller, prop))
                            controllers[controller].remove(prop)
                            if not controllers[controller]:
                                del controllers[controller]
                            
                    except:
                        self.log.info('Invalid controller: %s/%s' % (controller, prop), exc_info=True)
            
            self.log.debug('Cleaned up Controllers: %s' % controllers)
            
            if controllers:
                changeReport=smartDevice.changeReport(controllers)
            else:
                changeReport=None
                
            if changeReport and not newDevice:
                try:
                    dev=self.getDeviceByEndpointId(changeReport['event']['endpoint']['endpointId'])
                    for prop in changeReport['payload']['change']['properties']:
                        self.log.info('[> mqtt change: %s %s %s %s %s' % (dev.friendlyName, dev.endpointId, prop['namespace'], prop['name'], prop['value'] ))
                except:
                    self.log.info('[> mqtt changereport: %s' % changeReport, exc_info=True)
                await self.notify('sofa/updates',json.dumps(changeReport))
                return changeReport
        
            elif newDevice:
                await self.notify('sofa/updates',json.dumps(smartDevice.addOrUpdateReport))
                return None
                #return smartDevice.addOrUpdateReport

        except:
            self.log.error('Error with update device state', exc_info=True)

                        
    def generateStateReport(self, endpointId, correlationToken='', bearerToken=''):
            
        try:
            if not correlationToken:
                correlationToken=str(uuid.uuid1())

            stateReport=self.getDeviceByEndpointId(endpointId).StateReport(correlationToken, bearerToken)
            #self.log.info('State report: %s' % stateReport)         
            return stateReport
        except:
            self.log.error('Error generating state report: %s' % path, exc_info=True)
            return {}

    async def generateResponse(self, endpointId, correlationToken, controller=''):
            
        try:
            return self.getDeviceByEndpointId(endpointId).Response(correlationToken, controller=controller)
        except:
            self.log.error('Error generating response: %s' % endpointId, exc_info=True)
            return {}

    async def requestReportState(self, endpointId, mqtt_topic=None, correlationToken='', bearerToken=''):
        
        try:
            if not correlationToken:
                correlationToken=str(uuid.uuid1())
                
            header={"name": "ReportState", "namespace":"Alexa", "payloadVersion":"3", "messageId": str(uuid.uuid1()), "correlationToken": correlationToken }
            endpoint={"endpointId": endpointId, "cookie": {}, "scope":{ "type":"BearerToken", "token":bearerToken }}
            data=json.dumps({"directive": {"header": header, "endpoint": endpoint, "payload": {}}})
            
            if mqtt_topic:
                return await self.mqttRequestReply(data, correlationToken, topic=mqtt_topic)
            
            else:
                adapter=endpointId.split(":")[0]
                if adapter in self.adapters:
                    url=self.adapters[adapter]['url']

                    headers = { "Content-type": "text/xml" }
                    #self.log.info('Requesting report state: %s' % endpointId)
                    async with aiohttp.ClientSession() as client:
                        response=await client.post(url, data=data, headers=headers)
                        statereport=await response.read()
                        statereport=json.loads(statereport.decode())
                        #self.log.info('report state response: %s' % statereport)
                        if statereport and hasattr(self.adapter, "handleStateReport"):
                            await self.adapter.handleStateReport(statereport)
                        return statereport
            
            self.log.warn('.! No State Report returned')            
            return {}

        except:
            self.log.error("Error requesting state for %s" % endpointId,exc_info=True)
            return {}

    async def requestReportStates(self, adapter, devicelist):
        
        try:
            if adapter in self.adapters:
                url=self.adapters[adapter]['url']+"/deviceStates"
                headers = { "Content-type": "text/xml" }
                #self.log.info('data: %s' % json.dumps(devicelist))
                #self.log.info('Requesting report states: %s %s %s' % (adapter, devicelist, url))
                async with aiohttp.ClientSession() as client:
                    response=await client.post(url, data=json.dumps(devicelist), headers=headers)
                    statereports=await response.read()
                    statereports=statereports.decode()
                    if statereports.startswith('{'):
                        statereports=json.loads(statereports)
                        return statereports
                    else:
                        self.log.info('Adapter not upgraded: %s %s %s %s' % (adapter, devicelist, url, statereports))
                        return {}

                        
            return {}

        except:
            self.log.error("Error requesting state for %s (%s)" % (adapter, devicelist),exc_info=True)
            return {}
               
    #async def requestAlexaStateChange(self, data):
    async def sendDirectiveToAdapter(self, data):
    
        try:
            changereport={}
            adapter=data['directive']['endpoint']['endpointId'].split(":")[0]
            directiveName=data['directive']['header']['name']
            url=self.adapters[adapter]['url']
            headers = { "Content-type": "text/xml" }
            self.log.info('>> %s to %s: %s' % (directiveName, adapter, data))
            
            #self.log.info('URL: %s, Headers: %s, Data: %s' % (url,headers,data))
            
            async with aiohttp.ClientSession() as client:
                response=await client.post(url, data=json.dumps(data), headers=headers)
                changereport=await response.read()
                if changereport and hasattr(self.adapter, "handleChangeReport"):
                    await self.adapter.handleChangeReport(json.loads(changereport.decode()))
                self.log.info('<< %s %s response: %s' % (adapter, directiveName, changereport.decode()))    
                return json.loads(changereport.decode())

        except:
            self.log.error("Error requesting state: %s" % data,exc_info=True)
        

    #async def handleStateChange(self, data):
    async def handleDirective(self, data):
        
        try:
            endpointId=data['directive']['endpoint']['endpointId']
            endpoint=data['directive']['endpoint']['endpointId'].split(":")[2]
            controller=data['directive']['header']['namespace'].split('.')[1]
            command=data['directive']['header']['name']
            payload=data['directive']['payload']
            correlationToken=data['directive']['header']['correlationToken']
            cookie=data['directive']['endpoint']['cookie']
                
            #device=self.getDeviceByEndpointId(endpointId)
    
            changeReports=[]
            
            if hasattr(self.adapter, "nativeAlexaStateChange"):
                self.log.info('This adapter is using the deprecated nativeAlexaStateChange and should be moved to processDirective')
                changeReports=await self.adapter.nativeAlexaStateChange(data)
            elif hasattr(self.adapter, "processDirective"):
                response=await self.adapter.processDirective(endpointId, controller, command, payload, correlationToken=correlationToken, cookie=cookie)
                return response
            elif hasattr(self.adapter, "stateChange"):
                self.log.info('This adapter is using the deprecated stateChange and should be moved to processDirective')
                changeReports=await self.adapter.stateChange(endpointId, controller, command, payload)

            if changeReports:
                for report in changeReports:
                    try:
                        if report==None:
                            self.log.info('No change report.  I blame dpath.merge for not getting deep key changes.')
                        elif report['event']['endpoint']['endpointId']==data['directive']['endpoint']['endpointId']:
                            return report
                    except:
                        self.log.info('Poorly formatted change report skipped: %s' % report, exc_info=True)
            
        except:
            self.log.error('Error handling directive', exc_info=True)
        
        return {}

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
        self.restTimeout=20

    def getDeviceFromPath(self, path):
            
        try:
            return self.getDeviceByEndpointId("%s%s" % (self.adaptername, self.getObjectPath(path).replace("/",":")))
        except:
            self.log.error('Could not find device for path: %s' % path, exc_info=True)
            return None
   

    def getObjectPath(self, path):
            
        try:
            return "/%s/%s" % (path.split("/")[1], path.split("/")[2])
        except IndexError:
            return None
            
    def getNativeFromPath(self, path):

        try:
            data=self.nativeDevices
            for part in path.split("/")[1:]:
                data=data[part]
            return data
                    
        except:
            self.log.info('Error getting native from path', exc_info=True)
        
    def getNativeFromEndpointId(self, endpointId):
            
        try:
            return endpointId.split(":")[2]
        except:
            return False               
            
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
                            self.log.info('data: %s vs %s' % (item, part))
                            try:
                                if data[item]['name']==part:
                                    result=data[item]
                            except:
                                pass
                                
                            try:
                                if item['friendlyName']==part or item['endpointId']==part:
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
            
            #self.log.info('Path: %s %s' % (path,data))                    
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

    def deleteDevice(self, name):
            
        # add a smart device from the devices object set to the local device list
            
        try:
            self.log.info('devices: %s' % self.devices)
            if name in self.localDevices:
                del self.localDevices[name]
            else:
                for dev in self.localDevices:
                    if self.localDevices[dev].endpointId==name or self.localDevices[dev].friendlyName==name:    
                        del self.localDevices[dev]
                        break

            if name in self.devices:
                del self.devices[name]

            else:
                for dev in self.devices:
                    if self.devices[dev].endpointId==name or self.devices[dev].friendlyName==name:    
                        del self.devices[dev]
                        break
            
            return True
        except:
            self.log.info('Localdevs: %s' % self.localDevices)
            self.log.error('Error deleting device: %s' % (name), exc_info=True)
            return False

    def addDevice(self, name, obj):
            
        # add a smart device from the devices object set to the local device list
            
        try:
            self.localDevices[name]=obj
            #self.log.info('++ Added %s %s (%s)' % (obj.__class__.__name__, name, obj.endpointId))
            return self.localDevices[name]
        except:
            self.log.error('Error adding device: %s %s' % (name, obj))
            return False

    def newaddDevice(self, obj):
            
        # add a smart device from the devices object set to the local device list
            
        try:
            self.localDevices[obj.friendlyName]=obj
            #self.log.info('** Added %s %s (%s)' % (obj.__class__.__name__, obj.friendlyName, obj.endpointId))
            return self.localDevices[obj.friendlyName]
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
        
        # first check devices that are local to this adapter
        for device in self.localDevices:
            if self.localDevices[device].endpointId==endpointId:
                return self.localDevices[device]
        
        # now check other devices for collector type adapters
        for device in self.devices:
            try:
                if self.devices[device]['endpointId']==endpointId:
                    return self.devices[device]
            except:
                self.log.error('Error with %s' % self.devices[device], exc_info=True)
                
        return None
    
    def getDeviceByfriendlyName(self, friendlyName):
            
        for device in self.localDevices:
            try:
                if self.localDevices[device].friendlyName==friendlyName:
                    return self.localDevices[device]
            except:
                pass
                
        # now check other devices for collector type adapters
        for device in self.devices:
            if self.devices[device]['friendlyName']==friendlyName:
                return self.devices[device]
                
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

    async def getAllDirectives(self):

        # Walks through the list of current devices, identifies their controllers and extracts a list of 
        # possible directives for each controller and outputs the full list.

        directives={}

        try:
            for device in self.devices:
                for cap in self.devices[device]['capabilities']:
                    if len(cap['interface'].split('.')) > 1:
                        capname=cap['interface'].split('.')[1]
                        if capname not in directives:
                            try:
                                controllerclass = getattr(devices, capname)
                                xc=controllerclass()
                                try:
                                    directives[capname]=xc.directives
                                except AttributeError:
                                    directives[capname]={}
                                xc=None
                            except:
                                self.log.error('Error with getting directives from controller class: %s' % capname, exc_info=True)

        except:
            self.log.error('Error creating list of Alexa directives', exc_info=True)
        
        return directives
    
    async def getAllProperties(self):

        properties={}
        try:
            for device in self.devices:
                for cap in self.devices[device]['capabilities']:
                    if len(cap['interface'].split('.')) > 1:
                        capname=cap['interface'].split('.')[1]
                        if capname not in properties:
                            try:
                                controllerclass = getattr(devices, capname)
                                xc=controllerclass()
                                try:
                                    properties[capname]=xc.props
                                except AttributeError:
                                    properties[capname]={}
                                xc=None
                            except:
                                self.log.error('Error with getting properties from controller class', exc_info=True)
        except:
            self.log.error('Error creating list of Alexa properties', exc_info=True)
            
        return properties
       
       
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
        try:
            x=""
            for key in keys[:-1]:
                if key:
                    dic = dic.setdefault(key, {})
                    x=x+key+"."
            dic[keys[-1]] = value
            x=x+"%s=%s" % (keys[-1],value)
            #self.log.info('nested set: %s' % x)
        except:
            self.log.error('Error in nested_set', exc_info=True)
        
        
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
                            

    async def checkDevicesForChanges(self, patch, oldDevicePropertyStates):
        
        try:
            done=[]
            for item in patch:
                if len(item['path'].split('/'))<3:
                    # ignore top level category adds
                    continue
                if item['op']=='add' and hasattr(self.adapter, "addSmartDevice"):
                    smartDevice=await self.adapter.addSmartDevice(item['path'])
                    if smartDevice:
                        self.log.info('++ AddOrUpdateReport: %s (%s)' % (smartDevice.friendlyName, smartDevice.endpointId))
                        #self.log.info('++ AddOrUpdateReport: %s (%s) %s' % (smartDevice.friendlyName, smartDevice.endpointId, smartDevice.addOrUpdateReport))
                        self.notify('sofa/updates',json.dumps(smartDevice.addOrUpdateReport))
                        done.append(smartDevice.endpointId) 
                else:
                    smartDevice=self.getDeviceByEndpointId("%s%s" % (self.adaptername, self.getObjectPath(item['path']).replace("/",":")))
                    # Why the fuck are we using friendly names for keys in local devices instead of endpoint id's?
                    #if smartDevice and smartDevice.endpointId in oldDevicePropertyStates:
                    if smartDevice and smartDevice.endpointId not in done and smartDevice.friendlyName in oldDevicePropertyStates:
                        newdev={}
                        olddev={}
                        for prop in smartDevice.propertyStates: 
                            newdev[prop['namespace']+'.'+prop['name']]=prop
                        for prop in oldDevicePropertyStates[smartDevice.friendlyName]:
                            olddev[prop['namespace']+'.'+prop['name']]=prop
                        controllers={}
                        for prop in newdev:
                            # We may need to walk through the resulting dictionary for values that have a dict
                            if newdev[prop]['value']!=olddev[prop]['value']:
                                if newdev[prop]['namespace'] not in controllers:
                                    controllers[newdev[prop]['namespace']]=[]
                                controllers[newdev[prop]['namespace']].append(newdev[prop]['name'])

                        if controllers:
                            changeReport=smartDevice.changeReport(controllers)
                            if changeReport:
                                try:
                                    for prop in changeReport['event']['payload']['change']['properties']:
                                        self.log.info('[> mqtt change: %s %s %s %s %s' % (smartDevice.friendlyName, smartDevice.endpointId, prop['namespace'], prop['name'], prop['value'] ))
                                except:
                                    self.log.info('[> mqtt changereport: %s' % changeReport, exc_info=True)
                                self.notify('sofa/updates',json.dumps(changeReport))
                        done.append(smartDevice.endpointId) 
        except:
            self.log.error('Error checking devices', exc_info=True)

    async def ingest(self, data, notify=True, overwriteLevel=None, returnChangeReport=True):
        
        try:
            # Take a copy of the existing data dictionary, use dpath to merge the updated content with the old, 
            # and then use jsonpatch to find the differences and report them.  Olddata retains the previous state
            # in case it is needed.
            self.oldNativeDevices = copy.deepcopy(self.nativeDevices)
            oldDevices={}
            for dev in self.localDevices:
                oldDevices[dev]=[]
                for prop in self.localDevices[dev].propertyStates:
                    oldDevices[dev].append(copy.deepcopy(prop))
            
            if overwriteLevel:
                # overwriteLevel should start with a leading '/' because that's what the patch expects
                self.nested_set(self.nativeDevices, overwriteLevel.split('/'), list(data) )
                patch=[{"op":"change", "value":list(data), "path":overwriteLevel}]
            else:
                dpath.util.merge(self.nativeDevices, data, flags=dpath.util.MERGE_REPLACE)
                patch = jsonpatch.JsonPatch.from_diff(self.oldNativeDevices, self.nativeDevices)
            
            if patch:
                await self.checkDevicesForChanges(patch, oldDevices)
                return patch

            return {}
                
        except:
            self.log.error('Error ingesting new data to dataset: %s' % data, exc_info=True)
            return {}

                
    async def updateDevicesFromPatch(self,data):
            
        try:
            updates=[]
            
            #self.log.info('patch: %s' % data)

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
                                self.notify('sofa/updates',json.dumps(event))


                        update=await self.updateDeviceState(item['path'], newDevice=False, patch=item)
                        if update:
                            updates.append(update)
            return updates
        except:
            self.log.error('Error with controllermap: %s ' % item['path'], exc_info=True)

                      
    async def updateDeviceState(self, path, controllers={}, newDevice=False, correlationToken=None, patch=""):

        try:
            
            nativeObject=self.getObjectFromPath(self.getObjectPath(path))
            try:
                smartDevice=self.getDeviceByEndpointId("%s%s" % (self.adaptername, self.getObjectPath(path).replace("/",":")))
            except:
                self.log.error('Error getting device by endpointId: %s%s' % (self.adaptername, self.getObjectPath(path).replace("/",":")) )
                return None

            if not smartDevice:
                nodevpath="%s%s" % (self.adaptername, self.getObjectPath(path).replace("/",":"))
                if nodevpath not in self.nodevices:
                    self.log.info(".? No device for %s (%s)" % (nodevpath, path))
                    self.nodevices.append(nodevpath)
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
                self.log.debug('Change in controller: %s %s' % (controller, controllers[controller]))
                for prop in changecontrollers[controller]:
                    try:
                        smartController=getattr(smartDevice,controller)
                        smartProp=getattr(smartController, prop)
                        try:
                            setattr(smartController, prop, self.adapter.virtualControllerProperty(nativeObject, prop))
                        except AttributeError:
                            # During the transition to object based smart devices this will be triggered
                            # Moving it to debug for now
                            self.log.debug('Not a settable property: %s/%s' % (controller, prop))
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
                self.log.info('Change Report: %s' % changeReport)
                try:
                    dev=self.getDeviceByEndpointId(changeReport['event']['endpoint']['endpointId'])
                    for prop in changeReport['event']['payload']['change']['properties']:
                        self.log.info('[> mqtt change: %s %s %s %s %s' % (dev.friendlyName, dev.endpointId, prop['namespace'], prop['name'], prop['value'] ))
                except:
                    self.log.info('[> mqtt changereport: %s' % changeReport, exc_info=True)
                self.notify('sofa/updates',json.dumps(changeReport))
                return changeReport
        
            elif newDevice:
                self.log.info('++ AddOrUpdateReport: %s (%s) %s' % (smartDevice.friendlyName, smartDevice.endpointId, smartDevice.addOrUpdateReport))
                self.notify('sofa/updates',json.dumps(smartDevice.addOrUpdateReport))
                return None
                #return smartDevice.addOrUpdateReport

        except:
            self.log.error('Error with update device state', exc_info=True)

                        
    def generateStateReport(self, endpointId, correlationToken=None, bearerToken=''):
            
        try:
            return self.getDeviceByEndpointId(endpointId).StateReport(correlationToken, bearerToken)
        except AttributeError:
            self.log.warn('Device not ready for state report: %s' % endpointId)
            return {}
            
        except:
            self.log.error('Error generating state report for %s' % endpointId, exc_info=True)
            return {}

    async def generateResponse(self, endpointId, correlationToken, controller=''):
            
        try:
            return self.getDeviceByEndpointId(endpointId).Response(correlationToken, controller=controller)
        except:
            self.log.error('Error generating response: %s' % endpointId, exc_info=True)
            return {}

    async def generateDeleteReport(self, endpointId, bearerToken=''):
            
        try:
            report={
                        "event": {
                            "header": {
                                "messageId": str(uuid.uuid1()),
                                "name": "DeleteReport",
                                "namespace": "Alexa.Discovery",
                                "payloadVersion": "3"
                            },
                            "payload": {
                                "endpoints": [
                                    { "endpointId": endpointId }
                                ],
                                "scope": {
                                    "type": "BearerToken",
                                    "token": bearerToken
                                }
                            }
                        }
                    }
                    
            self.notify('sofa/updates',json.dumps(report))
            return report

        except:
            self.log.error('Error generating delete report: %s' % endpointId, exc_info=True)
            return {}

    async def restPost(self, url, data={}, headers={ "Content-type": "text/xml" }, adapter=''):  
        
        try:
            timeout = aiohttp.ClientTimeout(total=self.restTimeout)
            async with aiohttp.ClientSession(timeout=timeout) as client:
                response=await client.post(url, data=json.dumps(data), headers=headers)
                result=await response.read()
                if result:
                    return json.loads(result.decode())
                
                self.log.warn('!. No data received from post')
                return {}
        
        except (aiohttp.client_exceptions.ClientConnectorError,
                ConnectionRefusedError,
                aiohttp.client_exceptions.ClientOSError,
                concurrent.futures._base.CancelledError) as e:
            self.log.warn('!. Connection refused for adapter %s. %s' % (adapter, str(e)))       

        except:
            self.log.error("!. Error requesting state: %s" % data,exc_info=True)
      
        return {}


    async def requestReportState(self, endpointId, mqtt_topic=None, correlationToken='', bearerToken=''):
        
        try:
            if not correlationToken:
                correlationToken=str(uuid.uuid1())
            
            reportState=self.ReportState(endpointId, correlationToken, bearerToken)

            if mqtt_topic:
                return await self.mqttRequestReply(reportState, correlationToken, topic=mqtt_topic)
            
            else:
                adapter=endpointId.split(":")[0]
                if adapter in self.adapters:
                    url=self.adapters[adapter]['url']
                    statereport=await self.restPost(url, reportState)
                    if statereport and hasattr(self.adapter, "handleStateReport"):
                        await self.adapter.handleStateReport(statereport)
                        return statereport
            
            self.log.warn('.! No State Report returned for %s' % endpointId)            
            return {}

        except:
            self.log.error("Error requesting state for %s" % endpointId,exc_info=True)
        
        return {}
        
        
    def ReportState(self, endpointId, correlationToken='' , bearerToken=''):

        return  {
            "directive": {
                "header": {
                    "name":"ReportState",
                    "payloadVersion": 3,
                    "messageId":str(uuid.uuid1()),
                    "namespace":"Alexa",
                    "correlationToken":correlationToken
                },
                "endpoint": {
                    "endpointId": endpointId,
                    "scope": {
                        "type": "BearerToken",
                        "token": bearerToken
                    },     
                    "cookie": {}
                },
                "payload": {}
            },
        }
        
    async def requestReportStates(self, adapter, devicelist):
        
        try:
            reqstart=datetime.datetime.now()
            if adapter in self.adapters:
                url=self.adapters[adapter]['url']+"/deviceStates"
                outdata=await self.restPost(url, devicelist, adapter=adapter)
                if (datetime.datetime.now()-reqstart).total_seconds()>1:
                    self.log.info('Warning - %s Report States took %s seconds to respond' % (adapter, (datetime.datetime.now()-reqstart).total_seconds()))
                return outdata

        except:
            self.log.error("Error requesting states for %s (%s)" % (adapter, devicelist),exc_info=True)
        
        return {}
    
               
    async def sendDirectiveToAdapter(self, data):
    
        try:
            adapter=data['directive']['endpoint']['endpointId'].split(":")[0]
            url=self.adapters[adapter]['url']
            directiveName=data['directive']['header']['name']
            if adapter==self.adaptername:
                self.log.info('=> %s to %s: %s' % (directiveName, adapter, data))
                response=await self.handleDirective(data)
            else:
                self.log.info('>> %s to %s: %s' % (directiveName, adapter, data))
                response=await self.restPost(url, data)
            if response and hasattr(self.adapter, "handleResponse"):
                await self.adapter.handleResponse(response)
                self.log.info('<< %s %s response: %s' % (adapter, directiveName, response))    
                return response

        except ConnectionRefusedError:
            self.log.error("Error sending Directive to Adapter: %s (connection refused)" % data)
            
        except:
            self.log.error("Error sending Directive to Adapter: %s" % data,exc_info=True)
        
        return {}


    async def handleDirective(self, data):
        
        response={}
        try:
            endpointId=data['directive']['endpoint']['endpointId']
            endpoint=data['directive']['endpoint']['endpointId'].split(":")[2]
            controller=data['directive']['header']['namespace'].split('.')[1]
            directive=data['directive']['header']['name']
            payload=data['directive']['payload']
            correlationToken=data['directive']['header']['correlationToken']
            cookie=data['directive']['endpoint']['cookie']
            try:
                device_controller=None
                device=self.getDeviceByEndpointId(endpointId)
                if 'instance' in data['directive']['header']:
                    self.log.info('.. Looking for %s in %s' % (data['directive']['header']['instance'],device.interfaces ))
                    for cont in device.interfaces:
                        self.log.info('-- Looking for %s in %s' % (data['directive']['header']['instance'],cont ))
                        if hasattr(cont, 'instance') and cont.instance==data['directive']['header']['instance']:
                            self.log.info('.. instanced controller: %s %s' % (data['directive']['header']['instance'], cont))
                            device_controller=cont
                            break
                elif hasattr(device, controller):
                    device_controller=getattr(device, controller)
                
                if device_controller:
                    if hasattr(device_controller, directive):
                        if getattr(device_controller, directive)!=None:
                            args=[]
                            if payload:
                                args.append(payload)
                            kwargs={'correlationToken': correlationToken}
                            if directive in ['Activate','Deactivate'] and cookie:
                                kwargs['cookie']=cookie
                            response=await getattr(device_controller, directive)(*args, **kwargs)
                            return response
                else:
                    self.log.info('No interface found: %s %s' % (controller+'Interface', device.__dict__))
                self.log.info('~~ Fallthrough on handle directive for %s' % data)
            except:
                self.log.info('Could not run device integrated command: %s' % data, exc_info=True)
        
            if hasattr(self.adapter, "processDirective"):    
                response=await self.adapter.processDirective(endpointId, controller, directive, payload, correlationToken=correlationToken, cookie=cookie)

        except:
            self.log.error('Error handling directive', exc_info=True)
        
        return response

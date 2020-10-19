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
import reports

import inspect

class sofaDataset():
        
    def __init__(self, log=None, adaptername="sofa", loop=None, config=None):
        self.startupTime=datetime.datetime.now()
        self.adaptername=adaptername
        self.config=config
        self.localDevices={}
        self.nativeDevices={}
        self.devices={}
        self.listdata={}
        self.controllers={}
        self.log=log
        self.loop=loop
        self.mqtt={}
        self.nodevices=[]
        self.restTimeout=5
        self.pendingRequests={}
        self.lists={}

    def count_items(self, d, ct):
        nc=0
        if type(d)==list:
            for v in d:
                nc=nc+self.count_items(v, ct)
                
        elif type(d)==dict:        
            for k, v in d.items():
                if isinstance(v, (list,dict)):
                    nc=nc+self.count_items(v, ct)
                else:
                    nc= nc+1
        else:
            nc += 1
                    
        return ct+nc
                
    def getSizeOfNative(self):
        
        try:
            measured=self.nativeDevices
            length=self.count_items(measured, 0)
            return length
        except:
            self.log.error('!! Error getting Total size of native', exc_info=True)
            return 0


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
        except KeyError:
            self.log.info('Error getting native from path (probably adapter)')
            return {}
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


    async def discovery(self, remote=False):
    
        # respond to discovery with list of devices.  Use remote to list the devices known from other sources
        # otherwise just respond with devices owned by this adapter
        endpoints=[]

        if remote:
            endpoints=list(self.devices.values())
        else:
            for dev in self.localDevices:
                if not self.localDevices[dev].hidden:
                    endpoints.append(self.localDevices[dev].discoverResponse)
        
        return reports.DiscoveryResponse(endpoints)


    def deleteDevice(self, name): # delete a smart device from the devices object 
            
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


    def add_device(self, obj): # add a smart device from the devices object set to the local device list
            
        try:
            self.localDevices[obj.endpointId]=obj
            return self.localDevices[obj.endpointId]            
        except:
            self.log.error('!! Error adding device: %s' % (shortname), exc_info=True)
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


    def getDeviceByEndpointId(self, endpointId, as_dict=False):
        
        # first check devices that are local to this adapter
        
        for device in self.localDevices:
            if self.localDevices[device].endpointId==endpointId:
                if as_dict:
                    return self.localDevices[device].discoverResponse
                return self.localDevices[device]
        
        # now check other devices for collector type adapters
        for device in self.devices:
            try:
                if self.devices[device]['endpointId']==endpointId:
                    return self.devices[device]
            except:
                self.log.error('Error with %s' % self.devices[device], exc_info=True)
        
        return None
        
    def deviceHasCapability(self, endpointId, cap):
        
        try:
            if endpointId in self.localDevices:
                for devcap in self.localDevices[endpointId].capabilities:
                    if '.' in devcap['interface']:
                        if cap==devcap['interface'].split('.')[1]:
                            return True
                                
            if endpointId in self.devices:
                for devcap in self.devices[endpointId]['capabilities']:
                    #self.log.info('interface: %s %s %s' % (cap, devcap['interface'], '.' in devcap['interface']))
                    if '.' in devcap['interface']:
                        if cap==devcap['interface'].split('.')[1]:
                            return True
        except:
            self.log.error('!! Error checking for device capability on %s for %s' % (endpointId, cap), exc_info=True)
        return False    

    def device_capability(self, endpointId, cap):
        
        try:
            if endpointId in self.localDevices:
                for devcap in self.localDevices[endpointId].capabilities:
                    if '.' in devcap['interface']:
                        if cap==devcap['interface'].split('.')[1]:
                            return devcap
                                
            if endpointId in self.devices:
                for devcap in self.devices[endpointId]['capabilities']:
                    #self.log.info('interface: %s %s %s' % (cap, devcap['interface'], '.' in devcap['interface']))
                    if '.' in devcap['interface']:
                        if cap==devcap['interface'].split('.')[1]:
                            return devcap
        except:
            self.log.error('!! Error checking for device capability on %s for %s' % (endpointId, cap), exc_info=True)
        return False    


            
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

    def getObjectsByDisplayCategory(self, category, local=True):
            
        devicelist=[]
        for device in self.localDevices:
            try:
                if category.upper() in self.localDevices[device].displayCategories:
                    devicelist.append(self.localDevices[device])
            except:
                pass

        if not local:
            for device in self.devices:
                try:
                    if category.upper() in self.devices[device].displayCategories:
                        devicelist.append(self.devices[device])
                    else:
                        self.log.info('%s not in %s' % (category.upper(), self.devices[device].displayCategories))
                except:
                    self.log.error('%s not?' % category.upper(), exc_info=True)
                
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
                        #self.log.info('cap: %s %s' % (self.devices[device]['friendlyName'], cap))
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
                            

    async def addDeviceAndNotify(self, path):
        try:
            if hasattr(self.adapter, "addSmartDevice"):
                smartDevice=await self.adapter.addSmartDevice(path)
                if smartDevice:
                    self.log.info('++ AddOrUpdateReport: %s (%s)' % (smartDevice.friendlyName, smartDevice.endpointId))
                    if not smartDevice.hidden:
                        if hasattr(self, "web_notify"):
                            await self.web_notify(smartDevice.addOrUpdateReport)
                        #if hasattr(self.adapter, "virtual_notify"):
                        #    await self.adapter.virtual_notify(smartDevice.addOrUpdateReport)

                    return smartDevice.endpointId
        except:
            self.log.error('Error addDeviceAndNotify: %s' % path, exc_info=True)
            
    
    async def checkDevicesForChanges(self, patch, oldDevicePropertyStates):
        
        try:
            done=[]
            for item in patch:
                if len(item['path'].split('/'))<3:
                    continue # ignore top level category adds

                if item['op']=='add':
                    result=await self.addDeviceAndNotify(item['path'])
                    if result:
                        done.append(result) 
                else:
                    smartDevice=self.getDeviceByEndpointId("%s%s" % (self.adaptername, self.getObjectPath(item['path']).replace("/",":")))
                    shortname="%s%s" % (self.adaptername, self.getObjectPath(item['path']).replace("/",":"))
                    if smartDevice and smartDevice.endpointId not in done and smartDevice.endpointId in oldDevicePropertyStates:  
                        newdev={}
                        olddev={}
                        for prop in smartDevice.propertyStates: 
                            if 'instance' in prop:
                                newdev[prop['namespace']+'.'+prop['name']+"."+prop['instance']]=prop
                            else:
                                newdev[prop['namespace']+'.'+prop['name']]=prop
                                
                        for prop in oldDevicePropertyStates[smartDevice.endpointId]:
                            if 'instance' in prop:
                                olddev[prop['namespace']+'.'+prop['name']+"."+prop['instance']]=prop
                            else:
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
                                    proactive_report=False
                                    changes="[> changes: %s %s -" % (smartDevice.friendlyName, smartDevice.endpointId)
                                    for prop in changeReport['event']['payload']['change']['properties']:
                                        if self.is_change_proactively_reported(smartDevice, prop):
                                            proactive_report=True
                                        if 'instance' in prop:
                                            changes=changes+" %s.%s.%s %s" % (prop['namespace'], prop['instance'], prop['name'], prop['value'] )
                                        else:
                                            changes=changes+" %s.%s %s" % (prop['namespace'], prop['name'], prop['value'] )
                                        if self.config.log_changes:
                                            self.log.debug('.. Proactive: %s / Change: %s' % (proactive_report, changes))
                                except:
                                    self.log.debug('[> changereport: %s' % changeReport, exc_info=True)
                                if proactive_report:
                                    if hasattr(self, "web_notify"):
                                        await self.web_notify(changeReport)
                                    if hasattr(self.adapter, "virtual_notify"):
                                        await self.adapter.virtual_notify(changeReport)
                        done.append(smartDevice.endpointId) 
        except:
            self.log.error('Error checking devices', exc_info=True)


    def is_change_proactively_reported(self, device, change_prop):
        
        try:
            for cap in device.capabilities:
                if change_prop['namespace']==cap['interface']:
                    if not 'instance' in change_prop or ('instance' in cap and cap['instance']==change_prop['instance']):
                        if cap['properties']['proactivelyReported']:
                            return True
        except:
            self.log.error('!! error determining proactive reporting: %s %s' % (device.capabilities, change_prop), exc_info=True)
        return False
                    
        
    async def ingest(self, data, notify=True, overwriteLevel=None,  mergeReplace=False, returnChangeReport=True):
        
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
                if mergeReplace:
                    dpath.util.merge(self.nativeDevices, data, flags=dpath.util.MERGE_REPLACE)
                else:
                    dpath.util.merge(self.nativeDevices, data)
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
                                #self.notify('sofa/updates',json.dumps(event))
                                if hasattr(self, "web_notify"):
                                    await self.web_notify(event)
                                if hasattr(self.adapter, "virtual_notify"):
                                    await self.adapter.virtual_notify(event)
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
                
                if hasattr(self, "web_notify"):
                    await self.web_notify(changeReport)
                if hasattr(self.adapter, "virtual_notify"):
                    await self.adapter.virtual_notify(changeReport)
                return changeReport
        
            elif newDevice:
                self.log.info('++ AddOrUpdateReport: %s (%s) %s' % (smartDevice.friendlyName, smartDevice.endpointId, smartDevice.addOrUpdateReport))

                if hasattr(self, "web_notify"):
                    await self.web_notify(smartDevice.addOrUpdateReport)
                if hasattr(self.adapter, "virtual_notify"):
                    await self.adapter.virtual_notify(smartDevice.addOrUpdateReport)
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

    async def generateDeleteReport(self, endpoint_list, bearerToken=''):
            
        try:
            if type(endpoint_list)==str:
                endpoint_lists=[endpoint_list]
            
            endpoints=[]
            for endpointId in endpoint_list:
                endpoints.append( { "endpointId": endpointId} )
                
            if endpoints: 
                report=reports.DeleteReport(endpoints, bearerToken)
                await self.web_notify(report)
                if hasattr(self.adapter, "virtual_notify"):
                    await self.adapter.virtual_notify(report)
                
                return report

        except:
            self.log.error('Error generating delete report: %s' % endpoint_list, exc_info=True)
        return {}

    async def restPost(self, path="", data={}):  
        
        try:
            if self.token==None:
                self.log.error('!! Error - no token %s' % self.token)
                return {}
            headers={ "Content-type": "text/xml", "authorization": self.token }
            timeout = aiohttp.ClientTimeout(total=self.restTimeout)
            url=self.config.api_gateway
            if path:
                url=url+"/"+path
            async with aiohttp.ClientSession(timeout=timeout) as client:
                response=await client.post(url, data=json.dumps(data), headers=headers)
                result=await response.read()
                if result:
                    try:
                        return json.loads(result.decode())
                    except:
                        self.log.info('bad json? %s' % result)
                        self.log.info('request? %s %s' % (path,data))
                self.log.warn('!. No data received from post')
                return {}
        
        except concurrent.futures._base.TimeoutError:
            self.log.error("!. Error - Timeout in rest post to %s: %s %s" % (url, headers, data))
        except (aiohttp.client_exceptions.ClientConnectorError,
                ConnectionRefusedError,
                aiohttp.client_exceptions.ClientOSError,
                concurrent.futures._base.CancelledError) as e:
            self.log.warn('!. Connection refused. %s' % (str(e)))       
        except:
            self.log.error("!. Error requesting state: %s" % data,exc_info=True)
      
        return {}

    async def restGet(self, path=""):  
        
        try:
            if self.token==None:
                self.log.error('!! Error - no token %s' % self.token)
                return {}
            headers={ "Content-type": "text/xml", "authorization": self.token }
            timeout = aiohttp.ClientTimeout(total=self.restTimeout)
            url=self.config.api_gateway
            if path:
                url=url+"/"+path
            async with aiohttp.ClientSession(timeout=timeout) as client:
                response=await client.get(url, headers=headers)
                result=await response.read()
                if result:
                    try:
                        return json.loads(result.decode())
                    except:
                        self.log.info('bad json? %s' % result)
                        self.log.info('request? %s %s' % (path,data))
                self.log.warn('!. No data received from post')
                return {}
        
        except concurrent.futures._base.TimeoutError:
            self.log.error("!. Error - Timeout in rest post to %s: %s %s" % (url, headers, data))
        except (aiohttp.client_exceptions.ClientConnectorError,
                ConnectionRefusedError,
                aiohttp.client_exceptions.ClientOSError,
                concurrent.futures._base.CancelledError) as e:
            self.log.warn('!. Connection refused. %s' % (str(e)))       
        except:
            self.log.error("!. Error requesting state: %s" % data,exc_info=True)
      
        return {}


    async def generateStateReports(self, devlist, correlationToken='', bearerToken='', cookie={}):
        
        try:
            result={}
            for dev in devlist:
                try:
                    result[dev]=self.getDeviceByEndpointId(dev).StateReport()
                    #result[dev]=self.dataset.getDeviceByfriendlyName(dev).StateReport()
                #except AttributeError: 
                #    self.log.warn('Warning - device was not ready for statereport: %s' % dev)
                except AttributeError: 
                    self.log.error('!! Error getting statereport: %s does not exist' % dev)
                except:
                    self.log.error('!! Error getting statereport for %s' % dev, exc_info=True)
            return result    

        except:
            self.log.error('Error generating device states report: %s' % devlist, exc_info=True)
        return result        



    async def requestReportStates(self, devicelist, correlationToken='', bearerToken='', cookie={}):
        
        try:
            reqstart=datetime.datetime.now()
            if not correlationToken:
                correlationToken=str(uuid.uuid1())

            adapter=devicelist[0].split(":")[0]
            if adapter==self.adaptername:
                stateReports=await self.generateStateReports(devicelist)
            else:
                reportStates=self.ReportStates(devicelist)
                stateReports=await self.restPost(data=reportStates)


            if (datetime.datetime.now()-reqstart).total_seconds()>2:
                # typically takes about .5 seconds
                self.log.info('.. Warning - %s Report States took %s seconds to respond' % (adapter, (datetime.datetime.now()-reqstart).total_seconds()))
            
            for report in stateReports:
                if 'event' not in stateReports[report]:
                    self.log.info('report: %s' % stateReports[report])
                    
            return stateReports
        except:
            self.log.error("Error requesting states for %s (%s)" % (adapter, devicelist),exc_info=True)
        
        return {}


    async def requestReportState(self, endpointId, correlationToken='', bearerToken='', cookie={}):
        
        try:
            if endpointId not in self.devices:
                self.log.info('.. requested ReportState for unknown device: %s' % endpointId)
                return {}

            if not correlationToken:
                correlationToken=str(uuid.uuid1())
            
            reportState=reports.ReportState(endpointId, correlationToken, bearerToken, cookie)

            if endpointId in self.localDevices:
                statereport=self.generateStateReport(endpointId, correlationToken=correlationToken, bearerToken=bearerToken)
            else:
                statereport=await self.restPost(data=reportState)

            if statereport and statereport['event']['header']['name']=='ErrorResponse':
                self.log.warning('!! ErrorResponse received from ReportState: %s' % statereport)
                if statereport['event']['payload']['type']=='NO_SUCH_ENDPOINT':
                    endpointId=statereport['event']['endpoint']['endpointId']
                    if endpointId in self.devices:
                        del self.devices[endpointId]
                    await self.adapter.handleErrorResponse(statereport)
                    
                return statereport
                
            if statereport and hasattr(self.adapter, "handleStateReport"):
                await self.adapter.handleStateReport(statereport)
                return statereport
            
            self.log.warn('.! No State Report returned for %s' % endpointId)            
            return {}

        except concurrent.futures._base.TimeoutError:
            self.log.error("!! Error requesting state for %s (timeout)" % endpointId,exc_info=True)

        except:
            self.log.error("!! Error requesting state for %s" % endpointId,exc_info=True)
        
        return {}
        

    def ReportState(self, endpointId, correlationToken='' , bearerToken='', cookie={}):

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
                    "cookie": cookie
                },
                "payload": {}
            },
        }

    def ReportStates(self, endpoint_list, correlationToken='' , bearerToken='', cookie={}):

        return  {
            "directive": {
                "header": {
                    "name":"ReportStates",
                    "payloadVersion": 3,
                    "messageId":str(uuid.uuid1()),
                    "namespace":"Alexa",
                    "correlationToken":correlationToken
                },
                "payload": {
                    "endpoints": endpoint_list
                }
            },
        }


    async def checkNativeGroup(self, adapter, controller, devicelist, url, correlationToken=""):

        directive=  {
            "directive": {
                "header": {
                    "name":"CheckGroup",
                    "payloadVersion": 3,
                    "messageId":str(uuid.uuid1()),
                    "namespace":"Alexa",
                    "correlationToken":correlationToken
                },
                "payload": {
                    "controllers": controller,
                    "endpoints": devicelist
                }
            }
        }

        try:
            self.log.debug('>> checking for %s.%s in %s' % (devicelist, controller, adapter))
            response=await self.restPost(data=directive)
            if response:
                self.log.info('<< cng %s %s response: %s' % (adapter, devicelist, response))    
                return response

        except ConnectionRefusedError:
            self.log.error("!! Error sending Directive to Adapter: %s (connection refused)" % data)
            
        except:
            self.log.error("!! Error sending Directive to Adapter: %s" % data,exc_info=True)
        
        return {}


           
    async def sendDirectiveToAdapter(self, data, url=None):
    
        # 10/14/20 - should be Deprecated or renamed at a minimum - only the hub adapter needs to know where individual adapters
        # are and to send to them - everything else should pass commands through the event gateway
    
        try:
            directiveName=data['directive']['header']['name']
            if data['directive']['endpoint']['endpointId'] in self.localDevices:
                self.log.info('=> %s %s' % (self.config.adapter_name, reports.alexa_json_filter(data)))
                response=await self.handleDirective(data)
            else:
                self.log.info('>> event gateway > %s' % (reports.alexa_json_filter(data)))
                response=await self.restPost(data=data)
            if response and hasattr(self.adapter, "handleResponse"):
                await self.adapter.handleResponse(response)
                self.log.info('<< event gateway < %s response: %s' % (directiveName, reports.alexa_json_filter(data)))    
                return response

        except ConnectionRefusedError:
            self.log.error("Error sending Directive to hub: %s (connection refused)" % data)
            
        except:
            self.log.error("Error sending Directive to hub: %s" % data,exc_info=True)
        
        return {}


    async def handleDirective(self, data):
        
        response={}
        try:
            directive=data['directive']['header']['name']
            if directive=="Discover":
                self.log.info('.. discovery directive')
                return {}
            endpointId=data['directive']['endpoint']['endpointId']
            endpoint=data['directive']['endpoint']['endpointId'].split(":")[2]
            controller=data['directive']['header']['namespace'].split('.')[1]
            directive=data['directive']['header']['name']
            payload=data['directive']['payload']
            correlationToken=data['directive']['header']['correlationToken']
            if 'cookie' in data['directive']['endpoint']:
                cookie=data['directive']['endpoint']['cookie']
            else:
                cookie=""
            try:
                device_controller=None
                device=self.getDeviceByEndpointId(endpointId)
                if 'instance' in data['directive']['header']:
                    #self.log.info('.. Looking for %s in %s' % (data['directive']['header']['instance'],device.interfaces ))
                    for cont in device.interfaces:
                        #self.log.info('-- Looking for %s in %s' % (data['directive']['header']['instance'],cont ))
                        if hasattr(cont, 'instance') and cont.instance==data['directive']['header']['instance']:
                            #self.log.info('.. instanced controller: %s %s' % (data['directive']['header']['instance'], cont))
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
                    if device:
                        self.log.info('.! No interface found: %s %s' % (controller+'Interface', device.__dict__))
                    else:
                        self.log.info('.! No device found: %s %s' % (controller+'Interface', endpointId))
                        
                self.log.info('~~ Fallthrough on handle directive for %s' % data)
            except:
                self.log.info('Could not run device integrated command: %s' % data, exc_info=True)
        
            if hasattr(self.adapter, "processDirective"):    
                response=await self.adapter.processDirective(endpointId, controller, directive, payload, correlationToken=correlationToken, cookie=cookie)

        except:
            self.log.error('Error handling directive', exc_info=True)
        
        return response
        
    def date_handler(self, obj):
        
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        else:
            self.log.info('Caused type error: %s' % obj)
            raise TypeError

    async def handle_local_directive(self, data):

        response={}
        try:
            if 'directive' in data:
                if data['directive']['header']['name']=='Discover':
                    lookup=await self.discovery()
                    return lookup

    
                elif data['directive']['header']['name']=='ReportStates':
                    bearerToken=''
                    #self.log.info('Reportstate: %s %s' % (data['directive']['endpoint']['endpointId'], data['directive']['header']['correlationToken']))
                    response=await self.generateStateReports(data['directive']['payload']['endpoints'], correlationToken=data['directive']['header']['correlationToken'], bearerToken=bearerToken)
    
                elif data['directive']['header']['name']=='ReportState':
                    try:
                        bearerToken=data['directive']['endpoint']['scope']['token']
                    except:
                        self.log.info('No bearer token')
                        bearerToken=''
                    #self.log.info('Reportstate: %s %s' % (data['directive']['endpoint']['endpointId'], data['directive']['header']['correlationToken']))
                    response=self.generateStateReport(data['directive']['endpoint']['endpointId'], correlationToken=data['directive']['header']['correlationToken'], bearerToken=bearerToken)
    
                elif data['directive']['header']['name']=='CheckGroup':
                    try:
                        if hasattr(self.adapter, "virtual_group_handler"):
                            result=await self.adapter.virtual_group_handler(data['directive']['payload']['controllers'], data['directive']['payload']['endpoints'])
                            self.log.info('<< native group %s: %s' % (data['directive']['payload'], result))
                            return result
                    except:
                        self.log.info('!! error handling nativegroup request', exc_info=True)
                        response={}
    
                else:
                    target_namespace=data['directive']['header']['namespace'].split('.')[1]
                    self.log.info('<< %s' % (reports.alexa_json_filter(data)))
                    #self.log.info('<< %s' % data)
                    response=await self.handleDirective(data)
                    if response:
                        try:
                            self.log.info('>> %s' % (reports.alexa_json_filter(response, target_namespace)))
                        except:
                            self.log.warn('>> %s' % response)
            return response
        
        except:
            self.log.error('!! error with local directive processing', exc_info=True)
        return {}

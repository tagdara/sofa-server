#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

from sofabase import sofabase
from sofabase import adapterbase
import devices

import json
import pyvizio
import asyncio


class vizio(sofabase):
    
    class adapterProcess(adapterbase):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.dataset.nativeDevices['tv']={}
            self.log=log
            self.notify=notify
            self.polltime=5

            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            
        async def start(self):
            self.log.info('.. Starting vizio')
            self.tv = pyvizio.Vizio(self.dataset.config['device_id'],self.dataset.config['host'],self.dataset.config['tv_name'],self.dataset.config['token'])
            await self.pollTv()

            
        async def pollTv(self):
            while True:
                try:
                    #self.log.info("Polling bridge data")
                    await self.getTvData()
                    await asyncio.sleep(self.polltime)
                except:
                    self.log.error('Error polling TV', exc_info=True)
                    await asyncio.sleep(self.polltime)

        async def getTvData(self):

            try:
                tvdata={}
                tvdata['power']=self.tv.get_power_state()
                tvdata['volume']=self.tv.get_current_volume()
    
                tvdata['input_list']=[]
                allinputs=self.tv.get_inputs()
                
                if allinputs:
                    for input_ in allinputs:
                        #self.log.info('Input: %s' % input_.__dict__)
                        tvdata['input_list'].append(input_.name)

                    try:
                        tvdata['input']=self.tv.get_current_input().meta_name
                    except AttributeError:
                        self.log.warn('TV does not have current input: %s' % self.tv.get_current_input() )
                        tvdata['input']=tvdata['input_list'][0]
        
                    await self.dataset.ingest({'tv': { self.dataset.config['tv_name']: tvdata}})
                    return tvdata
                else:
                    self.log.warn('!! Warning - no list of inputs received. Connection with TV is likely lost')
                    return tvdata

            except:
                self.log.info('Error getting TV data', exc_info=True)
                return tvdata


        # Adapter Overlays that will be called from dataset
        async def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="tv":
                    return self.addSmartTV(path.split("/")[2], path.split("/")[2])
                else:
                    self.log.info('Path not adding device: %s' % path)

            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False


        def addSmartTV(self, deviceid, name="Vizio"):
            
            try:
                nativeObject=self.dataset.nativeDevices['tv'][name]
                if name not in self.dataset.localDevices:
                    if "volume" in nativeObject and "power" in nativeObject:
                        return self.dataset.addDevice(name, devices.tv('vizio/tv/%s' % deviceid, name, inputs= nativeObject['input_list']))
            except:
                self.log.error('!! Error adding smart TV: %s %s' % (deviceid, name))
            
            return False

        def getNativeFromEndpointId(self, endpointId):
            
            try:
                return endpointId.split(":")[2]
            except:
                return False
                
        async def processDirective(self, endpointId, controller, command, payload, correlationToken='', cookie={}):
    
            self.remotemap={"CursorUp":"UP", "CursorLeft":"LEFT", "CursorRight":"RIGHT", "CursorDown":"DOWN", "DpadCenter":"OK"}
            try:
                device=endpointId.split(":")[2]
                sysinfo={}
                
                if controller=="PowerController":
                    if command=='TurnOn':
                        sysinfo=self.tv.pow_on()
                    elif command=='TurnOff':
                        sysinfo=self.tv.pow_off()
                        
                elif controller=="InputController":
                    if command=='SelectInput':
                        sysinfo=self.tv.input_switch(payload['input'])
                        
                elif controller=="RemoteController":
                    if command=="PressRemoteButton":
                        self.log.info('keys: %s' % self.tv.get_device_keys())
                        if payload['buttonName'] in self.remotemap:
                            self.log.info('sending key %s' % self.remotemap[payload['buttonName']])
                            self.tv.remote(self.remotemap[payload['buttonName']])

                elif controller=="SpeakerController":
                    if command=="SetVolume":
                        cv=self.tv.get_current_volume()
                        vdelta=cv-int(payload['volume'])
                        for i in range(abs(vdelta)):
                            if vdelta < 0:
                                self.tv.vol_up()
                            elif vdelta > 0:
                                self.tv.vol_down()

                await self.getTvData()
                    
                response=await self.dataset.generateResponse(endpointId, correlationToken)
                return response
                  
            except:
                self.log.error('Error executing state change.', exc_info=True)


        def virtualControllers(self, itempath):
            
            controllerlist={}
               
            try:
                detail=itempath.split("/",3)[3]
            except:
                detail=""
            
            try:
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                
                if detail=="power" or detail=="":
                    controllerlist=self.addControllerProps(controllerlist,"PowerController","powerState")
                if detail=="input" or detail=="":
                    controllerlist=self.addControllerProps(controllerlist,"InputController","input")
                if detail=="volume" or detail=="":
                    controllerlist=self.addControllerProps(controllerlist,"SpeakerController","volume")

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)
                
            return controllerlist

           
        def virtualControllerProperty(self, nativeObj, controllerProp):
            
            #self.log.info('NativeObj: %s' % nativeObj)
            
            try:
                if controllerProp=='powerState':
                    return "ON" if nativeObj['power'] else "OFF"
    
                elif controllerProp=='input':
                    return nativeObj['input']
    
                elif controllerProp=='volume':
                    return nativeObj['volume']
    
                else:
                    self.log.info('Unknown controller property mapping: %s' % controllerProp)
                    return {}
            except:
                self.log.error('Error getting controller property: %s' % controllerProp, exc_info=True)
                
        async def virtualList(self, itempath, query={}):

            try:
                if itempath=="inputs":
                    return self.dataset.nativeDevices['tv']['Living Room TV']['input_list']

                return {}

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)


if __name__ == '__main__':
    adapter=vizio(name='vizio')
    adapter.start()

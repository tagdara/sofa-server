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
import json
import definitions
import asyncio
import aiohttp
import xml.etree.ElementTree as et
from collections import defaultdict
import socket


class BroadcastProtocol:

    def __init__(self, loop, log, keyphrases=[], returnmessage=None):
        self.log=log
        self.loop = loop
        self.keyphrases=keyphrases
        self.returnMessage=returnmessage


    def connection_made(self, transport):
        self.transport = transport
        sock = transport.get_extra_info("socket")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.log.info('.. ssdp now listening')


    def datagram_received(self, data, addr):
        #self.log.info('data received: %s %s' % (data, addr))
        data=data.decode()
        for phrase in self.keyphrases:
            if data.find(phrase)>-1 and data.find("<?xml")>-1:
                event=self.etree_to_dict(et.fromstring(data[data.find("<?xml"):]))
                self.log.info('>> ssdp %s' % event)
                self.processUPNPevent(event)
                #return str(data)


    def broadcast(self, data):
        self.log.info('>> ssdp/broadcast %s' % data)
        self.transport.sendto(data.encode(), ('192.168.0.255', 9000))


    def etree_to_dict(self, t):
        
        d = {t.tag: {} if t.attrib else None}
        children = list(t)
        if children:
            dd = defaultdict(list)
            for dc in map(self.etree_to_dict, children):
                for k, v in dc.items():
                    dd[k].append(v)
            d = {t.tag: {k: v[0] if len(v) == 1 else v for k, v in dd.items()}}
        if t.attrib:
            d[t.tag].update(('@' + k, v) for k, v in t.attrib.items())
        if t.text:
            text = t.text.strip()
            if children or t.attrib:
                if text:
                    d[t.tag]['#text'] = text
            else:
                d[t.tag] = text
        return d


    def processUPNPevent(self, event):   

        try:
            asyncio.ensure_future(self.returnMessage(event))

        except:
            self.log.info("Error processing UPNP Event: %s " % upnpxml,exc_info=True)


class yamahaXML():

    def __init__(self, log=None, dataset=None):
        self.log=log
        self.dataset=dataset
        self.definitions=definitions.yamahaDefinitions

    def etree_to_dict(self, t):
        
        d = {t.tag: {} if t.attrib else None}
        children = list(t)
        if children:
            dd = defaultdict(list)
            for dc in map(self.etree_to_dict, children):
                for k, v in dc.items():
                    dd[k].append(v)
            d = {t.tag: {k: v[0] if len(v) == 1 else v for k, v in dd.items()}}
        if t.attrib:
            d[t.tag].update(('@' + k, v) for k, v in t.attrib.items())
        if t.text:
            text = t.text.strip()
            if children or t.attrib:
                if text:
                    d[t.tag]['#text'] = text
            else:
                d[t.tag] = text
        return d


    def data2xml(self, d, name='YAMAHA_AV'):
        r = et.Element(name)
        r.set('cmd','PUT')
        return et.tostring(self.buildxml(r, d))

    def buildxml(self, r, d):
        if isinstance(d, dict):
            for k, v in d.items():
                s = et.SubElement(r, k)
                self.buildxml(s, v)
        elif isinstance(d, tuple) or isinstance(d, list):
            for v in d:
                s = et.SubElement(r, 'i')
                self.buildxml(s, v)
        elif isinstance(d, str):
            r.text = d
        else:
            r.text = str(d)
        return r

        
    async def sendCommand(self, category, item, data):
        try:
            #data={category: data}
            data=category
            data=self.data2xml(data).decode()
            socket.setdefaulttimeout(1)

            url = 'http://%s:%s/YamahaRemoteControl/ctrl' % (self.dataset.config['address'], self.dataset.config['port'])
            #self.log.info('Command: %s %s' % (url, data))
            headers = { "Content-type": "text/xml" }
            self.log.debug('Sending: %s %s %s' % (url, data, headers))
            async with aiohttp.ClientSession() as client:
                response=await client.post(url, data=data, headers=headers)
                xml=await response.read()
                self.log.debug('XML resp: %s' % xml)
                if xml:
                    ydata=self.etree_to_dict(et.fromstring(xml))
                    return ydata['YAMAHA_AV']
                else:
                    return {}
        except:
            self.log.error("send_command error",exc_info=True)
    
    async def getState(self, itemState):
        try:
            url = 'http://%s:%s/YamahaRemoteControl/ctrl' % (self.dataset.config['address'], self.dataset.config['port'])
            headers = { "Content-type": "text/xml" }
            data=self.definitions.itemStates[itemState]
            async with aiohttp.ClientSession() as client:
                response=await client.post(url, data=data, headers=headers)
                xml=await response.read()
                if xml:
                    ydata=self.etree_to_dict(et.fromstring(xml))
                    return ydata['YAMAHA_AV']
                else:
                    return {}

        except:
            self.log.error('Error sending command', exc_info=True)
    
    async def main(self):
        async with aiohttp.ClientSession() as client:
            html = await self.authenticate(client)
            return html


class yamaha(sofabase):

    class adapterProcess():


        def __init__(self, log=None, dataset=None, notify=None, request=None, loop=None, **kwargs):

            self.definitions=definitions.yamahaDefinitions
            self.dataset=dataset
            self.ssdpkeywords=self.dataset.config['ssdpkeywords']
            self.log=log
            self.notify=notify
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop

            
        async def updateState(self, itemState):

            try:
                result=await self.receiver.getState(itemState)
                for item in result:
                    if item.find('@')!=0:
                        await self.dataset.ingest({ "Receiver": {item: result[item]} })
            except:
                self.log.error('Error updating state of receiver: %s' % (itemState), exc_info=True)


        async def processUPNP(self, message):
            try:
                message=message['YAMAHA_AV']
                # Some messages might not be power or volume, but this works for now
                await self.updateState('basic_status')
            except:
                self.log.error('Error processing UPNP: %s' % message, exc_info=True)


        async def updateEverything(self):
            
            try:
                for detail in self.definitions.systemStates:
                    await self.updateState(detail)
                # zone state
                for detail in self.definitions.mainZoneStates:
                    await self.updateState(detail)
            
            except:
                self.log.error('Error updating everything', exc_info=True)

            
            
        async def start(self):

            try:
                self.address=self.dataset.config['address']
                self.port=self.dataset.config['port']
                self.receiver=yamahaXML(log=self.log, dataset=self.dataset)
                await self.updateEverything()
            except:
                self.log.error('error with update',exc_info=True)

            try:
                self.ssdp = self.loop.create_datagram_endpoint(lambda: BroadcastProtocol(self.loop, self.log, self.ssdpkeywords, returnmessage=self.processUPNP), local_addr=("239.255.255.250", 1900))
                await self.ssdp
            except:
                self.log.error('error with ssdp',exc_info=True)


            
        async def command(self, category, item, data):
            
            try:
                response=await self.receiver.sendCommand(category, item, data)
                self.log.info('Command response: %s' % response)
                return response
            except:
                self.log.error('error sending command',exc_info=True)


        async def addSmartDevice(self, path):
            
            try:
                if path.split("/")[2]=="Main_Zone":
                    return self.addSmartSpeaker(path.split("/")[2], "Receiver")

            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False


        def addSmartSpeaker(self, deviceid, name="Receiver"):
            
            nativeObject=self.dataset.nativeDevices['Receiver'][deviceid]
            if name not in self.dataset.devices:
                if "Input" in nativeObject:
                    return self.dataset.addDevice(name, devices.receiver('yamaha/Receiver/%s' % deviceid, name))
            
            return False


        async def processDirective(self, endpointId, controller, command, payload, correlationToken='', cookie={}):
    
            try:
                device=endpointId.split(":")[2]
                nativeCommand={}
                
                if controller=="PowerController":
                    if command=='TurnOn':
                        nativeCommand={"System": {"Power_Control": {"Power": "On"}}}
                    elif command=='TurnOff':
                        nativeCommand={"System": {"Power_Control": {"Power": "Standby"}}}
                elif controller=="SurroundController":
                    if command=="SetSurround":
                        nativeCommand={"Main_Zone": {"Surround": {"Program_Sel": { "Current": {"Sound_Program": payload['surround']}}}}}
                elif controller=="InputController":
                    if command=="SelectInput":
                        nativeCommand={"Main_Zone": {"Input": {"Input_Sel":  payload['input'].replace('_','')}}}
                elif controller=="SpeakerController":
                    if command=="SetVolume":
                        volrange={'max':0, 'min':-80}
                        unitconv=(volrange['max']-volrange['min'])/100
                        realvol=str(int(float(unitconv* int(payload['volume'])))+volrange['min'])+"0"
                        nativeCommand={"Main_Zone": {"Volume": {"Lvl": { "Val": realvol, "Exp": 1, "Unit": "dB"}}}}                 
                        
                if nativeCommand:      
                    response=await self.receiver.sendCommand(nativeCommand, '', payload)
                    self.log.info('<- %s' % response)
                    await self.updateEverything()
                    return await self.dataset.generateResponse(endpointId, correlationToken)
                  
            except:
                self.log.error('Error executing state change.', exc_info=True)

 
        def addControllerProps(self, controllerlist, controller, prop):
        
            try:
                if controller not in controllerlist:
                    controllerlist[controller]=[]
                if prop not in controllerlist[controller]:
                    controllerlist[controller].append(prop)
            except:
                self.log.error('Error adding controller property', exc_info=True)
                
            return controllerlist

        def virtualControllers(self, itempath):

            try:
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                self.log.debug('Checking object for controllers: %s' % nativeObject)
                
                try:
                    detail=itempath.split("/",3)[3]
                except:
                    detail=""

                controllerlist={}
                if "Basic_Status" in nativeObject:
                    if detail=="Basic_Status/Power_Control/Power" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist, "PowerController", "powerState")
                    if detail=="Basic_Status/Volume/Lvl/Val" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist, 'SpeakerController', 'volume')
                    if detail=="Basic_Status/Volume/Mute" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist, 'SpeakerController', 'muted')
                    if detail=="Basic_Status/Input/Input_Sel" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist, 'InputController', 'input')
                    if detail=="Basic_Status/Surround/Program_Sel/Current/Sound_Program" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist, "SurroundController", "surround")
                    if detail=="Basic_Status/Input/Decoder_Sel" or detail=="":
                        controllerlist=self.addControllerProps(controllerlist, "SurroundController", "decoder")
                return controllerlist
            except:
                self.log.error('Error getting virtual controller types for %s' % nativeObj, exc_info=True)
                
                
        def virtualControllerProperty(self, nativeObj, controllerProp):

            if controllerProp=='powerState':
                return "ON" if nativeObj['Basic_Status']['Power_Control']['Power']=="On" else "OFF"

            elif controllerProp=='volume':
                try:
                    #volrange={'max':15, 'min':-70}
                    volrange={'max':0, 'min':-80}
                    zvolume=float(nativeObj['Basic_Status']['Volume']['Lvl']['Val'])/10
                    zpos=int(((volrange['max']-volrange['min'])-(volrange['max']-zvolume))*(100/(volrange['max']-volrange['min'])))
                    return zpos
                except:
                    self.log.error('Error checking volume status', exc_info=True)

            elif controllerProp=='muted':
                try:
                    return nativeObj['Basic_Status']['Volume']['Mute']!='Off'
                except:
                    self.log.error('Error checking Mute status', exc_info=True)

            elif controllerProp=='input':
                try:
                    return nativeObj['Basic_Status']['Input']['Input_Sel']
                except:
                    self.log.error('Error checking Mute status', exc_info=True)

            elif controllerProp=='surround':
                try:
                    return nativeObj['Basic_Status']['Surround']['Program_Sel']['Current']['Sound_Program']
                except:
                    self.log.error('Error checking Surround status', exc_info=True)
            
            elif controllerProp=='decoder':
                try:
                    return nativeObj['Input']['Decoder_Sel']['Current']
                except:
                    self.log.error('Error checking Surround status', exc_info=True)
 
 
                
            else:
                self.log.info('Unknown controller property mapping: %s' % controllerProp)
                return {}


        async def virtualCategory(self, category):
            
            self.log.info('Virtual Category check: %s' % category)
            
            if category=='speaker':
                subset={ 'Main_Zone': self.dataset.mapProperties(self.dataset.nativeDevices['Main_Zone'],['Speaker']) }

            else:
                subset={}
            
            return subset
            
        async def virtualList(self, itempath, query={}):

            try:
                if itempath=="inputs":
                    return self.dataset.nativeDevices['Receiver']['System']['Config']['Name']['Input']
                return {}

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)


if __name__ == '__main__':
    adapter=yamaha(name="yamaha")
    adapter.start()
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
#import definitions
import asyncio
import aiohttp
import xml.etree.ElementTree as et
from collections import defaultdict
import struct
import socket
import urllib.request


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
        data=data.decode()
        for phrase in self.keyphrases:
            if data.find(phrase)>-1:
                if data.find('upnp:rootdevice')>-1:
                    self.processUPNPevent(data)
                #return str(data)
            #else:
             #   self.log.info('>> not the right ssdp: %s' % (data))


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


class sonyRest():

    def __init__(self, log=None, dataset=None):
        self.log=log
        self.dataset=dataset
        self.address=self.dataset.config['address']
        self.port=self.dataset.config['port']
        self.psk=self.dataset.config['psk']
    
    async def remoteControl(self, params):

        method = "POST"
        url="sony/IRCC"
        service='urn:schemas-sony-com:service:IRCC:1#X_SendIRCC'

        soap = 	'<?xml version="1.0"?>'\
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'\
            '<s:Body>'\
            '<u:X_SendIRCC xmlns:u="urn:schemas-sony-com:service:IRCC:1">'\
            '<IRCCCode>%s</IRCCCode>'\
            '</u:X_SendIRCC>'\
            '</s:Body>'\
            '</s:Envelope>' % (params)

        headers = {
            'Host': "%s:%s" % (self.address, self.port),
            'Content-length':len(soap),
            'Content-Type':'text/xml; charset="utf-8"',
            'X-Auth-PSK': self.psk,
            'SOAPAction':'"%s"' % (service)
            }

        req = urllib.request.Request("http://%s:%s/%s" % (self.address, self.port, url), data=soap.encode('ascii'), headers=headers)
        req.get_method = lambda: method

        try:
            response = urllib.request.urlopen(req)
        except urllib.HTTPError:
            self.log.error("!! HTTP Error", exc_info=True)
		
        except urllib.URLError:
            self.log.error("!! URL Error", exc_info=True)

        else:
            tree = response.read()
            #self.log.info('<- command Sent: %s' % str(tree))
            return tree


    async def getState(self, section, method, version='1.0', params=[]):
        
        try:
            url = "http://%s/sony/%s" % (self.address,section)
            headers={'X-Auth-PSK': self.psk}
            command={'id':2, 'method':method, 'version':version}
            if params==[]:
                command['params']=[]
            else:
                command['params']=[params]
            data=json.dumps(command)

            async with aiohttp.ClientSession() as client:
                response=await client.post(url, data=data, headers=headers)
                result=await response.read()
                result=json.loads(result.decode())
                
                if 'result' in result:
                    result=result['result']
                    return result
                if 'results' in result:
                    result=result['results']
                    for subresult in result:
                        self.log.info('Multi-result: %s' % subresult)
                    return result
                elif 'error' in result:
                    if 'Display Is Turned off' in result['error']:
                        pass
                    elif 'Illegal State' in result['error']:
                        pass

                    else:
                        self.log.error('Error result: %s %s' % (result, data))
                    return {}
                else:
                    self.log.info('Result has no result: %s' % result)
                    return result
        except aiohttp.client_exceptions.ClientConnectorError:
            self.log.error('!! Error connecting to TV, likely DNS or IP related')
            return {}
                
        except:
            self.log.error('Error sending command', exc_info=True)
            return {}



class sonybravia(sofabase):

    class adapterProcess(adapterbase):


        def __init__(self, log=None, dataset=None, notify=None, request=None, loop=None, **kwargs):
            self.dataset=dataset
            self.ssdpkeywords=self.dataset.config['ssdpkeywords']

            self.log=log
            self.notify=notify
            self.polltime=5
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
                
        def make_ssdp_sock(self):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', 1900))
            group = socket.inet_aton('239.255.255.250')
            mreq = struct.pack('4sL', group, socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)    
            return sock            

        async def processUPNP(self, message):
            try:
                await self.getUpdate()
            except:
                self.log.error('Error processing UPNP: %s' % message, exc_info=True)
            

        async def getInitialData(self):

            systemdata={    'system':       {   'systemInformation': { 'command':'getSystemInformation', 'listitem':0 },
                                                'remoteCommands': { 'command':'getRemoteControllerInfo', 'listitem':1 }},
                            'appControl':   {   'applications': {'command':'getApplicationList'}}}
            return await self.getStates(systemdata)

        async def getUpdate(self):
            
            systemdata={    'system':       {   'power': { 'command':'getPowerStatus', 'listitem':0 }},
                            'audio':        {   'audio': { 'command':'getVolumeInformation', 'listitem':0}},
                            'avContent':    {   'playingContent': {'command':'getPlayingContentInfo', 'listitem':0 },
                                                'inputStatus': {'command':'getCurrentExternalInputsStatus', 'listitem':0 }}}
            return await self.getStates(systemdata)


        async def getStates(self, systemdata):
            
            alldata={}
            
            try:
                for category in systemdata:
                    for interface in systemdata[category]:
                        if 'params' in systemdata[category][interface]:
                            sysinfo=await self.tv.getState(category, systemdata[category][interface]['command'], params=systemdata[category]['params'])
                        else:
                            sysinfo=await self.tv.getState(category, systemdata[category][interface]['command'])
                            
                        if sysinfo:
                            if 'listitem' in systemdata[category][interface]:
                                await self.dataset.ingest({'tv': { self.tvName: { interface: sysinfo[systemdata[category][interface]['listitem']] }}})
                            else:
                                await self.dataset.ingest({'tv': { self.tvName: { interface: sysinfo }}})
                        if category not in alldata:
                            alldata[category]={}
                        alldata[category][interface]=sysinfo
                return alldata
                
            except:
                self.log.error('error with update',exc_info=True)

        async def getTVname(self):
            
            sysinfo=await self.tv.getState('system','getSystemInformation')
            return sysinfo[0]['name']

        async def start(self):
            try:
                self.input_list=[]
                for port in self.dataset.config['hdmi_port_names']:
                    self.input_list.append(self.dataset.config['hdmi_port_names'][port])
            except:
                self.log.error('Error defining port list', exc_info=True)
                
            self.tv=sonyRest(log=self.log, dataset=self.dataset)
            self.tvName=await self.getTVname()

            try:
                await self.getInitialData()
                await self.getUpdate()

            except:
                self.log.error('error with update',exc_info=True)

            try:
                sock=self.make_ssdp_sock()
                self.ssdp = self.loop.create_datagram_endpoint(lambda: BroadcastProtocol(self.loop, self.log, self.ssdpkeywords, returnmessage=self.processUPNP), sock=sock)
                await self.ssdp
                await self.pollTV()
                
            except:
                self.log.error('error with ssdp',exc_info=True)
           
        async def pollTV(self):
            while True:
                try:
                    #self.log.info("Polling TV")
                    sysinfo=await self.tv.getState('system','getPowerStatus')
                    if sysinfo:
                        await self.dataset.ingest({'tv':  { self.tvName: {'power': sysinfo[0]}}})
                    await asyncio.sleep(self.polltime)
                except:
                    self.log.error('Error fetching TV Data', exc_info=True)

            
        async def command(self, category, item, data):
            
            try:
                response=await self.receiver.sendCommand(category, item, data)
                self.log.info('Command response: %s' % response)
                return response
            except:
                self.log.error('error sending command',exc_info=True)

        async def addSmartDevice(self, path):
            
            try:
                if path.split("/")[2]=="BRAVIA":
                    return self.addSmartTV(path.split("/")[2], "TV")
                else:
                    self.log.info('Path not adding device: %s' % path)

            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False


        def addSmartTV(self, deviceid, name="Bravia"):
            
            nativeObject=self.dataset.nativeDevices['tv'][deviceid]
            if name not in self.dataset.localDevices:
                if "systemInformation" in nativeObject and "power" in nativeObject:
                    return self.dataset.addDevice(name, devices.tv('sonybravia/tv/%s' % deviceid, name, inputs= self.input_list, noSpeaker=True))
            
            return False
            
        def findRemoteCode(self, codename):

            try:
                for code in self.dataset.nativeDevices['tv']['BRAVIA']['remoteCommands']:
                    if code['name']==codename:
                        #self.log.info('Found code for %s: %s' % (codename, code['value']))
                        return code['value']
                self.log.info('No code found for %s' % codename)
                return ''
            except:
                self.log.error('Error getting remote code', exc_info=True)
                return ''

        #async def stateChange(self, endpointId, controller, command, payload):
        async def processDirective(self, endpointId, controller, command, payload, correlationToken='', cookie={}):
    
            try:
                device=endpointId.split(":")[2]
                sysinfo={}
                
                if controller=="PowerController":
                    if command=='TurnOn':
                        sysinfo=await self.tv.getState('system', 'setPowerStatus', params={"status":True})
                    elif command=='TurnOff':
                        sysinfo=await self.tv.getState('system', 'setPowerStatus', params={"status":False})
                
                if controller=="InputController":
                    if command=='SelectInput':
                        if payload['input']=='Home':
                            sysinfo=await self.tv.remoteControl(self.findRemoteCode('Home'))
                        else:
                            inp=payload['input']
                            for port in self.dataset.config['hdmi_port_names']:
                                if payload['input']==self.dataset.config['hdmi_port_names'][port]:
                                    inp='extInput:hdmi?port=%s' % port
                                    break
                                
                            sysinfo=await self.tv.getState('avContent','setPlayContent',params={"uri":inp})
                            if inp.startswith('extInput:cec'):
                                # takes slightly longer for CEC sources to switch than raw AV inputs
                                await asyncio.sleep(.2)

                if controller=="RemoteController":
                    if command=='PressRemoteButton':
                        if self.findRemoteCode(payload['buttonName']):
                            sysinfo=await self.tv.remoteControl(self.findRemoteCode(payload['buttonName']))

                await self.getUpdate()
                    
                response=await self.dataset.generateResponse(endpointId, correlationToken)
                return response
                  
            except:
                self.log.error('Error executing state change.', exc_info=True)


                
        def virtualControllers(self, itempath):
            
            nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                
            try:
                detail=itempath.split("/",3)[3]
            except:
                detail=""

            controllerlist={}
            
            try:
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                controllerlist={}
                
                if detail=="power/status" or detail=="":
                    controllerlist=self.addControllerProps(controllerlist,"PowerController","powerState")
                if detail=="playingContent/uri" or detail=="":
                    controllerlist=self.addControllerProps(controllerlist,"InputController","input")
                #if detail=="playingContent/uri" or detail=="":
                #    controllerlist=self.addControllerProps(controllerlist,"SpeakerController","volume")
                #if detail==
                #    controllerlist=self.addControllerProps(controllerlist,"SpeakerController","volume")

                return controllerlist
            except:
                self.log.error('Error getting virtual controller types for %s' % nativeObj, exc_info=True)


        def getDetailsFromURI(self, uri):
            
            try:
                result={}
                conninfo=uri.split('?')[0]
                result['source']=conninfo.split(':')[0]
                result['type']=conninfo.split(':')[1]
                
                details=uri.split('?')[1]
                details=details.split('&')
                for detail in details:
                    dparts=detail.split('=')
                    result[dparts[0]]=dparts[1]
                    
                return result
            except:
                self.log.error('Error parsing input URI: %s' % uri, exc_info=True)
                

        def getInputName(self,nativeObj):
            
            try:
                if 'playingContent' not in nativeObj:
                    self.log.warn('No playing content: %s' % nativeObj)
                    return 'Android TV'
                details=self.getDetailsFromURI(nativeObj['playingContent']['uri'])
                if details['type'] in ['cec','hdmi']:
                    if details['port'] in self.dataset.config['hdmi_port_names']:
                        return self.dataset.config['hdmi_port_names'][details['port']]

                return nativeObj['playingContent']['title']
                    
            except:
                self.log.error('Error getting virtual input name for %s' % nativeObj, exc_info=True)

        def virtualControllerProperty(self, nativeObj, controllerProp):
            
            #self.log.info('NativeObj: %s' % nativeObj)

            if controllerProp=='powerState':
                return "ON" if nativeObj['power']['status']=="active" else "OFF"

            elif controllerProp=='input':
                try:
                    return self.getInputName(nativeObj)
                    #return nativeObj['playingContent']['title']
                except KeyError:
                    if nativeObj['power']['status']=="active":
                        return 'Android TV'
                    else:
                        return "Off"
                except:
                    self.log.error('Error checking input status', exc_info=True)
                
            else:
                self.log.info('Unknown controller property mapping: %s' % controllerProp)
                return {}

        async def virtualList(self, itempath, query={}):

            try:
                if itempath=="inputdata":
                    return self.dataset.nativeDevices['tv']['BRAVIA']['inputStatus']

                if itempath=="inputs":
                    return self.dataset.config['hdmi_port_names']
                    #return self.dataset.nativeDevices['tv']['BRAVIA']['inputStatus']

                if itempath=="status":
                    return await self.getUpdate()

                return {}

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)


if __name__ == '__main__':
    adapter=sonybravia(name="sonybravia")
    adapter.start()
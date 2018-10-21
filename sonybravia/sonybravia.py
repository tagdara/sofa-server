#!/usr/bin/python3

import sys
sys.path.append('/opt/beta')
import devices

from sofabase import sofabase

import math
import random
from collections import namedtuple
import json
#import definitions
import asyncio
import aiohttp
import xml.etree.ElementTree as et
from collections import defaultdict
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
        #self.log.info('data received: %s %s' % (data, addr))
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
            self.log.info('<- command Sent: %s' % str(tree))
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
                
        except:
            self.log.error('Error sending command', exc_info=True)



class sonybravia(sofabase):

    class adapterProcess():


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


        async def processUPNP(self, message):
            try:
                self.log.debug('SSDP Message: %s' % message)
                await self.getUpdate()
            except:
                self.log.error('Error processing UPNP: %s' % message, exc_info=True)
            

        async def getUpdate(self):
            
            systemdata={    'system':       {   'power': { 'command':'getPowerStatus', 'listitem':0 },
                                                'systemInformation': { 'command':'getSystemInformation', 'listitem':0 },
                                                'remoteCommands': { 'command':'getRemoteControllerInfo', 'listitem':1 }
                                            },
                            'appControl':   {   'applications': {'command':'getApplicationList'}
                                            },
                            'avContent':    {   'playingContent': {'command':'getPlayingContentInfo', 'listitem':0 },
                                                'inputStatus': {'command':'getCurrentExternalInputsStatus', 'listitem':0 }
                                            }

                        }

            try:
                for category in systemdata:
                    for interface in systemdata[category]:
                        self.log.debug('Interface: %s' % systemdata[category][interface])
                        if 'params' in systemdata[category][interface]:
                            sysinfo=await self.tv.getState(category, systemdata[category][interface]['command'], params=systemdata[category]['params'])
                        else:
                            sysinfo=await self.tv.getState(category, systemdata[category][interface]['command'])
                            
                        if sysinfo:

                            if 'listitem' in systemdata[category][interface]:
                                await self.dataset.ingest({'tv': { self.tvName: { interface: sysinfo[systemdata[category][interface]['listitem']] }}})
                            else:
                                await self.dataset.ingest({'tv': { self.tvName: { interface: sysinfo }}})
            except:
                self.log.error('error with update',exc_info=True)

        async def oldupdate(self):    
            
                sysinfo=await self.tv.getState('system','getSystemInformation')
                await self.dataset.ingest({'tv': {'systemInformation': sysinfo[0]}})
                sysinfo=await self.tv.getState('system','getPowerStatus')
                await self.dataset.ingest({'tv': {'status': sysinfo[0]}})
                sysinfo=await self.tv.getState('system','getRemoteControllerInfo')
                await self.dataset.ingest({'tv': {'remoteCommands': sysinfo[1]}})
                syscmd=await self.tv.getState('system','getMethodTypes',params=['1.0'])
                self.log.info('Syscmd: %s' % syscmd)
                sysinfo=await self.tv.getState('appControl','getApplicationList')
                #sysinfo=await self.tv.getState('appControl','getMethodTypes',params=['1.0'])
                await self.dataset.ingest({'tv': {'appControl': sysinfo}})
                #self.loop.run_until_complete(self.tv.getState('appControl','getMethodTypes',params=['1.0']))
            
        async def getTVname(self):
            
            sysinfo=await self.tv.getState('system','getSystemInformation')
            return sysinfo[0]['name']

        async def start(self):
            self.tv=sonyRest(log=self.log, dataset=self.dataset)
            self.tvName=await self.getTVname()

            try:
                await self.getUpdate()
            except:
                self.log.error('error with update',exc_info=True)

            try:
                self.ssdp = self.loop.create_datagram_endpoint(lambda: BroadcastProtocol(self.loop, self.log, self.ssdpkeywords, returnmessage=self.processUPNP), local_addr=("239.255.255.250", 1900))
                await self.ssdp
                await self.pollTV()
                
            except:
                self.log.error('error with ssdp',exc_info=True)
           
        async def pollTV(self):
            while True:
                try:
                    #self.log.info("Polling TV")
                    sysinfo=await self.tv.getState('system','getPowerStatus')
                    await self.dataset.ingest({'tv':  { self.tvName: {'power': sysinfo[0]}}})
                    await asyncio.sleep(self.polltime)
                except:
                    self.log.error('Error fetching Hue Bridge Data', exc_info=True)

            
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
            if name not in self.dataset.devices:
                if "systemInformation" in nativeObject and "power" in nativeObject:
                    return self.dataset.addDevice(name, devices.tv('sonybravia/tv/%s' % deviceid, name))
            
            return False
            
        def findRemoteCode(self, codename):

            try:
                for code in self.dataset.nativeDevices['tv']['BRAVIA']['remoteCommands']:
                    if code['name']==codename:
                        self.log.info('Found code for %s: %s' % (codename, code['value']))
                        return code['value']
                self.log.info('No code found for %s' % codename)
                return ''
            except:
                self.log.error('Error getting remote code', exc_info=True)
                return ''

        async def stateChange(self, device, controller, command, payload):
    
            try:
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
                            sysinfo=await self.tv.getState('avContent','setPlayContent',params={"uri":payload['input']})
                        
                if sysinfo:      
                    self.log.info('-> command response: %s' % sysinfo)
                    await self.getUpdate()
                  
            except:
                self.log.error('Error executing state change.', exc_info=True)


                
        def virtualControllers(self, itempath):

            try:
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                controllerlist={}
                if "systemInformation" in nativeObject:
                    controllerlist["PowerController"]=["powerState"]
                    controllerlist["InputController"]=["input"]
                return controllerlist
            except:
                self.log.error('Error getting virtual controller types for %s' % nativeObj, exc_info=True)


        def virtualControllerProperty(self, nativeObj, controllerProp):
            
            #self.log.info('NativeObj: %s' % nativeObj)

            if controllerProp=='powerState':
                return "ON" if nativeObj['power']['status']=="active" else "OFF"

            elif controllerProp=='input':
                try:
                    return nativeObj['playingContent']['title']
                except KeyError:
                    return 'Off'
                except:
                    self.log.error('Error checking input status', exc_info=True)
                
            else:
                self.log.info('Unknown controller property mapping: %s' % controllerProp)
                return {}

        async def virtualList(self, itempath, query={}):

            try:
                if itempath=="inputs":
                    return self.dataset.nativeDevices['tv']['BRAVIA']['inputStatus']
                return {}

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)


if __name__ == '__main__':
    adapter=sonybravia(port=9089, adaptername="sonybravia", isAsync=True)
    adapter.start()
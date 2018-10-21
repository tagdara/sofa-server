#!/usr/bin/python3

import sys
sys.path.append('/opt/beta')

from sofabase import sofabase
import devices
import json
import asyncio
import concurrent.futures
import datetime

import socket
import struct

class pcServer(sofabase):

    class adapterProcess():
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.dataset.nativeDevices['desktop']={}

            #self.definitions=definitions.Definitions
            self.adapterTopics=['sofa/pc']
            self.log=log
            self.notify=notify
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            
        async def start(self):
            self.log.info('.. Starting PC Manager')
            try:
                if 'cachedDevices' in self.dataset.config:
                    for dev in self.dataset.config['cachedDevices']:
                        await self.dataset.ingest({"desktop": { dev : self.dataset.config['cachedDevices'][dev] }}) 

            except:
                self.log.error('Error loading cached devices', exc_info=True)
                
            await self.notify('sofa/pc','{"op":"discover"}')
            
        # MQTT Adapter Specific Overlays
        async def processAdapterTopicMessage(self, topic, payload):
        
            try:
                self.log.info('Adapter MQTT Data received on topic %s: %s' % (topic,payload))
                try:
                    message=json.loads(payload)
                except json.decoder.JSONDecodeError:
                    self.log.error('Non JSON data received.')
                    return False
                
                if 'op' in message:
                    if message['op']=='state':
                        await self.dataset.ingest({"desktop": { message['device'] : message['state'] }})        

                if 'op' in message:
                    if message['op']=='change':
                        await self.dataset.ingest({"desktop": { message['device'] : { message['property']: message['value'] }}})        

                        
            except:
                self.log.error('Error handling Adapter MQTT Data', exc_info=True)


        async def updateDevice(self, obj):
            
            try:
                obj['state']={}
                await self.dataset.ingest({"desktop": { obj['friendlyName'] :obj }})
            except:
                self.log.error('Error updating device list: %s' % objlist[obj],exc_info=True)

        # Adapter Overlays that will be called from dataset
        def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="desktop":
                    return self.addSmartPC(path.split("/")[2])

            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False

        def checkCache(self, name):

            try:
                if 'cachedDevices' not in self.dataset.config:
                    self.log.info('Config does not have cache: %s' % self.dataset.config)
                    self.dataset.config['cachedDevices']=[]
                
                if name in self.dataset.config['cachedDevices']:
                    return False
                #for dev in self.dataset.config['cachedDevices']:
                #    if dev['friendlyName']==nativeObject['friendlyName']:
                #        return False
                        
                self.dataset.config['cachedDevices'].append(nativeObject)
                self.log.info('config now: %s' % self.dataset.config)
                self.dataset.saveConfig()
            except:
                self.log.error('Error checking cache', exc_info=True)
                return False


        async def addSmartPC(self, name):
            
            nativeObject=self.dataset.nativeDevices['desktop'][name]
            
            if name not in self.dataset.localDevices:
                self.checkCache(name)
                return self.dataset.addDevice(name, devices.smartPC('pc/desktop/%s' % name, name))
            
            return False
            

        async def nativeAlexaStateChange(self, event):
    
            try:
                if 'directive' in event:
                    pcname=event['directive']['endpoint']['endpointId'].split(':')[2]
                    if event['directive']['header']['name']=='TurnOn':
                        # should probably check to see if the machine is on, and if so also send the command so that
                        # things like unlock or wake-from-just-monitor-sleep will work without WOL
                        self.log.info('Alexa TurnOn Command')
                        if pcname in self.dataset.config['cachedMacAddresses']:
                            self.log.info('Sending Wake On LAN packet to: %s %s' % (pcname, self.dataset.config['cachedMacAddresses'][pcname]))
                            self.wakeonlan(self.dataset.config['cachedMacAddresses'][pcname])
                            return []
                        else:
                            self.log.info('Did not find MAC address for %s in %s' % ( pcname, self.dataset.config['cachedMacAddresses']))
                    elif event['directive']['header']['name']=='TurnOff':         
                        cmd={"op":"set", "property":"powerState", "value":"OFF", 'device': pcname }
                        await self.notify('sofa/pc', json.dumps(cmd))
                    elif event['directive']['header']['name']=='Lock':         
                        cmd={"op":"set", "property":"lockState", "value":"LOCKED", 'device': pcname }
                        await self.notify('sofa/pc', json.dumps(cmd))
                    elif event['directive']['header']['name']=='Unlock':
                        cmd={"op":"set", "property":"lockState", "value":"UNLOCKED", 'device': pcname }
                        await self.notify('sofa/pc', json.dumps(cmd))

                return []
            except:
                self.log.error('Error executing state change.', exc_info=True)

            
        def virtualControllers(self, itempath):

            try:
                itempart=itempath.split("/",3)
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                try:
                    detail=itempath.split("/",3)[3]
                except:
                    detail=""

                controllerlist={}

                if detail=="powerState" or detail=="":
                    controllerlist["PowerController"]=["powerState"]
                if detail=="lockState" or detail=="":
                    controllerlist["LockController"]=["lockState"]
                
                return controllerlist

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)


        def virtualControllerProperty(self, nativeObj, controllerProp):
        
            try:
                if controllerProp=='powerState':
                    return nativeObj['powerState']

                if controllerProp=='lockState':
                    return nativeObj['lockState']
                    
                self.log.info('Did not find %s in %s' % (controllerProp,nativeObj['state']))

            except:
                self.log.error('Error converting virtual controller property: %s %s' % (controllerProp, nativeObj), exc_info=True)

        async def virtualList(self, itempath, query={}):

            try:
                if itempath=="agentversion":
                    try:
                        with open('/opt/beta/pc/sofaagent.py','r') as agentfile:
                            line = agentfile.readline()
                            version='0000'
                            while line and version=='0000':
                                if line.startswith('SofaAgentVersion = '):
                                    version=line[19:].strip('\n').strip('\r')
                                line = agentfile.readline()
                    
                            self.log.info('Current Agent Version is: %s' % version )
                            return version
                    except:
                        self.log.error('Error determining Agent Version',exc_info=True)
                        return "0000"

                if itempath=="agent":
                    try:
                        with open('/opt/beta/pc/sofaagent.py','r') as agentfile:
                            return agentfile.read()
                    except:
                        self.log.error("Error loading agent file" ,exc_info=True)
                        return ""
            
            except:
                self.log.error('Error getting virtual list for %s' % itempath, exc_info=True)



        def wakeonlan(self, macaddress):
        
            try:
                if len(macaddress) == 12:
                    pass
                elif len(macaddress) == 12 + 5:
                    sep = macaddress[2]
                    macaddress = macaddress.replace(sep, '')
 
                # Pad the synchronization stream.
                data = ''.join(['FFFFFFFFFFFF', macaddress * 20])
                send_data = b'' 

                # Split up the hex values and pack.
                for i in range(0, len(data), 2):
                    send_data = b''.join([send_data, struct.pack('B', int(data[i: i + 2], 16))])
                # Broadcast it to the LAN.
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.sendto(send_data, ('<broadcast>', 7))    
                self.log.info('>> WOL magic packet sent to '+str(macaddress))
            except:
                self.log.error('Error sending Wake On LAN packet: %s' % macaddress, exc_info=True)


        def command(self, category, item, data):
            pass
        
        def get(self, category, item):
            pass
        


if __name__ == '__main__':
    adapter=pcServer(port=8097, adaptername='pc', isAsync=True)
    adapter.start()
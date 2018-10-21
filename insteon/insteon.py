#!/usr/bin/python3

import sys
sys.path.append('/opt/beta')
from sofabase import sofabase
import devices

import math
import random
import requests
import json
import asyncio
import definitions
import aiohttp
import base64
from collections import defaultdict
import xml.etree.ElementTree as et
import urllib.request

import deepdiff
from deepdiff import DeepDiff


class insteonAuthentication():
    
    async def authenticate(self, client):
        async with aiohttp.ClientSession() as client:
            html = await self.authenticate(client)
            return html

            self.insteonAddress='lights.dayton.home'
            self.port=80
            self.username="admin"
            self.password="$$lights11"
            self.payload='<s:Envelope><s:Body><u:Authenticate xmlns:u="urn:udi-com:service:X_Insteon_Lighting_Service:1"><name>%s</name><id>%s</id></u:Authenticate></s:Body></s:Envelope>\r\n' % (self.username, self.password)
            self.basicauth="Basic %s" % base64.encodebytes(("%s:%s" % (self.username,self.password)).encode('utf-8')).decode()

            url = 'http://%s' % self.insteonAddress
            headers = { "Authorization": self.basicauth, 
                        "SOAPACTION": '"urn:udi-com:service:X_Insteon_Lighting_Service:1#Authenticate"'}

            return await client.post(url, data=self.payload, headers=headers)        


            
class insteonCatalog():
    
    def __init__(self, log=None, dataset=None):
        self.dataset=dataset
        self.definitions=definitions.Definitions
        self.insteonAddress=self.dataset.config['address']
        self.port=self.dataset.config['port']
        self.username=self.dataset.config['user']
        self.password=self.dataset.config['password']
        self.log=log
        self.basicauth="Basic %s" % base64.encodebytes(("%s:%s" % (self.username,self.password)).encode('utf-8')).decode()
        self.sema = asyncio.Semaphore(5)
        
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

    async def authenticate(self):
        async with aiohttp.ClientSession() as client:
            self.payload='<s:Envelope><s:Body><u:Authenticate xmlns:u="urn:udi-com:service:X_Insteon_Lighting_Service:1"><name>%s</name><id>%s</id></u:Authenticate></s:Body></s:Envelope>\r\n' % (self.username, self.password)

            url = 'http://%s' % self.insteonAddress
            headers = { "Authorization": self.basicauth, 
                        "SOAPACTION": '"urn:udi-com:service:X_Insteon_Lighting_Service:1#Authenticate"'}

            return await client.post(url, data=self.payload, headers=headers)        

        
    async def getNodesList(self,client):
        
        try:
            self.log.info("GetNodesConfig Obtaining list of insteon nodes")
            self.nodesmaster={}
            url = "http://%s/rest/nodes/" % self.insteonAddress
            headers = { "Authorization": self.basicauth }
            data = await client.get(url, headers=headers)
            html = await data.read() 
            return html
        except:
            self.log.error("GetNodesList failed",exc_info=True)

    def getFolders(self, nodelist):
        
        folders=dict()
        for node in root.findall('folder'):
            address = node.find('address').text
            flag = node.get('flag')
            name = node.find('name').text
            try:
                parent = node.find('parent').text
            except:
                parent = '0000'

            folders[address]={"name":name,"parent":parent,"flag":flag,"address":address}
        
        for folder in folders:
            if folders[folder]['parent']=='0000':
                folders[folder]['parentname']='My Lighting'
            else:
                folders[folder]['parentname']=folders[folders[folder]['parent']]['name']
            self.log.debug("Folder discovered: "+str(folders[folder]))

        return folders
        
    async def getGroups(self,root):
        
        xmlgroups=[]
        groupprops=dict()

        for node in root.findall('group'):
            
            address = node.find('address').text
            flag = node.get('flag')
            name = node.find('name').text
            
            try:
                parent = node.find('parent').text
            except:
                parent = '0000'
                parentname = 'My Lighting'
                
            try:
                parentname=self.folders['folder'][parent]['name']
            except:
                parentname=parent
                
            xmlgroups.append([address,name])

            groupprops[address]=dict()
            groupprops[address]['address']=address
            groupprops[address]['name']=name
            groupprops[address]['parent']=parent
            groupprops[address]['parentname']=parentname
            self.log.debug("Group discovered: "+str(address)+":"+str(groupprops[address]))

        #return sorted(xmlgroups,key=itemgetter(1))
        return groupprops


    async def getNodeProperties(self, address):

        url="http://%s/rest/nodes/%s" % (self.insteonAddress, urllib.request.quote(address))
        headers = { "Authorization": self.basicauth }
        async with aiohttp.ClientSession() as client:
            async with self.sema, client.get(url, headers=headers) as data:
                html = await data.read()
        noderoot = et.fromstring(html)

        nodeprops={}
        for nodeproplist in noderoot.findall('properties'):
            for nodeprop in nodeproplist.findall('property'):
                #nodeprops[nodeprop.get("id")]=nodeprop.get("value")
                if nodeprop.get("id")!=None:
                    nodeprops[nodeprop.get("id")]=nodeprop.attrib  
                
        #self.log.info('Get props for '+str(address)+'='+str(nodeprops))
        return nodeprops
        
    def getNodeType(self,node):
        
        devicetypes={   'button': ["0.18.0.0","0.17.0.0","0.5.0.0"],
                        'thermostat': ['5.11.11.0'],
                        'light': ['1.9.43.0','1.0.51.0','1.1.53.0','1.6.51.0','1.14.58.0', '1.14.65.0','1.25.56.0','1.25.64.0','1.28.57.0','1.32.64.0','1.32.65.0','2.6.65.0','2.9.0.0','2.42.67.0','2.56.67.0'],
                        'device': ["2.31.65.0","3.13.0.0","2.55.70.0"]
                    }
                        
        try:
            self.log.info('Determining type for %s: %s %s' % (node['address'], node['pnode'], node['type']))
            #if node['name'] in self.adapterconfig['exceptions']:
            #    devtype=self.adapterconfig['exceptions'][node['name']]
            if (node['pnode']!=node['address']) and node['type'] in devicetypes['light']:
                return "button"
            elif node['type'] in devicetypes['button']:
                return "button"
            elif node['type'] in devicetypes['thermostat']:
                return "thermostat"
            elif node['type'] in devicetypes['device']:
                return "device"
            elif node['pnode']==node['address'] and (node['flag']=='128' or node['flag']=='144') and node['type'] in devicetypes['light']:
                return "light"
            else:
                return "unknown"
        
        except:
            self.log.error('Error determining node type',exc_info=True)
            return 'unknown'

         
    async def getNodes(self, root):

        try:
            if 'node' not in self.dataset.nativeDevices:
                self.dataset.nativeDevices['node']={}
            xnodes={}
            for node in root.findall('node'):
                xn=node.find('address').text
                xnodes[xn]=dict()
                xnodes[xn]['property']=dict()
                xnodes[xn]['flag']=node.get('flag')
                for prop in node.iter():
                    if prop.tag=='property':
                        xnodes[xn]['property'][prop.get("id")]=prop.attrib
                    elif prop.tag=='node':
                        pass
                    else:
                        xnodes[xn][prop.tag]=prop.text
                xnodes[xn]['devicetype']=self.getNodeType(xnodes[xn])
                if xnodes[xn]['devicetype'] in ['light','thermostat']:
                    xnodes[xn]['property']=await self.getNodeProperties(xn)
                if 'parent' in xnodes[xn]:
                    try:
                        if xnodes[xn]['parent'] in self.data['folder']:
                            xnodes[xn]['parentname']=self.dataset.nativeDevices['folder'][xnodes[xn]['parent']]['name']
                        elif xnodes[xn]['parent'] in self.dataset.nativeDevices['node']:
                            xnodes[xn]['parentname']=self.dataset.nativeDevices['node'][xnodes[xn]['parent']]['name']
                    except:
                        self.log.error('couldnt get parentname',exc_info=True)
        except:
            self.log.error('error making xnodes',exc_info=True)

        return xnodes

       
    async def main(self):
        async with aiohttp.ClientSession() as client:
            itemProperty=''
            html = await self.getNodesList(client)
            nodesJSON=self.etree_to_dict(et.fromstring(html))

            try:
                for nodetype in nodesJSON['nodes']:
                    if nodetype not in self.dataset.nativeDevices:
                        self.dataset.nativeDevices[nodetype]={} # helps make sure the first added item uses the same format as subsequent
                    try:
                        for item in nodesJSON['nodes'][nodetype]:
                            try:
                                if 'property' in item:
                                    item['property']=await self.getNodeProperties(item['address']) # Replace subset of property with complete set
                                    item['devicetype']=self.definitions.deviceTypes[item['type']]
                                    if item['devicetype']=='light':
                                        # fix for multi-button keypads
                                        if (item['pnode']!=item['address']):
                                            item['devicetype']='button'

                            except:
                                self.log.error('couldnt get property or find device type for: %s / %s' % (item['address'],item['type']), exc_info=True)
                            
                            await self.dataset.ingest({ nodetype: { item['address']:  item }})
                    except TypeError:
                        self.log.warn('No data in node type: %s' % nodetype)
                    except:
                        self.log.error('Couldnt walk node type %s: %s' % (nodetype,itemProperty), exc_info=True)

            except:
                self.log.error('Error with main', exc_info=True)
            


class insteonSubscription(asyncio.Protocol):

    def __init__(self, loop, log=None, notify=None, dataset=None, **kwargs):
        self.dataset=dataset
        self.is_open = False
        self.loop = loop
        self.log=log
        self.last_message = ""
        self.definitions=definitions.Definitions
        self.sendQueue=[]
        self.notify=notify
        self.insteonAddress=self.dataset.config['address']
        self.port=self.dataset.config['port']
        self.username=self.dataset.config['user']
        self.password=self.dataset.config['password']
        self.eventdata=''
        self.logbusy=False
        self.catalog=insteonCatalog
        self.controllerBusy=False
        self.basicauth="Basic %s" % base64.encodebytes(("%s:%s" % (self.username,self.password)).encode('utf-8')).decode()
        self.pendingChanges=[]

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


    async def getNodeProperties(self, address):

        try:
            url="http://%s/rest/nodes/%s" % (self.insteonAddress, urllib.request.quote(address))
            headers = { "Authorization": self.basicauth }
            async with aiohttp.ClientSession() as client:
                async with self.sema, client.get(url, headers=headers) as data:
                    html = await data.read()
                    noderoot = et.fromstring(html)

            nodeprops={}
            for nodeproplist in noderoot.findall('properties'):
                for nodeprop in nodeproplist.findall('property'):
                    #nodeprops[nodeprop.get("id")]=nodeprop.get("value")
                    if nodeprop.get("id")!=None:
                        nodeprops[nodeprop.get("id")]=nodeprop.attrib  
                
            #self.log.info('Get props for '+str(address)+'='+str(nodeprops))
            return nodeprops
        except:
            self.log.error('Error getting node properties: %s' % url, exc_info=True)

    def Setloglevel(self, level, transport):

        try:
            logstr="<s:Envelope><s:Body><u:SetDebugLevel xmlns:u=\"urn:udi-com:service:X_Insteon_Lighting_service:1\"><option>"+level+"</option></u:SetDebugLevel></s:Body></s:Envelope>"
            loghead="POST /services HTTP/1.1\r\n"
            loghead+="Host: %s:%u\r\n" % (self.insteonAddress,self.port)
            loghead+="Content-Length: %u\r\n" % len(logstr)
            loghead+="Content-Type: text/xml; charset=\"utf-8\"\r\n"	
            loghead+="Authorization: Basic "+ self.basicauth
            loghead+="SOAPACTION:\"urn:udi-com:service:X_Insteon_Lighting_Service:1#SetDebugLevel\"\r\n\r\n"
            loghead+=logstr+"\r\n"
            transport.write(loghead.encode())
            
            #sock.send(loghead.encode())
            answer = transport.recv(1024).decode()
            #sock.close()
            self.log.info('answer: %s' % answer)
            # print "Set Log Level response: "+answer
            #if (answer.find("HTTP/1.1 200 OK") == -1):
            #    self.adapter.forwardevent(action="info",data="Could not set log level")
            #    self.adapter.forwardevent(action="info",data=answer.strip())
            #    return False
            #else:
            #    self.log.info("Log level set to "+str(level))
            #    #self.adapter.forwardevent(action="info",data="Log level set to "+level)
            #    return True
        except:
            self.log.error('Error setting ISY Log Level',exc_info=True)
            return False        
                
    def sendSubscribeRequest(self, transport):
        try:
            subscribestr="<s:Envelope><s:Body><u:Subscribe xmlns:u=\"urn:udi-com:service:X_Insteon_Lighting_Service:1\"></u:Subscribe></s:Body></s:Envelope>"
            connecthead="SUBSCRIBE /eventing HTTP/1.1\r\n"
            connecthead+="Host: %s:%u\r\n" % (self.insteonAddress,self.port)
            connecthead+="Content-Length: %u\r\nContent-Type: text/xml; charset=\"utf-8\"\r\n" % len(subscribestr)
            connecthead+="CALLBACK:<REUSE_SOCKET>\r\nNT:upnp:event\r\nTIMEOUT:Second-infinite\r\n"
            connecthead+="Authorization: %s" % self.basicauth
            connecthead+="SOAPACTION:\"urn:udi-com:service:X_Insteon_Lighting_Service:1#Subscribe\"\r\n\r\n"
            connecthead+=subscribestr+"\r\n"
            transport.write(connecthead.encode())
        except:
            self.log.error('Error subscribing to ISY', exc_info=True)

   
    def connection_made(self, transport):
        
        try:
            self.sockname = transport.get_extra_info("sockname")
            self.transport = transport
            self.is_open = True
            #self.log.info('Sending log level request')
            #self.Setloglevel('3',self.transport)
            self.log.info('Sending subscription request')
            self.sendSubscribeRequest(self.transport)
            self.sema = asyncio.Semaphore(5)
        except:
            self.log.error('Insteon Subscriber Connection made but something went wrong.', exc_info=True)
        

    def connection_lost(self, exc):
        self.log.info('Insteon Subscription Connection lost')
        self.is_open = False
        self.loop.stop()
        
        
    def send(self, data):
        
        try:
            self.transport.write(data.encode())
            self.log.info('> insteon  %s' % data)
        except:
            self.log.error('Error on send', exc_info=True)


    def data_received(self, data):

        self.eventdata=self.eventdata+data.decode()
        
        while (self.eventdata.find("<Event") > -1):
            try:
                event=self.eventdata[self.eventdata.find("<Event"):self.eventdata.find("</Event>")+8]
                self.eventdata=self.eventdata[self.eventdata.find("</Event>")+8:]
                #self.log.info('insteon > (%s)' % event)
                asyncio.ensure_future(self.process_event(event))
            except:
                self.log.error('Error on receive: %s' % self.eventdata, exc_info=True)


    async def process_event(self, eventdata):
        
        try:
            event=self.etree_to_dict(et.fromstring(eventdata))['Event']
        except:
            self.log.error('Error parsing event to dict: %s' % eventdata, exc_info=True)
            return None
            
        try:
            if event['control']=='_0':
                self.process_heartbeat(event)
            elif event['control']=='_1':
                self.process_triggerevents(event)
            elif event['control']=='_3':
                self.process_nodechanged(event)
            elif event['control']=='_4':
                self.log.debug('Systems setting change reported: %s' % event['action'])
            elif event['control']=='_5':
                self.process_busystate(event)
                self.log.debug('Busy state command: %s' % event)
                if event['action']=='1':
                    self.controllerBusy=True
                if event['action']=='0':
                    self.controllerBusy=False
            elif event['control']=="_7":  # Progress Report.  Whatever that is.
                self.log.debug("Progress Report: %s " % event['action'])

            elif event['control']=="_19": # Elk commands per https://www.universal-devices.com/developers/wsdk/3.3.1/ISY-WS-SDK-ELK.pdf
                pass

            elif event['control']=='ERR':
                if event['action']!='0':
                    self.log.info('Node is in error state: %s (%s)' % (event['node'], event['action']))
                else:
                    self.log.debug('Node is in cleared error state: %s (%s)' % (event['node'], event['action']))
                
            elif event['control'] in ['RR','OL','ST','UOM','CLIFS','CLIHCS','CLIHUM','CLIMD','CLISPC','CLISPH']:
                
                # These controls seem to hit before the actual device is updated, so the follow-on REST check
                # comes back with the existing data and nothing happens.  A later update occurs with a _3 node change to 
                # confirm the node has changed. 
                # Since this issues a request for each message that is wasted, consider eliminating this altogether,
                # but confirm that all functionality is handled by a _3 (thermostats, etc)
                
                try:
                    try:
                        #self.log.info('Property event: %s %s' % (event['node'],event))
                        #self.log.info('Existing data: %s' % self.dataset.nativeDevices['node'][event['node']])
                        if event['control'] in self.dataset.nativeDevices['node'][event['node']]['property']:
                            if self.dataset.nativeDevices['node'][event['node']]['property'][event['control']]['value']==event['action']:
                                return None
                    except:
                        self.log.error('Error comparing previous state', exc_info=True)
                    #self.log.info('Property event: %s %s' % (event['node'],event))
                    #self.log.info('Existing data: %s %s' % (event['node'], self.dataset.nativeDevices['node'][event['node']]))
                    if event['node'] not in self.pendingChanges:
                        # testing allowing the _1 update to provide the update when the change was requested by the UI
                        updatedProperties=await self.getNodeProperties(event['node'])
                        self.log.info('event UpdatedProperties: %s %s' % (event['node'], updatedProperties))
                        changeReport=await self.dataset.ingest({'node': { event['node']: {'property':updatedProperties}}})
                        if changeReport:
                            self.log.info('event changereport: %s' % changeReport)
                    else:
                        updatedProperties=await self.getNodeProperties(event['node'])
                        self.log.info('Update processing deferred to change: %s %s' %  (updatedProperties, self.dataset.nativeDevices['node'][event['node']]))

                except TimeoutError:
                    self.log.error('Timeout accessing ISY for node properties: %s' % event['node'])
                except:
                    self.log.error('Error updating node: %s (%s)' % (event['node'], eventdata), exc_info=True)

            else: 
                self.log.info('Unprocessed response: %s (%s)' % (event, eventdata))
        except:
            self.log.warn('No control found in %s' % event,exc_info=True)


    def process_heartbeat(self, event):
        
        try:
            self.log.debug('Heartbeat with interval of %s seconds' % event['action'])
        except:
            self.log.warn('Error processing heartbeat: %s' % event,exc_info=True)


    def process_busystate(self, event):

        try:
            self.log.debug('insteon controller > %s' % self.definitions.busyStates[event['action']])
        except:
            self.log.warn('Error processing busy state: %s' % event,exc_info=True)
            
    def process_triggerevents(self, event):
        
        try:
            self.log.debug('Trigger Event > %s > %s' % (self.definitions.triggerEvents[event['action']], event['eventInfo']))
        except:
            self.log.warn('Error processing trigger event %s' % event,exc_info=True)

        try:
            #self.log.info('<[ %s %s ' % (event['action'],event))
            if event['action']=='3':
                vEvent={}
                vEvent['node']=event['eventInfo'][event['eventInfo'].find("[")+1:event['eventInfo'].find("]")].strip()
                try:
                    vEvent['name']=self.dataset.nativeDevices['node'][vEvent['node']]['name']
                except:
                    pass
                    
                vEvent['cmd']=event['eventInfo'][event['eventInfo'].find("]")+1:].strip()
                if vEvent['node'].find('VAR')>-1:
                    vEvent['var']=vEvent['node'].split()[1]
                    vEvent['val']=vEvent['node'].split()[2]
                    self.log.info("insteon Variable %s set to %s" % (vEvent['var'], vEvent['val']))
                elif vEvent['node']=="Time":
                    self.log.debug("Time info: %s %s" % (vEvent['node'], event['eventInfo']))
                else:
                    vEvent['val']=int(vEvent['cmd'].split()[1])
                    vEvent['command']=vEvent['cmd'].split()[0]
                    self.log.info('<[ %s' % vEvent)
                    if vEvent['node'] in self.pendingChanges:
                        self.pendingChanges.remove(vEvent['node'])
                    if vEvent['command'] in ['DON','DOF','DFOF','DFON']:
                        self.log.info('Button command received on Insteon Bus: %s' % vEvent)
                        asyncio.ensure_future(self.notify("insteon",json.dumps(vEvent)))

        except:
            self.log.error('Error handling trigger event: %s' % event, exc_info=True)


    def process_nodechanged(self, event):
        
        try:
            if self.definitions.nodeChanges[event['action']]=="Node Error (Comm. Errors)":
                if self.dataset.nativeDevices['node'][event['node']]['type'] in self.definitions.wirelessDeviceTypes:
                    self.log.debug('Node Changed > %s (wireless) > %s' % (self.definitions.nodeChanges[event['action']], event['node']))
                    return None
                    
            self.log.info('Node Changed > %s > %s' % (self.definitions.nodeChanges[event['action']], event['node']))
            if event['node'] in self.pendingChanges:
                self.pendingChanges.remove(event['node'])
        except:
            self.log.warn('Error processing Node Change: %s' % event,exc_info=True)
        
    
    # --------------------------------------------------------------------------    
      
class insteonSetter():
    
    def __init__(self, log, dataset=None):
        self.dataset=dataset
        self.insteonAddress=self.dataset.config['address']
        self.port=self.dataset.config['port']
        self.username=self.dataset.config['user']
        self.password=self.dataset.config['password']
        self.log=log
        self.basicauth="Basic %s" % base64.encodebytes(("%s:%s" % (self.username,self.password)).encode('utf-8')).decode()


    @asyncio.coroutine
    def insteonRestCommand(self, client, url):
        
        try:
            headers = { "Authorization": self.basicauth }
            data = yield from client.get(url, headers=headers)
            html = yield from data.read() 
            return html
        except:
            self.log.error("insteonRestCommand failed: %s" % url,exc_info=True)


    async def setNode(self, node, data):
        
        try:
            self.log.info('.. Setting node: %s %s' % (node, data))
            if node not in self.dataset.nativeDevices['node']:
                for alight in self.dataset.nativeDevices['node']:
                    if self.dataset.nativeDevices['node'][alight]['name']==node:
                        node=alight
                        break
                
            for nodeattrib in data:
                if nodeattrib.upper() in ['DON','DOF','DFON', 'DFOF']:
                    url="http://%s/rest/nodes/%s/%s/%s" % (self.insteonAddress, node, "cmd", nodeattrib)
                elif nodeattrib.upper()=='ST':
                    if int(data[nodeattrib])==0:
                        control='DOF'
                    else:
                        control='DON'
                    url="http://%s/rest/nodes/%s/%s/%s/%s" % (self.insteonAddress, node, "cmd", control, data[nodeattrib])
                else:
                    url="http://%s/rest/nodes/%s/%s/%s/%s" % (self.insteonAddress, node, "set", nodeattrib.upper(), data[nodeattrib])
                
                #self.log.info('Using url: %s' % url)
                async with aiohttp.ClientSession() as client:
                    html = await self.insteonRestCommand(client, url)
                    root=et.fromstring(html)
                    return html
        except:
            self.log.error('Insteon setNode error: %s %s' % (node, data), exc_info=True)


    async def setGroup(self, group, data):
        
        try:
            self.log.info('Setting Group: %s %s' % (group, data))
            if group not in self.dataset.nativeDevices['group']:
                for agroup in self.dataset.nativeDevices['group']:
                    if self.dataset.nativeDevices['group'][agroup]['name']==group:
                        group=agroup
                        break
                
            for groupattrib in data:
                if groupattrib.upper()=='ST':
                    if int(data[groupattrib])==0:
                        control='DOF'
                    else:
                        control='DON'
                    url="http://%s/rest/nodes/%s/%s/%s/%s" % (self.insteonAddress, group, "cmd", control, data[groupattrib])
                else:
                    url="http://%s/rest/nodes/%s/%s/%s/%s" % (self.insteonAddress, group, "set", groupattrib.upper(), data[groupattrib])
                
                self.log.info('Using url: %s' % url)
                async with aiohttp.ClientSession() as client:
                    html = await self.insteonRestCommand(client, url)
                    root=et.fromstring(html)
                    return root
        except:
            self.log.error('Insteon setNode error: %s %s' % (group, data), exc_info=True)


        
class insteon(sofabase):

    class adapterProcess():
    
        def __init__(self, log=None, dataset=None, notify=None, request=None, loop=None, **kwargs):
            self.dataset=dataset
            self.insteonAddress='lights.dayton.home'
            self.log=log
            self.definitions=definitions.Definitions
            self.notify=notify
            self.insteonNodes=insteonCatalog(self.log, self.dataset)
            self.setInsteon=insteonSetter(self.log, dataset=self.dataset)
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            
            
        async def start(self):
            
            self.log.info('Starting Insteon')
            try:
                self.insteonNodes.data=self.dataset.nativeDevices
                self.setInsteon.data=self.dataset.nativeDevices
                await self.insteonNodes.authenticate()
                await self.insteonNodes.main()
                self.log.info('----')
                
                self.subscription = insteonSubscription(self.loop, self.log, self.notify, self.dataset)
                await self.loop.create_connection(lambda: self.subscription, self.insteonAddress, 80)
            except:
                self.log.error('Error', exc_info=True)

            
        async def command(self, category, item, data):
            
            self.log.info('Received insteon command: %s %s %s' % (category, item, data))
            
            if category=='node':
                await self.setInsteon.setNode(item, data)

            elif category=='group':
                await self.setInsteon.setGroup(item, data)


        def percentage(self, percent, whole):
            return int((percent * whole) / 100.0)


        async def addSmartDevice(self, path):
            
            # All Insteon Smart Devices will be nodes
            if path.split("/")[1]!='node':
                return False
            
            deviceid=path.split("/")[2]    
            nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(path))
            if nativeObject['name'] not in self.dataset.devices:
                if nativeObject["devicetype"]=="light":
                    if nativeObject["property"]["ST"]["uom"].find("%")>-1:
                        return self.dataset.addDevice(nativeObject['name'], devices.dimmableLight('insteon/node/%s' % deviceid, nativeObject['name']))
                    else:
                        return self.dataset.addDevice(nativeObject['name'], devices.simpleLight('insteon/node/%s' % deviceid, nativeObject['name']))
                elif nativeObject["devicetype"]=="thermostat":
                    if nativeObject['pnode']==deviceid:
                        return self.dataset.addDevice(nativeObject['name'], devices.smartThermostat('insteon/node/%s' % deviceid, nativeObject['name'], supportedModes=["HEAT", "FAN", "OFF"] ))
            
            return False


        async def stateChange(self, device, controller, command, payload):
            
            try:
                nativeCommand={}
                
                if controller=="PowerController":
                    if command=='TurnOn':
                        nativeCommand['DON']=100
                    elif command=='TurnOff':
                        nativeCommand['DOF']=0
                elif controller=="BrightnessController":
                    if command=="SetBrightness":
                        nativeCommand['ST']=self.percentage(int(payload['brightness']), 255)
                elif controller=="ThermostatController":
                    if command=="SetTargetTemperature":
                        nativeCommand['CLISPH']=int(payload['targetSetPoint'])*2
                    if command=="SetThermostatMode":
                        if payload['thermostatMode']=='OFF':
                            nativeCommand['CLIMD']='0'
                            nativeCommand['CLIFS']='0'
                        elif payload['thermostatMode']=='HEAT':
                            nativeCommand['CLIMD']='1'
                        elif payload['thermostatMode']=='COOL':
                            nativeCommand['CLIMD']='2'
                        elif payload['thermostatMode']=='AUTO':
                            nativeCommand['CLIMD']='3'
                        elif payload['thermostatMode']=='FAN':
                            nativeCommand['CLIMD']='4'
                        elif payload['thermostatMode']=='PROGRAM HEAT':
                            nativeCommand['CLIMD']='5'
                        elif payload['thermostatMode']=='PROGRAM COOL':
                            nativeCommand['CLIMD']='6'
                        elif payload['thermostatMode']=='PROGRAM AUTO':
                            nativeCommand['CLIMD']='7'


                if nativeCommand:
                    await self.setInsteon.setNode(device, nativeCommand)
                    if device not in self.subscription.pendingChanges:
                        self.subscription.pendingChanges.append(device)
                    await self.waitPendingChange(device)
                    updatedProperties=await self.insteonNodes.getNodeProperties(device)
                    self.log.info('UpdatedProperties: %s' % updatedProperties)
                    changeReport=await self.dataset.ingest({'node': { device: {'property':updatedProperties}}})
                    self.log.info('Changereport: %s' % changeReport)
                    return changeReport
                else:
                    self.log.info('Could not find a command for: %s %s %s %s' % (device, controller, command, payload) )
                    
            except:
                self.log.error('Error executing state change.', exc_info=True)
                
        async def waitPendingChange(self, device):
        
            # The ISY will send an update to the properties, but it takes .5-1 second to complete
            # Waitiing up to 2 seconds allows us to send back a change report for the change command
            count=0
            while device in self.subscription.pendingChanges and count<30:
                #self.log.info('Waiting for update... %s %s' % (device, self.subscription.pendingChanges))
                await asyncio.sleep(.1)
                count=count+1
            return True
                
                

        async def virtualCategory(self, category):
            
            if category in ['light','button','device']:
                subset={key: value for (key,value) in self.dataset.nativeDevices['node'].items() if value['devicetype']==category}

            elif category=='discovery':
                subset=[]
                devlist={key: value for (key,value) in self.dataset.nativeDevices['node'].items() if value['devicetype']=='light'}
                for item in devlist:
                    if self.dataset.nativeDevices['node'][item]["property"]["ST"]["uom"].find("%")>-1:
                        subset.append(self.dataset.discoveryEndpoint('/node/%s' % item, ['PowerController', 'BrightnessController'], ['LIGHT']))
                    else:
                        subset.append(self.dataset.discoveryEndpoint('/node/%s' % item, ['PowerController'], ['LIGHT']))
                        
                
            elif category=='endpoint':
                subset={key: value for (key,value) in self.dataset.nativeDevices['node'].items() if value['devicetype']=='light'}
                for item in subset:
                    subset[item]=self.dataset.mapProperties(subset[item], ['PowerController','BrightnessController'])
            else:
                subset={}
            
            return subset


        def virtualControllers(self, itempath):
            
            try:
                itempart=itempath.split("/",3)
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                try:
                    detail=itempath.split("/",3)[3]
                except:
                    detail=""
                    
                controllerlist={}
                if nativeObject["devicetype"]=="light":
                    if detail=="property/ST/value" or detail=="":
                        controllerlist["PowerController"]=["powerState"]
                        if nativeObject["property"]["ST"]["uom"].find("%")>-1:
                            controllerlist["BrightnessController"]=["brightness"]
                
                elif nativeObject["devicetype"]=="thermostat":
                    if detail=="property/ST/value" or detail=="":
                        controllerlist["TemperatureSensor"]=["temperature"]

                    if detail=="property/CLISPH/value" or detail=="":
                        controllerlist["ThermostatController"]=["targetSetPoint","thermostatMode"]
                    
                    if detail=="property/CLIMD/value" or detail=="":
                        controllerlist["ThermostatController"]=["targetSetPoint","thermostatMode"]
                        
                return controllerlist
            except KeyError:
                self.log.info('Key Error: %s' % itempath, exc_info=True)

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)

        
        def virtualControllerProperty(self, nativeObj, controllerProp):
            
            try:
                if controllerProp=='brightness':
                    # sometimes switches have their ST value set to space instead of a number (shrug)
                    if nativeObj['property']['ST']['value']==' ':
                        try:
                            return int((float(nativeObj['property']['OL']['value'])/254)*100)
                        except:
                            return 0
                            
                    # Return the on-level brightness if the device is off and it is available, similar to Hue lights
                    if int((float(nativeObj['property']['ST']['value'])/254)*100)==0:
                        try:
                            return int((float(nativeObj['property']['OL']['value'])/254)*100)
                        except:
                            pass
                    
                    return int((float(nativeObj['property']['ST']['value'])/254)*100)
                    
                elif controllerProp=='powerState':
                    if nativeObj['property']['ST']['value']==' ':
                        return "OFF"
                    return "ON" if int((float(nativeObj['property']['ST']['value'])/254)*100)>0 else "OFF"


                elif controllerProp=='temperature':
                    if nativeObj['property']['ST']['value']==' ':
                        return {}
                    return int(float(nativeObj['property']['ST']['value'])/2)
                
                elif controllerProp=='targetSetPoint':
                    if nativeObj['property']['CLISPH']['value']==' ':
                        return {}
                    return int(float(nativeObj['property']['CLISPH']['value'])/2)
                
                elif controllerProp=='thermostatMode':
                    if nativeObj['property']['CLIMD']['formatted']==' ':
                        return "OFF"
                    return nativeObj['property']['CLIMD']['formatted'].upper()

                else:
                    self.log.info('Unknown controller property mapping: %s' % controllerProp)
                    return {}
            except:
                self.log.error('Error converting virtual controller property: %s %s' % (controllerProp, nativeObj), exc_info=True)


if __name__ == '__main__':
    adapter=insteon(port=8083, adaptername="insteon", isAsync=True)
    adapter.start()
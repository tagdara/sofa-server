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
import gmqtt
import os

from gmqtt import Client as MQTTClient

class sofaMQTT():

    # The Sofa MQTT Handler provides an process for pushing updates to MQTT
        
    def __init__(self, adaptername, restPort, restAddress, dataset={}, log=None):
        self.backlog=[]
        self.connected=False
        if log:
            self.log=log
        else:
            self.log = logging.getLogger('sofamqtt')

        self.client = MQTTClient('sofa-%s-%s' % (adaptername,os.getpid()))
        self.dataset=dataset
        self.adaptername=adaptername
        self.restPort=restPort
        self.restAddress=restAddress
        self.dataset.mqtt={'connected':False, 'lastmessage':'', 'lasttime':'never', 'backlog':len(self.backlog)}
        self.log.info('.. MQTT Module initialized')
        self.pendingRequests=[]
        self.adapter_channels=[]
        self.pendingResponses={}
        
    def jsonDateHandler(self, obj):

        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        else:
            self.log.error('Found unknown object for json dump: (%s) %s' % (type(obj),obj))
            return None
            
    async def connectServer(self):
        try:
            self.client.on_message = self.on_message
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.log.info('.. mqtt connecting: %s' % self.dataset.baseConfig['mqttBroker'] )
            await self.client.connect(self.dataset.baseConfig['mqttBroker'], 1883, version=gmqtt.constants.MQTTv311)
        except:
            self.log.error('Error connecting to MQTT broker: %s' % self.dataset.baseConfig['mqttBroker'])
            self.connected=False
            self.dataset.mqtt['connected']=False
            return False
        
        backlogresult=self.sendBacklog()
     
     
    def sendBacklog(self):
        try:
            if self.connected:
                for item in self.backlog:
                    self.log.info('Pushing from backlog: %s' % item)
                    self.notify(item['topic'], item['message'])
                return True
            else:
                return False
        except:
            self.log.error('Error sending backlog to MQTT', exc_info=True)
            return False

        
    def on_connect(self, client, flags, rc, properties):
        self.log.info('+. mqtt server connected %s' % self.dataset.baseConfig['mqttBroker'] )
        self.connected=True
        self.dataset.mqtt['connected']=True
        self.topicSubscribe()
        self.subscribeAdapterTopics()
        backlogresult=self.sendBacklog()

    def on_disconnect(self, client, packet, exc=None):
        try:
            if self.client._reconnect:
                self.log.info('-- mqtt server disconnected %s.  Will retry to connect ' % self.dataset.baseConfig['mqttBroker'])
            else:
                self.log.info('-- mqtt server disconnected %s.  Will not retry to connect' % self.dataset.baseConfig['mqttBroker'] )
        except:
            self.log.error('Error server disconnected from client: %s' % client, exc_info=True)
        
    def on_message(self, client, topic, payload, qos, properties):
        try:
            try:
                message=json.loads(payload.decode())
                # Look for correlation tokens in all channels
                if 'event' in message:
                    if 'correlationToken' in message['event']['header']:
                        if message['event']['header']['correlationToken'] in self.pendingRequests:
                            self.pendingResponses[message['event']['header']['correlationToken']]=message
                            self.pendingRequests.remove(message['event']['header']['correlationToken'])
                            return True
                            
            except json.decoder.JSONDecodeError:
                self.log.warn('JSON decode error', exc_info=True)
                pass

            if hasattr(self.adapter, "adapterTopics"):
                if topic in self.adapter.adapterTopics:
                    if hasattr(self.adapter, "processAdapterTopicMessage"):
                        asyncio.tasks.ensure_future(self.adapter.processAdapterTopicMessage(topic, payload.decode()))
                        return True
                        
            self.log.debug('<< mqtt/%s %s' % (topic, payload.decode()))
            asyncio.tasks.ensure_future(self.processSofaMessage(topic, json.loads(payload.decode())))
        except:
            self.log.error('Error handling message',exc_info=True)

    async def disconnectTopics(self):

        try:
            self.log.info(".! Error count: %s.  mqtt/%s now unsubscribed" % (mqttErrors,topic))
            await self.client.disconnect()
        except: 
            self.log.error('.! Error disconnecting from MQTT', exc_info=True)

    def topicSubscribe(self):
    
        topics=['sofa','sofa/updates','sofa/changes']

        try:
            for topic in topics:
                self.client.subscribe(topic, qos=1)

            self.log.info(".. mqtt subscribed topics: %s" % topics)
            self.announceRest('sofa')
            self.notify('sofa','{"op":"discover"}')
        except ClientException as ce:
            self.log.error("!! mqtt client exception: %s" % ce)


    def subscribeAdapterTopics(self):
    
        try:
            if hasattr(self.adapter, "adapterTopics"):

                for topic in self.adapter.adapterTopics:
                    self.client.subscribe(topic, qos=1)

                self.log.info(".. mqtt subscribed adapter topics: %s" % self.adapter.adapterTopics)

        except ClientException as ce:
            self.log.error("!! mqtt client adapter topic exception: %s" % ce)
    
    
    def notify(self, topic, message):
        
        try:
            self.log.debug(">> mqtt/%s %s" % (topic, message))
            if self.connected:
                self.client.publish(topic, message)
            else:
                self.log.info('!! MQTT not ready to publish message, adding to backlog: %s %s' % (topic,message))
                self.backlog.append({'topic':topic, 'message':message})
        except:
            self.log.error('!! Error publishing message, adding to backlog', exc_info=True)
            self.backlog.append({'topic':topic, 'message':message})

      
    async def notifyChanges(self, topic, changes):
            
        try:
            if self.connected:
                for item in changes:
                    self.log.debug(">> mqtt/sofa/changes %s" % item)
                    item['path']="%s%s" % (self.adaptername, item['path'])
                    self.client.publish('sofa/changes', json.dumps(item))
            else:
                self.log.info('.! MQTT not ready to publish message: sofa/changes %s' % changes)

        except:
            self.log.error('!! Error sending sofa/changes', exc_info=True)
                

    def announceRest(self, topic):
            
        try:
            discoveryResponse={"op":"announce", "adapter":self.adaptername, "address":self.restAddress, "port":self.restPort, "startup":self.dataset.startupTime}
            self.notify(topic,json.dumps(discoveryResponse, default=self.jsonDateHandler))
        except:
            self.log.error('!! Error processing MQTT Message', exc_info=True)

    async def discover(self, topic):
            
        try:
            self.log.info('.. sending discovery request on MQTT Topic %s' % topic)
            discoveryResponse={"op":"discover", "adapter":self.adaptername, "address":self.restAddress, "port":self.restPort}
            self.notify(topic,json.dumps(discoveryResponse))
        except:
            self.log.error('!! Error processing MQTT Message', exc_info=True)
            
            
    async def requestReply(self, request, correlationToken, timeout=2, topic='sofa'):
        try:
            self.pendingRequests.append(correlationToken)
            self.notify(topic,request)
            count=0
            while correlationToken not in self.pendingResponses and count<30:
                #self.log.info('Waiting for update...topic:%s -  %s %s' % (topic, correlationToken, self.pendingResponses))
                await asyncio.sleep(.1)
                count=count+1
                
            if correlationToken in self.pendingResponses:
                result=dict(self.pendingResponses[correlationToken])
                del self.pendingResponses[correlationToken]
                return result
            else:
                self.log.info('Timeout on response for request %s' % correlationToken)
                return {}
        
        except:
            self.log.error('Error with request and reply',exc_info=True)
            return {}

 

    async def processSofaMessage(self, topic, message):
            
        try:
  
            if 'op' in message:
                if message['op']=='discover':
                    #self.log.info('Adapter requesting discovery')
                    self.announceRest(topic)
                elif message['op']=='announce':
                    #self.log.info('Adapter Announcement: %s' % message)
                    await self.dataset.register({message['adapter'] : { 'startup': message['startup'], 'address':message['address'], 'port':message['port'], "url": "http://%s:%s" % (message['address'],message['port'])}})

            elif 'event' in message:
            
                if 'correlationToken' in message['event']['header']:
                    try:
                        if message['event']['header']['correlationToken'] in self.pendingRequests:
                            self.pendingResponses[message['event']['header']['correlationToken']]=message
                            self.pendingRequests.remove(message['event']['header']['correlationToken'])
                    except:
                        self.log.error('Error handling a correlation token response: %s ' % message, exc_info=True)


                elif message['event']['header']['name']=='DoorbellPress':
                    if message['event']['endpoint']['endpointId'].split(":")[0]!=self.adaptername:
                        if hasattr(self.adapter, "handleAlexaEvent"):
                            await self.adapter.handleAlexaEvent(message)
            
                elif message['event']['header']['name']=='StateReport':
                    if message['event']['endpoint']['endpointId'].split(":")[0]!=self.adaptername:
                        if hasattr(self.adapter, "handleStateReport"):
                            await self.adapter.handleStateReport(message)

                elif message['event']['header']['name']=='ChangeReport':
                    if message['event']['endpoint']['endpointId'].split(":")[0]!=self.adaptername:
                        if hasattr(self.adapter, "handleChangeReport"):
                            await self.adapter.handleChangeReport(message)

                elif message['event']['header']['name']=='DeleteReport':
                    if hasattr(self.adapter, "handleDeleteReport"):
                        await self.adapter.handleDeleteReport(message)

                
                elif message['event']['header']['name']=='AddOrUpdateReport':
                    if hasattr(self.adapter, "handleAddOrUpdateReport"):
                        await self.adapter.handleAddOrUpdateReport(message)
                        #await self.adapter.handleAddOrUpdateReport(message['event']['payload']['endpoints'])
                
                else:
                    self.log.info('Message type not processed: %s' % message)
                    
            self.dataset.mqtt['lastmessage']="%s/%s" % (topic, message)
            self.dataset.mqtt['lasttime']=datetime.datetime.now()
                
        except:
            self.log.error('Error processing MQTT Message', exc_info=True)


    

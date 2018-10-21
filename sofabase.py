import asyncio
import aiohttp
from aiohttp import web
import concurrent.futures
import os
import logging
from logging.handlers import RotatingFileHandler
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
import sofamqtt
import sofadataset
import sofarest
import sofarequester


class adapterbase():
        
    def jsonDateHandler(self, obj):

        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        else:
            self.log.error('Found unknown object for json dump: (%s) %s' % (type(obj),obj))
            return None
 
 
    def loadJSON(self, jsonfilename):
        
        try:
            with open(jsonfilename,'r') as jsonfile:
                return json.loads(jsonfile.read())
        except:
            self.log.error('Error loading pattern: %s' % jsonfilename,exc_info=True)
            return {}


    def saveJSON(self, jsonfilename, data):
        
        try:
            jsonfile = open(jsonfilename, 'wt')
            json.dump(data, jsonfile, ensure_ascii=False, default=self.jsonDateHandler)
            jsonfile.close()
        except:
            self.log.error('Error saving json to %s' % jsonfilename, exc_info=True)
            
class sofabase():

    class adapterProcess():
        
        # AdapterProcess should be implemented independently by each adapter
    
        def __init__(self, log):
            pass
        
        def get(self):
            pass


    def logsetup(self, level="INFO", errorOnly=[]):
        
        log_formatter = logging.Formatter('%(asctime)-6s.%(msecs).03d %(levelname).1s %(lineno)4d %(threadName)-.1s: %(message)s','%m/%d %H:%M:%S')
        if not os.path.exists("%s/log/%s" % (self.basepath, self.adaptername)):
            os.makedirs("%s/log/%s" % (self.basepath, self.adaptername))
        #check if a log file already exists and if so rotate it
        needRoll = os.path.isfile("%s/log/%s/%s.log" % (self.basepath, self.adaptername, self.adaptername))
        logFile = "%s/log/%s/%s.log" % (self.basepath, self.adaptername, self.adaptername)
        log_handler = RotatingFileHandler(logFile, mode='a', maxBytes=1024*1024, backupCount=5)
        log_handler.setFormatter(log_formatter)
        log_handler.setLevel(getattr(logging,level))
        if needRoll:
            log_handler.doRollover()
            
        console = logging.StreamHandler()
        console.setFormatter(log_handler)
        console.setLevel(logging.INFO)
        
        logging.getLogger(self.adaptername).addHandler(console)

        self.log =  logging.getLogger(self.adaptername)
        self.log.setLevel(logging.INFO)
        self.log.addHandler(log_handler)
        if not os.path.exists("%s/log/%s.log" % (self.basepath, self.adaptername)):
            os.symlink("%s/log/%s/%s.log" % (self.basepath, self.adaptername, self.adaptername), "%s/log/%s.log" % (self.basepath, self.adaptername))
        
        self.log.info('-- -----------------------------------------------')
        
        for lg in logging.Logger.manager.loggerDict:
            #self.log.info('.. Active logger: %s' % lg)
            for item in errorOnly:
                if lg.startswith(item):
                    self.log.debug('.. Logger set to error and above: %s' % lg)
                    logging.getLogger(lg).setLevel(logging.ERROR)


            
    def oldlogsetup(self, level="INFO", errorOnly=[]):
        
        loglevel=getattr(logging,level)
        logging.basicConfig(level=loglevel, format='%(asctime)-6s.%(msecs).03d %(levelname).1s %(lineno)4d %(threadName)-.1s: %(message)s',datefmt='%m/%d %H:%M:%S', filename='/opt/beta/log/%s.log' % self.adaptername,)
        self.log = logging.getLogger(self.adaptername)
        
        formatter = logging.Formatter('%(asctime)-6s.%(msecs).03d %(levelname).1s %(lineno)4d %(threadName)-.1s: %(message)s',datefmt='%m/%d %H:%M:%S')
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(logging.INFO)

        self.log.info('-- -----------------------------------------------')

        logging.getLogger(self.adaptername).addHandler(console)
        
        for lg in logging.Logger.manager.loggerDict:
            #self.log.info('.. Active logger: %s' % lg)
            for item in errorOnly:
                if lg.startswith(item):
                    self.log.info('.. Logger set to error and above: %s' % lg)
                    logging.getLogger(lg).setLevel(logging.ERROR)

        
    def readconfig(self):

        try:
            with open('/opt/beta/config/%s.json' % (self.adaptername),'r') as configfile:
                return json.loads(configfile.read())
        except FileNotFoundError:
            self.log.error('.! Config file was not found for: %s' % self.adaptername)
            return {}
        except:
            self.log.error('Did not load config: %s' % self.adaptername, exc_info=True)
            return {}

    def saveConfig(self):

        try:
            self.log.info('data: %s' % self.dataset.config)
            with open('/opt/beta/config/%s.json' % (self.adaptername),'w') as configfile:
                configfile.write(json.dumps(self.dataset.config))

        except:
            self.log.debug('Did not save config: %s' % self.adaptername, exc_info=True)

    def readBaseConfig(self):

        try:
            with open('/opt/beta/config/sofabase.json','r') as configfile:
                return json.loads(configfile.read())
        except:
            self.log.debug('Did not load base config', exc_info=True)
            return {}
       

    def __init__(self, port=8081, adaptername='sofa', isAsync=False, loglevel="INFO"):
        
        self.adaptername=adaptername
        self.basepath="/opt/beta"
        self.logsetup(loglevel,errorOnly=['aiohttp.access','gmqtt.mqtt.protocol','gmqtt.mqtt.handler','gmqtt.mqtt.package'])

        self.loop = asyncio.get_event_loop()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=3,)
        self.restPort=port
        self.isAsync=isAsync
        
        
    def start(self):
        self.log.info('.. Sofa 2 Adapter module initialized and starting.')

        asyncio.set_event_loop(self.loop)
        
        self.dataset=sofadataset.sofaDataset(self.log, adaptername=self.adaptername, loop=self.loop)
        self.dataset.baseConfig=self.readBaseConfig()
        self.dataset.config=self.readconfig()
        self.dataset.saveConfig=self.saveConfig
        
        self.requester=sofarequester.sofaRequester()
        self.requester.data=self.dataset.data
        
        self.log.info('.. starting MQTT client')
        self.restAddress = self.dataset.baseConfig['restAddress']
        #self.mqttServer = self.sofaMQTT(self.adaptername, self.restPort, self.restAddress, dataset=self.dataset )
        self.mqttServer = sofamqtt.sofaMQTT(self.adaptername, self.restPort, self.restAddress, dataset=self.dataset)

        
        self.dataset.notify=self.mqttServer.notify
        self.dataset.notifyChanges=self.mqttServer.notifyChanges
        self.dataset.mqttRequestReply=self.mqttServer.requestReply
        
        self.log.info('.. starting REST server on port %s' % self.restPort)
        self.restServer = sofarest.sofaRest(port=self.restPort, loop=self.loop, log=self.log, dataset=self.dataset)
        self.restServer.initialize()

        self.log.info('.. starting main adapter %s' % self.adaptername)
        self.adapter=self.adapterProcess(log=self.log, dataset=self.dataset, notify=self.mqttServer.notify, discover=self.mqttServer.discover, request=self.requester.request, loop=self.loop)
        self.dataset.adapter=self.adapter
        self.mqttServer.adapter=self.adapter
        self.restServer.adapter=self.adapter
    
        # wait until the adapter is created to avoid a number of race conditions
        self.loop.run_until_complete(self.mqttServer.connectServer())
        self.loop.run_until_complete(self.mqttServer.topicSubscribe())
        self.loop.run_until_complete(self.mqttServer.subscribeAdapterTopics())
        
        if self.isAsync:
            self.adapter.running=True
            self.loop.run_until_complete(self.adapter.start())
            #asyncio.ensure_future(self.adapter.start())
        else:
            self.workload = asyncio.ensure_future(self.loop.run_in_executor(self.executor,self.adapter.start,))
    
        self.restServer.adapter=self.adapter
        self.restServer.workloadData=self.adapter.dataset.data
        
        try:
            self.loop.run_forever()
        except KeyboardInterrupt:  # pragma: no cover
            pass
        except:
            self.log.error('Loop terminated', exc_info=True)
        finally:
            self.adapter.running=False
            self.restServer.shutdown()
            self.executor.shutdown()
        
        self.log.info('.. stopping adapter %s' % self.adaptername)
        self.loop.close()


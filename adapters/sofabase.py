import os
import sys
import logging
import asyncio
import aiohttp
from aiohttp import web
import concurrent.futures
from logging.handlers import RotatingFileHandler
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
            with open(os.path.join(self.dataset.baseConfig['configDirectory'], '%s.json' % jsonfilename),'r') as jsonfile:
                return json.loads(jsonfile.read())
        except:
            self.log.error('Error loading pattern: %s' % jsonfilename,exc_info=True)
            return {}


    def saveJSON(self, jsonfilename, data):
        
        try:
            jsonfile = open(os.path.join(self.dataset.baseConfig['configDirectory'], '%s.json' % jsonfilename), 'wt')
            json.dump(data, jsonfile, ensure_ascii=False, default=self.jsonDateHandler)
            jsonfile.close()
        except:
            self.log.error('Error saving json to %s' % jsonfilename, exc_info=True)
    
    def addControllerProps(self, controllerlist, controller, prop):
        
        try:
            if controller not in controllerlist:
                controllerlist[controller]=[]
            if prop not in controllerlist[controller]:
                controllerlist[controller].append(prop)
        except:
            self.log.error('Error adding controller property', exc_info=True)
                
        return controllerlist
            
class sofabase():

    class adapterProcess():
        
        # AdapterProcess should be implemented independently by each adapter
    
        def __init__(self, log):
            pass
        
        def get(self):
            pass


    def logsetup(self, logbasepath, logname, level="INFO", errorOnly=[]):

        #log_formatter = logging.Formatter('%(asctime)-6s.%(msecs).03d %(levelname).1s %(lineno)4d %(threadName)-.1s: %(message)s','%m/%d %H:%M:%S')
        log_formatter = logging.Formatter('%(asctime)-6s.%(msecs).03d %(levelname).1s%(lineno)4d: %(message)s','%m/%d %H:%M:%S')
        logpath=os.path.join(logbasepath, logname)
        logfile=os.path.join(logpath,"%s.log" % logname)
        loglink=os.path.join(logbasepath,"%s.log" % logname)
        if not os.path.exists(logpath):
            os.makedirs(logpath)
        #check if a log file already exists and if so rotate it

        needRoll = os.path.isfile(logfile)
        log_handler = RotatingFileHandler(logfile, mode='a', maxBytes=1024*1024, backupCount=5)
        log_handler.setFormatter(log_formatter)
        log_handler.setLevel(getattr(logging,level))
        if needRoll:
            log_handler.doRollover()
            
        console = logging.StreamHandler()
        console.setFormatter(log_handler)
        console.setLevel(logging.INFO)
        
        logging.getLogger(logname).addHandler(console)

        self.log =  logging.getLogger(logname)
        self.log.setLevel(logging.INFO)
        self.log.addHandler(log_handler)
        if not os.path.exists(loglink):
            os.symlink(logfile, loglink)
        
        self.log.info('-- -----------------------------------------------')
        
        for lg in logging.Logger.manager.loggerDict:
            #self.log.info('.. Active logger: %s' % lg)
            for item in errorOnly:
                if lg.startswith(item):
                    self.log.debug('.. Logger set to error and above: %s' % lg)
                    logging.getLogger(lg).setLevel(logging.ERROR)

  
    def readconfig(self):

        try:
            with open(os.path.join(self.baseConfig["configDirectory"], "%s.json" % (self.adaptername)), "r") as configfile:
                configdata=configfile.read()
                return json.loads(configdata)
        except FileNotFoundError:
            self.log.error('.! Config file was not found for: %s' % self.adaptername)
            sys.exit(1)
        except:
            self.log.error('Did not load config: %s' % self.adaptername, exc_info=True)
            sys.exit(1)

    def saveConfig(self):

        try:
            with open(os.path.join(self.baseConfig["configDirectory"], "%s.json" % (self.adaptername)), "w") as configfile:
                configfile.write(json.dumps(self.dataset.config))
            return True

        except:
            self.log.error('Did not save config: %s' % self.adaptername, exc_info=True)
            return False

    def readBaseConfig(self, configpath):

        try:
            baseconfig={}
            configdir=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config'))
            with open(os.path.join(configdir, 'sofabase.json'), "r") as configfile:
                baseconfig=json.loads(configfile.read())
        except:
            print('Did not load base config')
            
        try:
            if 'configDirectory' not in baseconfig:
                baseconfig['configDirectory']=configdir
            if 'baseDirectory' not in baseconfig:
                baseconfig['baseDirectory']=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
            if 'logDirectory' not in baseconfig:
                baseconfig['logDirectory']=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'log'))
            if 'mqttBroker' not in baseconfig:
                baseconfig['mqttBroker']='localhost'
            if 'restAddress' not in baseconfig:
                baseconfig['restAddress']='localhost'

            return baseconfig
        except:
            print('Did not get base config properly')
            sys.exit(1)
       
       
    def __init__(self, name=None, loglevel="INFO"):
        
        if name==None:
            print('Adapter name not provided')
            sys.exit(1)
            
        self.adaptername=name
        self.configpath=".."
        self.baseConfig=self.readBaseConfig(self.configpath)
        self.basepath=self.baseConfig['baseDirectory']
        self.logsetup(self.baseConfig['logDirectory'], self.adaptername, loglevel, errorOnly=['aiohttp.access','gmqtt.mqtt.protocol','gmqtt.mqtt.handler','gmqtt.mqtt.package'])
        self.loop = asyncio.get_event_loop()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=3,)
        
        
    def start(self):
        self.log.info('.. Sofa 2 Adapter module initialized and starting.')
        asyncio.set_event_loop(self.loop)
        self.dataset=sofadataset.sofaDataset(self.log, adaptername=self.adaptername, loop=self.loop)
        #self.dataset.baseConfig=self.readBaseConfig()
        self.dataset.baseConfig=self.baseConfig
        self.dataset.config=self.readconfig()
        self.dataset.saveConfig=self.saveConfig
        
        self.requester=sofarequester.sofaRequester()
        
        self.log.info('.. starting MQTT client')
        self.restAddress = self.dataset.baseConfig['restAddress']
        self.restPort=self.dataset.config['rest_port']
        
        self.mqttServer = sofamqtt.sofaMQTT(self.adaptername, self.restPort, self.restAddress, dataset=self.dataset, log=self.log)

        self.dataset.notify=self.mqttServer.notify
        self.dataset.notifyChanges=self.mqttServer.notifyChanges
        self.dataset.mqttRequestReply=self.mqttServer.requestReply
        
        self.log.info('.. starting REST server on port %s' % self.dataset.config['rest_port'])
        self.restServer = sofarest.sofaRest(port=self.dataset.config['rest_port'], loop=self.loop, log=self.log, dataset=self.dataset)
        self.restServer.initialize()

        self.log.info('.. starting main adapter %s' % self.adaptername)
        self.adapter=self.adapterProcess(log=self.log, dataset=self.dataset, notify=self.mqttServer.notify, discover=self.mqttServer.discover, request=self.requester.request, loop=self.loop, executor=self.executor)
        self.dataset.adapter=self.adapter
        self.mqttServer.adapter=self.adapter
        self.restServer.adapter=self.adapter
    
        # wait until the adapter is created to avoid a number of race conditions
        self.loop.run_until_complete(self.mqttServer.connectServer())
        self.loop.run_until_complete(self.mqttServer.topicSubscribe())
        self.loop.run_until_complete(self.mqttServer.subscribeAdapterTopics())
        
        self.adapter.running=True
        self.loop.run_until_complete(self.adapter.start())

        self.restServer.adapter=self.adapter

        
        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            pass
        except:
            self.log.error('Loop terminated', exc_info=True)
        finally:
            self.adapter.running=False
            self.restServer.shutdown()
            self.log.info('Shutting down executor')
            self.executor.shutdown()
        
        self.log.info('.. stopping adapter %s' % self.adaptername)
        self.loop.close()


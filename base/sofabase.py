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
import signal

import sofamqtt
import sofadataset
import sofarest
import sofarequester

from logging import handlers

class DailyRotatingFileHandler(handlers.RotatingFileHandler):

    def __init__(self, alias, basedir, mode='a', maxBytes=0, backupCount=0, encoding=None, delay=0):
        """
        @summary: 
        Set self.baseFilename to date string of today.
        The handler create logFile named self.baseFilename
        """
        self.basedir_ = basedir
        self.alias_ = alias

        self.baseFilename = self.getBaseFilename()

        handlers.RotatingFileHandler.__init__(self, self.baseFilename, mode, maxBytes, backupCount, encoding, delay)

    def getBaseFilename(self):
        """
        @summary: Return logFile name string formatted to "today.log.alias"
        """
        self.today_ = datetime.date.today()
        basename_ = self.alias_+"."+self.today_.strftime("%Y-%m-%d") + ".log"
        return os.path.join(self.basedir_, basename_)

    def shouldRollover(self, record):
        """
        @summary: 
        Rollover happen 
        1. When the logFile size is get over maxBytes.
        2. When date is changed.

        @see: BaseRotatingHandler.emit
        """

        if self.stream is None:                
            self.stream = self._open()

        if self.maxBytes > 0 :                  
            msg = "%s\n" % self.format(record)
            self.stream.seek(0, 2)  
            if self.stream.tell() + len(msg) >= self.maxBytes:
                return 1

        if self.today_ != datetime.date.today():
            self.baseFilename = self.getBaseFilename()
            return 1

        return 0

class adapterbase():
    
    @property
    def collector(self):
        return False 
        
    @property
    def collector_categories(self):
        return []  
            
    async def stop(self):
        self.log.info('Stopping adapter')
        
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
        except FileNotFoundError:
            self.log.error('!! Error loading json - file does not exist: %s' % jsonfilename)
            return {}
        except:
            self.log.error('Error loading pattern: %s' % jsonfilename,exc_info=True)
            return {}
            
    def saveJSON(self, jsonfilename, data):
        
        try:
            jsonfile = open(os.path.join(self.dataset.baseConfig['configDirectory'], '%s.json' % jsonfilename), 'wt')
            json.dump(data, jsonfile, ensure_ascii=False, default=self.jsonDateHandler)
            jsonfile.close()

        except:
            self.log.error('Error saving json: %s' % jsonfilename,exc_info=True)
            return {}
            
    def load_cache(self, filename, json_format=True):
        
        try:
            if json_format:
                filename="%s.json" % filename
            with open(os.path.join(self.dataset.baseConfig['cacheDirectory'], filename),'r') as cachefile:
                if json_format:
                    return json.loads(cachefile.read())
                else:
                    return cachefile.read()
        except FileNotFoundError:
            self.log.error('!! Error loading cache - file does not exist: %s' % filename)
            return {}
        except:
            self.log.error('Error loading cache: %s' % filename,exc_info=True)
            return {}

    def save_cache(self, filename, data, json_format=True):
        
        try:
            if json_format:
                filename="%s.json" % filename
            cachefile = open(os.path.join(self.dataset.baseConfig['cacheDirectory'], filename), 'wt')
            if json_format:
                json.dump(data, cachefile, ensure_ascii=False, default=self.jsonDateHandler)
            else:
                cachefile.write(data)
            cachefile.close()
        except:
            self.log.error('Error saving cache to %s' % filename, exc_info=True)


    def addControllerProps(self, controllerlist, controller, prop):
        
        try:
            if controller not in controllerlist:
                controllerlist[controller]=[]
            if prop not in controllerlist[controller]:
                controllerlist[controller].append(prop)
        except:
            self.log.error('Error adding controller property', exc_info=True)
                
        return controllerlist



class MsgCounterHandler(logging.Handler):

    def __init__(self, *args, **kwargs):
        super(MsgCounterHandler, self).__init__(*args, **kwargs)
        self.logged_lines={'ERROR':0, 'INFO':0, 'WARNING':0, 'DEBUG':0}

    def emit(self, record):
        l = record.levelname
        if l in self.logged_lines:
            self.logged_lines[l]+=1
            
class sofabase():

    class adapterProcess():
        
        # AdapterProcess should be implemented independently by each adapter

        def __init__(self, log):
            pass
        
        def get(self):
            pass
        
        async def stop(self):
            self.log.info('Stopping adapter')

        def alexa_json_filter(self, data, namespace="", level=0):
            
            # this function allows for logging alexa smarthome API commands while reducing unnecessary fields
            
            try:
                out_data={}
                if 'directive' in data:
                    out_data['type']='Directive'
                    out_data['name']=data['directive']['header']['name']
                    out_data['namespace']=data['directive']['header']['namespace'].split('.')[1]
                    out_data['endpointId']=data['directive']['endpoint']['endpointId']
                    out_text="%s: %s/%s %s" % (out_data['type'], out_data['namespace'], out_data['name'], out_data['endpointId'])
                    
                elif 'event' in data:
                    # CHEESE: Alexa API formatting is weird with the placement of payload
                    out_data['type']='Event'
                    out_data['name']=data['event']['header']['name']
                    if data['event']['header']['name']=='ErrorResponse':
                        return "%s: %s %s" % (out_data['name'], out_data['endpointId'], data['event']['payload'])    
                    
                    if data['event']['header']['namespace'].endswith('Discovery'):
                        if 'payload' in data['event'] and 'endpoints' in data['event']['payload']:
                            out_data['endpointId']='['
                            for item in data['event']['payload']['endpoints']:
                                out_data['endpointId']+=item['endpointId']+" "
                        out_text="%s: %s" % (out_data['name'], out_data['endpointId'])    
                        return out_text
    
                    out_data['endpointId']=data['event']['endpoint']['endpointId']
                    out_text="%s: %s" % (out_data['name'], out_data['endpointId'])
    
                    if 'payload' in data['event'] and data['event']['payload']:
                        out_text+=" %s" % data['event']['payload']
                    elif 'payload' in data and data['payload']:
                        out_text+=" %s" % data['payload']
                        
                    if namespace:
                        out_text+=" %s:" % namespace
                        if 'context' in data and 'properties' in data['context']:
                            for prop in data['context']['properties']:
                                if prop['namespace'].endswith(namespace):
                                    out_text+=" %s : %s" % (prop['name'], prop['value'])
    
                else:
                    self.log.info('.. unknown response to filter: %s' % data)
                    return data
    
                return out_text
            except:
                self.log.error('Error parsing alexa json', exc_info=True)
                return data


    def __init__(self, name=None, loglevel="INFO"):
        
        if name==None:
            print('Adapter name not provided')
            sys.exit(1)
        
        
        self.adaptername=name
        self.configpath=".."
        self.baseConfig=self.readBaseConfig(self.configpath)
        self.basepath=self.baseConfig['baseDirectory']
        self.logsetup(self.baseConfig['logDirectory'], self.adaptername, loglevel, errorOnly=self.baseConfig['error_only_logs'])

        self.loop = asyncio.get_event_loop()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10,)


    def logsetup(self, logbasepath, logname, level="INFO", errorOnly=[]):

        #log_formatter = logging.Formatter('%(asctime)-6s.%(msecs).03d %(levelname).1s %(lineno)4d %(threadName)-.1s: %(message)s','%m/%d %H:%M:%S')

        #log_error_formatter = logging.Formatter('%(asctime)-6s.%(msecs).03d %(levelname).1s%(lineno)4d: %(message)s','%m/%d %H:%M:%S')
        log_formatter = logging.Formatter('%(asctime)-6s.%(msecs).03d %(filename).8s %(levelname).1s%(lineno)4d: %(message)s','%m/%d %H:%M:%S')
        logpath=os.path.join(logbasepath, logname)
        logfile=os.path.join(logpath,"%s.log" % logname)
        errorfile=os.path.join(logpath,"%s.err.log" % logname)
        loglink=os.path.join(logbasepath,"%s.log" % logname)
        if not os.path.exists(logpath):
            os.makedirs(logpath)
        #check if a log file already exists and if so rotate it
        
        #log_error_handler = logging.FileHandler(errorfile)
        log_error_handler = RotatingFileHandler(errorfile, mode='a', maxBytes=1024*1024, backupCount=5)

        log_error_handler.setFormatter(log_formatter)
        log_error_handler.setLevel(logging.WARNING)
        if os.path.isfile(logfile):
            log_error_handler.doRollover()
            
        log_handler = RotatingFileHandler(logfile, mode='a', maxBytes=1024*1024, backupCount=5)
        #log_handler = RotatingFileHandler(logname, logbasepath, mode='a', maxBytes=1024*1024, backupCount=5)

        log_handler.setFormatter(log_formatter)
        log_handler.setLevel(getattr(logging,level))
        if os.path.isfile(logfile):
            log_handler.doRollover()
            
        self.count_handler = MsgCounterHandler()
        
        #log_error = logging.FileHandler(os.path.join(logbasepath,"sofa-error.log"))
        #log_error.setFormatter(log_formatter)
        #log_error.setLevel(logging.WARNING)
        
        console = logging.StreamHandler()
        console.setFormatter(log_handler)
        console.setLevel(getattr(logging,level))
        
        logging.getLogger(logname).addHandler(console)
        #logging.getLogger(logname).addHandler(log_error)
        
        self.log =  logging.getLogger(logname)
        self.log.setLevel(getattr(logging,level))
        self.log.addHandler(log_handler)
        self.log.addHandler(log_error_handler)
        self.log.addHandler(self.count_handler)

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

    
    def service_stop(self, sig=None):
        try:
            self.log.info('Terminating loop due to service stop. %s' % sig)
            try:
                if self.adapter:
                    self.adapter.running=False
                    if hasattr(self.adapter, 'service_stop'):
                        self.adapter.service_stop()
                    #asyncio.ensure_future(self.adapter.stop())

                if self.restServer:
                    self.restServer.shutdown()
                if self.executor:
                    self.log.info('Shutting down executor')
                    self.executor.shutdown()
                    
                tasks = asyncio.all_tasks(self.loop)
                #expensive_tasks = {task for task in tasks if task._coro.__name__ != coro.__name__}
                self.loop.run_until_complete(asyncio.gather(*tasks))
                
            except:
                self.log.error('!! error in service stop', exc_info=True)
            self.loop.stop()
        except:
            self.log.error('Error stopping loop', exc_info=True)

        
    def start(self):
        self.log.info('.. Sofa 2 Adapter module initialized and starting')
        signal.signal(signal.SIGTERM, self.service_stop)
        asyncio.set_event_loop(self.loop)
        for signame in {'SIGINT', 'SIGTERM'}:
            self.loop.add_signal_handler(
                getattr(signal, signame),
                functools.partial(self.service_stop, signame))


        self.dataset=sofadataset.sofaDataset(self.log, adaptername=self.adaptername, loop=self.loop)
        self.dataset.logged_lines=self.count_handler.logged_lines
        #self.dataset.baseConfig=self.readBaseConfig()
        self.dataset.baseConfig=self.baseConfig
        self.dataset.config=self.readconfig()
        self.dataset.saveConfig=self.saveConfig
        
        if 'log_changes' in self.dataset.config and self.dataset.config['log_changes']==True:
            pass
        else:
            self.log.info('.. this adapter is not logging device changes')
        
        #self.requester=sofarequester.sofaRequester()
        
        self.restAddress = self.dataset.baseConfig['restAddress']
        self.restPort=self.dataset.config['rest_port']
        
        mqtt_deprecated=True
        if 'mqtt' in self.dataset.config and self.dataset.config['mqtt']==False:
            mqtt_deprecated=True
        
        if not mqtt_deprecated:
            self.log.info('.. starting MQTT client')
            self.mqttServer = sofamqtt.sofaMQTT(self.adaptername, self.restPort, self.restAddress, dataset=self.dataset, log=self.log, deprecated=mqtt_deprecated)

            self.dataset.notify=self.mqttServer.notify
            self.dataset.notifyChanges=self.mqttServer.notifyChanges
            self.dataset.mqttRequestReply=self.mqttServer.requestReply

        self.log.info('.. starting main adapter %s' % self.adaptername)
        if not mqtt_deprecated:
            #self.adapter=self.adapterProcess(log=self.log, dataset=self.dataset, notify=self.mqttServer.notify, discover=self.mqttServer.discover, request=self.requester.request, loop=self.loop, executor=self.executor, token=self.restServer.token)
            #self.adapter=self.adapterProcess(log=self.log, dataset=self.dataset, notify=self.mqttServer.notify, discover=self.mqttServer.discover, request=self.requester.request, loop=self.loop, executor=self.executor)
            self.adapter=self.adapterProcess(log=self.log, dataset=self.dataset, notify=self.mqttServer.notify, discover=self.mqttServer.discover, request=None, loop=self.loop, executor=self.executor)

        else:
            #self.adapter=self.adapterProcess(log=self.log, dataset=self.dataset, notify=None, discover=None, request=self.requester.request, loop=self.loop, executor=self.executor, token=self.restServer.token)
            #self.adapter=self.adapterProcess(log=self.log, dataset=self.dataset, notify=None, discover=None, request=self.requester.request, loop=self.loop, executor=self.executor)
            self.adapter=self.adapterProcess(log=self.log, dataset=self.dataset, notify=None, discover=None, request=None, loop=self.loop, executor=self.executor)
        self.adapter.url='http://%s:%s' % (self.dataset.baseConfig['restAddress'], self.dataset.config['rest_port'])
        
        self.log.info('.. starting REST server: http://%s:%s' % (self.dataset.baseConfig['restAddress'], self.dataset.config['rest_port']))
        self.restServer = sofarest.sofaRest(port=self.dataset.config['rest_port'], loop=self.loop, log=self.log, dataset=self.dataset, collector=self.adapter.collector, categories=self.adapter.collector_categories)
        result=self.restServer.initialize()
        if not result:
            self.loop.stop()
            self.loop.close()
            sys.exit(1)
        self.dataset.adapter=self.adapter
        
        if not mqtt_deprecated:
            self.mqttServer.adapter=self.adapter
        
        self.restServer.adapter=self.adapter
    
        # wait until the adapter is created to avoid a number of race conditions
        if not mqtt_deprecated:
            self.loop.run_until_complete(self.mqttServer.connectServer())
            if not 'delay_discovery' in self.dataset.config or self.dataset.config['delay_discovery']==False:
                self.loop.run_until_complete(self.mqttServer.discoverAdapters())
        self.loop.run_until_complete(self.restServer.activate())
        self.dataset.web_notify=self.restServer.notify_event_gateway
        self.dataset.token=self.restServer.token
        self.adapter.running=True

        #self.loop.run_until_complete(self.restServer.start_event_listener())

        self.loop.run_until_complete(self.adapter.start())
        
        if not mqtt_deprecated and 'delay_discovery' in self.dataset.config and self.dataset.config['delay_discovery']==True:
            self.loop.run_until_complete(self.mqttServer.discoverAdapters())
        
        try:
            self.log.info('.. adapter primary loop running')
            self.loop.run_forever()
        except KeyboardInterrupt:
            pass
        except:
            self.log.error('.. adapter primary loop terminated', exc_info=True)
        #finally:
            #self.service_stop()
        
        self.log.info('.. stopping adapter %s' % self.adaptername)
        self.loop.close()


import os
import sys
import logging
import asyncio
import concurrent.futures
from logging.handlers import RotatingFileHandler
import json
import datetime
import functools
import signal

import sofadataset
import sofarest


class DailyRotatingFileHandler(RotatingFileHandler):

    def __init__(self, alias, basedir, mode='a', maxBytes=0, backupCount=0, encoding=None, delay=0):
        """
        @summary: 
        Set self.baseFilename to date string of today.
        The handler create logFile named self.baseFilename
        """
        self.basedir_ = basedir
        self.alias_ = alias

        self.baseFilename = self.getBaseFilename()

        RotatingFileHandler.__init__(self, self.baseFilename, mode, maxBytes, backupCount, encoding, delay)

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


class configbase():
    
    def __init__(self, adapter_name, adapter_config={}, base_config={}):
        self.adapter_name=adapter_name
        self.config_needed=False
        self.missing_fields=[]
        self.base_config=self.read_base_config()
        self.adapter_config=self.read_adapter_config()
        self.log_changes=self.set_or_default("log_changes",default=False)
        self.rest_port=self.set_or_generate("rest_port")
        self.rest_address=self.set_or_generate("rest_address")
        self.api_key=self.set_or_generate("api_key")
        self.event_gateway=self.set_or_generate("event_gateway")
        self.api_gateway=self.set_or_generate("api_gateway", mandatory=True)
        self.adapter_fields()
        
    def adapter_fields(self):
        pass

    def read_base_config(self, config_path=None):

        try:
            base_config={}
            if config_path:
                config_dir=config_path
            else:
                config_dir=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config'))
            if not os.path.isdir(config_dir):
                os.makedirs(config_dir)
            else:
                with open(os.path.join(config_dir, 'sofabase.json'), "r") as config_file:
                    base_config=json.loads(config_file.read())
        except:
            print('Did not load base config')
            
        try:
            if 'config_directory' in base_config:
                self.config_directory=base_config['config_directory']
            else:
                self.config_directory=config_dir

            if 'base_directory' in base_config:
                self.base_directory=base_config['base_directory']
            else:
                self.base_directory=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

            if 'data_directory' in base_config:
                self.data_directory=base_config['data_directory']
            else:
                self.data_directory=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))

            if 'video_directory' in base_config:
                self.video_directory=base_config['video_directory']
            else:
                self.video_directory=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'video'))

            if 'cache_directory' in base_config:
                self.cache_directory=base_config['cache_directory']
            else:
                self.cache_directory=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cache'))

            if 'log_directory' in base_config:
                self.log_directory=base_config['log_directory']
            else:
                self.log_directory=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'log'))

            if 'rest_address' in base_config:
                self.log_directory=base_config['rest_address']
            else:
                self.log_directory='localhost'


        except:
            print('Did not get base config properly')
            sys.exit(1)
        return base_config
            

    def read_adapter_config(self):

        try:
            if not os.path.isdir(self.config_directory):
                os.makedirs(self.config_directory)
            with open(os.path.join(self.config_directory, "%s.json" % (self.adapter_name)), "r") as configfile:
                configdata=configfile.read()
                return json.loads(configdata)
        except:
            self.log.error('Did not load config: %s' % self.adaptername, exc_info=True)
        return {}

        
    def set_or_default(self, property_name, mandatory=False, default=None):
        if property_name in self.adapter_config:
            setattr(self, property_name, self.adapter_config[property_name])
            return self.adapter_config[property_name]
        if property_name in self.base_config:
            setattr(self, property_name, self.base_config[property_name])
            return self.base_config[property_name]
        if mandatory:
            self.config_needed=True
            self.missing_fields.append(property_name)
            return None
        setattr(self, property_name, default)
        return default

    def set_or_generate(self, property_name, mandatory=False):
        if property_name in self.adapter_config:
            return self.adapter_config[property_name]
        if property_name in self.base_config:
            return self.base_config[property_name]

        if mandatory:
            self.config_needed=True
            self.missing_fields.append(property_name)
        return default


class adapterbase():

    
    @property
    def collector(self):
        return False 
        
    @property
    def collector_categories(self):
        return []  

    def __init__(self, log=None, loop=None, dataset=None, config=None, **kwargs):
        self.dataset=dataset
        self.config=config
        self.log=log
        self.loop=loop

            
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
            with open(os.path.join(self.config.config_directory, '%s.json' % jsonfilename),'r') as jsonfile:
                return json.loads(jsonfile.read())
        except FileNotFoundError:
            self.log.error('!! Error loading json - file does not exist: %s' % jsonfilename)
            return {}
        except:
            self.log.error('Error loading pattern: %s' % jsonfilename,exc_info=True)
            return {}
            
    def saveJSON(self, jsonfilename, data):
        
        try:
            jsonfile = open(os.path.join(self.config.config_directory, '%s.json' % jsonfilename), 'wt')
            json.dump(data, jsonfile, ensure_ascii=False, default=self.jsonDateHandler)
            jsonfile.close()

        except:
            self.log.error('Error saving json: %s' % jsonfilename,exc_info=True)
            return {}
            
    def load_cache(self, filename, json_format=True):
        
        try:
            if json_format:
                filename="%s.json" % filename
            with open(os.path.join(self.config.cache_directory, filename),'r') as cachefile:
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
            cachefile = open(os.path.join(self.config.cache_directory, filename), 'wt')
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
    
    class adapter_config(configbase):
    
        def start(self):
            pass

    class adapterProcess():
        
        # AdapterProcess should be implemented independently by each adapter

        def __init__(self, log):
            pass
        
        def get(self):
            pass
        
        async def stop(self):
            self.log.info('Stopping adapter')
            
        async def start(self):
            self.log.info('Starting adapter')
            pass


    def __init__(self, name=None, loglevel="INFO"):
        
        if name==None:
            print('Adapter name not provided')
            sys.exit(1)
        
        self.adaptername=name
        self.configpath=".."
        self.baseConfig=self.readBaseConfig(self.configpath)
        self.basepath=self.baseConfig['baseDirectory']
        self.logsetup(self.baseConfig['logDirectory'], self.adaptername, loglevel, errorOnly=self.baseConfig['error_only_logs'])
        
        # https://github.com/django/asgiref/issues/143
        if sys.platform == "win32" and sys.version_info >= (3, 8, 0):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
        self.loop = asyncio.get_event_loop()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10,)

    class eight_filter(logging.Filter):
        def filter(self, record):
            record.filename_eight = record.filename.split(".")[0][:8]
            return True   
            
    def logsetup(self, logbasepath, logname, level="INFO", errorOnly=[]):

        log_formatter = logging.Formatter('%(asctime)-6s.%(msecs).03d %(filename_eight)-8s %(levelname).1s%(lineno)4d: %(message)s','%m/%d %H:%M:%S')
        if not os.path.isdir(logbasepath):
            os.makedirs(logbasepath)
        logpath=os.path.join(logbasepath, logname)
        logfile=os.path.join(logpath,"%s.log" % logname)
        errorfile=os.path.join(logpath,"%s.err.log" % logname)
        loglink=os.path.join(logbasepath,"%s.log" % logname)
        if not os.path.exists(logpath):
            os.makedirs(logpath)

        log_error_handler = RotatingFileHandler(errorfile, mode='a', maxBytes=1024*1024, backupCount=5)
        log_error_handler.setFormatter(log_formatter)
        log_error_handler.setLevel(logging.WARNING)
        if os.path.isfile(logfile):
            log_error_handler.doRollover()
            
        log_handler = RotatingFileHandler(logfile, mode='a', maxBytes=1024*1024, backupCount=5)
        log_handler.setFormatter(log_formatter)
        log_handler.setLevel(getattr(logging,level))
        if os.path.isfile(logfile):
            log_handler.doRollover()
            
        self.count_handler = MsgCounterHandler()
        
        console = logging.StreamHandler()
        console.setFormatter(log_handler)
        console.setLevel(getattr(logging,level))
        
        logging.getLogger(logname).addHandler(console)
        
        self.log =  logging.getLogger(logname)
        self.log.addFilter(self.eight_filter()) 
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
            if not os.path.isdir(self.config.config_directory):
                os.makedirs(self.config.config_directory)
            with open(os.path.join(self.config.config_directory, "%s.json" % (self.adaptername)), "r") as configfile:
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
            if not os.path.isdir(self.config.config_directory):
                os.makedirs(self.config.config_directory)
            with open(os.path.join(self.config.config_directory, "%s.json" % (self.adaptername)), "w") as configfile:
                configfile.write(json.dumps(self.dataset.config))
            return True

        except:
            self.log.error('Did not save config: %s' % self.adaptername, exc_info=True)
            return False

    def readBaseConfig(self, config_path):

        try:
            base_config={}
            config_dir=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config'))
            if not os.path.isdir(config_dir):
                os.makedirs(config_dir)
            with open(os.path.join(config_dir, 'sofabase.json'), "r") as config_file:
                base_config=json.loads(config_file.read())
        except:
            print('Did not load base config')
            
        try:
            if 'configDirectory' not in base_config:
                base_config['configDirectory']=config_dir
            if 'baseDirectory' not in base_config:
                base_config['baseDirectory']=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
            if 'logDirectory' not in base_config:
                base_config['logDirectory']=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'log'))
            if 'restAddress' not in base_config:
                base_config['restAddress']='localhost'

            return base_config
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
                    
                for task in asyncio.Task.all_tasks():
                    task.cancel()
                    
                if self.restServer:
                    self.restServer.shutdown()
                if self.executor:
                    self.log.info('Shutting down executor')
                    self.executor.shutdown(wait=True)
                #self.loop.run_until_complete(self.loop.shutdown_asyncgens())
                
                #tasks = asyncio.all_tasks(self.loop)
                #self.loop.run_until_complete(asyncio.gather(*tasks))
                
            except:
                self.log.error('!! error in service stop', exc_info=True)
            self.loop.stop()
        except:
            self.log.error('Error stopping loop', exc_info=True)

        
    def start(self):

        self.log.info('.. Sofa 2 Adapter module initialized and starting')
        asyncio.set_event_loop(self.loop)
        if not sys.platform == "win32":
            signal.signal(signal.SIGTERM, self.service_stop)
            for signame in {'SIGINT', 'SIGTERM'}:
                self.loop.add_signal_handler(
                    getattr(signal, signame),
                    functools.partial(self.service_stop, signame))
        
        self.config=self.adapter_config(adapter_name=self.adaptername)

        self.dataset=sofadataset.sofaDataset(self.log, adaptername=self.adaptername, loop=self.loop, config=self.config)
        self.dataset.logged_lines=self.count_handler.logged_lines
        #self.dataset.baseConfig=self.baseConfig
        #self.dataset.config=self.readconfig()
        self.dataset.saveConfig=self.saveConfig
        
        if self.config.config_needed:
            self.log.error('.. Mandatory fields missing from config: %s' % self.config.missing_fields)
            self.loop.stop()
            self.loop.close()
            sys.exit(1)
            
        #self.dataset.config=self.config
            
        if self.config.log_changes==True:
            pass
        else:
            self.log.debug('.! adapter is not logging device changes')
        
        self.log.info('.. intializing main adapter %s' % self.adaptername)
        self.adapter=self.adapterProcess(log=self.log, dataset=self.dataset, notify=None, discover=None, request=None, loop=self.loop, executor=self.executor, config=self.config)

        self.adapter.running=True
        self.dataset.adapter=self.adapter
        
        if hasattr(self.adapter,'pre_activate'):
            self.loop.run_until_complete(self.adapter.pre_activate())

        self.adapter.url='http://%s:%s' % (self.config.rest_address, self.config.rest_port)
        
        self.log.info('.. starting REST server: http://%s:%s' % (self.config.rest_address, self.config.rest_port))
        self.restServer = sofarest.sofaRest(loop=self.loop, log=self.log, dataset=self.dataset, collector=self.adapter.collector, categories=self.adapter.collector_categories, config=self.config)
        self.restServer.adapter=self.adapter
        
        result=self.restServer.initialize()

        if not result:
            self.loop.stop()
            self.loop.close()
            sys.exit(1)

        self.loop.run_until_complete(self.restServer.activate())
        self.dataset.web_notify=self.restServer.notify_event_gateway
        self.dataset.token=self.restServer.token
        self.loop.run_until_complete(self.adapter.start())
        

        try:
            self.log.info('.. adapter primary loop running')
            self.loop.run_forever()
        except KeyboardInterrupt:
            pass
        except:
            self.log.error('.. adapter primary loop terminated', exc_info=True)

        self.log.info('.. stopping adapter %s' % self.adaptername)
        self.loop.close()


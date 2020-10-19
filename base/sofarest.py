import devices
import reports
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

class sofaRest():
    
    def initialize(self):
            
        try:
            if not self.config.rest_port:
                self.log.info('.. no rest port provided.  Adapter rest server will start when port is specified')
            while not self.config.rest_port:
                asyncio.sleep(1)
                
            #self.log.info('Dataset: %s' % self.dataset.__dict__)
            self.serverAddress=self.config.rest_address
            self.serverApp = aiohttp.web.Application()
            self.serverApp.router.add_get('/', self.statusHandler)
            self.serverApp.router.add_post('/', self.rootRequestHandler)
            
            self.serverApp.router.add_get('/native', self.nativeLookupHandler)
            self.serverApp.router.add_get('/status', self.statusHandler)
            
            self.serverApp.router.add_get('/favicon.ico', self.iconHandler)
            self.serverApp.router.add_get('/adapters', self.adapterLookupHandler)
            
            self.serverApp.router.add_get('/discovery', self.deviceLookupHandler)
            self.serverApp.router.add_get('/devices', self.deviceLookupHandler)        
            self.serverApp.router.add_get('/devices/local', self.local_devices_handler)
            self.serverApp.router.add_get('/devices/remote', self.remoteDeviceLookupHandler)         
            self.serverApp.router.add_get('/devices/remote/{item}', self.remoteDeviceStateReportHandler)
            self.serverApp.router.add_get('/devices/{item}', self.deviceStateReportHandler)
            self.serverApp.router.add_get('/deviceState/{item}', self.deviceStateReportHandler)
            self.serverApp.router.add_post('/deviceStates', self.deviceStatesReportHandler)
            self.serverApp.router.add_get('/ReportState/{item}', self.deviceStateReportHandler)
            
            self.serverApp.router.add_post('/nativegroup', self.nativeGroupHandler)
            
            self.serverApp.router.add_get('/image/{item:.+}', self.imageHandler)
            self.serverApp.router.add_get('/thumbnail/{item:.+}', self.thumbnailHandler)
            self.serverApp.router.add_get('/list/{list:.+}', self.listHandler)
            self.serverApp.router.add_post('/list/{list:.+}', self.listPostHandler)
            
            self.serverApp.router.add_get('/var/{list:.+}', self.varHandler)
            
            self.serverApp.router.add_post('/update/{item}', self.updatePostHandler)
            
            self.serverApp.router.add_post('/save/{save:.+}', self.saveHandler)
            self.serverApp.router.add_post('/add/{add:.+}', self.addHandler)
            self.serverApp.router.add_post('/del/{del:.+}', self.delHandler)            
            
            self.serverApp.router.add_get('/{category}', self.categoryLookupHandler)
            self.serverApp.router.add_get('/{category}/{item:.+}', self.itemLookupHandler)

            self.runner=aiohttp.web.AppRunner(self.serverApp)

            self.loop.run_until_complete(self.runner.setup())

            self.site = aiohttp.web.TCPSite(self.runner, self.serverAddress, self.config.rest_port)
            self.loop.run_until_complete(self.site.start())
            return True
        except OSError as e:
            if e.errno==98:
                self.log.error('!! REST port %s is already in use.  Is another copy of the adapter running?' % (self.config.rest_port))
            else:
                self.log.error('!! Error starting REST server', exc_info=True)
        except:
            self.log.error('!! Error starting REST server', exc_info=True)
            return False

    def json_response(self, body='', **kwargs):
        try:
            if (body or 'body' in kwargs):
                kwargs['body'] = json.dumps(body or kwargs['body'], default=self.date_handler).encode('utf-8')
            kwargs['content_type'] = 'application/json'
            return aiohttp.web.Response(**kwargs)
        except:
            self.log.error('!! error with json response: %s %s' % (body, kwargs), exc_info=True)
            return aiohttp.web.Response({'body':''})
            

    def date_handler(self, obj):
        
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        else:
            self.log.info('Caused type error: %s' % obj)
            raise TypeError
            
    def get_ip(self, request):
        try:
            return request.headers['X-Real-IP']
        except:
            return request.remote
            
    def lookupAddressOrName(self, item, lookup=None):
            
        if lookup==None:
            lookup=self.data
            
        result = self.dataset.getObjectFromPath("/%s" % item, data=lookup, trynames=True)
        if result!={}:
            return result
            
        if item.split('/')[0] in lookup:
            try:
                return dpath.util.get(lookup, item)
            except:
                self.log.error('Error with data lookup: %s' % item, exc_info=True)
                return {}
        else:
            try:
                nameItems=item.split('/')
                for aitem in lookup:
                    if 'name' in lookup[aitem]:
                        if lookup[aitem]['name'].lower()==nameItems[0].lower():
                            nameItems[0]=aitem
                            newsearch="/".join(nameItems)
                            return dpath.util.get(lookup, newsearch)
                    if 'friendlyName' in lookup[aitem]:
                        if lookup[aitem]['friendlyName'].lower()==nameItems[0].lower():
                            nameItems[0]=aitem
                            newsearch="/".join(nameItems)
                            return dpath.util.get(lookup, newsearch)
            except:
                self.log.error('Error with data request',exc_info=True)
                        
        return {}

    def queryStringAdjuster(self, querystring, lookup):
            
        if querystring.find('stateReport')>-1:
            self.log.info('Querystring: %s' % querystring)
            controllers={}
            try:
                for cap in lookup['capabilities']:
                    if ('&' not in querystring) or (cap['interface'].split('.')[1] in querystring.split('&')):
                        props=[]
                        for item in cap['properties']['supported']:
                            props.append(item['name'])
                        controllers[cap['interface'].split('.')[1]]=props
                self.log.info('Cont: %s' % controllers)
                lookup=self.dataset.generateStateReport(lookup['cookie']['path'], controllers)
                if '&' in querystring:
                    lookup=lookup['context']['properties']
            except:
                self.log.error('Couldnt build state report for %s' % querystring, exc_info=True)

                
        elif querystring.find('keynames')>-1:
            namepairs={}
            for item in lookup:
                try:
                    namepairs[item]=lookup[item]['name']
                except:
                    namepairs[item]=item
            lookup=dict(namepairs)

        elif querystring.find('namekeys')>-1:
            namepairs={}
            for item in lookup:
                try:
                    namepairs[lookup[item]['name']]=item
                except:
                    namepairs[item]=item
            lookup=dict(namepairs)

        elif querystring.find('keys')>-1:
            lookup=list(lookup.keys())

        elif querystring.find('names')>-1:
            namepairs=[]
            for item in lookup:
                try:
                    namepairs.append(lookup[item]['name'])
                except:
                    namepairs.append(item)
            lookup=list(namepairs)
                
        return lookup
        
            
    async def nativeLookupHandler(self, request):
    
        try:
            lookup=self.dataset.nativeDevices
            if request.query_string:
                lookup=self.queryStringAdjuster(request.query_string, lookup)
            return self.json_response(lookup)
        except:
            self.log.error('Error with native lookup', exc_info=True)


    async def deviceLookupHandler(self, request):
        self.log.info('.. device lookup handler')
        lookup=await self.dataset.discovery()
        return self.json_response(lookup)

    async def local_devices_handler(self, request):
        return self.json_response(self.dataset.localDevices)


    async def remoteDeviceLookupHandler(self, request):
        self.log.info('.. device lookup handler')
        lookup=await self.dataset.remote_devices()
        return self.json_response(lookup)
        

    async def remoteDeviceStateReportHandler(self, request):
        try:
            dev=urllib.parse.unquote(request.match_info['item'])
            self.log.info('.. remote device lookup handler: %s' % dev)
    
            if hasattr(self.adapter, 'state_cache'):
                if dev in self.adapter.state_cache:
                    return self.json_response(self.adapter.state_cache[dev])
        except:
            self.log.error('!! error getting remote device state', exc_info=True)
        return {}

        
    async def deviceStatesReportHandler(self, request):
        
        body=''
        try:
            if request.body_exists:
                body=await request.read()
                body=body.decode()
                devlist=json.loads(body)
                result={}
                self.log.info('.. states report handler: %s %s' % (self.get_ip(request),devlist) )
                for dev in devlist:
                    try:
                        result[dev]=self.dataset.getDeviceByEndpointId(dev).StateReport()
                        #result[dev]=self.dataset.getDeviceByfriendlyName(dev).StateReport()
                    except AttributeError: 
                        self.log.warn('.! warning - device was not ready for statereport: %s' % dev)
                    except:
                        self.log.error('!! error getting statereport for %s' % dev, exc_info=True)

                return self.json_response(result) 
            else:
                return self.json_response({})      

        except:
            self.log.error('!! Error delivering device states report: %s' % body, exc_info=True)
            return self.json_response({})        

    async def deviceStateReportHandler(self, request):
        try:
            self.log.info('.. state report handler: %s %s' % (self.get_ip(request), request.match_info['item']) )
            dev=urllib.parse.unquote(request.match_info['item'])
            try:
                lookup=self.dataset.getDeviceByEndpointId(dev).StateReport()
                return self.json_response(lookup)
            except AttributeError:
                pass
            
            try:
                lookup=self.dataset.getDeviceByfriendlyName(dev).StateReport()
                return self.json_response(lookup)
            except AttributeError:
                pass
            
        except KeyError:
            self.log.error('Lookup error for %s' % urllib.parse.unquote(request.match_info['item']))
        except:
            self.log.error('Error delivering state report for %s' % urllib.parse.unquote(request.match_info['item']), exc_info=True)
        
        return self.json_response({})


    async def categoryLookupHandler(self, request):
        try:
            self.log.info('request: %s' % request.match_info['category'])
            #subset=await self.dataset.getCategory(request.match_info['category'])
            subset=self.dataset.getObjectsByDisplayCategory(request.match_info['category'])
            if request.query_string:
                subset=self.queryStringAdjuster(request.query_string, subset)
            return self.json_response(subset)
        except:
            self.log.error('Error on category lookup', exc_info=True)
            return self.json_response({})


    async def listHandler(self, request):
        try:
            #self.log.info('request: %s' % request.match_info['list'])
            subset=await self.dataset.getList(request.match_info['list'])
            #self.log.info('List: %s %s' % (request.match_info['list'],subset))
            return self.json_response(subset)
        except:
            self.log.info('error handling list', exc_info=True)
            return self.json_response({})

    async def varHandler(self, request):
        try:
            self.log.info('request: %s' % request.match_info['list'])
            subset=await self.dataset.getList(request.match_info['list'])
            return self.json_response(subset)

        except:
            self.log.info('error handling list', exc_info=True)
            return self.json_response({})

    async def listPostHandler(self, request):
        
        try:
            subset={}
            if request.body_exists:
                try:
                    body=await request.read()
                    #item="%s?%s" % (request.match_info['list'], request.query_string)
                    item=request.match_info['list']
                    body=body.decode()
                    subset=await self.dataset.getList(request.match_info['list'], query=body)
                    #self.log.info('List Query request for %s: %s' % (request.match_info['list'], body))
                except:
                    self.log.info('error handling list query request', exc_info=True)
                    
            return self.json_response(subset)
        except:
            self.log.info('error handling list post', exc_info=True)
            return self.json_response({})


    async def nativeGroupHandler(self, request):
        try:
            response={}
            if hasattr(self.adapter, "virtual_group_handler"):
                subset={}
                if request.body_exists:
                    try:
                        body=await request.read()
                        body=body.decode()
                        data=json.loads(body)
                        result=await self.adapter.virtual_group_handler(data['controller'], data['devices'])
                        self.log.info('<< native group %s: %s' % (body, result))
                    except:
                        self.log.info('!! error handling nativegroup request', exc_info=True)
        except:
            self.log.info('error handling list post', exc_info=True)
        return self.json_response(result)


    async def updatePostHandler(self, request):
        
        try:
            if hasattr(self.adapter, "virtual_update"):
                subset={}
                if request.body_exists:
                    try:
                        body=await request.read()
                        #item="%s?%s" % (request.match_info['list'], request.query_string)
                        item=request.match_info['item']
                        body=body.decode()
                        self.log.info('>> update/%s: %s' % (request.match_info['item'], body))
                        response=await self.adapter.virtual_update(request.match_info['item'], data=body)
                    except:
                        self.log.info('error handling list query request', exc_info=True)
            return self.json_response(response)        
        except:
            self.log.info('error handling list post', exc_info=True)
            return self.json_response({})

            
    async def saveHandler(self, request):
        
        if request.body_exists:
            try:
                outputData={}
                body=await request.read()
                #item="%s?%s" % (request.match_info['save'], request.query_string)
                item=request.match_info['save']
                body=body.decode()
                self.log.info('.. save request for %s: %s' % (request.match_info['save'], body))
                if hasattr(self.adapter, "virtualSave"):
                    result=await self.adapter.virtualSave(request.match_info['save'], body)
                    return self.json_response(result)
                response
                return self.json_response({"status":"failed", "reason":"No Save Handler Available"})
                
            except:
                self.log.info('error handling write request', exc_info=True)
                return self.json_response({"status":"failed", "reason":"Error with Save Handler"})

    async def addHandler(self, request):
        
        if request.body_exists:
            try:
                outputData={}
                body=await request.read()
                #item="%s?%s" % (request.match_info['add'], request.query_string)
                item=request.match_info['add']
                body=body.decode()
                self.log.info('.. add request for %s: %s' % (request.match_info['add'], body))
                if hasattr(self.adapter, "virtualAdd"):
                    result=await self.adapter.virtualAdd(request.match_info['add'], body)
                    return self.json_response(result)
                return self.json_response({"status":"failed", "reason":"No Add Handler Available"})
                
            except:
                self.log.info('error handling add request', exc_info=True)
                return self.json_response({"status":"failed", "reason":"Error with Add Handler"})

    async def delHandler(self, request):

        try:
            outputData={}
            body={}
            if request.body_exists:
                body=await request.read()
                body=body.decode()
            #item="%s?%s" % (request.match_info['del'], request.query_string)
            item=request.match_info['del']
            self.log.info('.. del request for %s: %s' % (request.match_info['del'], body))
            if hasattr(self.adapter, "virtualDel"):
                result=await self.adapter.virtualDel(request.match_info['del'], body)
                return self.json_response(result)
            return self.json_response({"status":"failed", "reason":"No Del Handler Available"})
            
        except:
            self.log.info('error handling del request', exc_info=True)
            return self.json_response({"status":"failed", "reason":"Error with Del Handler"})

    async def imageHandler(self, request):
            
        try:
            if hasattr(self.adapter, "virtualImage"):
                result=await self.adapter.virtualImage(request.match_info['item'], width=request.rel_url.query.get('width'), height=request.rel_url.query.get('height'))
                return aiohttp.web.Response(body=result, headers = { "Content-type": "image/jpeg" })
                        
            return aiohttp.web.Response(text='No image found')
        except:
            self.log.error('Error getting image for: %s' % request.match_info['item'], exc_info=True)
            return aiohttp.web.Response(text='No image found')
 
                
    async def thumbnailHandler(self, request):
            
        try:
            if hasattr(self.adapter, "virtualThumbnail"):
                result=await self.adapter.virtualThumbnail(request.match_info['item'], width=request.rel_url.query.get('width'), height=request.rel_url.query.get('height'))
                return aiohttp.web.Response(body=result, headers = { "Content-type": "image/jpeg" })
                        
            return aiohttp.web.Response(text='No thumbnail image found')
        except:
            self.log.error('Error getting thumbnail image for: %s' % request.match_info['item'], exc_info=True)
            return aiohttp.web.Response(text='No thumbnail image found')


    async def itemLookupHandler(self, request):
        self.log.info('Request: %s %s' % (request.match_info['category'], request))
        subset=self.dataset.getObjectsByDisplayCategory(request.match_info['category'])
        #subset=await self.dataset.getCategory(request.match_info['category'])
        self.log.info('Relative path: %s' % request.rel_url)
        #subset=self.lookupAddressOrName(urllib.parse.unquote(request.match_info['item']), subset)
        subset=self.dataset.getObjectFromPath("/%s" % urllib.parse.unquote(request.match_info['item']), data=subset, trynames=True)    
        if request.query_string:
            subset=self.queryStringAdjuster(request.query_string, subset)
        
        return self.json_response(subset)


    async def adapterLookupHandler(self, request):
                
        return self.json_response(self.dataset.adapters)


    async def rootRequestHandler(self, request):
        
        response={}
#        try:
        reqstart=datetime.datetime.now()
        if self.response_token==None:
            self.log.info('.. adapter is not activated and no response_token has been generated.')
            raise aiohttp.web.HTTPUnauthorized()
        elif 'authorization' in request.headers:
            if request.headers['authorization']!=self.response_token:
                self.log.info('.. incorrect response_token: (sent %s vs actual %s)' % (request.headers['authorization'],self.response_token))
                raise aiohttp.web.HTTPUnauthorized()
        else:
            self.log.info('.. no token was provided.')
            raise aiohttp.web.HTTPUnauthorized()
        if request.body_exists:
            try:
                readstart=datetime.datetime.now()
                body=await request.read()
                jsondata=json.loads(body.decode())
                readend=datetime.datetime.now()
                #self.log.info('>> Post JSON: %s %s' % ('event' in jsondata, hasattr(self.adapter,'process_event')))
                if 'event' in jsondata and hasattr(self.adapter,'process_event'):
                    #self.log.info('.. processing event: %s' % self.dataset.alexa_json_filter(jsondata))
                    asyncio.create_task(self.adapter.process_event(jsondata))
                    
                if 'directive' in jsondata:
                    response= await self.dataset.handle_local_directive(jsondata)

            except KeyError:
                self.log.error('!! Invalid root request from %s: %s' % (request.remote, body), exc_info=True)
            except:
                self.log.error('Error handling root request from %s: %s' % (request.remote, body),exc_info=True)
        reqend=datetime.datetime.now()
        if (reqend-reqstart).total_seconds() > 1:
            self.log.info('.. long request handle time: %s / read: %s ' % ( (reqend-reqstart).total_seconds(), (readend-readstart).total_seconds() )  )
#        except:
#            self.log.error('.. error with root request handler', exc_info=True)
        return self.json_response(response)

        
    async def statusHandler(self, request):
        try:
            urls={ "native": "http://%s:%s/native" % (self.serverAddress, self.config.rest_port), "devices": "http://%s:%s/devices" % (self.serverAddress, self.config.rest_port)}
            return self.json_response({"name": self.dataset.adaptername, "mqtt": self.dataset.mqtt, "logged": self.dataset.logged_lines, "native_size": self.dataset.getSizeOfNative(), "urls": urls})
        except:
            self.log.error('!! Error handling status request',exc_info=True)


    async def iconHandler(self, request):
        return self.json_response({"icon": "missing"})
        
    async def retry_activation(self):
        try:
            self.log.info('.. waiting %s seconds to retry activation' % self.activation_retry)
            await asyncio.sleep(self.activation_retry)
            self.activated=await self.activate(force=True)
        except:
            self.log.error('!! error retrying activation')

    async def publish_adapter_device(self):
        try:
            url="http://%s:%s" % (self.serverAddress, self.config.rest_port)
            device=devices.alexaDevice('%s/adapter/%s' % (self.dataset.adaptername, self.dataset.adaptername), self.dataset.adaptername, displayCategories=["ADAPTER"], adapter=self)
            device.AdapterHealth=devices.AdapterHealth(device=device, url=url)
            smartAdapter=self.dataset.newaddDevice(device)
            self.log.info('++ AddOrUpdateReport: %s (%s)' % (smartAdapter.friendlyName, smartAdapter.endpointId))
            await self.notify_event_gateway(smartAdapter.addOrUpdateReport)
        except:
            self.log.error('!! error publishing adapter', exc_info=True)

    async def hub_watchdog(self):

        # This function does not have a try/except clause due to rare problems with GeneratorExit on 
        # unusual crashes like temporary network connectivity problems
        # https://stackoverflow.com/questions/30862196/generatorexit-in-python-generator

        while self.activated:
            status=await self.get_post_event_gateway(method='GET', path='status')
            if 'status' in status and status['status']=='up':
                self.log.debug('.. good status from watchdog: %s' % status)
            else:
                self.log.warning('!! hub monitor failed to reply on status update check. attempting to re-activate adapter.')
                self.activated=False
                break
            await asyncio.sleep(20)
        await self.activate()

    async def hub_discovery(self):

        try:
            if self.activated:
                result=await self.get_post_event_gateway(data=json.dumps(reports.Discover()))
                await self.adapter.handleAddOrUpdateReport(result)
                self.log.info('.. discovered %s devices on hub @ %s' % (len(result['event']['payload']['endpoints']), self.config.event_gateway) )
                if hasattr(self.adapter, 'state_cache'):
                    self.log.info('.. clearing state cache')
                    self.adapter.state_cache={}

        except:
            self.log.error('!! Error running discovery on hub: %s' % self.config.event_gateway ,exc_info=True)

        
    async def activate(self, force=False):
        try:
            if self.adapter.is_hub:
                return True
            
            if not self.activating or force:
                self.activating=True
                self.response_token=str(uuid.uuid1())
                if not hasattr(self.config,'api_key') or self.config.api_key=="":
                    self.config.api_key=str(uuid.uuid1())
                    self.dataset.saveConfig()
                url = '%s/activate' % (self.config.api_gateway)
                data={  'name':self.dataset.adaptername, 'response_token': self.response_token, 'api_key': self.config.api_key, 
                        'collector': self.adapter.collector, "categories": self.adapter.collector_categories, "type": "adapter", 
                        "url": "http://%s:%s" % (self.serverAddress, self.config.rest_port) }
    
                self.log.info('>> Posting activation request to %s %s' % (url, self.response_token))
                #self.log.debug('.. activation request: %s' % data)

                result=await self.get_post_event_gateway(path='activate', data=data)
                if 'token' in result:
                    self.token=result['token']
                    self.dataset.token=result['token']
                    self.token_expires=datetime.datetime.strptime(result['expiration'], '%Y-%m-%dT%H:%M:%S.%f')
                    # supposedly supported in python 3.7 but does not seem to work in 3.7.3 on rpi
                    # self.token_expires=datetime.fromisoformat(result['expiration'])
                    self.log.info('<< received hub token: %s good until %s' % (result['token'][-10:], result['expiration']))
                    self.activated=True
    
                    if self.adapter.collector:
                        asyncio.create_task(self.hub_discovery())    
                    
                    asyncio.create_task(self.hub_watchdog())
                    
                    self.activating=False
                    if hasattr(self.adapter,'post_activate'):
                        await self.adapter.post_activate()
                    
                    return True
                elif result:
                    self.log.error('<< Error with activation request: %s' % result)
                    
                asyncio.create_task(self.retry_activation())
            else:
                self.log.debug('.. activation is already in progress')
        
        except:
            self.log.error('!! Error with activation', exc_info=True)        
        
        self.devices={}
        return False


    async def check_token_refresh(self, refresh_buffer=120):
        try:
            expire_seconds=0
            if self.token_expires:
                delta=(self.token_expires-datetime.datetime.now()).total_seconds()
                expire_seconds=int(delta)
            if expire_seconds<refresh_buffer:
                self.log.info('.. token needs refresh')
                await self.activate()

        except:
            self.log.error('error checking token expiration', exc_info=True)

    async def notify_event_gateway(self, data):
        try:
            if self.activated:
                await self.check_token_refresh()
            if self.token and self.activated:
                await self.get_post_event_gateway(data=data)
        except:
            self.log.error('.. error in event gateway notify', exc_info=True)


    async def get_post_event_gateway(self, path=None, method='POST', data={}, timeout=5):
        try:
            result={}
            url = self.config.event_gateway
            if path:
                url="%s/%s" % (url, path)
            if self.token:
                headers = { 'authorization': self.token }
            else:
                headers = {}
            total_timeout = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=total_timeout) as client:
                if method=='POST':
                    response=await client.post(url, json=data, headers=headers)
                elif method=='GET':
                    response=await client.get(url, headers=headers)
                else:
                    self.log.info('.. unsupported gateway method: %s' % method)
                    return {}

                if response.status == 200:
                    #self.log.info('>> event gateway: %s' % (self.adapter.alexa_json_filter(data)))
                    result=await response.read()
                    result=result.decode()
                    result=json.loads(result)
                    if result:
                        self.log.debug('.. result: %s' % result)
                elif response.status == 401:
                    self.log.info('.. error token is not valid: %s %s' % (response.status, self.token))
                    self.activated=False
                    asyncio.create_task(self.activate())
                    result={}
                else:
                    self.log.error('>! Error sending to event gateway: %s' % response.status, exc_info=True)
                    result={}     
                    
        except concurrent.futures._base.CancelledError:
            self.log.error(">! Error sending to event gateway (cancelled) %s" % ( self.dataset.alexa_json_filter(data)))
        except aiohttp.client_exceptions.ClientConnectorError:
            self.log.warn('>! Error in %s to event gateway (Client Connector Error): %s %s %s' % (method, url, headers, data))
        except aiohttp.client_exceptions.ServerDisconnectedError:
            self.log.error('>! Error sending to event gateway (server disconnected): %s %s %s' % (method, url, headers, data))
        except concurrent.futures._base.TimeoutError:
            self.log.warn('>! Error in %s to event gateway (Timeout): %s %s' % (method, url, data))
        except:
            self.log.warn('>! Error in %s to event gateway: %s %s' % (method, url, data), exc_info=True)
        return result

    def shutdown(self):
        self.log.info('.. do we need rest server shutdown? skipped for testing')
        #asyncio.create_task(self.serverApp.shutdown())

    #def __init__(self, loop, log=None, dataset={}, collector=False, categories=[], config=None):
    def __init__(self, loop, log=None, dataset={}, adapter=None, config=None):

        self.config=config
        self.loop = loop
        self.log=log
        self.adapter=adapter
        self.dataset=dataset
        self.activated=False
        self.activating=False
        self.activation_retry=20
        self.token=None
        self.response_token=None
        self.token_expires=0

    

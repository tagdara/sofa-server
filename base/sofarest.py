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
import sofamqtt
import sofadataset
from aiohttp_sse_client import client as sse_client

class sofaRest():
        
    # The Sofa Rest Handler provides an http request framework for retrieving the current state of an adapter
    
    # API
    #       /status         - Show basic status and health of the adapter
    #       /native         - List native devices and their properties
    #       /discovery      - List device discovery data in Alexa format
    
    
    def initialize(self):
            
        try:
            #self.log.info('Dataset: %s' % self.dataset.__dict__)
            self.serverAddress=self.dataset.baseConfig['restAddress']
            self.serverApp = web.Application()
            self.serverApp.router.add_get('/', self.statusHandler)
            self.serverApp.router.add_post('/', self.rootRequestHandler)
            
            self.serverApp.router.add_get('/native', self.nativeLookupHandler)
            self.serverApp.router.add_get('/status', self.statusHandler)
            
            self.serverApp.router.add_get('/favicon.ico', self.iconHandler)
            self.serverApp.router.add_get('/adapters', self.adapterLookupHandler)
            
            self.serverApp.router.add_get('/discovery', self.deviceLookupHandler)
            self.serverApp.router.add_get('/devices', self.deviceLookupHandler)            
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

            self.site = web.TCPSite(self.runner, self.serverAddress, self.port)
            self.loop.run_until_complete(self.site.start())
            return True
        except OSError as e:
            if e.errno==98:
                self.log.error('!! REST port %s is already in use.  Is another copy of the adapter running?' % (self.port))
            else:
                self.log.error('!! Error starting REST server', exc_info=True)
        except:
            self.log.error('!! Error starting REST server', exc_info=True)
            return False

    def json_response(self, body='', **kwargs):
        try:
            kwargs['body'] = json.dumps(body or kwargs['body']).encode('utf-8')
            kwargs['content_type'] = 'application/json'
            return web.Response(**kwargs)
        except:
            self.log.error('!! error with json response', exc_info=True)
            return web.Response({'body':''})


    def date_handler(self, obj):
        
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        else:
            self.log.info('Caused type error: %s' % obj)
            raise TypeError
            
                
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
            return web.Response(text=json.dumps(lookup, default=self.date_handler))
        except:
            self.log.error('Error with native lookup', exc_info=True)


    async def deviceLookupHandler(self, request):
        lookup=self.dataset.discovery()
        #self.log.info('Devices: %s' % lookup)
        return web.Response(text=json.dumps(lookup, default=self.date_handler))
            
    async def deviceStatesReportHandler(self, request):
        
        body=''
        try:
            if request.body_exists:
                body=await request.read()
                body=body.decode()
                devlist=json.loads(body)
                result={}
                for dev in devlist:
                    try:
                        result[dev]=self.dataset.getDeviceByEndpointId(dev).StateReport()
                        #result[dev]=self.dataset.getDeviceByfriendlyName(dev).StateReport()
                    except AttributeError: 
                        self.log.warn('Warning - device was not ready for statereport: %s' % dev)
                    except:
                        self.log.error('Error getting statereport for %s' % dev, exc_info=True)

                return web.Response(text=json.dumps(result, default=self.date_handler))
            else:
                return web.Response(text="{}")        

        except:
            self.log.error('Error delivering device states report: %s' % body, exc_info=True)
            return web.Response(text="{}")        

    async def deviceStateReportHandler(self, request):
        try:
            dev=urllib.parse.unquote(request.match_info['item'])
            try:
                lookup=self.dataset.getDeviceByEndpointId(dev).StateReport()
                return web.Response(text=json.dumps(lookup, default=self.date_handler))
            except AttributeError:
                pass
            
            try:
                lookup=self.dataset.getDeviceByfriendlyName(dev).StateReport()
                return web.Response(text=json.dumps(lookup, default=self.date_handler))
            except AttributeError:
                pass
            
        except KeyError:
            self.log.error('Lookup error for %s' % urllib.parse.unquote(request.match_info['item']))
        except:
            self.log.error('Error delivering state report for %s' % urllib.parse.unquote(request.match_info['item']), exc_info=True)
        
        return web.Response(text="{}")


    async def categoryLookupHandler(self, request):
        try:
            self.log.info('request: %s' % request.match_info['category'])
            #subset=await self.dataset.getCategory(request.match_info['category'])
            subset=await self.dataset.getObjectsByDisplayCategory(request.match_info['category'])
            if request.query_string:
                subset=self.queryStringAdjuster(request.query_string, subset)
            return web.Response(text=json.dumps(subset, default=self.date_handler))
        except:
            self.log.error('Error on category lookup', exc_info=True)
            return web.Response(text="{}")


    async def listHandler(self, request):
        try:
            #self.log.info('request: %s' % request.match_info['list'])
            subset=await self.dataset.getList(request.match_info['list'])
            #self.log.info('List: %s %s' % (request.match_info['list'],subset))

            return web.Response(text=json.dumps(subset, default=self.date_handler))
        except:
            self.log.info('error handling list', exc_info=True)

    async def varHandler(self, request):
        try:
            self.log.info('request: %s' % request.match_info['list'])
            subset=await self.dataset.getList(request.match_info['list'])
            return self.json_response(subset)
            #return web.Response(body=subset)
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
                    self.log.info('List Query request for %s: %s' % (request.match_info['list'], body))
                except:
                    self.log.info('error handling list query request', exc_info=True)
                    
            return web.Response(text=json.dumps(subset, default=self.date_handler))
        except:
            self.log.info('error handling list post', exc_info=True)
            return web.Response(text="{}")

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
        return web.Response(text=json.dumps(result, default=self.date_handler))


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
                    
            return web.Response(text=json.dumps(response, default=self.date_handler))
        except:
            self.log.info('error handling list post', exc_info=True)
            return web.Response(text="{}")

            

            
    async def saveHandler(self, request):
        
        if request.body_exists:
            try:
                outputData={}
                body=await request.read()
                #item="%s?%s" % (request.match_info['save'], request.query_string)
                item=request.match_info['save']
                body=body.decode()
                self.log.info('Write request for %s: %s' % (request.match_info['save'], body))
                if hasattr(self.adapter, "virtualSave"):
                    result=await self.adapter.virtualSave(request.match_info['save'], body)
                    return web.Response(text=result)
                
                return web.Response(text='{"status":"failed", "reason":"No Save Handler Available"}')
                
            except:
                self.log.info('error handling write request', exc_info=True)
                return web.Response(text='{"status":"failed", "reason":"Error with Save Handler"}')

    async def addHandler(self, request):
        
        if request.body_exists:
            try:
                outputData={}
                body=await request.read()
                #item="%s?%s" % (request.match_info['add'], request.query_string)
                item=request.match_info['add']
                body=body.decode()
                self.log.info('Write request for %s: %s' % (request.match_info['add'], body))
                if hasattr(self.adapter, "virtualAdd"):
                    result=await self.adapter.virtualAdd(request.match_info['add'], body)
                    return web.Response(text=result)
                
                return web.Response(text='{"status":"failed", "reason":"No Add Handler Available"}')
                
            except:
                self.log.info('error handling add request', exc_info=True)
                return web.Response(text='{"status":"failed", "reason":"Error with Add Handler"}')

    async def delHandler(self, request):

        try:
            outputData={}
            body={}
            if request.body_exists:
                body=await request.read()
                body=body.decode()
            #item="%s?%s" % (request.match_info['del'], request.query_string)
            item=request.match_info['del']
            self.log.info('Write request for %s: %s' % (request.match_info['del'], body))
            if hasattr(self.adapter, "virtualDel"):
                result=await self.adapter.virtualDel(request.match_info['del'], body)
                return web.Response(text=result)
            
            return web.Response(text='{"status":"failed", "reason":"No Del Handler Available"}')
            
        except:
            self.log.info('error handling del request', exc_info=True)
            return web.Response(text='{"status":"failed", "reason":"Error with Del Handler"}')


    async def imageHandler(self, request):
            
        try:
            if hasattr(self.adapter, "virtualImage"):
                result=await self.adapter.virtualImage(request.match_info['item'])
                return web.Response(body=result, headers = { "Content-type": "image/jpeg" })
                        
            return web.Response(text='No image found')
        except:
            self.log.error('Error getting image for: %s' % request.match_info['item'], exc_info=True)
            return web.Response(text='No image found')
 
                
    async def thumbnailHandler(self, request):
            
        try:
            if hasattr(self.adapter, "virtualThumbnail"):
                result=await self.adapter.virtualThumbnail(request.match_info['item'])
                return web.Response(body=result, headers = { "Content-type": "image/jpeg" })
                        
            return web.Response(text='No thumbnail image found')
        except:
            self.log.error('Error getting thumbnail image for: %s' % request.match_info['item'])
            return web.Response(text='No thumbnail image found')


    async def itemLookupHandler(self, request):
        self.log.info('Request: %s %s' % (request.match_info['category'], request))
        subset=self.dataset.getObjectsByDisplayCategory(request.match_info['category'])
        #subset=await self.dataset.getCategory(request.match_info['category'])
        self.log.info('Relative path: %s' % request.rel_url)
        #subset=self.lookupAddressOrName(urllib.parse.unquote(request.match_info['item']), subset)
        subset=self.dataset.getObjectFromPath("/%s" % urllib.parse.unquote(request.match_info['item']), data=subset, trynames=True)    
        if request.query_string:
            subset=self.queryStringAdjuster(request.query_string, subset)
                
        return web.Response(text=json.dumps(subset, default=self.date_handler))


    async def adapterLookupHandler(self, request):
                
        return web.Response(text=json.dumps(self.dataset.adapters, default=self.date_handler))


    async def rootRequestHandler(self, request):
            
        #cmds=['SetBrightness', 'TurnOn', 'TurnOff', 'SetColorTemperature', 'SetColor', 'SetVolume', 'SetMute', 'Play', 'Pause', 'Stop', 'SetSurround', 'SetDecoder']
            
        response={}
        if self.response_token==None:
            self.log.info('.. adapter is not activated and no response_token has been generated. %s' % jsondata)
            raise web.HTTPUnauthorized()
        elif 'authorization' in request.headers:
            if request.headers['authorization']!=self.response_token:
                self.log.info('.. incorrect response_token: %s vs %s' % (request.headers['authorization'],self.response_token))
                raise web.HTTPUnauthorized()
        else:
            self.log.info('.. no token was provided.')
            raise web.HTTPUnauthorized()
        if request.body_exists:
            try:
                body=await request.read()
                jsondata=json.loads(body.decode())
                #self.log.info('>> Post JSON: %s %s' % ('event' in jsondata, hasattr(self.adapter,'process_event')))
                if 'event' in jsondata and hasattr(self.adapter,'process_event'):
                    await self.adapter.process_event(jsondata)
                    
                if 'directive' in jsondata:
                    if jsondata['directive']['header']['name']=='Discover':
                        lookup=self.dataset.discovery()
                        #self.log.info('>> discovery Devices: %s' % lookup)
                        return web.Response(text=json.dumps(lookup, default=self.date_handler))

                    elif jsondata['directive']['header']['name']=='ReportStates':
                        bearerToken=''
                        #self.log.info('Reportstate: %s %s' % (jsondata['directive']['endpoint']['endpointId'], jsondata['directive']['header']['correlationToken']))
                        response=await self.dataset.generateStateReports(jsondata['directive']['payload']['endpoints'], correlationToken=jsondata['directive']['header']['correlationToken'], bearerToken=bearerToken)

                    elif jsondata['directive']['header']['name']=='ReportState':
                        try:
                            bearerToken=jsondata['directive']['endpoint']['scope']['token']
                        except:
                            self.log.info('No bearer token')
                            bearerToken=''
                        #self.log.info('Reportstate: %s %s' % (jsondata['directive']['endpoint']['endpointId'], jsondata['directive']['header']['correlationToken']))
                        response=self.dataset.generateStateReport(jsondata['directive']['endpoint']['endpointId'], correlationToken=jsondata['directive']['header']['correlationToken'], bearerToken=bearerToken)

                    elif jsondata['directive']['header']['name']=='CheckGroup':
                        try:
                            if hasattr(self.adapter, "virtual_group_handler"):
                                result=await self.adapter.virtual_group_handler(jsondata['directive']['payload']['controllers'], jsondata['directive']['payload']['endpoints'])
                                self.log.info('<< native group %s: %s' % (jsondata['directive']['payload'], result))
                                return web.Response(text=json.dumps(result, default=self.date_handler))
                        except:
                            self.log.info('!! error handling nativegroup request', exc_info=True)
                            response={}

                    else:
                        target_namespace=jsondata['directive']['header']['namespace'].split('.')[1]
                        self.log.info('<< %s' % (self.dataset.alexa_json_filter(jsondata)))
                        response=await self.dataset.handleDirective(jsondata)
                        if response:
                            try:
                                self.log.info('>> %s' % (self.dataset.alexa_json_filter(response, target_namespace)))
                            except:
                                self.log.warn('>> %s' % response)
        
                #else:
                #    self.log.info('<< Post JSON: %s' %  jsondata)
            except KeyError:
                self.log.error('!! Invalid root request from %s: %s' % (request.remote, body), exc_info=True)
            except:
                self.log.error('Error handling root request from %s: %s' % (request.remote, body),exc_info=True)
                response={}
                
        return web.Response(text=json.dumps(response, default=self.date_handler))

        
    async def statusHandler(self, request):
        try:
            urls={ "native": "http://%s:%s/native" % (self.serverAddress, self.port), "devices": "http://%s:%s/devices" % (self.serverAddress, self.port)}
            return web.Response(text=json.dumps({"name": self.dataset.adaptername, "mqtt": self.dataset.mqtt, "logged": self.dataset.logged_lines, "native_size": self.dataset.getSizeOfNative(), "urls": urls}, default=self.date_handler))
        except:
            self.log.error('!! Error handling status request',exc_info=True)
    async def rootHandler(self, request):

        return web.Response(text=json.dumps(self.dataset.mqtt, default=self.date_handler))

    async def iconHandler(self, request):

        return web.Response(text="")
        
    async def retry_activation(self):
        try:
            await asyncio.sleep(20)                
            self.activated=await self.activate()
        except:
            self.log.error('!! error retrying activation')

    async def publish_adapter_device(self):
        try:
            url="http://%s:%s" % (self.serverAddress, self.port)
            device=devices.alexaDevice('%s/adapter/%s' % (self.dataset.adaptername, self.dataset.adaptername), self.dataset.adaptername, displayCategories=["ADAPTER"], adapter=self)
            device.AdapterHealth=devices.AdapterHealth(device=device, url=url)
            smartAdapter=self.dataset.newaddDevice(device)
            self.log.info('++ AddOrUpdateReport: %s (%s)' % (smartAdapter.friendlyName, smartAdapter.endpointId))
            await self.notify_event_gateway(smartAdapter.addOrUpdateReport)
        except:
            self.log.error('!! error publishing adapter', exc_info=True)

    async def hub_watchdog(self):
        try:
            while self.activated:
                url = '%s/status' % (self.dataset.baseConfig['hub_address'] )
                headers = { 'authorization': self.token }
                async with aiohttp.ClientSession() as client:
                    async with client.get(url, headers=headers) as response:
                        if response.status != 200:
                            self.log.info('.. hub monitor failed to reply on status update check. attempting to re-activate adapter.')
                            self.activated=False
                            break
                await asyncio.sleep(20)
            
            await self.activate()
        except aiohttp.client_exceptions.ClientConnectorError:
            await self.activate()
        except:
            self.log.error('!! error running watchdog', exc_info=True)

    async def hub_discovery(self):

        discovery_directive={   "directive": {
                                    "header": {
                                        "namespace": "Alexa.Discovery", 
                                        "name": "Discover", 
                                        "messageId": str(uuid.uuid1()),
                                        "payloadVersion": "3"
                                    },
                                    "payload": {
                                        "scope": {
                                            "type": "BearerToken",
                                            "token": "fake_temporary"
                                        }
                                    }
                                }
                            }


        try:
            if self.activated:
                headers = { 'authorization': self.token }
                async with aiohttp.ClientSession() as client:
                    async with client.post(self.dataset.baseConfig['hub_address'], data=json.dumps(discovery_directive), headers=headers) as response:
                        result=await response.read()
                        result=result.decode()
                        result=json.loads(result)
                        await self.adapter.updateDeviceList(result['event']['payload']['endpoints'])
                        self.log.info('.. discovered %s devices on hub @ %s' % (len(result['event']['payload']['endpoints']), self.dataset.baseConfig['hub_address']) )
        except:
            self.log.error('!! Error running discovery on hub: %s' % self.dataset.baseConfig['hub_address'] ,exc_info=True)
        
    async def activate(self):
        try:
            self.response_token=str(uuid.uuid1())
            if self.dataset.adaptername=="hub":
                self.log.info('.. activation not required for Hub adapter')
                return True
            if 'api_key' not in self.dataset.config:
                self.dataset.config['api_key']=str(uuid.uuid1())
                self.dataset.saveConfig()
            url = '%s/activate' % (self.dataset.baseConfig['apiGateway'] )
            data={ 'name':self.dataset.adaptername, 'response_token': self.response_token, 'api_key': self.dataset.config['api_key'], 'collector': self.collector, "categories": self.collector_categories, "type": "adapter", "url": "http://%s:%s" % (self.serverAddress, self.port) }

            self.log.info('>> Posting activation request to %s - %s' % (url, data))
            timeout = aiohttp.ClientTimeout(total=1)
            async with aiohttp.ClientSession(timeout=timeout) as client:
                async with client.post(url, json=data) as response:
                    if response.status == 200:
                        result=await response.read()
                        result=result.decode()
                        self.log.debug('.. activation response: %s' % result)
                        result=json.loads(result)
                        if 'token' in result:
                            self.log.info('.. received token: %s' % result['token'][-10:])
                            self.token=result['token']
                            self.dataset.token=result['token']
                            self.token_expires=datetime.datetime.strptime(result['expiration'], '%Y-%m-%dT%H:%M:%S.%f')
                            # supposedly supported in python 3.7 but does not seem to work in 3.7.3 on rpi
                            #self.token_expires=datetime.fromisoformat(result['expiration'])
                            self.activated=True
                            if self.collector:
                                asyncio.create_task(self.hub_discovery())    

                            asyncio.create_task(self.hub_watchdog())
                            return True
                        else:
                            self.log.debug('.. activation failed with response: %s' % result)
                    else:
                        self.log.error('.. activation failed with %s ' % response.status)

        except aiohttp.client_exceptions.ClientConnectorError:
            self.log.error('!! Error activating (could not connect)')
        except:
            self.log.error('!! Error activating', exc_info=True)
        try:
            asyncio.create_task(self.retry_activation())
        except:
            self.log.error('!! Error retrying activation', exc_info=True)        
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
                self.activated=await self.activate()
                if self.token_expires:
                    delta=(self.token_expires-datetime.datetime.now()).total_seconds()
                    expire_seconds=int(delta)
        except:
            self.log.error('error checking token expiration', exc_info=True)

    async def notify_event_gateway(self, data):
        try:
            if self.activated:
                await self.check_token_refresh()
            if self.token and self.activated:
                if self.dataset.adaptername=="hub":
                    self.log.info('.. activation not required for Hub')
                    return True
                url = self.dataset.baseConfig['eventGateway'] 
                headers = { 'authorization': self.token }
                async with aiohttp.ClientSession() as client:
                    async with client.post(url, json=data, headers=headers) as response:
                        if response.status == 200:
                            #self.log.info('>> event gateway: %s' % (self.adapter.alexa_json_filter(data)))
                            result=await response.read()
                            result=result.decode()
                            if result!="{}":
                                self.log.info('.. result: %s' % result)
                        elif response.status == 401:
                            self.log.info('.. error token is not valid: %s' % response.status)
                            self.activated=False
                            asyncio.create_task(self.activate())
                        else:
                            self.log.error('>! Error sending to event gateway: %s' % response.status, exc_info=True)
            #else:
            #    self.log.info('$$ did not forward to event gateway: %s %s' % (self.activated, self.token))
        except aiohttp.client_exceptions.ClientConnectorError:
            self.log.error('>! Error sending to event gateway (could not connect)', exc_info=True)
        except:
            self.log.error('.. error in event gateway notify', exc_info=True)


    def shutdown(self):
        #asyncio.ensure_future(self.serverApp.shutdown())
        asyncio.create_task(self.serverApp.shutdown())

    def __init__(self, port, loop, log=None, dataset={}, collector=False, categories=[]):
        self.port = port
        self.loop = loop
        self.workloadData={}
        self.log=log
        self.adapter=None
        self.dataset=dataset
        self.activated=False
        self.token=None
        self.response_token=None
        self.token_expires=0
        self.collector=collector
        self.url='http://%s:%s' % (self.dataset.baseConfig['restAddress'], self.dataset.config['rest_port'])
        self.collector_categories=categories

    

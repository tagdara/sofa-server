#!/usr/bin/python3
from sofabase3 import log_setup, SofaConfig, SofaBase, Discover, AddOrUpdateReport, Response, ErrorResponse, ReportState, DiscoveryResponse, alexa_json_filter, json_date_handler

import sys, os
import datetime
import json
import ssl
import uuid
import asyncio
import aiohttp
from aiohttp import web
import aiohttp_cors
from aiohttp_sse import sse_response
import copy
import concurrent.futures
from auth import api_consumer, Auth

from wakeonlan import send_magic_packet

logger = log_setup("eventgateway", level="INFO")


class EventGateway(SofaBase):

    #def __init__(self, api_consumers=None, adapters_not_responding=[], dataset=None, adapter=None, config=None):

    def add_adapter_fields(self):
        SofaConfig.add("web_address", mandatory=True)
        SofaConfig.add("web_port", default=6443)
        SofaConfig.add("token_secret", mandatory=True)
        SofaConfig.add("certificate", mandatory=True)
        SofaConfig.add("certificate_key", mandatory=True)
        SofaConfig.add("token_expires", default=604800)
        SofaConfig.add("error_threshold", default=20)
        SofaConfig.add("adapter_poll_time", default=60)        

    @property
    def caching_enabled(self):
        return True

    async def add_sofa_device(self, endpointId, path):
        #logger.info(f".. add sofa device (skipped) {endpointId} {path}")
        pass
        # figure out why this is even called

    async def pre_activate(self):
        self.dataset=self.sofa.dataset
        #self.dataset['adapters']={}
        self.api_consumers = self.loadJSON("api_consumers")
        self.imageCache={}
        self.adapterTimeout=2
        self.slow_post=2
        self.sse_updates=[]
        self.sse_last_update=datetime.datetime.now(datetime.timezone.utc)
        self.active_sessions={}
        self.pending_activations=[]
        self.rest_timeout = 8 # Alexa spec allows for 8 seconds https://developer.amazon.com/en-US/docs/alexa/device-apis/alexa-response.html
        self.conn = aiohttp.TCPConnector()
        self.adapters_not_responding=[]
        self.queued_for_state=[]
        self.adapter_semaphore = asyncio.Semaphore(value=20)
        self.directive_groups={}   
        self.device_adapter_map={}    
        self.cached_wol_endpoints=[] 
        self.recent_changes=[]
        self.recent_limit=25
        self.access_logging = False
        logger.info('.. loading cached endpoints')

        cached_devices = self.load_cache('event_gateway_device_cache')

        logger.info(f'.. cached endpoints: {len(cached_devices.keys())}')

        await self.add_endpoints_to_dataset(cached_devices.values(), skip_cache=True)

        logger.info('.. done loading')      

    async def initialize(self):

        try:
            self.auth=Auth(secret=SofaConfig.token_secret, token_expires=SofaConfig.token_expires)
            for consumer in self.api_consumers:
                api_consumer.objects.create(name=consumer, api_key=self.api_consumers[consumer]['api_key'])
            
            self.serverApp = aiohttp.web.Application(middlewares=[self.auth.middleware])
            
            self.serverApp.router.add_post('/', self.event_gateway_handler)
            self.serverApp.router.add_get('/status', self.status_handler)
            self.serverApp.router.add_post('/activate', self.activation_handler)
            self.serverApp.router.add_post('/refresh', self.activation_refresh_handler)
            self.serverApp.router.add_post('/activations/{cmd}', self.activation_approve_handler)
            self.serverApp.router.add_get('/activations', self.activations_handler)

            self.serverApp.router.add_get('/list/{list:.+}', self.listHandler)
            self.serverApp.router.add_post('/list/{list:.+}', self.listPostHandler)
            
            self.serverApp.router.add_post('/add/{add:.+}', self.adapterAddHandler)
            self.serverApp.router.add_post('/del/{del:.+}', self.adapterDelHandler)
            self.serverApp.router.add_post('/save/{save:.+}', self.adapterSaveHandler)
            
            self.serverApp.router.add_get('/image/{item:.+}', self.imageHandler)
            self.serverApp.router.add_get('/thumbnail/{item:.+}', self.imageHandler)

            #self.serverApp.router.add_get('/pending-activations', self.get_user)
            self.serverApp.router.add_get('/eventgateway/status', self.status_handler)   
            self.serverApp.router.add_post('/eventgateway/activate', self.activation_handler)
            self.serverApp.router.add_post('/eventgateway', self.event_gateway_handler)
            self.serverApp.router.add_post('/eventgateway/refresh_token', self.refresh_token_handler)
            # Add CORS support for all routes so that the development version can run from a different port
            self.cors = aiohttp_cors.setup(self.serverApp, defaults={
                "*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_methods='*', allow_headers="*") })

            for route in self.serverApp.router.routes():
                self.cors.add(route)

            self.runner=aiohttp.web.AppRunner(self.serverApp, access_log=self.access_logging)
            await self.runner.setup()

            self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            self.ssl_context.load_cert_chain(SofaConfig.certificate, SofaConfig.certificate_key)

            self.site = aiohttp.web.TCPSite(self.runner, SofaConfig.web_address, SofaConfig.web_port, ssl_context=self.ssl_context)
            await self.site.start()
            logger.info(f".. started event gateway at {SofaConfig.web_address}:{SofaConfig.web_port}")

        except:
            logger.error('!! Error intializing event gateway web server', exc_info=True)
            
    def login_required(func):
        def wrapper(self, request):
            if not request.api_consumer:
                raise web.HTTPUnauthorized()
            return func(self, request)
        return wrapper

    def json_response(self, body='', **kwargs):
        try:
            kwargs['body'] = json.dumps(body, default=self.date_handler).encode('utf-8')
            kwargs['content_type'] = 'application/json'
            return aiohttp.web.Response(**kwargs)
        except:
            logger.error('!! error with json response', exc_info=True)
            return aiohttp.web.Response({'body':''})

    async def loadData(self, jsonfilename):
        try:
            with open(os.path.join(SofaConfig.data_directory, '%s.json' % jsonfilename),'r') as jsonfile:
                return json.loads(jsonfile.read())
        except:
            logger.error('Error loading pattern: %s' % jsonfilename,exc_info=True)
            return {}

            
    def date_handler(self, obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        else:
            raise TypeError

    async def get_local_jwt(self, name, api_key):
        return await self.auth.get_token_from_api_key(name, api_key)

    # handler to authorize communication with adapters
    # Adapters should request a token from the api_code and name first, as this is no longer an unsecured request

    # When adapters first start, they send an activation request to hub to validate their connectivity and to send back response tokens and url information
    # This now also acts as the 'ready' state to let the event gateway know how and where to reach the adapter

    async def activation_handler(self, request):
        try:
            body=await request.read()
            data=json.loads(body.decode())
            if 'url' in data:
                data['activated'] = True
                data['last_seen'] = datetime.datetime.now().isoformat()
                await self.dataset.ingest({'adapters': { data['name'] : data }}, mergeReplace=True ) # Mergereplace prevents the categories list from duping
                
                if data['name'] in self.adapters_not_responding:
                    self.adapters_not_responding.remove(data['name'])
            
                logger.info(f"[< {data['name']} - activated at {data['url']} {data['response_token']}")
                return self.json_response({'activated': True})
            else:   
                already_pending=False
                for item in self.pending_activations:
                    if item['name']==data['name']:
                        already_pending=True
                        break
                    
                if not already_pending:
                    self.pending_activations.append(data)
                return self.json_response({'activated': 'pending'})
        except:
            logger.error('!! error with activation request', exc_info=True)
        return self.json_response({'activated': 'failed'})


    async def refresh_token_handler(self, request):
        try:
            body=await request.read()
            data=json.loads(body.decode())
            token = await self.auth.get_token_from_api_key(data['name'], data['api_key'])
            if token:
                expiration=datetime.datetime.now() + datetime.timedelta(seconds=(SofaConfig.token_expires-5))           
                logger.info(f"[> {data['name']} - refresh token valid until {expiration.isoformat()}")
                return self.json_response({'token': token, 'expiration': expiration.isoformat() })

        except:
            logger.error('!! error with refresh token request', exc_info=True)

        return self.json_response({'error': 'could not refresh token'})


    async def activation_refresh_handler(self, request):
        try:
            body=await request.read()
            data=json.loads(body.decode())
            #logger.info('.. activation request for %s' % data['name'])
            check=await self.auth.get_token_from_api_key(data['name'], data['api_key'])
            if check:
                expiration=datetime.datetime.now() + datetime.timedelta(seconds=(SofaConfig.token_expires-5))
                return self.json_response({'token': check, 'expiration': expiration.isoformat() })

        except:
            logger.error('!! error with activation request', exc_info=True)
        return self.json_response({'refresh': 'failed'})


    async def list_activations(self):
        try:
            logger.info('.. activations list request')
            obscured_keys=[]
            for pender in self.pending_activations:
                obscured_keys.append( { "name":pender['name'], "key": pender["api_key"][-6:] } )
                
            activated_keys=[]
            for approved in api_consumer.objects.all():
                activated_keys.append({ "name":approved.name, "key": approved.api_key[-6:]})
                logger.info('item: %s' % approved)
                
            return {"pending": obscured_keys, "activated": activated_keys}
        except:
            logger.error('!! error with activations list', exc_info=True)
        return []


    async def activations_handler(self, request):
        try:
            return self.json_response(await self.list_activations())
        except:
            logger.error('!! error with activations list handler', exc_info=True)
        return self.json_response([])


    async def status_handler(self, request):
        try:
            return self.json_response({"status": "up"})
            #return self.json_response({"status": "up", "data": self.sofa.dataset.devices})
        except:
            logger.error('!! error with status handler', exc_info=True)
        return self.json_response([])


    async def status_post_handler(self, request):
          
        result={} 
        if request.body_exists:
            try:
                result={}
                outputData={}
                body=await request.read()
                body=body.decode()
                logger.info('list post request: %s' % (body))
                #item="%s?%s" % (request.match_info['list'], request.query_string)
                item=request.match_info['list']
                source=item.split('/',1)[0] 
                if source in self.dataset.nativeDevices['adapters']:
                    result='#'
                    url = 'http://%s:%s/list/%s' % (self.dataset.nativeDevices['adapters'][source]['address'], self.dataset.nativeDevices['adapters'][source]['port'], item.split('/',1)[1] )
                    logger.info('>> Posting list request to %s %s' % (source, item.split('/',1)[1] ))
                    async with aiohttp.ClientSession() as client:
                        async with client.post(url, data=body) as response:
                            result=await response.read()
                            result=result.decode()
            except:
                logger.error('Error transferring command: %s' % body,exc_info=True)
        
        return self.json_response(result)


    async def activation_approve_handler(self, request):
        
        # This handler allows an admin to approve/remove new adapters and api keys.
        
        try:
            cmd=request.match_info['cmd']
            remove_pending=None
            body=await request.read()
            data=json.loads(body.decode())
            logger.info('cmd: %s' % cmd)

            if cmd=='approve':
                logger.info('.. activation approval for %s' % data['name'])
                for pender in self.pending_activations:
                    if pender['name']==data['name'] and pender['api_key'][-6:]==data['api_key']:
                        remove_pending=pender
                        api_consumer.objects.create(name=pender['name'], api_key=pender['api_key'])
                        self.api_consumers[pender['name']]={ "api_key": pender['api_key'] }
                        self.adapter.saveJSON('api_consumers',self.api_consumers)
                        break
                if remove_pending:
                    self.pending_activations.remove(remove_pending)
                    #return self.json_response({'activation': 'approved', "name":data['name'], "short_key":data['api_key']})

            if cmd=='remove':
                logger.info('.. activation removal for %s' % data['name'])
                if data['name'] in self.api_consumers:
                    api_consumer.objects.delete(name=data['name'])
                    self.adapter.saveJSON('api_consumers',self.api_consumers)
                    
        except:
            logger.error('!! error with activation approval request', exc_info=True)
        return self.json_response(await self.list_activations())

        
    async def logout_handler(self, request):
        return self.json_response({"loggedIn":False})  

            

    async def directivesHandler(self, request):
        try:
            #await check_permission(request, 'api')
            directives=await self.dataset.getAllDirectives()
            return self.json_response(directives)
        except:
            logger.error('Error with Directives Handler', exc_info=True)
            return self.json_response({'Error':True})

    async def eventsHandler(self, request):
        
        eventSources={ 'DoorbellEventSource': { "event": "doorbellPress"}}
        return self.json_response(eventSources)
        
        
    async def propertiesHandler(self, request):
        
        properties=await self.dataset.getAllProperties()
        return self.json_response(properties)
        

    async def listHandler(self, request):

        try:
            adapter_response={}
            item="%s?%s" % (request.match_info['list'], request.query_string)
            item=request.match_info['list']
            
            items=request.match_info['list'].split('/')
            
            #logger.info('~~ list: %s' % item)
            
            if items[0]=="devices":
                if len(items)>1:
                    return self.json_response(self.dataset.devices[items[1]])
                return self.json_response(self.dataset.devices)

            if items[0]=="deviceState":
                if len(items)>1:
                    return self.json_response(self.adapter.sofa.dataset.state_cache[items[1]])
            
            adapter_name=item.split('/',1)[0]
            if adapter_name=="hub":
                item='/'.join(request.match_info['list'].split('/')[1:])
                adapter_response=await self.adapter.virtualList(item, query=request.query_string)
                #logger.info('response: %s' % adapter_response)
            elif adapter_name in self.dataset.nativeDevices['adapters'] and self.dataset.nativeDevices['adapters'][adapter_name]['activated']:
                if self.dataset.nativeDevices['adapters'][adapter_name]['activated']:
                    url = '%s/list/%s' % (self.dataset.nativeDevices['adapters'][adapter_name]['url'], item.split('/',1)[1] )
                    response_token=self.dataset.nativeDevices['adapters'][adapter_name]['response_token']
                    adapter_response=await self.adapter_post(url, token=response_token, method='GET')
                else:
                    logger.error('>! %s - list request for %s (not activated)' % (request.api_consumer, adapter_name))
            else:
                logger.error('>! %s - list request for %s (unavailable)' % (request.api_consumer, adapter_name))
            return self.json_response(adapter_response)

        except aiohttp.client_exceptions.ClientConnectorError:
            logger.error('!! Connection refused for adapter %s.  Adapter is likely stopped' % adapter_name)

        except ConnectionRefusedError:
            logger.error('!! Connection refused for adapter %s.  Adapter is likely stopped' % adapter_name)
        except concurrent.futures._base.TimeoutError:
            logger.error('!! Error getting list data %s (timed out)' % item)
        except concurrent.futures._base.CancelledError:
            logger.error('!! Error getting list data %s (cancelled)' % item)
        except:
            logger.error('!! Error getting list data %s %s' % (request.__dict__, item), exc_info=True)
        
        return self.json_response({})
        

    async def listPostHandler(self, request):
          
        result={} 
        if request.body_exists:
            try:
                result={}
                outputData={}
                body=await request.read()
                body=body.decode()
                item=request.match_info['list']
                adapter_name=item.split('/',1)[0] 
                logger.info('>> %s list post request: %s' % (request.api_consumer, item))
                if adapter_name in self.dataset.nativeDevices['adapters']:
                    if self.dataset.nativeDevices['adapters'][adapter_name]['activated']:
                        result='#'
                        url = '%s/list/%s' % (self.dataset.nativeDevices['adapters'][adapter_name]['url'], item.split('/',1)[1] )
                        logger.info('<< Posting list request to %s %s' % (adapter_name, item.split('/',1)[1] ))
                        async with aiohttp.ClientSession() as client:
                            async with client.post(url, data=body) as response:
                                result=await response.read()
                                result=result.decode()
                                if type(result)==str:
                                    result=json.loads(result)
                    else:
                        logger.error('>! %s - list post request for %s (not activated)' % (request.api_consumer, adapter_name))
            except:
                logger.error('!! Error with list request: %s' % body,exc_info=True)
        
        return self.json_response(result)


    async def imageGetter(self, item, width=640, thumbnail=False):

        try:
            reqstart=datetime.datetime.now()
            source=item.split('/',1)[0] 
            if source in self.dataset.nativeDevices['adapters']:
                result='#'
                if thumbnail:
                    url = '%s/thumbnail/%s' % (self.dataset.nativeDevices['adapters'][source]['url'], item.split('/',1)[1] )
                else:
                    url = '%s/image/%s' % (self.dataset.nativeDevices['adapters'][source]['url'], item.split('/',1)[1] )
                
                async with aiohttp.ClientSession() as client:
                    async with client.get(url) as response:
                        result=await response.read()
                        if "{" in str(result)[:10]:
                            logger.info('.. error getting image %s: %s' % (item, result.decode()))
                        return result
                        #result=result.decode()
                        if str(result)[:10]=="data:image":
                            #result=base64.b64decode(result[23:])
                            self.imageCache[item]=str(result)
                            return result
        except aiohttp.client_exceptions.ServerDisconnectedError:
            logger.warning('.. image request failed after %s seconds for %s (Server Disconnect)' % ((datetime.datetime.now()-reqstart).total_seconds(), item))
        except aiohttp.client_exceptions.ClientOSError:
            logger.warning('.. image request failed after %s seconds for %s (Client Error/Connection Reset)' % ((datetime.datetime.now()-reqstart).total_seconds(), item))
        except concurrent.futures._base.CancelledError:
            logger.warning('.. image request cancelled after %s seconds for %s' % ((datetime.datetime.now()-reqstart).total_seconds(), item))
        except:
            logger.error('Error after %s seconds getting image %s' % ((datetime.datetime.now()-reqstart).total_seconds(), item), exc_info=True)
        return None


    async def imageHandler(self, request):

        try:
            fullitem=request.match_info['item']
            if request.query_string:
                fullitem="%s?%s" % (request.match_info['item'], request.query_string)
            #logger.info(f'image request {fullitem} ')
            #logger.info('.. image request: %s (%s)' % (fullitem, request.query_string))
            if fullitem in self.imageCache:
                logger.info('.. image from cache')
                result=base64.b64decode(self.imageCache[fullitem][23:])
                return aiohttp.web.Response(body=result, headers = { "Content-type": "image/jpeg" })
            
            if "width=" not in request.query_string or request.path.find('thumbnail')>0:
                result=await self.imageGetter(fullitem, thumbnail=True)
            else:
                result=await self.imageGetter(fullitem)

            return aiohttp.web.Response(body=result, headers = { "Content-type": "image/jpeg" })
            
            if str(result)[:10]=="data:image":
                result=base64.b64decode(result[23:])
                #result=base64.b64decode(result[23:])
                return aiohttp.web.Response(body=result, headers = { "Content-type": "image/jpeg" })
            
            logger.info('Did not get an image to return for %s: %s' % (request.match_info['item'], str(result)[:10]))
            return aiohttp.web.Response(content_type="text/html", body='')
        except:
            logger.error('Error with image handler', exc_info=True)


    async def adapterSaveHandler(self, request):

        try:    
            if request.body_exists:
                try:
                    outputData={}
                    body=await request.read()
                    #item="%s?%s" % (request.match_info['save'], request.query_string)
                    item=request.match_info['save']
                    logger.info('save: %s %s' % (item, body))
                    source=item.split('/',1)[0] 
                    if source in self.dataset.nativeDevices['adapters']:
                        result='#'
                        url = '%s/save/%s' % (self.dataset.nativeDevices['adapters'][source]['url'], item.split('/',1)[1] )
                        async with aiohttp.ClientSession() as client:
                            async with client.post(url, data=body) as response:
                                result=await response.read()
                                result=result.decode()
                                logger.info('resp: %s' % result)
                    
                except:
                    logger.error('Error transferring command: %s' % body,exc_info=True)
    
                return aiohttp.web.Response(text=result)
        except:
            logger.error('Error with save command',exc_info=True)


    async def adapterDelHandler(self, request):
            
        try:
            outputData={}   
            body=""
            if request.body_exists:
                body=await request.read()
            #item="%s?%s" % (request.match_info['del'], request.query_string)
            item=request.match_info['del']
            source=item.split('/',1)[0] 
            logger.info('.. delete request for %s %s %s' % (source, item, body))
            if source in self.dataset.nativeDevices['adapters']:
                result='#'
                url = '%s/del/%s' % (self.dataset.nativeDevices['adapters'][source]['url'], item.split('/',1)[1] )
                logger.info('Posting Delete Data to: %s' % url)
                async with aiohttp.ClientSession() as client:
                    async with client.post(url, data=body) as response:
                        result=await response.read()
                        result=result.decode()
                        logger.info('resp: %s' % result)
            
        except:
            logger.error('Error transferring command: %s' % body,exc_info=True)

        return aiohttp.web.Response(text=result)


    async def adapterAddHandler(self, request):
        result = {}
        if request.body_exists:
            body=""
            try:
                outputData={}
                body=await request.read()
                #item="%s?%s" % (request.match_info['add'], request.query_string)
                item=request.match_info['add']
                source=item.split('/',1)[0] 
                if source in self.dataset.nativeDevices['adapters']:
                    logger.info('.. preparing to send add to: %s' % self.dataset.nativeDevices['adapters'][source])
                    url = '%s/add/%s' % (self.dataset.nativeDevices['adapters'][source]['url'], item.split('/',1)[1] )
                    logger.info('<+ Posting Add Data to: %s' % url)
                    async with aiohttp.ClientSession() as client:
                        async with client.post(url, data=body) as response:
                            result = await response.read()
                            result = result.decode()
                            result = json.loads(result)
                            logger.info('+> %s add response: %s' % (source, result))
            except:
                logger.error('!+ Error transferring add command: %s' % body,exc_info=True)

        return self.json_response(result)



    async def hub_discovery(self, adapter_name, categories):
    
        # respond to discovery with list of local devices
        
        disco=[]
        try:
            for dev in self.dataset.devices:
                #if not self.dataset.devices[dev].hidden:
                if 'ALL' in categories or any(item in self.dataset.devices[dev]['displayCategories'] for item in categories):
                    try:
                        if self.adapter.device_adapter_map[dev] == adapter_name:
                            pass
                            #logger.info('~~ skipping device %s in discovery for owner adapter %s' % (dev,adapter_name))
                        else:
                            disco.append(self.dataset.devices[dev])
                    except KeyError:
                        pass
                        # When using cache, many devices will not have an adapter in the map initially
                        # we should probably also cache the map

                        #logger.warning('.! warning - unknown device %s / %s' % (dev, self.dataset.devices[dev]))
                    
            logger.info('<< %s Discover.Response %s devices filtered for %s' % (adapter_name, len(disco), categories) )
        except:
            logger.error('!! error in hub_discovery', exc_info=True)
            
        return DiscoveryResponse(endpoints=disco)

    # Event Gateway
  
    async def event_gateway_handler(self, request):
        
        response={}
        try:
            if request.body_exists:
                body=await request.read()
                data=json.loads(body.decode())
                if type(data)==str:
                    data=json.loads(data)

                try:
                    source=request.api_consumer
                except:
                    source=None

                response = await self.process_gateway_message(data, source)
                return web.Response(text=json.dumps(response, default=self.date_handler))
            else:
                logger.info('[< eg no body %s' % request)
        except TypeError:
            logger.error(f"!! error - bad gateway response {response}")
        except:
            logger.error('!! Error with event gateway',exc_info=True)
        return self.json_response({})
  

    def get_source_from_token(self, token):
        try:
            for consumer in self.api_consumers:
                if self.api_consumers[consumer]['api_key']==token:
                    return consumer
        except:
            logger.error('!! error getting source from token', exc_info=True)
        return None
 
        
    async def process_gateway_message(self, message, source=None):
        
        #  Processes message from the event gateway handler in the web server 
    
        try:
            if 'directive' in message:
                try:
                    if 'endpoint' in message['directive']:
                        token=message['directive']['endpoint']['scope']['token']
                    else:
                        token=message['directive']['payload']['scope']['token']
                    if not source:
                        source=self.get_source_from_token(token)
                except KeyError:
                    source=None
                    
                if not source:
                    logger.error(f'!! {source} missing or bad bearer token: {message}')
                    return {}

                if message['directive']['header']['name']=='Discover':
                    if not 'categories' in self.dataset.nativeDevices['adapters'][source]:
                        self.dataset.nativeDevices['adapters'][source]['categories'] ="ALL"
                    return await self.hub_discovery(source, self.dataset.nativeDevices['adapters'][source]['categories'])
                
                logger.debug(f'[< {source} {alexa_json_filter(message)}')
                return await self.process_gateway_directive(message, source=source)
                
            elif 'event' in message:
                # Everything that isn't a directive gets processed in an async task
                # logger.info(f'[< {source} {alexa_json_filter(message)}')
                asyncio.create_task(self.process_gateway_event(message, source=source))
                return {}
            else:
                logger.error(f'!! {source} no event or directive in message: {message}')
        
        except:
            logger.error(f'!! {source} error with process_gateway_message',exc_info=True)

        return ErrorResponse(endpointId, 'INTERNAL_ERROR', 'Did not recognize or could not process message')


    async def process_gateway_directive(self, data, source=None):
        try:
            if data['directive']['header']['name'] in ['CheckGroup','ReportStates']:
                endpointId=data['directive']['payload']['endpoints'][0]
            else:
                endpointId=data['directive']['endpoint']['endpointId']

            if endpointId not in self.dataset.devices and endpointId not in self.dataset.localDevices:
                logger.info('.. device not in dataset: %s %s %s' % (source, endpointId, data))
                return ErrorResponse(endpointId, 'NO_SUCH_ENDPOINT', 'hub could not locate this device in dataset')

            if endpointId not in self.adapter.device_adapter_map:
                if endpointId not in self.cached_wol_endpoints and not self.dataset.deviceHasCapability(endpointId, 'WakeOnLANController'):
                    logger.info('.. device not in adapter map: %s %s %s' % (source, endpointId, data))
                    return ErrorResponse(endpointId, 'NO_SUCH_ENDPOINT', 'hub could not locate this device in the adapter map')

            if 'cookie' in data['directive']['endpoint']:
                if 'groupKey' in data['directive']['endpoint']['cookie']:
                    groupKey=data['directive']['endpoint']['cookie']['groupKey']
                    groupCount=data['directive']['endpoint']['cookie']['groupCount']
                    
                    start=datetime.datetime.now()
                    if groupKey in self.directive_groups:
                        logger.debug('.. adding to Directive Group: %s/%s %s' % (groupKey, groupCount, data))
                    else:
                        logger.debug('.. new Directive Group: %s/%s %s' % (groupKey, groupCount, data))
                        self.directive_groups[groupKey]={ "count" : groupCount, "directives": [], "start": start, "adapter_group": {} }
                    self.directive_groups[groupKey]['directives'].append(data)

                    directive_adapter = self.adapter.device_adapter_map[endpointId]

                    if directive_adapter not in self.directive_groups[groupKey]['adapter_group']:
                        self.directive_groups[groupKey]['adapter_group'][directive_adapter]=[]
                    self.directive_groups[groupKey]['adapter_group'][directive_adapter].append(data)
                    
                    try:
                        while self.directive_groups[groupKey]['count'] > len(self.directive_groups[groupKey]['directives']) and (datetime.datetime.now()-self.directive_groups[groupKey]['start']).total_seconds() < 1:
                            await asyncio.sleep(0.01)
                    except KeyError:
                        pass

                    logger.debug('~~ All group commands received: %s in %s' % (groupKey, (datetime.datetime.now()-start).total_seconds() ))
            
                    for target_adapter in self.directive_groups[groupKey]['adapter_group'][directive_adapter]:
                        data['directive']['endpoint']['cookie']['groupCount']=len(self.directive_groups[groupKey]['adapter_group'][directive_adapter])
            
            if data['directive']['header']['name']=='TurnOn':
                # Intercept Wake on LAN for devices with that controller
                # This should return the deferred result and all of the Alexa model but for now just adds the WOL action
                if endpointId in self.cached_wol_endpoints or self.dataset.deviceHasCapability(endpointId, 'WakeOnLANController'):
                    logger.info(f'.. triggering WOL for TurnOn directive on device with WakeOnLANController: {endpointId}')
                    return await self.adapter.wake_on_lan(endpointId)
                    
            if endpointId in self.adapter.device_adapter_map and self.adapter.device_adapter_map[endpointId] in self.dataset.nativeDevices['adapters']:
                # Pass along directives to other adapters as necessary
                adapter_name=self.adapter.device_adapter_map[endpointId]
                
                if data['directive']['header']['name']=='ReportState':
                    if endpointId in self.adapter.sofa.dataset.state_cache:
                        correlationToken=data['directive']['header']['correlationToken']
                        logger.debug(f"[> {source} StateReport from cache for {endpointId}")
                        return await self.cached_state_report(endpointId, correlationToken=correlationToken)

                #if adapter_name in self.adapters_not_responding:
                    #asyncio.create_task( self.adapter.check_adapter_health(adapter_name))
                    #logger.warning('!< warning: %s requested data from non-responsive adapter: %s' % (source, adapter_name))
                #    logger.error(f"[> {source} ErrorResponse BRIDGE_UNREACHABLE - requested data from non-responsive adapter {adapter_name}")
                #    return ErrorResponse(endpointId, 'BRIDGE_UNREACHABLE', f'requested data from non-responsive adapter {adapter_name}')

                if not self.dataset.nativeDevices['adapters'][adapter_name]['activated']:
                    #logger.warning('~~ not activated: %s source: %s / %s' % (adapter_name, source, data['directive']['header']['name']))
                    logger.error(f"[> {source} ErrorResponse BRIDGE_UNREACHABLE - requested data from non-activated adapter {adapter_name}")
                    return ErrorResponse(endpointId, 'BRIDGE_UNREACHABLE', 'requested data from non-activated adapter')

                if "directive_url" in self.dataset.nativeDevices['adapters'][adapter_name]:
                    url=self.dataset.nativeDevices['adapters'][adapter_name]['directive_url']
                else:
                    url=self.dataset.nativeDevices['adapters'][adapter_name]['url']
                    
                if 'endpoint' in data['directive']['header']:
                    data['directive']['header']['endpoint']['token']=response_token
                    
                response_token=self.dataset.nativeDevices['adapters'][adapter_name]['response_token']

                if 'endpoint' in data['directive']:
                    data['directive']['endpoint']['scope']['token']=response_token
                else:
                    data['directive']['payload']['scope']['token']=response_token
                logger.debug(f"[> relay directive {source}>{adapter_name}")
                adapter_response=await self.adapter_post(url, data, token=response_token)
                logger.debug(f"[< relay response {adapter_name}<{source}: {adapter_response}")

                # cache result - should be refactored to not compete with handleStateReport
                try:
                    if adapter_response and adapter_response['event']['header']['name']=='StateReport':
                        endpointId=adapter_response['event']['endpoint']['endpointId']
                        self.adapter.sofa.dataset.state_cache[endpointId]={ "time": datetime.datetime.utcnow(), "properties" : adapter_response['context']['properties'] }
                except KeyError:
                    pass

                if data['directive']['header']['name']=='StateReport':
                    await self.adapter.handleStateReport(message, source=source)
                return adapter_response
            else:
                # This is a shim for the non-Alexa ReportStates (multi-report states)
                if data['directive']['header']['name'] =='ReportStates':
                    logger.warning('!! REPORTSTATES: %s' % data['directive']['payload']['endpoints'])
                    errors={}
                    for dev in data['directive']['payload']['endpoints']:
                        errors[dev]=ErrorResponse(dev, 'NO_SUCH_ENDPOINT', 'hub could not locate this device')
                    return errors
                    
                if endpointId in self.dataset.devices:
                    return ErrorResponse(endpointId, 'BRIDGE_UNREACHABLE', 'requested data from non-responsive adapter')
                    
                return ErrorResponse(endpointId, 'NO_SUCH_ENDPOINT', 'hub could not locate this device')
            
        except:
            logger.error('!! error finding endpoint', exc_info=True)
            
        logger.error(f"!! {source} error dealing with directive {data}")
        return ErrorResponse(endpointId, 'INTERNAL_ERROR', 'hub failed to process gateway directive')


    async def process_gateway_event(self, message, source=None):
            
        try:
            if 'correlationToken' in message['event']['header']:
                pass
                # TODO/CHEESE it is unclear whether we actually still use pending requests or not, although the async event gateway
                # behavior would require something like this
                # even if it is still needed, it is unclear why it would be part of the rest of the if statement since this would
                # effectively ignore the result unless its picked up elsewhere

                #try:
                #    if message['event']['header']['correlationToken'] in self.pendingRequests:
                #        self.pendingResponses[message['event']['header']['correlationToken']]=message
                #        self.pendingRequests.remove(message['event']['header']['correlationToken'])
                #except:
                #    logger.error('Error handling a correlation token response: %s ' % message, exc_info=True)

            if message['event']['header']['name']=='DoorbellPress':
                if message['event']['endpoint']['endpointId'].split(":")[0]!=self.dataset.adaptername:
                    if hasattr(self.adapter, "handleAlexaEvent"):
                        await self.adapter.handleAlexaEvent(message, source=source)
        
            elif message['event']['header']['name']=='StateReport':
                if hasattr(self.adapter, "handleStateReport"):
                    await self.adapter.handleStateReport(message, source=source)

            elif message['event']['header']['name']=='ChangeReport':
                await self.handle_change_report(message, source=source)

            elif message['event']['header']['name']=='DeleteReport':
                if hasattr(self.adapter, "handleDeleteReport"):
                    await self.adapter.handleDeleteReport(message, source=source)
            
            elif message['event']['header']['name']=='AddOrUpdateReport':
                await self.handle_addorupdate_report(message, source=source)
            
            else:
                logger.warning('.! gateway message type not processed: %s' % message)
                    
        except:
            logger.error('!! Error processing gateway message: %s' % message, exc_info=True)

    # New message distribution system that scans events and forwards them via rest to collector adapters
    
    async def send_collector_addorupdate(self, adapter_name, device_list):
        if adapter_name not in self.dataset.nativeDevices['adapters'] or 'categories' not in self.dataset.nativeDevices['adapters'][adapter_name]:
            return False

        adapter_categories = self.dataset.nativeDevices['adapters'][adapter_name]['categories']
        adapter_endpoints = []

        for item in device_list:
            device = self.dataset.getDeviceByEndpointId(item['endpointId'])    
            if 'ALL' in adapter_categories or any(item in device['displayCategories'] for item in adapter_categories):
                adapter_endpoints.append(item)

        if len(adapter_endpoints)>0:
            short_items = [x['endpointId'] for x in adapter_endpoints]
            logger.debug(f'>> Adding {len(short_items)} {short_items} to {adapter_name}')
            updated_message = AddOrUpdateReport(adapter_endpoints)
            response_token = self.dataset.nativeDevices['adapters'][adapter_name]['response_token']
            asyncio.create_task(self.adapter_post(self.dataset.nativeDevices['adapters'][adapter_name]['url'], updated_message, token = response_token))


    async def add_collector_update(self, message, source=None):
        try:
            for adapter_name in self.dataset.nativeDevices['adapters']:
                if not self.dataset.nativeDevices['adapters'][adapter_name]['activated']:
                    continue
                if 'collector' not in self.dataset.nativeDevices['adapters'][adapter_name] or not self.dataset.nativeDevices['adapters'][adapter_name]['collector']:
                    continue
                if len(self.dataset.nativeDevices['adapters'][adapter_name]['categories'])==0:
                    continue
                if adapter_name == 'hub' or adapter_name == source:
                    continue
                
                device={}

                try:
                    if message['event']['header']['name']=='AddOrUpdateReport':
                        await self.send_collector_addorupdate(adapter_name, message['event']['payload']['endpoints'])

                    elif message['event']['header']['name']=='DeleteReport':
                        # TODO/CHEESE - Delete reports do not contain categories and the device seems like it might have been already deleted
                        # from the dataset, so send all delete messages to all adapters in the meantime
                        adapter_endpoints=[]
                        for item in message['event']['payload']['endpoints']:
                            #device=self.dataset.getDeviceByEndpointId(item['endpointId'])    
                            #if 'ALL' in self.dataset.nativeDevices['adapters'][adapter]['categories'] or any(item in device['displayCategories'] for item in self.dataset.nativeDevices['adapters'][adapter]['categories']):
                            
                            # TODO/CHEESE - Delete reports do not contain categories and the device seems like it might have been already deleted
                            # from the dataset, so send all delete messages to all adapters in the meantime
                            adapter_endpoints.append(item)
                        if len(adapter_endpoints)>0:
                            #logger.info('>> Adding %s devices to %s' % (len(adapter_endpoints), adapter))
                            updated_message=dict(message)
                            updated_message['event']['payload']['endpoints']=adapter_endpoints
                            response_token = self.dataset.nativeDevices['adapters'][adapter_name]['response_token']
                            asyncio.create_task(self.adapter_post(self.dataset.nativeDevices['adapters'][adapter]['url'], updated_message, token=response_token))
                    
                    elif 'endpoint' in message['event']:
                        if source == adapter_name:  # This check has to bypass AddOrUpdate to avoid device list gaps where local devices don't get added 
                            continue
                        device=self.dataset.getDeviceByEndpointId(message['event']['endpoint']['endpointId'], as_dict=True)
                        if not device:
                            #logger.warning('.. warning: did not find device for %s : %s' % (message['event']['endpoint']['endpointId'], message['event']['header']['name']))
                            break
                        else:
                            try:
                                if 'ALL' in self.dataset.nativeDevices['adapters'][adapter_name]['categories'] or any(item in device['displayCategories'] for item in self.dataset.nativeDevices['adapters'][adapter_name]['categories']):
                                    asyncio.create_task(self.adapter_post(self.dataset.nativeDevices['adapters'][adapter_name]['url'], message, token=self.dataset.nativeDevices['adapters'][adapter_name]['response_token']))
                            except:
                                logger.error('!! error adding collector update - %s v %s' % (self.dataset.nativeDevices['adapters'][adapter_name],device ), exc_info=True)
                    else:
                        logger.warning('.! warning: no endpoint in %s' % message)
                    
                except:
                    logger.error('!! error with acu: %s' % adapter_name, exc_info=True)

        except concurrent.futures._base.CancelledError:
            logger.error('!! Error updating collectors (cancelled)', exc_info=True)
        except:
            logger.error('!! Error updating collectors', exc_info=True)


    async def remove_adapter_activation_by_url(self, url, token):
        try:
            for adapter in self.dataset.nativeDevices['adapters']:
                if self.dataset.nativeDevices['adapters'][adapter]['url']==url and self.dataset.nativeDevices['adapters'][adapter]['response_token']==token:
                    logger.info('.. retracting bad adapter activation token: %s %s' % (self.dataset.nativeDevices['adapters'][adapter]['name'],token))
                    await self.dataset.ingest({"adapters": { adapter : { 'activated':False, 'response_token':None }}})
                    
                    break
        except:
            logger.error("!. Error removing adapter activation for %s" % url, exc_info=True)
            
            
    async def adapter_post(self, url, data={}, headers={ "Content-type": "text/xml" }, token=None, adapter='', method="POST"):  
        
        result = {}
        try:
            start_token = str(token)
            request_id=uuid.uuid1()
            adapter_name=self.adapter_name_from_url(url)
 
            #if self.adapter_name_from_url(url) in self.adapters_not_responding:
            #    #logger.error("!. Error - Request for adapter that is offline: %s %s %s %s" % (self.adapter_name_from_url(url), url, headers, data))
            #    asyncio.create_task(self.adapter.check_adapter_health(self.adapter_name_from_url(url)))
            #    return await self.post_error_response(data)
                
            if not self.dataset.nativeDevices['adapters'][adapter_name]['activated']:
                #logger.error("!! error - adapter not activated for %s %s %s" % (adapter_name, url, data))
                return await self.post_error_response(data, source=adapter_name)
                
            if not token:
                logger.error("!! error - no token provided for %s %s %s" % (self.adapter_name_from_url(url), url, data))
                return await self.post_error_response(data, source=adapter_name)

            if not url:
                logger.error('!! Error sending rest/post - no URL for %s' % data)
                return {}

            if method not in ['POST','GET']:
                logger.error('!! unknown method: %s' % method)
                return {}
            
            headers['authorization']=token


            #logger.info('1 token %s vs headers %s' % (token, headers))
            timeout = aiohttp.ClientTimeout(total=self.rest_timeout)
            jsondata=json.dumps(data)
            #logger.info('Adapter post: %s %s' % (url, data))
            # TODO/CHEESE - Using this semap
            
            #async with self.adapter_semaphore:
            if 1==1:
                if token != headers['authorization']:
                    logger.info('AAAAAAAAAAAAAAAA token %s vs headers %s vs start %s' % (token, headers, start_token))

                async with aiohttp.ClientSession(connector=self.conn, connector_owner=False, timeout=timeout) as client:
                    poststart=datetime.datetime.now()
                    if token != headers['authorization']:
                        logger.info('!!!!!!!!!!!!!!!!! token %s vs headers %s vs start %s' % (token, headers, start_token))

                    #logger.info('-> %s %s %s %s %s %s %s %s' % (adapter_name, request_id,  token, url, data, headers, adapter, method))

                    if method=='POST':
                        response=await client.post(url, data=jsondata, headers=headers)
                    elif method=='GET':
                        response=await client.get(url, headers=headers)
                    
                    #logger.info('-> %s' % response)
                    #self.adapter_semaphore.release()
                    postend=datetime.datetime.now()
                    if response.status == 200:
                        #logger.info('>> event gateway: %s' % (self.adapter.alexa_json_filter(data)))
                        if self.adapter_name_from_url(url) in self.adapters_not_responding:
                            logger.info('.. removing adapter %s on status code %s from not responding list: %s' % (self.adapter_name_from_url(url), response.status, self.adapters_not_responding))
                            self.adapters_not_responding.remove(self.adapter_name_from_url(url))
                            
                        result = await response.read()
                        #logger.info('adapter response: %s' % result)
                    elif response.status == 401:
                        #logger.info('3 token %s vs headers %s' % (token, headers))
                        logger.error('.. error response token is not valid: %s [%s] %s' % (self.adapter_name_from_url(url), token, headers))
                        #logger.info('XXXXX %s %s %s %s %s %s %s' % (request_id,  token, url, data, headers, adapter, method))

                        await self.remove_adapter_activation_by_url(url, token)
                        return ErrorResponse(None, "INVALID_AUTHORIZATION_CREDENTIAL", "response was not valid or expired")

                    elif response.status == 500:
                        #await self.remove_adapter_activation_by_url(url, token)
                        logger.error('>! Error sending to %s %s (500 remote adapter internal error)' % (adapter, url))
                        return ErrorResponse(None, "INTERNAL_ERROR", f"adapter {adapter} internal error")
                    else:
                        #await self.remove_adapter_activation_by_url(url, token)
                        logger.error('>! Error sending to adapter: %s %s' % (url, response.status))
                        return ErrorResponse(None, "INTERNAL_ERROR", f"Unknown HTTP Response code: {response.status}")

                    try:
                        posttime = (postend-poststart).total_seconds()
                        if posttime>self.slow_post:
                            logger.info('.! slow adapterpost: %s %s / datasize: %s<>%s / runtime: %s / %s ' % (self.adapter_name_from_url(url), url, len(jsondata), len(result), posttime, alexa_json_filter(data)))
                        if len(result.decode()) == 0:
                            return {}
                        json_result = json.loads(result.decode())
                        #jsonresult['adapterpost']={ "url": url, "runtime": (datetime.datetime.now()-reqstart).total_seconds() }
                        return json_result
                    except:
                        return ErrorResponse(None, "INTERNAL_ERROR", f"Bad JSON response: {result}")

                return ErrorResponse(None, "INTERNAL_ERROR", f"An unknown error occurred during message processing")
        
        except asyncio.exceptions.TimeoutError:
            if self.adapter_name_from_url(url) not in self.adapters_not_responding:
                logger.error("!. Error - Timeout in rest post to %s: %s %s" % (self.adapter_name_from_url(url), url, data))
            result = ErrorResponse(None, "INTERNAL_ERROR", f"Timeout in rest post {self.adapter_name_from_url(url)}")
        except asyncio.exceptions.CancelledError:
            if self.adapter_name_from_url(url) not in self.adapters_not_responding:
                logger.error("!. Error - Cancelled rest post to %s: %s %s %s" % (self.adapter_name_from_url(url), url, headers, alexa_json_filter(data)))
            result = ErrorResponse(None, "INTERNAL_ERROR", f"Cancelled during rest post {self.adapter_name_from_url(url)}")
        except aiohttp.client_exceptions.ClientConnectorError:
            if self.adapter_name_from_url(url) not in self.adapters_not_responding:
                logger.error("!. Error - adapter post failed to %s %s %s" % (self.adapter_name_from_url(url), url, alexa_json_filter(data)))
            result = ErrorResponse(None, "INTERNAL_ERROR", f"Client connector error {self.adapter_name_from_url(url)}")
        except aiohttp.client_exceptions.ClientOSError:
            if self.adapter_name_from_url(url) not in self.adapters_not_responding:
                logger.error("!. Error - adapter post failed to %s %s %s (Client OS Error / Connection reset by peer)" % (self.adapter_name_from_url(url), url, alexa_json_filter(data)))
            result = ErrorResponse(None, "INTERNAL_ERROR", f"Client OS error {self.adapter_name_from_url(url)}")
        except ConnectionRefusedError:
            if self.adapter_name_from_url(url) not in self.adapters_not_responding:
                logger.error('!. Connection refused for adapter %s %s. %s %s' % (self.adapter_name_from_url(url), url, data, str(e)))     
            result = ErrorResponse(None, "INTERNAL_ERROR", f"Connection refused by {self.adapter_name_from_url(url)}")
        except:
            if self.adapter_name_from_url(url) not in self.adapters_not_responding:
                logger.error("!. Error requesting state: %s" % data,exc_info=True)
            result = ErrorResponse(None, "INTERNAL_ERROR", f"Unknown error requesting state {self.adapter_name_from_url(url)}")    
        if self.adapter_name_from_url(url) not in self.adapters_not_responding:
            logger.warning('!+ adapter %s added to not responding list' % self.adapter_name_from_url(url) )
            self.adapters_not_responding.append(self.adapter_name_from_url(url))
            #await self.adapter.check_adapter_health(self.adapter_name_from_url(url))
        return result
    
    async def post_error_response(self, data, source=None):
        try:
            if 'directive' in data:
                if data['directive']['header']['name']!="Discover":
                    endpointId=data['directive']['endpoint']['endpointId']
                    return ErrorResponse(endpointId, 'BRIDGE_UNREACHABLE', f'hub cannot reach adapter {source}')
                else:
                    logger.error('!! need error response for discovery', exc_info=True)
        except:
            logger.info('.. error sorting post error', exc_info=True)
        return {}      
        
    def adapter_name_from_url(self, url):
        try:
            for adp in self.dataset.nativeDevices['adapters']:
                if url.startswith(self.dataset.nativeDevices['adapters'][adp]['url']):
                    return adp
        except:
            logger.error('!. error getting adapter from url %s' % url)
        return None

    def loadJSON(self, jsonfilename):
        
        try:
            with open(os.path.join(SofaConfig.config_directory, '%s.json' % jsonfilename),'r') as jsonfile:
                return json.loads(jsonfile.read())
        except FileNotFoundError:
            logger.error('!! Error loading json - file does not exist: %s' % jsonfilename)
            return {}
        except:
            logger.error('Error loading pattern: %s' % jsonfilename,exc_info=True)
            return {}

            
    def saveJSON(self, jsonfilename, data):
        
        try:
            jsonfile = open(os.path.join(SofaConfig.config_directory, '%s.json' % jsonfilename), 'wt')
            json.dump(data, jsonfile, ensure_ascii=False, default=self.date_handler)
            jsonfile.close()

        except:
            logger.error('Error saving json: %s' % jsonfilename,exc_info=True)
            return {}

    def load_cache(self, filename, json_format=True):
        
        try:
            if json_format:
                filename="%s.json" % filename
            with open(os.path.join(SofaConfig.cache_directory, filename),'r') as cachefile:
                if json_format:
                    return json.loads(cachefile.read())
                else:
                    return cachefile.read()
        except FileNotFoundError:
            logger.error('!! Error loading cache - file does not exist: %s' % filename)
            return {}
        except:
            logger.error('Error loading cache: %s' % filename,exc_info=True)
            return {}


    def save_cache(self, filename, data, json_format=True):
        
        try:
            if json_format:
                filename="%s.json" % filename
            cachefile = open(os.path.join(SofaConfig.cache_directory, filename), 'wt')
            if json_format:
                json.dump(data, cachefile, ensure_ascii=False, default = json_date_handler)
            else:
                cachefile.write(data)
            cachefile.close()
        except:
            logger.error('Error saving cache to %s' % filename, exc_info=True)


    async def add_endpoints_to_dataset(self, endpoints, skip_cache=False):

        # Take endpoints from a discovery or AddOrUpdate report and merge them into the dataset, replacing any existing
        # object with the same endpointId
        
        for endpoint in endpoints:
            self.dataset.devices[ endpoint['endpointId'] ] = endpoint

        # Newly discovered devices should be tested again to see if they are unreachable
        if endpoint['endpointId'] in self.dataset.unreachable_devices:
            self.dataset.unreachable_devices.remove(endpoint['endpointId'])

        # If caching is enabled save these devices so that they are present after a restart and before the 
        # adapter has activated
        if self.caching_enabled and not skip_cache:
            self.save_cache(f'{SofaConfig.adapter_name}_device_cache', self.dataset.devices)


    async def request_report_states(self, endpoints, source=None):

        # After endpoints are added or replaced in the dataset, we need to request the state of the endpoint
        logger.info(f">> {source} requesting report states for {len(endpoints)} devices")
        for endpoint in endpoints:
            response_token = self.get_response_token_from_endpointId(endpoint['endpointId'])
            asyncio.create_task(self.request_report_state(endpoint['endpointId'], bearerToken = response_token))


    async def handle_addorupdate_report(self, message, source=None):

        try:
            endpoints = message['event']['payload']['endpoints']
            await self.add_endpoints_to_dataset(endpoints)

            logger.info(f'++ {source} AddOrUpdate {len(endpoints)} devices Now {len(self.dataset.devices)} total devices.')

            if self.caching_enabled:
                await self.request_report_states(endpoints, source=source)

            if source:
                await self.update_device_adapter_map(source, endpoints)
                await self.add_collector_update(message, source=source)

        except:
            logger.error(f'!! error handling AddorUpdate: {message}', exc_info=True)


    async def handle_change_report(self, message, source=None):
        try:
            logger.debug('<< changereport from %s: %s' % (source, message))
            #await super().handleChangeReport(message)
            if message:
                if self.sofa.caching_enabled:
                    try:
                        endpointId=message['event']['endpoint']['endpointId']
                        self.sofa.dataset.state_cache[endpointId]={ "time": datetime.datetime.utcnow(), "properties" : list(message['context']['properties']) }
                        #self.state_cache[endpointId]=list(message['context']['properties'])
                        for prop in message['event']['payload']['change']['properties']:
                            self.sofa.dataset.state_cache[endpointId]['properties'].append(prop)
                        #logger.info('~~ Change report cached for %s: %s' % (endpointId, self.state_cache[endpointId]))
                    except:
                        logger.error("!! Error caching state from change report", exc_info=True)

                try:
                    await self.add_collector_update(message, source=source)
                    await self.add_to_recent(message)

                except:
                    logger.warn('!. bad or empty ChangeReport message not sent to SSE: %s' % message, exc_info=True)
        except:
            logger.error('Error updating from change report', exc_info=True)


    async def update_device_adapter_map(self, adapter_name, endpoints):
        try:
            #logger.info(f'.. updating device adapter map {adapter_name} {endpoints}')
            new_map_items=False
            endpoint_list=[]
            for item in endpoints:
                endpoint_list.append(item['endpointId'])
                if item['endpointId'] not in self.device_adapter_map or self.device_adapter_map[item['endpointId']]!=adapter_name:
                    new_map_items=True
                    self.device_adapter_map[item['endpointId']]=adapter_name
            
            dead_devices=[]
            for existing in self.device_adapter_map:
                if self.device_adapter_map[existing]==adapter_name and existing not in endpoint_list:
                    #logger.info('~~ found likely dead device: %s %s %s' % (existing, adapter_name, endpoint_list))
                    dead_devices.append(existing)
                    new_map_items=True
                    
            for dead in dead_devices:     
                if dead in self.device_adapter_map:               
                    del self.device_adapter_map[dead]
                if dead in self.sofa.dataset.devices:
                    del self.sofa.dataset.devices[dead]
                    
                
            if new_map_items:
                self.save_cache('adapter_map', self.device_adapter_map)
        except:
            logger.error('!! error updating device adapter map', exc_info=True)

    def get_response_token_from_endpointId(self, endpointId):
        try:
            adapter_name = self.get_adapter_from_endpointId(endpointId)
            if not adapter_name:
                return None
            if adapter_name in self.dataset.nativeDevices['adapters']:
                response_token = self.dataset.nativeDevices['adapters'][adapter_name]['response_token']
                return response_token
        except:
            logger.error('!! error getting response token for %s' % endpointId, exc_info=True)
        return None

    def get_url_from_endpointId(self, endpointId):
        try:
            adapter_name = self.get_adapter_from_endpointId(endpointId)
            if not adapter_name:
                return None
            if adapter_name in self.dataset.nativeDevices['adapters']:
                #logger.info(f"adapter data: {self.dataset.nativeDevices['adapters'][adapter_name]}")
                url = self.dataset.nativeDevices['adapters'][adapter_name]['url']
                return url
        except:
            logger.error(f'!! error getting url for {endpointId}', exc_info=True)
        return None

    def get_adapter_from_endpointId(self, endpointId):
        try:
            if not hasattr(self, 'device_adapter_map'):
                #logger.info('.. this is not a hub')
                return None
            if endpointId in self.device_adapter_map:
                adapter_name=self.device_adapter_map[endpointId]
                #logger.info('got adapter from map: %s %s' % (endpointId, adapter_name))
                return adapter_name
        except:
            logger.error('!! error getting adapter from endpoint %s' % endpointId, exc_info=True)
        try:
            return discovered_device.split(':')[0]
        except:
            pass
        return None

    async def handle_state_report(self, message, source=None):
        if self.caching_enabled:
            try:
                if message['event']['header']['name']!='StateReport':
                    logger.error("!! non-statereport sent to state report handler: %s %s" % ( message['event']['header']['name'], message))
                    return False
                endpointId=message['event']['endpoint']['endpointId']
                self.dataset.state_cache[endpointId]={ "time": datetime.datetime.utcnow(), "properties" : message['context']['properties'] }
            except:
                logger.error("!! Error caching statereport %s" % message, exc_info=True)

    async def add_to_recent(self, message):
        try:
            #if message['event']['endpoint']['endpointId'].find('pc')>-1:
            #    logger.info('<+ pc change report: %s' % message )
            self.recent_changes.append(message)
            self.recent_changes=self.recent_changes[-1*self.recent_limit:]
        except:
            logger.error('Error getting virtual list for %s' % itempath, exc_info=True)


    async def request_report_state(self, endpointId, correlationToken='', bearerToken=None, cookie={}):
        
        try:
            # This version is modified for event_gateway and does not check for local devices since the gateway
            # should not host any

            if endpointId not in self.dataset.devices:
                logger.info(f'.. requested ReportState for unknown device: {endpointId}')
                return ErrorResponse(endpointId, "NO_SUCH_ENDPOINT", "This device does not exist %s" % endpointId)

            if endpointId in self.dataset.unreachable_devices:
                logger.info('.. requested ReportState for previously unreachable device: %s' % endpointId)
                return ErrorResponse(endpointId, "ENDPOINT_UNREACHABLE", "This device is currently unreachable %s" % endpointId)
                
            if bearerToken==None:
                bearerToken = self.get_response_token_from_endpointId(endpointId)

            if bearerToken==None:
                adapter_name = self.adapter.device_adapter_map.get(endpointId, "unknown")
                logger.info(f'!! No response token: adapter {adapter_name} - {endpointId}')
                return ErrorResponse(None, "INVALID_AUTHORIZATION_CREDENTIAL", f"No response token: adapter {adapter_name} - {endpointId}")

            if not correlationToken:
                correlationToken=str(uuid.uuid1())

            url = self.get_url_from_endpointId(endpointId)
            
            reportState = ReportState(endpointId, correlationToken=correlationToken, bearerToken=bearerToken, cookie=cookie)
            statereport = await self.adapter.sofa.rest_client.send(url=url, data = reportState, method="post", token=bearerToken)
                
            # correlationToken will likely change if it passes through the gateway
            if statereport and 'correlationToken' in statereport['event']['header']:
                statereport['event']['header']['correlationToken'] = correlationToken
                
            if statereport and statereport['event']['header']['name']=='ErrorResponse':
                #logger.debug('!! ErrorResponse received from ReportState: %s' % statereport)
                if endpointId not in self.dataset.unreachable_devices:
                    self.dataset.unreachable_devices.append(endpointId)

                if statereport['event']['payload']['type']=="INVALID_AUTHORIZATION_CREDENTIAL":
                    adapter_name = self.device_adapter_map.get(endpointId, "")
                    logger.error(f"!! error statereport {endpointId} - incorrect reponse token for {adapter_name} {bearerToken}")

                if statereport['event']['payload']['type']=='NO_SUCH_ENDPOINT':
                    endpointId = statereport['event']['endpoint']['endpointId']
                    if endpointId in self.dataset.devices:
                        del self.dataset.devices[endpointId]
                    await self.handle_error_response(statereport)
                    
                return statereport
                
            if statereport:
                await self.handle_state_report(statereport)
                return statereport
            
            logger.warning('.! No State Report returned for %s' % endpointId)            
            return {}

        except concurrent.futures._base.TimeoutError:
            logger.error("!! Error requesting state for %s (timeout)" % endpointId,exc_info=True)

        except KeyError:
            logger.error(f"!! Error requesting state for {endpointId} and report format error in {statereport}",exc_info=True)

        except:
            logger.error("!! Error requesting state for %s" % endpointId,exc_info=True)
        
        return {}


    async def cached_state_report(self, endpointId, correlationToken=None):
        try:
            response={ 
                'event': {
                    'header': {
                        'name': 'StateReport', 
                        'payloadVersion': '3', 
                        'messageId': str(uuid.uuid1()), 
                        'namespace': 'Alexa'
                    },
                    'endpoint': {
                        'endpointId': endpointId,
                        'scope': {'type': 'BearerToken', 'token': ''}, 
                        'cookie': {}
                    }
                }
            }
            
            if correlationToken:
                response['event']['header']['correlationToken']=correlationToken
                
            response['context']={ "properties" : self.dataset.state_cache[endpointId]['properties'] }
            return response
        except:
            logger.error('!! error generating cached state report %s' % endpointId, exc_info=True)
        return {}


    async def wake_on_lan(self, endpointId, correlationToken=None):
        
        try:
            if endpointId in self.cached_wol_endpoints:
                macs = self.cached_wol_endpoints[endpointId]
            
            elif self.dataset.deviceHasCapability(endpointId, 'WakeOnLANController'):
                for devcap in self.dataset.devices[endpointId]['capabilities']:
                    if devcap['interface']=='Alexa.WakeOnLANController':
                        macs=devcap['configuration']['MACAddresses']
            if macs:
                for mac in macs:
                    logger.info(f'.. sending wake on lan to {endpointId} - {mac}')
                    #mac.replace(':','.')
                    for x in range(1, 10, 1):
                        send_magic_packet(mac.replace(':','.'))
                        asyncio.sleep(0.1)
                    response = Response(endpointId, {}, correlationToken=correlationToken, controller="WakeOnLANController")
                    logger.info(f"WOL response: {response}")
                    return response

        except:
            logger.error(f'Error sending wake on lan for {endpointId}', exc_info=True)

        return ErrorResponse(endpointId, 'INTERNAL_ERROR', f'hub could not send wake-on-lan to {endpointId}')


if __name__ == '__main__':
    event_gateway = EventGateway(name='event_gateway', gateway=True)
    event_gateway.start()
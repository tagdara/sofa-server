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
            
            self.serverApp.router.add_get('/image/{item:.+}', self.imageHandler)
            self.serverApp.router.add_get('/thumbnail/{item:.+}', self.thumbnailHandler)
            self.serverApp.router.add_get('/list/{list:.+}', self.listHandler)
            self.serverApp.router.add_post('/list/{list:.+}', self.listPostHandler)

            self.serverApp.router.add_get('/var/{list:.+}', self.varHandler)
            
            self.serverApp.router.add_post('/save/{save:.+}', self.saveHandler)
            self.serverApp.router.add_post('/add/{add:.+}', self.addHandler)
            self.serverApp.router.add_post('/del/{del:.+}', self.delHandler)            
            
            self.serverApp.router.add_get('/{category}', self.categoryLookupHandler)
            self.serverApp.router.add_get('/{category}/{item:.+}', self.itemLookupHandler)

            self.runner=aiohttp.web.AppRunner(self.serverApp)
            self.loop.run_until_complete(self.runner.setup())

            self.site = web.TCPSite(self.runner, self.serverAddress, self.port)
            self.loop.run_until_complete(self.site.start())
        except:
            self.log.error('Error starting REST server', exc_info=True)



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
            lookup=self.dataset.getDeviceByfriendlyName(dev).StateReport()

            #lookup=self.dataset.localDevices[urllib.parse.unquote(request.match_info['item'])].StateReport
            return web.Response(text=json.dumps(lookup, default=self.date_handler))
        except KeyError:
            self.log.error('Lookup error for %s' % urllib.parse.unquote(request.match_info['item']))
            return web.Response(text="{}")
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
            return web.Response(body=subset)
        except:
            self.log.info('error handling list', exc_info=True)


    async def listPostHandler(self, request):
        
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
        
        if request.body_exists:
            try:
                outputData={}
                body=await request.read()
                #item="%s?%s" % (request.match_info['del'], request.query_string)
                item=request.match_info['del']
                body=body.decode()
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
                #self.log.info('Requesting thumbnail from camera: %s' % request.match_info['item'])
                result=await self.adapter.virtualThumbnail(request.match_info['item'])
                return web.Response(body=result, headers = { "Content-type": "image/jpeg" })
                        
            return web.Response(text='No thumbnail image found')
        except:
            self.log.error('Error getting thumbnail image for: %s' % request.match_info['item'])
            return web.Response(text='No thumbnail image found')


    async def itemLookupHandler(self, request):
        subset=await self.dataset.getObjectsByDisplayCategory(request.match_info['category'])
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
        if request.body_exists:
            try:
                body=await request.read()
                jsondata=json.loads(body.decode())
                self.log.debug('Post JSON: %s' % jsondata)
                if 'directive' in jsondata:
                    if jsondata['directive']['header']['name']=='ReportState':
                        try:
                            bearerToken=jsondata['directive']['endpoint']['scope']['token']
                        except:
                            self.log.info('No bearer token')
                            bearerToken=''
                        #self.log.info('Reportstate: %s %s' % (jsondata['directive']['endpoint']['endpointId'], jsondata['directive']['header']['correlationToken']))
                        response=self.dataset.generateStateReport(jsondata['directive']['endpoint']['endpointId'], correlationToken=jsondata['directive']['header']['correlationToken'], bearerToken=bearerToken)
                    else:
                        self.log.info('<< %s %s / %s' % (jsondata['directive']['header']['name'],jsondata['directive']['endpoint']['endpointId'], jsondata))
                        response=await self.dataset.handleDirective(jsondata)
                        if response:
                            self.log.info('>> %s %s / %s' % (response['event']['header']['name'],response['event']['endpoint']['endpointId'], response))
            except:
                self.log.error('Error handling root request: %s' % body,exc_info=True)
                response={}
                
        return web.Response(text=json.dumps(response, default=self.date_handler))

        
    async def statusHandler(self, request):
        urls={ "native": "http://%s:%s/native" % (self.serverAddress, self.port), "devices": "http://%s:%s/devices" % (self.serverAddress, self.port)}
        return web.Response(text=json.dumps({"mqtt": self.dataset.mqtt, "logged": self.dataset.logged_lines, "urls": urls}, default=self.date_handler))

    async def rootHandler(self, request):

        return web.Response(text=json.dumps(self.dataset.mqtt, default=self.date_handler))

    async def iconHandler(self, request):

        return web.Response(text="")



        
    def shutdown(self):
        self.loop.run_until_complete(self.serverApp.shutdown())


    def __init__(self, port, loop, log=None, dataset={}):
        self.port = port
        self.loop = loop
        self.workloadData={}
        self.log=log
        self.adapter=None
        self.dataset=dataset
    

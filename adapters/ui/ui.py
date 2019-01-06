#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

from sofabase import sofabase
from sofabase import adapterbase
import devices


from sofacollector import SofaCollector

import math
import random
import json
import asyncio
import aiohttp
from aiohttp import web
import aiohttp_jinja2
import jinja2

import concurrent.futures
import aiofiles
import datetime
import re
import dpath
import urllib
import definitions
import base64
import ssl
import devices
import inspect

import uuid

class sofaWebUI():
    
    def __init__(self, config=None, loop=None, log=None, request=None, dataset=None, notify=None, discover=None, adapter=None):
        self.config=config
        self.log=log
        self.loop = loop
        self.request=request
        self.workloadData={}
        self.adapter=adapter
        self.filecache={}
        self.cardcache={}
        self.fieldcache={}
        self.dataset=dataset
        self.wsclients=[]
        self.wsclientInfo=[]
        self.allowCardCaching=False
        self.definitions=definitions.Definitions
        self.notify=notify
        self.discover=discover
        self.imageCache={}
        self.stateReportCache={}
        self.layout={}

    async def initialize(self):

        try:
            self.serverAddress=self.config['web_address']
            self.serverApp = web.Application()

            self.serverApp.router.add_get('/', self.root_handler)
            self.serverApp.router.add_get('/index.html', self.root_handler)
            self.serverApp.router.add_get('/sofa.appcache', self.manifestHandler)

            self.serverApp.router.add_get('/directives', self.directivesHandler)
            self.serverApp.router.add_get('/properties', self.propertiesHandler)
            self.serverApp.router.add_get('/layout', self.layoutHandler)

            #self.serverApp.router.add_get('/controllercommands', self.controllerHandler)
            self.serverApp.router.add_get('/data/{item:.+}', self.dataHandler)
            self.serverApp.router.add_get('/list/{list:.+}', self.listHandler)
            self.serverApp.router.add_get('/var/{list:.+}', self.varHandler)
            self.serverApp.router.add_post('/list/{list:.+}', self.listPostHandler)
            
            self.serverApp.router.add_get('/adapters', self.adapterHandler)            
            self.serverApp.router.add_get('/devices', self.devicesHandler)      
            self.serverApp.router.add_get('/deviceList', self.deviceListHandler)
            self.serverApp.router.add_post('/deviceState', self.deviceStatePostHandler)
            self.serverApp.router.add_post('/directive', self.directiveHandler) 
            
            self.serverApp.router.add_post('/add/{add:.+}', self.adapterAddHandler)
            self.serverApp.router.add_post('/del/{del:.+}', self.adapterDelHandler)   
            self.serverApp.router.add_post('/save/{save:.+}', self.adapterSaveHandler)
            
            self.serverApp.router.add_get('/displayCategory/{category:.+}', self.displayCategoryHandler)
            self.serverApp.router.add_get('/image/{item:.+}', self.imageHandler)
            self.serverApp.router.add_get('/thumbnail/{item:.+}', self.imageHandler)
            self.serverApp.router.add_get('/ws', self.websocket_handler)
            self.serverApp.router.add_get('/ws/', self.websocket_handler)    
            self.serverApp.router.add_get('/refresh', self.refresh_handler)  
            self.serverApp.router.add_post('/data/{item:.+}', self.dataPostHandler)
            self.serverApp.router.add_static('/log/', path=self.dataset.baseConfig['logDirectory'])
            self.serverApp.router.add_static('/bundle', path=self.config['client_bundle_directory'])
            self.serverApp.router.add_static('/', path=self.config['client_static_directory'])

            self.runner=aiohttp.web.AppRunner(self.serverApp)
            await self.runner.setup()

            self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            self.ssl_context.load_cert_chain(self.config['certificate'], self.config['certificate_key'])

            self.site = web.TCPSite(self.runner, self.config['web_address'], self.config['port'], ssl_context=self.ssl_context)
            await self.site.start()

        except:
            self.log.error('Error with ui server', exc_info=True)

    async def requestField(self, source, item, client=None):

        try:
            if not client:
                client = aiohttp.ClientSession()

            if source in self.dataset.adapters:
                url = 'http://%s:%s/%s' % (self.dataset.adapters[source]['address'], self.dataset.adapters[source]['port'], item)
                async with client.get(url) as response:
                    result=await response.read()
                    result=json.loads(result.decode())

                self.log.info('%s:%s = %s (Retrieved from %s)' % (source, item, result, url))
                #dpath.util.new(self.dataset.data, 'cache/%s/%s' % (source, item), result)
                
                self.log.info('Cache is now: %s ' % self.dataset.data['cache'])
                return {"op":"add", "path": "%s/%s" % (source, item), "value":result}
            else:
                self.log.info('Dont know how to reach adapter for item %s: %s (%s)' % (item, source, self.dataset.adapters))
                return None
        except:
            self.log.error('Error requesting field', exc_info=True)
            return None


    async def requestDiscoveryField(self, item, client=None):

        try:
            if not client:
                client = aiohttp.ClientSession()
                
            discoveryitem=item.split('/')[1]
            if discoveryitem in self.dataset.devices:
                #self.log.info('Cookie data: %s ' % self.dataset.devices[discoveryitem]['cookie'])
                source=self.dataset.devices[discoveryitem]['cookie']['adapter']
                self.log.debug('Identified source %s for Item: %s %s' % (self.dataset.adapters[source], discoveryitem, self.dataset.devices[discoveryitem]))
                
                if source in self.dataset.adapters:
                    url = 'http://%s:%s/discovery/%s?stateReport' % (self.dataset.adapters[source]['address'], self.dataset.adapters[source]['port'], discoveryitem)
                    async with client.get(url) as response:
                        result=await response.read()
                        result=json.loads(result.decode())
                    
                        # convert for short paths in data-xx
                        for prop in result['context']['properties']:
                            if prop['namespace'].split(".")[1]==item.split('/')[2]:
                                if prop['name']==item.split('/')[3]:
                                    result=prop['value']
                                    self.log.info('%s = %s (Retrieved from %s)' % (item, result, url))
                                    dpath.util.new(self.dataset.data, 'cache/%s' % item, result)
                        
                    
                    return {"op":"add", "path": item, "value":result}
                else:
                    self.log.info('Dont know how to reach adapter for item %s: %s (%s)' % (item, source, self.dataset.adapters))
                    return None
            else:
                self.log.info('Could not find %s in %s' % (discoveryitem, self.dataset.devices.keys()))
        except:
            self.log.error('Error requesting field: %s' % item, exc_info=True)
            return None



    async def lookupCardField(self, field, client=None):
        
        try:
            result=self.dataset.getObjectFromPath('/cache/%s' % field)
            
            if result!={}:
                return {"op":"add", "path": field, "value":result}
                #return result
            
            self.log.info('Looking up type for %s: %s' % (field, field.split('/',1)[0].lower()))
            if field.split('/',1)[0].lower()=='discovery':
                return await self.requestDiscoveryField(field, client)
            else:
                return await self.requestField(field.split('/',1)[0], field.split('/',1)[1], client)
            
        except:
            self.log.error('Error looking up requested field: %s' % field, exc_info=True)
            return None

    async def layoutUpdate(self):
        try:
            async with aiofiles.open(os.path.join(self.config['layout_directory'], 'layout.json'), mode='r') as f:
                layout = await f.read()
                return layout
        except:
            self.log.error('Error getting file for cache: %s' % filename, exc_info=True)

    async def layoutHandler(self, request):
        if not self.layout:
            self.layout=await self.layoutUpdate()
            
        return web.Response(content_type="text/html", body=json.dumps(json.loads(self.layout)))


    async def directivesHandler(self, request):
        
        # Walks through the list of current devices, identifies their controllers and extracts a list of 
        # possible directives for each controller and outputs the full list.

        directives={}
        try:
            for device in self.dataset.devices:
                for cap in self.dataset.devices[device]['capabilities']:
                    if len(cap['interface'].split('.')) > 1:
                        capname=cap['interface'].split('.')[1]
                        if capname not in directives:
                            try:
                                controllerclass = getattr(devices, capname+"Interface")
                                xc=controllerclass()
                                try:
                                    directives[capname]=xc.directives
                                except AttributeError:
                                    directives[capname]={}
                            except:
                                self.log.error('Error with getting directives from controller class', exc_info=True)

        except:
            self.log.error('Error creating list of Alexa directives', exc_info=True)
            
        return web.Response(text=json.dumps(directives))

    async def propertiesHandler(self, request):
        
        # Walks through the list of current devices, identifies their controllers and extracts a list of 
        # possible properties for each controller and outputs the full list.
        
        properties={}

        for device in self.dataset.devices:
            for cap in self.dataset.devices[device]['capabilities']:
                if len(cap['interface'].split('.')) > 1:
                    capname=cap['interface'].split('.')[1]
                    if capname not in properties:
                        try:
                            controllerclass = getattr(devices, capname+"Interface")
                            xc=controllerclass()
                            try:
                                properties[capname]=xc.props
                            except AttributeError:
                                properties[capname]={}
                        except:
                            self.log.error('Error with getting properties from controller class', exc_info=True)
            
        return web.Response(text=json.dumps(properties))

        

    async def controllerHandler(self, request):
    
        controllerlist={}

        for device in self.dataset.devices:
            for cap in self.dataset.devices[device]['capabilities']:
                capname=cap['interface'].split('.')[1]
                if capname not in controllerlist:
                    try:
                        controllerclass = getattr(devices, capname+"Interface")
                        xc=controllerclass()
                        try:
                            controllerlist[capname]=xc.commands
                        except AttributeError:
                            controllerlist[capname]={}
                    except:
                        self.log.error('Error with controller class', exc_info=True)
            
        return web.Response(text=json.dumps(controllerlist))


    async def dataSender(self, item):
        
        try:
            if item=="all":
                sendData=self.dataset.getAllDevices()
                
            elif item=="adapters":
                sendData=self.dataset.adapters

            elif item=="areas":
                sendData={}
                for area in self.definitions.areaMap:
                    sendData[area]=[]
                    for category in self.definitions.areaMap[area]:
                        sendData[area]={}
                        for device in self.definitions.areaMap[area][category]:
                            sendData[area][device]=self.dataset.getObjectFromPath("/devices/%s" % device, trynames=True)
                            #sendData[area].append(self.dataset.getObjectFromPath("/devices/%s" % device, trynames=True))

            elif item=='cameras':
                sendData={}
                sendData=self.definitions.cameras
                # hack for now
                #for camera in self.definitions.cameras:
                #    sendData[camera]=self.dataset.getObjectFromPath("/devices/%s" % camera, trynames=True)

            elif item=='virtual':
                sendData={}
                sendData=self.definitions.virtual
                # hack for now
                #for camera in self.definitions.cameras:
                #    sendData[camera]=self.dataset.getObjectFromPath("/devices/%s" % camera, trynames=True)

            elif item.find('devices')==0:
                self.log.info('datasender-Device request: %s' % urllib.parse.unquote(item))
                sendData=self.dataset.getObjectFromPath("/%s" % urllib.parse.unquote(item), trynames=True)
                self.log.info('datasender-Device retrieved: %s' % sendData)
                if 'endpointId' in sendData:
                    return sendData
                    
                outlist=[]    
                for obj in sendData:
                    outlist.append(sendData[obj])
                self.log.info('.. Device count: %s' % len(outlist))
                return outlist
                

            else:
                self.log.info('---- > Looking up: %s' % item)
                async with aiohttp.ClientSession() as client:
                    sendData=await self.lookupCardField(item, client)
                #sendData=self.dataset.getObjectFromPath("/%s" % urllib.parse.unquote(item), trynames=True) 
                self.log.info('datasender done')
            return sendData
        except:
            self.log.error('Error getting file for cache: %s' % cardname, exc_info=True)
            

    async def displayCategoryHandler(self, request):
        
        try:
            category=request.match_info['category']
            devicelist=[]
            alldevices=self.dataset.getObjectFromPath("/devices")
            for device in alldevices:
                try:
                    if category.upper() in alldevices[device]['displayCategories']:
                        devicelist.append(alldevices[device])
                except:
                    pass

            return web.Response(text=json.dumps(devicelist))

        except:
            self.log.error('Error getting items for display category: %s' % category, exc_info=True)


    async def queryStringAdjuster(self, querystring, lookup):
            

        if querystring.find('stateReport')>-1:
            self.log.info('Getting state report from query string adjuster')
            controllers={}
            try:
                #if lookup['endpointId'] not in self.stateReportCache:
                #self.log.info('not in cache: %s' % lookup['endpointId'] )
                newState=await self.dataset.requestReportState(lookup['endpointId'])
                self.stateReportCache[lookup['endpointId']]=json.loads(newState.decode())
                
                self.log.debug('Lookup: %s' % lookup)
                return self.stateReportCache[lookup['endpointId']]
            except:
                self.log.error('Couldnt build state report for %s: %s' % (querystring, lookup), exc_info=True)

                
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

            
    def date_handler(self, obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        else:
            raise TypeError
 

    async def manifestUpdate(self):
        try:
            async with aiofiles.open(os.path.join(self.config['client_static_directory'], 'sofa.appcache'), mode='r') as f:
                manifest = await f.read()
                                           # v-auto
                manifest=manifest.replace('# v-auto', '# v%s' % datetime.datetime.now().strftime("%I:%M%p on %B %d, %Y"))
                return manifest
        except:
            self.log.error('Error getting file for cache: %s' % filename, exc_info=True)

    async def manifestHandler(self, request):
        return web.Response(content_type="text/html", body=await self.manifestUpdate())

    
    async def dataHandler(self, request):
        result=await self.dataSender(request.match_info['item'])
        if request.query_string:
            result=await self.queryStringAdjuster(request.query_string, result)

        return web.Response(text=json.dumps(result))
        

    async def imageGetter(self, item, thumbnail=False):

        try:
            source=item.split('/',1)[0] 
            if source in self.dataset.adapters:
                result='#'
                if thumbnail:
                    url = 'http://%s:%s/thumbnail/%s' % (self.dataset.adapters[source]['address'], self.dataset.adapters[source]['port'], item.split('/',1)[1] )
                else:
                    url = 'http://%s:%s/image/%s' % (self.dataset.adapters[source]['address'], self.dataset.adapters[source]['port'], item.split('/',1)[1] )
                async with aiohttp.ClientSession() as client:
                    async with client.get(url) as response:
                        result=await response.read()
                        return result
                        #result=result.decode()
                        if str(result)[:10]=="data:image":
                            #result=base64.b64decode(result[23:])
                            self.imageCache[item]=str(result)
                            return result
            return None

        except concurrent.futures._base.CancelledError:
            self.log.error('Error getting image %s (cancelled)' % item)
        except:
            self.log.error('Error getting image %s' % item, exc_info=True)
            return None


    async def imageHandler(self, request):

        try:
            fullitem="%s?%s" % (request.match_info['item'], request.query_string)
            if fullitem in self.imageCache:
                result=base64.b64decode(self.imageCache[fullitem][23:])
                return web.Response(body=result, headers = { "Content-type": "image/jpeg" })
            
            if request.path.find('thumbnail')>0:
                result=await self.imageGetter(fullitem, thumbnail=True)
            else:
                result=await self.imageGetter(fullitem)
            
            return web.Response(body=result, headers = { "Content-type": "image/jpeg" })
            
            if str(result)[:10]=="data:image":
                result=base64.b64decode(result[23:])
                #result=base64.b64decode(result[23:])
                return web.Response(body=result, headers = { "Content-type": "image/jpeg" })
            
            self.log.info('Did not get an image to return for %s: %s' % (request.match_info['item'], str(result)[:10]))
            return web.Response(content_type="text/html", body='')
        except:
            self.log.error('Error with image handler', exc_info=True)

    async def listHandler(self, request):

        try:
            #self.log.info('List handler: %s ' % request)
            result={}
            item="%s?%s" % (request.match_info['list'], request.query_string)
            item=request.match_info['list']
            source=item.split('/',1)[0] 
            if source in self.dataset.adapters:
                result='#'
                url = 'http://%s:%s/list/%s' % (self.dataset.adapters[source]['address'], self.dataset.adapters[source]['port'], item.split('/',1)[1] )
                #self.log.info('Requesting list data from: %s' % url)

                async with aiohttp.ClientSession() as client:
                    async with client.get(url) as response:
                        result=await response.read()
                        result=json.loads(result.decode())
                        #self.log.info('resp: %s' % result)
            else:
                self.log.error('Source not in adapters: %s %s' % (source, self.dataset.adapters))

            return web.Response(text=json.dumps(result, default=self.date_handler))

        except concurrent.futures._base.CancelledError:
            self.log.error('Error getting list data %s (cancelled)' % item)
            return web.Response(text=json.dumps({}, default=self.date_handler))
        except:
            self.log.error('Error getting list data %s' % item, exc_info=True)
            return web.Response(text=json.dumps({}, default=self.date_handler))

    async def listPostHandler(self, request):
          
        result={} 
        if request.body_exists:
            try:
                result={}
                outputData={}
                body=await request.read()
                #item="%s?%s" % (request.match_info['list'], request.query_string)
                item=request.match_info['list']
                source=item.split('/',1)[0] 
                if source in self.dataset.adapters:
                    result='#'
                    url = 'http://%s:%s/list/%s' % (self.dataset.adapters[source]['address'], self.dataset.adapters[source]['port'], item.split('/',1)[1] )
                    self.log.info('Posting Save Data to: %s' % url)
                    async with aiohttp.ClientSession() as client:
                        async with client.post(url, data=body) as response:
                            result=await response.read()
                            result=result.decode()
                
            except:
                self.log.error('Error transferring command: %s' % body,exc_info=True)

        return web.Response(text=result)

    async def varHandler(self, request):

        try:
            # Same as list but not json
            self.log.info('.. var handler: %s ' % request)
            result={}
            item="%s?%s" % (request.match_info['list'], request.query_string)
            item=request.match_info['list']
            source=item.split('/',1)[0] 
            if source in self.dataset.adapters:
                result='#'
                url = 'http://%s:%s/var/%s' % (self.dataset.adapters[source]['address'], self.dataset.adapters[source]['port'], item.split('/',1)[1] )
                async with aiohttp.ClientSession() as client:
                    async with client.get(url) as response:
                        result=await response.read()
                        result=result.decode()
            else:
                self.log.error('Source not in adapters: %s %s' % (source, self.dataset.adapters))

            return web.Response(text=result)

        except concurrent.futures._base.CancelledError:
            self.log.error('Error getting list data %s (cancelled)' % item)
            return web.Response(text='')
        except:
            self.log.error('Error getting list data %s' % item, exc_info=True)
            return web.Response(text='')


    async def adapterSaveHandler(self, request):
            
        if request.body_exists:
            try:
                outputData={}
                body=await request.read()
                #item="%s?%s" % (request.match_info['save'], request.query_string)
                item=request.match_info['save']
                source=item.split('/',1)[0] 
                if source in self.dataset.adapters:
                    result='#'
                    url = 'http://%s:%s/save/%s' % (self.dataset.adapters[source]['address'], self.dataset.adapters[source]['port'], item.split('/',1)[1] )
                    self.log.info('Posting Save Data to: %s' % url)
                    async with aiohttp.ClientSession() as client:
                        async with client.post(url, data=body) as response:
                            result=await response.read()
                            result=result.decode()
                            self.log.info('resp: %s' % result)
                
            except:
                self.log.error('Error transferring command: %s' % body,exc_info=True)

            return web.Response(text=result)


    async def adapterDelHandler(self, request):
            
        if request.body_exists:
            try:
                outputData={}
                body=await request.read()
                #item="%s?%s" % (request.match_info['del'], request.query_string)
                item=request.match_info['del']
                source=item.split('/',1)[0] 
                if source in self.dataset.adapters:
                    result='#'
                    url = 'http://%s:%s/del/%s' % (self.dataset.adapters[source]['address'], self.dataset.adapters[source]['port'], item.split('/',1)[1] )
                    self.log.info('Posting Delete Data to: %s' % url)
                    async with aiohttp.ClientSession() as client:
                        async with client.post(url, data=body) as response:
                            result=await response.read()
                            result=result.decode()
                            self.log.info('resp: %s' % result)
                
            except:
                self.log.error('Error transferring command: %s' % body,exc_info=True)

            return web.Response(text=result)

    async def adapterAddHandler(self, request):
            
        if request.body_exists:
            try:
                outputData={}
                body=await request.read()
                #item="%s?%s" % (request.match_info['add'], request.query_string)
                item=request.match_info['add']
                source=item.split('/',1)[0] 
                if source in self.dataset.adapters:
                    result='#'
                    url = 'http://%s:%s/add/%s' % (self.dataset.adapters[source]['address'], self.dataset.adapters[source]['port'], item.split('/',1)[1] )
                    self.log.info('Posting Add Data to: %s' % url)
                    async with aiohttp.ClientSession() as client:
                        async with client.post(url, data=body) as response:
                            result=await response.read()
                            result=result.decode()
                            self.log.info('resp: %s' % result)
                
            except:
                self.log.error('Error transferring command: %s' % body,exc_info=True)

            return web.Response(text=result)


    async def directiveHandler(self, request):
        
        # Take alexa directive commands such as 'TurnOn' or 'SelectInput'
        response={}
        
        try:
            if request.body_exists:
                body=await request.read()
                data=json.loads(body.decode())
                if 'directive' in data:
                    self.log.info("<- %s %s %s/%s" % (request.remote, data['directive']['header']['name'], data['directive']['endpoint']['endpointId'], data['directive']['header']['namespace'].split('.')[1]))

                    #self.log.info('<- %s %s: %s' % (request.remote, data['directive']['header']['name'], data))
                    response=await self.dataset.sendDirectiveToAdapter(data)
                    return web.Response(text=json.dumps(response, default=self.date_handler))
                else:
                    return web.Response(text="{}")                    

        except:
            self.log.error('Error transferring directive: %s' % body,exc_info=True)
            return web.Response(text="{}")

    
    async def devicesHandler(self, request):

        try:
            self.log.info('devices handler: %s ' % request)
            return web.Response(text=json.dumps(self.dataset.devices, default=self.date_handler))
        except:
            self.log.error('Error transferring list of devices: %s' % body,exc_info=True)

    async def deviceListHandler(self, request):

        try:
            self.log.info('<- %s devicelist request' % (request.remote))
            outlist=[]
            for dev in self.dataset.devices:
                outlist.append(self.dataset.devices[dev])
            return web.Response(text=json.dumps(outlist, default=self.date_handler))
        except:
            self.log.error('Error transferring list of devices: %s' % body,exc_info=True)

    async def deviceStatePostHandler(self, request):
            
        if request.body_exists:
            rqid=str(uuid.uuid1())
            #self.log.info('Data Post Handler started: %s' % rqid)
            try:
                outputData={}
                body=await request.read()
                devices=json.loads(body.decode('utf-8'))
                #self.log.info('Data Post Handler body read: %s' % body)
                getByAdapter={}
                alldevs=[]
                for dev in devices:
                    result=self.adapter.getDeviceByfriendlyName(dev)
                    #result=self.dataset.getObjectFromPath("/%s" % dev, trynames=True)
                    #self.log.info('result: %s' % result)
                    adapter=result['endpointId'].split(':')[0]
                    if adapter not in getByAdapter:
                        getByAdapter[adapter]=[]
                    getByAdapter[adapter].append(result['friendlyName'])
                    alldevs.append(result['endpointId'])

                allstates=await asyncio.gather(*[self.dataset.requestReportStates(adapter, getByAdapter[adapter]) for adapter in getByAdapter ])
                    
                #allstates = await asyncio.gather(*[self.dataset.requestReportState(dev) for dev in alldevs ])
                #self.log.info('allstates: %s' % allstates)
                outd={}
                for statelist in allstates:
                    for device in statelist:
                        outd[device]=statelist[device]

                #self.log.info('allstates: %s' % outd)
                #self.log.info('by adapter: %s' % getByAdapter)

                return web.Response(text=json.dumps(outd, default=self.date_handler))
            except:
                self.log.error('Couldnt build device state report', exc_info=True)

            return web.Response(text=json.dumps({}, default=self.date_handler))

    async def dataPostHandler(self, request):
            
        if request.body_exists:
            rqid=str(uuid.uuid1())
            self.log.info('Data Post Handler started: %s' % rqid)
            try:
                outputData={}
                body=await request.read()
                devices=json.loads(body.decode('utf-8'))
                self.log.info('Data Post Handler body read: %s' % rqid)
                for dev in devices:
                    result=await self.dataSender("%s/%s" % (request.match_info['item'], dev))
                    if request.query_string:
                        result=await self.queryStringAdjuster(request.query_string, result)
                    outputData[dev]=result
                self.log.info('Data Post response assembled: %s' % rqid)

            except:
                self.log.error('Error transferring command: %s' % body,exc_info=True)

            return web.Response(text=json.dumps(outputData, default=self.date_handler))

    async def refresh_handler(self,request):
    
        try:
            await self.discover('sofa')
            return web.Response(text='Discovery request sent')

        except:
            self.log.error('Error running discovery', exc_info=True)
            return web.Response(text='Discovery request failed')
            
    async def adapterHandler(self,request):
        return web.Response(text=json.dumps(self.dataset.adapters, default=self.date_handler))


    async def websocket_handler(self, request):

        # everything should be moved to the POST based API, and endpoints should not need to send commands via
        # websocket.  The websocket is still needed for streaming updates from server to client.

        try:
            try:
                peername=request.transport.get_extra_info('peername')
            except:
                peername=("(unknown)",0)
                
            self.log.info('++ %s/%s websocket connected' % peername)
            
            ws = web.WebSocketResponse()
            self.wsclients.append(ws)
            await ws.prepare(request)

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    self.log.info('<- wsdata: %s' % msg.data)
                    try:
                        message=json.loads(msg.data)
                        if 'directive' in message:
                            await self.dataset.sendDirectiveToAdapter(message)

                    except:
                        self.log.error('!! Error decoding websocket message: %s' % msg.data, exc_info=True)
                    if msg.data == 'close':
                        await ws.close()
                    #else:
                    #    await ws.send_str("msg.data + '/answer')
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.log.error('-! ws connection closed with exception: %s' % ws.exception())


            self.log.info('-- Websocket closed: %s %s' % peername)
            return ws
        except concurrent.futures._base.CancelledError:
            self.wsclients.remove(ws)
            
            try:
                ws.close()
            except:
                self.log.error('-! Could not close websocket')
            
            self.log.info('-- Websocket cancelled: %s %s (this is a normal close for mobile safari)' % peername)
            return ws
            
        except:
            try:
                ws.close()
            except:
                self.log.error('Could not close websocket')
            self.log.error('Websocket error', exc_info=True)
            try:
                if self.wsclients.index(ws):
                    del self.wsclients[self.wsclients.index(ws)]
            except:
                self.log.error('Error deleting busted websocket', exc_info=True)
                

    async def root_handler(self, request):
        return web.FileResponse(os.path.join(self.config['client_static_directory'],'index.html'))


    async def wsBroadcast(self, message):
        
        try:
            liveclients=[]
            openSocketList=[]
            for i, wsclient in enumerate(self.wsclients):
                try:
                    if not wsclient.closed:
                        await wsclient.send_str(message)
                        openSocketList.append(wsclient)
                        liveclients.append(wsclient._req.transport.get_extra_info('peername'))
                except:
                    self.log.error('Something was wrong with websocket %s (%s), and it will be removed.' % (i, wsclient.__dict__))
                    
            # This purges the closed websockets
            if self.wsclients!=openSocketList:
                deadlist = list(set(self.wsclientInfo) - set(liveclients))
                self.log.info('-> (wsbc) live: %s / dead: %s)' % (liveclients, deadlist))
                self.wsclientInfo=liveclients
            self.wsclients=openSocketList
        except:
            self.log.error('Error broadcasting to websockets: %s' % message, exc_info=True)
 

class ui(sofabase):

    class adapterProcess(SofaCollector.collectorAdapter):

        def __init__(self, log=None, loop=None, dataset=None, notify=None, discover=None, request=None,  **kwargs):
            self.dataset=dataset
            self.config=self.dataset.config
            self.dataset.data['cache']={}
            self.log=log
            self.notify=notify
            self.request=request
            self.discover=discover
            #self.loop = asyncio.new_event_loop()
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            
            
        async def start(self):
            self.log.info('.. Starting ui server')
            self.uiServer = sofaWebUI(config=self.config, loop=self.loop, log=self.log, request=self.request, dataset=self.dataset, notify=self.notify, discover=self.discover, adapter=self)
            await self.uiServer.initialize()
            #await self.discover('sofa')

        async def handleStateReport(self, message):
        
            try:
                await super().handleStateReport(message)
                # Just send the state report for now so that I can finish react testing
                await self.uiServer.wsBroadcast(json.dumps(message))

            except:
                self.log.error('Error updating from state report: %s' % message, exc_info=True)

        async def handleChangeReport(self, message):
        
            try:
                super().handleChangeReport(message)
                if message:
                    try:
                        crs=[]
                        for prop in message['payload']['change']['properties']:
                            crs.append("%s/%s/%s=%s" % (message['event']['endpoint']['endpointId'], prop['namespace'].split('.')[1], prop['name'], prop['value']))
                            self.log.info('-> ws ChangeReport %s' % crs)
                            await self.uiServer.wsBroadcast(json.dumps(message))
                    except:
                        self.log.warn('!. bad or empty ChangeReport message not sent to ws: %s' % message)

            except:
                self.log.error('Error updating from change report', exc_info=True)


        async def virtualCategory(self, category):
            
            if category in ['light','thermostat']:
                subset={key: value for (key,value) in self.dataset.devices.items() if category.upper() in value['displayCategories']}
            else:
                subset={}
                
            return subset


if __name__ == '__main__':
    adapter=ui(name='ui')
    adapter.start()
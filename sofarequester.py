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
import sofarest

class sofaRequester():
        
    def __init__(self):
        pass

    async def reportStateRequest(self, path):
            
        async with aiohttp.ClientSession() as client:
            header={"name": "ReportState", "namespace":"Alexa", "payloadVersion":"3", "messageId": str(uuid.uuid1()), "correlationToken": str(uuid.uuid1())}
            endpoint={"endpointId":"%s#%s#%s" % (self.adaptername, category, item), "cookie": {"adapter": self.adaptername, "path": path}}
            
        
    async def sendRequest(self, client, source, category, item):
        restAddress='127.0.0.1'
        restPort=8081
        url = 'http://%s:%s/%s/%s' % (restAddress, restPort, category, item)
        response=await client.get(url)
        return await response.read()        

    
    async def request(self, source, category, item):
        async with aiohttp.ClientSession() as client:
            itemvalue=await self.sendRequest(client, source, category, item)
            self.data.setdefault(source, {}).setdefault(category, {})[item]=json.loads(itemvalue.decode())
            #self.data[source][category][item]=itemvalue
            return json.loads(itemvalue.decode())
            


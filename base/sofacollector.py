import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))

from sofabase import sofabase, adapterbase

import asyncio
import json
import datetime
import uuid

class SofaCollector(sofabase):

    # This is a variant of sofabase that listens for other adapters and collects information.  Generally this would be used for
    # UI, Logic, or other modules where state tracking of devices is important

    class collectorAdapter(adapterbase):

        @property
        def collector(self):
            return True

        @property
        def is_hub(self):
            return False


        @property
        def collector_categories(self):
            return ['ALL']


        def __init__(self, log=None, loop=None, dataset=None, config=None, **kwargs):
            self.dataset=dataset
            self.config=config
            self.log=log
            self.loop=loop
            self.device_cache={}
            self.state_cache={}
            self.caching_enabled=True
            self.pendingRequests={}
            try:
                if self.caching_enabled:
                    self.dataset.devices=self.load_cache('%s_device_cache' % self.config.adapter_name)    
            except:
                self.log.error('!! Error loading devices from device cache')


        async def handle_discovery_report(self, message, adapter=None):
            try:
                devlist=message['event']['payload']['endpoints']
                if devlist:
                    for dev in devlist:
                        self.dataset.devices[dev['endpointId']]=dev
                        if hasattr(self, "virtualAddDevice"):
                            await self.virtualAddDevice(dev['endpointId'], dev)
                        
                        # deprecating virtualAddDevice for process_ for better clarity in adapters
                        
                        if hasattr(self, "add_remote_device"):
                            await self.add_remote_device(dev['endpointId'], dev)
                            
                    self.log.info('++ AddOrUpdate %s devices. Now %s total devices.'  % (len(devlist), len(self.dataset.devices)))
                    if self.caching_enabled:
                        self.save_cache('%s_device_cache' % self.config.adapter_name, self.dataset.devices)

            except:
                self.log.error('Error handling AddorUpdate: %s' % message , exc_info=True)


        async def handleAddOrUpdateReport(self, message, source=None):

            try:
                devlist=message['event']['payload']['endpoints']
                if devlist:
                    for dev in devlist:
                        self.dataset.devices[dev['endpointId']]=dev
                        if hasattr(self, "virtualAddDevice"):
                            await self.virtualAddDevice(dev['endpointId'], dev)
                        
                        # deprecating virtualAddDevice for process_ for better clarity in adapters
                        
                        if hasattr(self, "add_remote_device"):
                            await self.add_remote_device(dev['endpointId'], dev)
                            
                    self.log.info('++ AddOrUpdate %s devices. Now %s total devices.'  % (len(devlist), len(self.dataset.devices)))
                    if self.caching_enabled:
                        self.save_cache('%s_device_cache' % self.config.adapter_name, self.dataset.devices)
                        # TODO/CHEESE - Probably need to update the device states here but need to think about how
                        #self.request_state_reports

            except:
                self.log.error('Error handling AddorUpdate: %s' % message , exc_info=True)

                    
        async def sendAlexaCommand(self, command, controller, endpointId, payload={}, cookie={}, trigger={}):
            
            try:
                header={"name": command, "namespace":"Alexa." + controller, "payloadVersion":"3", "messageId": str(uuid.uuid1()), "correlationToken": str(uuid.uuid1())}
                endpoint={"endpointId": endpointId, "cookie": cookie, "scope":{ "type":"BearerToken", "token":self.config.api_key }}
                data={"directive": {"header": header, "endpoint": endpoint, "payload": payload }}
                report=await self.dataset.sendDirectiveToAdapter(data)
                return report
            except:
                self.log.error('Error executing Alexa Command: %s %s %s %s' % (command, controller, endpointId, payload), exc_info=True)
                return {}


        async def handleStateReport(self, message, source=None):
            if self.caching_enabled:
                try:
                    if message['event']['header']['name']!='StateReport':
                        self.log.error("!! non-statereport sent to state report handler: %s %s" % ( message['event']['header']['name'], message))
                        return False
                    endpointId=message['event']['endpoint']['endpointId']
                    self.state_cache[endpointId]=message['context']['properties']
                    #self.log.info('~~ State report cached for %s: %s' % (endpointId, self.state_cache[endpointId]))
                except:
                    self.log.error("!! Error caching statereport %s" % message, exc_info=True)


        async def handleResponse(self, message):
            try:
                if not message:
                    return {}

                if self.config.log_changes:
                    self.log.info('.. Response Prop: %s' % message)
                
                if 'event' in message:
                    if message['event']['header']['name']=='ErrorResponse':
                        await self.handleErrorResponse(message)
                        self.log.info('!> ErrorResponse: %s' % message)
                        if hasattr(self, "virtualErrorHandler"):
                            # This is mostly just for logic but other adapters could hook this eventually
                            await self.virtualErrorHandler(message['event']['endpoint']['endpointId'], message['event']['payload']['t'])
                        
                    
                if 'context' in message and 'properties' in message['context']:
                    # Certain responses like the CameraStream do not include context
                    for prop in message['context']['properties']:
                        if hasattr(self, "virtualChangeHandler"):
                            # This is mostly just for logic but other adapters could hook this eventually
                            await self.virtualChangeHandler(message['event']['endpoint']['endpointId'], prop)
            except:
                self.log.error('Error processing Change Report', exc_info=True)


        async def handleErrorResponse(self, message ):
            try:
                self.log.info('!> ErrorResponse: %s' % message)
                error_type=message['event']['payload']['type']
                endpointId=message['event']['endpoint']['endpointId']
                if error_type=="BRIDGE_UNREACHABLE":
                    if endpointId in self.state_cache:
                        for prop in self.state_cache[endpointId]:
                            if prop['namespace']=="Alexa.EndpointHealth":
                                prop['value']={"value": "UNREACHABLE"}
                
                elif error_type=="NO_SUCH_DEVICE":
                    if endpointId in self.state_cache:
                        del self.state_cache[endpointId]
                    
                if hasattr(self, "virtualErrorHandler"):
                    await self.virtualErrorHandler(message['event']['endpoint']['endpointId'], message['event']['payload']['type'], message['event']['payload']['message'])
            except:
                self.log.error('Error processing ErrorResponse', exc_info=True)

        

        async def handleAlexaEvent(self, message):
            
            # This handler accepts Alexa events such as DoorbellPress
            
            try:
                self.log.info('.! alexa event received: %s' % message)
                if hasattr(self, "virtualEventHandler"):
                    await self.virtualEventHandler(message['event']['header']['name'], message['event']['endpoint']['endpointId'], "", message)

                # deprecating virtual event handler, removing source and rearranging param order

                if hasattr(self, "process_remote_event"):
                    await self.process_remote_event(message['event']['endpoint']['endpointId'], message['event']['header']['name'], message)
                    
            except:
                self.log.error('Error handling Alexa Event', exc_info=True)

        async def handleChangeReport(self, message):
            
            try:

                if self.caching_enabled:
                    try:
                        endpointId=message['event']['endpoint']['endpointId']
                        self.state_cache[endpointId]=message['context']['properties']
                        for prop in message['event']['payload']['change']['properties']:
                            self.state_cache[endpointId].append(prop)
                        #self.log.info('~~ Change report cached for %s: %s' % (endpointId, self.state_cache[endpointId]))
                    except:
                        self.log.error("!! Error caching state from change report", exc_info=True)
    
                            
                for prop in message['event']['payload']['change']['properties']:
                    if hasattr(self, "virtualChangeHandler"):
                        # This is mostly just for logic but other adapters could hook this eventually
                        await self.virtualChangeHandler(message['event']['endpoint']['endpointId'], prop)
            except:
                self.log.error('Error processing Change Report', exc_info=True)
            return {}


        async def handleDeleteReport(self, message):
            try:
                if not message:
                    return {}
                    
                if 'event' not in message or 'payload' not in message['event']:
                    self.log.error('Error: invalid delete report - has no event or event/payload: %s' % message)
                    return {}

                for prop in message['event']['payload']['endpoints']:
                    if prop['endpointId'] in self.dataset.devices:
                        self.log.info('-- Removing device: %s %s' % (prop['endpointId'], self.dataset.devices[prop['endpointId']]))
                        del self.dataset.devices[prop['endpointId']]
                    if hasattr(self, "virtualDeleteHandler"):
                        await self.virtualDeleteHandler(prop['endpointId'])
            except:
                self.log.error('Error handing deletereport: %s' % message, exc_info=True)


        async def remove_devices(self, objlist):
            
            # This function is called by the adapter itsely to remove devices that are no longer being shared from
            # another adapter.  It's designed to help with clean-up but a manual approach might be more in line with the Alexa model.
            
            for endpointId in objlist:
                try:
                    del self.dataset.devices[endpointId]
                    if hasattr(self, "virtualDeleteDevice"):
                        await self.virtualDeleteDevice(endpointId)
                except:
                    self.log.error('Error updating device list: %s' % objlist, exc_info=True)


        async def process_event(self, message, source=None):
            
            # Only Collector modules should need to handle Event messages
            try:
                if 'event' in message:
                    try:
                        if message['event']['endpoint']['endpointId'].split(":")[0]==self.dataset.adaptername:
                            return False
                    except KeyError:
                        pass

                    if 'correlationToken' in message['event']['header']:
                        try:
                            if message['event']['header']['correlationToken'] in self.pendingRequests:
                                self.pendingResponses[message['event']['header']['correlationToken']]=message
                                self.pendingRequests.remove(message['event']['header']['correlationToken'])
                        except:
                            self.log.error('Error handling a correlation token response: %s ' % message, exc_info=True)
                    
                    # Note this is a separate if statement from the correlation token tracker and should not be combined
                    # 10/14/20 caused major confusion when the following was elif
                    
                    if message['event']['header']['name']=='DoorbellPress':
                        await self.handleAlexaEvent(message)
                
                    elif message['event']['header']['name']=='StateReport':
                        await self.handleStateReport(message)
    
                    elif message['event']['header']['name']=='ChangeReport':
                        await self.handleChangeReport(message)
    
                    elif message['event']['header']['name']=='DeleteReport':
                        await self.handleDeleteReport(message)
                    
                    elif message['event']['header']['name']=='AddOrUpdateReport':
                        await self.handleAddOrUpdateReport(message)
                    else:
                        self.log.info('Message type not processed: %s' % message['event']['header']['name'])
            except:
                self.log.error('Error processing event message: %s' % message, exc_info=True)
                
                
        ## New Caching mechanisms
        
        async def last_cache_update(self):
            
            latest_time=None
            self.log.info('.. getting latest update from %s items' % len(self.state_cache.keys()))
            try:
                for item in self.state_cache:
                    for prop in self.state_cache[item]['context']['properties']:
                        working=prop['timeOfSample'].split('.')[0].replace('Z','')
                        working=datetime.datetime.strptime(working, '%Y-%m-%dT%H:%M:%S')
                        if latest_time==None or working>latest_time:
                            latest_time=working
                self.log.info('.. latest update: %s' % working)
                return working
            except:
                self.log.error('!! error getting date for latest cache update', exc_info=True)


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
                    
                response['context']={ "properties" : self.state_cache[endpointId] }
                return response
            except:
                self.log.error('!! error generating cached state report %s' % endpointId, exc_info=True)
            return {}

                
        async def request_state_reports(self, device_list, cache=True):
            try:
                results=[]
                req_start=datetime.datetime.now()
                web_requests=[]
                cache_results=[]
                for dev in device_list:
                    proactive=True
                    for cap in self.dataset.devices[dev]['capabilities']:
                        if 'properties' in cap and not cap['properties']['proactivelyReported']:      
                            proactive=False
                            break
                    if dev in self.state_cache and proactive:
                        #self.log.info('.. getting %s from cache' % dev)
                        cache_results.append(await self.cached_state_report(dev))
                    else:
                        web_requests.append(self.dataset.requestReportState(dev))
                if len(web_requests)>0:
                    results = await asyncio.gather(*web_requests)

                results=results+cache_results
                if len(web_requests)>0:
                    self.log.info('>> requested state reports: %s seconds / %s items / %s cache misses / %s results' % ((datetime.datetime.now()-req_start).total_seconds(), len(device_list), len(web_requests), len(results)))
            except:
                self.log.error('!! error generating cached state report %s' % endpointId, exc_info=True)
            return results




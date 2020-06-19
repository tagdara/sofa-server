
    async def sseDeviceUpdater(self, resp, remoteip):
        try:
            self.log.info('<- %s devicelist request' % (remoteip))
            outlist=[]
            byadapter={}
            
            # Carving this up by adapter to deal with the 128k size limitation issues with aiohttp_sse
            # Data updates were already by adapter due to the way we request information
            # https://github.com/rtfol/aiohttp-sse-client/issues/11
            
            for dev in self.dataset.devices:
                dei=self.dataset.devices[dev]['endpointId'].split(':')[0]
                if dei not in byadapter:
                    byadapter[dei]=[]
                byadapter[dei].append(self.dataset.devices[dev])
            for adapter in byadapter:
                aou={"event": { "header": { "namespace": "Alexa.Discovery", "name": "AddOrUpdateReport", "payloadVersion": "3", "messageId": str(uuid.uuid1()) }, "payload": {"endpoints": byadapter[adapter]}}}
                await resp.send(json.dumps(aou, default=self.date_handler))
            self.log.info('-> %s devicelist' % remoteip)
        except:
            self.log.error('!! SSE Error transferring list of devices',exc_info=True)


    async def sseDataUpdater(self, resp):
        try:
            req_start=datetime.datetime.now()
            devoutput={}
            devices=list(self.dataset.devices.values())

            getByAdapter={} 
            for dev in self.dataset.devices:
                adapter=dev.split(':')[0]
                if adapter not in getByAdapter:
                    getByAdapter[adapter]=[]
                getByAdapter[adapter].append(dev)
                
            gfa=[]
            
            for adapter in getByAdapter:
                gfa.append(self.dataset.requestReportStates(adapter, getByAdapter[adapter]))
                
            for f in asyncio.as_completed(gfa):
                devstate = await f  # Await for next result.
                devoutput={"event": { "header": { "name": "Multistate" }}, "state": devstate}
                await resp.send(json.dumps(devoutput))
                if (datetime.datetime.now()-req_start).total_seconds()>0.5:
                    self.log.info('.. completed req in %s for %s' % (datetime.datetime.now()-req_start, devstate.keys()))

        except concurrent.futures._base.CancelledError:
            self.log.warn('.. sse update cancelled. %s' % devoutput)
                    
        except:
            self.log.error('Error sse list of devices', exc_info=True)


    async def startEventConnection(self, retry_time=300):
        
        try:
            self.sse_connect_errors=0
            if self.dataset.adaptername=="ui" or self.dataset.adaptername=="hub":
                #self.log.info('.. activation not required for Hub and UI adapter')
                #self.log.info('.. activation not required for UI adapter')
                return False
            
            if self.collector==False:
                self.log.info('.. SSE event stream not required for non collector adapter')
                return False

            while self.adapter.running==True:
                if not self.token or not self.activated:
                    self.activated=await self.activate()
                    if not self.token or not self.activated:
                        self.log.info('.. did not activate and no token available. checking again in %s seconds' % retry_time)
                        await asyncio.sleep(retry_time)
                    else:
                        self.log.info('.. Activated: %s / Token: %s' % (self.activated, self.token))
                
                while self.activated==True:
                    if self.sse_connect_errors>0:
                        self.log.info('.. SSE connection problems (%s) - waiting %s to retry' % (self.sse_connect_errors, self.sse_connect_errors*5))
                        await asyncio.sleep(self.sse_connect_errors*5)
                    try:
                        # This should establish an SSE connection with the UI adapter
                        url = '%s/sse' % (self.dataset.baseConfig['apiGateway'] )
                        timeout = aiohttp.ClientTimeout(total=0)
                        headers = { 'authorization': self.token }
                        async with sse_client.EventSource(url, timeout=timeout, headers=headers) as event_source:
                            try:
                                self.sse_connect_errors=0
                                self.log.info('[] SSE connection established with event gateway')
                                async for event in event_source:
                                    try:
                                        data=json.loads(event.data)
                                        #self.log.info('<< (sse) %s' % data)
                                        await self.dataset.processSofaMessage(data)
                                        self.sse_connect_errors=0
                                    except:
                                        self.log.error('!< error with sse data', exc_info=True)
                            except aiohttp.client_exceptions.ClientPayloadError:
                                self.log.warning('!! error with SSE connection (client payload error / payload not complete)', exc_info=True)
                    except ConnectionError as e:
                        if '502' in str(e):
                            self.log.error('!! error with SSE connection (502 bad gateway / server down)')
                        elif '401' in str(e):
                            self.log.error('!! token not valid for SSE connection %s' % (str(e)))
                            self.activated=False
                            break
                        else:
                            self.log.error('!! error with SSE connection %s' % (str(e)), exc_info=True)
                        self.sse_connect_errors+=1
                        if event_source:
                            await event_source.close()
                    except concurrent.futures._base.TimeoutError:
                        self.log.error('!! error - event SSE timeout')
                        self.sse_connect_errors+=1
                    except ConnectionRefusedError as e:
                        if '401' in str(e):
                            self.log.error('.. Adapter not activated')
                        else:
                            self.log.error('!! error starting event SSE connection: %s %s' % (e.errno, dir(e)), exc_info=True)
                        self.sse_connect_errors+=1
                    except Exception as e:
                        self.log.error('!! error starting event SSE connection: %s %s' % (e.errno, dir(e)), exc_info=True)
                        self.sse_connect_errors+=1
        except:
            self.log.error('!! Error in event connection loop', exc_info=True)

    async def start_event_listener(self):
        asyncio.create_task(self.startEventConnection())


    @login_required
    async def sse_handler(self, request):
        try:

            remoteip=request.remote
            remoteuser=request.user
            sessionid=str(uuid.uuid1())
            if remoteip not in self.active_sessions:
                self.active_sessions[sessionid]=remoteip

            self.log.info('++ SSE started for %s/%s' % (request.remote, request.user))

            client_sse_date=datetime.datetime.now(datetime.timezone.utc)
            async with sse_response(request) as resp:
                await self.sseDeviceUpdater(resp, remoteip)
                await self.sseDataUpdater(resp)
                self.log.info('.. initial SSE data load complete')

                while self.adapter.running:
                    if self.sse_last_update>client_sse_date:
                        if request.collector:
                            sendupdates=[]
                            for update in reversed(self.sse_updates):
                                if update['date']>client_sse_date:
                                    sendupdates.append(update['message'])
                                else:
                                    break
                            for update in reversed(sendupdates):
                                #self.log.info('Sending SSE update: %s' % update )
                                await resp.send(json.dumps(update))
                        client_sse_date=self.sse_last_update
                        
                    if client_sse_date<datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10):
                        data={"event": {"header": {"name": "Heartbeat"}}, "heartbeat":self.sse_last_update, "lastupdate":self.sse_last_update }
                        await resp.send(json.dumps(data,default=self.date_handler))
                        client_sse_date=datetime.datetime.now(datetime.timezone.utc)
                    await asyncio.sleep(.1)
                self.log.info('no longer running?')
                del self.active_sessions[sessionid]
            return resp
        except concurrent.futures._base.CancelledError:
            self.log.info('-- SSE closed for %s/%s' % (remoteip, remoteuser))
            del self.active_sessions[sessionid]
            return resp
        except:
            self.log.error('!! Error in SSE loop for %s/%s' % (remoteip, remoteuser), exc_info=True)
            del self.active_sessions[sessionid]
            return resp
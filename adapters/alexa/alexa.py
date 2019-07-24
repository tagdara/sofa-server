#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

from sofabase import sofabase
from sofabase import adapterbase
import devices
from sofacollector import SofaCollector
from concurrent.futures import ThreadPoolExecutor


import json
import asyncio
import concurrent.futures
import datetime
import uuid
import asyncio
import aiobotocore
import time
import copy
import aiohttp

# This needs to be closely reworked, probably with AIOBOTOCORE https://github.com/aio-libs/aiobotocore

class alexaBridge(sofabase):

    class adapterProcess(SofaCollector.collectorAdapter):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.dataset.nativeDevices['scene']={}
            self.dataset.nativeDevices['activity']={}
            self.messagepool = ThreadPoolExecutor(10)

            #self.definitions=definitions.Definitions
            self.log=log
            self.notify=notify
            self.running=True
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
                
        def suppressTokens(self, oldlogmessage):

            logmessage=copy.deepcopy(oldlogmessage)
            try:
                del logmessage['directive']['header']['correlationToken']
            except:
                pass
         
            try:
                del logmessage['directive']['endpoint']['scope']['token']
            except:
                pass
            
            try:
                del logmessage['event']['endpoint']['scope']['token']
            except:
                pass
       
            try:
                del logmessage['event']['header']['correlationToken']
            except:
                pass

            return logmessage

        def jsonDateHandler(self, obj):

            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            else:
                self.log.error('Found unknown object for json dump: (%s) %s' % (type(obj),obj))
            return None

            
        async def start(self):
            self.polltime=1
            self.newGrant=False
            self.tokenRefresh=False
            self.grant=self.loadJSON('alexagrant')
            if 'expires' in self.grant:
                self.grant['expires']=datetime.datetime.strptime(self.grant['expires'].split('.')[0], '%Y-%m-%dT%H:%M:%S')    
            self.log.info('.. Starting Alexa Bridge')
            try:
                session = aiobotocore.get_session(loop=self.loop)
                self.sqs = session.create_client('sqs', region_name=self.dataset.config["region_name"],
                                   aws_secret_access_key=self.dataset.config["aws_secret_access_key"],
                                   aws_access_key_id=self.dataset.config["aws_access_key_id"])

                await self.connectSQSqueue('sofa')
                await self.pollSQSlong()

            except:
                self.log.error('Error loading cached devices', exc_info=True)

                
        async def processSQS(self,event,returnqueue):
        
            #self.log.info('Starting process SQS for %s' % str(event))
        
            if isinstance(event, str):
                self.log.info('SQS Request:'+str(event))
                event=json.loads(event)
        
            #if not self.localcache['config']['acceptingcommands']:
            #    self.log.info('Alexa command received, but processing is currently disabled in the adapter configuration.')
            #    header["name"]="BridgeOfflineError"
            #    return {"header":header, "payload":{}}
        
            if "directive" in event:
                if 'header' in event["directive"]:
                    if 'messageId' in event["directive"]["header"]:
                        messageId=event["directive"]["header"]['messageId']
                    else:
                        messageId="Unknown"
                    if 'name' in event["directive"]["header"]:
                        command=event["directive"]["header"]['name']
                        if command=='Discover':
                            response=self.alexaDiscovery(messageId)
                            return response
                        elif command=='AcceptGrant':
                            response=await self.alexaAcceptGrant(event)
                            return response
                        elif command=='ReportState':
                            response=await self.dataset.requestReportState(event['directive']['endpoint']['endpointId'], correlationToken=event["directive"]["header"]['correlationToken'], bearerToken=self.grant['token'])
                            #self.log.info('Reportstate: %s' % response)
                            return response
                        else:
                            # CHEESE This is all wrong now because Logic is actually sending back activationstarted.  It needs to be changed to receive an async
                            # completion status and send that to the alexa gateway.  right now it just generates 2 activation started sends.
                            
                            if event["directive"]["header"]['name']in ['Activate','Deactivate']:
                                response=await self.activationStarted(event)  
                                await self.SQSearlyResponse(response, returnqueue)
                            
                            response=await self.dataset.sendDirectiveToAdapter(event)
                            try:
                                if 'properties' in response['context']:
                                    response['context']['properties']=self.trimProps(response['context']['properties'])
                            except:
                                self.log.error('Error trimming properties from response: %s' % response, exc_info=True)

                            if 'correlationToken' in event["directive"]["header"] and response:
                                if response['event']['header']['name']!='Response':
                                    response=await self.convertChangeToResponse(response)
                                response['event']['header']['correlationToken']=event["directive"]["header"]['correlationToken']
                                response['event']['endpoint']['scope']=event["directive"]["endpoint"]['scope']
                                #self.log.info('Response: %s' % response)
                            return response

                        #{'directive': {'endpoint': {'endpointId': 'hue:lights:16', 'cookie': {}, 'scope': {'type': 'BearerToken'}}, 'header': {'messageId': '296fb949-a51d-44fc-9240-28fc4f3efd3e', 'payloadVersion': '3', 'name': 'ReportState', 'namespace': 'Alexa'}, 'payload': {}}}


        
            self.log.error('Command not implemented yet: %s %s' % (command, event))
            return None

        def trimProps(self, props):
            
            try:
                outprops=[]
                for prop in props:
                    if prop['namespace'].startswith('Alexa'):
                        outprops.append(prop)
                    else:
                        self.log.info('Trimmed non-alexa property: %s' % prop)
                return outprops
            except:
                self.log.error('Error trimming props', exc_info=True)
                return []

        
        async def convertChangeToResponse(self, changereport):
        
            try:
                if changereport['event']['header']['name']=='ChangeReport':
                    return { "event": { "header" : {"namespace": "Alexa", "name":"Response", "payloadVersion": "3", "messageId": str(uuid.uuid1()) } , "endpoint" : { "endpointId": changereport['event']['endpoint']['endpointId'] } , "payload": {} }, "context": { "properties" :  changereport['payload']['change']['properties'] } }
                
                return changereport

            except:
                self.log.error('Error converting change report: %s' % changereport, exc_info=True)
                return changereport

        async def activationStarted(self, event):
        
            try:
                response={ "event": { "header" : {"namespace": "Alexa.SceneController", "name":"ActivationStarted", "payloadVersion": "3", "messageId": str(uuid.uuid1()), 'correlationToken' : event["directive"]["header"]['correlationToken'] }, "endpoint" : { "endpointId": event['directive']['endpoint']['endpointId'], "scope":event["directive"]["endpoint"]['scope']} , "payload": { "timestamp":datetime.datetime.utcnow().isoformat() + "Z", "cause": { "type": "VOICE_INTERACTION"}} }, "context": {} }
                return response
            except:
                self.log.error('Error converting change report', exc_info=True)


        async def connectReturnQueue(self,qname):
            
            try:
                queue_obj = await self.sqs.get_queue_url(QueueName=qname)
                #self.log.info('connect return queue SQS: %s' % queue_obj['QueueUrl'])
                queue_url=queue_obj['QueueUrl']
                return queue_url
            except:
                self.log.info('Return queue does not exist: %s' % qname)
                return None

        async def connectSQSqueue(self,qname):

            try:
                #self.log.info('SQS: %s' % await self.sqs.get_queue_url(QueueName=qname))
                queue_obj = await self.sqs.get_queue_url(QueueName=qname)
                queue_url=queue_obj['QueueUrl']
                #self.log.info('qurl: %s' % queue_url)
                response = await self.sqs.set_queue_attributes(QueueUrl=queue_url,
                    Attributes={
                        'MessageRetentionPeriod': '60',
                        'VisibilityTimeout':'2'
                    }
                )

                try:
                    await self.sqs.purge(QueueUrl=queue_url)
                    #queue.purge()
                except:
                    #If you call this more than once a minute it fails, but it doesn't really matter
                    pass
            
                #self.log.info('Queue '+qname+' exists: '+str(queue_url))
                return queue_url
                
            except:
                self.log.error('Queue does not exist',exc_info=True)
                try:
                    queue=self.sqs.create_queue(QueueName=qname)
                    return queue
                except:
                    return None

        async def SQSearlyResponse_eventgateway(self, response, returnqueue=None):

            try:
                await self.alexaSendToEventGateway(json.dumps(response))
                
                try:
                    self.log.info('<- %s/%s %s %s' % (response["event"]["header"]["name"], response["event"]["header"]["messageId"], self.suppressTokens(response)))
                except:
                    self.log.info('<- response %s' % response)

            except:
                self.log.error('Error sending back early response: %s' % response, exc_info=True)

        async def SQSearlyResponse(self, response, returnqueue):

            try:
                await self.sqs.send_message(QueueUrl=returnqueue,MessageBody=json.dumps(response))

                try:
                    self.log.info('<- %s/%s %s %s' % (response["event"]["header"]["name"], response["event"]["header"]["messageId"], self.suppressTokens(response)))
                except:
                    self.log.info('<- response %s' % response)

            except:
                self.log.error('Error sending back early response: %s' % response, exc_info=True)


        def queueId(self, message):
            try:
                if 'correlationToken' in message['directive']['header']:
                    qid=message['directive']['header']['correlationToken']
                else:
                    qid=message['directive']['header']['messageId']
                qid=qid[-10:-2]
                delchars=str.maketrans('','','+=-!/&$\\')
                #delchars=str.maketrans('','','+=-!/&$\\')

                return 'sofa-%s' % qid.translate(delchars)

            except:
                logger.error('Message did not have a messageId or Correlation token')
                return None

        async def handleSQSmessage_eventgateway(self, sqsbody):
        
            try:
                qid=self.queueId(sqsbody)
                response=await self.processSQS(sqsbody, None)
                if response:
                    await self.alexaSendToEventGateway(json.dumps(response))

                try:
                    #self.log.info('Tokenrefresh? %s / %s' % (self.tokenRefresh, self.newGrant))
                    if self.newGrant:
                        await self.alexaGetTokenForNewGrant()
                    elif self.tokenRefresh or ('expires' in self.grant and datetime.datetime.now()>self.grant["expires"]):
                        await self.alexaRefreshToken()
                except:
                    self.log.info('Token refresh probably needed but failed', exc_info=True)
                    
                try:
                    if response["event"]["header"]['name']=='StateReport':
                        self.log.info('<- %s/%s %s %s' % (response["event"]["header"]['name'], response["event"]["endpoint"]['endpointId'], qid, self.suppressTokens(response)))
                    elif response["event"]["header"]['name'].startswith('Discover'):
                        self.log.info('<- %s %s %s' % (response["event"]["header"]['name'], qid, self.suppressTokens(response)))
                    elif "context" in response and "properties" in response["context"]:
                        self.log.info('<- %s %s/%s %s' % (qid, response["context"]["properties"][0]["name"], sqsbody["directive"]["header"]["messageId"], self.suppressTokens(response)))
                    else:
                        self.log.info('<- response/%s %s' % (sqsbody["directive"]["header"]["messageId"], response))
                except:
                    self.log.info('<- response/%s %s' % (sqsbody["directive"]["header"]["messageId"], response), exc_info=True)
                    
            except:
                self.log.error('Error in handleSQSMessage', exc_info=True)


        async def handleSQSmessage(self,sqsbody):
        
            try:
                #sqsbody=json.loads(msg.body)
                #self.log.info('Handling message '+sqsbody["directive"]["header"]["messageId"])
                qid=self.queueId(sqsbody)
                returnqueue=await self.connectReturnQueue(qid)
                response=await self.processSQS(sqsbody, returnqueue)
                if response:
                    #await self.sqs.send_message(QueueUrl=self.lambdaqueue,MessageBody=json.dumps(response))
                    await self.sqs.send_message(QueueUrl=returnqueue,MessageBody=json.dumps(response))

                try:
                    #self.log.info('Tokenrefresh? %s / %s' % (self.tokenRefresh, self.newGrant))
                    if self.newGrant:
                        await self.alexaGetTokenForNewGrant()
                    elif self.tokenRefresh or ('expires' in self.grant and datetime.datetime.now()>self.grant["expires"]):
                        await self.alexaRefreshToken()
                except:
                    self.log.info('Token refresh probably needed but failed', exc_info=True)
                    
                try:
                    if response["event"]["header"]['name']=='StateReport':
                        self.log.info('<- %s/%s %s %s' % (response["event"]["header"]['name'], response["event"]["endpoint"]['endpointId'], qid, self.suppressTokens(response)))
                    elif response["event"]["header"]['name'].startswith('Discover'):
                        self.log.info('<- %s %s %s' % (response["event"]["header"]['name'], qid, self.suppressTokens(response)))
                    elif "context" in response and "properties" in response["context"]:
                        self.log.info('<- %s %s/%s %s' % (qid, response["context"]["properties"][0]["name"], sqsbody["directive"]["header"]["messageId"], self.suppressTokens(response)))
                    else:
                        self.log.info('<- response/%s %s' % (sqsbody["directive"]["header"]["messageId"], response))
                except:
                    self.log.info('<- response/%s %s' % (sqsbody["directive"]["header"]["messageId"], response), exc_info=True)
                
            except:
                self.log.error('Error in handleSQSMessage', exc_info=True)
  
        
        async def connectQueue(self):

            while not self.sqsconnected:
                self.log.info('Trying to connect to queue...')
                try:
                    self.sofaqueue=await self.connectSQSqueue('sofa')
                    self.log.info('Connected to queue.')
                    #self.lambdaqueue=await self.connectSQSqueue('sofalambda')
                    if self.sofaqueue!=None: #and self.lambdaqueue!=None:
                        self.sqsconnected=True
                    else:
                        self.log.error('Error connecting to SQS queues.  Waiting 10 seconds to retry')
                        await asyncio.sleep(10)
                except:
                    self.log.error('Error connecting to SQS queues.  Waiting 10 seconds to retry', exc_info=True)
                    await asyncio.sleep(30)


        async def handleMessage(self, sqsitem, loop):

            try:
                #self.log.info('sqsitem: %s' % sqsitem['Body'])
                sqsbody=json.loads(sqsitem['Body'])
                await self.sqs.delete_message(QueueUrl=self.sofaqueue,ReceiptHandle=sqsitem['ReceiptHandle'])
                if sqsbody["directive"]["header"]["messageId"] in self.currentMessages:
                    self.log.info('-> %s/%s (retry ignored)' % (sqsbody["directive"]["header"]['name'], sqsbody["directive"]["header"]["messageId"]))
                else:
                    if sqsbody["directive"]["header"]['name']=='ReportState':
                        self.log.info('-> %s/%s  %s' % (sqsbody["directive"]["header"]['name'], sqsbody["directive"]["endpoint"]['endpointId'], self.suppressTokens(sqsbody)))
                    else:
                        self.log.info('-> %s/%s  %s' % (sqsbody["directive"]["header"]['name'], sqsbody["directive"]["header"]["messageId"], self.suppressTokens(sqsbody)))
                    self.currentMessages[sqsbody["directive"]["header"]["messageId"]]=sqsitem
                    await self.handleSQSmessage(sqsbody)
                    #self.msgThreads[sqsbody["directive"]["header"]["messageId"]]=self.messageSQSthread(sqsbody["directive"]["header"]["messageId"],sqsitem)
            except:
                try:
                    self.log.error('-> %s/%s Error Processing %s' % (sqsbody["directive"]["header"]['name'], sqsbody["directive"]["header"]["messageId"], sqsbody),exc_info=True)
                except:
                    self.log.error('->  Error Processing Message', exc_info=True)
                    
        def handleMessageGroup(self, message, loop):
            try:
                allmsg = asyncio.ensure_future(asyncio.gather(*[self.handleMessage(sqsitem, loop) for sqsitem in message['Messages']], loop=loop), loop=loop)
            except:
                self.log.error('Error handling message group', exc_info=True)
           
        async def pollSQSlong(self):
            self.sqsconnected=False
            done=False
            self.log.info('.. Starting polling loop')
            self.currentMessages={}
            while self.running:
                await self.connectQueue()
                try:
                    #self.log.info('Checking queue for messages (20sec max)')
                    message = await self.sqs.receive_message(QueueUrl=self.sofaqueue, WaitTimeSeconds=20)
                    #message=await self.sofaqueue.receive_messages(WaitTimeSeconds=20)
                    #self.log.info('.. Found %s messages in sqs queue' % len(message))
                    #self.log.info('.. message: %s' % message)
                    if 'Messages' in message:
                        self.loop.run_in_executor(self.messagepool, self.handleMessageGroup, message, self.loop)

                except:
                    self.sqsconnected=False
                    self.log.error('Error polling Amazon queue.  Waiting 30 seconds before attempting again.',exc_info=True)
                    time.sleep(30)


        def virtualControllers(self, itempath):

            try:
                return {}

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)

        async def virtualEventHandler(self, event, source, deviceId, message):
            
            try:
                if event=='DoorbellPress':
                    self.log.info('Doorbell Press: %s %s' % (deviceId, message))
                    await self.alexaSendToEventGateway(message)
                else:
                    self.log.info('Unknown event: %s %s %s' % (event, deviceId, message))
            except:
                self.log.error('Error in virtual event handler: %s %s %s' % (event, deviceId, message), exc_info=True)

        async def virtualChangeHandler(self, deviceId, change):
            
            try:
                if change['namespace']=='Alexa.ContactSensor':
                    self.log.info('Contact Sensor Change report: %s %s' % (deviceId, change))
                    changereport=await self.buildVirtualChangeReport(deviceId, change)
                    await self.alexaSendToEventGateway(changereport)
                    
            except:
                self.log.error('Error in virtual change handler: %s %s' % (deviceId, change), exc_info=True)

        async def buildVirtualChangeReport(self, deviceId, change):
            
            # This is cheese and should be replaced by generating the real changereport in dataset and then
            # just sending it, but due to formatting challenges, its built this way during test
            sample=datetime.datetime.now(datetime.timezone.utc).isoformat()[:-10]+"Z"
            change['timeOfSample']=sample

            return {
                        "event": {
                            "header": {
                                "name":"ChangeReport",
                                "payloadVersion": "3",
                                "messageId":str(uuid.uuid1()),
                                "namespace":"Alexa"
                            },
                            "endpoint": {
                                "endpointId": deviceId,
                                "scope": {
                                    "type": "BearerToken",
                                    "token": ""
                                }
                            },
                            "payload": {
                                "change": {
                                    "cause": {
                                        "type":"PHYSICAL_INTERACTION"
                                    },
                                    "properties": [ change ]
                                }
                            }
                        },
                        "context": {
                            "properties": [
                                        {
                                            "namespace": "Alexa.EndpointHealth",
                                            "name": "connectivity",
                                            "value": {
                                                "value": "OK"
                                            },
                                            "timeOfSample": sample,
                                            "uncertaintyInMilliseconds": 0
                                        }
                            ]
                        }
                    }
             


        async def alexaSendToEventGateway(self, body):
            
            try:
                try:
                    if datetime.datetime.now()>self.grant["expires"]:
                        await self.alexaRefreshToken()
                except:
                    self.log.error('Error checking token')
                    
                # set token after refresh if needed
                body['event']['endpoint']['scope']['token']=self.grant['access_token']
                url="https://api.amazonalexa.com/v3/events"
                headers = { "Content-type": "application/json", "Authorization": "Bearer %s" % self.grant['access_token'] }

                self.log.debug('Sending to alexa event gateway: %s' % body)

                async with aiohttp.ClientSession() as client:
                    response=await client.post(url, data=json.dumps(body), headers=headers)
                    if response.status==202:
                        self.log.debug('Proactive event succesfully sent to gateway')
                    else:
                        cresponse=await response.read()
                        cresponse=cresponse.decode()
                        self.log.info('Proactive Event failure: %s %s' % (response.status,cresponse))
            except:
                self.log.error('Error refreshing token', exc_info=True)


        async def alexaRefreshToken(self):
            
            try:
                tokenresponse={}
                self.log.info('Current grant: %s' % self.grant)
                url="https://api.amazon.com/auth/o2/token"
                headers = { "Content-type": "application/x-www-form-urlencoded;charset=UTF-8" }

                data = aiohttp.FormData()
                data.add_field("grant_type", "refresh_token")
                data.add_field("refresh_token", self.grant["refresh_token"])
                data.add_field("client_id", self.dataset.config["alexa_skill_client_id"])
                data.add_field("client_secret", self.dataset.config["alexa_skill_client_secret"])
                #data.add_field("code", self.grant["code"])

                async with aiohttp.ClientSession() as client:
                    response=await client.post(url, data=data, headers=headers)
                    tokenresponse=await response.read()
                    tokenresponse=tokenresponse.decode()
                    tokenresponse=json.loads(tokenresponse)
                
                expiretime=datetime.datetime.now()+datetime.timedelta(0,int(tokenresponse["expires_in"]))
                self.grant['access_token']=tokenresponse["access_token"]
                self.grant['refresh_token']=tokenresponse["refresh_token"]
                self.grant['expires']=datetime.datetime.now()+datetime.timedelta(0,int(tokenresponse["expires_in"]))
                self.saveJSON('alexagrant', self.grant )
                self.tokenRefresh=False
                self.log.info('New grant data: %s' % self.grant)
            except:
                self.log.error('Error refreshing token: %s' % tokenresponse, exc_info=True)


        async def alexaGetTokenForNewGrant(self):
            
            try:
                url="https://api.amazon.com/auth/o2/token"
                headers = { "Content-type": "application/x-www-form-urlencoded;charset=UTF-8" }

                data = aiohttp.FormData()
                data.add_field("grant_type", "authorization_code")
                data.add_field("code", self.grant["code"])
                data.add_field("client_id", self.dataset.config["alexa_skill_client_id"])
                data.add_field("client_secret", self.dataset.config["alexa_skill_client_secret"])

                async with aiohttp.ClientSession() as client:
                    response=await client.post(url, data=data, headers=headers)
                    tokenresponse=await response.read()
                    tokenresponse=tokenresponse.decode()
                    tokenresponse=json.loads(tokenresponse)
                
                self.log.info('++ first token from new grant: %s' % tokenresponse)

                expiretime=datetime.datetime.now()+datetime.timedelta(0,int(tokenresponse["expires_in"]))
                self.grant['access_token']=tokenresponse["access_token"]
                self.grant['refresh_token']=tokenresponse["refresh_token"]
                self.grant['expires']=datetime.datetime.now()+datetime.timedelta(0,int(tokenresponse["expires_in"]))
                self.saveJSON('alexagrant', self.grant )
                self.tokenRefresh=False
                self.newGrant=False
                self.log.info('New grant data: %s' % self.grant)
            except:
                self.log.error('Error refreshing token', exc_info=True)

        async def alexaAcceptGrant(self, message):
            
            try:
                self.log.info('++ new grant message: %s' % message)
                self.grant={'code': message['directive']['payload']['grant']['code'], 'token':message['directive']['payload']['grantee']['token']}
                self.saveJSON('alexagrant', self.grant )
                self.tokenRefresh=False
                self.newGrant=True
                return {
                        "event": {
                            "header": {
                                "messageId": str(uuid.uuid1()),
                                "namespace": "Alexa.Authorization",
                                "name": "AcceptGrant.Response",
                                "payloadVersion": "3"
                            },
                            "payload": {}
                        }
                }
            except:
                self.log.error('Error accepting grant', exc_info=True)
                return {
                        "event": {
                            "header": {
                                "messageId": str(uuid.uuid1()),
                                "namespace": "Alexa.Authorization",
                                "name": "ErrorResponse",
                                "payloadVersion": "3"
                            },
                            "payload": {
                                "type": "ACCEPT_GRANT_FAILED",
                                "message": "Failed to handle the AcceptGrant directive"
                            }
                         }
                }                

                
            
        def alexaDiscovery(self,messageId=None):
        
            if not messageId:
                messageId=str(uuid.uuid1())
            return {
                "event": {
                    "header": {
                        "namespace": "Alexa.Discovery",
                        "name": "Discover.Response",
                        "payloadVersion": "3",
                        "messageId":  messageId,
                    },
                    "payload": {
                        "endpoints": self.alexadevices()
                    }
                }
        }

        def alexadevices(self):
            
            try:
                alexadevs=[]
                for dev in self.dataset.devices:
                    try:
                        if dev in self.dataset.config['excluded_devices']:
                            alexadev=False
                        else:
                            if self.dataset.devices[dev]['displayCategories'][0] in self.dataset.config['allowed_types']:
                                alexadev=False
                                adev=copy.deepcopy(self.dataset.devices[dev])
                                for cap in self.dataset.devices[dev]['capabilities']:
                                    if not cap['interface'].startswith('Alexa'):
                                        adev['capabilities'].remove(cap)
                                        self.log.info('Trimmed non-alexa cap: %s' % cap)
                                    else:
                                        alexadev=True
                                if alexadev:
                                    self.log.info('Discovered device: %s %s' % (dev, adev))
                                    alexadevs.append(adev)
                    except:
                        self.log.error('Error processing device: %s' % dev, exc_info=True)
                self.log.info('Returning %s Alexa devices' % len(alexadevs) )
                return alexadevs
            except:
                self.log.error('Error getting alexa devices', exc_info=True)
                return {}

        async def virtualList(self, itempath, query={}):

            try:
                if itempath=='AlexaDevices':
                    return self.alexaDiscovery()
                if itempath=='allDevices':
                    return self.dataset.devices


                self.log.info('Itempath: %s' % itempath)
                return {}

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)



        def virtualControllerProperty(self, nativeObj, controllerProp):
        
            # Scenes have no properties
            return None

if __name__ == '__main__':
    adapter=alexaBridge(name='alexa')
    adapter.start()
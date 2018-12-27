#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

from sofabase import sofabase
from sofabase import adapterbase
import devices
from sofacollector import SofaCollector


import json
import asyncio
import concurrent.futures
import datetime
import uuid
import asyncio
import aiobotocore
import time

# This needs to be closely reworked, probably with AIOBOTOCORE https://github.com/aio-libs/aiobotocore

class alexaBridge(sofabase):

    class adapterProcess(SofaCollector.collectorAdapter):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.dataset.nativeDevices['scene']={}
            self.dataset.nativeDevices['activity']={}

            #self.definitions=definitions.Definitions
            self.log=log
            self.notify=notify
            self.running=True
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
                
        def suppressTokens(self,logmessage):


            #try:
            #    del logmessage['directive']['header']['correlationToken']
            #except:
            #    pass
         
            #try:
            #    del logmessage['directive']['endpoint']['scope']['token']
            #except:
            #    pass
        
            #try:
            #    del logmessage['event']['header']['correlationToken']
            #except:
            #    pass

            return logmessage

        def jsonDateHandler(self, obj):

            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            else:
                self.log.error('Found unknown object for json dump: (%s) %s' % (type(obj),obj))
            return None

        def saveJSON(self, jsonfilename, data):
        
            try:
                jsonfile = open(jsonfilename, 'wt')
                json.dump(data, jsonfile, ensure_ascii=False, default=self.jsonDateHandler)
                jsonfile.close()
            except:
                self.log.error('Error saving json to %s' % jsonfilename, exc_info=True)

            
        async def start(self):
            self.polltime=1
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

                
        async def processSQS(self,event):
        
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
                            #self.log.info('Discover Request.  Building response')
                                response=self.alexaDiscovery(messageId)
                            #self.log.info('Discover response complete:'+str(response))
                                return response
                        elif command=='ReportState':
                            response=await self.dataset.requestReportState(event['directive']['endpoint']['endpointId'])
                            #self.log.info('Reportstate: %s' % response)
                            return response
                        else:
                            #self.log.info('Correlation Token: %s' % event["directive"]["header"]['correlationToken'] )
                            if event["directive"]["header"]['name']in ['Activate','Deactivate']:
                                response=await self.activationStarted(event)  
                                await self.SQSearlyResponse(response)
                            
                            response=await self.dataset.sendDirectiveToAdapter(event)

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

        async def convertChangeToResponse(self, changereport):
        
            try:
                response={}
                if changereport:
                    response={ "event": { "header" : {"namespace": "Alexa", "name":"Response", "payloadVersion": "3", "messageId": str(uuid.uuid1()) } , "endpoint" : { "endpointId": changereport['event']['endpoint']['endpointId'] } , "payload": {} }, "context": { "properties" :  changereport['payload']['change']['properties'] } }
                return response
            except:
                self.log.error('Error converting change report: %s' % changereport, exc_info=True)

        async def activationStarted(self, event):
        
            try:
                response={ "event": { "header" : {"namespace": "Alexa.SceneController", "name":"ActivationStarted", "payloadVersion": "3", "messageId": str(uuid.uuid1()), 'correlationToken' : event["directive"]["header"]['correlationToken'] }, "endpoint" : { "endpointId": event['directive']['endpoint']['endpointId'], "scope":event["directive"]["endpoint"]['scope']} , "payload": { "timestamp":datetime.datetime.utcnow().isoformat() + "Z", "cause": { "type": "VOICE_INTERACTION"}} }, "context": {} }
                return response
            except:
                self.log.error('Error converting change report', exc_info=True)


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

        async def SQSearlyResponse(self, response):

            try:
                await self.sqs.send_message(QueueUrl=self.lambdaqueue,MessageBody=json.dumps(response))
                try:
                    self.log.info('<- %s/%s %s %s' % (response["event"]["header"]["name"], response["event"]["header"]["messageId"], self.suppressTokens(response)))
                except:
                    self.log.info('<- response %s' % response)

            except:
                self.log.error('Error sending back early response: %s' % response, exc_info=True)

        async def handleSQSmessage(self,sqsbody):
        
            try:
                #sqsbody=json.loads(msg.body)
                #self.log.info('Handling message '+sqsbody["directive"]["header"]["messageId"])
                response=await self.processSQS(sqsbody)
                if response:
                    await self.sqs.send_message(QueueUrl=self.lambdaqueue,MessageBody=json.dumps(response))

                try:
                    self.log.info('<- %s/%s %s' % (response["context"]["properties"][0]["name"], sqsbody["directive"]["header"]["messageId"],  self.suppressTokens(response)))
                except:
                    self.log.info('<- response/%s %s' % (sqsbody["directive"]["header"]["messageId"], response))
                    
            except:
                self.log.error('Error in handleSQSMessage', exc_info=True)
  
        
        async def pollSQSlong(self):
            sqsconnected=False
            while not sqsconnected:
                self.sofaqueue=await self.connectSQSqueue('sofa')
                self.lambdaqueue=await self.connectSQSqueue('sofalambda')
                if self.sofaqueue!=None and self.lambdaqueue!=None:
                    sqsconnected=True
                else:
                    self.log.error('Error connecting to SQS queues.  Waiting 10 seconds to retry')
                    time.sleep(10)
                
            done=False
            self.log.info('.. Starting polling loop')
            self.currentMessages={}
            while self.running:
                try:
                    #self.log.info('Checking queue for messages (20sec max)')
                    message = await self.sqs.receive_message(QueueUrl=self.sofaqueue, WaitTimeSeconds=20)
                    #message=await self.sofaqueue.receive_messages(WaitTimeSeconds=20)
                    #self.log.info('.. Found %s messages in sqs queue' % len(message))
                    #self.log.info('.. message: %s' % message)
                    if 'Messages' in message:
                        for sqsitem in message['Messages']:
                            #self.log.info('sqsitem: %s' % sqsitem['Body'])
                            sqsbody=json.loads(sqsitem['Body'])
                            await self.sqs.delete_message(QueueUrl=self.sofaqueue,ReceiptHandle=sqsitem['ReceiptHandle'])
                            try:
                                if sqsbody["directive"]["header"]["messageId"] in self.currentMessages:
                                    self.log.info('-> %s/%s (retry ignored)' % (sqsbody["directive"]["header"]['name'], sqsbody["directive"]["header"]["messageId"]))
                                else:
                                    self.log.info('-> %s/%s %s' % (sqsbody["directive"]["header"]['name'], sqsbody["directive"]["header"]["messageId"], self.suppressTokens(sqsbody)))
                                    self.currentMessages[sqsbody["directive"]["header"]["messageId"]]=sqsitem
                                    await self.handleSQSmessage(sqsbody)
                                    #self.msgThreads[sqsbody["directive"]["header"]["messageId"]]=self.messageSQSthread(sqsbody["directive"]["header"]["messageId"],sqsitem)
                            except:
                                self.log.error('-> %s/%s Error Processing %s' % (sqsbody["directive"]["header"]['name'], sqsbody["directive"]["header"]["messageId"], sqsbody),exc_info=True)

                except:
                    self.log.error('Error polling Amazon queue.  Waiting 30 seconds before attempting again.',exc_info=True)
                    time.sleep(30)


        def virtualControllers(self, itempath):

            try:
                return {}

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)


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
                                alexadev=True
                                for cap in self.dataset.devices[dev]['capabilities']:
                                    if not cap['interface'].startswith('Alexa'):
                                        alexadev=False
                                if alexadev:
                                    alexadevs.append(self.dataset.devices[dev])
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
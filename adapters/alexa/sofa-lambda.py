import boto3
import logging
import json
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):

    try:
        result=''
        logger.info('Starting Sofa SQS Lambda')
        sqs=connectSQS()
        if not sqs:
            return False
            
        qid=queueId(event)
        if not qid:
            return False

        sofaqueue=getSQSQueueURL(sqs, 'sofa')
        if sofaqueue:
            logger.info('Sofa queue url: %s' % sofaqueue)
            logger.info('Create return queue: %s' % qid)
            returnqueue=createReturnQueue(sqs,qid)
            if returnqueue:
                logger.info('Move message to sofa queue: %s' % event)
                messageId=sendSQSqueue(sqs, sofaqueue, event)
                if messageId:
                    logger.info('Waiting to process result')
                    result=checkSQSqueue(sqs, returnqueue, messageId)

        logger.info('Final result: %s' % result)
        deleteReturnQueue(sqs,returnqueue)
        return result
        
    except:
        logger.error('Error with lambda handler', exc_info=True)
        return False

def queueId(message):
    try:
        logger.info('Message: %s' % message)
        if 'correlationToken' in message['directive']['header']:
            qid=message['directive']['header']['correlationToken']
        elif 'messageId' in message['directive']['header']:
            qid=message['directive']['header']['messageId']
        else:
            logger.error('Message did not have a messageId or Correlation token', exc_info=True)
            return None
        qid=qid[-10:-2]
        delchars=str.maketrans('','','+=-!/&$\\')
        return 'sofa-%s' % qid.translate(delchars)
    except KeyError:
        logger.error('Message did not have necessary fields')
        return None
    except:
        logger.error('Error building queue ID', exc_info=True)
        return None

def connectSQS():
    
    try:
        # when this is run on Lambda, it should get your credentials automatically from the IAM Exection Role
        sqs=boto3.client('sqs',region_name="us-east-1")
        return sqs
    except:
        logger.error("Error connecting to SQS",exc_info=True)
        return None


def getSQSQueueURL(sqs, queuename):

    try:
        return sqs.get_queue_url(QueueName=queuename)['QueueUrl']
    except:
        logger.error("Could not get queue URL for %s " % queuename,exc_info=True)
        return None


def getSQSqueue(sqs,queuename):
    
    try:
        queue = sqs.get_queue_by_name(QueueName=queuename)
        return queue
    except:
        logger.error("Could not connect to queue "+str(queuename),exc_info=True)
        return None
        
def createReturnQueue(sqs, qname):
    
    try:
        queue=sqs.create_queue(QueueName=qname)
        return queue['QueueUrl']
    except:
        logger.error('Error creating return queue: %s' % qname, exc_info=True)
        return None

def deleteReturnQueue(sqs, returnqueue):
    
    try:
        sqs.delete_queue(QueueUrl=returnqueue)
        return True
    except:
        logger.error('Error deleting return queue', exc_info=True)
        return False


def sendSQSqueue(sqs, queuename, message):
    
    try:
        if 'correlationToken' in message['directive']['header']:
            messageId=message['directive']['header']['correlationToken']
        else:
            messageId=message['directive']['header']['messageId']
        response = sqs.send_message(QueueUrl=queuename, MessageBody=json.dumps(message))
        return messageId
    except:
        logger.error("Error sending on queue",exc_info=True)
        return None
        

def checkSQSqueue(sqs, queuename, messageId):

    try:
        tries=1
        result=""
        while tries<4:
            response=sqs.receive_message(QueueUrl=queuename, MaxNumberOfMessages=10, WaitTimeSeconds=10)
            logger.info('Found %s items on pass %s' % (len(response['Messages']), tries))
            messages=response['Messages']
            for sqsitem in messages:
                try:
                    sqsdata=json.loads(sqsitem['Body'])
                    if 'correlationToken' in sqsdata["event"]["header"]:
                        logger.info('Looking for '+messageId+' vs '+sqsdata["event"]["header"]['correlationToken'])
                        if messageId==sqsdata["event"]["header"]['correlationToken']:
                            logger.info('Processing Item: %s' % sqsitem['Body'])
                            return sqsdata
                    elif 'messageId' in sqsdata["event"]["header"]:
                        logger.info('Looking for '+messageId+' vs '+sqsdata["event"]["header"]["messageId"])
                        if messageId==sqsdata["event"]["header"]["messageId"]:
                            logger.info('Processing Item: '+str(sqsitem.__dict__))
                            return sqsdata
                except:
                    logger.error("Error handling queue item message",exc_info=True)
    
            tries=tries+1
            logger.warn('Did not find message ID. %s more attempts remain' % 3-tries)
        return None
    
    except:
        logger.error('Error with checkSQSqueue', exc_info=True)
        return None


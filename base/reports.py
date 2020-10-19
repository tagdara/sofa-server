import sys
import uuid
import datetime
import copy
import asyncio
import datetime

def alexa_json_filter(data, namespace="", level=0):
        
    # this function allows for logging alexa smarthome API commands while reducing unnecessary fields
    
    try:
        out_data={}
        
        if data=={}:
            return ""
        elif 'directive' in data:
            out_data['type']='Directive'
            out_data['name']=data['directive']['header']['name']
            if '.' in data['directive']['header']['namespace']:
                out_data['namespace']=data['directive']['header']['namespace'].split('.')[1]
            else:
                out_data['namespace']=data['directive']['header']['namespace'] # some commands like reportstate have just 'Alexa' as the namespace
                
            if 'endpoint' in data['directive'] and 'endpointId' in data['directive']['endpoint']:
                out_data['endpointId']=data['directive']['endpoint']['endpointId']
            else:
                out_data['endpointId']=""
            out_text="%s: %s/%s %s" % (out_data['type'], out_data['namespace'], out_data['name'], out_data['endpointId'])
            
        elif 'event' in data:
            # CHEESE: Alexa API formatting is weird with the placement of payload
            out_data['type']='Event'
            out_data['name']=data['event']['header']['name']
            if data['event']['header']['name']=='ErrorResponse':
                return "%s: %s %s" % (out_data['name'], out_data['endpointId'], data['event']['payload'])    
            
            if data['event']['header']['namespace'].endswith('Discovery'):
                if 'payload' in data['event'] and 'endpoints' in data['event']['payload']:
                    out_data['endpointId']='['
                    for item in data['event']['payload']['endpoints']:
                        out_data['endpointId']+=item['endpointId']+" "
                out_text="%s: %s" % (out_data['name'], out_data['endpointId'])    
                return out_text

            out_data['endpointId']=data['event']['endpoint']['endpointId']
            out_text="%s: %s" % (out_data['name'], out_data['endpointId'])

            if 'payload' in data['event'] and data['event']['payload']:
                out_text+=" %s" % data['event']['payload']
            elif 'payload' in data and data['payload']:
                out_text+=" %s" % data['payload']
                
            if namespace:
                out_text+=" %s:" % namespace
                if 'context' in data and 'properties' in data['context']:
                    for prop in data['context']['properties']:
                        if prop['namespace'].endswith(namespace):
                            out_text+=" %s : %s" % (prop['name'], prop['value'])

        else:
            # unknown response to filter
            return data

        return out_text
    except:
        #self.log.error('Error parsing alexa json', exc_info=True)
        return data

# =========================

def ActivationStarted(endpointId, correlationToken="", bearerToken="", cause="PHYSICAL_INTERACTION"):
    
    return {
        "context" : { },
        "event": {
            "header": {
                "messageId": str(uuid.uuid1()),
                "correlationToken": correlationToken,
                "namespace": "Alexa.SceneController",
                "name": "ActivationStarted",
                "payloadVersion": "3"
            },
            "endpoint": {
                "scope": {
                    "type": "BearerToken",
                    "token": bearerToken,
                },
                "endpointId": endpointId,
            },
            "payload": {
                "cause" : {
                    "type" : cause
                },
                "timestamp" : datetime.datetime.now(datetime.timezone.utc).isoformat()[:-10]+"Z"
            }
        }
    }

def AddOrUpdateReport(endpoints, payloadVersion=3):
    
    return {
            "event": {
                "header": {
                    "namespace": "Alexa.Discovery",
                    "name": "AddOrUpdateReport",
                    "payloadVersion": payloadVersion,
                    "messageId": str(uuid.uuid1()),
                },
                "payload": {
                    "endpoints": endpoints
                }
            }
        }

def ChangeReport(endpointId, changedPropertyStates, unchangedPropertyStates=[], cause="APP_INTERACTION", payloadVersion=3, namespace="Alexa", cookie={}):  

    return  {
            "event": {
                "header": {
                    "name":"ChangeReport",
                    "payloadVersion": payloadVersion,
                    "messageId": str(uuid.uuid1()),
                    "namespace": namespace
                },
                "endpoint": {
                    "endpointId": endpointId,
                    "cookie": cookie,
                },
                "payload": {
                    "change": {
                        "cause": {
                            "type": cause
                        },
                        "properties": changedPropertyStates
                    }
                }
            },
            "context": {
                "properties": unchangedPropertyStates
            },
        }


def DeleteReport(endpoints=[], bearer_token=""):
    
    return  {
                "event": {
                    "header": {
                        "messageId": str(uuid.uuid1()),
                        "name": "DeleteReport",
                        "namespace": "Alexa.Discovery",
                        "payloadVersion": "3"
                    },
                    "payload": {
                        "endpoints": endpoints,
                        "scope": {
                            "type": "BearerToken",
                            "token": bearerToken
                        }
                    }
                }
            }

def Discover(endpoints=[], bearer_token=""):
 
    return  {
                "directive": {
                    "header": {
                        "namespace": "Alexa.Discovery", 
                        "name": "Discover", 
                        "messageId": str(uuid.uuid1()),
                        "payloadVersion": "3"
                    },
                    "payload": {
                        "scope": {
                            "type": "BearerToken",
                            "token": bearer_token,
                        }
                    }
                }
            }

def DiscoveryResponse(endpoints=[]):
    
    return  {
                "event": {
                    "header": {
                        "namespace": "Alexa.Discovery",
                        "name": "Discovery.Response",
                        "payloadVersion": "3",
                        "messageId":  str(uuid.uuid1()),
                    },
                    "payload": {
                        "endpoints": endpoints        
                    }
                }
            }

def DoorbellPress(endpointId, cause="PHYSICAL_INTERACTION", bearerToken=""):
    
    return {
            "context": {},
            "event": {
                "header": {
                    "messageId": str(uuid.uuid1()),
                    "namespace" : "Alexa.DoorbellEventSource",
                    "name": "DoorbellPress",
                    "payloadVersion": "3"
                },
                "endpoint": {
                    "scope": {
                        "type": "BearerToken",
                        "token": bearerToken
                    },
                    "endpointId": endpointId
                },
                "payload" : {
                    "cause": {
                        "type": cause
                    },
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()[:-10]+"Z"
                }
            }
        }


        
def ErrorResponse(endpointId, error_type, message, payload={}, messageId=None, correlationToken=None, bearerToken=""):

    error_types=[  "ALREADY_IN_OPERATION","BRIDGE_UNREACHABLE","CLOUD_CONTROL_DISABLED","ENDPOINT_BUSY", "ENDPOINT_LOW_POWER", "ENDPOINT_UNREACHABLE", 
                        "EXPIRED_AUTHORIZATION_CREDENTIAL","FIRMWARE_OUT_OF_DATE", "HARDWARE_MALFUNCTION", "INSUFFICIENT_PERMISSIONS", "INTERNAL_ERROR", 
                        "INVALID_AUTHORIZATION_CREDENTIAL", "INVALID_DIRECTIVE", "INVALID_VALUE", "NO_SUCH_ENDPOINT", "NOT_CALIBRATED", 
                        "NOT_SUPPORTED_IN_CURRENT_MODE", "NOT_IN_OPERATION", "POWER_LEVEL_NOT_SUPPORTED", "RATE_LIMIT_EXCEEDED", 
                        "TEMPERATURE_VALUE_OUT_OF_RANGE","TOO_MANY_FAILED_ATTEMPTS","VALUE_OUT_OF_RANGE"
                    ]

    if not messageId:
        messageId=str(uuid.uuid1())
        
    if error_type not in error_types:
        error_type="INTERNAL_ERROR"
        
    payload['type']=error_type
    payload['message']=message
    
    error = { 
            "event": {
                "header": {
                    "namespace": "Alexa",
                    "name": "ErrorResponse",
                    "messageId": messageId,
                    #"correlationToken": "<an opaque correlation token>",
                    "payloadVersion": "3"
                },
                "endpoint":{
                    "scope":{
                        "type":"BearerToken",
                        "token":bearerToken
                    },
                    "endpointId": endpointId
                },
                "payload": payload
            }
        }
                
    if correlationToken:
        error['event']['header']['correlationToken']=correlationToken
        
    return error


def ReportState(endpointId, namespace='Alexa', correlationToken='' , bearerToken='', cookie={}):

        return  {
            "directive": {
                "header": {
                    "name":"ReportState",
                    "payloadVersion": 3,
                    "messageId": str(uuid.uuid1()),
                    "namespace": namespace,
                    "correlationToken":correlationToken
                },
                "endpoint": {
                    "endpointId": endpointId,
                    "scope": {
                        "type": "BearerToken",
                        "token": bearerToken
                    },     
                    "cookie": cookie
                },
                "payload": {}
            },
        }
        
def Response(endpointId, context_properties, namespace="Alexa", correlationToken='', controller='', payload={}, override={}, payloadVersion=3):

    return {
        "event": {
            "header": {
                "name":"Response",
                "payloadVersion": payloadVersion,
                "messageId": str(uuid.uuid1()),
                "namespace": namespace,
                "correlationToken":correlationToken
            },
            "endpoint": {
                "endpointId": endpointId
            }
        },
        "context": {
            "properties": context_properties
        },
        "payload": payload
    }


def StateReport(endpointId, namespace='Alexa', correlationToken=None, bearerToken='', payloadVersion=3, cookie={}, payload={}, propertyStates=[]):
        
    if not correlationToken:
        correlationToken=str(uuid.uuid1())
        
    return  {
        "event": {
            "header": {
                "name":"StateReport",
                "payloadVersion": payloadVersion,
                "messageId": str(uuid.uuid1()),
                "namespace": namespace,
                "correlationToken":correlationToken
            },
            "endpoint": {
                "endpointId": endpointId,
                "scope": {
                    "type": "BearerToken",
                    "token": bearerToken
                },     
                "cookie": cookie
            },
            "payload": payload
        },
        "context": {
            "properties": propertyStates
        }
    }
        

if __name__ == '__main__':
    pass
    
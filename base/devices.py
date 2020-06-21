import sys
import uuid
import datetime
import copy
import asyncio

class capabilityInterface(object):

    def __init__(self, device=None):
        self.device=device
        if device:
            self.path=device.path
            self.adapter=device.adapter
            self.log=device.log
            self.nativeObject=self.device.native
            self.deviceid=self.device.path.split('/')[2]
    
    @property
    def commands(self):
        #deprecated
        return self.props
    
    @property
    def interface(self):
        return "%s.%s" % (self.namespace, self.controller)
        
    @property
    def version(self):
        if hasattr(self, '_version'):
            return self._version
        else:
            return "3"
            
    @property
    def capabilityType(self):
        return "%sInterface" % self.namespace
        
    @property
    def proactivelyReported(self):
        if hasattr(self, '_proactivelyReported'):
            return self._proactivelyReported
        else:
            return True

    @property
    def retrievable(self):
        if hasattr(self, '_retrievable'):
            return self._retrievable
        else:
            return True
        
    @property
    def namespace(self):
        if hasattr(self, '_namespace'):
            return self._namespace
        else:
            return "Alexa"
            
    @property
    def properties(self):
        supported=[]
        for prop in self.props:
            supported.append({"name": prop})
        baseprop={ "proactivelyReported": self.proactivelyReported, "retrievable": self.retrievable }
        if supported:
            baseprop["supported"]=supported
        if hasattr(self, 'nonControllable'):
            baseprop["nonControllable"]=self.nonControllable

        return baseprop

    @property
    def capability(self):
        basecapability={"interface":self.interface, "version": self.version, "type": self.capabilityType, "properties": self.properties}
        if self.configuration:
            basecapability['configuration']=self.configuration
            
        return basecapability
        
    @property
    def configuration(self):
        return {}
        
    @property            
    def directives(self):
        return {}

    @property          
    def props(self):
        return {}
    
    @property
    def state(self):
        supported=[]
        
        for prop in self.props:

            try:
                data={
                        "name": prop,
                        "value": getattr(self, prop),
                        "namespace":self.interface, 
                        "uncertaintyInMilliseconds": 0, 
                        "timeOfSample":datetime.datetime.now(datetime.timezone.utc).isoformat()[:-10]+"Z"
                    }
                try:
                    data['instance']=self.instance
                except:
                    pass
                supported.append(data)

            except:
                self.log.error('Error adding property to state report: %s %s' % (prop, sys.exc_info()))
        
        return supported



# Work in progress - very different from other device types        
class CameraStreamController(capabilityInterface):

    def __init__(self, device=None):
        self.streaming=False
        self.heartbeat=None
        super().__init__(device=device)

    @property
    def controller(self):
        return "CameraStreamController"

    @property
    def capability(self):
        return {"interface":self.interface, "version": self.version, "type": self.capabilityType, "cameraStreamConfigurations": self.cameraStreamConfigurations}

    @property
    def cameraStreamConfigurations(self):
        return []

    @property
    def properties(self):
        # not supported on cameras
        return {}

    @property            
    def directives(self):
        return { 'InitializeCameraStreams' : { "cameraStreams": "list" }, "KeepAlive": {} }

    @property          
    def props(self):
        return {}
        
    async def KeepAlive(self, correlationToken="", bearerToken=""):
        self.log.info('.. keepalive: %s' % self.device.friendlyName)
        self.heartbeat=datetime.datetime.now()



class StateController(capabilityInterface):

    def __init__(self, device=None):
        self.savedState={}
        super().__init__(device=device)
    
    @property
    def controller(self):
        return "StateController"
    
    @property            
    def directives(self):
        return { 'Capture' : {}, 'Reset':{}}

    @property          
    def props(self):
        return { 'savedState' : { "value": "dictionary" }}

    async def Capture(self, correlationToken=''):
        
        try:
            newstate=copy.deepcopy(self.device.propertyStates)
            # this prevents recursive state from increasing object size
            for propstate in newstate:
                if propstate['name']=='savedState':
                    newstate.remove(propstate)
            self.savedState=newstate
            self.log.info('.. Captured state %s: %s' % (self.device.endpointId, self.savedState))
        except:
            self.log.error('!! Error capturing state for %s' % self.device.endpointId)

    async def Reset(self, correlationToken=''):
        
        skip_controllers=['Alexa.EndpointHealth', 'Alexa.StateController', 'Sofa.StateController']
        
        try:
            powerstate=False
            self.log.info('.. Current state %s: %s' % (self.device.endpointId, self.device.propertyStates))
            self.log.info('.. Restoring state %s: %s' % (self.device.endpointId, self.savedState))
            
            newprops={}
            for prop in self.device.propertyStates:
                if prop['namespace'] not in skip_controllers:
                    propname="%s.%s" % (prop['namespace'], prop['name'])
                    newprops[propname]=prop['value']
                
            oldprops={}
            for prop in self.savedState:
                if prop['namespace'] not in skip_controllers:
                    propname="%s.%s" % (prop['namespace'], prop['name'])
                    oldprops[propname]=prop['value']


            powerOff=False
            # This is a shim to deal with brightness conflicts between the colorcontroller and the brightness controller
            if 'Alexa.BrightnessController.brightness' in oldprops and 'Alexa.ColorController.color' in oldprops:
                if oldprops['Alexa.BrightnessController.brightness']!=int(round(oldprops['Alexa.ColorController.color']['brightness'],2)*100):
                    self.log.warn('Warning: brightness (%s) and color brightness (%s) do not match' % (oldprops['Alexa.BrightnessController.brightness'], int(round(oldprops['Alexa.ColorController.color']['brightness'],2)*100)))
                    # it seems like the right answer is normally in the brightness value so overlaying this to minimize
                    # the number of required commands on color bulbs.
                    oldprops['Alexa.ColorController.color']['brightness']=oldprops['Alexa.BrightnessController.brightness']/100

            for prop in oldprops:
                if prop in newprops:
                    #if 1==1:  # do it anyway right now because some of the adapters respond too slow or async to changes
                    if oldprops[prop]!=newprops[prop]:
                        self.log.info('Difference discovered %s - now %s was %s' % (prop, oldprops[prop], newprops[prop]))
                        if prop=='Alexa.BrightnessController.brightness' and 'Alexa.ColorController.color' not in oldprops:
                            await self.device.BrightnessController.SetBrightness({"brightness": oldprops[prop]} )
                        elif prop=='Alexa.ColorController.color':
                            await self.device.ColorController.SetColor({"color" : oldprops[prop]} )
                        elif prop=='Alexa.PowerController.powerState':
                            if oldprops[prop]=='ON':
                                await self.device.PowerController.TurnOn()
                            else:
                                powerOff=True
                                # This has to be done last or the other settings will either miss or reset the on
                                # For lights that are on, bri and color have poweron built in

            if powerOff:
                await self.device.PowerController.TurnOff()               
                 
        except:
            self.log.error('!! Error reset state for %s' % self.device.endpointId, exc_info=True)            

class BrightnessController(capabilityInterface):
    
    @property
    def controller(self):
        return "BrightnessController"

    @property            
    def directives(self):
        return { 'SetBrightness' : { 'brightness': "integer" }}

    @property          
    def props(self):
        return { 'brightness' : { "value": "integer" }}



class PowerLevelController(capabilityInterface):
    
    @property
    def controller(self):
        return "PowerLevelController"

    @property            
    def directives(self):
        return { 'SetPowerLevel' : { "powerLevel": "integer" }}

    @property          
    def props(self):
        return { 'powerLevel' : { "value": "integer" }}


class EnergySensor(capabilityInterface):

    @property
    def controller(self):
        return "EnergySensor"

    @property          
    def props(self):
        return { 'voltage' : { "value": "integer" }, "current": { "value": "integer" }, "power" : { "value": "integer" }, "total" : { "value": "integer" } }

    @property
    def namespace(self):
        return "Sofa"

    @property            
    def voltage(self):
        return 0

    @property            
    def current(self):
        return 0
            
    @property            
    def power(self):
        return 0

    @property            
    def total(self):
        return 0


class ColorController(capabilityInterface):
    
    @property
    def controller(self):
        return "ColorController"

    @property            
    def directives(self):
        return { "SetColor" : { "color": { "hue": "decimal", "saturation": 'decimal', "brightness": "decimal" }}}

    @property          
    def props(self):
        return { "color": { "hue": "decimal", "saturation": 'decimal', "brightness": "decimal" }}


class ColorTemperatureController(capabilityInterface):
    
    @property
    def controller(self):
        return "ColorTemperatureController"

    @property            
    def directives(self):
        return { 'SetColorTemperature' : { "colorTemperatureInKelvin" : "integer" }}

    @property          
    def props(self):
        return { 'colorTemperatureInKelvin': { "value": "integer" }}


class InputController(capabilityInterface):
   
    def __init__(self, device=None, inputs=[]):
        self.savedState={}
        self._inputs=inputs
        super().__init__(device=device)
    
    @property
    def controller(self):
        return "InputController"

    @property            
    def directives(self):
        return { "SelectInput": { "input": "string" }}

    @property          
    def props(self):
        return { "input" : { "value" : "string" }}

    @property
    def input(self):
        return self._input
    
    @input.setter
    def input(self, value):
        self._input=value

    def updateInput(self, value):
        self.inputName=value
        
    def SelectInput(self, value):
        self.inputName=value            

    @property
    def inputs(self):
        inputlist=[]
        try:
            for inp in self._inputs:
                inputlist.append({'name':inp})
        except:
            pass
        return inputlist

    @property
    def capability(self):
        basecapability={"interface":self.interface, "version": self.version, "type": self.capabilityType, "properties": self.properties}
        if self.inputs:
            basecapability['inputs']=self.inputs
        if self.configuration:
            basecapability['configuration']=self.configuration
            
        return basecapability


class ModeController(capabilityInterface):
   
    def __init__(self, name='ModeController', device=None, friendlyNames=[], supportedModes=[], devicetype=None, nonControllable=False):
        self.name=name
        self.device=device
        self._supportedModes=supportedModes
        self.nonControllable=nonControllable
        
        self._friendlyNames=friendlyNames
        if not self._friendlyNames:
            self._friendlyNames=[self.name]
            
        self._devicetype=devicetype
        if not self._devicetype:
            try:
                self._devicetype=self.device._displayCategories[0].capitalize()
            except:
                self._devicetype="Mode"
        
        super().__init__(device=device)

    @property
    def mode(self):
        return "Unknown"

    @property
    def controller(self):
        return "ModeController"
    
    @property
    def ordered(self):
        return False
        
    @property
    def locale(self):
        return "en-US"

    @property
    def instance(self):
        return "%s.%s" % (self._devicetype, self.name)
        
    @property 
    def friendlyNames(self):
        fns=[]
        for fn in self._friendlyNames:
            fns.append({ "@type": "text", "value": { "text": fn, "locale": self.locale }})
        return fns 

    @property
    def capabilityResources(self):
        return { "friendlyNames": self.friendlyNames }

    @property            
    def directives(self):
        return { "SetMode": { "mode": "string" }}

    @property          
    def props(self):
        return { "mode" : { "value" : "string" }}
        
    @property
    def configuration(self):
        return { "ordered": self.ordered, "supportedModes": self.supportedModes }

    @property
    def supportedModes(self):
        sms=[]
        for sm in self._supportedModes:
            sms.append( {   "value": "%s.%s" % (self.name,sm), 
                            "modeResources": { 
                                "friendlyNames": [{ "@type": "text", "value": { "text": self._supportedModes[sm], "locale": self.locale }}],
                            }
                        })
        return sms 

    @property
    def capability(self):
        basecapability={"interface":self.interface, "version": self.version, "type": self.capabilityType, "instance": self.instance, "properties": self.properties}
        if self.capabilityResources:
            basecapability['capabilityResources']=self.capabilityResources
        if self.configuration:
            basecapability['configuration']=self.configuration
            
        return basecapability
 
class RemoteController(capabilityInterface):
    
    @property
    def controller(self):
        return "RemoteController"
        
    @property
    def namespace(self):
        return "Sofa"

    @property            
    def directives(self):
        return { "PressRemoteButton": { "buttonName": "string" }}

    @property          
    def props(self):
        return {}
    
class LockController(capabilityInterface):
    
    @property
    def controller(self):
        return "LockController"

    @property            
    def directives(self):
        return { "Lock": {}, "Unlock": {} }

    @property          
    def props(self):
        return { "lockState" : { "value" : "string" }}

class PowerController(capabilityInterface):
    
    @property
    def controller(self):
        return "PowerController"

    @property            
    def directives(self):
        return { "TurnOn": {}, "TurnOff": {} }

    @property          
    def props(self):
        return { "powerState" : { "value": "string" }}


class ButtonController(capabilityInterface):
    
    @property            
    def controller(self):
        return 'ButtonController'

    @property
    def namespace(self):
        return "Sofa"

    @property            
    def directives(self):
        return { "Press": {}, "Hold": { "duration" : "integer" }, "Release": {} }

    @property          
    def props(self):
        return { "pressState" : { "value": "string" }}

            
class SceneController(capabilityInterface):
    
    @property
    def controller(self):
        return "SceneController"

    @property            
    def directives(self):
        return { "Activate": {}, "Deactivate": {} }

    @property          
    def props(self):
        return {}
        
    def ActivationStarted(self, correlationToken="", bearerToken=""):
        
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
                    "endpointId": self.device.endpointId,
                },
                "payload": {
                    "cause" : {
                        "type" : "PHYSICAL_INTERACTION"
                    },
                    "timestamp" : datetime.datetime.now(datetime.timezone.utc).isoformat()[:-10]+"Z"
                }
            }
        }

class TemperatureSensor(capabilityInterface):
    
    def __init__(self, device=None, scale="FAHRENHEIT"):
        self.scale=scale
        super().__init__(device=device)

    @property
    def controller(self):
        return "TemperatureSensor"
        
    @property            
    def directives(self):
        return {}

    @property          
    def props(self):
        return {"temperature": { "value" : "decimal", "scale":"string"}}

    @property
    def state(self):
        thisState=super().state
        for item in thisState:
            if item['name'] in ["temperature", "targetSetpoint", "lowerSetpoint", "upperSetpoint"]:
                item['value']={'value': item['value'], 'scale':self.scale}
                
        return thisState

class SwitchController(capabilityInterface):
    
    @property
    def controller(self):
        return "SwitchController"

    @property            
    def directives(self):
        return { "SetOnLevel": { "onLevel": "percentage"} }

    @property          
    def props(self):
        return { "pressState" : { "value": "string" }, "onLevel": { "value": "percentage" }}

    def updatePressState(self, value):
        if value=="ON":
            self.pressState="ON"
        elif value=="OFF":
            self.pressState="OFF"
        else:
            self.log.warn('Invalid PressState value: %s' % value)  


class ThermostatController(capabilityInterface):

    def __init__(self, device=None, scale="FAHRENHEIT", supportedModes=["HEAT","COOL","AUTO","OFF"], supportsScheduling=False, supportedRange=[60,90]):
        self.scale=scale
        self.supportedModes=supportedModes
        self.supportsScheduling=supportsScheduling
        self.supportedRange=supportedRange
        super().__init__(device=device)
    
    @property
    def controller(self):
        return "ThermostatController"

    @property
    def configuration(self):
        return {"supportsScheduling": self.supportsScheduling, "supportedModes": self.supportedModes, "supportedRange": self.supportedRange }

    @property            
    def directives(self):
        return { "SetTargetTemperature": { "targetSetpoint": { "value": "integer", "scale":"string" }}, "SetThermostatMode": {"thermostatMode": {"value": "string"}} }
        
    @property          
    def props(self):
        return { "targetSetpoint" : { "value":"integer", "scale":"string" }, "thermostatMode": { "value" : "string" }}

    @property
    def state(self):
        thisState=super().state
        for item in thisState:
            if item['name'] in ["temperature", "targetSetpoint", "lowerSetpoint", "upperSetpoint"]:
                item['value']={'value': item['value'], 'scale':self.scale}
                
        return thisState
        

class LogicController(capabilityInterface):
    
    @property
    def controller(self):
        return "LogicController"
        
    @property
    def namespace(self):
        return "Sofa"
    
    @property
    def time(self):
        # should we really be returning UTC? datetime.datetime.now(datetime.timezone.utc).isoformat()[:-10]+"Z"
        return datetime.datetime.now()
 
    @property
    def sunset(self):
        # should we really be returning UTC? datetime.datetime.now(datetime.timezone.utc).isoformat()[:-10]+"Z"
        return datetime.datetime.now()

    @property
    def sunrise(self):
        # should we really be returning UTC? datetime.datetime.now(datetime.timezone.utc).isoformat()[:-10]+"Z"
        return datetime.datetime.now()

        
    @property            
    def directives(self):
        return {    "Delay": { "duration": "integer" }, 
                    "Alert": { "message": { "text":"string", "image":"string" }},
                    "Wait": {}
                }
        
    @property          
    def props(self):
        return { "time": { "start":"time", "end":"time" }, "sunrise": { "value": "time"}, "sunset": { "value": "time"} }

        
class MusicController(capabilityInterface):
    

    @property
    def controller(self):
        return "MusicController"
        
    @property
    def namespace(self):
        return "Sofa"

    @property            
    def directives(self):
        return {    "PlayFavorite": { "favorite": "string" }, 
                    "Play": {},
                    "Pause": {},
                    "Stop": {},
                    "Previous": {},
                    "Skip": {}
                }
        
    @property          
    def props(self):
        return {    "artist": { "value" : "string"}, "album": { "value" : "string"}, "title" : { "value" : "string"}, "url": { "value" : "string" },
                    "art": { "value" : "string"}, "linked": { "value" : "string"}, "playbackState": { "value" : "string"},
        }
            

class SpeakerController(capabilityInterface):
    
    @property
    def controller(self):
        return "SpeakerController"
        
    @property
    def namespace(self):
        return "Sofa"

    @property            
    def directives(self):
        return {    "SetVolume": { "volume": "percentage" }, 
                    "SetMute": { "mute" : "string" }
                }
   
    @property          
    def props(self):
        return { "volume": { "value" : "percentage"}, "mute": { "value" : "string"}}



class SurroundController(capabilityInterface):
    
    def __init__(self, device=None, inputs=[]):
        self.savedState={}
        self._inputs=inputs
        super().__init__(device=device)
        
    @property
    def inputs(self):
        inputlist=[]
        try:
            for inp in self._inputs:
                inputlist.append({'name':inp})
        except:
            pass
        return inputlist
        
    @property
    def controller(self):
        return "SurroundController"
        
    @property
    def namespace(self):
        return "Sofa"

    @property            
    def directives(self):
        return {    "SetSurround": { "surround": "string" }, 
                    "SetDecoder": { "decoder" : "string" }
                }
        
    @property          
    def props(self):
        return { "surround": { "value" : "string"}, "decoder": { "value" : "string"}}

    @property
    def capability(self):
        basecapability={"interface":self.interface, "version": self.version, "type": self.capabilityType, "properties": self.properties}
        if self.inputs:
            basecapability['inputs']=self.inputs
        if self.configuration:
            basecapability['configuration']=self.configuration
            
        return basecapability


class AreaController(capabilityInterface):
    
    @property
    def controller(self):
        return "AreaController"

    @property
    def namespace(self):
        return "Sofa"

    @property            
    def directives(self):
        return { "SetChildren": { "children": "list" }, "SetShortcuts": { "shortcuts": "list" }, "SetScene": {"scene":"string"}}
        
    @property          
    def props(self):
        return { "children": { "value" : "list"}, "shortcuts": {"value": "list"}, "scene" : {"value":"string"}}



class MotionSensor(capabilityInterface):
    
    @property
    def controller(self):
        return "MotionSensor"

    @property            
    def directives(self):
        return {}
        
    @property          
    def props(self):
        return { "detectionState": { "value" : "string"}}

class ContactSensor(capabilityInterface):
    
    @property
    def controller(self):
        return "ContactSensor"

    @property            
    def directives(self):
        return {}
        
    @property          
    def props(self):
        return { "detectionState": { "value" : "string"}}

class DoorbellEventSource(capabilityInterface):

    @property
    def controller(self):
        return "DoorbellEventSource"

    @property            
    def directives(self):
        return {}
        
    @property          
    def props(self):
        return {}
        
    @property
    def capability(self):
        # DoorbellEventSource is Quirks mode stuff: https://developer.amazon.com/docs/device-apis/alexa-doorbelleventsource.html
        return {"interface":self.interface, "version": self.version, "type": self.capabilityType, "proactivelyReported": True}

    def press(self):
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
                                "token": ""
                            },
                            "endpointId": self.endpointId
                        },
                        "payload" : {
                            "cause": {
                                "type": "PHYSICAL_INTERACTION"
                            },
                            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()[:-10]+"Z"
                        }
                    }
                }

    

class EndpointHealth(capabilityInterface):
    
    @property
    def controller(self):
        return "EndpointHealth"

    @property
    def state(self):
        thisState=super().state
        for item in thisState:
            if item['name'] in ["connectivity"]:
                item['value']={'value': item['value']}
                
        return thisState

    @property            
    def directives(self):
        return {}

    @property          
    def props(self):
        return { "connectivity": { "value": "string"} }
        
class AdapterHealth(capabilityInterface):

    @property
    def namespace(self):
        return "Sofa"
    
    @property
    def controller(self):
        return "AdapterHealth"

    @property
    def url(self):
        return ""

    @property            
    def directives(self):
        return {}
        
    @property            
    def startup(self):
        return ''

    @property            
    def datasize(self):
        return 0

    @property            
    def logged(self):
        return {'ERROR':0, 'INFO':0}    
        
    @property          
    def props(self):
        return { "url": { "value": "string"},  "startup": { "value": "string"}, "logged": {"value": "dict" }, "datasize": { "value": "number" } }

class alexaDevice(object):
    
    def __init__(self, path, name, adapter=None, nativeObject=None, displayCategories=["OTHER"], description="Smart Device", manufacturerName="Sofa", modelName="", log=None, hidden=False, native=None):
        self._path=path
        self._friendlyName=name
        self._displayCategories=displayCategories
        self._description=description
        self._manufacturerName=manufacturerName
        self._modelName=modelName
        self._interfaces=[]
        self.log=adapter.log
        self.adapter=adapter
        self.nativeObject=nativeObject
        self.hidden=hidden
    
    @property
    def name(self):
        if hasattr(self, '_friendlyName'):
            return self._friendlyName
        return self.endpointId

    @property
    def friendlyName(self):
        if hasattr(self, '_friendlyName'):
            return self._friendlyName
        return self.endpointId


    @property
    def path(self):
        if hasattr(self, '_path'):
            return self._path
        return ""
        
    @property
    def native(self):
        if hasattr(self, '_path') and hasattr(self, 'adapter'):
            return self.adapter.dataset.getNativeFromPath(self._path)
        return ""

    @property
    def interfaces(self):
        if hasattr(self, '_interfaces') and self._interfaces!=[]:
            return self._interfaces

        interf=[]
        skip=[  'Interfaces', 'interfaces', 'capabilities', 'name', 'path', 'ReportState', 'Capture', 'Reset', 'Response', 'fullDiscoverResponse',
                'StateReport','addOrUpdateReport','changeReport','description','discoverResponse','displayCategories',
                'endpointId','friendlyName','log','manufacturer','namespace', 'native', 'payloadVersion', 'propertyStates']

        #allself=[a for a in dir(self) if (not a.startswith('_') and a not in skip)]
        #self.log.info('self: %s' % allself)
        for obj in [a for a in dir(self) if (not a.startswith('_') and a not in skip)]:
            #self.log.info('selfx: %s' % obj)
            if issubclass(type(getattr(self, obj)), capabilityInterface):
                interf.append(getattr(self, obj))

        return interf


    @property
    def displayCategories(self):
        if hasattr(self, '_displayCategories'):
            return self._displayCategories
        else:
            return []

    @property
    def endpointId(self):
        return self.path.replace('/',':')

    @property
    def manufacturerName(self):
        if hasattr(self, '_manufacturerName'):
            return self._manufacturerName
        else:
            return ""
            
    @property
    def modelName(self):
        if hasattr(self, '_modelName'):
            return self._modelName
        else:
            return ""

    @property
    def description(self):
        if hasattr(self, '_description'):
            return self._description
        else:
            return ""

    @property
    def payloadVersion(self):
        if hasattr(self, '_version'):
            return self._version
        else:
            return "3"

    @property
    def namespace(self):
        if hasattr(self, '_namespace'):
            return self._namespace
        else:
            return "Alexa"

    @property
    def capabilities(self):
        if hasattr(self, '_noAlexaInterface'):
            caps=[]
        else:
            caps=[{ "type": "AlexaInterface", "interface": "Alexa", "version": "3"}]
        for obj in self.interfaces:
            caps.append(obj.capability)
        return caps
        
    @property
    def propertyStates(self):
        states=[]
        for obj in self.interfaces:
            states.extend(obj.state)
        return states

    @property 
    def fullDiscoverResponse(self):
        return {
            "event": {
                "header": {
                    "namespace": "Alexa.Discovery",
                    "name": "Discover.Response",
                    "payloadVersion": "3",
                    "messageId":  str(uuid.uuid1()),
                },
                "payload": {
                    "endpoints": [
                        self.discoverResponse
                    ]          
                }
            }
        }
        
    @property
    def discoverResponse(self):
        
        return  {
            "displayCategories": self.displayCategories,
            "endpointId": self.endpointId,
            "friendlyName": self.friendlyName,
            "description": self.description,
            "manufacturerName": self.manufacturerName,
            "modelName": self.modelName,
            "cookie": {"url": self.adapter.url},
            "capabilities": self.capabilities,
        }
        
    def ReportState(self, correlationToken='' , bearerToken=''):

        return  {
            "directive": {
                "header": {
                    "name":"ReportState",
                    "payloadVersion": self.payloadVersion,
                    "messageId":str(uuid.uuid1()),
                    "namespace":self.namespace,
                    "correlationToken":correlationToken
                },
                "endpoint": {
                    "endpointId": self.endpointId,
                    "scope": {
                        "type": "BearerToken",
                        "token": bearerToken
                    },     
                    "cookie": {}
                },
                "payload": {}
            },
        }

    def StateReport(self, correlationToken=None, bearerToken=''):
        
        if not correlationToken:
            correlationToken=str(uuid.uuid1())
            
        return  {
            "event": {
                "header": {
                    "name":"StateReport",
                    "payloadVersion": self.payloadVersion,
                    "messageId":str(uuid.uuid1()),
                    "namespace":self.namespace,
                    "correlationToken":correlationToken
                },
                "endpoint": {
                    "endpointId": self.endpointId,
                    "scope": {
                        "type": "BearerToken",
                        "token": bearerToken
                    },     
                    "cookie": {}
                },
                "payload": {}
            },
            "context": {
                "properties": self.propertyStates
            }
        }
        
    @property
    def addOrUpdateReport(self):
        return {
            "event": {
                "header": {
                    "namespace": "Alexa.Discovery",
                    "name": "AddOrUpdateReport",
                    "payloadVersion": "3",
                    "messageId": str(uuid.uuid1()),
                },
                "payload": {
                    "endpoints": [
                        self.discoverResponse
                    ]          
                }
            }
        }
        
    def changeReport(self, controllers, names={}):
        
        props=self.propertyStates
        unchangedPropertyStates=[]
        changedPropertyStates=[]
        for prop in props:
            if prop['namespace'].split(".")[1] in controllers:
                if prop['name'] in controllers[prop['namespace'].split(".")[1]]:
                    changedPropertyStates.append(prop)
                    continue
            
            # new version does not remove the first part of the namespace
            if prop['namespace'] in controllers:
                if prop['name'] in controllers[prop['namespace']]:
                    changedPropertyStates.append(prop)
                    continue
                    
            unchangedPropertyStates.append(prop)
                
        if not changedPropertyStates:
            return {}
                
        return  {
            "event": {
                "header": {
                    "name":"ChangeReport",
                    "payloadVersion": self.payloadVersion,
                    "messageId":str(uuid.uuid1()),
                    "namespace":self.namespace
                },
                "endpoint": {
                    "endpointId": self.endpointId,
                    "cookie": {
                        "name": self.friendlyName
                    }
                },
                "payload": {
                    "change": {
                        "cause": {
                            "type":"APP_INTERACTION"
                        },
                        "properties": changedPropertyStates
                    }
                }
            },
            "context": {
                "properties": unchangedPropertyStates
            },
        }


    def Response(self, correlationToken='', controller='', payload={}, override={}):

        return {
            "event": {
                "header": {
                    "name":"Response",
                    "payloadVersion": self.payloadVersion,
                    "messageId":str(uuid.uuid1()),
                    "namespace":self.namespace,
                    "correlationToken":correlationToken
                },
                "endpoint": {
                    "endpointId": self.endpointId
                }
            },
            "context": {
                "properties": [prop for prop in self.propertyStates if (prop['namespace'].split('.')[1]==controller or not controller)]
            },
            "payload": payload
        }

    def ErrorResponse(self, correlationToken="", error_type="INTERNAL_ERROR", error_message="An unknown exception occurred"):

        # Possible error messages are defined at https://developer.amazon.com/en-US/docs/alexa/device-apis/alexa-errorresponse.html
        return {
            "event": {
                "header": {
                    "name":"ErrorResponse",
                    "payloadVersion": self.payloadVersion,
                    "messageId":str(uuid.uuid1()),
                    "namespace":self.namespace,
                    "correlationToken":correlationToken
                },
                "endpoint": {
                    "endpointId": self.endpointId
                }
            },
            "payload": {
                "type": error_type,
                "message": error_message
            }
        }

        

class remoteAlexaDevice(object):
    # This is a representation of a device that is hosted on another adapter.  It should be used by
    # Collector type adapters.
    
    # This is work-in-progress but should be able to have the existing device definition from discovery passed in
    # and then create a working virtual device that requests data from the appropriate adapter.
    
    def __init__(self, localadapter, adapter, device):
        # local adapter is used for services and logging
        # device is the json representation of the discovery info
        self._path=adapter
        self._friendlyName=device.friendlyName
        self._displayCategories=device.displayCategories
        self._description=device.description
        self._manufacturer=device.manufacturer
        self._interfaces=device.capabilities
        self.log=localadapter.log
        self.adapter=localadapter
        self.nativeObject=None
        self.adaptername=self.adapter.dataset.adaptername
        self.url=self.adapter.url

if __name__ == '__main__':
    pass
    
import sys
import uuid
import datetime

class smartInterface(object):
    
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
        return { "proactivelyReported": self.proactivelyReported, "retrievable": self.retrievable, "supported": supported}

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
                supported.append({
                        "name": prop,
                        "value": getattr(self, prop),
                        "namespace":self.interface, 
                        "uncertaintyInMilliseconds": 1000, 
                        "timeOfSample":datetime.datetime.utcnow().isoformat() + 'Z'})
            except:
                print('Error adding property to state report: %s %s' % (prop, sys.exc_info()))
        
        return supported



# Work in progress - very different from other device types        
class cameraInterface(smartInterface):

    def __init__(self, controller, version="3", proactivelyReported=True, retrievable=True, namespace="Alexa", camerastreamconfigurations=[]):
        self.controller="CameraController"
        self._namespace=namespace
        self.interface="%s.%s" % (namespace, controller)
        self.version=version
        self.capabilityType="%sInterface" % namespace
        self.proactivelyReported=proactivelyReported
        self.retrievable=retrievable
        self.camconfigs=camerastreamconfigurations


    @property
    def capability(self):
        return {"interface":self.interface, "version": self.version, "type": self.capabilityType, "cameraStreamConfigurations": self.cameraStreamConfigurations}


    @property
    def cameraStreamConfigurations(self):
        
        #camstreamconfig=[]
        #for csc in self.camconfigs:
        # hardcoded for now
        camstreamconfig=[
                {
                    "protocols": ["RTSP","MJPEG"], 
                    "resolutions": [{"width":1280, "height":720}], 
                    "authorizationTypes": ["BASIC"], 
                    "videoCodecs": ["H264", "MPEG2"], 
                    "audioCodecs": ["G711"] 
                }
            ]
        return camstreamconfig

    @property
    def properties(self):
        # not supported on cameras
        return {}

    @property            
    def directives(self):
        return {}

    @property          
    def props(self):
        return {}
    
        
class CameraStreamControllerInterface(cameraInterface):

    def __init__(self):
        smartInterface.__init__(self, "CameraStreamController")


class BrightnessControllerInterface(smartInterface):
    
    def __init__(self, brightness=0, SetBrightness=None):
        self.controller="BrightnessController"
        self.brightness=brightness
        if SetBrightness:
            self.SetBrightness=SetBrightness
    
    @property            
    def commands(self):
        return {'SetBrightness': { 'brightness': 'value' }}

    @property            
    def directives(self):
        return { 'SetBrightness' : { 'brightness': { "value": "integer" }}}

    @property          
    def props(self):
        return { 'brightness' : { "value": "integer" }}


    def updateBrightness(self, value):
        self.brightness=value

        
    def SetBrightness(self, value):
        if value<=100 and value>=0:
            self.brightness=value
        else:
            print('Brightness value out of range: %s' % value)


class PowerLevelControllerInterface(smartInterface):
    
    def __init__(self, powerLevel=0, SetPowerLevel=None):
        self.controller="PowerLevelController"
        self.powerLevel=powerLevel
        if SetPowerLevel:
            self.SetPowerLevel=SetPowerLevel
    
    @property            
    def commands(self):
        return {'SetPowerLevel': { 'powerLevel': 'value' }}

    @property            
    def directives(self):
        return { 'SetPowerLevel' : { "value" : { "powerLevel": "integer" }}}

    @property          
    def props(self):
        return { 'powerlevel' : { "value": "integer" }}

    def SetPowerLevel(self, value):
        if value<=100 and value>=0:
            self.powerLevel=value
        else:
            print('Power Level value out of range: %s' % value)



class ColorControllerInterface(smartInterface):
    
    def __init__(self, color={"hue":0, "saturation": 0, "brightness":0}, SetColor=None):
        self.controller="ColorController"
        self.color=color
        if SetColor:
            self.SetColor=SetColor

    @property            
    def commands(self):
        return {'SetColor': { 'color': 'value' }}

    @property            
    def directives(self):
        return { "SetColor" : { "color": { "value" : { "hue": "decimal", "saturation": 'decimal', "brightness": "decimal" }}}}

    @property          
    def props(self):
        return { "color": { "value": { "hue": "decimal", "saturation": 'decimal', "brightness": "decimal" }}}

    def updateColor(self, value):
        # value should be a dict with hue, saturation, and brightness
        self.color=value

        
    def SetColor(self, value):
        # value should be a dict with hue, saturation, and brightness
        self.color=value


class ColorTemperatureControllerInterface(smartInterface):
    
    def __init__(self, colorTemperatureInKelvin=7000, SetColorTemperature=None):
        self.controller="ColorTemperatureController"
        self.colorTemperatureInKelvin=colorTemperatureInKelvin
        if SetColorTemperature:
            self.SetColorTemperature=SetColorTemperature

    @property            
    def commands(self):
        return { 'SetColorTemperature': { 'colorTemperatureInKelvin': 'value' }}

    @property            
    def directives(self):
        return { 'SetColorTemperature' : { "colorTemperatureInKelvin": {"value": "integer" }}}

    @property          
    def props(self):
        return { 'colorTemperatureInKelvin': { "value": "integer" }}

    def updateColorTemperature(self, value):
        # value should be a number from 2-7k
        self.colorTemperatureInKelvin=value
        
    def SetColorTemperature(self, value):
        # value should be a number from 2-7k
        self.colorTemperatureInKelvin=value


class InputControllerInterface(smartInterface):
    
    def __init__(self, inputName="Input", SelectInput=None):
        self.controller="InputController"
        self._input=inputName
        if SelectInput:
            self.SelectInput=SelectInput

    @property            
    def commands(self):
        return {'SelectInput': { 'input': 'value' }}

    @property            
    def directives(self):
        return { "SelectInput": { "input": { "value": "string" }}}

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

class LockControllerInterface(smartInterface):
    
    def __init__(self, lockState="LOCKED", Lock=None, Unlock=None):
        self.controller="LockController"
        self.lockState=lockState
        if Lock:
            self.Lock=Lock
        if Unlock:
            self.Unlock=Unlock

    @property            
    def commands(self):
        return {'Lock': {}, 'Unlock': {}}

    @property            
    def directives(self):
        return { "Lock": {}, "Unlock": {} }

    @property          
    def props(self):
        return { "lockState" : { "value" : "string" }}

    def updateLockState(self, value):
        if value in ['LOCKED','UNLOCKED','JAMMED']:
            self.lockState=value
        else:
            self.log.warn('Invalid LockState value: %s' % value)
       

class PowerControllerInterface(smartInterface):
    
    def __init__(self, powerState="OFF", TurnOn=None, TurnOff=None):
        self.controller="PowerController"
        self.powerState=powerState
        if TurnOn:
            self.TurnOn=TurnOn
        if TurnOn:
            self.TurnOff=TurnOff
            
    @property            
    def commands(self):
        return {'TurnOn': {}, 'TurnOff': {}}

    @property            
    def directives(self):
        return { "TurnOn": {}, "TurnOff": {} }

    @property          
    def props(self):
        return { "powerState" : { "value": "string" }}

    def updatePowerState(self, value):
        if value=="ON":
            self.powerState="ON"
        elif value=="OFF":
            self.powerState="OFF"
        else:
            self.log.warn('Invalid PowerState value: %s' % value)
        
    def TurnOn(self):
        self.powerState="ON"
        
    def TurnOff(self):
        self.powerState="OFF"


class ButtonControllerInterface(smartInterface):
    
    def __init__(self, duration=1, pressState="none", Press=None, Hold=None):
        self.controller="ButtonController"
        self.pressState=pressState
        self.Press=Press
        self.Hold=Hold
        
    @property            
    def commands(self):
        return {'Press': {}, 'Hold': {'duration':'value'}, 'Release': {}}

    @property            
    def directives(self):
        return { "Press": {}, "Hold": { "duration" : { "value" : "integer", "unit" : "string" }}, "Release": {} }

    @property          
    def props(self):
        return { "pressState" : { "value": "string" }}

    def updatePressState(self, value):
        if value=="ON":
            self.pressState="ON"
        elif value=="OFF":
            self.pressState="OFF"
        else:
            self.log.warn('Invalid PressState value: %s' % value)
            
class SceneControllerInterface(smartInterface):
    
    def __init__(self, powerState="OFF", Activate=None, Deactivate=None):
        self.controller="SceneController"
        self.powerState=powerState
        self.Activate=Activate
        self.Deactivate=Deactivate
            
    @property            
    def commands(self):
        return {'Activate': {}, 'Deactivate': {}}

    @property            
    def directives(self):
        return { "Activate": {}, "Deactivate": {} }

    @property          
    def props(self):
        return {}
        

class TemperatureSensorInterface(smartInterface):
    
    def __init__(self, temperature=72, scale="FAHRENHEIT"):
        self.controller="TemperatureSensor"
        self.scale=scale
        self.temperature=temperature

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
            if item['name']=='temperature':
                item['scale']=self.scale
        return thisState

class SwitchSensorInterface(smartInterface):
    
    def __init__(self, pressState="none"):
        self.controller="SwitchSensor"
        self.pressState=pressState
        
    @property            
    def directives(self):
        return {}

    @property          
    def props(self):
        return { "pressState" : { "value": "string" }}

    def updatePressState(self, value):
        if value=="ON":
            self.pressState="ON"
        elif value=="OFF":
            self.pressState="OFF"
        else:
            self.log.warn('Invalid PressState value: %s' % value)  


class ThermostatControllerInterface(smartInterface):
    
    def __init__(self, targetSetPoint=70, lowerSetPoint=70, upperSetPoint=70, thermostatMode="AUTO", scale="FAHRENHEIT", supportedModes=["HEAT", "COOL", "AUTO", "OFF"], supportsScheduling=False):
        self.controller="ThermostatController"
        self.scale=scale
        self.targetSetPoint=targetSetPoint
        self.lowerSetPoint=lowerSetPoint
        self.upperSetPoint=upperSetPoint
        self.thermostatMode=thermostatMode
        self.supportedModes=supportedModes
        self.supportsScheduling=supportsScheduling

    @property
    def configuration(self):
        return {"supportsScheduling": self.supportsScheduling, "supportedModes": self.supportedModes }

    @property            
    def commands(self):
        return {'SetTargetTemperature': {'targetSetPoint':'value', 'scale':'FAHRENHEIT' }, 'SetThermostatMode': {'thermostatMode':'value'}}

    @property            
    def directives(self):
        return { "SetTargetTemperature": { "targetSetPoint": { "value":"integer", "scale":"string" }}, "SetThermostatMode": {'thermostatMode': {"value": "string"}} }
        
    @property          
    def props(self):
        return { "targetSetPoint" : { "value":"integer", "scale":"string" }, "thermostatMode": { "value" : "string" }}


    @property
    def state(self):
        thisState=super().state
        for item in thisState:
            if item['name'] in ["targetSetPoint","lowerSetPoint","upperSetPoint"]:
                item['scale']=self.scale
        return thisState
        
    def SetTargetTemperature(self, value):
        self.targetSetPoint=value

    def updateTargetSetPoint(self, value):
        self.targetSetPoint=value


class LogicControllerInterface(smartInterface):
    
    def __init__(self, duration=0, Delay=None, Alert=None, Capture=None, Reset=None, Wait=None, namespace="Sofa" ):
        self.controller="LogicController"
        self.Delay=Delay
        self.Alert=Alert
        self.Reset=Reset
        self.Wait=Wait
    
    @property
    def time(self):
        return datetime.datetime.now()
        
    @property            
    def commands(self):
        return {'Delay': {'duration':'value'}, 'Alert': {'message':'value'}, 'Capture': {'device':'value'}, 'Reset': {'device':'value'}, "Wait":{}}
    
    @property            
    def directives(self):
        return {    "Delay": { "duration": { "value":"integer", "unit":"string" }}, 
                    "Alert": { "message": { "value":"string", "image":"string" }},
                    "Capture": { "device": { "name":"string" }},
                    "Reset": { "device": { "name": "string" }},
                    "Wait": {}
                }
        
    @property          
    def props(self):
        return { "time": { "value":"time"}}

        
class MusicControllerInterface(smartInterface):
    
    def __init__(self, artist="", title="", album="", url="", art="", linked=[], namespace="Sofa", playbackState='STOPPED', PlayFavorite=None, Play=None, Pause=None, Stop=None, Skip=None, Previous=None):
        self.controller="MusicController"
        self._namespace="Sofa"
        self.artist=artist
        self.title=title
        self.album=album
        self.url=url
        self.art=art
        self.linked=linked
        self.playbackState=playbackState

        self.Play=Play
        self.Pause=Pause
        self.Stop=Stop
        self.Previous=Previous
        self.Skip=Skip

    @property            
    def commands(self):
        return { 'PlayFavorite': {'favorite':'value'}, 'Play': {}, 'Pause': {}, 'Stop': {}, 'Previous': {}, 'Skip': {} }

    @property            
    def directives(self):
        return {    "PlayFavorite": { "favorite": { "value" : "string" }}, 
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
            
    def updateArtist(self, value):
        self.artist=value

    def updateTitle(self,value):
        self.title=value
        
    def updateAlbum(self,value):
        self.album=value

    def updateUrl(self,value):
        self.url=value
        
    def updateArt(self,value):
        self.art=value
        
    def updateLinked(self,value):
        self.linked=value

    def updatePlayBackState(self, value):
        self.playbackState=value


class SpeakerControllerInterface(smartInterface):
    
    def __init__(self, volume=0, muted=False, SetVolume=None, SetMuted=None):
        self.controller="SpeakerController"
        self._namespace="Sofa"
        self.volume=volume
        self.muted=muted
        if SetVolume:
            self.SetVolume=SetVolume
        if SetMuted:
            self.SetMuted=SetMuted

    @property            
    def commands(self):
        return { 'SetVolume': {'volume':'value'}, 'SetMuted': {'muted':'value'}}

    @property            
    def directives(self):
        return {    "SetVolume": { "volume": { "value" : "percentage" }}, 
                    "SetMuted": { "muted" : { "value": "string" }}
                }
        
    @property          
    def props(self):
        return { "volume": { "value" : "percentage"}, "muted": { "value" : "string"}}

    def updateVolume(self, value):
        self.volume=value

    def updateMuted(self, value):
        self.muted=value

        
    def SetVolume(self, value):
        if value<=100 and value>=0:
            self.volume=value

    def SetMuted(self, value):
        self.muted=value


class SurroundControllerInterface(smartInterface):
    
    def __init__(self, surround="Straight", namespace="Sofa", decoder="Dolby", SetSurround=None, SetDecoder=None):
        self.controller="SurroundController"
        self._namespace="Sofa"
        self.surround=surround
        self.decoder=decoder

        self.SetSurround=SetSurround
        self.SetDecoder=SetDecoder
        
    @property            
    def commands(self):
        return { 'SetSurround': { 'surround':'value' }, 'SetDecoder': {'decoder': 'value'}}

    @property            
    def directives(self):
        return {    "SetSurround": { "surround": { "value" : "string" }}, 
                    "SetDecoder": { "decoder" : { "value": "string" }}
                }
        
    @property          
    def props(self):
        return { "surround": { "value" : "string"}, "decoder": { "value" : "string"}}

    def updateSurround(self, value):
        self.surround=value

    def updateDecoder(self, value):
        self.decoder=value


        
class ZoneSensorInterface(smartInterface):
    
    def __init__(self, position="open", type="unknown", namespace="Sofa"):
        self.controller="ZoneSensor"
        self._namespace="Sofa"
        self.position=position
        self.type=type

    @property            
    def directives(self):
        return {}
        
    @property          
    def props(self):
        return { "position": { "value" : "string"}, "type": { "value" : "string" }}


   
class smartObject(object):
    
    def __init__(self, path, name):
        
        self.interfaces=[]
        self.displayCategories=[]
        self.description=""
        self.manufacturer=""
        self.payloadVersion="3"
        self.namespace="Alexa"
        self.endpointId=path.replace('/',':')

        if name:
            self.friendlyName=name
        else:
            self.friendlyName=self.endpointId

    @property
    def capabilities(self):
        caps=[]
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
            "manufacturerName": self.manufacturer,
            "cookie": {},
            "capabilities": self.capabilities,
        }
        
    @property
    def stateReport(self):
        return  {
            "event": {
                "header": {
                    "name":"StateReport",
                    "payloadVersion": self.payloadVersion,
                    "messageId":str(uuid.uuid1()),
                    "namespace":self.namespace
                },
                "endpoint": {
                    "endpointId": self.endpointId,
                    "cookie": {
                        "name": self.friendlyName
                    }
                }
            },
            "context": {
                "properties": self.propertyStates
            },
            "payload": {}
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
        
    def changeReport(self, controllers):
        
        props=self.propertyStates
        unchangedPropertyStates=[]
        changedPropertyStates=[]
        for prop in props:
            if prop['namespace'].split(".")[1] in controllers:
                if prop['name'] in controllers[prop['namespace'].split(".")[1]]:
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
                }
            },
            "context": {
                "properties": unchangedPropertyStates
            },
            "payload": {
                "change": {
                    "cause": {
                        "type":"APP_INTERACTION"
                    },
                    "properties": changedPropertyStates
                }
            }
        }


    def Response(self, correlationToken=''):
        return  {
            "event": {
                "header": {
                    "name":"Response",
                    "payloadVersion": self.payloadVersion,
                    "messageId":str(uuid.uuid1()),
                    "namespace":self.namespace,
                    "correlationToken":correlationToken
                },
                "endpoint": {
                    "endpointId": self.endpointId,
                    "cookie": {
                        "name": self.friendlyName
                    }
                }
            },
            "context": {
                "properties": self.propertyStates
            },
            "payload": {}
        }


            

class basicDevice(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["DEVICE"]
        self.PowerController=PowerControllerInterface()
        self.interfaces=[self.PowerController]
        self.description=description
        self.manufacturer=manufacturer

class simpleMode(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["MODE"]
        self.PowerController=PowerControllerInterface()
        self.interfaces=[self.PowerController]
        self.description=description
        self.manufacturer=manufacturer


class smartButton(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["BUTTON"]
        self.ButtonController=ButtonControllerInterface()
        self.interfaces=[self.ButtonController]
        self.description=description
        self.manufacturer=manufacturer

class simpleActivity(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["ACTIVITY_TRIGGER"]
        self.SceneController=SceneControllerInterface()
        self.interfaces=[self.SceneController]
        self.description=description
        self.manufacturer=manufacturer

class simpleScene(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["SCENE_TRIGGER"]
        self.SceneController=SceneControllerInterface()
        self.interfaces=[self.SceneController]
        self.description=description
        self.manufacturer=manufacturer


class simpleLight(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["LIGHT"]
        self.description=description
        self.manufacturer=manufacturer
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.interfaces=[self.PowerController]

class simpleLightWithSwitch(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["LIGHT"]
        self.description=description
        self.manufacturer=manufacturer
        self.SwitchSensor=SwitchSensorInterface()
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.interfaces=[self.SwitchSensor, self.PowerController]

        
class dimmableLight(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, SetBrightness=None, log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["LIGHT"]
        self.description=description
        self.manufacturer=manufacturer
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.BrightnessController=BrightnessControllerInterface(SetBrightness)
        self.interfaces=[self.PowerController, self.BrightnessController]

class dimmableLightWithSwitch(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, SetBrightness=None, log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["LIGHT"]
        self.description=description
        self.manufacturer=manufacturer
        self.SwitchSensor=SwitchSensorInterface()
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.BrightnessController=BrightnessControllerInterface(SetBrightness)
        self.interfaces=[self.SwitchSensor, self.PowerController, self.BrightnessController]

class lightSwitch(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["SWITCH"]
        self.description=description
        self.manufacturer=manufacturer
        self.SwitchSensor=SwitchSensorInterface()
        self.interfaces=[self.SwitchSensor]



class tunableLight(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, SetBrightness=None, SetColorTemperature=None, log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["LIGHT"]
        self.description=description
        self.manufacturer=manufacturer
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.BrightnessController=BrightnessControllerInterface(SetBrightness)
        self.ColorTemperatureController=ColorTemperatureControllerInterface(SetColorTemperature)
        self.interfaces=[self.PowerController, self.BrightnessController, self.ColorTemperatureController]



class colorLight(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, SetBrightness=None, SetColorTemperature=None, SetColor=None, log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["LIGHT"]
        self.description=description
        self.manufacturer=manufacturer
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        print('SetBrightness: %s' % SetBrightness)
        self.BrightnessController=BrightnessControllerInterface(SetBrightness=SetBrightness)
        self.ColorController=ColorControllerInterface(SetColor)
        self.ColorTemperatureController=ColorTemperatureControllerInterface(SetColorTemperature)
        self.interfaces=[self.PowerController, self.BrightnessController, self.ColorController, self.ColorTemperatureController]


class soundSystem(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", SetVolume=None, SetMute=None, SelectInput=None, log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["SPEAKER"]
        self.description=description
        self.manufacturer=manufacturer
        self.InputController=InputControllerInterface(SelectInput)
        self.SpeakerController=SpeakerControllerInterface(SetVolume, SetMute)
        self.MusicController=MusicControllerInterface()
        self.interfaces=[self.InputController, self.SpeakerController, self.MusicController]

class receiver(smartObject):

    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, SetVolume=None, SetMute=None, SelectInput=None, SetSurround=None, SetDecoder=None, log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["RECEIVER"]
        self.description=description
        self.manufacturer=manufacturer
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.InputController=InputControllerInterface(SelectInput)
        self.SpeakerController=SpeakerControllerInterface(SetVolume, SetMute)
        self.SurroundController=SurroundControllerInterface(SetSurround, SetDecoder)
        self.interfaces=[self.PowerController, self.InputController, self.SpeakerController, self.SurroundController]

class tv(smartObject):

    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, SelectInput=None, log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["TV"]
        self.description=description
        self.manufacturer=manufacturer
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.InputController=InputControllerInterface(SelectInput)
        self.interfaces=[self.PowerController, self.InputController]


class smartSpeaker(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", SetVolume=None, SetMute=None, SelectInput=None, log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["SPEAKER"]
        self.description=description
        self.manufacturer=manufacturer
        self.InputController=InputControllerInterface(SelectInput)
        self.SpeakerController=SpeakerControllerInterface(SetVolume, SetMute)
        self.interfaces=[self.InputController, self.SpeakerController]

class smartPC(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, Lock=None, Unlock=None, log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["PC"]
        self.description=description
        self.manufacturer=manufacturer
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.LockController=LockControllerInterface(Lock, Unlock)
        self.interfaces=[self.PowerController, self.LockController]
   
        
class simpleThermostat(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["THERMOSTAT"]
        self.description=description
        self.manufacturer=manufacturer
        self.TemperatureSensor=TemperatureSensorInterface()
        self.interfaces=[self.TemperatureSensor]


class smartThermostat(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", SetTargetTemperature=None, supportedModes=["HEAT", "COOL", "AUTO", "OFF"], log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["THERMOSTAT"]
        self.description=description
        self.manufacturer=manufacturer
        self.TemperatureSensor=TemperatureSensorInterface()
        self.ThermostatController=ThermostatControllerInterface(SetTargetTemperature, supportedModes=supportedModes)
        self.interfaces=[self.TemperatureSensor, self.ThermostatController]

class smartThermostatFan(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", SetPowerLevel=None, SetTargetTemperature=None, supportedModes=["HEAT", "COOL", "AUTO", "OFF"], log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["THERMOSTAT"]
        self.description=description
        self.manufacturer=manufacturer
        self.PowerLevelController=PowerLevelControllerInterface(SetPowerLevel)
        self.TemperatureSensor=TemperatureSensorInterface()
        self.ThermostatController=ThermostatControllerInterface(SetTargetTemperature, supportedModes=supportedModes)
        self.interfaces=[self.TemperatureSensor, self.ThermostatController, self.PowerLevelController]

        
class simpleZone(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["ZONE"]
        self.description=description
        self.manufacturer=manufacturer
        self.ZoneSensor=ZoneSensorInterface()
        self.interfaces=[self.ZoneSensor]


class simpleCamera(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["CAMERA"]
        self.description=description
        self.manufacturer=manufacturer
        self.ZoneSensor=ZoneSensorInterface()
        self.interfaces=[self.ZoneSensor]
        
class simpleLogicCommand(smartObject):

    def __init__(self, path, name, description="", manufacturer="sofa", log=None):
        smartObject.__init__(self, path, name)
        self.displayCategories=["LOGIC"]
        self.description=description
        self.manufacturer=manufacturer
        self.LogicController=LogicControllerInterface()
        self.interfaces=[self.LogicController]


if __name__ == '__main__':
    newlight=dimmableLight("test/office/1", "Office Light")
    print(newlight.discoverResponse)
    print('--')
    print(newlight.stateReport)
    newlight.PowerController.powerState="ON"
    newlight.BrightnessController.SetBrightness(100)
    print(newlight.stateReport)
    
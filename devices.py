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
    def directives(self):
        return { 'SetBrightness' : { 'brightness': "integer" }}

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
    def directives(self):
        return { 'SetPowerLevel' : { "powerLevel": "integer" }}

    @property          
    def props(self):
        return { 'powerLevel' : { "value": "integer" }}

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
    def directives(self):
        return { "SetColor" : { "color": { "hue": "decimal", "saturation": 'decimal', "brightness": "decimal" }}}

    @property          
    def props(self):
        return { "color": { "hue": "decimal", "saturation": 'decimal', "brightness": "decimal" }}

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
    def directives(self):
        return { 'SetColorTemperature' : { "colorTemperatureInKelvin" : "integer" }}

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

class LockControllerInterface(smartInterface):
    
    def __init__(self, lockState="LOCKED", Lock=None, Unlock=None):
        self.controller="LockController"
        self.lockState=lockState
        if Lock:
            self.Lock=Lock
        if Unlock:
            self.Unlock=Unlock

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
    def directives(self):
        return { "Press": {}, "Hold": { "duration" : "integer" }, "Release": {} }

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
    
    def __init__(self, targetSetpoint=70, lowerSetpoint=70, upperSetpoint=70, thermostatMode="AUTO", scale="FAHRENHEIT", supportedModes=["HEAT", "COOL", "AUTO", "OFF"], supportsScheduling=False):
        self.controller="ThermostatController"
        self.scale=scale
        self.targetSetpoint=targetSetpoint
        self.lowerSetpoint=lowerSetpoint
        self.upperSetpoint=upperSetpoint
        self.thermostatMode=thermostatMode
        self.supportedModes=supportedModes
        self.supportsScheduling=supportsScheduling

    @property
    def configuration(self):
        return {"supportsScheduling": self.supportsScheduling, "supportedModes": self.supportedModes }

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
            if item['name'] in ["targetSetpoint","lowerSetpoint","upperSetpoint"]:
                item['scale']=self.scale
        return thisState
        
    def SetTargetTemperature(self, value):
        self.targetSetpoint=value

    def updateTargetSetpoint(self, value):
        self.targetSetpoint=value


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
    def directives(self):
        return {    "Delay": { "duration": "integer" }, 
                    "Alert": { "message": { "text":"string", "image":"string" }},
                    "Capture": { "device": { "name":"string", "endpointId":"string" }},
                    "Reset": { "device": { "name": "string", "endpointId":"string" }},
                    "Wait": {}
                }
        
    @property          
    def props(self):
        return { "time": { "start":"time", "end":"time" }}

        
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
    def directives(self):
        return {    "SetVolume": { "volume": "percentage" }, 
                    "SetMuted": { "muted" : "string" }
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
    def directives(self):
        return {    "SetSurround": { "surround": "string" }, 
                    "SetDecoder": { "decoder" : "string" }
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
    def interfaces(self):
        if hasattr(self, '_interfaces'):
            return self._interfaces
        return []

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
    def manufacturer(self):
        if hasattr(self, '_manufacturer'):
            return self._manufacturer
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
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["DEVICE"]
        self.PowerController=PowerControllerInterface()
        self._interfaces=[self.PowerController]
        self._description=description
        self._manufacturer=manufacturer
        self._path=path

class simpleMode(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["MODE"]
        self.PowerController=PowerControllerInterface()
        self._interfaces=[self.PowerController]
        self._description=description
        self._manufacturer=manufacturer
        self._path=path

class smartButton(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["BUTTON"]
        self.ButtonController=ButtonControllerInterface()
        self._interfaces=[self.ButtonController]
        self._description=description
        self._manufacturer=manufacturer
        self._path=path
        
class simpleActivity(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["ACTIVITY_TRIGGER"]
        self.SceneController=SceneControllerInterface()
        self._interfaces=[self.SceneController]
        self._description=description
        self._manufacturer=manufacturer
        self._path=path
        
class simpleScene(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["SCENE_TRIGGER"]
        self.SceneController=SceneControllerInterface()
        self._interfaces=[self.SceneController]
        self._description=description
        self._manufacturer=manufacturer
        self._path=path

class simpleLight(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["LIGHT"]
        self._description=description
        self._manufacturer=manufacturer
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self._interfaces=[self.PowerController]
        self._path=path

class simpleLightWithSwitch(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["LIGHT"]
        self._description=description
        self._manufacturer=manufacturer
        self.SwitchSensor=SwitchSensorInterface()
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self._interfaces=[self.SwitchSensor, self.PowerController]
        self._path=path
        
class dimmableLight(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, SetBrightness=None, log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["LIGHT"]
        self._description=description
        self._manufacturer=manufacturer
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.BrightnessController=BrightnessControllerInterface(SetBrightness)
        self._interfaces=[self.PowerController, self.BrightnessController]
        self._path=path
        
class dimmableLightWithSwitch(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, SetBrightness=None, log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["LIGHT"]
        self._description=description
        self._manufacturer=manufacturer
        self.SwitchSensor=SwitchSensorInterface()
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.BrightnessController=BrightnessControllerInterface(SetBrightness)
        self._interfaces=[self.SwitchSensor, self.PowerController, self.BrightnessController]
        self._path=path
        
class lightSwitch(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None):
        self._friendlyName=name
        self._displayCategories=["SWITCH"]
        self._description=description
        self._manufacturer=manufacturer
        self.SwitchSensor=SwitchSensorInterface()
        self._interfaces=[self.SwitchSensor]
        self._path=path
        
class tunableLight(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, SetBrightness=None, SetColorTemperature=None, log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["LIGHT"]
        self._description=description
        self._manufacturer=manufacturer
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.BrightnessController=BrightnessControllerInterface(SetBrightness)
        self.ColorTemperatureController=ColorTemperatureControllerInterface(SetColorTemperature)
        self._interfaces=[self.PowerController, self.BrightnessController, self.ColorTemperatureController]
        self._path=path

class colorLight(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, SetBrightness=None, SetColorTemperature=None, SetColor=None, log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["LIGHT"]
        self._description=description
        self._manufacturer=manufacturer
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.BrightnessController=BrightnessControllerInterface(SetBrightness=SetBrightness)
        self.ColorController=ColorControllerInterface(SetColor)
        self.ColorTemperatureController=ColorTemperatureControllerInterface(SetColorTemperature)
        self._interfaces=[self.PowerController, self.BrightnessController, self.ColorController, self.ColorTemperatureController]
        self._path=path

class soundSystem(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", SetVolume=None, SetMute=None, SelectInput=None, log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["SPEAKER"]
        self._description=description
        self._manufacturer=manufacturer
        self.InputController=InputControllerInterface(SelectInput)
        self.SpeakerController=SpeakerControllerInterface(SetVolume, SetMute)
        self.MusicController=MusicControllerInterface()
        self._interfaces=[self.InputController, self.SpeakerController, self.MusicController]
        self._path=path
        
class receiver(smartObject):

    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, SetVolume=None, SetMute=None, SelectInput=None, SetSurround=None, SetDecoder=None, log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["RECEIVER"]
        self._description=description
        self._manufacturer=manufacturer
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.InputController=InputControllerInterface(SelectInput)
        self.SpeakerController=SpeakerControllerInterface(SetVolume, SetMute)
        self.SurroundController=SurroundControllerInterface(SetSurround, SetDecoder)
        self._interfaces=[self.PowerController, self.InputController, self.SpeakerController, self.SurroundController]
        self._path=path
        
class tv(smartObject):

    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, SelectInput=None, log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["TV"]
        self._description=description
        self._manufacturer=manufacturer
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.InputController=InputControllerInterface(SelectInput)
        self._interfaces=[self.PowerController, self.InputController]
        self._path=path

class smartSpeaker(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", SetVolume=None, SetMute=None, SelectInput=None, log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["SPEAKER"]
        self._description=description
        self._manufacturer=manufacturer
        self.InputController=InputControllerInterface(SelectInput)
        self.SpeakerController=SpeakerControllerInterface(SetVolume, SetMute)
        self._interfaces=[self.InputController, self.SpeakerController]
        self._path=path
        
class smartPC(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", TurnOn=None, TurnOff=None, Lock=None, Unlock=None, log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["PC"]
        self._description=description
        self._manufacturer=manufacturer
        self.PowerController=PowerControllerInterface(TurnOn, TurnOff)
        self.LockController=LockControllerInterface(Lock, Unlock)
        self._interfaces=[self.PowerController, self.LockController]
        self._path=path   
        
class simpleThermostat(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["THERMOSTAT"]
        self._description=description
        self._manufacturer=manufacturer
        self.TemperatureSensor=TemperatureSensorInterface()
        self._interfaces=[self.TemperatureSensor]
        self._path=path

class smartThermostat(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", SetTargetTemperature=None, supportedModes=["HEAT", "COOL", "AUTO", "OFF"], log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["THERMOSTAT"]
        self._description=description
        self._manufacturer=manufacturer
        self.TemperatureSensor=TemperatureSensorInterface()
        self.ThermostatController=ThermostatControllerInterface(SetTargetTemperature, supportedModes=supportedModes)
        self._interfaces=[self.TemperatureSensor, self.ThermostatController]
        self._path=path
        
class smartThermostatFan(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", SetPowerLevel=None, SetTargetTemperature=None, supportedModes=["HEAT", "COOL", "AUTO", "OFF"], log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["THERMOSTAT"]
        self._description=description
        self._manufacturer=manufacturer
        self.PowerLevelController=PowerLevelControllerInterface(SetPowerLevel)
        self.TemperatureSensor=TemperatureSensorInterface()
        self.ThermostatController=ThermostatControllerInterface(SetTargetTemperature, supportedModes=supportedModes)
        self._interfaces=[self.TemperatureSensor, self.ThermostatController, self.PowerLevelController]
        self._path=path
        
class simpleZone(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["ZONE"]
        self._description=description
        self._manufacturer=manufacturer
        self.ZoneSensor=ZoneSensorInterface()
        self._interfaces=[self.ZoneSensor]
        self._path=path

class simpleCamera(smartObject):
    
    def __init__(self, path, name, description="", manufacturer="sofa", log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["CAMERA"]
        self._description=description
        self._manufacturer=manufacturer
        self.ZoneSensor=ZoneSensorInterface()
        self._interfaces=[self.ZoneSensor]
        self._path=path
        
class simpleLogicCommand(smartObject):

    def __init__(self, path, name, description="", manufacturer="sofa", log=None, native=None):
        self._friendlyName=name
        self._displayCategories=["LOGIC"]
        self._description=description
        self._manufacturer=manufacturer
        self.LogicController=LogicControllerInterface()
        self._interfaces=[self.LogicController]
        self._path=path

if __name__ == '__main__':
    newlight=dimmableLight("test/office/1", "Office Light")
    print(newlight.discoverResponse)
    print('--')
    print(newlight.stateReport)
    newlight.PowerController.powerState="ON"
    newlight.BrightnessController.SetBrightness(100)
    print(newlight.stateReport)
    
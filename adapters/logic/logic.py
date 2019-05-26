#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

from sofabase import sofabase
from sofabase import adapterbase
import devices

from sofacollector import SofaCollector
from sendmail import mailSender
from concurrent.futures import ThreadPoolExecutor

import json
import asyncio
import concurrent.futures
import datetime
import time
import uuid
import aiohttp
from aiohttp import web
import copy
from operator import itemgetter

class logicServer(sofabase):
    
    class adapterProcess(SofaCollector.collectorAdapter):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.dataset.nativeDevices['scene']={}
            self.dataset.nativeDevices['activity']={}
            self.dataset.nativeDevices['logic']={}
            self.dataset.nativeDevices['mode']={}
            self.dataset.nativeDevices['area']={}
            
            self.logicpool = ThreadPoolExecutor(10)

            #self.definitions=definitions.Definitions
            self.log=log
            self.notify=notify
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
                

        async def virtualAdd(self, datapath, data):
            
            try:
                dp=datapath.split("/")
                if dp[0]=='automation':
                    result=await self.saveAutomation(dp[1], data)
                elif dp[0]=='scene':
                    result=await self.saveScene(dp[1], data)  
                elif dp[0]=='region':
                    result=await self.saveRegion(dp[1], data)  
                elif dp[0]=='area':
                    result=await self.saveArea(dp[1], data)  

                else:
                    return '{"status":"failed", "reason":"No Save Handler Available for type %s"}' % dp[0]
                    
                if result:
                    if dp[0]=='automation':
                        for auto in self.automations:
                            await self.dataset.ingest({"activity": { auto : self.automations[auto] }})
                    elif dp[0]=='mode':
                        for mode in self.modes:
                            await self.dataset.ingest({"mode": { mode : self.modes[mode] }})
                    elif dp[0]=='scene':    
                        for scene in self.scenes:
                            await self.dataset.ingest({"scene": { scene : self.scenes[scene] }})
                    return '{"status":"success", "reason":"Save Handler completed for %s"}' % datapath

                else:
                    return '{"status":"failed", "reason":"Save Handler did not complete for %s"}' % datapath
            
            except:
                self.log.error('Error loading pattern: %s' % jsonfilename,exc_info=True)
                return '{"status":"failed", "reason":"Internal Adapter Save Handler Error"}'

        async def virtualDel(self, datapath, data):
            
            try:
                dp=datapath.split("/")
                if dp[0]=='automation':
                    result=await self.delAutomation(dp[1])
                elif dp[0]=='scene':
                    result=await self.delScene(dp[1])  
                elif dp[0]=='region':
                    result=await self.delRegion(dp[1])  
                elif dp[0]=='area':
                    result=await self.delRegion(dp[1])  

                else:
                    return '{"status":"failed", "reason":"No Del Handler Available for type %s"}' % dp[0]
                    
                if result:
                    return '{"status":"success", "reason":"Del Handler completed for %s"}' % datapath
                else:
                    return '{"status":"failed", "reason":"Del Handler did not complete for %s"}' % datapath
            
            except:
                self.log.error('Error loading pattern: %s' % jsonfilename,exc_info=True)
                return '{"status":"failed", "reason":"Internal Adapter Del Handler Error"}'

                
        async def virtualSave(self, datapath, data):
            
            try:
                dp=datapath.split("/")
                if dp[0]=='automation':
                    result=await self.saveAutomation(dp[1], data)
                elif dp[0]=='scene':
                    result=await self.saveScene(dp[1], data)  
                elif dp[0]=='region':
                    result=await self.saveRegion(dp[1], data)  
                elif dp[0]=='area':
                    result=await self.saveArea(dp[1], data)  

                else:
                    return '{"status":"failed", "reason":"No Save Handler Available for type %s"}' % dp[0]
                    
                if result:
                    return '{"status":"success", "reason":"Save Handler completed for %s"}' % datapath
                else:
                    return '{"status":"failed", "reason":"Save Handler did not complete for %s"}' % datapath
                
                    
            except:
                self.log.error('Error loading pattern: %s' % jsonfilename,exc_info=True)
                return '{"status":"failed", "reason":"Internal Adapter Save Handler Error"}'
            
        def jsonDateHandler(self, obj):

            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            else:
                self.log.error('Found unknown object for json dump: (%s) %s' % (type(obj),obj))
            return None

        async def saveAutomation(self, name, data):
            
            try:
                data=json.loads(data)
                if name not in self.automations:
                    self.automations[name]={"lastrun": "never", "actions": [], "conditions": [], "schedules":[], "favorite": False }
                
                if 'actions' in data:
                    self.automations[name]['actions']=data['actions']
                if 'conditions' in data:
                    self.automations[name]['conditions']=data['conditions']
                if 'triggers' in data:
                    self.automations[name]['triggers']=data['triggers']
                if 'schedules' in data:
                    self.automations[name]['schedules']=data['schedules']
                if 'favorite' in data:
                    self.automations[name]['favorite']=data['favorite']

                self.calculateNextRun()
                self.saveJSON('automations',self.automations)
                self.eventTriggers=self.buildTriggerList()
                return True
            except:
                self.log.error('Error saving automation: %s %s' % (name, data), exc_info=True)
                return False

        async def saveScene(self, name, data):
            
            try:
                data=json.loads(data)
                self.scenes[name]=data
                self.saveJSON('scenes',self.scenes)
                return True
            except:
                self.log.error('Error saving automation: %s %s' % (name, data), exc_info=True)
                return False


        async def delAutomation(self, name):
            
            try:
                if name in self.automations:
                    del self.automations[name]
                self.calculateNextRun()
                self.saveJSON('automations',self.automations)
                return True
            except:
                self.log.error('Error deleting automation: %s' % name, exc_info=True)
                return False

        async def delRegion(self, name):
            
            try:
                if name in self.regions:
                    del self.regions[name]
                
                self.saveJSON('regions',self.regions)
                return True
            except:
                self.log.error('Error deleting automation: %s' % name, exc_info=True)
                return False

        async def delArea(self, name):
            
            try:
                if name in self.areas:
                    del self.areas[name]
                
                self.saveJSON('areas',self.areas)
                return True
            except:
                self.log.error('Error deleting automation: %s' % name, exc_info=True)
                return False

        async def saveArea(self, name, data):
            
            try:
                self.log.info('Saving Area: %s %s' % (name, data))
                if type(data)==str:
                    data=json.loads(data)
                    
                self.areas[name]=data

                self.saveJSON('areas',self.areas)

                return True
            except:
                self.log.error('Error saving area: %s %s' % (name, data), exc_info=True)
                return False

        async def saveRegion(self, name, data):
            
            try:
                if type(data)==str:
                    data=json.loads(data)
                    
                self.log.info('Saving Region: %s %s' % (name, data['areas'].keys()))
                    
                if 'areas' in data:
                    if type(data['areas'])!=list:
                        data={'areas': list(data['areas'].keys()) }
                    else:
                        data={ 'areas': data['areas'] }
                    
                    self.regions[name]=data

                    self.saveJSON('regions',self.regions)
                    return True
                else:
                    self.log.error('!~ No area data in region %s save: %s' % (name,data))
                    return False
                    
            except:
                self.log.error('Error saving region: %s %s' % (name, data), exc_info=True)
                return False


        def fixdate(self, datetext):
            try:
                working=datetext.split('.')[0].replace('Z','')
                if working.count(':')>1:
                    return datetime.datetime.strptime(working, '%Y-%m-%dT%H:%M:%S')    
                else:
                    return datetime.datetime.strptime(working, '%Y-%m-%dT%H:%M')
            except:
                self.log.error('Error fixing date: %s' % datetext, exc_info=True)
                return None
                

        def calculateNextRun(self, name=None):
            
            # This is all prototype code and should be cleaned up once it is functional
            
            wda=['mon','tue','wed','thu','fri','sat','sun'] # this is stupid but python weekdays start monday
            nextruns={}
            try:
                now=datetime.datetime.now()
                for automation in self.automations:
                    startdate=None
                    if 'schedules' in self.automations[automation]:
                        for sched in self.automations[automation]['schedules']:
                            try:
                                startdate = self.fixdate(sched['start'])
    
                                if sched['type']=='days':
                                    while now>startdate or wda[startdate.weekday()] not in sched['days']:
                                        startdate=startdate+datetime.timedelta(days=1)
    
                            
                                elif sched['type']=='interval':
                                    if sched['unit']=='days':
                                        idelta=datetime.timedelta(days=int(sched['interval']))
                                    elif sched['unit']=='hours':
                                        idelta=datetime.timedelta(hours=int(sched['interval']))
                                    elif sched['unit']=='min':
                                        idelta=datetime.timedelta(minutes=int(sched['interval']))
                                    elif sched['unit']=='sec':
                                        idelta=datetime.timedelta(seconds=int(sched['interval']))
    
                                    while now>startdate:
                                        startdate=startdate+idelta
                                
                                else:
                                    self.log.warn('!. Unsupported type for %s: %s' % (automation, sched['type']))
    
                                if automation in nextruns:
                                    if startdate < nextruns[automation]:
                                        nextruns[automation]=startdate
                                else:
                                    if startdate:
                                        nextruns[automation]=startdate
                                
                            except:
                                self.log.error('!! Error computing next start for %s' % automation, exc_info=True)

                    if startdate:
                        self.log.debug('** %s next start %s %s %s' % (automation, wda[startdate.weekday()], startdate, sched))
                        self.automations[automation]['nextrun']=nextruns[automation].isoformat()+"Z"
                    else:
                        self.automations[automation]['nextrun']=''

                return nextruns
                
            except:
                self.log.error('Error with next run calc', exc_info=True)


        async def buildLogicCommand(self):
            try:
                logicCommand={"logic": {"command": {"Delay": 0, "Alert":0, "Capture":"", "Reset":"", "Wait":0}}}
                await self.dataset.ingest(logicCommand)
            except:
                self.log.error('Error adding logic commands', exc_info=True)
             
        async def fixAutomationTypes(self):
            
            try:
                for auto in self.automations:
                    changes=False
                    for trigger in self.automations[auto]['triggers']:
                        if "type" not in trigger:
                            trigger['type']="property"
                            changes=True
                    for cond in self.automations[auto]['conditions']:
                        if "type" not in cond:
                            cond['type']="property"
                            changes=True
                    for action in self.automations[auto]['actions']:
                        if "type" not in action:
                            action['type']="command"
                            changes=True
                        elif action['type']=='property':
                            action['type']='command'
                            changes=True
                    
                    if changes:
                        await self.saveAutomation(auto, json.dumps(self.automations[auto]))
            except:
                self.log.error('Error fixing automations', exc_info=True)
                    
                        
                
        async def start(self):
            self.polltime=1
            self.log.info('.. Starting Logic Manager')
            try:
                self.mailconfig=self.loadJSON('mail')
                self.mailsender=mailSender(self.log, self.mailconfig)
                self.users=self.loadJSON('users')
                self.modes=self.loadJSON('modes')
                self.areas=self.loadJSON('areas')
                self.scenes=self.loadJSON('scenes')
                self.security=self.loadJSON('security')
                self.automations=self.loadJSON('automations')
                await self.fixAutomationTypes()
                self.regions=self.loadJSON('regions')
                self.virtualDevices=self.loadJSON('virtualDevices')
                self.eventTriggers=self.buildTriggerList()
                self.calculateNextRun()

                self.capturedDevices={}
                await self.buildLogicCommand()

                for area in self.areas:
                    await self.dataset.ingest({"area": { area : self.areas[area] }})
                
                for auto in self.automations:
                    await self.dataset.ingest({"activity": { auto : self.automations[auto] }})

                for mode in self.modes:
                    await self.dataset.ingest({"mode": { mode : self.modes[mode] }})
                    
                for scene in self.scenes:
                    await self.dataset.ingest({"scene": { scene : self.scenes[scene] }})
                
                await self.pollSchedule()
            
            except GeneratorExit:
                self.running=False    
            except:
                self.log.error('Error loading cached devices', exc_info=True)
                
        async def pollSchedule(self):
            
            while self.running:
                try:
                    await self.checkScheduledItems()
                    await asyncio.sleep(self.polltime)
                except GeneratorExit:
                    self.running=False
                except:
                    self.log.error('Error polling schedule', exc_info=True)
                    self.running=False

                
        async def checkScheduledItems(self):
            try:
                now = datetime.datetime.now()
                for automation in self.automations:
                    try:
                        if self.automations[automation]['nextrun']:
                            if now>self.fixdate(self.automations[automation]['nextrun']):
                                self.log.info('Scheduled run is due: %s %s' % (automation,self.automations[automation]['nextrun']))
                                await self.sendAlexaCommand('Activate', 'SceneController', 'logic:activity:%s' % automation)  
                                self.automations[automation]['lastrun']=now.isoformat()+"Z"
                                self.calculateNextRun()
                                await self.saveAutomation(automation, json.dumps(self.automations[automation]))
                    except:
                        self.log.error('Error checking schedule for %s' % automation, exc_info=True)
            except:
                self.log.error('Error checking scheduled items', exc_info=True)
                    
                
        # Adapter Overlays that will be called from dataset
        def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="activity":
                    return self.addSimpleActivity(path.split("/")[2])
                elif path.split("/")[1]=="mode":
                    return self.addSimpleMode(path.split("/")[2])
                elif path.split("/")[1]=="scene":
                    return self.addSimpleScene(path.split("/")[2])
                elif path.split("/")[1]=="logic":
                    return self.addLogicCommand(path.split("/")[2])
                elif path.split("/")[1]=="area":
                    return self.addArea(path.split("/")[2])

                else:
                    self.log.error('Not adding: %s' % path)

            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False
                
        async def addArea(self, name):
        
            nativeObject=self.dataset.nativeDevices['area'][name]
            
            if name not in self.dataset.devices:
                return self.dataset.addDevice(name, devices.simpleArea('logic:area:%s' % name, name))
            
            return False


        async def addLogicCommand(self, name):
        
            nativeObject=self.dataset.nativeDevices['logic']['command']
            
            if name not in self.dataset.devices:
                return self.dataset.addDevice('Logic', devices.simpleLogicCommand('logic:logic:command', 'Logic'))
            
            return False

        async def addSimpleMode(self, name):
            
            nativeObject=self.dataset.nativeDevices['mode'][name]
            
            if name not in self.dataset.devices:
                return self.dataset.addDevice(name, devices.simpleMode('logic:mode:%s' % name, name))
            
            return False
                
        async def addSimpleActivity(self, name):
            
            nativeObject=self.dataset.nativeDevices['activity'][name]
            
            if name not in self.dataset.devices:
                return self.dataset.addDevice(name, devices.simpleActivity('logic:activity:%s' % name, name))
            
            return False

        async def addSimpleScene(self, name):
            
            nativeObject=self.dataset.nativeDevices['scene'][name]
            
            if name not in self.dataset.devices:
                return self.dataset.addDevice(name, devices.simpleScene('logic:scene:%s' % name, name))
            
            return False

        async def sendAlexaDirective(self, action, trigger={}):
            try:
                if 'value' in action:
                    return await self.sendAlexaCommand(action['command'], action['controller'], action['endpointId'], action['value'], trigger=trigger)
                else:
                    return await self.sendAlexaCommand(action['command'], action['controller'], action['endpointId'], trigger=trigger)
            except:
                self.log.error('Error sending alexa directive: %s' % action, exc_info=True)
                return {}


        async def sendAlexaCommand(self, command, controller, endpointId, payload={}, cookie={}, trigger={}):
            
            try:
                if trigger:
                    cookie["trigger"]=trigger

                header={"name": command, "namespace":"Alexa." + controller, "payloadVersion":"3", "messageId": str(uuid.uuid1()), "correlationToken": str(uuid.uuid1())}
                endpoint={"endpointId": endpointId, "cookie": cookie, "scope":{ "type":"BearerToken", "token":"access-token-from-skill" }}
                data={"directive": {"header": header, "endpoint": endpoint, "payload": payload }}
                
                changereport=await self.dataset.sendDirectiveToAdapter(data)
                return changereport
            except:
                self.log.error('Error executing Alexa Command: %s %s %s %s' % (command, controller, endpointId, payload), exc_info=True)
                return {}

        async def captureDeviceState(self, endpointId, deviceName):
            
            try:
                device=self.getDeviceByfriendlyName(deviceName)
                if device:
                    devprops=await self.dataset.requestReportState(device['endpointId'])
                    self.capturedDevices[deviceName]=devprops
                    self.log.info('Captured prop for %s (%s) - %s' % (deviceName, device['endpointId'], devprops))
            except:
                self.log.error('Error saving device state', exc_info=True)


        async def resetCapturedDeviceState(self, endpointId, deviceName):
            
            try:
                self.log.info('Attempting to reset %s' % deviceName)
                if deviceName in self.capturedDevices:
                    olddevice=self.capturedDevices[deviceName]
                    endpointId=olddevice['event']['endpoint']['endpointId']
                    newdevice=await self.dataset.requestReportState(endpointId)
                
                    oldprops={}
                    for prop in olddevice['context']['properties']:
                        propname="%s.%s" % (prop['namespace'], prop['name'])
                        oldprops[propname]=prop['value']
                
                    newprops={}
                    for prop in newdevice['context']['properties']:
                        propname="%s.%s" % (prop['namespace'], prop['name'])
                        newprops[propname]=prop['value']
                    
                    self.log.info('%s oldprops : %s ' % (deviceName, oldprops))
                    self.log.info('%s newprops : %s ' % (deviceName, newprops))

                    powerOff=False
                    for prop in oldprops:
                        if prop in newprops:
                            if 1==1:  # do it anyway right now because some of the adapters respond too slow or async to changes
                            #if oldprops[prop]!=newprops[prop]:
                                self.log.info('Difference discovered %s - now %s was %s' % (prop, oldprops[prop], newprops[prop]))
                                # Need to figure out how to get back to the command from the property, but for now this
                                # mostly just applies to lights so will shim in this fix
                                if prop=='Alexa.BrightnessController.brightness':
                                    await self.sendAlexaCommand('SetBrightness', 'BrightnessController', endpointId, {"brightness": oldprops[prop]})
                                elif prop=='Alexa.ColorController.color':
                                    await self.sendAlexaCommand('SetColor', 'ColorController', endpointId, {"color" : oldprops[prop]} )
                                elif prop=='Alexa.PowerController.powerState':
                                    if oldprops[prop]=='ON':
                                        await self.sendAlexaCommand('TurnOn', 'PowerController', endpointId)
                                    else:
                                        powerOff=True
                                        # This has to be done last or the other settings will either miss or reset the on
                                        # For lights that are on, bri and color have poweron built in

                    if powerOff:
                        await self.sendAlexaCommand('TurnOff', 'PowerController', endpointId)                        
                                        
                else:
                    self.log.info('Device: %s not in %s' % (deviceName, self.capturedDevices))
                    
            except:
                self.log.error('Error resetting saved device state', exc_info=True)
            

        async def findStateForCondition(self, controller, propertyName, deviceState):
            
            try:
                for prop in deviceState:
                    if propertyName==prop['name'] and controller==prop['namespace'].split('.')[1]:
                        return prop
                
                return False
            except:
                self.log.error('Error finding state for condition: %s %s' % (propertyName, deviceState), exc_info=True)

        def compareCondition(self, conditionValue, operator, propertyValue):
            
            try:
                if operator=='=' or operator=='==':
                    if propertyValue==conditionValue:
                        return True
                elif operator=='!=':
                    if propertyValue!=conditionValue:
                        return True
                elif operator=='>':
                    if propertyValue>conditionValue:
                        return True
                elif operator=='<':
                    if propertyValue<conditionValue:
                        return True
                elif operator=='>=':
                    if propertyValue>=conditionValue:
                        return True
                elif operator=='<=':
                    if propertyValue<=conditionValue:
                        return True
                elif operator=='contains':
                    if str(conditionValue) in str(propertyValue):
                        return True
                
                return False
            except:
                self.log.error('Error comparing condition: %s %s %s' % (conditionValue, operator, propertyValue), exc_info=True)
            
        async def checkLogicConditions(self, conditions, activityName=""):
            
            try:
                devstateCache={}
                conditionMatch=True
                for condition in conditions:
                    if condition['endpointId'] not in devstateCache:
                        devstate=await self.dataset.requestReportState(condition['endpointId'])
                        devstateCache[condition['endpointId']]=devstate['context']['properties']
                    devstate=devstateCache[condition['endpointId']]
                    prop=await self.findStateForCondition(condition['controller'], condition['propertyName'], devstate)
                    if prop==False:
                        self.log.info('!. %s did not find property for condition: %s vs %s' % (activityName, condition, devstate))
                        conditionMatch=False
                        break
                    
                    if 'value' in condition['value']:
                        condval=condition['value']['value']
                        if not self.compareCondition(condval,condition['operator'],prop['value']):
                            self.log.info('!. %s did not meet condition: %s vs %s' % (activityName, prop['value'], condval))
                            conditionMatch=False
                            break
                        
                    elif 'end' in condition['value']:
                        condval=condition['value']
                        st=datetime.datetime.strptime(condition['value']['start'],"%H:%M").time()
                        et=datetime.datetime.strptime(condition['value']['end'],"%H:%M").time()
                        ct=self.fixdate(prop['value']).time()
                        if st<ct and et>ct:
                            self.log.info('Passed time check: %s<%s<%s' % (st, ct, et))
                            pass
                        else:
                            self.log.info('Failed time check: %s<%s<%s' % (st, ct, et))
                            conditionMatch=False
                            break

                return conditionMatch
            except:
                self.log.error('Error with chunky Activity', exc_info=True)  
                
        async def runActivity(self, activityName, trigger={}, triggerEndpointId=''):
            
            try:
                if 'conditions' in self.automations[activityName]:
                    if not await self.checkLogicConditions(self.automations[activityName]['conditions'], activityName=activityName):
                        return False
                
                activity=self.automations[activityName]['actions']
                chunk=[]
                for action in activity:
                    if action['command']=="Delay":
                        chunk.append(action)
                        result=await self.runActivityChunk(chunk)
                        #self.log.info('Result of Pre-Delay chunk: %s' % result)
                        chunk=[]
                    elif action['command']=="Wait":
                        result=await self.runActivityChunk(chunk)
                        #self.log.info('Result of chunk: %s' % result)
                        chunk=[]
                    elif action['command']=="Alert":
                        alert=copy.deepcopy(action)
                        if trigger:
                            self.log.info('Trigger: %s' % trigger)
                            if 'endpointId' in trigger:
                                deviceName=self.getfriendlyNamebyendpointId(trigger['endpointId'])
                                alert['value']['message']['text']=alert['value']['message']['text'].replace('[deviceName]',deviceName)
                            if 'value' in trigger:
                                avals={'DETECTED':'open', 'NOT_DETECTED':'closed'}
                                alert['value']['message']['text']=alert['value']['message']['text'].replace('[value]',avals[trigger['value']])
                        self.log.info('Result of Alert Macro: %s vs %s / trigger: %s ' % (alert,action, trigger))
                        chunk.append(alert)
                                
                    else:
                        chunk.append(action)
                if chunk:
                    result=await self.runActivityChunk(chunk)

                self.automations[activityName]['lastrun']=datetime.datetime.now().isoformat()+"Z"
                await self.saveAutomation(activityName, json.dumps(self.automations[activityName]))
                    
                return result
                
            except:
                self.log.error('Error with chunky Activity', exc_info=True)

        async def runActivityChunk(self, chunk ):
        
            try:
                allacts = await asyncio.gather(*[self.sendAlexaDirective(action) for action in chunk ])
                #self.log.info('chunk result: %s' % allacts)
                return allacts
            except:
                self.log.error('Error executing activity', exc_info=True)
            
        async def runScene(self, sceneName):
        
            try:
                scene=self.scenes[sceneName]
                acts=[]
                
                for light in scene:
                    try:
                        self.log.info('scene dev: %s' % self.dataset.getDeviceByfriendlyName(light))
                        epid=self.dataset.getDeviceByfriendlyName(light)['endpointId']
                    except:
                        self.log.error('Error gettind endpointId for %s' % light, exc_info=True)
                        continue
                    if int(scene[light]['brightness'])==0:
                        acts.append({'command':'TurnOff', 'controller':'PowerController', 'endpointId':epid, 'value': None})
                    else:
                        if 'hue' in scene[light]:
                            acts.append({'command':'SetColor', 'controller':'ColorController', 'endpointId':epid, "value": { 'color': { 
                                "brightness": scene[light]['brightness']/100,
                                "saturation": scene[light]['saturation'],
                                "hue": scene[light]['hue'] }}})
                        else:
                            acts.append({'command':'SetBrightness', 'controller':'BrightnessController', 'endpointId':epid, 'value': { "brightness": int(scene[light]['brightness']) }} )

                        
                allacts = await asyncio.gather(*[self.sendAlexaDirective(action) for action in acts ])
                self.log.info('scene %s result: %s' % (sceneName, allacts))    
            except:
                self.log.error('Error executing Scene', exc_info=True)

        async def imageGetter(self, item, thumbnail=False):

            try:
                source=item.split('/',1)[0] 
                if source in self.dataset.adapters:
                    result='#'
                    if thumbnail:
                        url = 'http://%s:%s/thumbnail/%s' % (self.dataset.adapters[source]['address'], self.dataset.adapters[source]['port'], item.split('/',1)[1] )
                    else:
                        url = 'http://%s:%s/image/%s' % (self.dataset.adapters[source]['address'], self.dataset.adapters[source]['port'], item.split('/',1)[1] )
                    async with aiohttp.ClientSession() as client:
                        async with client.get(url) as response:
                            result=await response.read()
                            return result
                            #result=result.decode()
                            if str(result)[:10]=="data:image":
                                #result=base64.b64decode(result[23:])
                                self.imageCache[item]=str(result)
                                return result
                return None
    
            except concurrent.futures._base.CancelledError:
                self.log.error('Error getting image %s (cancelled)' % item)
            except:
                self.log.error('Error getting image %s' % item, exc_info=True)
                return None
                
        async def runAlert(self, message, image=None):
            
            try:
                if message.startswith('Garage Door') or message.startswith('Garage Side Door'):
                    camera='driveway'
                elif message.startswith('Doorbell') or message.startswith('Front Door') or message.startswith('Office Window') or message.startswith('Front Gate'):
                    camera='frontdoor'
                elif message.startswith('Stairs Door'):
                    camera='garage'
                else:
                    camera=''
                
                if camera:
                    image=await self.imageGetter('dlink/camera/'+camera)
                    
                for user in self.users:
                    if self.users[user]['alerts']:
                        self.mailsender.sendmail(self.users[user]['email'], '', message+' @'+datetime.datetime.now().strftime("%l:%M.%S%P")[:-1], image)
                        asyncio.sleep(.5)
            except:
                self.log.error('Error sending alert', exc_info=True)
                        
        async def processDirective(self, endpointId, controller, command, payload, correlationToken='', cookie={}):
            
            try:
                device=endpointId.split(":")[2]
                nativeCommand={}
                
                if controller=="PowerController":
                    if device in self.modes:
                        self.log.info('Modes: %s ' % self.modes)
                        if command=="TurnOn":
                            changes=await self.dataset.ingest({ "mode" : { device: {'active':True }}})
                            self.saveJSON('modes',self.modes)
                        if command=="TurnOff":
                            
                            changes=await self.dataset.ingest({ "mode" : { device: {'active':False }}})
                            self.saveJSON('modes',self.modes)
                        self.log.info('Changes: %s' % changes)
                        response=await self.dataset.generateResponse(endpointId, correlationToken)
                        return response
                        
                
                if controller=="LogicController":
                    if command=='Alert':
                        self.log.info('Sending Alert: %s' % payload['message']['text'])
                        await self.runAlert(payload['message']['text'])
                    if command=='Delay':
                        self.log.info('Delaying for %s seconds' % payload['duration'])
                        await asyncio.sleep(int(payload['duration']))
                    if command=='Capture':
                        await self.captureDeviceState(payload['device']['endpointId'],payload['device']['name'])
                    if command=='Reset':
                        await self.resetCapturedDeviceState(payload['device']['endpointId'],payload['device']['name'])
                    else:
                        # Not a supported command then
                        return {}
                        
                    response=await self.dataset.generateResponse(endpointId, correlationToken)
                    return response
                        
                if controller=="SceneController":
                    if command=="Activate":
                        trigger={}
                        if 'trigger' in cookie:
                            trigger=cookie['trigger']
                        triggerEndPointId=''
                        if 'triggerEndpointId' in cookie:
                            triggerEndPointId=cookie['triggerEndPointId']
                        if device in self.automations:
                            task = asyncio.ensure_future(self.runActivity(device, trigger, triggerEndPointId))
                            #self.log.info('Started automation as task: %s /%s' % (device, task))
                            return self.dataset.getDeviceByEndpointId(endpointId).ActivationStarted(endpointId)
                            # This should return the scene started ack
                        elif device in self.scenes:
                            await self.runScene(device)
                            # This should return the scene started ack - i took out the await so maybe the response will go through?
                        else:
                            self.log.info('Could not find scene or activity: %s' % device)
                            return {}
                    
                        response=await self.dataset.generateResponse(endpointId, correlationToken)
                        return response
                            
                            
                self.log.info('Could not find any supported action: %s' % device)
                return {}
                
            except:
                self.log.error('Error applying state change', exc_info=True)
                return []
                
            
        def virtualControllers(self, itempath):

            try:
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                self.log.debug('Checking object for controllers: %s' % nativeObject)
                try:
                    detail=itempath.split("/",3)[3]
                except:
                    detail=""

                controllerlist={}
                if itempath.startswith('/mode'):
                    controllerlist["PowerController"]=["powerState"]
                elif itempath.startswith('/logic'):
                    if detail=='time' or detail=='':
                        controllerlist["LogicController"]=["time"]
                elif itempath.startswith('/area'):
                    controllerlist["AreaController"]=["children","shortcuts"]


                return controllerlist
            except KeyError:
                pass
            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)

        def virtualControllerProperty(self, nativeObj, controllerProp):
            
            try:
                if controllerProp=='powerState':
                    return "ON" if nativeObj['active'] else "OFF"
                if controllerProp=='time':
                    return datetime.datetime.now().time()
                if controllerProp=='children':
                    return nativeObj['children']
                if controllerProp=='shortcuts':
                    if 'newshortcuts' in nativeObj:
                        return nativeObj['newshortcuts']
                    return []

            except:
                self.log.error('Error converting virtual controller property: %s %s' % (controllerProp, nativeObj), exc_info=True)
                return False

        def buildTriggerList(self):
            
            triggerlist={}
            try:
                for automation in self.automations:
                    if 'triggers' in self.automations[automation]:
                        for trigger in self.automations[automation]['triggers']:
                            try:
                                if trigger['type']=='property':
                                    trigname="%s.%s.%s=%s" % (trigger['endpointId'], trigger['controller'], trigger['propertyName'], trigger['value'])
                                elif trigger['type']=='event':
                                    trigname="event=%s.%s.%s" % (trigger['endpointId'], trigger['controller'], trigger['propertyName'])
                                    self.log.debug('Event trigger: %s' % trigname)

                                else:
                                    self.log.info('Skipping unknown trigger type: %s' % trigger)
                                    continue
                                if trigname not in triggerlist:
                                    triggerlist[trigname]=[]
                                triggerlist[trigname].append({ 'name':automation, 'type':'automation' })
                            except:
                                self.log.error('Error computing trigger shorthand for %s %s' % (automation,trigger), exc_info=True)
                            
                self.log.debug('Triggers: %s' % (len(triggerlist)))
            except:
                self.log.error('Error calculating trigger shorthand:', exc_info=True)
            
            return triggerlist

        async def runEvents(self, events, change, trigger=''):
        
            try:
                actions=[]
                for event in events:
                    self.log.info('.. Triggered Event: %s' % event)
                    if event['type']=='event':
                        action=self.events[event['name']]['action']
                    elif event['type']=='automation':
                        action={"controller": "SceneController", "command":"Activate", "endpointId":"logic:activity:"+event['name']}
                    
                    if "value" in action:
                        aval=action['value']
                    else:
                        action['value']=''
                        
                    actions.append(action)
                    
                allacts = await asyncio.gather(*[self.sendAlexaDirective(action, trigger=change) for action in actions ])
                self.log.info('.. Trigger %s result: %s' % (change, allacts))
                return allacts
            except:
                self.log.error('Error executing event reactions', exc_info=True)

        def runEventsThread(self, events, change, trigger='', loop=None):
        
            try:
                actions=[]
                for event in events:
                    #self.log.info('.. Triggered Event: %s' % event)
                    if event['type']=='event':
                        action=self.events[event['name']]['action']
                    elif event['type']=='automation':
                        action={"controller": "SceneController", "command":"Activate", "endpointId":"logic:activity:"+event['name']}
                    
                    if "value" in action:
                        aval=action['value']
                    else:
                        action['value']=''
                        
                    actions.append(action)
                
                allacts = asyncio.ensure_future(asyncio.gather(*[self.sendAlexaDirective(action, trigger=change) for action in actions ], loop=loop), loop=loop)
                #self.log.info('.. Trigger %s result: %s' % (change, allacts))
                return allacts
            except:
                self.log.error('Error executing threaded event reactions', exc_info=True)
                            
       
        async def virtualChangeHandler(self, deviceId, change):
            
            try:
                trigname="%s.%s.%s=%s" % (deviceId, change['namespace'].split('.')[1], change['name'], change['value'])
                if trigname in self.eventTriggers:
                    self.log.info('!+ This is a trigger we are watching for: %s %s' % (trigname, change))
                    change['endpointId']=deviceId
                    self.loop.run_in_executor(self.logicpool, self.runEventsThread, self.eventTriggers[trigname], change, trigname, self.loop)
                    #await self.runEvents(self.eventTriggers[trigname], change, trigname)
            except:
                self.log.error('Error in virtual change handler: %s %s' % (deviceName, change), exc_info=True)

        async def virtualEventHandler(self, event, source, deviceId, message):
            
            try:
                trigname="event=%s.%s.%s" % (deviceId, source, event)
                self.log.info('Event trigger: %s' % trigname)
                if trigname in self.eventTriggers:
                    self.log.info('!+ This is an event trigger we are watching for: %s %s' % (trigname, message))
                    #await self.runEvents(self.eventTriggers[trigname], message, trigname)
                    self.loop.run_in_executor(self.logicpool, self.runEventsThread, self.eventTriggers[trigname], message, trigname, self.loop)

            except:
                self.log.error('Error in virtual event handler: %s %s %s' % (event, deviceId, message), exc_info=True)


        async def buildRegion(self, thisRegion=None):
            
            try:
                reg={}
                for region in self.regions:
                    reg[region]={ 'scenes': {}, 'areas':{} }
                    for area in self.regions[region]['areas']:
                        reg[region]['areas'][area]=self.areas[area]
                        for scene in self.areas[area]['scenes']:
                            reg[region]['scenes'][scene]=self.scenes[scene]
                            
                if thisRegion:
                    return reg[thisRegion]
                    
                return reg
            except:
                self.log.info('Error building region data: %s' % region, exc_info=True)
            


        async def virtualList(self, itempath, query={}):

            try:
                if itempath=="automations":
                    return self.automations

                if itempath=='schedule':
                    scheduled=[]
                    for automation in self.automations:
                        try:
                            if self.automations[automation]['nextrun']:
                                scheduled.append({"name":automation, "nextrun":self.automations[automation]['nextrun'], "lastrun": self.automations[automation]['lastrun'], "schedule":self.automations[automation]['schedules']})
                        except:
                            self.log.info('Not including %s' % automation,exc_info=True)
                    ss = sorted(scheduled, key=itemgetter('nextrun'))
                    #ss.reverse()
                    self.log.info('Sched: %s' % ss)
                    return ss                
                if itempath=="scenes":
                    return self.scenes

                if itempath=="security":
                    return self.security

                if itempath=="areas":
                    return self.areas

                if itempath=="events":
                    self.loadEvents()
                    return {"events": self.events, "triggers": self.eventTriggers}
                    
                if itempath=="regions":
                    return await self.buildRegion()

                if itempath=="virtualDevices":
                    return self.virtualDevices
                    
                if itempath=="automationlist":
                    al={}
                    for auto in self.automations:
                        if 'conditions' not in self.automations[auto]:
                            self.automations[auto]['conditions']=[]
                        if 'triggers' not in self.automations[auto]:
                            self.automations[auto]['triggers']=[]
                        if 'favorite' not in self.automations[auto]:
                            self.automations[auto]['favorite']=False

                        al[auto]={ 'favorite':self.automations[auto]['favorite'], 'lastrun': self.automations[auto]['lastrun'], 'triggerCount': len(self.automations[auto]['triggers']), 'actionCount': len(self.automations[auto]['actions']), 'conditionCount': len(self.automations[auto]['conditions']), 'endpointId':'logic:activty:%s' % auto }
                    return al

                if itempath=="arealist":
                    al={}
                    for area in self.areas:
                        al[area]={ 'lights': self.areas[area]['lights'], 'scenes': self.areas[area]['lights'] }
                    return al

                if itempath=="regionlist":
                    al={}
                    for region in self.regions:
                        al[region]={ 'count': len(self.regions[region]['rooms']) }
                    return al
                    
                if '/' in itempath:
                    ip=itempath.split('/')
                    if ip[0]=='automation':
                        if ip[1] in self.automations:
                            return self.automations[ip[1]]
                    if ip[0]=='region':
                        if ip[1] in self.regions:
                            return await self.buildRegion(ip[1])
                            #return self.regions[ip[1]]['rooms']
                    if ip[0]=='area':
                        if ip[1] in self.areas:
                            return self.areas[ip[1]]
                    if ip[0]=='arealights':
                        if ip[1] in self.areas:
                            return self.areas[ip[1]]['lights']
                    if ip[0]=='areascenes':
                        if ip[1] in self.areas:
                            return self.areas[ip[1]]['scenes']
                        else:
                            result={}

                        if ip[1] in self.areas:
                            result['lights']=self.areas[ip[1]]['lights']
                        return result
                    
                return {}

            except:
                self.log.error('Error getting virtual list for %s' % itempath, exc_info=True)
                

if __name__ == '__main__':
    adapter=logicServer(name='logic')
    adapter.start()
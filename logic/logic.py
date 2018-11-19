#!/usr/bin/python3

import sys
sys.path.append('/opt/beta')

from sofabase import sofabase
from sofacollector import SofaCollector
from sendmail import mailSender

import devices
import json
import asyncio
import concurrent.futures
import datetime
import time
import uuid
import aiohttp
from aiohttp import web


class logicServer(sofabase):
    
    class adapterProcess(SofaCollector.collectorAdapter):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.dataset.nativeDevices['scene']={}
            self.dataset.nativeDevices['activity']={}
            self.dataset.nativeDevices['logic']={}
            self.dataset.nativeDevices['mode']={}

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
                elif dp[0]=='schedule':
                    result=await self.saveScheduleWeb(dp[1], data)  
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

        async def virtualDel(self, datapath, data):
            
            try:
                dp=datapath.split("/")
                if dp[0]=='automation':
                    result=await self.delAutomation(dp[1])
                elif dp[0]=='scene':
                    result=await self.delScene(dp[1])  
                elif dp[0]=='schedule':
                    result=await self.delSchedule(dp[1])  
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
                elif dp[0]=='schedule':
                    result=await self.saveScheduleWeb(dp[1], data)  
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
                    self.automations[name]={"lastrun": "never", "actions": [], "conditions": []}
                
                if 'actions' in data:
                    self.automations[name]['actions']=data['actions']
                if 'conditions' in data:
                    self.automations[name]['conditions']=data['conditions']
                if 'triggers' in data:
                    self.automations[name]['triggers']=data['triggers']

                self.saveJSON('/opt/beta/config/automations.json',self.automations)
                self.eventTriggers=self.buildTriggerList()
                return True
            except:
                self.log.error('Error saving automation: %s %s' % (name, data), exc_info=True)
                return False

        async def saveScene(self, name, data):
            
            try:
                data=json.loads(data)
                self.scenes[name]=data
                self.saveJSON('/opt/beta/config/scenes.json',self.scenes)
                return True
            except:
                self.log.error('Error saving automation: %s %s' % (name, data), exc_info=True)
                return False


        async def delAutomation(self, name):
            
            try:
                if name in self.automations:
                    del self.automations[name]
                
                self.saveJSON('/opt/beta/config/automations.json',self.automations)
                return True
            except:
                self.log.error('Error deleting automation: %s' % name, exc_info=True)
                return False

        async def delSchedule(self, name):
            
            try:
                if name in self.schedule:
                    del self.schedule[name]
                
                self.saveJSON('/opt/beta/config/schedule.json',self.schedule)
                self.calculateNextRun()
                return True
            except:
                self.log.error('Error deleting automation: %s' % name, exc_info=True)
                return False

        async def delRegion(self, name):
            
            try:
                if name in self.regions:
                    del self.regions[name]
                
                self.saveJSON('/opt/beta/config/regions.json',self.regions)
                return True
            except:
                self.log.error('Error deleting automation: %s' % name, exc_info=True)
                return False

        async def delArea(self, name):
            
            try:
                if name in self.areas:
                    del self.areas[name]
                
                self.saveJSON('/opt/beta/config/areas.json',self.areas)
                return True
            except:
                self.log.error('Error deleting automation: %s' % name, exc_info=True)
                return False


        def loadJSON(self, configname):
        
            try:
                with open('/opt/beta/config/%s.json' % configname,'r') as jsonfile:
                    return json.loads(jsonfile.read())
            except:
                self.log.error('Error loading pattern: %s' % jsonfilename,exc_info=True)
                return {}


        async def saveScheduleWeb(self, name, data):
            
            try:
                self.log.info('Saving Schedule: %s %s' % (name, data))
                if type(data)==str:
                    data=json.loads(data)
                    
                self.schedule[name]=data

                self.saveJSON('/opt/beta/config/schedule.json',self.schedule)
                self.calculateNextRun()
                return True
            except:
                self.log.error('Error saving schedule: %s %s' % (name, data), exc_info=True)
                return False

        async def saveArea(self, name, data):
            
            try:
                self.log.info('Saving Area: %s %s' % (name, data))
                if type(data)==str:
                    data=json.loads(data)
                    
                self.areas[name]=data

                self.saveJSON('/opt/beta/config/areas.json',self.areas)

                return True
            except:
                self.log.error('Error saving schedule: %s %s' % (name, data), exc_info=True)
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

                    self.saveJSON('/opt/beta/config/regions.json',self.regions)
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
                for sched in self.schedule:
                    #self.log.info('Checking: %s %s' % (sched,self.schedule[sched]))
                    startdate = self.fixdate(self.schedule[sched]['start'])
                    if self.schedule[sched]['type']=='specificTime':
                        try:
                            runtime = datetime.datetime.strptime(self.schedule[sched]['schedule']['at'],'%H:%M')
                        except ValueError as v:
                            # if it includes seconds or microseconds, strp will fail with the value error
                            ulr = len(v.args[0].partition('unconverted data remains: ')[2])
                            if ulr:
                                runtime = datetime.datetime.strptime(self.schedule[sched]['schedule']['at'][:-ulr], '%H:%M')
                                
                        if self.schedule[sched]['schedule']['daysType']=='daysOfTheWeek':
                            if startdate>now:
                                #self.log.info('Starts in the future: %s' % self.schedule[sched]['start'])
                                onStartDate=startdate.replace(hour=runtime.hour, minute=runtime.minute)
                                
                                if onStartDate>startdate:  # see if this is later in the day and if not, add a day
                                    startdate=onStartDate
                                else:
                                    startdate=onStartDate+datetime.timedelta(days=1)
                            else:
                                startdate=now.replace(hour=runtime.hour, minute=runtime.minute)
                                if now>startdate:
                                    startdate=startdate+datetime.timedelta(days=1)
                                    
                            if self.schedule[sched]['lastrun']!='never':
                                lastrun=self.fixdate(self.schedule[sched]['lastrun'])
                                if lastrun.replace(hour=runtime.hour, minute=runtime.minute)+datetime.timedelta(days=1) >= startdate:
                                    startdate=lastrun.replace(hour=runtime.hour, minute=runtime.minute)+datetime.timedelta(days=1)
                                    
                            while wda[startdate.weekday()] not in self.schedule[sched]['schedule']['days']:
                                startdate=startdate+datetime.timedelta(days=1)
                                
                            self.log.info('** %s next start %s %s %s' % (sched, wda[startdate.weekday()], startdate, self.schedule[sched]))
                            nextruns[sched]=startdate
                        
                        elif self.schedule[sched]['schedule']['daysType']=='interval':
                            if startdate>now:
                                #self.log.info('Starts in the future: %s' % self.schedule[sched]['start'])
                                if startdate.replace(hour=runtime.hour, minute=runtime.minute) >= startdate:
                                    startdate=startdate.replace(hour=runtime.hour, minute=runtime.minute)
                                else:
                                    startdate=startdate.replace(hour=runtime.hour, minute=runtime.minute)+datetime.timedelta(days=1)
                            else:
                                delta = now - startdate
                                interval=int(self.schedule[sched]['schedule']['interval'])
                                if startdate.replace(hour=runtime.hour, minute=runtime.minute) >= startdate:
                                    startdate=startdate.replace(hour=runtime.hour, minute=runtime.minute)
                                else:
                                    startdate=startdate.replace(hour=runtime.hour, minute=runtime.minute)+datetime.timedelta(days=1)
                                
                                if self.schedule[sched]['lastrun']!='never':
                                    lastrun=self.fixdate(self.schedule[sched]['lastrun'])
                                    if lastrun.replace(hour=runtime.hour, minute=runtime.minute) >= startdate:
                                        startdate=lastrun.replace(hour=runtime.hour, minute=runtime.minute)
                                
                                while startdate < now:
                                    startdate=startdate+datetime.timedelta(days=interval)
                                    
                            self.log.info('** %s next start %s %s %s' % (sched, wda[startdate.weekday()], startdate, self.schedule[sched]))
                            nextruns[sched]=startdate
 
                    elif self.schedule[sched]['type']=='interval':  
                        startdate = self.fixdate(self.schedule[sched]['start'])
                        if startdate>now:
                            self.log.info('** Starts in the future: %s %s' % (sched, self.schedule[sched]['start']))
                            nextruns[sched]=startdate
                        else:
                            if self.schedule[sched]['lastrun']=='never':
                                delta = now - startdate
                            else:
                                delta = self.fixdate(self.schedule[sched]['lastrun']) - startdate
                                
                            interval=int(self.schedule[sched]['schedule']['interval'])
                            unit=self.schedule[sched]['schedule']['unit']
                            
                            if unit=='minute':
                                delta_minutes = delta.days * 24 * 60 + delta.seconds / 60
                                #self.log.info('Number of %s since start: %s / %s / %s ' % ( unit, delta_minutes, interval, delta_minutes//interval))
                                totalint=(delta_minutes//interval)*interval+interval
                                startdate=startdate+datetime.timedelta(seconds=totalint*60)
                                self.log.info('** %s next start %s %s %s' % (sched, wda[startdate.weekday()], startdate, self.schedule[sched]))
                                nextruns[sched]=startdate
                                
                            elif unit=='hour':
                                delta_hours = delta.days * 24 + delta.seconds / 3600.0
                                #self.log.info('Number of %s since start: %s / %s / %s ' % ( unit, delta_hours, interval, delta_hours//interval))
                                totalint=(delta_hours//interval)*interval+interval
                                startdate=startdate+datetime.timedelta(seconds=totalint*60*60)
                                self.log.info('** %s next start %s %s %s' % (sched, wda[startdate.weekday()], startdate, self.schedule[sched]))
                                nextruns[sched]=startdate
                            
                            elif unit=='day':
                                #self.log.info('Number of %s since start: %s / %s / %s ' % ( unit, delta.days, interval, delta.days/interval))
                                totalint=(delta.days//interval)*interval+interval
                                startdate=startdate+datetime.timedelta(days=totalint)
                                self.log.info('** %s next start %s %s %s' % (sched, wda[startdate.weekday()], startdate, self.schedule[sched]))
                                nextruns[sched]=startdate
                                
                for nextrun in nextruns:
                    # update schedule so it is available to the web ui
                    self.schedule[nextrun]['nextrun']=nextruns[nextrun]
                return nextruns
                
            except:
                self.log.error('Error with next run calc: %s' % self.schedule, exc_info=True)

                
        def saveJSON(self, jsonfilename, data):
        
            try:
                jsonfile = open(jsonfilename, 'wt')
                json.dump(data, jsonfile, ensure_ascii=False, default=self.jsonDateHandler)
                jsonfile.close()
            except:
                self.log.error('Error saving json to %s' % jsonfilename, exc_info=True)


        async def buildLogicCommand(self):
            try:
                logicCommand={"logic": {"command": {"Delay": 0, "Alert":0, "Capture":"", "Reset":"", "Wait":0}}}
                await self.dataset.ingest(logicCommand)
            except:
                self.log.error('Error adding logic commands', exc_info=True)
                
                
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
                self.automations=self.loadJSON('automations')
                self.regions=self.loadJSON('regions')
                self.schedule=self.loadJSON('schedule')
                self.virtualDevices=self.loadJSON('virtualDevices')
                self.log.info('self.users: %s' % self.users)
                self.eventTriggers=self.buildTriggerList()
                self.calculateNextRun()

                self.capturedDevices={}
                await self.buildLogicCommand()
                
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
                for sched in self.schedule:
                    if now>self.schedule[sched]['nextrun']:
                        self.log.info('Scheduled run is due: %s %s' % (sched,self.schedule[sched]['nextrun']))
                        action=self.schedule[sched]['action']
                        await self.sendAlexaCommand(action['command'], action['controller'], action['endpointId'], action['value'])  
                        self.schedule[sched]['lastrun']=now.isoformat()+"Z"
                        await self.saveScheduleWeb(sched, self.schedule[sched])
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
                else:
                    self.log.error('Not adding: %s' % path)

            except:
                self.log.error('Error defining smart device', exc_info=True)
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


        async def sendAlexaCommand(self, command, controller, endpointId, payloadvalue=None, cookie={}, trigger={}):
            
            try:
                
                #self.log.info('obj: %s' % getattr(devices,controller+'Interface')().commands)
                objcommands=getattr(devices,controller+'Interface')().commands
                if command in objcommands:
                    payload=objcommands[command]
                else:
                    payload={}
                    
                for prop in payload:
                    if payload[prop]=='value':
                        payload[prop]=payloadvalue
                        
                if trigger:
                    cookie={ "trigger": trigger }


                header={"name": command, "namespace":"Alexa." + controller, "payloadVersion":"3", "messageId": str(uuid.uuid1()), "correlationToken": str(uuid.uuid1())}
                endpoint={"endpointId": endpointId, "cookie": cookie, "scope":{ "type":"BearerToken", "token":"access-token-from-skill" }}
                data={"directive": {"header": header, "endpoint": endpoint, "payload": payload }}
                
                changereport=await self.dataset.sendDirectiveToAdapter(data)
                return changereport
            except:
                self.log.error('Error executing Alexa Command', exc_info=True)
                return {}

        async def captureDeviceState(self, deviceName):
            
            try:            
                device=self.getDeviceByfriendlyName(deviceName)
                if device:
                    devprops=await self.dataset.requestReportState(device['endpointId'])
                    self.capturedDevices[deviceName]=devprops
                    self.log.info('Captured prop for %s (%s) - %s' % (deviceName, device['endpointId'], devprops))
            except:
                self.log.error('Error saving device state', exc_info=True)


        async def resetCapturedDeviceState(self, deviceName):
            
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
                    
                    powerOff=False
                    for prop in oldprops:
                        if prop in newprops:
                            if oldprops[prop]!=newprops[prop]:
                                self.log.info('Difference discovered %s - now %s was %s' % (prop, oldprops[prop], newprops[prop]))
                                # Need to figure out how to get back to the command from the property, but for now this
                                # mostly just applies to lights so will shim in this fix
                                if prop=='Alexa.BrightnessController.brightness':
                                    await self.sendAlexaCommand('SetBrightness', 'BrightnessController', endpointId, oldprops[prop])
                                elif prop=='Alexa.ColorController.color':
                                    await self.sendAlexaCommand('SetColor', 'ColorController', endpointId, oldprops[prop])
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
            
            

        async def runActivityWait(self, activityName, trigger={}):
            
            try:
                devstateCache={}
                conditionlist=[]
                conditionMatch=True
                if 'conditions' in self.automations[activityName]:
                    conditions=self.automations[activityName]['conditions']
                    for condition in conditions:
                        if condition['endpointId'] not in devstateCache:
                            devstate=await self.dataset.requestReportState(condition['endpointId'])
                            devstateCache[condition['endpointId']]=devstate['context']['properties']
                        devstate=devstateCache[condition['endpointId']]
                        self.log.info('Devstate from condition for %s: %s' % (condition['endpointId'], devstate))
                        for prop in devstate:
                            if prop['namespace'].split('.')[1]==condition['controller'] and prop['name']==condition['propertyName']:
                                if condition['operator']=='=' or condition=='==':
                                    if prop['value']==condition['value']:
                                        break
                                elif condition['operator']=='!=':
                                    if prop['value']!=condition['value']:
                                        break
                                elif condition['operator']=='>':
                                    if prop['value']>condition['value']:
                                        break
                                elif condition['operator']=='<':
                                    if prop['value']<condition['value']:
                                        break
                                elif condition['operator']=='>=':
                                    if prop['value']>=condition['value']:
                                        break
                                elif condition['operator']=='<=':
                                    if prop['value']<=condition['value']:
                                        break
                                elif condition['operator']=='contains':
                                    if str(condition['value']) in str(prop['value']):
                                        break
                                self.log.info('Did not meet condition: %s %s' % (prop, condition))
                                conditionMatch=False
                                break
                                    

                    if not conditionMatch:           
                        self.log.info('Did not meet conditions')
                        return False
                        
                activity=self.automations[activityName]['actions']
                chunk=[]
                for action in activity:
                    if action['command']=="Delay":
                        chunk.append(action)
                        result=await self.runActivityChunk(chunk)
                        self.log.info('Result of Pre-Delay chunk: %s' % result)
                        chunk=[]
                    elif action['command']=="Wait":
                        result=await self.runActivityChunk(chunk)
                        self.log.info('Result of chunk: %s' % result)
                        chunk=[]
                    elif action['command']=="Alert":
                        alert=action.copy()
                        if trigger:
                            if 'deviceName' in trigger:
                                alert['value']=alert['value'].replace('[deviceName]',trigger['deviceName'])
                            if 'value' in trigger:
                                alert['value']=alert['value'].replace('[value]',trigger['value'])
                        self.log.info('Result of Alert Macro: %s vs %s / trigger: %s ' % (alert,action, trigger))
                        chunk.append(alert)
                                
                    else:
                        chunk.append(action)
                if chunk:
                    result=await self.runActivityChunk(chunk)
                    
                return result
                
            except:
                self.log.error('Error with chunky Activity', exc_info=True)

        async def runActivityChunk(self, chunk ):
        
            try:
                allacts = await asyncio.gather(*[self.sendAlexaCommand(action['command'], action['controller'], action['endpointId'], action['value']) for action in chunk ])
                self.log.info('chunk result: %s' % allacts)
                return allacts
            except:
                self.log.error('Error executing activity', exc_info=True)
            
        async def runScene(self, sceneName):
        
            try:
                scene=self.scenes[sceneName]
                acts=[]
                
                for light in scene:
                    if int(scene[light]['brightness'])==0:
                        acts.append({'command':'TurnOff', 'controller':'PowerController', 'endpointId':light, 'value': None})
                    else:
                        acts.append({'command':'SetBrightness', 'controller':'BrightnessController', 'endpointId':light, 'value': int(scene[light]['brightness']) } )
                        
                allacts = await asyncio.gather(*[self.sendAlexaCommand(action['command'], action['controller'], action['endpointId'], action['value']) for action in acts ])
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
            
            # CHEESE: This needs to be coded to properly handle activation responses and to move from changereports
            # 
            
            try:
                device=endpointId.split(":")[2]
                nativeCommand={}
                
                if controller=="PowerController":
                    if device in self.modes:
                        self.log.info('Modes: %s ' % self.modes)
                        if command=="TurnOn":
                            changes=await self.dataset.ingest({ "mode" : { device: {'active':True }}})
                            self.saveJSON('/opt/beta/config/modes.json',self.modes)
                        if command=="TurnOff":
                            
                            changes=await self.dataset.ingest({ "mode" : { device: {'active':False }}})
                            self.saveJSON('/opt/beta/config/modes.json',self.modes)
                        self.log.info('Changes: %s' % changes)
                        response=await self.dataset.generateResponse(endpointId, correlationToken)
                        return response
                        
                
                if controller=="LogicController":
                    if command=='Alert':
                        self.log.info('Sending Alert: %s' % payload['message'])
                        await self.runAlert(payload['message'])
                    if command=='Delay':
                        self.log.info('Delaying for %s seconds' % payload['duration'])
                        await asyncio.sleep(int(payload['duration']))
                    if command=='Capture':
                        await self.captureDeviceState(payload['device'])
                    if command=='Reset':
                        await self.resetCapturedDeviceState(payload['device'])
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

                        if device in self.automations:
                            await self.runActivityWait(device, trigger)
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
                
                

        async def xstateChange(self, endpointId, controller, command, payload):
    
            try:
                device=endpointId.split(":")[2]
                #self.log.info('Directive: %s %s %s %s' % (device, controller, command, payload))

                if controller=="PowerController":
                    if device in self.modes:
                        self.log.info('Modes: %s ' % self.modes)
                        if command=="TurnOn":
                            changes=await self.dataset.ingest({ "mode" : { device: {'active':True }}})
                            self.saveJSON('/opt/beta/config/modes.json',self.modes)
                        if command=="TurnOff":
                            
                            changes=await self.dataset.ingest({ "mode" : { device: {'active':False }}})
                            self.saveJSON('/opt/beta/config/modes.json',self.modes)
                        self.log.info('Changes: %s' % changes)
                        return changes
                        
                
                if controller=="LogicController":
                    if command=='Alert':
                        self.log.info('Sending Alert: %s' % payload['message'])
                        await self.runAlert(payload['message'])
                        return []
                    if command=='Delay':
                        self.log.info('Delaying for %s seconds' % payload['duration'])
                        await asyncio.sleep(int(payload['duration']))
                        return []
                    if command=='Capture':
                        await self.captureDeviceState(payload['device'])
                        return []
                    if command=='Reset':
                        await self.resetCapturedDeviceState(payload['device'])
                        return []
                        
                if controller=="SceneController":
                    if command=="Activate":
                        if device in self.automations:
                            await self.runActivityWait(device)
                            # This should return the scene started ack
                            return []
                        elif device in self.scenes:
                            await self.runScene(device)
                            # This should return the scene started ack
                            return []
                            
                self.log.info('Could not find scene or activity: %s' % device)
                return []
                
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
                #self.log.info('Itempath / Detail: %s %s' % (itempath, detail))
                if itempath.startswith('/mode'):
                    controllerlist["PowerController"]=["powerState"]

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
                    return datetime.datetime.now()

            except:
                self.log.error('Error converting virtual controller property: %s %s' % (controllerProp, nativeObj), exc_info=True)
                return False

        def buildTriggerList(self):
            
            triggerlist={}
            try:
                for automation in self.automations:
                    if 'triggers' in self.automations[automation]:
                        for trigger in self.automations[automation]['triggers']:
                            trigname="%s.%s.%s=%s" % (trigger['deviceName'], trigger['controller'], trigger['propertyName'], trigger['value'])
                            if trigname not in triggerlist:
                                triggerlist[trigname]=[]
                            triggerlist[trigname].append({ 'name':automation, 'type':'automation' })
                            
                self.log.info('Triggers: %s' % len(triggerlist))
            except:
                self.log.error('Error calculating trigger shorthand:', exc_info=True)
            
            return triggerlist

        async def runEvents(self, events, change, trigger=''):
        
            try:
                actions=[]
                for event in events:
                    self.log.info('.. Triggered Event: %s' % events)
                    if event['type']=='event':
                        action=self.events[event['name']]['action']
                    elif event['type']=='automation':
                        action={"controller": "SceneController", "command":"Activate", "endpointId":"logic:activity:"+event['name']}
                    
                    if "value" in action:
                        aval=action['value']
                    else:
                        action['value']=''
                        
                    actions.append(action)
                    
                allacts = await asyncio.gather(*[self.sendAlexaCommand(action['command'], action['controller'], action['endpointId'], action['value'], trigger=change) for action in actions ])
                self.log.info('.. Trigger %s result: %s' % (change, allacts))
                return allacts
            except:
                self.log.error('Error executing event reactions', exc_info=True)
                            
       
        async def virtualChangeHandler(self, deviceName, change):
            
            try:
                change['deviceName']=deviceName
                #self.log.info('Change detected for %s: %s' % (deviceName, change))
                trigname="%s.%s.%s=%s" % (deviceName, change['namespace'].split('.')[1], change['name'], change['value'])
                if trigname in self.eventTriggers:
                    self.log.info('!+ This is a trigger we are watching for: %s %s %s' % (trigname, deviceName, change))
                    await self.runEvents(self.eventTriggers[trigname], change, trigname)
            except:
                self.log.error('Error in virtual change handler: %s %s' % (deviceName, change), exc_info=True)

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

                if itempath=="schedule":
                    return self.schedule
                
                if itempath=="scenes":
                    return self.scenes

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

                        al[auto]={ 'lastrun': self.automations[auto]['lastrun'], 'triggerCount': len(self.automations[auto]['triggers']), 'actionCount': len(self.automations[auto]['actions']), 'conditionCount': len(self.automations[auto]['conditions']), 'endpointId':'logic:activty:%s' % auto }
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
    adapter=logicServer(port=8096, adaptername='logic', isAsync=True)
    adapter.start()
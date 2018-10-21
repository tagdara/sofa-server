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
import uuid


class logicServer(sofabase):
    
    class adapterProcess(SofaCollector.collectorAdapter):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.dataset.nativeDevices['scene']={}
            self.dataset.nativeDevices['activity']={}
            self.dataset.nativeDevices['logic']={}

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

        async def saveAutomation(self, name,data):
            
            try:
                data=json.loads(data)
                if name not in self.automations:
                    self.automations[name]={"lastrun": "never", "actions": []}
                
                self.automations[name]['actions']=data
                self.saveJSON('/opt/beta/config/automations.json',self.automations)
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


        def loadJSON(self, configname):
        
            try:
                with open('/opt/beta/config/%s.json' % configname,'r') as jsonfile:
                    return json.loads(jsonfile.read())
            except:
                self.log.error('Error loading pattern: %s' % jsonfilename,exc_info=True)
                return {}

        async def saveSchedule(self, name, data):
            
            try:
                if type(data)==str:
                    data=json.loads(data)
                
                
                self.log.info('Saving: %s %s' % (name, data))
                if name not in self.schedule:
                    self.log.info('not in sched')
                    self.schedule[name]={"lastrun": "never", "enabled": True}
                else:
                    self.schedule[name]['lastrun']=data['lastrun']
                    self.schedule[name]['enabled']=data['enabled']
                self.schedule[name]['start']=data['start']
                self.schedule[name]['interval']=data['interval']
                self.schedule[name]['intervalunit']=data['intervalunit']
                self.schedule[name]['action']=data['action']

                self.saveJSON('/opt/beta/config/schedule.json',self.schedule)
                return True
            except:
                self.log.error('Error saving schedule: %s %s' % (name, data), exc_info=True)
                return False

                
        def saveJSON(self, jsonfilename, data):
        
            try:
                jsonfile = open(jsonfilename, 'wt')
                json.dump(data, jsonfile, ensure_ascii=False, default=self.jsonDateHandler)
                jsonfile.close()
            except:
                self.log.error('Error saving json to %s' % jsonfilename, exc_info=True)


        async def buildLogicCommand(self):
            try:
                logicCommand={"logic": {"command": {"Delay": 0, "Alert":0}}}
                await self.dataset.ingest(logicCommand)
            except:
                self.log.error('Error adding logic commands', exc_info=True)
                
           
        async def start(self):
            self.polltime=1
            self.log.info('.. Starting Logic Manager')
            try:
                self.mailconfig=self.loadJSON('mail')
                self.mailsender=mailSender(self.log, self.mailconfig)
                self.areas=self.loadJSON('areamap')
                self.automations=self.loadJSON('automations')
                self.scenes=self.loadJSON('scenemap')
                self.regions=self.loadJSON('regions')
                self.schedule=self.loadJSON('schedule')
                self.events=self.loadJSON('events')
                self.users=self.loadJSON('users')
                self.log.info('self.users: %s' % self.users)
                self.eventTriggers=self.buildTriggerList(self.events)
                await self.buildLogicCommand()
                
                for auto in self.automations:
                    await self.dataset.ingest({"activity": { auto : self.automations[auto] }})
                    
                for area in self.scenes:
                    for scene in self.scenes[area]['scenes']:
                        await self.dataset.ingest({"scene": { "%s %s" % (area, scene) : self.scenes[area]['scenes'][scene] }})
                
                await self.pollSchedule()
                
            except:
                self.log.error('Error loading cached devices', exc_info=True)
                
        async def pollSchedule(self):
            
            while True:
                try:
                    #self.log.info("Polling schedule data")
                    await self.checkScheduledItems()
                    await asyncio.sleep(self.polltime)
                except:
                    self.log.error('Error polling schedule', exc_info=True)
                

        async def checkScheduledItems(self):
        
            try:
        
                intervalConversion={'seconds':1, 'minutes':60, 'hours':3600, 'days':86400}
                now = datetime.datetime.now()
            
                for item in self.schedule:
                    if self.schedule[item]['enabled']==True:
                        if now>=datetime.datetime.strptime(self.schedule[item]['start'], '%Y-%m-%dT%H:%M:%S.%fZ'):
                            #self.log.info('After Launch Time: %s' % self.schedule[item]['start'])
                            intervalsec=int(self.schedule[item]['interval'])*intervalConversion[self.schedule[item]['intervalunit']]
                            if self.schedule[item]['lastrun']!='never':
                                #self.log.info('Using lastrun: %s' % self.schedule[item]['lastrun'])
                                delta = now-datetime.datetime.strptime(self.schedule[item]['lastrun'], '%Y-%m-%dT%H:%M:%S.%fZ')
                            else:
                                #self.log.info('Using start: %s instead of %s' % (self.schedule[item]['start'],self.schedule[item]['lastrun']))
                                delta = now-datetime.datetime.strptime(self.schedule[item]['start'], '%Y-%m-%dT%H:%M:%S.%fZ')
                            
                            #self.log.info('Delta vs intervalsec: %s %s' % (delta.seconds, intervalsec))
                            if delta.seconds>intervalsec or self.schedule[item]['lastrun']=='never':
                                self.log.info('Event to be triggered on schedule: %s %s' % (item, self.schedule[item]))
                                action=self.schedule[item]['action']
                                await self.sendAlexaCommand(action['command'], action['controller'], action['endpointId'], action['value'])
                                self.schedule[item]['lastrun']=now.isoformat()+"Z"
                                await self.saveSchedule(item, self.schedule[item])
            
            except:
                self.log.error('Error checking schedules', exc_info=True)



        # Adapter Overlays that will be called from dataset
        def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="activity":
                    return self.addSimpleActivity(path.split("/")[2])
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

        async def sendAlexaCommand(self, command, controller, endpointId, payloadvalue=None):
            
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

                header={"name": command, "namespace":"Alexa." + controller, "payloadVersion":"3", "messageId": str(uuid.uuid1()), "correlationToken": str(uuid.uuid1())}
                endpoint={"endpointId": endpointId, "cookie": {}, "scope":{ "type":"BearerToken", "token":"access-token-from-skill" }}
                data={"directive": {"header": header, "endpoint": endpoint, "payload": payload }}
                
                changereport=await self.dataset.requestAlexaStateChange(data)
                return changereport
            except:
                self.log.error('Error executing Alexa Command', exc_info=True)
                return {}

        async def runActivity(self, activityName ):
        
            try:
                activity=self.automations[activityName]['actions']
                allacts = asyncio.gather(*[self.sendAlexaCommand(action['command'], action['controller'], action['endpointId'], action['value']) for action in activity ])
                self.log.info('activity %s result: %s' % (activityName, allacts))   
            except:
                self.log.error('Error executing activity', exc_info=True)

        async def runScene(self, area, sceneName):
        
            try:
                scene=self.scenes[area]['scenes'][sceneName]
                acts=[]
                
                for light in scene:
                    if light in self.areas[area]['lights']:
                        endpointId=self.areas[area]['lights'][light]['endpointId']
                        if int(scene[light]['set'])==0:
                            acts.append({'command':'TurnOff', 'controller':'PowerController', 'endpointId':endpointId, 'value': None})
                        else:
                            acts.append({'command':'SetBrightness', 'controller':'BrightnessController', 'endpointId':endpointId, 'value': int(scene[light]['set']) } )
                    else:
                        self.log.info('Scene commands without an endpoint ID are not supported: %s %s' % (light, self.areas[area]['lights']))
                        
                allacts = await asyncio.gather(*[self.sendAlexaCommand(action['command'], action['controller'], action['endpointId'], action['value']) for action in acts ])
                self.log.info('scene %s result: %s' % (sceneName, allacts))    
            except:
                self.log.error('Error executing Scene', exc_info=True)


        async def runAlert(self, message, image=None):
            
            try:
                for user in self.users:
                    if self.users[user]['alerts']:
                        self.mailsender.sendmail(self.users[user]['email'], '', message+' @'+datetime.datetime.now().strftime("%l:%M.%S%P")[:-1], image)
                        asyncio.sleep(.5)
            except:
                self.log.error('Error sending alert', exc_info=True)
                        

        async def stateChange(self, device, controller, command, payload):
    
            try:
                self.log.info('Statechange: %s %s %s %s' % (device, controller, command, payload))
                
                if controller=="LogicController":
                    if command=='Alert':
                        self.log.info('Sending Alert: %s' % payload['message'])
                        await self.runAlert(payload['message'])
                        return []
                    if command=='Delay':
                        asyncio.sleep(payload['duration'])
                        return []
                        
                if controller=="SceneController":
                    if command=="Activate":
                        # This is heavy handed but it will make sure the current data is loaded
                        # Until I can implement saving through this adapter
                        self.automations=self.loadJSON('automations')
                        self.scenes=self.loadJSON('scenemap')

                        if device in self.automations:
                            await self.runActivity(device)
                            # This should return the scene ack
                            return []
                        else:
                            for area in self.scenes:
                                for scene in self.scenes[area]['scenes']:
                                    if ('%s %s' % (area,scene))==device:
                                        await self.runScene(area,scene)
                                        # This should return the scene ack
                                        return []
                            
                self.log.info('Could not find scene or activity: %s' % device)
                return []
                
            except:
                self.log.error('Error applying state change', exc_info=True)
                return []

        def virtualControllers(self, itempath):

            try:
                return {}

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)


        def buildTriggerList(self, events):
            
            triggerlist={}
            try:
                for event in events:
                    if 'triggers' in events[event]:
                        for trigger in events[event]['triggers']:
                            trigname="%s.%s.%s=%s" % (trigger['deviceName'], trigger['controller'], trigger['name'], trigger['value'])
                            if trigname not in triggerlist:
                                triggerlist[trigname]=[]
                            triggerlist[trigname].append(event)
                            
                self.log.info('Triggerlist: %s' % triggerlist)
            except:
                self.log.error('Error calculating trigger shorthand:', exc_info=True)
            
            return triggerlist
                            
        async def runEvents(self, events):
            
            try:
                for event in events:
                    action=self.events[event]['action']
                    self.log.info('Running event %s action: %s' % (event, action))
                    await self.sendAlexaCommand(action['command'], action['controller'], action['endpointId'], action['value'])
            except:
                self.log.error('Error running events: %s' % events, exc_info=True)

       
        async def virtualChangeHandler(self, deviceName, change):
            
            try:
                #self.log.info('Change detected for %s: %s' % (deviceName, change))
                trigname="%s.%s.%s=%s" % (deviceName, change['namespace'].split('.')[1], change['name'], change['value'])
                if trigname in self.eventTriggers:
                    self.log.info('!+ This is a trigger we are watching for: %s %s %s' % (trigname, deviceName, change))
                    await self.runEvents(self.eventTriggers[trigname])
            except:
                self.log.error('Error in virtual change handler: %s %s' % (deviceName, change), exc_info=True)

        async def virtualList(self, itempath, query={}):

            try:
                if itempath=="automations":
                    return self.automations

                if itempath=="schedule":
                    return self.schedule

                    
                if itempath=="automationlist":
                    al={}
                    for auto in self.automations:
                        al[auto]={ 'lastrun': self.automations[auto]['lastrun'], 'count': len(self.automations[auto]['actions']), 'endpointId':'logic:activty:%s' % auto }
                    return al

                if itempath=="arealist":
                    al={}
                    for area in self.areas:
                        al[area]={ 'lights': self.areas[area]['lights'] }
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
                            return self.regions[ip[1]]['rooms']
                    if ip[0]=='area':
                        if ip[1] in self.areas:
                            return self.areas[ip[1]]['lights']
                    if ip[0]=='areascenes':
                        if ip[1] in self.scenes:
                            result=self.scenes[ip[1]] 
                        else:
                            result={}

                        if ip[1] in self.areas:
                            result['lights']=self.areas[ip[1]]['lights']
                        return result
                    
                return {}

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)



        def virtualControllerProperty(self, nativeObj, controllerProp):
        
            # Scenes have no properties
            return None

        

if __name__ == '__main__':
    adapter=logicServer(port=8096, adaptername='logic', isAsync=True)
    adapter.start()
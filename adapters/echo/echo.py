#!/usr/bin/python3
import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

from sofabase import sofabase
from sofabase import adapterbase
import devices
#import definitions

import asyncio
import datetime

from alexasupport import AlexaClient, AlexaAPI, AlexaLogin, AlexaDeviceUpdater

from datetime import timedelta
import os

class echo(sofabase):
    
    class adapterProcess(adapterbase):
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.dataset.nativeDevices['devices']={}
            self.data={ "clients": {} }
            self.log=log
            self.notify=notify
            self.polltime=10
            self.captcha_time=None
            self.captcha_needed=False
            self.captcha=None
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            
        async def start(self):
            self.log.info('.. Starting echo')
            self.config=self.dataset.config
            self.login = AlexaLogin(self.config['url'], self.config['email'], self.config['password'], self.config['path'], log=self.log)
            #result=login.login()  
            self.log.info('Result: %s' % self.login.status)
            await self.waitforcaptcha()
    
            if 'login_successful' in self.login.status and self.login.status['login_successful']:
                self.alexa_devices=AlexaDeviceUpdater(self.config, self.data, self.login, self.log)
                self.alexa_devices.cookies=self.login.cookies
                await self.pollAlexa()
                
        async def waitforcaptcha(self):
            try:
                if 'captcha_required' in self.login.status and self.login.status['captcha_required']:
                    self.captcha_needed=True
                
                while self.captcha_needed:
                    if self.captcha_time==None or (datetime.datetime.now()-self.captcha_time)>datetime.timedelta(seconds=300):
                        self.captcha_time=datetime.datetime.now()
                        self.login.captchaDownload(self.login.status['captcha_image_url'])
                    
                    if self.captcha:
                        result=self.login.login(captcha=self.captcha)
                        self.captcha=None
                        self.log.info('Result: %s %s' % (result, self.login.status))
                        self.captcha_needed=False
                        self.captcha_time=None
                        
                    await asyncio.sleep(.1)
            except:
                self.log.error('Error waiting for the captcha', exc_info=True)

        async def pollAlexa(self):
            while True:
                try:
                    #self.log.info("Polling alexa data")
                    devices=self.alexa_devices.update()
                    #self.log.info('Devices: %s' % self.alexa_devices.alexa_clients)
                    changes=await self.dataset.ingest({'devices':devices})
                    if changes:
                        self.log.info('Changes: %s' % changes)
                except:
                    self.log.error('Error fetching alexa Data', exc_info=True)
                await asyncio.sleep(self.polltime)


        def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="devices":
                    return self.addSmartPlayer(path.split("/")[2])
            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False


        async def addSmartPlayer(self, deviceid):
            
            nativeObject=self.dataset.nativeDevices['devices'][deviceid]
            if nativeObject['accountName'] not in self.dataset.localDevices:
                if nativeObject['deviceFamily']=='ECHO':
                    return self.dataset.addDevice(nativeObject['accountName'], devices.soundSystem('echo/devices/%s' % deviceid, nativeObject['accountName']))
            
            return False


        def virtualControllers(self, itempath):

            try:
                nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(itempath))
                self.log.info('Checking object for controllers: %s' % nativeObject)
                self.log.info('Checking object path: %s' % itempath)
                try:
                    detail=itempath.split("/",3)[3]
                except:
                    detail=""

                controllerlist={}
                if "session" in nativeObject:

                    if detail=="session/playerSource":
                        controllerlist["InputController"]=["input"]
                        controllerlist["MusicController"]=["linked"]
                        
                    if detail=="session/state":
                        controllerlist["MusicController"]=["playbackState"]
                    if detail=="session/infoText/subText1":
                        controllerlist["MusicController"]=["artist"]
                    if detail=="session/infoText/title":
                        controllerlist["MusicController"]=["title"]
                    if detail=="session/infoText/subText2":  
                        controllerlist["MusicController"]=["album"]
                    if detail=="session/mainArt/url":
                        controllerlist["MusicController"]=["art"]
                    if detail=="session/mediaId":
                        controllerlist["MusicController"]=["url"]

                    if detail=="session/volume/volume":
                        controllerlist["SpeakerController"]=["volume"]
                    if detail=="session/volume/muted":
                        controllerlist["SpeakerController"]=["muted"]

                    if detail=="":    
                        controllerlist["MusicController"]=["artist", "title", "album", "url", "art", "linked", "playbackState"]
                        controllerlist["SpeakerController"]=["volume","muted"]
                        controllerlist["InputController"]=["input"]
                        
                return controllerlist
            except:
                self.log.error('Error getting virtual controller types for %s' % nativeObj, exc_info=True)


        def virtualControllerProperty(self, nativeObj, controllerProp):
            
            if controllerProp=='volume':
                try:
                    if 'volume' in nativeObj['session']:
                        if nativeObj['session']['volume']:
                            return int(nativeObj['session']['volume']['volume'])
                    return 0
                except:
                    self.log.error('Error checking volume status', exc_info=True)

            elif controllerProp=='muted':
                if 'volume' in nativeObj['session']:
                    if nativeObj['session']['volume']:
                        return nativeObj['session']['volume']['muted']
                return False
            
            elif controllerProp=='playbackState':
                try:
                    if 'state' in nativeObj['session']:
                        return nativeObj['session']['state']
                    return 'STOPPED'
                except:
                    return 'STOPPED'

            elif controllerProp=='input':
                try:
                    return ''
                except:
                    self.log.error('Error checking input status', exc_info=True)
                    return ''
                    
            elif controllerProp=='artist':
                
                try:
                    if 'infoText' in nativeObj['session']:
                        return nativeObj['session']['infoText']['subText1']
                    return ''
                except:
                    self.log.debug('Error checking artist for %s' % nativeObj['accountName'])
                    return ""

            elif controllerProp=='title':
                try:                    
                    if 'infoText' in nativeObj['session']:
                        return nativeObj['session']['infoText']['title']
                    return ''
                except:
                    self.log.debug('Error checking title')
                    return ""

            elif controllerProp=='album':
                try:
                    if 'infoText' in nativeObj['session']:
                        return nativeObj['session']['infoText']['subText2']
                    return ''
                except:
                    self.log.debug('Error checking album')
                    return ""

            elif controllerProp=='art':
                try:
                    if 'mainArt' in nativeObj['session']:
                        if nativeObj['session']['mainArt']:
                            return '/static/albumart-%s.jpg?%s' % (nativeObj['serialNumber'], nativeObj['session']['infoText']['subText2'])
                        #return nativeObj['session']['mainArt']['url']
                    return ''
                except:
                    self.log.info('Error checking art', exc_info=True)
                    return ""

            elif controllerProp=='url':
                try:
                    if 'mediaId' in nativeObj['session']:
                        return nativeObj['sesion']['mediaId']
                    return ''
                except:
                    self.log.debug('Error checking url')
                    return ""
                    
            elif controllerProp=='linked':
                try:
                    return []
                except:
                    self.log.debug('Error getting linked players')
                    return []
                

            else:
                self.log.info('Unknown controller property mapping: %s' % controllerProp)
                return {}
                
                
        async def processDirective(self, endpointId, controller, command, payload, correlationToken='', cookie={}):
    
            try:
                self.log.info('Directive for %s: %s %s' % (endpointId, controller, command))
                dev=self.dataset.getDeviceByEndpointId(endpointId)
                playerid=endpointId.split(':')[2]
                player=self.alexa_devices.alexa_clients[playerid]
                self.log.info('Player: %s' % player)
                if controller=="MusicController":
                    if command=='Play':
                        player.media_play()
                    elif command=='Pause':
                        player.media_pause()
                    elif command=='Stop':
                        player.media_pause()
                    elif command=='Next':
                        player.media_next_track()
                    elif command=='Previous':
                        player.media_previous_track()
                    else:
                        self.log.warn('Requested command not available for %s: %s' % (playerid, command))
                        response=await self.dataset.generateResponse(endpointId, correlationToken)
                        return response

                    response=await self.dataset.generateResponse(endpointId, correlationToken)
                    return response

                return {}

            except:
                self.log.error('Error executing state change.', exc_info=True)

        async def virtualList(self, itempath, query={}):

            try:
                self.log.info('List: %s' % itempath)
                items=itempath.split('/')
                if items[0]=="captcha":
                    self.log.info('Setting captcha reply to %s' % items[1])
                    self.captcha=items[1]
                return {}

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)

                
if __name__ == '__main__':
    adapter=echo(name='echo')
    adapter.start()
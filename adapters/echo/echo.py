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
            if 'captcha_required' in self.login.status and self.login.status['captcha_required']:
                self.login.captchaDownload(self.login.status['captcha_image_url'])
                captcha=input('Enter the captcha:')
                result=self.login.login(captcha=captcha)
                self.log.info('Result: %s %s' % (result, self.login.status))
    
            if 'login_successful' in self.login.status and self.login.status['login_successful']:
                self.alexa_devices=AlexaDeviceUpdater(self.config, self.data, self.login, self.log)
                self.alexa_devices.cookies=self.login.cookies
                await self.pollAlexa()

        async def pollAlexa(self):
            while True:
                try:
                    self.log.info("Polling alexa data")
                    devices=self.alexa_devices.update()
                    await self.dataset.ingest({'devices':devices})
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
                self.log.debug('Checking object for controllers: %s' % nativeObject)
                self.log.debug('Checking object path: %s' % itempath)
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
                    # Sonos doesn't always populate the zone_group_name field, even when a player is grouped.  It's probably just a Sonos
                    # thing, but it might be a Soco thing.  Anyway, here's Wonderwall.
                    #if nativeObj['ZoneGroupTopology']['zone_group_name']==None:
                    return nativeObj['accountName']

                    # Sometimes it's right tho   
                    # But we're still not using it as it's kinda arbitrary
                    #return nativeObj['ZoneGroupTopology']['zone_group_name']
                except:
                    self.log.error('Error checking input status', exc_info=True)
                    return nativeObj['accountName']
                    
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


                
if __name__ == '__main__':
    adapter=echo(name='echo')
    adapter.start()
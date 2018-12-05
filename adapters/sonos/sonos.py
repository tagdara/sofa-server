#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

from sofabase import sofabase
from sofabase import adapterbase
import devices


import requests
import math
import random
from collections import namedtuple
from collections import defaultdict
import xml.etree.ElementTree as et
import time
import json
import asyncio
import aiohttp
import xmltodict

import base64
import logging

import soco
import soco.music_library
from soco.events import event_listener
from operator import itemgetter


class sonos(sofabase):

    class adapterProcess(adapterbase):
        
        def setSocoLoggers(self, level):
            
            for lg in logging.Logger.manager.loggerDict:
                if lg.startswith('soco'):
                    logging.getLogger(lg).setLevel(level)
              
        
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.log=log
            self.setSocoLoggers(logging.WARN)
            self.notify=notify
            self.polltime=.1
            self.subscriptions=[]
            self.artcache={}
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            self.readLightLogoImage()
            self.readDarkLogoImage()
                
        def readLightLogoImage(self):
            sonoslogofile = open("/opt/beta/sonos/sonoslogo.png", "rb")
            self.sonoslogo = sonoslogofile.read()
            self.lightlogo = self.sonoslogo

        def readDarkLogoImage(self):
            try:
                sonoslogofile = open("/opt/beta/sonos/sonosdark.png", "rb")
                self.darklogo = sonoslogofile.read()
            except:
                self.log.error('Error getting dark logo', exc_info=True)
               
                
        async def start(self):
            try:
                self.log.info('.. Starting Sonos')
                self.players=await self.sonosDiscovery()
                for player in self.players:
                    for subService in ['avTransport','deviceProperties','renderingControl','zoneGroupTopology']:
                        newsub=self.subscribeSonos(player,subService)
                        self.log.info('++ sonos state subscription: %s/%s' % (player.player_name, newsub.service.service_type))
                        self.subscriptions.append(newsub)
                self.sonosGetSonosFavorites(self.players[0])
                await self.pollFake()
            except:
                self.log.error('Error starting sonos service',exc_info=True)
            

        def sonosQuery(self, resmd="", uri="", player="192.168.0.94"):
        
            parentsource="MediaRenderer/"
            source="AVTransport"
            command="SetAVTransportURI"
            resmd='<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"><item id="1006206clibrary%2fplaylists%2f56de4623-3f02-4dc8-8d62-3a580d5325eb%2f%23library_playlist" parentID="10082064library%2fplaylists%2f%23library_playlists" restricted="true"><dc:title>A fantastic raygun</dc:title><upnp:class>object.container.playlistContainer</upnp:class><desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">SA_RINCON51463_X_#Svc51463-0-Token</desc></item></DIDL-Lite>'
            uri="x-rincon-cpcontainer:1006206clibrary%2fplaylists%2f56de4623-3f02-4dc8-8d62-3a580d5325eb%2f%23library_playlist"
            payload="<InstanceID>0</InstanceID><CurrentURI>"+uri+"</CurrentURI><CurrentURIMetaData>"+resmd+"</CurrentURIMetaData>"
            port=1400
        
            url="http://"+player+":"+str(port)+"/"+parentsource+source+"/Control"
            template='<s:Envelope s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><u:'+command+' xmlns:u="urn:schemas-upnp-org:service:'+source+':1">'+payload+'</u:'+command+'></s:Body></s:Envelope>'
            headers={'SOAPACTION': 'urn:schemas-upnp-org:service:'+source+':1#'+command}
            r = requests.post(url, data=template, headers=headers)
            namespaces = {
                'http://schemas.xmlsoap.org/soap/envelope/': None
            }
            response = dict(xmltodict.parse(r.text, namespaces=namespaces))
            self.log.info('.. sonos raw query '+command+': '+str(response))
            return response

        
        async def sonosDiscovery(self):
        
            try:
                discoverlist=list(soco.discover())
                if discoverlist==None:
                    self.log.error('Discover: No sonos devices detected')
                    return None
                for player in discoverlist:
                    spinfo=player.get_speaker_info()
                    await self.dataset.ingest({"player": { spinfo["uid"]: { "speaker": spinfo, "name":player.player_name, "ip_address":player.ip_address }}})
                return discoverlist
            except:
                self.log.error('Error discovering Sonos devices', exc_info=True)

        async def getGroupUUIDs(self, playerId):
        
            try:
                linkedPlayers=[]
                for player in self.players:
                    if player.player_name==playerId or player.uid==playerId:
                        for linked in player.group:
                            if linked.is_visible:
                                linkedPlayers.append(linked.uid)
                if linkedPlayers:
                    return ','.join(linkedPlayers)
                else:
                    return ''
            except:
                self.log.error('Error getting linked players', exc_info=True)


        async def getGroupName(self, playerId):
        
            try:
                for player in self.players:
                    if player.player_name==playerId or player.uid==playerId:
                        return player.group.short_label       
                return ''
            except:
                self.log.error('Error getting group name', exc_info=True)

            
        async def pollFake(self):
            
            while True:
                try:
                    for device in self.subscriptions:
                        if device.is_subscribed:
                            if not device.events.empty():
                                update=self.unpackEvent(device.events.get())
                                #self.log.info('Ingesting change: %s %s' % (device.service.soco.uid, device.service.service_id))
                                if device.service.service_id=='ZoneGroupTopology' and update:
                                    #self.log.info('Replacing  %s ZoneGroupTopology with: %s' % (device.service.soco.uid, update))
                                    if 'zone_player_uui_ds_in_group' in update:
                                        if update['zone_player_uui_ds_in_group']==None:
                                            # This is such garbage but the first zone group status always sets this to None
                                            update['zone_player_uui_ds_in_group']=await self.getGroupUUIDs(device.service.soco.uid)
                                            # And we might as well fix the fucking label while we're at it since that gets skipped too
                                            update['zone_group_name']=await self.getGroupName(device.service.soco.uid)
                                    await self.dataset.ingest(update, overwriteLevel='player/%s/%s' % (device.service.soco.uid, device.service.service_id) )
                                else:
                                    #self.log.info('.> Update from %s:%s - %s' % (device.service.soco.uid, device.service.service_id, update ))
                                    await self.dataset.ingest({'player': { device.service.soco.uid : { device.service.service_id: update }}})
                        else:
                            self.log.info("Subscription ended: %s" % device.__dict__)
                    #time.sleep(self.polltime)
                    await asyncio.sleep(self.polltime)
                except:
                    self.log.error('Error polling', exc_info=True)
                    
        async def updateLinkedPlayers(self,nativeObj):
            
            try:
                linkedPlayers=self.getLinkedPlayers(nativeObj)
                self.log.debug('Linked Players: %s' % linkedPlayers)
                for player in linkedPlayers:
                    await self.dataset.updateDeviceState('/player/%s' % linkedPlayers[player])
            except:
                self.log.error('Problem updating linked players',exc_info=True)
                return []



        def getLinkedPlayers(self, nativeObj):
            
            try:
                linkedPlayers={}
                if 'ZoneGroupTopology' not in nativeObj:
                    return []
                if 'zone_group_state' not in nativeObj['ZoneGroupTopology']:
                    self.log.error('!! Cant get linked players: zone_group_state not in %s' % nativeObj['ZoneGroupTopology'])
                    return []
                for group in nativeObj['ZoneGroupTopology']['zone_group_state']['ZoneGroups']['ZoneGroup']:
                    if group['@Coordinator']==nativeObj['speaker']['uid']:
                        if type(group['ZoneGroupMember'])!=list:
                            group['ZoneGroupMember']=[group['ZoneGroupMember']]
                        for member in group['ZoneGroupMember']:
                            if member['@UUID']!=group['@Coordinator'] and '@Invisible' not in member:
                                linkedPlayers[member['@ZoneName']]=member['@UUID']
                                
                return linkedPlayers

            except:
                self.log.error('Problem getting linked players',exc_info=True)
                return []



        def subscribeSonos(self,zone,sonosservice):
            
            try:
                subscription=getattr(zone, sonosservice) 
                #self.log.info('Subscribed to '+zone.player_name+'.'+sonosservice+' for '+str(xsub.timeout))
                return subscription.subscribe(requested_timeout=180, auto_renew=True)
            except:
                self.log.error('Error configuring subscription', exc_info=True)


        def unpackEvent(self, event):
            
            try:
                eventVars={}
                for item in event.variables:
                    eventVars[item]=self.didlunpack(event.variables[item])
                    if str(eventVars[item])[:1]=="<":
                        #self.log.info('Possible XML: %s' % str(eventVars[item]) )
                        eventVars[item]=self.etree_to_dict(et.fromstring(str(eventVars[item])))
                return eventVars
                
                
            except:
                self.log.error('Error unpacking event', exc_info=True)


        def sonosGetSonosFavorites(self,player):

            #{'type': 'instantPlay', 'title': 'A fantastic raygun', 'description': 'Amazon Music Playlist', 'parent_id': 'FV:2', 'item_id': 'FV:2/27', 'album_art_uri': 'https://s3.amazonaws.com/redbird-icons/blue_icon_playlists-80x80.png', 'desc': None, 'favorite_nr': '0', 'resource_meta_data': '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"><item id="1006206clibrary%2fplaylists%2f56de4623-3f02-4dc8-8d62-3a580d5325eb%2f%23library_playlist" parentID="10082064library%2fplaylists%2f%23library_playlists" restricted="true"><dc:title>A fantastic raygun</dc:title><upnp:class>object.container.playlistContainer</upnp:class><desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">SA_RINCON51463_X_#Svc51463-0-Token</desc></item></DIDL-Lite>', 'resources': [<DidlResource 'x-rincon-cpcontainer:1006206clibrary%2fplaylists%2f56de4623-3f02-4dc8-8d62-3a580d5325eb%2f%23library_playlist' at 0x748733f0>], 'restricted': False}

        
            try:
                ml=soco.music_library.MusicLibrary()
                favorites=[]
                sonosfavorites=ml.get_sonos_favorites()
                #sonosfavorites=player.get_sonos_favorites()
                # this does not currently get the album art
                #self.log.info('fav: %s' % sonosfavorites)
                for fav in sonosfavorites:
                    newfav=fav.__dict__
                    try:
                        #self.log.info('res: %s' % fav.resources[0].uri)
                        newfav['uri']=fav.resources[0].uri
                        newfav['resources']=fav.resources[0].__dict__
                    except:
                        self.log.error('Error deciphering resources', exc_info=True)
                        newfav['resources']={}
                        newfav['uri']=''
                    favorites.append(newfav)
                favorites=sorted(favorites, key=itemgetter('title')) 
                #self.log.info('fav: %s' % favorites)
                
                self.dataset.listIngest('favorites',favorites)
                self.sonosQuery()
            except:
                self.log.error('Error getting sonos favorites', exc_info=True)


        def etree_to_dict(self, t):
        
            d = {t.tag: {} if t.attrib else None}
            children = list(t)
            if children:
                dd = defaultdict(list)
                for dc in map(self.etree_to_dict, children):
                    for k, v in dc.items():
                        dd[k].append(v)
                d = {t.tag: {k: v[0] if len(v) == 1 else v for k, v in dd.items()}}
            if t.attrib:
                d[t.tag].update(('@' + k, v) for k, v in t.attrib.items())
            if t.text:
                text = t.text.strip()
                if children or t.attrib:
                    if text:
                        d[t.tag]['#text'] = text
                else:
                    d[t.tag] = text
            return d


        def didlunpack(self,didl):
        
            try:
                if str(type(didl)).lower().find('didl')>-1:
                    didl=didl.to_dict() #This should work according to the docs but does not for DidlResource
                    #didl=didl.__dict__
                    for item in didl:
                        #self.log.info('Event var: %s (%s) %s' % (item, type(didl[item]).__name__, didl[item]))
                        if type(didl[item]).__name__ in ['MSTrack']:
                            didl[item]=didl[item].__dict__
                            if 'resources' in didl[item]:
                                didl[item]['resources']=self.didlunpack(didl[item]['resources'])
                        else:
                            didl[item]=self.didlunpack(didl[item])

                    #self.log.info('Unpacked DIDL:'+str(didl))
                elif type(didl)==list:
                    for i, item in enumerate(didl):
                        didl[i]=self.didlunpack(item)
                elif type(didl)==dict:
                    for item in didl:
                        #self.log.info('Event var: %s (%s) %s' % (item, type(didl[item]).__name__, didl[item]))
                        if type(didl[item]).__name__ in ['MSTrack']:
                            didl[item]=didl[item].__dict__
                            if 'resources' in didl[item]:
                                didl[item]['resources']=self.didlunpack(didl[item]['resources'])
                        else:
                            didl[item]=self.didlunpack(didl[item])

                        #didl[item]=self.didlunpack(didl[item])
                elif type(didl).__name__ in ['MSTrack']:
                    didl=didl.__dict__
                    if 'metadata' in didl:
                        didl={**didl, **didl['metadata']}
                    if 'resources' in didl:
                        didl['resources']=self.didlunpack(didl['resources'])

        
                return didl    
            except:
                self.log.error('Error unpacking didl: %s' % didl, exc_info=True)
                


        async def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="player":
                    return self.addSoundSystem(path.split("/")[2])

            except:
                self.log.error('Error defining smart device', exc_info=True)
                return None


        def addSoundSystem(self, deviceid):
            
            nativeObject=self.dataset.nativeDevices['player'][deviceid]
            if 'name' not in nativeObject:
                self.log.error('No name in %s %s' % (deviceid, nativeObject))
                return None
                

            if nativeObject['name'] not in self.dataset.localDevices:
                if 'RenderingControl' in nativeObject:
                    if 'ZoneGroupTopology' in nativeObject:
                        return self.dataset.addDevice(nativeObject['name'], devices.soundSystem('sonos/player/%s' % deviceid, nativeObject['name']))
            
            return None


        #async def stateChange(self, endpointId, controller, command, payload):
        async def processDirective(self, endpointId, controller, command, payload, correlationToken='', cookie={}):
    
            try:
                device=endpointId.split(":")[2]
                for player in self.players:
                    if player.player_name==device or player.uid==device:

                        if controller=="SpeakerController":
                            if command=='SetVolume':
                                player.volume=int(payload['volume'])
                            elif command=='SetMute':
                                player.mute=payload['muted']
                                
                        elif controller=="MusicController":
                            if command=='PlayFavorite':
                                player.playFavorite(payload['favorite'])
                            elif command=='Play':
                                player.play()
                            elif command=='Pause':
                                player.pause()
                            elif command=='Stop':
                                player.stop()
                            elif command=='Skip':
                                player.next()
                            elif command=='Previous':
                                player.previous()
                                
                        elif controller=="InputController":
                            if command=='SelectInput':
                                if payload['input']=='':
                                    player.unjoin()
                                else:
                                    for otherplayer in self.players:
                                        if otherplayer.player_name==payload['input']:
                                            player.join(otherplayer)
                   
                        #await self.dataset.ingest({"player": { spinfo["uid"]: { "speaker": spinfo, "name":player.player_name, "ip_address":player.ip_address }}})
                        response=await self.dataset.generateResponse(endpointId, correlationToken)
                        return response

            except soco.exceptions.SoCoUPnPException:
                self.log.error('Error from Soco while trying to issue command', exc_info=True)
            except:
                self.log.error('Error executing state change.', exc_info=True)


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
                if "speaker" in nativeObject:

                    if detail=="ZoneGroupTopology/zone_player_uui_ds_in_group":
                        controllerlist["InputController"]=["input"]
                        controllerlist["MusicController"]=["linked"]
                        
                    if detail=="AVTransport/transport_state":
                        controllerlist["MusicController"]=["playbackState"]
                    if detail=="AVTransport/current_track_meta_data/creator":
                        controllerlist["MusicController"]=["artist"]
                    if detail=="AVTransport/current_track_meta_data/title":
                        controllerlist["MusicController"]=["title"]
                    if detail=="AVTransport/current_track_meta_data/album":  
                        controllerlist["MusicController"]=["album"]
                    if detail=="AVTransport/current_track_meta_data/album_art_uri":
                        controllerlist["MusicController"]=["art"]
                    if detail=="AVTransport/current_track_uri":
                        controllerlist["MusicController"]=["url"]

                    if detail=="RenderingControl/volume/Master":
                        controllerlist["SpeakerController"]=["volume"]
                    if detail=="RenderingControl/mute/Master":
                        controllerlist["SpeakerController"]=["muted"]

                    if detail=="":    
                        controllerlist["MusicController"]=["artist", "title", "album", "url", "art", "linked", "playbackState"]
                        controllerlist["SpeakerController"]=["volume","muted"]
                        controllerlist["InputController"]=["input"]
                        
                return controllerlist
            except:
                self.log.error('Error getting virtual controller types for %s' % nativeObj, exc_info=True)


        def getCoordinator(self, nativeObj):
            
            try:
                # Sonos doesn't always populate the zone_group_name field, even when a player is grouped.  It's probably just a Sonos
                # thing, but it might be a Soco thing.  Anyway, here's Wonderwall.
                if 'zone_group_state' not in nativeObj['ZoneGroupTopology']:
                    return nativeObj
                for group in nativeObj['ZoneGroupTopology']['zone_group_state']['ZoneGroups']['ZoneGroup']:
                    if group['@Coordinator']==nativeObj['speaker']['uid']:
                        return nativeObj
                    #ugh so inconsistent
                    if type(group['ZoneGroupMember'])!=list:
                        group['ZoneGroupMember']=[group['ZoneGroupMember']]
                    for member in group['ZoneGroupMember']:
                        try:
                            if member['@UUID']==nativeObj['speaker']['uid']:
                                return self.dataset.nativeDevices['player'][group['@Coordinator']]
                        except:
                            self.log.info('Bad Member: %s %s' % (nativeObj['name'], member))
                        
                # If not all of that, then lets just assume it's not grouped.
                self.log.info('Didnt find coordinator for %s: %s' % (nativeObj['name'],nativeObj['ZoneGroupTopology']))
                return nativeObj

            except:
                self.log.error('Error getting coordinator', exc_info=True)
                return nativeObj
            

        def virtualControllerProperty(self, nativeObj, controllerProp):
        
            if controllerProp=='volume':
                try:
                    return int(nativeObj['RenderingControl']['volume']['Master'])
                except:
                    self.log.error('Error checking volume status', exc_info=True)

            elif controllerProp=='muted':
                return nativeObj['RenderingControl']['mute']['Master']=="1"

            
            elif controllerProp=='playbackState':
                try:
                    if nativeObj['AVTransport']['transport_state']=='TRANSITIONING':
                        return 'PLAYING'
                    else:
                        return nativeObj['AVTransport']['transport_state']
                except:
                    return 'STOPPED'

            elif controllerProp=='input':
                try:
                    # Sonos doesn't always populate the zone_group_name field, even when a player is grouped.  It's probably just a Sonos
                    # thing, but it might be a Soco thing.  Anyway, here's Wonderwall.
                    #if nativeObj['ZoneGroupTopology']['zone_group_name']==None:
                    return self.getCoordinator(nativeObj)['name']

                    # Sometimes it's right tho   
                    # But we're still not using it as it's kinda arbitrary
                    #return nativeObj['ZoneGroupTopology']['zone_group_name']
                except:
                    self.log.error('Error checking input status', exc_info=True)
                    return nativeObj['name']
                    
            elif controllerProp=='artist':
                
                try:
                    coordinator=self.getCoordinator(nativeObj)
                    return coordinator['AVTransport']['current_track_meta_data']['creator']

                except:
                    self.log.debug('Error checking artist for %s' % nativeObj['name'])
                    return ""

            elif controllerProp=='title':
                try:                    
                    coordinator=self.getCoordinator(nativeObj)
                    return coordinator['AVTransport']['current_track_meta_data']['title']
                except:
                    self.log.debug('Error checking title')
                    return ""

            elif controllerProp=='album':
                try:
                    coordinator=self.getCoordinator(nativeObj)
                    return coordinator['AVTransport']['current_track_meta_data']['album']
                except:
                    self.log.debug('Error checking album')
                    return ""

            elif controllerProp=='art':
                try:
                    coordinator=self.getCoordinator(nativeObj)
                    return "/image/sonos/player/%s/AVTransport/current_track_meta_data/album_art_uri?%s" % (coordinator['speaker']['uid'], coordinator['AVTransport']['current_track_meta_data']['album'])
                    #return coordinator['AVTransport']['current_track_meta_data']['album_art_uri']
                except:
                    self.log.debug('Error checking art')
                    return "/image/sonos/logo"
                    #return ""

            elif controllerProp=='url':
                try:
                    coordinator=self.getCoordinator(nativeObj)
                    return coordinator['AVTransport']['enqueued_transport_uri']
                except:
                    self.log.debug('Error checking url')
                    return ""
                    
            elif controllerProp=='linked':
                try:
                    return list(self.getLinkedPlayers(nativeObj).keys())
                except:
                    self.log.debug('Error getting linked players')
                    return []
                

            else:
                self.log.info('Unknown controller property mapping: %s' % controllerProp)
                return {}


        async def virtualImage(self, path, client=None):
            
            try:

                if path=='darklogo':
                    return self.darklogo

                if path=='lightlogo':
                    return self.lightlogo

                if path=='logo':
                    return self.sonoslogo
                    
                playerObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath("/"+path))
                url=self.dataset.getObjectFromPath("/"+path)
                #self.log.info('VI: %s %s %s' % (path, url, playerObject))

                if url.find('http')==0:
                    pass
                elif url.find('/')==0:
                    url='http://'+playerObject['ip_address']+':1400'+url                    
                else:
                    url='http://'+playerObject['ip_address']+':1400/'+url
                if path in self.artcache:
                    if self.artcache[path]['url']==url:
                        return self.artcache[path]['image']

                async with aiohttp.ClientSession() as client:
                    async with client.get(url) as response:
                        result=await response.read()
                        self.artcache[path]={'url':url, 'image':result}
                        return result

            except concurrent.futures._base.CancelledError:
                self.log.error('Attempt to get art cancelled for %s' % path, exc_info=True)
                return self.sonoslogo
            except:
                self.log.error('Couldnt get art for %s' % playerObject, exc_info=True)
                #return {'name':playerObject['name'], 'id':playerObject['speaker']['uid'], 'image':""}
                return self.sonoslogo
                    
        async def virtualCategory(self, category):
            
            self.log.info('Virtual Category check: %s' % category)
            
            subset={}
            
            return subset



if __name__ == '__main__':
    adapter=sonos(port=9090, adaptername='sonos', isAsync=True)
    adapter.start()
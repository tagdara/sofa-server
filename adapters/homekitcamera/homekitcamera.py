#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))
from sofacollector import SofaCollector

from sofabase import sofabase
from sofabase import adapterbase
import devices

import math
import random
from collections import namedtuple
import requests
import json
import asyncio
import aiohttp
import logging
import pickle
import signal
import copy

import pyhap.util as util
#from pyhap.accessories.TemperatureSensor import TemperatureSensor
from pyhap.accessory import Accessory
from pyhap import camera
from pyhap.accessory_driver import AccessoryDriver

import random
import time
import datetime
import os
import functools
import concurrent.futures
import uuid


class unifi_camera(camera.Camera):

    def __init__(self, options, loop, log, cameraconfig, *args, **kwargs):
        self.log=log
        self.loop=loop

        asyncio.set_event_loop(self.loop)

        self.cameraconfig=copy.deepcopy(cameraconfig)
        
        super().__init__(options, *args, **kwargs)
        motion=self.add_preload_service('MotionSensor')
        self.char_detected = motion.configure_char('MotionDetected')

    def blip(self):
        self.log.info('Blipping motion detect')
        self.char_detected.set_value(True)
        time.sleep(.1)
        self.char_detected.set_value(False)
        self.log.info('Done blipping motion detect')  
        
    def _detected(self):
        self.char_detected.set_value(True)

    def _notdetected(self):
        self.char_detected.set_value(False)

    def get_snapshot(self, image_size):  # pylint: disable=unused-argument, no-self-use

        try:   
            future=asyncio.run_coroutine_threadsafe(self.get_unifi_snap(image_size['image-width']), loop=self.loop)
            return future.result() 
        except:
            self.log.error('Error getting snapshot', exc_info=True)
 
    async def get_unifi_snap(self, width):

        try:
            if width<640:
                width=640
            url="https://%s:%s/api/2.0/snapshot/camera/%s?force=true&width=%s&apiKey=%s" % (self.cameraconfig['nvr_address'], self.cameraconfig['nvr_snapshot_port'], self.cameraconfig['camera_id'], width, self.cameraconfig['api_key'])
            #self.log.info('%s URL: %s' % (self.cameraconfig['camera_id'],url))
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as client:
                async with client.get(url) as response:
                    result=await response.read()
                    return result  
        except:
            self.log.error('Error getting unifi snap', exc_info=True)
                    
    async def start_stream(self, session_info, stream_config):
        
        try:
            self.log.info('Starting stream %s with the following parameters: %s', session_info['id'], stream_config)
    
            stream_config.update(self.cameraconfig)
            self.log.info('stream: %s' % stream_config)
            if stream_config['v_max_bitrate']<1500: stream_config['v_max_bitrate']=1500
            cmd = self.start_stream_cmd.format(**stream_config).split()
            self.log.info('Executing start stream command: "%s"', ' '.join(cmd))
            try:
                process = await asyncio.create_subprocess_exec(*cmd,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.PIPE,
                        limit=1024)
            except Exception as e:  # pylint: disable=broad-except
                self.log.error('Failed to start streaming process because of error', exc_info=True)
                return False
    
            session_info['process'] = process
    
            self.log.info('[%s] Started stream process - PID %d',
                         session_info['id'], process.pid)
    
            return True
        except:
            self.log.error('Error starting stream', exc_info=True)

class homekitcamera(sofabase):

    class adapterProcess(SofaCollector.collectorAdapter):

        # Specify the audio and video configuration that your device can support
        # The HAP client will choose from these when negotiating a session.

        
        options = {
            "video": {
                "codec": {
                    "profiles": [
                        camera.VIDEO_CODEC_PARAM_PROFILE_ID_TYPES["BASELINE"],
                        camera.VIDEO_CODEC_PARAM_PROFILE_ID_TYPES["MAIN"],
                        camera.VIDEO_CODEC_PARAM_PROFILE_ID_TYPES["HIGH"]
                    ],
                    "levels": [
                        camera.VIDEO_CODEC_PARAM_LEVEL_TYPES['TYPE3_1'],
                        camera.VIDEO_CODEC_PARAM_LEVEL_TYPES['TYPE3_2'],
                        camera.VIDEO_CODEC_PARAM_LEVEL_TYPES['TYPE4_0'],
                    ],
                },
                "resolutions": [
                    # Width, Height, framerate
                    [320, 240, 15],  # Required for Apple Watch
                    [640, 360, 15],
                    [1024, 576, 15],
                ],
            },
            "audio": {
                "codecs": [
                    {
                        'type': 'OPUS',
                        'samplerate': 24,
                    },
                    {
                        'type': 'AAC-eld',
                        'samplerate': 16
                    }
                ],
            },
            "srtp": True,
            "address": "192.168.0.35",
            "start_stream_cmd":  (
                "ffmpeg -rtsp_transport http -re -i rtsp://{nvr_address}:{nvr_rtsp_port}/{camera_id}_{stream_id}?apiKey={api_key} "
                "-vcodec libx264 -an -pix_fmt yuv420p -r {fps} -f rawvideo -tune zerolatency -vf scale={width}x{height} "
                "-b:v {v_max_bitrate}k -bufsize {v_max_bitrate}k -payload_type 99 -ssrc {v_ssrc} -f rtp -srtp_out_suite AES_CM_128_HMAC_SHA1_80 "
                "-srtp_out_params {v_srtp_key} "
                "srtp://{address}:{v_port}?rtcpport={v_port}&localrtcpport={v_port}&pkt_size=1378"
            )
        }
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, executor=None,  **kwargs):
            self.dataset=dataset
            self.log=log
            self.notify=notify
            self.polltime=5
            self.maxaid=8
            self.executor=executor
            
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            self.addExtraLogs()


        async def start(self):
            
            try:
                self.drivers={}
                self.acc={}
                self.log.info('Starting homekit')
                #await self.dataset.ingest({'accessorymap': self.loadJSON(self.dataset.config['accessory_map'])})
                #self.log.info('Known devices: %s' % self.dataset.nativeDevices['accessorymap'])
                #self.getNewAid()
                self.accloop=asyncio.new_event_loop()
                cameraconfig=self.dataset.config['nvr_config']
                index=0
                asyncio.get_child_watcher()
                for cam in self.dataset.config['cameras'].keys():
                    self.drivers[cam] = AccessoryDriver(port=51830+index, persist_file='/opt/sofa-server/config/homekitcamera-%s.json' % cam)
                    self.log.info('Camera: %s PIN: %s' % (self.dataset.config['cameras'][cam]['name'], self.drivers[cam].state.pincode))
                    self.log.info('Options: %s' % self.options)
                    cameraconfig['camera_id']=self.dataset.config['cameras'][cam]['id']
                    self.acc[cam] = unifi_camera(self.options, self.loop, self.log, cameraconfig, self.drivers[cam], self.dataset.config['cameras'][cam]['name'])
                    self.drivers[cam].add_accessory(accessory=self.acc[cam])
                    signal.signal(signal.SIGTERM, self.drivers[cam].signal_handler)
                    self.executor.submit(self.drivers[cam].start)
                    index=index+1
 
                self.log.info('Accessory Bridge Driver started')
            except:
                self.log.error('Error during startup', exc_info=True)
                
        async def stop(self):
            
            try:
                self.log.info('Stopping Accessory Bridge Driver')
                for drv in self.drivers:
                    self.drivers[drv].stop()
            except:
                self.log.error('Error stopping Accessory Bridge Driver', exc_info=True)
                
        def addExtraLogs(self):
            
            pass
        
            #self.accessory_logger = logging.getLogger('pyhap.accessory_driver')
            #self.accessory_logger.addHandler(self.log.handlers[0])
            #self.accessory_logger.setLevel(logging.INFO)
        
            #self.accessory_driver_logger = logging.getLogger('pyhap.accessory_driver')
            #self.accessory_driver_logger.addHandler(self.log.handlers[0])
            #self.accessory_driver_logger.setLevel(logging.INFO)

            #self.hap_server_logger = logging.getLogger('pyhap.hap_server')
            #self.hap_server_logger.addHandler(self.log.handlers[0])
            #self.hap_server_logger.setLevel(logging.INFO)
        
            #self.log.setLevel(logging.INFO)   
            
        async def virtualChangeHandler(self, deviceId, prop):
            
            # map open/close events to fake motion sense in order to send images through homekit notifications
            devname=self.getfriendlyNamebyendpointId(deviceId)
            maps=self.dataset.config['motionmap']
            
            try:
                #self.log.info('.. Changed %s/%s %s = %s' % (deviceId, prop['namespace'], prop['name'], prop['value']))
                if deviceId in maps:
                    self.log.info('Motion simulator detected for %s' % self.acc[maps[deviceId]])
                    self.acc[maps[deviceId]].blip()
                    #asyncio.sleep(3)
                    #self.acc[maps[deviceId]]._notdetected()
                
            except:
                self.log.error('Error in virtual change handler: %s %s' % (deviceId, prop), exc_info=True)

if __name__ == '__main__':
    adapter=homekitcamera(name='homekitcamera')
    adapter.start()

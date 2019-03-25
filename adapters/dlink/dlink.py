#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

from sofabase import sofabase
from sofabase import adapterbase
import devices


import datetime
import time
import os
import math
import random
import json
import aiohttp
import asyncio
import base64
from PIL import Image
import io
import shutil

import concurrent.futures

class OldcameraReader(object):
    
    basepath="/opt/sofa"
    
    def __init__(self, local_logger):
        self.log=local_logger
        self.cameras=self.loadAdapterPattern('camera')

    def loadAdapterPattern(self,pattern):
        
        try:
            return json.loads(open("%s/data/pattern/%s.json" % (self.basepath,pattern)).read())
        except:
            self.log.error('Error loading pattern: %s' % pattern,exc_info=True)

    def getAdminCredentials(self,cameraname):
        
        try:
            camcreds='%s:%s' % (self.cameras[cameraname]['admin'],self.cameras[cameraname]['adminpassword'])
            return camcreds.encode('utf-8')
        except:
            self.log.error('Could not find creds for %s' % cameraname,exc_info=True)
            return None

    def getCredentials(self,cameraname):
        
        try:
            camcreds='%s:%s' % (self.cameras[cameraname]['username'],self.cameras[cameraname]['password'])
            return camcreds.encode('utf-8')
        except:
            self.log.error('Could not find creds for %s' % cameraname,exc_info=True)
            return None

    def streamCamera(self,cameraname):
        try:

            if cameraname.lower() in self.cameras:
                if self.cameras[cameraname.lower()]['type']=='dlink':
                    stream=self.streamDlink(cameraname.lower())
                elif self.cameras[cameraname.lower()]['type']=='edimax':
                    stream=self.streamEdimax(cameraname.lower())
                elif self.cameras[cameraname.lower()]['type']=='amcrest':
                    stream=self.streamAmcrest(cameraname.lower())
                else:
                    stream=None
            else:
                stream=None
        
            return stream
        except:
            self.log.error('Error streaming camera',exc_info=True)
            return None

    def snapshotCamera(self,cameraname):
        try:
            if cameraname.lower() in self.cameras:
                if self.cameras[cameraname.lower()]['type']=='dlink':
                    snapshot=self.snapshotDlink(cameraname.lower())
                elif self.cameras[cameraname.lower()]['type']=='edimax':
                    snapshot=self.snapshotEdimax(cameraname.lower())
                elif self.cameras[cameraname.lower()]['type']=='amcrest':
                    snapshot=self.snapshotAmcrest(cameraname.lower())

                else:
                    snapshot=None
            else:
                snapshot=None
                
            return snapshot
        except:
            self.log.error('Error taking camera snapshot',exc_info=True)
            return None

    def movePointCamera(self, cameraname, position):
        
        if cameraname.lower() in self.cameras:
            if self.cameras[cameraname.lower()]['type']=='dlink':
                self.movePointDlink(cameraname.lower(), position)
            else:
                self.log.error('Move requested for an unsupported camera vendor: %s' % self.cameras[cameraname.lower()]['type'])

    def privacyCamera(self, cameraname, setmode='Toggle'):
        
        self.log.info('Setting privacy mode for %s (%s)' % (cameraname.lower(), setmode))
        if cameraname.lower() in self.cameras:
            if self.cameras[cameraname.lower()]['type']=='dlink':
                self.privacyDlink(cameraname.lower(), setmode)
            else:
                self.log.error('Privacy requested for an unsupported camera vendor: %s' % self.cameras[cameraname.lower()]['type'])

        
        
    def snapshotEdimax(self,cameraname):
        try:
            response = urllib.request.urlopen("http://%s/snapshot.jpg" % self.cameras[cameraname.lower()]['fqdn'],timeout=2)
            return response.read()
        except:
            self.log.info("Edimax Camera Snapshot Error", exc_info=True)

    def streamEdimax(self,cameraname):
        try: 
            request = urllib.request.Request("http://%s:80/mjpg/video.mjpg" % self.cameras[cameraname.lower()]['fqdn'])
            request.add_header("Authorization", "Basic %s" % base64.b64encode(self.getCredentials(cameraname)).decode())   
            response = urllib.request.urlopen(request,timeout=2)
            return response            
        except:
            self.log.info("Edimax Camera ("+cameraname+") stream Error", exc_info=True)

    def snapshotAmcrest(self,cameraname):
        
        amcrestretry=0
        if amcrestretry<5:
            try:
                url="http://%s/cgi-bin/snapshot.cgi" % self.cameras[cameraname.lower()]['fqdn']
                p = urllib.request.HTTPPasswordMgrWithDefaultRealm()
                p.add_password(None, url, self.cameras[cameraname]['username'], self.cameras[cameraname]['password'])
                auth_handler = urllib.request.HTTPDigestAuthHandler(p)
                opener = urllib.request.build_opener(auth_handler)
                #urllib.request.install_opener(opener)
                response = opener.open(url,timeout=2)
                return response.read()
            
            except socket.timeout:
                self.log.info("Amcrest Camera ("+cameraname+") snapshot: Timeout Error")
                return None
            
            except urllib.error.URLError:
                self.log.info("Amcrest Camera ("+cameraname+") snapshot: URL open Error")
                return None
            
            except http.client.BadStatusLine:
                self.log.info('Amcrest returned Bad Status Line, because Amcrest is garbage.')
                return None
                #
                #self.log.info("Amcrest Camera ("+cameraname+") http Error", exc_info=True)
                #amcrestretry+=1
                #self.log.info("Will retry up to 5 times.  Retry: %s" % amcrestretry)
                
            except:
                self.log.info("Amcrest Camera ("+cameraname+") snapshot Error", exc_info=True)
                return None
        
        self.log.error('Too many retries on Amcrest camera snapshot: %s' % cameraname)
        return None

    def streamAmcrest(self,cameraname):
        try:
            url="http://%s/cgi-bin/mjpg/video.cgi" % self.cameras[cameraname.lower()]['fqdn']
            request = urllib.request.Request(url)
            self.log.info('start streaming amcrest: %s' % url)
            p = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            p.add_password(None, url, self.cameras[cameraname]['username'], self.cameras[cameraname]['password'])
            auth_handler = urllib.request.HTTPDigestAuthHandler(p)
            opener = urllib.request.build_opener(auth_handler)
            urllib.request.install_opener(opener)
            self.log.info('streaming amcrest: %s' % opener)
            response =  urllib.request.urlopen(request,timeout=2)
            self.log.info('streaming amcrest: %s' % response)
            return response
        except socket.timeout:
            self.log.info("Amcrest Camera ("+cameraname+") snapshot: Timeout Error")
            return None
        except urllib.error.URLError:
            self.log.info("Amcrest Camera ("+cameraname+") snapshot: URL open Error")
            return None
        except:
            self.log.info("Amcrest Camera ("+cameraname+") snapshot Error", exc_info=True)
            return None

    def streamDlink(self,cameraname):
        try:
            request = urllib.request.Request("http://%s/video/mjpg.cgi?profileid=2" % self.cameras[cameraname.lower()]['fqdn'])
            request.add_header("Authorization", "Basic %s" % base64.b64encode(self.getCredentials(cameraname)).decode())   
            response = urllib.request.urlopen(request,timeout=2)
            return response            
        except:
            self.log.info("dLink Camera ("+cameraname+") stream Error", exc_info=True)
            return None
    
    def snapshotDlink(self,cameraname):
        
        try:
            request = urllib.request.Request("http://%s/image/jpeg.cgi?profileid=2" % self.cameras[cameraname.lower()]['fqdn'])
            request.add_header("Authorization", "Basic %s" % base64.b64encode(self.getCredentials(cameraname)).decode())   
            response = urllib.request.urlopen(request,timeout=2)
            return response.read()
        except socket.timeout:
            self.log.info("dLink Camera ("+cameraname+") snapshot: Timeout Error")
            return None
        except urllib.error.URLError:
            self.log.info("dLink Camera ("+cameraname+") snapshot: URL open Error")
            return None
        except:
            self.log.info("dLink Camera ("+cameraname+") snapshot Error", exc_info=True)
            return None

    def privacyDlink(self, cameraname, setmode='Toggle'):
        try:
            self.log.info('Setting privacy mode to %s on %s' % (cameraname, setmode))
            if setmode==True or setmode=='True' or setmode=='1' or setmode==1:
                privset=1
            elif setmode==False or setmode=='False' or setmode=='0' or setmode==0:
                privset=0
            elif setmode=='Toggle':
                request = urllib.request.Request("http://%s/vb.htm?privacymaskenable" % self.cameras[cameraname.lower()]['fqdn'])
                request.add_header("Authorization", "Basic %s" % base64.b64encode(self.getAdminCredentials(cameraname)).decode())   
                response = urllib.request.urlopen(request,timeout=2)
                if response.read().decode('utf-8').find('privacymaskenable=1')>-1:
                    privset=0
                else:
                    privset=1

            request = urllib.request.Request("http://%s/vb.htm?privacymaskenable=%s" % (self.cameras[cameraname.lower()]['fqdn'], privset))
            request.add_header("Authorization", "Basic %s" % base64.b64encode(self.getAdminCredentials(cameraname)).decode())   
            response = urllib.request.urlopen(request,timeout=2)
            return response.read()
        except:
            self.log.info("dLink Camera ("+cameraname+") Move Error", exc_info=True)
        

    def moveDlink(self,cameraname,x,y):
        try:
            request = urllib.request.Request("http://%s/cgi/ptdc.cgi?command=set_relative_pos&posX=%s&posY=%s" % (self.cameras[cameraname.lower()]['fqdn'], x,y))
            request.add_header("Authorization", "Basic %s" % base64.b64encode(self.getAdminCredentials(cameraname)).decode())   
            response = urllib.request.urlopen(request,timeout=2)
            return response.read()
        except:
            self.log.info("dLink Camera ("+cameraname+") Move Error", exc_info=True)

    def movePointDlink(self,cameraname,point):
        try:
            self.log.info('Moving dlink camera %s to point %s' % (cameraname,point))
            request = urllib.request.Request("http://%s/cgi-bin/longcctvpst.cgi?action=goto&number=%s" % (self.cameras[cameraname.lower()]['fqdn'], point))
            request.add_header("Authorization", "Basic %s" % base64.b64encode(self.getAdminCredentials(cameraname)).decode())   
            response = urllib.request.urlopen(request,timeout=2)
            return response.read()
        except:
            self.log.info("dLink Camera ("+cameraname+") MovePoint Error", exc_info=True)


    def homeDlink(self,cameraname):
        try:
            request = urllib.request.Request("http://"+cameraname+".dayton.home/cgi/ptdc.cgi?command=go_home" % self.cameras[cameraname.lower()]['fqdn'])
            request.add_header("Authorization", "Basic %s" % base64.b64encode(self.getAdminCredentials(cameraname)).decode())   
            response = urllib.request.urlopen(request,timeout=2)
            return response.read()
        except:
            self.log.info("dLink Camera ("+cameraname+") move home Error", exc_info=True)

class dlinkCameraControl():

    def snapshotCamera(self,cameraname):
        
        try:
            request = urllib.request.Request("http://%s/image/jpeg.cgi?profileid=2" % self.cameras[cameraname.lower()]['fqdn'])
            request.add_header("Authorization", "Basic %s" % base64.b64encode(self.getCredentials(cameraname)).decode())   
            response = urllib.request.urlopen(request,timeout=2)
            return response.read()
        except socket.timeout:
            self.log.info("dLink Camera ("+cameraname+") snapshot: Timeout Error")
            return None
        except urllib.error.URLError:
            self.log.info("dLink Camera ("+cameraname+") snapshot: URL open Error")
            return None
        except:
            self.log.info("dLink Camera ("+cameraname+") snapshot Error", exc_info=True)
            return None
    


class dlink(sofabase):

    class adapterProcess():

        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.log=log
            self.notify=notify
            #self.cameras=dlinkCameraControl()
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            
            
        async def start(self):
            try:
                self.log.info('.. Starting dlink')
                self.retainment=self.dataset.config['captures']['retain']
                await self.dataset.ingest({'camera': self.dataset.config['cameras']})
                await self.cleanRetainment()
            except:
                self.log.error('Error getting camera list', exc_info=True)

        async def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="camera":
                    return self.addCamera(path.split("/")[2])

            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False


        def addCamera(self, deviceid):

            nativeObject=self.dataset.nativeDevices['camera'][deviceid]
            if nativeObject['name'] not in self.dataset.devices:
                return self.dataset.addDevice(nativeObject['name'], devices.simpleCamera('dlink/camera/%s' % deviceid, nativeObject['name']))
           
            return False


        async def checkRetainment(self):
        
            try:
                realdirs=[]
                capdirs=self.getCaptureDirectories()
                for cap in capdirs:
                    camtypes=self.getCameraCaptureTypes(cap)
                    for camtype in camtypes:
                        dates=self.getCameraCaptureDates(cap, camtype, includeEvent=True)
                        realdates=[]
                        for cdate in dates:
                            if cdate.startswith('Event/'):
                                realdate=datetime.datetime.strptime(cdate.split('/')[1], '%Y%m%d')
                            else:
                                realdate=datetime.datetime.strptime(cdate, '%Y%m%d')
                            delta=datetime.datetime.now()-realdate
                            if delta.days>self.dataset.config['captures']['retain']:
                                realdirs.append('%s/%s/%s/%s' % (self.dataset.config['captures']['basedir'], cap, camtype, cdate))
                return realdirs
            except:
                self.log.error('Error checking retainment', exc_info=True)

        async def cleanRetainment(self):
            olddirs=await self.checkRetainment()
            if not olddirs:
                self.log.info('.. No Directories found beyond the %s day retainment policy: %s' % (self.dataset.config['captures']['retain'], olddirs))
                return False
            for olddir in olddirs:
                try:
                    shutil.rmtree(olddir)
                    self.log.info('.. Removed old directory: %s' % olddir)
                except:
                    self.log.error('.. Error removing old directory: %s' % olddir, exc_info=True)
                return True

        def getCaptureDirectories(self):
            
            try:
                result={}
                basepath = self.dataset.config['captures']['basedir']
                
                for dirname in os.listdir(basepath):
                    fullpath = os.path.join(basepath, dirname)
                    if os.path.isdir(fullpath):
                        if dirname in self.dataset.config['cameras']:
                            result[dirname]=self.getCameraCaptureTypes(dirname)
                        
                return result
                
            except:
                self.log.error('Couldnt get directories', exc_info=True)
            
        def getCameraCaptureTypes(self, cameraname):
            
            try:
                result=[]

                campath = os.path.join(self.dataset.config['captures']['basedir'], cameraname)
                for dirname in os.listdir(campath):
                    fullpath = os.path.join(campath, dirname)
                    if os.path.isdir(fullpath):
                        if dirname.lower() in ['video','picture']:
                            result.append(dirname)

                return result
                
            except:
                self.log.error('Couldnt get directories', exc_info=True)

        def getCameraCaptureDates(self, cameraname, capturetype, includeEvent=False):
            
            try:
                result={}
                hasEvent=False

                campath = os.path.join(self.dataset.config['captures']['basedir'], cameraname, capturetype)
                
                # Motion capture events may use this structure
                if 'Event' in os.listdir(campath):
                    campath = os.path.join(campath,'Event')
                    hasEvent=True
                    
                for dirname in os.listdir(campath):
                    fullpath = os.path.join(campath, dirname)
                    if os.path.isdir(fullpath):
                        if dirname.startswith('20'):
                            data={'date': datetime.datetime.strptime(dirname, '%Y%m%d').strftime('%a %b %e') }
                            if includeEvent and hasEvent:
                                result['Event/%s' % dirname]=data
                            else:
                                result[dirname]=data
                        
                return result
                
            except:
                self.log.error('Couldnt get directories', exc_info=True)

        def getCameraCaptureHours(self, cameraname, capturetype, capturedate):
            
            try:
                result=[]

                precampath = os.path.join(self.dataset.config['captures']['basedir'], cameraname, capturetype)
                # Motion capture events may use this structure
                if 'Event' in os.listdir(precampath):
                    precampath = os.path.join(precampath,'Event')

                campath = os.path.join(precampath, capturedate)
                for dirname in os.listdir(campath):
                    fullpath = os.path.join(campath, dirname)
                    if os.path.isdir(fullpath):
                        if int(dirname)<24:
                            result.append(dirname)
                return result
                
            except:
                self.log.error('Couldnt get directories', exc_info=True)

        def getCameraCapturesByTime(self, cameraname, capturetype, capturedate, capturehour):
            
            try:
                result={}

                precampath = os.path.join(self.dataset.config['captures']['basedir'], cameraname, capturetype)
                # Motion capture events may use this structure
                if 'Event' in os.listdir(precampath):
                    precampath = os.path.join(precampath,'Event')

                campath = os.path.join(precampath, capturedate, capturehour)
                for filename in os.listdir(campath):
                    fullpath = os.path.join(campath, filename)
                    if os.path.isfile(fullpath):
                        t = os.path.getmtime(fullpath)
                        #self.log.info('gm: %s ' % strfdatedatetime.datetime.fromtimestamp(t) )
                        result[filename]={'date' : datetime.datetime.fromtimestamp(t).strftime('%-I:%M:%-S') }
                        #result[filename]={'date':stat.st_mtime}                       
                         
                return result
                
            except:
                self.log.error('Couldnt get directories', exc_info=True)


        def getCaptureByTimePath(self, cameraname, capturetype, capturedate, capturehour, filename, thumbnail=False):
            
            try:
                result=[]
                precampath = os.path.join(self.dataset.config['captures']['basedir'], cameraname, capturetype)
                # Motion capture events may use this structure
                if 'Event' in os.listdir(precampath):
                    precampath = os.path.join(precampath,'Event')

                campath = os.path.join(precampath, capturedate, capturehour, filename)

                img = Image.open(campath)
                if thumbnail:
                    img.thumbnail((200, 200), Image.ANTIALIAS)

                with io.BytesIO() as output:
                    img.save(output, format="JPEG")
                    return output.getvalue()

                #with open(campath,'rb') as imagefile:
                #    return imagefile.read()
            except:
                self.log.error('Error loading image: %s' % filename,exc_info=True)
                return None



        async def virtualThumbnail(self, path, client=None):
            
            try:
                if path.split('/')[0]=='captures':
                    ip=path.split('/')
                    return self.getCaptureByTimePath(ip[1], ip[2], ip[3], ip[4], ip[5], thumbnail=True)
                else:
                    playerObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath("/"+path))
                    url='http://'+playerObject['address']+"/image/jpeg.cgi"
                    auth = aiohttp.BasicAuth(playerObject["username"], playerObject["password"])
                    async with aiohttp.ClientSession(auth=auth) as client:
                        try:
                            async with client.get(url) as response:
                                result=await response.read()
                                return result

                        except asyncio.CancelledError:
                            self.log.error('asyncio Couldnt get thumbnail image for %s (cancelled)' % path)
                            return None

                        except concurrent.futures._base.CancelledError:
                            self.log.error('concurrent Couldnt get thumbnail image for %s (cancelled)' % path)
                            return None
            except:
                self.log.error('Couldnt get thumbnail image for %s' % path, exc_info=True)
                #return {'name':playerObject['name'], 'id':playerObject['speaker']['uid'], 'image':""}


        async def virtualImage(self, path, client=None):
            
            try:
                #self.log.info('Virtual image path: %s' % path)
                if path.split('/')[0]=='captures':
                    ip=path.split('/')
                    return self.getCaptureByTimePath(ip[1] ,ip[2], ip[3], ip[4], ip[5])
                    
                else:
                    playerObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath("/"+path))
                    url='http://'+playerObject['address']+"/image/jpeg.cgi?profileid=2"
                    auth = aiohttp.BasicAuth(playerObject["username"], playerObject["password"])
                    async with aiohttp.ClientSession(auth=auth) as client:
                        async with client.get(url) as response:
                            result=await response.read()
                            return result

            except:
                self.log.error('Couldnt get image for %s' % playerObject, exc_info=True)
                #return {'name':playerObject['name'], 'id':playerObject['speaker']['uid'], 'image':""}
                

        async def virtualList(self, itempath, query={}):

            try:
                if itempath=="captures":
                    return self.getCaptureDirectories()

                if '/' in itempath:
                    ip=itempath.split('/')
                    
                    # This is garbage and needs to be handled better
                    
                    if ip[0]!='captures':
                        return false
                    
                    if len(ip)==3:
                        if ip[1] in self.dataset.config['cameras']:
                            if ip[2] in self.getCameraCaptureTypes(ip[1]):
                                return self.getCameraCaptureDates(ip[1], ip[2])

                    if len(ip)==4:
                        if ip[1] in self.dataset.config['cameras']:
                            if ip[2] in self.getCameraCaptureTypes(ip[1]):
                                if ip[3] in self.getCameraCaptureDates(ip[1],ip[2]):
                                    return self.getCameraCaptureHours(ip[1] ,ip[2], ip[3])

                    if len(ip)==5:
                        if ip[1] in self.dataset.config['cameras']:
                            if ip[2] in self.getCameraCaptureTypes(ip[1]):
                                if ip[3] in self.getCameraCaptureDates(ip[1],ip[2]):
                                    if ip[4] in self.getCameraCaptureHours(ip[1] ,ip[2], ip[3]):
                                        return self.getCameraCapturesByTime(ip[1] ,ip[2], ip[3], ip[4])


            except:
                self.log.error('Couldnt get list for %s' % itempath, exc_info=True)



if __name__ == '__main__':
    adapter=dlink(name='dlink')
    adapter.start()
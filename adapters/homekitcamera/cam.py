"""An example of how to setup and start an Accessory.

This is:
1. Create the Accessory object you want.
2. Add it to an AccessoryDriver, which will advertise it on the local network,
    setup a server to answer client queries, etc.
"""
import logging
import signal
import asyncio
import aiohttp

from pyhap.accessory_driver import AccessoryDriver
from pyhap import camera

class unifi_camera(camera.Camera):

    def __init__(self, options, log, *args, **kwargs):
        self.log=log
        self.log.info('Options: %s' % options)
        super().__init__(options, *args, **kwargs)
        motion=self.add_preload_service('MotionSensor')
        self.char_detected = motion.configure_char('MotionDetected')


    def _detected(self):
        self.char_detected.set_value(True)
    
    def get_snapshot(self, image_size):  # pylint: disable=unused-argument, no-self-use
        """Return a jpeg of a snapshot from the camera.

        Overwrite to implement getting snapshots from your camera.

        :param image_size: ``dict`` describing the requested image size. Contains the
            keys "image-width" and "image-height"
        """
        
        if not hasattr(self, 'loop'):
            self.loop=asyncio.new_event_loop()
        self._detected()    
        return self.loop.run_until_complete(self.get_unifi_snap())

    async def get_unifi_snap(self):
        nvr="unifi-video.dayton.tech"
        nvr_port="7443"
        api_key="DFJxPqr96pRQtPPzE0s27vu8LQqFBp2A"
        camera_id="5cb660eec2dcf0bd5a94a99a"
        
        url="https://%s:%s/api/2.0/snapshot/camera/%s?force=true&apiKey=%s" % (nvr, nvr_port, camera_id, api_key)
        #self.log.info('URL: %s' % url)
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as client:
            async with client.get(url) as response:
                result=await response.read()
                return result    


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
                    [640, 480, 30],
                    [1280, 720, 15],
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
            "address": "192.168.0.35"
            "start_stream_cmd":  (
                "ffmpeg -rtsp_transport http -re -i rtsp://unifi-video.dayton.tech:7447/5cb660eec2dcf0bd5a94a99a_0?apiKey=DFJxPqr96pRQtPPzE0s27vu8LQqFBp2A "
                "-vcodec libx264 -an -pix_fmt yuv420p -r {fps} -f rawvideo -tune zerolatency -vf scale=1280x720 "
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
                self.log.info('Starting homekit')
                await self.dataset.ingest({'accessorymap': self.loadJSON(self.dataset.config['accessory_map'])})
                #self.log.info('Known devices: %s' % self.dataset.nativeDevices['accessorymap'])
                #self.getNewAid()
                self.accloop=asyncio.new_event_loop()

                self.driver = AccessoryDriver(port=51827)
                self.log.info('PIN: %s' % self.driver.state.pincode)
                self.log.info('Options: %' % self.options)
                self.acc = unifi_camera(self.options, self.log, driver, "Street")
                self.driver.add_accessory(accessory=self.acc)

                signal.signal(signal.SIGTERM, self.driver.signal_handler)

                self.executor.submit(self.driver.start)
                self.log.info('Accessory Bridge Driver started')
            except:
                self.log.error('Error during startup', exc_info=True)
                
        async def stop(self):
            
            try:
                self.log.info('Stopping Accessory Bridge Driver')
                self.driver.stop()
            except:
                self.log.error('Error stopping Accessory Bridge Driver', exc_info=True)
                
        def addExtraLogs(self):
            
            pass
        
            self.accessory_logger = logging.getLogger('pyhap.accessory_driver')
            self.accessory_logger.addHandler(self.log.handlers[0])
            self.accessory_logger.setLevel(logging.DEBUG)
        
            self.accessory_driver_logger = logging.getLogger('pyhap.accessory_driver')
            self.accessory_driver_logger.addHandler(self.log.handlers[0])
            self.accessory_driver_logger.setLevel(logging.DEBUG)

            self.hap_server_logger = logging.getLogger('pyhap.hap_server')
            self.hap_server_logger.addHandler(self.log.handlers[0])
            self.hap_server_logger.setLevel(logging.DEBUG)
        
            self.log.setLevel(logging.DEBUG)        


if __name__ == '__main__':
    adapter=homekitcamera(name='homekitcamera')
    adapter.start()


import sys
import shelve
import datetime
import time

import pytz
from six.moves import input

from pyecobee import *

class adapterid():
    
    configinfo={"adapterid":"ecobeeInfo","savestate":False,"noloop":False}

class ecobeeInfo():

    def __init__ (self, adapter):

        self.adapter=adapter
        self.mqueue=adapter.mqueue
        self.aqueue=adapter.adapterqueue
        self.localcache=adapter.localcache
        self.forwardevent=adapter.forwardevent
        self.log=adapter.log
        self.adapterconfig=adapter.adapterconfig
        self.configinfo=adapter.configinfo
        self.zonesfaulted=[]
        self.queuestart=datetime.datetime.now()
        self.timepoll=self.configinfo['pollinterval']
        self.thermostat_name = self.configinfo['name']
        self.apikey=self.configinfo['apikey']
        self.shelfdb=self.configinfo['shelfdb']
        self.authFail=False

    def start(self):
        self.ecobee_service=self.setupEcobee()
        thermostatdata=self.updateThermostat()
        #self.log.info('Thermostat Data: %s' % thermostatdata)
        self.forwardevent(action="update", category="thermostat", data=thermostatdata)
        self.getSimpleThermostats()
        return True
        
    def processQueue(self):
        pass
        
    def processNoQueue(self): 
        try:
            delta = datetime.datetime.now()-self.queuestart
            if delta.seconds>self.timepoll:
                #self.log.info('heartbeat: %s' % self.device)
                self.queuestart=datetime.datetime.now()
                if datetime.datetime.now(pytz.utc) > self.ecobee_service.access_token_expires_on:
                    token_response = self.refresh_tokens(self.ecobee_service)
                thermostatdata=self.updateThermostat()
                #self.log.info('Thermostat Data: %s' % thermostatdata)
                self.forwardevent(action="update", category="thermostat", data=thermostatdata)
                self.getSimpleThermostats()
            else:
                time.sleep(.1)
        except:
            self.log.error('Error handling noqueue checks',exc_info=True)
        pass

    def persist_to_shelf(self, file_name, ecobee_service):
        pyecobee_db = shelve.open(file_name, protocol=2)
        pyecobee_db[ecobee_service.thermostat_name] = ecobee_service
        pyecobee_db.close()


    def refresh_tokens(self, ecobee_service):
        token_response = ecobee_service.refresh_tokens()
        self.log.info('Ecobee Token refreshed')
        self.log.debug('TokenResponse returned from ecobee_service.refresh_tokens():\n{0}'.format(token_response.pretty_format()))
        self.persist_to_shelf(self.shelfdb, ecobee_service)

    def request_tokens(self, ecobee_service):
        token_response = ecobee_service.request_tokens()
        self.log.info('TokenResponse returned from ecobee_service.request_tokens():\n{0}'.format(token_response.pretty_format()))
        self.persist_to_shelf(self.shelfdb, ecobee_service)


    def authorize(self, ecobee_service):
        authorize_response = ecobee_service.authorize()
        self.log.info('AuthorizeResponse returned from ecobee_service.authorize():\n{0}'.format(authorize_response.pretty_format()))

        self.persist_to_shelf(self.shelfdb, ecobee_service)

        self.log.info('Please goto ecobee.com, login to the web portal and click on the settings tab. Ensure the My '
                'Apps widget is enabled. If it is not click on the My Apps option in the menu on the left. In the '
                'My Apps widget paste "{0}" and in the textbox labelled "Enter your 4 digit pin to '
                'install your third party app" and then click "Install App". The next screen will display any '
                'permissions the app requires and will ask you to click "Authorize" to add the application.\n\n'
                'After completing this step please hit "Enter" to continue.'.format(
        authorize_response.ecobee_pin))
        #input()

    def props(self, et):
        return {s: getattr(et, s) for s in et.__slots__ if hasattr(et, s)}
    
    def updateThermostat(self):
        
        selection = Selection(selection_type=SelectionType.REGISTERED.value, selection_match='', include_alerts=True,
                      include_device=True, include_electricity=True, include_equipment_status=True,
                      include_events=True, include_extended_runtime=True, include_house_details=True,
                      include_location=True, include_management=True, include_notification_settings=True,
                      include_oem_cfg=False, include_privacy=False, include_program=True, include_reminders=True,
                      include_runtime=True, include_security_settings=False, include_sensors=True,
                      include_settings=True, include_technician=True, include_utility=True, include_version=True,
                      include_weather=True)

        thermostat_response = self.ecobee_service.request_thermostats(selection)
        #self.log.info((thermostat_response.pretty_format())
        #assert thermostat_response.status.code == 0, 'Failure while executing request_thermostats:\n{0}'.format(thermostat_response.pretty_format()) 
        stats=dict()
        for therm in thermostat_response.thermostat_list:
            tstat=dict()
            tstat['name']=therm.name
            tstat['brand']=therm.brand
            tstat['equipment_status']=therm.equipment_status
            #et=therm.extended_runtime
            tstat['runtime']=self.smoothData(self.props(therm.runtime))
            stats[str(therm.identifier)]=tstat
        return stats
        
    def smoothData(self, data):
        
        temperatureValues=['_desired_cool', '_desired_heat', '_actual_temperature', '_desired_cool_range', '_desired_heat_range']

        output={}
        for item in data:
            if item in temperatureValues:
                if type(data[item])==list:
                    output[item.strip('_')]=[]
                    for litem in data[item]:
                        output[item.strip('_')].append(litem/10)
                else:
                    output[item.strip('_')]=data[item]/10
            else:
                output[item.strip('_')]=data[item]
        
        return output

    def getSimpleThermostats(self):
        
        simplethermostats=dict()
        for node in self.localcache['thermostat']:
            try:
                thermostat=dict()
                thermostat['address']=self.adapter.adaptername+'.thermostat.'+node
                thermostat['temperature']=self.localcache['thermostat'][node]['runtime']['actual_temperature']
                thermostat['state']=self.localcache['thermostat'][node]['equipment_status']
                thermostat['humidity']=self.localcache['thermostat'][node]['runtime']['actual_humidity']
                thermostat['mode']='cool' #SHIM!
                thermostat['heatsetpoint']=self.localcache['thermostat'][node]['runtime']['desired_heat']
                thermostat['coolsetpoint']=self.localcache['thermostat'][node]['runtime']['desired_cool']
                thermostat['source']='eb'
                simplethermostats[self.localcache['thermostat'][node]['name']]=thermostat
                
                self.forwardevent(action="update", category="simple", data={'thermostat':simplethermostats})

            except:
                self.log.error('Error converting to simple thermostats',exc_info=True)
        
        return { 'thermostat': simplethermostats }
            
       
    def setupEcobee(self):
        
        try:
            pyecobee_db = shelve.open(self.shelfdb, protocol=2)
            ecobee_service = pyecobee_db[self.thermostat_name]
        except KeyError:
            application_key = self.apikey
            ecobee_service = EcobeeService(thermostat_name=self.thermostat_name, application_key=application_key)
        finally:
            pyecobee_db.close()

        if not ecobee_service.authorization_token:
            self.authorize(ecobee_service)

        if not ecobee_service.access_token or self.authFail:
            self.request_tokens(ecobee_service)
            pass

        now_utc = datetime.datetime.now(pytz.utc)
        if now_utc > ecobee_service.refresh_token_expires_on:
            self.authorize(ecobee_service)
            self.request_tokens(ecobee_service)
        elif now_utc > ecobee_service.access_token_expires_on:
            token_response = self.refresh_tokens(ecobee_service)
            
        return ecobee_service
        


if __name__ == '__main__':
    pass
    
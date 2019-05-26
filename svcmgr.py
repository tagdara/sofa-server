#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
import json

class sofa_service_manager():
    
    def __init__(self, adaptername):
        self.adapter=adaptername
    
    def buildContents(self, basepath, adapter, **kwargs):

        data = {    "Unit": {
                                "Description": "Sofa 2 - %s" % adapter,
                                "After":"syslog.target network-online.target",
                            },
                            "Service": {
                                "Type": "simple",
                                "ExecStart":"%s/adapters/%s/%s.py" % (basepath, adapter, adapter),
                                "Restart":"Always",
                                "RestartSec":"300",
                                "KillMode":"control-group",
                            },
                            "Install": {
                                "WantedBy": "multi-user.target"
                            }
                        }
        return data
        
        
    def systemd_formatter(self, data):
        
        output=""
        for section in data:
            output+="[%s]\r\n" % section
            for line in data[section]:
                output+="%s=%s\r\n" % (line, data[section][line])
            output+="\r\n"
        return output
        
    def check_for_service(self, servicefilename):
        try:
            with open(servicefilename, "r") as servicefile:
                serviceinfo=servicefile.read()
            print('Contents of existing service file:')
            print(serviceinfo)
        except:
            print('could not open  %s' % servicefilename)
        
        
    def readBaseConfig(self):

        try:
            baseconfig={}
            configdir=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config'))
            with open(os.path.join(configdir, 'sofabase.json'), "r") as configfile:
                baseconfig=json.loads(configfile.read())
        except:
            print('Did not load base config')
            
        try:
            if 'configDirectory' not in baseconfig:
                baseconfig['configDirectory']=configdir
            if 'baseDirectory' not in baseconfig:
                baseconfig['baseDirectory']=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
            if 'logDirectory' not in baseconfig:
                baseconfig['logDirectory']=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'log'))
            if 'mqttBroker' not in baseconfig:
                baseconfig['mqttBroker']='localhost'
            if 'restAddress' not in baseconfig:
                baseconfig['restAddress']='localhost'

            return baseconfig
        except:
            print('Did not get base config properly')
            sys.exit(1)

    def start(self):
        self.config=self.readBaseConfig()
        self.servicefilename=os.path.join('/etc/systemd/system', 'sofa-%s.service' % self.adapter)
        self.check_for_service(self.servicefilename)
        self.contents=self.buildContents(self.config['baseDirectory'], self.adapter)
        output=self.systemd_formatter(self.contents)
        print('using path %s' % self.servicefilename )
        with open(self.servicefilename, "w") as servicefile:
            servicefile.write(output)
        print(output)
        

if __name__ == '__main__':
    svcmgr=sofa_service_manager('homekitcamera')
    svcmgr.start()

#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
import json
import subprocess
import pprint

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
                                "Restart":"always",
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
            print('Service exists: %s ' % servicefilename)
            #print(serviceinfo)
            return True
        except:
            print('could not open  %s' % servicefilename)
            return False
            
    def check_service_running(self, servicefilename):
        result = self.run_and_return("systemctl is-active --quiet %s" % servicefilename, True)
        if result>0:
            return False
        return True
            
    def run_and_return(self, command, returncode=False):
        result = subprocess.run(command.split(" "), stdout=subprocess.PIPE)
        if returncode:
            return result.returncode
        else:
            return result.stdout
        
    def check_services(self, service_list):
        
        pp = pprint.PrettyPrinter(indent=4, width=80, compact=True)
        for service in service_list:
            #try:
                self.servicefilename=os.path.join('/etc/systemd/system', 'sofa-%s.service' % service)
                service_exists=self.check_for_service(self.servicefilename)
                if service_exists:
                    service_running=self.check_service_running(self.servicefilename)
                    print('.. %s service exists. running: %s / %s ' % (service, service_running, self.servicefilename))
                else:
                    service_running=False
                    
                if not service_running:
                    if service_exists:
                        result = self.run_and_return("systemctl stop sofa-%s.service" % service)
                        print('.. %s service stop: %s' % (service, result))
                        result = self.run_and_return("systemctl disable sofa-%s.service" % service)
                        print('.. %s service disable: %s' % (service, result))
                    self.contents=self.buildContents(self.config['baseDirectory'], service)
                    output=self.systemd_formatter(self.contents)
                    print('.. %s creating service file:  %s' % (service, self.servicefilename) )
                    with open(self.servicefilename, "w") as servicefile:
                        servicefile.write(output)
                    result = self.run_and_return("systemctl daemon-reload")      
                    print('.. %s daemon-reload: %s' % (service, result))
                    result = self.run_and_return("systemctl enable sofa-%s.service" % service)
                    print('.. %s service enable: %s' % (service, result))
                    print(' .. %s starting service' % service)
                    result = self.run_and_return("systemctl start sofa-%s.service" % service)
                    pp.pprint('.. %s service start: %s' % (service, result))
                
                result = self.run_and_return("systemctl status sofa-%s.service --lines=0" % service)
                pp.pprint('service status: %s' % result)
            #except:
            #    print('.. error while trying to add service for %s' % service)
                
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
        if self.adapter=='all':
            if 'adapters' in self.config:
                self.check_services(self.config['adapters'])
        else:
            self.check_services([self.adapter])
        

if __name__ == '__main__':

    svcmgr=sofa_service_manager(sys.argv[1])
    svcmgr.start()

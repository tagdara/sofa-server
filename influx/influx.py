#!/usr/bin/python3

import sys
sys.path.append('/opt/beta')

from sofabase import sofabase
import devices
import json
import asyncio
import concurrent.futures
import datetime
import uuid
import influxdb

class influxServer(sofabase):

    class adapterProcess():
    
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            #self.definitions=definitions.Definitions
            self.log=log
            self.notify=notify
            self.dbConnected=False
            self.dbRetries=0
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
                

        def jsonDateHandler(self, obj):

            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            else:
                self.log.error('Found unknown object for json dump: (%s) %s' % (type(obj),obj))
            return None
            
            
        async def start(self):
            self.polltime=1
            self.dblistcache=[]
            self.log.info('.. Starting Influx Manager')
            self.connectDatabase('beta')
                
        async def handleChangeReport(self, message):
            try:
                endpointId=message['event']['endpoint']['endpointId']
                for change in message['payload']['change']['properties']:
                    if type(change['value']) in [list, dict]:
                        change['value']=str(change['value'])
                    if change['value']:
                        line=[{  "measurement":"controller_property", 
                            "tags": {"endpoint":endpointId, "namespace":change['namespace'].split('.')[0], "controller": change['namespace'].split('.')[1] },
                            "time": change["timeOfSample"],
                            "fields": { change["name"] : change["value"]}
                        }]
                        self.influxclient.write_points(line,database='beta')
                        self.log.info('<< Influx: %s' % line)
            except:
                self.log.info("Error handling change report for %s" % message,exc_info=True)            


        def retryDatabase(self, dbname):
            
            try:
                self.log.info('Retrying database connection')
                time.sleep(5*dbRetries)
                self.connectDatabase(dbname)
            except:
                self.log.error('Error Retrying Database Connection', exc_info=True)
                self.dbConnected=False

        def connectDatabase(self, dbname):
            
            try:
                self.influxclient=influxdb.InfluxDBClient(self.dataset.config['dbserver'])
                dbs=self.influxclient.get_list_database()    
                if not self.databaseExists(dbname):
                    self.createDatabase(dbname)
                self.log.info('Databases: %s' % dbs)
                self.dbConnected=True
                self.dbRetries=0
            except:
                self.log.error('Error starting Influx', exc_info=True)
                self.dbConnected=False
                  
        def createDatabase(self, dbname):
        
            try:
                self.influxclient.create_database(dbname)
                self.dblistcache.append(dbname)
            except:
                self.log.info("Could not create Database "+dbname,exc_info=True)


        def databaseExists(self, dbname):
        
            if dbname in self.dblistcache:
                return True
        
            try:
                dblist=self.influxclient.get_list_database()
                for db in dblist:
                    if db['name']==dbname:
                        self.dblistcache.append(dbname)
                        return True
                return False
            except:
                self.log.info("Could not look for Database "+dbname,exc_info=True)

        def writeInflux(self, adapter, item, data):
        
            try:
                if type(data)==list:
                    self.log.info('List data is not currently supported in the influx history database: %s' % (item))
                    return None
            
                if not self.databaseExists(adapter):
                    self.createDatabase(adapter)
                
                ifjson=[{'measurement':item,'fields': {'value':data}}]
                
                try:
                    while not self.dbConnected:
                        self.retryDatabaseConnection('beta')
                    self.influxclient.write_points(ifjson,database=adapter)
                except ConnectionRefusedError:
                    self.dbConnected=False
                    self.retryDatabaseConnection('beta')
                
                self.log.info('Sent %s to influx' % ifjson)

            except:
                self.log.error('Error inserting influx data with the following value: %s = %s (%s)' % (item, data, ifjson),exc_info=True)


        def virtualControllers(self, itempath):

            try:
                return {}

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)

        async def virtualList(self, itempath, query={}):

            try:
                if itempath=="powerState":
                    qry='select endpoint,powerState from controller_property'
                    result=self.influxclient.query(qry,database='beta')
                    return result.raw
                    
                if itempath=="query":
                    qry=query
                    result=self.influxclient.query(qry,database='beta')
                    return result.raw
                    
                return {}

            except:
                self.log.error('Error getting virtual controller types for %s' % itempath, exc_info=True)



        def virtualControllerProperty(self, nativeObj, controllerProp):
        
            # Scenes have no properties
            return None

        

if __name__ == '__main__':
    adapter=influxServer(port=8094, adaptername='influx', isAsync=True)
    adapter.start()
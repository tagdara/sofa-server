
import aiohttp
import json
import asyncio

class dev_builder():
    
    def __init__(self):
        pass
    
    def start(self):
        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(self.get_spec())
    
    async def get_spec(self):  
        
        url="https://raw.githubusercontent.com/alexa/alexa-smarthome/master/validation_schemas/alexa_smart_home_message_schema.json"
        async with aiohttp.ClientSession() as client:
            async with client.get(url) as response:
                result=await response.read()
                if result:
                    self.spec=json.loads(result.decode())
                    self.interface_defs=self.spec['definitions']['common.properties']['interfaces']
                    print(json.dumps(self.interface_defs, indent=4, sort_keys=True))
                    for interface in self.interface_defs:
                        print(interface)
                else:
                    print('No data received from post')
                    self.spec={}
                        



if __name__ == '__main__':
    db=dev_builder()
    db.start()
# statusAnswer.py
# copyright 2018, Keith P Jolley, keithpjolley@gmail.com, squalor heights, ca, usa
# Thu May 31 16:47:03 PDT 2018

# Don't look at me, i'm hideous.
# Decoding network structures is ugly and error prone.
# 

import struct
import numpy as np

# expects:
#   "want" is the type of data we are looking for
#     see https://docs.python.org/3/library/struct.html#format-characters
#     I make (un)educated guesses on if I think the data will be signed or unsigned.
#   "buff" is the buffer to extract from
#   "offset" is where in the buffer to read from
# returns (data, newoffset) where:
#  "data" is sizeof("want") byte(s) from "want" starting at "offset"
#  "newoffset" is "offset + sizeof("want") to help keep track of where in "buff" to read next
def getSome(want, buff, offset):
    if want=='S':
        return decodeString(buff,offset)
    if want=='s':
        return decodeString(buff,offset,2)
    fmt = "<" + want
    newoffset = offset + struct.calcsize(fmt)
    if want=='c':
        return struct.unpack_from(fmt, buff, offset)[0], newoffset
    return struct.unpack_from(fmt, buff, offset)[0], newoffset

# decode the gateway's response to a "status" query
# see: https://github.com/parnic/node-screenlogic/blob/master/messages/SLPoolStatusMessage.js

def decodeString(data, offset, bonus=0):
    
    sl, offset=getSome('i', data, offset)
    s=""

    if (sl % 4):
        # print('Adding %s+%s to get to multiple of 4' % (sl, (4-(sl % 4))))
        sl=sl+(4-(sl % 4))

    for i in range(sl):
        ns, offset=getSome('c',data, offset)
        if ns.decode()!="\x00":
            s=s+ns.decode()
    return s, offset

def decodeControllerConfig(data):
    
    config={}
    offset=0
    fieldlist={'controller_id':'I','min_set_point_low':'B','min_set_point_high':'B',
                'max_set_point_low':'B','max_set_point_high':'B',
                "deg_c":"B", "controller_type":"B", "hw_type": "B", "controller_data": "B",
                "equip_flags":"I", "generic_circuit_name":"s", "circuit_count":"I",
    }
    circuitfields={"id":"I","name":"S", "name_index":"B", "function":"B", "interface":"B", "flags":"B",
                    "color_set":"B", "color_pos":"B", "color_stagger":"B", "device_id": "B", "default_RT":"H",
                    "pad_1":"B", "pad_2":"B"}

    config['config']={}
    for datafield in fieldlist:
        df, offset = getSome(fieldlist[datafield], data, offset)
        config['config'][datafield]=df
    
    config['circuits']={}
    for i in range(config['config']['circuit_count']):
        circ={}
        for datafield in circuitfields:
            df, offset = getSome(circuitfields[datafield], data, offset)
            circ[datafield]=df        
    
        config['circuits']['%s' % i]=circ
    
    return config

def decodeStatusAnswer(data):
    
    offset=0
    fieldlist={ "ok":"I", "freezeMode":"B", "remotes":"B", "poolDelay":"B", "spaDelay":"B", 
                "cleanerDelay":"B"
    }

    status={}
    for datafield in fieldlist:
        df, offset = getSome(fieldlist[datafield], data, offset)
        status[datafield]=df
   
    # fast forward 3 bytes. why? because.
    offset = offset + struct.calcsize("3B")

    fieldlist={ "airtemp":"I", "bodyCount":"I" }

    for datafield in fieldlist:
        df, offset = getSome(fieldlist[datafield], data, offset)
        status[datafield]=df

    fieldlist={"bodyType":"I", 'currentTemp':'I','heatStatus':'I','setPoint':'I','coolSetPoint':'I','heatMode':'I'}
    status['bodies']={}
    for i in range(status['bodyCount']):
        bstatus={}
        for datafield in fieldlist:
            df, offset = getSome(fieldlist[datafield], data, offset)
            bstatus[datafield]=int(df)

        if bstatus['bodyType']==0:
            status['bodies']['pool']=bstatus
        if bstatus['bodyType']==1:
            status['bodies']['spa']=bstatus

    circuitCount, offset = getSome("I", data, offset)
    status["circuitCount"]=int(circuitCount)
    status['circuits']={}
    fieldlist={'id':'I','state':'I','color_set':'B','color_pos':'B','color_stagger':'B', 'delay':'B'}
    for i in range(circuitCount):
        cstatus={}
        for datafield in fieldlist:
            df, offset = getSome(fieldlist[datafield], data, offset)
            cstatus[datafield]=int(df)
        status['circuits']['%s' % i]=cstatus

    return status
    


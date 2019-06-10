#! /usr/bin/env python
# -*- coding: UTF8 -*-

# doQuery.py
# copyright 2018, Keith P Jolley, keithpjolley@gmail.com, squalor heights, ca, usa
# Thu May 31 16:47:03 PDT 2018

# sends the gateway a few commands and decodes/prints the responses.

import socket
import login
import doMessages
import decodeStatusAnswer
from constants import *

class doquery():

    def __init__(self, log, gatewayIP, gatewayPort):
        
        self.log=log
        self.gatewayIP=gatewayIP
        self.gatewayPort=gatewayPort

    def startPentair(self):
        
        try:
            if self.connectGateway(self.gatewayIP, self.gatewayPort):
                self.attentionGateway()
                self.challengeGateway()
                self.loginGateway()

                data=self.queryGatewayConfig()
                data['version']=self.queryGateway()
                return data
        except:
            self.log.error('Error getting Data', exc_info=True)
            return False

    def connectGateway(self, gatewayIP, gatewayPort):
    
        self.tcpSock = None
        self.log.info('Connecting to gateway: %s:%s' % (gatewayIP, gatewayPort))
        for res in socket.getaddrinfo(gatewayIP, gatewayPort, socket.AF_UNSPEC, socket.SOCK_STREAM):
            af, socktype, proto, canonname, sa = res
            try:
                self.tcpSock = socket.socket(af, socktype, proto)
            except OSError as msg:
                self.log.info('OS error connecting', exc_info=True)
                self.tcpSock = None
                return False
            
            try:
                self.tcpSock.connect(sa)
            except OSError as msg:
                self.log.info('OS error connecting', exc_info=True)
                self.tcpSock.close()
                self.tcpSock = None
                return False
            
            break
    
        if self.tcpSock is None:
            self.log.error("ERROR: {}: Could not open socket to gateway host.\n".format(me))
            return False
        
        self.log.info('TCPSOCK Connection made')
        return True


    def attentionGateway(self):
    
        try:
            #with self.tcpSock:
            # get the gateway's attention. The Protocol_Document.pdf explains how, not why.
            connectString = b'CONNECTSERVERHOST\r\n\r\n'  # not a string...
            self.tcpSock.sendall(connectString)
            # the gateway does not respond to the connect message. don't wait for something here because you aren't going to get it
            return True

        except:
            self.log.error('Error sending attention code', exc_info=True)
            return False

    def challengeGateway(self):
    
        try:
            # tx/rx challenge  (?)  (gateway returns its mac address in the form 01-23-45-AB-CD-EF)
            # why? dunno.
            #with self.tcpSock:
            #self.log.info('Sending challenge: %s' % doMessages.makeMessage(code.CHALLENGE_QUERY))
            self.tcpSock.sendall(doMessages.makeMessage(code.CHALLENGE_QUERY))
            data = self.tcpSock.recv(48)
            if not data:
                self.log.error("WARNING: {}: no {} data received.\n".format(me, "CHALLENGE_ANSWER"))
                return False
            rcvcode, data = doMessages.decodeMessage(data)
            if(rcvcode != code.CHALLENGE_ANSWER):
                self.log.error("WARNING: {}: rcvCode2({}) != {}.\n".format(me, CHALLENGE_ANSWER))
                return False
            
            return True
        
        except:
            self.log.error('Error sending challenge', exc_info=True)
            return False
   
    def loginGateway(self):
        # now that we've "connected" and "challenged," we can "login." None of these things
        # actually do anything, but they are required.
        try:
            msg = login.createLoginMessage()
            self.tcpSock.sendall(doMessages.makeMessage(code.LOCALLOGIN_QUERY, msg))
            data = self.tcpSock.recv(48)
            if not data:
                self.log.error("WARNING: {}: no {} data received.\n".format(me, "LOCALLOGIN_ANSWER"))
                return False
            rcvcode, data = doMessages.decodeMessage(data)
            if(rcvcode != code.LOCALLOGIN_ANSWER):
                self.log.error("WARNING: {}: rcvCode2({}) != {}.\n".format(me, rcvCode2, code.LOCALLOGIN_ANSWER))
                return False
                # response should be empty
            return True
        except:
            self.log.error('Error during login', exc_info=True)
            
    def queryGateway(self):
        
        try:
            # send a simple query and print the response, no advanced decoding required.
            self.tcpSock.sendall(doMessages.makeMessage(code.VERSION_QUERY))
            data = self.tcpSock.recv(480)
            if not data:
                self.log.error("WARNING: {}: no {} data received.\n".format(me, "VERSION_ANSWER"))
                return False
            rcvcode, data = doMessages.decodeMessage(data)
            if (rcvcode != code.VERSION_ANSWER):
                self.log.error("WARNING: {}: rcvCode2({}) != {}.\n".format(me, rcvCode2, code.VERSION_ANSWER))
                return False
                
            result=doMessages.getMessageString(data)
            #self.log.info('Query response: %s' % result)
            return result
        except:
            self.log.error('Error querying gateway', exc_info=True)

    def sendButtonPress(self, circuit, onoff):
        
        try:
            # send a simple query and print the response, no advanced decoding required.
            # onoff should be 1 or 0
            self.tcpSock.sendall(doMessages.makeMessage(code.BUTTONPRESS_QUERY, struct.pack("<III", 0, circuit, onoff)))
            rcvcode, data = doMessages.decodeMessage(self.tcpSock.recv(1024))
            if (rcvcode != code.BUTTONPRESS_ANSWER):
                self.log.error("WARNING: {}: rcvCode2({}) != {}.\n".format(me, rcvcode, code.BUTTONPRESS_ANSWER))
                return False
            #result=decodeStatusAnswer.decodeStatusAnswer(data)
            self.log.info('send button response: %s' % data)
            #return result
        except:
            self.log.error('Error querying gateway', exc_info=True)


    def sendColorLightsCommand(self, cmd):
        
        try:
            # send a simple query and print the response, no advanced decoding required.
            # cmd should be 0 to 21
            self.tcpSock.sendall(doMessages.makeMessage(code.COLORLIGHTSCOMMAND_QUERY, struct.pack("<II", 0, cmd)))
            rcvcode, data = doMessages.decodeMessage(self.tcpSock.recv(1024))
            if (rcvcode != code.COLORLIGHTSCOMMAND_ANSWER):
                self.log.error("WARNING: {}: rcvCode2({}) != {}.\n".format(me, rcvcode, code.COLORLIGHTSCOMMAND_ANSWER))
                return False
            #result=decodeStatusAnswer.decodeStatusAnswer(data)
            self.log.info('send button response: %s' % data)
            #return result
        except:
            self.log.error('Error querying gateway', exc_info=True)


    def queryGatewayConfig(self):
        
        try:
            self.tcpSock.sendall(doMessages.makeMessage(code.CONTROLLERCONFIG_QUERY, struct.pack("<II", 0, 0)))
            rcvcode, data = doMessages.decodeMessage(self.tcpSock.recv(1024))
            if (rcvcode != code.CONTROLLERCONFIG_ANSWER):
                self.log.error("WARNING: {}: rcvCode2({}) != {}.\n".format(me, rcvcode, code.CONTROLLERCONFIG_ANSWER))
                #return False
                
            result=decodeStatusAnswer.decodeControllerConfig(data)
            #self.log.info('Query response: %s' % result)
            return result
        except:
            self.log.error('Error querying gateway', exc_info=True)


    def advancedQueryGateway(self):
        
        try:
            # send a more advanced query and print the response. decoding done in "decodeStatusAnswer.py"
            self.tcpSock.sendall(doMessages.makeMessage(code.POOLSTATUS_QUERY, struct.pack("<I", 0)))
            rcvcode, data = doMessages.decodeMessage(self.tcpSock.recv(480))
            if (rcvcode != code.POOLSTATUS_ANSWER):
                self.log.error("WARNING: {}: rcvCode2({}) != {}.\n".format(me, rcvcode, code.POOLSTATUS_ANSWER))
                return False
            result=decodeStatusAnswer.decodeStatusAnswer(data)
            #self.log.info('Query response: %s' % result)
            return result

        except:
            self.log.error('Error with advanced querying gateway', exc_info=True)
            self.startPentair()
            return False


# same as "screen-logic.py" but you supply the host and port
if __name__ == "__main__":
    
    import sys
    if(len(sys.argv) != 3):
        print("ERROR: {}: usage: '{} gatewayIP port'".format(me(), me()))
        sys.exit(20)
    # don't bother checking for saneness, our user is really smart
    gatewayIP = sys.argv[1]
    gatewayPort = sys.argv[2]
    queryGateway(gatewayIP, gatewayPort)

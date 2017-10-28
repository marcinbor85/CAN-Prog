'''
Created on 23.10.2017

@author: mborowicz
'''
from . import AbstractProtocol

import can

import struct

from canprog.logger import log

CMD_INIT = 0x79
CMD_GET_COMMANDS = 0x00
CMD_GET_VERSION = 0x01
CMD_GET_ID = 0x02
CMD_CHANGE_SPEED = 0x03
CMD_READ_MEMORY = 0x11
CMD_GO = 0x21
CMD_WRITE_MEMORY = 0x31
CMD_ERASE = 0x43
CMD_WRITE_PROTECT = 0x63
CMD_WRITE_UNPROTECT = 0x73
CMD_READOUT_PROTECT = 0x82
CMD_READOUT_UNPROTECT = 0x92

BYTE_ACK = 0x79
BYTE_NOACK = 0x1F

CHIP_ID = {0x412: "STM32F Low-density",
           0x410: "STM32F Medium-density",
           0x414: "STM32F High-density",
           0x418: "STM32F Connectivity line",
           0x420: "STM32F Low/Medium-density VL",
           0x428: "STM32F High-density VL",
           0x430: "STM32F XL-density",
           0x416: "STM32L Medium-density",
           0x436: "STM32L High-density",
           0x440: "STM32F051x",
           0x411: "STM32F2xx",
           0x413: "STM32F4xx",
           0x427: "STM32L Medium-density Plus",
           0x422: "STM32F30x & F31x",
           0x432: "STM32F37x & F38x",
           0x444: "STM32F050x"} 


class STM32Protocol(AbstractProtocol):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._supported_commands = {  CMD_GET_COMMANDS: {'name': 'get', 'support': False},
                                      CMD_GET_VERSION: {'name': 'get_version', 'support': False},
                                      CMD_GET_ID: {'name': 'get_id', 'support': False},
                                      CMD_CHANGE_SPEED: {'name': 'change_speed', 'support': False},
                                      CMD_READ_MEMORY: {'name': 'read_memory', 'support': False},
                                      CMD_GO: {'name': 'go', 'support': False},
                                      CMD_WRITE_MEMORY: {'name': 'write_memory', 'support': False},
                                      CMD_ERASE: {'name': 'erase', 'support': False},
                                      CMD_WRITE_PROTECT: {'name': 'write_protect', 'support': False},
                                      CMD_WRITE_UNPROTECT: {'name': 'write_unprotect', 'support': False},
                                      CMD_READOUT_PROTECT: {'name': 'readout_protect', 'support': False},
                                      CMD_READOUT_UNPROTECT: {'name': 'readout_unprotect', 'support': False} }
    
    def _check_response(self, arb_id, dlc=None, ack_bytes=None):
        def _check_message(msg):
            if msg.arbitration_id != arb_id:
                return False
            if dlc:
                if msg.dlc != dlc:
                    return False
            if ack_bytes:
                if msg.data[0] in ack_bytes:
                    return True
                return False
            return True
        return _check_message
    
    def _check_ack(self, arb_id):
        return self._check_response(arb_id, 1, (BYTE_ACK,))
    
    def _check_byte(self, arb_id):
        return self._check_response(arb_id, 1)
    
    def _check_ack_or_noack(self, arb_id):
        return self._check_response(arb_id, 1, (BYTE_ACK, BYTE_NOACK))
    
    def _wait_for_ack(self, cmd):
        self._recv(checker=self._check_ack(cmd))
        
    def _send_data(self, cmd, data=[]):
        self._send(can.Message(arbitration_id=cmd, data=data, extended_id=False))
    
    def _init(self):
        self._send_data(CMD_INIT)
        self._recv(checker=self._check_ack_or_noack(CMD_INIT))
        
    def _recv_data(self, cmd, size=None):
        msg = self._recv(checker=self._check_response(cmd, size))
        return msg.data
        
    def _get_commands(self):
        self._send_data(CMD_GET_COMMANDS)

        self._wait_for_ack(CMD_GET_COMMANDS)
        commands_num = self._recv_data(CMD_GET_COMMANDS, 1)[0]
        boot_version = self._recv_data(CMD_GET_COMMANDS, 1)[0]
        
        commands = []
        for _ in range(commands_num):
            cmd = self._recv_data(CMD_GET_COMMANDS, 1)[0]
            commands.append(cmd)
            
        self._wait_for_ack(CMD_GET_COMMANDS)

        for k, v in self._supported_commands.items():
            v['support'] = True if k in commands else False

        self._bootloader_version = '{}.{}'.format((boot_version>>4)&0x0F, (boot_version)&0x0F)
        
    def _get_version(self):

        self._send_data(CMD_GET_VERSION)

        self._wait_for_ack(CMD_GET_VERSION)
        self._recv_data(CMD_GET_VERSION, 1)
        option_msg = self._recv_data(CMD_GET_VERSION, 2)[0:2]
        
        self._wait_for_ack(CMD_GET_VERSION)
        
        self._read_protection_bytes = '0x{}'.format(''.join(['{:02X}'.format(i) for i in option_msg]))
    
    def _get_id(self):
        self._send_data(CMD_GET_ID)

        self._wait_for_ack(CMD_GET_ID)
        chip_id = self._recv_data(CMD_GET_ID)
        self._wait_for_ack(CMD_GET_ID)
        
        self._chip_id = '0x{}'.format(''.join(['{:02X}'.format(i) for i in chip_id]))
        
    def _connect(self):
        self._init()
        log.info('Bootloader initialized')
        
        self._get_commands()       
                
        log.info('Bootloader version: {version}'.format(version=self._bootloader_version))
        
        if self._supported_commands[CMD_GET_VERSION]['support']:
            self._get_version()
                
            log.info('Read protection: {bytes}'.format(bytes=self._read_protection_bytes))
        
        if self._supported_commands[CMD_GET_ID]['support']:
    
            self._get_id()
            
            try:
                name = CHIP_ID[int(self._chip_id,0)]
            except KeyError:
                name = 'Unknown CHIP ID'
                
            log.info('Chip ID: {hexid} - {name}'.format(hexid=self._chip_id, name=name))
        
    def _disconnect(self):
        pass
    
    def _go(self, address):
        if not self._supported_commands[CMD_GO]['support']:
            raise Exception('No support GO command')
        self._send_data(CMD_GO, struct.pack(">I", address))        
        self._wait_for_ack(CMD_GO)
    
        
import threading
import socket
import logging
import struct
from select import select
import time
import argparse
import logging.config



class ConnectionClosedError(Exception):
    pass

class ConnectionTimeoutOccuredError(Exception):
    pass

class BadLengthData(Exception):
    pass

class CloseException(Exception):
    pass

class ExitException(Exception):
    pass



class MySocket(socket.socket):
    def recv(self, bufsize, *args, **kwargs):
        if 'while_timeout' in kwargs:
            while_timeout = kwargs['while_timeout']
            del kwargs['while_timeout']
        else:
            while_timeout = WHILE_TIMEOUT
        if 'timeout' in kwargs:
            timeout = kwargs['timeout']
            del kwargs['timeout']
        else:
            timeout = TIMEOUT_FOR_SOCKET_OPERATION
            
        readable = []
        if timeout != None:
            start_time = time.time()
            while time.time() <= start_time + timeout and not main_flag_to_close:
                try:
                    readable, __, __ = select([self], [], [], 0)
                except (ValueError, OSError):
                    raise CloseException
                if len(readable):
                    break
                time.sleep(while_timeout)
            if main_flag_to_close:
                raise ExitException()
        else:
            while not main_flag_to_close:
                try:
                    readable, __, __ = select([self], [], [], 0)
                except (ValueError, OSError):
                    raise CloseException
                if len(readable):
                    break
                time.sleep(while_timeout)
            if main_flag_to_close:
                raise ExitException()
        if len(readable):
            try:
                data = super().recv(bufsize, *args, **kwargs)
            except ConnectionAbortedError:
                raise ConnectionClosedError(self)
            except ConnectionResetError:
                raise ConnectionClosedError(self)
            except OSError:
                raise ConnectionClosedError(self)
            if len(data) == 0 and bufsize != 0:
                raise ConnectionClosedError(self)
            return data
        else:
            raise ConnectionTimeoutOccuredError(self, timeout)
            
    def sendall(self, data, *args, **kwargs):
        if 'timeout' in kwargs:
            timeout = kwargs['timeout']
            del kwargs['timeout']
        else:
            timeout = TIMEOUT_FOR_SOCKET_OPERATION
        try:
            old_timeout = self.gettimeout()
            self.settimeout(timeout)
            length = super().sendall(data, *args, **kwargs)
            self.settimeout(old_timeout)
            return length
        except socket.timeout:
            raise ConnectionTimeoutOccuredError(self, timeout)
        except ConnectionAbortedError:
            raise ConnectionClosedError(self)
        except ConnectionResetError:
            raise ConnectionClosedError(self)
        except OSError:
            raise ConnectionClosedError(self)
        
    def accept(self, *args, **kwargs):
        if 'while_timeout' in kwargs:
            while_timeout = kwargs['while_timeout']
            del kwargs['while_timeout']
        else:
            while_timeout = WHILE_TIMEOUT
        if 'timeout' in kwargs:
            timeout = kwargs['timeout']
            del kwargs['timeout']
        else:
            timeout = None
            
        if timeout != None:
            start_time = time.time()
            while time.time() <= start_time + timeout and not main_flag_to_close:
                try:
                    readable, __, __ = select([self], [], [], 0)
                except (ValueError, OSError):
                    raise CloseException
                if len(readable):
                    return super().accept(*args, **kwargs)
                time.sleep(while_timeout)
            if main_flag_to_close:
                raise ExitException()
            else:
                raise ConnectionTimeoutOccuredError(self, timeout)
        else:
            while not main_flag_to_close:
                try:
                    readable, __, __ = select([self], [], [], 0)
                except (ValueError, OSError):
                    raise CloseException
                if len(readable):
                    return super().accept(*args, **kwargs)
                time.sleep(while_timeout)
            raise ExitException()

class MyServiceSocket(MySocket):
    def __init__(self, *args, **kwargs):
        if 'must_equal' in kwargs:
            self.must_equal = kwargs['must_equal']
            del kwargs['must_equal']
        else:
            self.must_equal = False
        super().__init__(*args, **kwargs)
    
    def recv(self, bufsize, *args, **kwargs):
        if 'must_equal' in kwargs:
            must_equal = kwargs['must_equal']
            del kwargs['must_equal']
        else:
            must_equal = self.must_equal
            
        data = super().recv(bufsize, *args, **kwargs)
        if len(data) != bufsize and must_equal:
            raise BadLengthData(self, len(data), bufsize)
        return data
        
    def __setatrr__(self, name, value, *args, **kwargs):
        if name == 'must_equal':
            object.__setattr__(self, name, value, *args, **kwargs)
        else:
            super().__setatrr__(self, name, value, *args, **kwargs)

socket.socket = MyServiceSocket

























class Handler(threading.Thread):
    def __init__(self, service_port, service_address, allow_no_verifing, login, password, running_handlers): #
        super().__init__()
        self.deamon = True
        self.service_port = service_port
        self.service_address = service_address
        self.running_handlers = running_handlers
        self.running_handlers += [self]
        handler_index = len(self.running_handlers) - 1
        self.logger = logging.getLogger(f'Handler[{handler_index}]')
        self.login = login
        self.password = password
        self.allow_no_verifing = allow_no_verifing

    def close(self, *args, **kwargs): #
        if hasattr(self, 'service_connection'):
            self.service_connection.close()
            self.logger.debug('Service connection was closed')
        if hasattr(self, 'client_connection'):
            self.client_connection.close()
            self.logger.debug('Service socket was closed')
        self.running_handlers.remove(self)
        if 'raise_exception' in kwargs:
            if kwargs['raise_exception']:
                raise CloseException()
        else:
            raise CloseException()
        
    def run(self): #
        try:
            self.return_service_connection()
            self.verify_client()
            self.start_transferring()
            self.close()
        except CloseException:
            self.logger.debug('By CloseException', exc_info=True)
            pass
        except ConnectionClosedError:
            self.logger.debug('By ConnectionClosedError', exc_info=True)
            self.close(raise_exception=False)
        except ConnectionTimeoutOccuredError:
            self.logger.debug('By ConnectionTimeoutOccuredError', exc_info=True)
            self.close(raise_exception=False)
        except BadLengthData:
            self.logger.debug('By BadLengthData', exc_info=True)
            self.close(raise_exception=False)
        except ExitException:
            self.logger.debug('By ExitException', exc_info=True)
            pass
            
    def return_service_connection(self): #
        self.service_connection = socket.socket()
        try:
            self.service_connection.connect((self.service_address, self.service_port))
        except:
            self.close()
        self.service_connection.must_equal = True
        
    def verify_client(self): #
        nmethods = struct.unpack('B', self.service_connection.recv(1))[0]
        methods = struct.unpack('B' * nmethods, self.service_connection.recv(nmethods))
        if self.allow_no_verifing and 0 in methods:
            self.service_connection.sendall(struct.pack('B', 0))
            return
        elif 2 in methods:
            self.service_connection.sendall(struct.pack('B', 2))
            ulen, plen = struct.unpack('BB', self.service_connection.recv(2))
            login = self.service_connection.recv(ulen).decode('utf-8')
            password = self.service_connection.recv(plen).decode('utf-8')
            if login == self.login and password == self.password:
                self.service_connection.sendall(struct.pack('B', 1))
            else:
                self.service_connection.sendall(struct.pack('B', 0))
                self.logger.debug('Proxy server returned bad login or password')
                self.close()
        else:
            self.service_connection.sendall(struct.pack('B', 255))
            self.logger.debug('Proxy server returned unaccaptable verify methods ')
            self.close()
            
    def start_transferring(self): #
        cmd, atype, target_length = struct.unpack('BBB', self.service_connection.recv(3))
        if cmd == 1:
            if atype == 1:
                try:
                    target = socket.inet_ntoa(self.service_connection.recv(4))
                except:
                    self.logger.warning('Proxy server returned bad IPv4 address', exc_info=True)
                    self.close()
            elif atype == 3:
                try:
                    target = self.service_connection.recv(target_length).decode('utf-8')
                    self.logger.debug('Proxy server selected domain name as target address')
                except:
                    self.logger.debug('Some problems in decode procedure', exc_info=True)
                    self.close()
            elif atype == 4:
                self.logger.warning('Proxy server selected unsupported addressing IPv6')
                self.close()
            else:
                self.logger.warning('Proxy server selected unknown addressing')
                self.close()
            target_port = struct.unpack('H', self.service_connection.recv(2))[0]
            dst_ip, dst_port = self.return_tcp_client_connection(target, target_port)
            self.service_connection.sendall(struct.pack('B', 1))
            self.service_connection.sendall(struct.pack('BB', 1, 4) + socket.inet_pton(socket.AF_INET, dst_ip) + struct.pack('H', dst_port))
            self.CONNECT_transferring()
        elif cmd == 2:
            self.logger.warning('Proxy server select unsupported operation BIND')
            self.close()
        elif cmd == 3:
            self.logger.warning('Proxy server select unsupported operation UDP')
            self.close()
        else:
            self.logger.warning('Proxy server select unknown operation')
            self.close()

    def return_tcp_client_connection(self, target, target_port): #
        client_connection = socket.socket()
        try:
            client_connection.connect((target, target_port))
        except Exception:
            self.service_connection.sendall(struct.pack('B', 0))
            self.logger.debug(f'Didn\'t connect to {(target, target_port)}', exc_info=True)
            self.close()
        self.client_connection = client_connection
        return self.client_connection.getpeername()
        
    def CONNECT_transferring(self): #
        while True:
            try:
                readable, __, __ = select([self.client_connection], [], [], 0)
                if len(readable):
                    data = self.client_connection.recv(16384, must_equal=False)
                    self.service_connection.sendall(data)
                readable, __, __ = select([self.service_connection], [], [], 0)
                if len(readable):
                    data = self.service_connection.recv(16384, must_equal=False)
                    self.client_connection.sendall(data)
                time.sleep(WHILE_TIMEOUT_CONNECT)
            except (ValueError, OSError):
                self.logger.debug('By OSError', exc_info=True)
                raise CloseException
        
        
        
class ControllerCommandConnection(threading.Thread):
    def __init__(self, proxy_server_address, proxy_port_for_command_connection, allow_no_verifing, login, password): #
        super().__init__()
        self.flag_to_close = False
        self.proxy_server_address = proxy_server_address
        self.proxy_port_for_command_connection = proxy_port_for_command_connection
        self.allow_no_verifing = allow_no_verifing
        self.login = login
        self.password = password
        self.logger = logging.getLogger('ControllerCommandConnection')
        self.running_handlers = []
        self.deamon = True
        
    def run(self): #
        try:
            self.command_connection = socket.socket()
            while not self.flag_to_close:
                try:
                    self.command_connection.connect((self.proxy_server_address, self.proxy_port_for_command_connection))
                    break
                except ConnectionRefusedError:
                    self.logger.warning(f'Didn\'t connect to proxy server {(self.proxy_server_address, self.proxy_port_for_command_connection)}. Next attempt will be in 30 seconds')
                    start_time = time.time()
                    while not self.flag_to_close and start_time + 30 >= time.time():
                        time.sleep(1)
                except OSError:
                    self.logger.warning('Given port is not open.')
                    self.logger.debug('By OSError', exc_info=True)
                    self.close()
                    return
            if self.flag_to_close:
                return
            self.command_connection.must_equal = True
            self.logger.info('Connection to proxy server was established')
            while not self.flag_to_close:
                try:
                    service_port = struct.unpack('H', self.command_connection.recv(2, timeout=60 * 2 + 10))[0] #TIMEOUT_FOR_SOCKET_OPERATION * 2
                except CloseException:
                    self.logger.debug('By CloseException', exc_info=True)
                    break
                if service_port == 0:
                    self.command_connection.sendall(struct.pack('H', 0))
                    continue
                handler = Handler(service_port, self.proxy_server_address, self.allow_no_verifing, self.login, self.password, self.running_handlers)
                handler.start()
        except ConnectionClosedError:
            self.logger.info('Proxy server closed command connection')
            self.logger.debug('By ConnectionClosedError', exc_info=True)
            self.close()
        except ConnectionTimeoutOccuredError:
            self.logger.warning('Command connection is down')
            self.logger.debug('By ConnectionTimeoutOccuredError', exc_info=True)
            self.restart()
        except ExitException:
            self.logger.debug('By ExitException', exc_info=True)
            pass
        
    def close(self): #
        self.flag_to_close = True
        global main_flag_to_close
        main_flag_to_close = True
        while len(self.running_handlers):
            running_handler = self.running_handlers[0]
            running_handler.close(raise_exception=False)
        self.command_connection.close()
        
    def restart(self): #
        self.logger.info('Restarting')
        self.flag_to_close = True
        while len(self.running_handlers):
            running_handler = self.running_handlers[0]
            running_handler.close(raise_exception=False)
        self.command_connection.close()
        thread = ControllerCommandConnection(self.proxy_server_address, self.proxy_port_for_command_connection, self.allow_no_verifing, self.login, self.password)
        thread.start()
    
TIMEOUT_FOR_SOCKET_OPERATION = 10
    
main_flag_to_close = False
def main(proxy_server_address, proxy_port_for_command_connection, allow_no_verifing, login, password): #
    try:
        thread = ControllerCommandConnection(proxy_server_address, proxy_port_for_command_connection, allow_no_verifing, login, password)
        thread.start()
        while not main_flag_to_close:
            time.sleep(1)
    except KeyboardInterrupt:
        thread.close()
    

logging.config.fileConfig('/root/proxy_server/logging_config.ini', disable_existing_loggers=False)


parser = argparse.ArgumentParser()
parser.add_argument("-ip", dest="proxy_ip", required=True)
parser.add_argument("-port", dest="proxy_port", required=True, type=int)
parser.add_argument("-while_timeout", dest="while_timeout", required=False, type=float, default=0.01)
parser.add_argument("-while_timeout_connect", dest="while_timeout_connect", required=False, type=float, default=0.01)
parser.add_argument("--proxy_authentication", dest="proxy_authentication", action='store_true')
parser.add_argument("-proxy_username", dest="proxy_username", required=False, type=str, default='')
parser.add_argument("-proxy_password", dest="proxy_password", required=False, type=str, default='')
args = parser.parse_args()

try:
    socket.inet_aton(args.proxy_ip)
    proxy_ip = args.proxy_ip
    proxy_port = args.proxy_port
    WHILE_TIMEOUT_CONNECT = args.while_timeout_connect
    WHILE_TIMEOUT = args.while_timeout
    proxy_authentication = args.proxy_authentication
    proxy_username = args.proxy_username
    proxy_password = args.proxy_password
    
    if not (0 <= WHILE_TIMEOUT and 0 <= WHILE_TIMEOUT_CONNECT):
        logging.error('Invalid timeouts. They must be positive')
        exit()
    if not (1 >= WHILE_TIMEOUT and 1 >= WHILE_TIMEOUT_CONNECT):
        logging.warning('Timeouts are too large')
    if not (0 < proxy_port and proxy_port <= 65535):
        logging.error('Invalid port')
        exit()
    if proxy_authentication and (not proxy_username or not proxy_password):
        logging.error('Username and password are required, because you select --proxy_authentication option')
        exit()
        
    main(proxy_ip, proxy_port, not proxy_authentication, proxy_username, proxy_password)
except:
    logging.error('Invalid ip')











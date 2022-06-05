#!/usr/bin/python3
import threading
import socket
from socketserver import ThreadingTCPServer, BaseRequestHandler
import logging
import struct
from select import select
import time
from http.server import ThreadingHTTPServer
from http.server import BaseHTTPRequestHandler
import base64
import argparse
import logging.config

ThreadingTCPServer.allow_reuse_address = True

class ConnectionClosedError(Exception): #для закрытия обработчика
    pass

class ConnectionTimeoutOccuredError(Exception): #если какое-то соединение было закрыто с другой стороны
    pass

class BadLengthData(Exception): #чтобы не парится с обработкой каждой recv()
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
            
        #readable = []
        if timeout != None and timeout != 0:
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
        elif timeout == 0:
            try:
                readable, __, __ = select([self], [], [], 0)
            except (ValueError, OSError):
                raise CloseException
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





























































class SocksProxyHandler(BaseRequestHandler): #
    def close(self, *args, **kwargs):
        self.request.close()
        if hasattr(self, 'service_connection'):
            self.service_connection.close()
            self.logger.debug('Service connection is closed')
        elif hasattr(self, 'service_socket'):
            self.service_socket.close()
            self.logger.debug('Service socket is closed')
        self.server.runnings_handlers.remove(self)
        self.logger.debug('Socks5ProxyHandler was closed')
        if 'raise_exception' in kwargs:
            if kwargs['raise_exception']:
                raise CloseException()
        else:
            raise CloseException()
        
    def handle(self): #
        try:
            self.request.must_equal = True
            self.server.runnings_handlers += [self]
            self.handle_index = len(self.server.runnings_handlers) - 1
            self.logger = logging.getLogger(f'Handler[{self.server.port_for_socks_proxy}][{self.handle_index}]')
            self.logger.debug(f'Socks5ProxyHandler was started to handle client {self.client_address}')
            
            self.start_handle_request()
        except CloseException:
            self.logger.debug('By CloseException', exc_info=True)
            pass
        except ConnectionClosedError as error:
            if error.args[0] == self.server.command_connection:
                self.logger.debug('By ConnectionClosedError. Command connection was closed', exc_info=True)
            else:
                self.logger.debug('By ConnectionClosedError', exc_info=True)
            self.close(raise_exception=False)
        except ConnectionTimeoutOccuredError as error:
            if error.args[0] == self.server.command_connection:
                self.logger.debug('By ConnectionTimeoutOccuredError', exc_info=True)
                self.logger.warning('Command connection was down. Pinger will find out about it and will try to up the connection')
            else:
                self.logger.debug('By ConnectionTimeoutOccuredError', exc_info=True)
            self.close(raise_exception=False)
        except BadLengthData as error:
            if error.args[0] == self.service_connection:
                self.logger.warning('Remote server returned data whose length is bad', exc_info=True)
            else:
                self.logger.debug('By BadLengthData', exc_info=True)
            self.close(raise_exception=False)
        except ExitException:
            self.logger.debug('By ExitException', exc_info=True)
            self.close(raise_exception=False)

    def start_handle_request(self): #
        version, nmethods = struct.unpack('BB', self.request.recv(2))
        if version != 5:
            self.logger.debug('Client returned bad socks version')
            self.close()
        if nmethods == 0:
            self.logger.debug('Client provided zero number of verify methods')
            self.close()
        self.return_service_connection()
        self.verify_client(nmethods)
        self.start_transferring()
        self.close()
        
    def verify_client(self, nmethods): #
        self.service_connection.sendall(struct.pack('B', nmethods) + self.request.recv(nmethods))
        suitable_methods = struct.unpack('B', self.service_connection.recv(1))[0]
        if suitable_methods == 255:
            self.logger.debug('Remote server refused client due to unacceptable methods')
            self.close()
        elif suitable_methods == 0:
            self.request.sendall(struct.pack('BB', 5, 0))
            return
        elif suitable_methods == 2:
            self.request.sendall(struct.pack('BB', 5, 2))
            version, ulen = struct.unpack('BB', self.request.recv(2))
            if version != 1:
                self.logger.debug('Client returned bad version of verify method')
                self.close()
            b_login = self.request.recv(ulen)
            plen = struct.unpack('B', self.request.recv(1))[0]
            b_password = self.request.recv(plen)
            self.service_connection.sendall(struct.pack('BB', ulen, plen) + b_login + b_password)
            status = struct.unpack('B', self.service_connection.recv(1))[0]
            if status:
                self.request.sendall(struct.pack('BB', 1, 0))
            else:
                self.request.sendall(struct.pack('BB', 1, 1))
                self.logger.debug('Remote server returned bad status')
                self.close()
        else:
            self.logger.warning('Remote server selected not supported verify method')
            self.close()
        
    def return_service_connection(self): #
        service_socket = socket.socket()
        port = 0
        while True:
            try:
                port = select_port(port)
                service_socket.bind((PROXY_SERVER_ADDRESS, port))
                self.service_socket = service_socket
                self.service_port = port
                break
            except OSError:
                global ports_pool
                ports_pool[port] = 'is busy'
                self.logger.debug(f'Service connection didn\'t bind to port {port}', exc_info=True)
        self.service_socket.listen(0)
        self.server.command_connection.sendall(struct.pack('H', self.service_port))
        self.server.last_time_of_establish_service_connection = time.time()
        while True:
            self.service_connection, self.service_connection_address = self.service_socket.accept(timeout=TIMEOUT_FOR_SOCKET_OPERATION)
            if self.service_connection_address[0] != self.server.command_address[0]:
                self.service_connection.close()
                self.logger.debug(f'Somebody {self.service_connection_address} tried to connect to service socket instead of remote server {self.server.command_address}, but was blocked')
                continue
            self.service_socket.close()
            self.service_connection.must_equal = True
            self.logger.debug(f'Service connection {self.service_connection_address} was up.')
            return

    def start_transferring(self): #
        version, cmd, _, atype = struct.unpack('BBBB', self.request.recv(4))
        if version != 5:
            self.logger.debug('Client returned bad socks version')
            self.close()
        if atype == 1:
            b_target = self.request.recv(4)
        elif atype == 3:
            b_taget_length = struct.unpack('B', self.request.recv(1))[0] 
            b_target = self.request.recv(b_taget_length)
            self.logger.debug('Client request to connect using domain name as target address')
        elif atype == 4:
            self.request.sendall(struct.pack('BBBBHHH', 5, 5, 0, 1, 0, 0, 0))
            self.logger.debug('Client request to connect using unsupported IPv6')
            self.close()
        else:
            self.logger.debug('Client request to connect using unknown addressing')
            self.close()
        b_target_port = self.request.recv(2)[::-1]
        if cmd == 1:
            self.service_connection.sendall(struct.pack('BBB', cmd, atype, len(b_target)) + b_target + b_target_port)
            status = struct.unpack('B', self.service_connection.recv(1))[0]
            if not status:
                self.request.sendall(struct.pack('BBBBHHH', 5, 5, 0, 1, 0, 0, 0))
                self.logger.debug('Remote server returned bad status')
                self.close()
            atype = struct.unpack('B', self.service_connection.recv(1))[0]
            b_dst_length = struct.unpack('B', self.service_connection.recv(1))[0]
            if atype == 1:
                b_dst = self.service_connection.recv(4)
                b_dst_port = self.service_connection.recv(2)
                self.request.sendall(struct.pack('BBBB', 5, 0, 0, atype) + b_dst + b_dst_port[::-1])
            elif atype == 4:
                self.logger.warning('Remote server selected unsupported addressing IPv6')
                self.request.sendall(struct.pack('BBBBHHH', 5, 5, 0, 1, 0, 0, 0))
                self.close()
            else:
                self.logger.warning(f'Remote server select unknown addressing')
                self.request.sendall(struct.pack('BBBBHHH', 5, 5, 0, 1, 0, 0, 0))
                self.close()
            self.CONNECT_transferring()
        elif cmd == 2:
            self.logger.debug('Client select unsupported operation BIND')
            self.close()
        elif cmd == 3:
            self.logger.debug('Client select unsupported operation UDP')
            self.close()
        else:
            self.logger.debug('Client select unknown operation')
            self.close()
            
    def CONNECT_transferring(self): #
        while True:
            try:
                readable, __, __ = select([self.request], [], [], 0)
                if len(readable):
                    data = self.request.recv(16384, must_equal=False)
                    self.service_connection.sendall(data)
                readable, __, __ = select([self.service_connection], [], [], 0)
                if len(readable):
                    data = self.service_connection.recv(16384, must_equal=False)
                    self.request.sendall(data)
                time.sleep(WHILE_TIMEOUT_CONNECT)
            except (ValueError, OSError):
                self.logger.debug('Some error was happened', exc_info=True)
                raise CloseException
                

class SocksProxy(ThreadingTCPServer):
    def __init__(self, port_for_socks_proxy, command_connection, command_address):
        super().__init__((PROXY_SERVER_ADDRESS, port_for_socks_proxy), SocksProxyHandler)
        self.runnings_handlers = []
        self.daemon_threads = True
        self.logger = logging.getLogger(f'Socks5Proxy[{port_for_socks_proxy}]')
        self.port_for_socks_proxy = port_for_socks_proxy
        self.command_connection = command_connection
        self.command_address = command_address
        self.logger.info('Starting Socks5Proxy')
        global running_socks_proxies_and_pingers
        running_socks_proxies_and_pingers[self.port_for_socks_proxy] += [self]
        
    def close(self):
        self.shutdown()
        while len(self.runnings_handlers):
            running_handler = self.runnings_handlers[0]
            running_handler.close(raise_exception=False)
        self.command_connection.close() 
        self.server_close()
        self.logger.info('Socks5Proxy was closed')
        global running_socks_proxies_and_pingers
        running_socks_proxies_and_pingers[self.port_for_socks_proxy].remove(self)



class Pinger(threading.Thread):
    def __init__(self, port_for_socks_proxy, command_connection, command_address, port_for_command_connection): #
        super().__init__()
        self.deamon = True
        self.logger = logging.getLogger(f'Pinger[{port_for_socks_proxy}]')
        self.port_for_socks_proxy = port_for_socks_proxy
        self.command_connection = command_connection
        self.command_address = command_address
        self.port_for_command_connection = port_for_command_connection
        self.logger.info('Starting Pinger')
        global running_socks_proxies_and_pingers
        running_socks_proxies_and_pingers[self.port_for_socks_proxy] += [self]
        
    def close(self): #
        self.logger.info('Pinger was closed')
        global running_socks_proxies_and_pingers
        running_socks_proxies_and_pingers[self.port_for_socks_proxy].remove(self)
        self.command_connection.close()

    def run(self): #
        try:
            while not main_flag_to_close:
                self.command_connection.sendall(struct.pack('H', 0), timeout=60)
                timeout_for_recv = 60 #= TIMEOUT_FOR_SOCKET_OPERATION
                try:
                    self.command_connection.recv(1024, timeout=timeout_for_recv) #self.socks_proxy.last_time_of_establish_service_connection
                except ConnectionTimeoutOccuredError:
                    if time.time() - self.socks_proxy.last_time_of_establish_service_connection > timeout_for_recv:
                        raise
                    self.logger.info('Handlers take too much thread time')
                timeout = 60 #= TIMEOUT_FOR_SOCKET_OPERATION
                start_time = time.time()
                while not main_flag_to_close and start_time + timeout >= time.time():
                    time.sleep(1)
            raise ExitException()
        except CloseException:
            self.logger.debug('By CloseException', exc_info=True)
            pass
        except ConnectionTimeoutOccuredError:
            self.logger.warning('Command connection is down', exc_info=True)
            close_all(self.port_for_socks_proxy)      
        except ConnectionClosedError:
            self.logger.debug('Remote server closed command connection', exc_info=True)
            close_all(self.port_for_socks_proxy)  
        except ExitException:
            self.logger.debug('By ExitException', exc_info=True)
            pass

class StartThreadForSocksProxy(threading.Thread):
    def __init__(self, port_for_command_connection): #
        super().__init__()
        self.logger = logging.getLogger(f'StarterSocks5Proxies')
        self.command_socket = socket.socket()
        try:
            self.command_socket.bind((PROXY_SERVER_ADDRESS, port_for_command_connection))
        except OSError:
            self.logger.error(f'Gaven port is busy {port_for_command_connection}, wait for few seconds, possibly OS will release port')
            self.logger.debug(f'By OSerror', exc_info=True)
            raise
        self.command_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.command_socket.listen(0)
        self.port_for_command_connection = port_for_command_connection
        self.deamon = True
        
    def run(self): #
        while not main_flag_to_close:
            self.logger.info('Waiting for remote server connection')
            try:
                self.command_connection, self.command_address = self.command_socket.accept()
            except ExitException:
                self.logger.debug('By ExitException', exc_info=True)
                return
            except CloseException:
                self.logger.debug('By CloseException', exc_info=True)
                return
            #self.command_connection.must_equal=True
            port_for_socks_proxy = 0
            while not main_flag_to_close:
                try:
                    port_for_socks_proxy = select_port(port_for_socks_proxy)
                    self.start_socks_proxy_server(port_for_socks_proxy)
                    self.start_pinger(port_for_socks_proxy)
                    self.logger.info(f'Socks5Proxy was started at {port_for_socks_proxy} port')
                    break
                except OSError:
                    global ports_pool
                    ports_pool[port_for_socks_proxy] = 'is busy'
                    self.logger.debug(f'Service connection didn\'t bind to port {port}', exc_info=True)
            
        
    def start_socks_proxy_server(self, port_for_socks_proxy): #
        self.logger.info('Initialization Socks5Proxy')
        global running_socks_proxies_and_pingers
        running_socks_proxies_and_pingers[port_for_socks_proxy] = []
        try:
            self.socks_proxy = SocksProxy(port_for_socks_proxy, self.command_connection, self.command_address)
            self.socks_proxy.last_time_of_establish_service_connection = time.time()
        except OSError:
            self.logger.info('Initialization Socks5Proxy is fail')
            self.logger.debug('BY OSError', exc_info=True)
            raise
        thread = threading.Thread(target=self.socks_proxy.serve_forever, args=tuple())
        thread.start()
        
    def start_pinger(self, port_for_socks_proxy): #
        self.pinger = Pinger(port_for_socks_proxy, self.command_connection, self.command_address, self.port_for_command_connection)
        self.pinger.socks_proxy = self.socks_proxy
        self.pinger.start()
        
    def close(self): #
        self.logger.info('Closing')
        self.command_socket.close()
        time.sleep(1)
        
        
        
        
        
class MyHTTPServer(ThreadingHTTPServer):
    def __init__(self, *args, **kwargs): #
        self.runnings_handlers = []
        self.logger = logging.getLogger('HTTPServer')
        self.daemon_threads = True
        if '_username' not in kwargs or '_password' not in kwargs:
            self.logger.error('Username and password are needed')
            close_all()
            return
        _username = kwargs.pop('_username')
        _password = kwargs.pop('_password')
        self.set_auth(_username, _password)
        
        try:
            super().__init__(*args, **kwargs)
        except OSError:
            self.logger.error('Gaven port is busy, wait for few seconds, possibly OS will release port')
            self.logger.debug(f'Service connection didn\'t bind to port {port}', exc_info=True)
            raise
    
    def close(self): #
        self.shutdown()
        while len(self.runnings_handlers):
            running_handler = self.runnings_handlers[0]
            running_handler.close() #raise_exception=False
        self.server_close()
        self.logger.info('HTTPServer was closed')
        
    def serve_forever(self, *args, **kwargs): # #если че выпилить
        try:
            super().serve_forever(*args, **kwargs)
        except ExitException:
            self.logger.debug('By ExitException', exc_info=True)
            return
        
    def set_auth(self, username, password):
        self.key = base64.b64encode(bytes('%s:%s' % (username, password), 'utf-8')).decode('ascii')
        
    
class MyHTTPHandler(BaseHTTPRequestHandler): #
    def close(self):
        self.request.close()
        self.server.runnings_handlers.remove(self)

    def do_GET(self): #
        self.logger = logging.getLogger('HTTPHandler')
        self.server.runnings_handlers += [self]
        
        key = self.server.key
        
        if self.headers.get('Authorization') == None:
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="Demo Realm"')
            #self.send_header('Content-type', 'text/html')
            #self.wfile.write(''.encode())
            self.end_headers()
            self.close()
        elif self.headers.get('Authorization') == 'Basic ' + str(key):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            
            if self.path != '/del_remote_server':
                self.wfile.write('<html><head><meta charset="utf-8">'.encode())
                self.wfile.write('<title>Панель контроля</title></head>'.encode())
                self.wfile.write('<body>'.encode())
                self.wfile.write('''
                                <script>
                                document.addEventListener("click", function(event){
                                    var el = event.target
                                    if (el.type == "button"){
                                        var socks_port = el.id;
                                        var x = new XMLHttpRequest();
                                        x.open("GET", "/del_remote_server", true);
                                        x.setRequestHeader("socks_port", socks_port.slice(1));
                                        x.onload = function (){
                                            if (x.response == 'good'){
                                                var table = el.parentElement.parentElement.parentElement;
                                                var raw = el.parentElement.parentElement;
                                                raw.children[3].removeChild(el);
                                                for (let i = 0; i < raw.children.length; i++) {
                                                    raw.removeChild(raw.children[i]);
                                                }
                                                table.removeChild(raw);
                                                alert("Клиент с соскс портом " + socks_port.slice(1) + " был отключен");
                                            }else if (x.response == "not exist"){
                                                var table = el.parentElement.parentElement.parentElement;
                                                var raw = el.parentElement.parentElement;
                                                raw.children[3].removeChild(el);
                                                for (let i = 0; i < raw.children.length; i++) {
                                                    raw.removeChild(raw.children[i]);
                                                }
                                                table.removeChild(raw);
                                                alert("Клиент с соскс портом " + socks_port.slice(1) + " был не удален, так как не существует. Скорее всего он отключился раньше, чем была сделана попытка его отключения");
                                            }else{
                                                alert("Проблемы с сервером");
                                            }
                                        }
                                        x.onerror = function() {
                                            alert("Ошибка соединения");
                                        };
                                        x.send();
                                    }
                                });
                                </script>        
                                '''.encode())
                self.wfile.write('<table border="1px">'.encode())
                self.wfile.write('<tr>'.encode())
                self.wfile.write(f'<td>Номер в списке</td><td>Адрес клиента</td><td>Порт сокс сервера</td><td></td>'.encode())
                self.wfile.write('</tr>'.encode())
                i = 0
                for socks_port in running_socks_proxies_and_pingers:
                    if not len(running_socks_proxies_and_pingers[socks_port]):
                        continue
                    remote_server_address = running_socks_proxies_and_pingers[socks_port][0].command_address
                    self.wfile.write(f'<tr>'.encode())
                    self.wfile.write(f'<td>{i + 1}</td><td>{remote_server_address[0]}</td><td>{socks_port}</td><td><input id="P{socks_port}" type="button" value="Отключить клиента"></td>'.encode())
                    self.wfile.write('</tr>'.encode())
                    i += 1
                self.wfile.write('</table>'.encode())
                self.wfile.write('</body></html>'.encode())
            else:
                try:
                    port = int(self.headers['socks_port'])
                    try:
                        if port in running_socks_proxies_and_pingers:
                            if len(running_socks_proxies_and_pingers[port]):
                                close_all(port)
                                self.wfile.write('good'.encode())
                            else:
                                self.wfile.write('not exist'.encode())
                        else:
                            self.wfile.write('not exist'.encode())
                    except KeyError:
                        self.wfile.write('not exist'.encode())
                except Exception as error:
                    self.logger.debug('Some error in taking port operation', exc_info=True)
            self.close()
        else:
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="Demo Realm"')
            #self.send_header('Content-type', 'text/html')
            #self.wfile.write(''.encode())
            self.end_headers()
            self.close()
        time.sleep(1)
        
        
        
        
        
        
        
#нежелательно редактировать
TIMEOUT_FOR_SOCKET_OPERATION = 10

def select_port(port_=0): #
    global ports_pool
    while True:
        for port, value in ports_pool.items():
            if value == None:
                ports_pool[port] = True
                return port
        for port, value in ports_pool.items():
            if not value:
                ports_pool[port] = True
                return port
            
        for port, value in ports_pool.items():
            if value == 'is busy' and port_ < port:
                ports_pool[port] = True
                return port
        logging.warning('Ports pool is exhausted')
        port_ = 0
    
    
    

running_socks_proxies_and_pingers = {}
main_flag_to_close = False
main_starter = None
http_server = None
def start_all(port_for_command_socket): #
    try:
        logging.info('Start')
        try:
            global main_starter
            main_starter = StartThreadForSocksProxy(port_for_command_socket)
        except OSError:
            logging.info('Closing')
            return
        try:
            global http_server
            http_server = MyHTTPServer((HTTP_SERVER_ADDRESS, HTTP_PORT), MyHTTPHandler, _username=HTTP_USERNAME, _password=HTTP_PASSWORD)
            http_server.allow_reuse_address = True
        except OSError:
            logging.info('Closing')
            main_starter.close()
            return
        thread = threading.Thread(target=http_server.serve_forever, args=tuple())
        main_starter.start()
        thread.start()
        while not main_flag_to_close:
            time.sleep(1)
    except KeyboardInterrupt:
        close_all()
    
def close_all(*args): #
    if len(args):
        for port_for_socks_proxy in args:
            runnings = running_socks_proxies_and_pingers[port_for_socks_proxy]
            while len(runnings):
                running = runnings[0]
                running.close()
            global ports_pool
            ports_pool[port_for_socks_proxy] = None
    else:
        logging.info('Closing, wait for few seconds. If program will not close, press CTRL+C again few time. If it not helped you, kill process')
        global main_flag_to_close
        if not main_flag_to_close:
            main_flag_to_close = True
            for port_for_socks_proxy, runnings in running_socks_proxies_and_pingers.items():
                while len(runnings):
                    running = runnings[0]
                    running.close()
            main_starter.close()
            if hasattr(http_server, 'key'):
                http_server.close()
    
PROXY_SERVER_ADDRESS = '0.0.0.0'


logging.config.fileConfig('/root/proxy_server/logging_config.ini', disable_existing_loggers=False)

parser = argparse.ArgumentParser()
parser.add_argument("-http_port", dest="http_port", required=True, type=int)
parser.add_argument("-client_port", dest="client_port", required=True, type=int)
parser.add_argument("-first_pool_port", dest="first_pool_port", default=2000, type=int)
parser.add_argument("-last_pool_port", dest="last_pool_port", default=65500, type=int)
parser.add_argument("-while_timeout", dest="while_timeout", required=False, type=float, default=0.01)
parser.add_argument("-while_timeout_connect", dest="while_timeout_connect", required=False, type=float, default=0.01)
parser.add_argument("--localhost", dest="only_localhost", action='store_true')
parser.add_argument("-http_username", dest="http_username", required=True, type=str)
parser.add_argument("-http_password", dest="http_password", required=True, type=str)

args = parser.parse_args()

http_port = args.http_port
client_port = args.client_port
first_pool_port = args.first_pool_port
last_pool_port = args.last_pool_port
only_localhost = args.only_localhost

WHILE_TIMEOUT_CONNECT = args.while_timeout_connect
WHILE_TIMEOUT = args.while_timeout

HTTP_USERNAME = args.http_username
HTTP_PASSWORD = args.http_password
print(HTTP_USERNAME, HTTP_PASSWORD)
p = True
if not (0 < http_port and http_port <= 65535):
    logging.error('Invalid http_port')
    p = False
if not (0 < client_port and client_port <= 65535):
    logging.error('Invalid client_port')
    p = False
if not (0 < first_pool_port and first_pool_port <= 65535):
    logging.error('Invalid first_pool_port')
    p = False
if not (0 < last_pool_port and last_pool_port <= 65535):
    logging.error('Invalid last_pool_port')
    p = False
if not (first_pool_port < last_pool_port and last_pool_port - first_pool_port + 1 >= 1000):
    logging.error('Invalid range of ports pool: range must be more than 1000 and first_pool_port < last_pool_port')
    p = False

if not (0 <= WHILE_TIMEOUT and 0 <= WHILE_TIMEOUT_CONNECT):
    logging.error('Invalid timeouts. They must be positive')
    p = False
if not (1 >= WHILE_TIMEOUT and 1 >= WHILE_TIMEOUT_CONNECT):
    logging.warning('Timeouts are too large')

if only_localhost:
    HTTP_SERVER_ADDRESS = 'localhost'
else:
    HTTP_SERVER_ADDRESS = PROXY_SERVER_ADDRESS

if p:
    HTTP_PORT = http_port
    
    FIRTS_FREE_PORT = first_pool_port
    LAST_FREE_PORT = last_pool_port
    
    ports_pool = {port:False for port in range(FIRTS_FREE_PORT, LAST_FREE_PORT + 1)}
    start_all(client_port)


        

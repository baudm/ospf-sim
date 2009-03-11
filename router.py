# -*- coding: utf-8 -*-

import socket
import asyncore
import asynchat
from threading import Timer
try:
    import cPickle as pickle
except ImportError:
    import pickle

import ospf


hello_interval = 5 # 5 seconds


class Router(object):

    def __init__(self, name):
        self.name = name
        self.table = RoutingTable()
        self.lsdb = ospf.Database()
        self.timers = {}
        self.interfaces = {}

    def iface_create(self, name, bandwidth, port):
        self.interfaces[name] = Interface(name, bandwidth, port, self.lsdb)

    def iface_config(self, name, address, netmask, host, port):
        iface = self.interfaces[name]
        iface.address = address
        iface.netmask = netmask
        iface.remote_node = (host, port)

    def start(self):
        # Establish adjacency
        self.hello()
        asyncore.loop()

    def stop(self):
        for t in self.timers.values():
            t.cancel()
        for iface in self.interfaces.values():
            iface.handle_close()

    def hello(self):
        """Simple neighbor reachability check"""
        t = Timer(hello_interval, self.hello)
        self.timers['hello'] = t
        t.start()
        for iface in self.interfaces.values():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.connect(iface.remote_node)
            except socket.error:
                print '%s %s neighbor down' % (self.name, iface.name)
                # remove entry from lsdb
            else:
                # update lsdb
                print '%s %s neighbor up' % (self.name, iface.name)
            finally:
                s.close()

    def advertise(self):
        # for each neighbor in self.lsdb
        # send ospf.Packet()
        pass


class Interface(asyncore.dispatcher):
    """Physical Router interface"""

    def __init__(self, name, bandwidth, port, lsdb):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('', port))
        self.listen(1)
        self.name = name
        self.bandwidth = bandwidth
        self.lsdb = lsdb
        self.address = None
        self.netmask = None
        self.remote_node = None
        self.connections = {}
        self.log('%s up.' % (self.name, ))

    @staticmethod
    def writable():
        return False

    def handle_close(self):
        self.close()
        for conn in self.connections.values():
            conn.handle_close()
        self.log('%s down.' % (self.name, ))

    def handle_accept(self):
        conn, addr = self.accept()
        #self.log('Connection accepted: %s' % (addr, ))
        # Dispatch connection to a Channel
        Channel(self.lsdb, self.log, self.connections, conn)



class Channel(asynchat.async_chat):

    ac_in_buffer_size = 512
    ac_out_buffer_size = 512

    def __init__(self, lsdb, log, connections, conn):
        asynchat.async_chat.__init__(self, conn)
        self.add_channel(connections)
        self.set_terminator('\r\n')
        self.lsdb = lsdb
        self.log = log
        self.connections = connections
        self.buffer = []

    def collect_incoming_data(self, data):
        self.buffer.append(data)

    def found_terminator(self):
        data = ''.join(self.buffer)
        self.buffer = []
        entry = pickle.loads(data)
        self.lsdb.update(entry)

    def handle_close(self):
        del self.connections[self._fileno]
        self.close()
        #self.log('Connection closed: %s' % (self.addr, ))


class Route(object):

    def __init__(self, dest, next, cost):
        self.dest = dest
        self.next_hop = next
        self.cost = cost


class RoutingTable(list):

    def __repr__(self):
        routes = ['Dest\tNext Hop\tCost']
        for r in self:
            routes.append("%s\t%s\t%.2f" % (r.dest, r.next_hop, r.cost))
        return '\n'.join(routes)

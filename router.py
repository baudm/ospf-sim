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
        self.lsdb = ospf.Database(10, 3)
        self.timers = {}
        self.interfaces = {}
        self.neighbors = {}
        self.retransmission_list = []

    def __del__(self):
        self.stop()

    def iface_create(self, name, bandwidth, port):
        if name not in self.interfaces:
            self.interfaces[name] = Interface(name, bandwidth, port, self.lsdb)

    def iface_config(self, name, address, netmask, host, port):
        iface = self.interfaces[name]
        iface.address = address
        iface.netmask = netmask
        iface.remote_end = (host, port)

    def start(self):
        # Establish adjacency
        self.hello()
        asyncore.loop()

    def stop(self):
        self.lsdb.cleanup()
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
            if iface.name not in self.neighbors:
                self.neighbors[iface.name] = False
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.connect(iface.remote_end)
            except socket.error:
                #print '%s %s neighbor down' % (self.name, iface.name)
                if self.neighbors[iface.name]:
                    self.retransmission_list.append(iface.name)
                self.neighbors[iface.name] = False
            else:
                # FIXME: send request to get router id
                if not self.neighbors[iface.name]:
                    self.retransmission_list.append(iface.name)
                self.neighbors[iface.name] = True
                #print '%s %s neighbor up' % (self.name, iface.name)
            finally:
                s.close()
        # Advertise any changes
        self.advertise()

    def advertise(self):
        if not self.retransmission_list:
            return
        neighbors = {}
        for iface in self.interfaces.values():
            if self.neighbors[iface.name]:
                cost = ospf.bandwidth_base / float(iface.bandwidth)
                neighbors[iface.address + '.0'] = cost # FIXME: this should be the router id
        for iface in self.interfaces.values():
            if not self.neighbors[iface.name]:
                continue
            if iface.address in self.lsdb:
                lsa = self.lsdb[iface.address]
                lsa.seq_no += 1
                lsa.neighbors = neighbors
            else:
                lsa = ospf.LsaPacket(iface.address, 1, 1, neighbors)
            iface.transmit(lsa)
        self.retransmission_list = []


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
        self.remote_end = None
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
        # Dispatch connection to a IfaceRx
        IfaceRx(self.lsdb, self.log, self.connections, conn)

    def transmit(self, lsa):
        tx = IfaceTx(self.log, self.connections)
        tx.connect(self.remote_end)
        data = pickle.dumps(lsa)
        tx.push(''.join([data, '\r\n\r\n']))


class IfaceTx(asynchat.async_chat):

    #ac_in_buffer_size = 512
    #ac_out_buffer_size = 512

    def __init__(self, log, connections):
        asynchat.async_chat.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.add_channel(connections)
        self.log = log
        self.connections = connections

    @staticmethod
    def handle_connect():
        return

    def handle_close(self):
        del self.connections[self._fileno]
        self.close()


class IfaceRx(asynchat.async_chat):

    #ac_in_buffer_size = 512
    #ac_out_buffer_size = 512

    def __init__(self, lsdb, log, connections, conn):
        asynchat.async_chat.__init__(self, conn)
        self.add_channel(connections)
        self.set_terminator('\r\n\r\n')
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
        print self.lsdb
        self.handle_close()

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

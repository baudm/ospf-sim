# -*- coding: utf-8 -*-

import socket
import asyncore
import asynchat
try:
    import cPickle as pickle
except ImportError:
    import pickle

import ospf


class Router(asyncore.dispatcher):

    def __init__(self, router_id, port):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('', port))
        self.listen(1)
        self.router_id = router_id
        self.table = RoutingTable()
        self.lsdb = ospf.Database()
        self.neighbors = {}

    def writable(self):
        return False

    def handle_close(self):
        self.close()
        for channel in asyncore.socket_map.values():
            channel.handle_close()
        self.log('Server closed.')

    def handle_accept(self):
        conn, addr = self.accept()
        self.log('Connection accepted: %s' % (addr, ))
        # Dispatch connection to a Channel
        Channel(self.lsdb, self.log, conn)

    def start(self):
        self.log(repr(self))
        # Establish adjacency
        self.hello()
        asyncore.loop()

    def stop(self):
        self.handle_close()

    def add_neighbor(self, host, port, bandwidth):
        neighbor = (host, port, bandwidth)
        self.neighbors[id(neighbor)] = neighbor

    def hello(self):
        """Simple neighbor reachability check"""
        for idx, neighbor in self.neighbors.iteritems():
            host, port, bandwidth = neighbor
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.connect((host, port))
            except socket.error:
                # remove entry from lsdb
                pass
            else:
                # update lsdb
                pass

    def advertise(self):
        # for each neighbor in self.lsdb
        # send ospf.Packet()
        pass


class Channel(asynchat.async_chat):

    ac_in_buffer_size = 512
    ac_out_buffer_size = 512

    def __init__(self, lsdb, log, conn):
        asynchat.async_chat.__init__(self, conn)
        self.set_terminator('\r\n')
        self.buffer = []
        self.lsdb = lsdb
        self.log = log

    def collect_incoming_data(self, data):
        self.buffer.append(data)

    def found_terminator(self):
        data = ''.join(self.buffer)
        self.buffer = []
        entry = pickle.loads(data)
        self.lsdb.update(entry)

    def handle_close(self):
        self.close()
        self.log('Connection closed: %s' % (self.addr, ))


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

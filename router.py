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


_terminator = '\0E\0O\0F\0'


class Router(object):

    def __init__(self, hostname):
        self.hostname = hostname
        self.table = RoutingTable()
        self.lsdb = ospf.Database()
        self.timers = {}
        self.interfaces = {}
        self.neighbors = {}

    def __del__(self):
        self.stop()

    def _update_lsdb(self):
        t = Timer(ospf.AGE_INTERVAL, self._update_lsdb)
        t.start()
        self.timers['lsdb'] = t
        self.lsdb.update()

    def _refresh_ls(self):
        t = Timer(ospf.LS_REFRESH_TIME, self._refresh_ls)
        t.start()
        self.timers['refresh_ls'] = t
        if self.hostname in self.lsdb:
            print 'Refreshing LSA'
            lsa = self.lsdb[self.hostname]
            # reset age
            lsa.age = 1
            # and flood to network
            self.advertise()

    def iface_create(self, name, bandwidth, port):
        if name not in self.interfaces:
            self.interfaces[name] = Interface(name, bandwidth, port, self)

    def iface_config(self, name, address, netmask, host, port):
        iface = self.interfaces[name]
        iface.address = address
        iface.netmask = netmask
        iface.remote_end = (host, port)

    def start(self):
        # Bootstrap processes
        self._update_lsdb()
        self._refresh_ls()
        self.hello()
        # start asyncore framework
        asyncore.loop()

    def stop(self):
        for t in self.timers.values():
            t.cancel()
        for iface in self.interfaces.values():
            iface.handle_close()

    def hello(self):
        """Establish adjacency"""
        for iface in self.interfaces.values():
            packet = ospf.HelloPacket(self.hostname, iface.address, iface.netmask)
            iface.transmit(packet)
        t = Timer(ospf.HELLO_INTERVAL, self.hello)
        t.start()
        self.timers['hello'] = t

    def remove_neighbor(self, neighbor_id):
        del self.timers[neighbor_id]
        del self.neighbors[neighbor_id]
        print neighbor_id, 'is down'
        self.advertise()

    def flood(self, source_iface, packet):
        """Flood received packet to other interfaces"""
        print 'Flooding LSA received from %s' % (source_iface, )
        interfaces = self.interfaces.keys()
        interfaces.remove(source_iface)
        for iface_name in interfaces:
            self.interfaces[iface_name].transmit(packet)

    def advertise(self):
        neighbors = {}
        for neighbor_id, iface_name in self.neighbors.iteritems():
            iface = self.interfaces[iface_name]
            cost = ospf.BANDWIDTH_BASE / float(iface.bandwidth)
            neighbors[neighbor_id] = cost
        # Create new or update existing LSA
        if self.hostname in self.lsdb:
            lsa = self.lsdb[self.hostname]
            lsa.seq_no += 1
            lsa.neighbors = neighbors
        else:
            lsa = ospf.LinkStatePacket(self.hostname, 1, 1, neighbors)
        self.lsdb.insert(lsa)
        # Flood LSA to neighbors
        for iface_name in self.neighbors.values():
            iface = self.interfaces[iface_name]
            iface.transmit(lsa)


class Interface(asyncore.dispatcher):
    """Physical Router interface"""

    def __init__(self, name, bandwidth, port, router):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('', port))
        self.listen(1)
        self.name = name
        self.bandwidth = bandwidth
        self.router = router
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
        IfaceRx(self.router, self.name, self.connections, conn)

    def transmit(self, packet):
        """Transmit a packet through the interface"""
        tx = IfaceTx(self.remote_end, self.connections)
        # Serialize packet
        data = pickle.dumps(packet)
        # Push data to remote end
        tx.push(''.join([data, _terminator]))


class IfaceTx(asynchat.async_chat):

    ac_in_buffer_size = 0
    ac_out_buffer_size = 2048

    def __init__(self, address, connections):
        asynchat.async_chat.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.add_channel(connections)
        self.connect(address)
        self.connections = connections

    def handle_error(self):
        self.close()

    @staticmethod
    def handle_connect():
        return

    def handle_close(self):
        if self._fileno in self.connections:
            del self.connections[self._fileno]
        self.close()


class IfaceRx(asynchat.async_chat):

    ac_in_buffer_size = 2048
    ac_out_buffer_size = 2048

    def __init__(self, router, name, connections, conn):
        asynchat.async_chat.__init__(self, conn)
        self.add_channel(connections)
        self.set_terminator(_terminator)
        self.router = router
        self.iface_name = name
        self.connections = connections
        self.buffer = []

    def collect_incoming_data(self, data):
        self.buffer.append(data)

    def found_terminator(self):
        data = ''.join(self.buffer)
        self.buffer = []
        # Deserialize packet
        packet = pickle.loads(data)
        if isinstance(packet, ospf.HelloPacket):
            if packet.router_id in self.router.timers:
                self.router.timers[packet.router_id].cancel()
            t = Timer(ospf.DEAD_INTERVAL, self.router.remove_neighbor, args=(packet.router_id, ))
            t.start()
            self.router.timers[packet.router_id] = t
            self.router.neighbors[packet.router_id] = self.iface_name
            # Advertise LSA if there are changes
            if self.router.hostname in self.router.lsdb:
                lsdb_neighbors = self.router.lsdb[self.router.hostname].neighbors.keys()
                lsdb_neighbors.sort()
                current_neighbors = self.router.neighbors.keys()
                current_neighbors.sort()
                if lsdb_neighbors != current_neighbors:
                    print 'network topology changed'
                    self.router.advertise()
            else:
                print 'network topology changed'
                self.router.advertise()
        elif isinstance(packet, ospf.LinkStatePacket):
            print 'Received LSA from %s' % (packet.adv_router)
            #print packet
            # Insert to Link State database
            self.router.lsdb.insert(packet)
            self.router.flood(self.iface_name, packet)
        self.handle_close()
        print self.router.lsdb.values()
        print '\n'

    def handle_close(self):
        if self._fileno in self.connections:
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

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

def get_network_address(addr, netmask):
    addr = addr.split('.')
    netmask = netmask.split('.')
    netadd = []
    for i in xrange(4):
        netadd.append(str(int(addr[i]) & int(netmask[i])))
    return '.'.join(netadd)


class Router(object):

    def __init__(self, hostname):
        self._hostname = hostname
        self._table = RoutingTable()
        self._lsdb = ospf.Database()
        self._timers = {}
        self._interfaces = {}
        self._neighbors = {}

    def __del__(self):
        self.stop()

    def _update_lsdb(self):
        self._lsdb.update()
        # Reschedule
        t = Timer(ospf.AGE_INTERVAL, self._update_lsdb)
        t.start()
        self._timers['lsdb'] = t

    def _refresh_lsa(self):
        if self._hostname in self._lsdb:
            print 'Refreshing LSA'
            lsa = self._lsdb[self._hostname]
            # reset age
            lsa.age = 1
            # and flood to network
            self._advertise()
        # Reschedule
        t = Timer(ospf.LS_REFRESH_TIME, self._refresh_lsa)
        t.start()
        self._timers['refresh_lsa'] = t

    def _hello(self):
        """Establish adjacency"""
        for iface in self._interfaces.values():
            packet = ospf.HelloPacket(self._hostname, iface.address, iface.netmask)
            iface.transmit(packet)
        # Reschedule
        t = Timer(ospf.HELLO_INTERVAL, self._hello)
        t.start()
        self._timers['hello'] = t

    def _update_routing_table(self):
        self._table = RoutingTable()
        for path in self._lsdb.get_shortest_paths(self._hostname):
            next_hop, before_dest, dest, cost = path
            iface, gateway = self._lsdb[self._hostname].neighbors[next_hop][:2]
            dest_addr, netmask = self._lsdb[before_dest].neighbors[dest][1:3]
            dest_net = get_network_address(dest_addr, netmask)
            r = Route(dest_net, gateway, netmask, cost, iface)
            self._table.append(r)
        print self._table

    def _break_adjacency(self, neighbor_id):
        del self._timers[neighbor_id]
        del self._neighbors[neighbor_id]
        print neighbor_id, 'is down'
        self._advertise()

    def _flood(self, packet, source_iface=None):
        """Flood received packet to other interfaces"""
        interfaces = []
        for data in self._neighbors.values():
            interfaces.append(data[0])
        if source_iface in interfaces:
            print 'Flooding LSA received from %s' % (source_iface, )
            interfaces.remove(source_iface)
        else:
            print 'Flooding LSA originating from self'
        for iface_name in interfaces:
            iface = self._interfaces[iface_name]
            iface.transmit(packet)

    def _advertise(self):
        neighbors = {}
        for neighbor_id, data in self._neighbors.iteritems():
            iface_name, address, netmask = data
            iface = self._interfaces[iface_name]
            cost = ospf.BANDWIDTH_BASE / float(iface.bandwidth)
            neighbors[neighbor_id] = (iface_name, address, netmask, cost)
        # Create new or update existing LSA
        if self._hostname in self._lsdb:
            lsa = self._lsdb[self._hostname]
            lsa.seq_no += 1
            lsa.neighbors = neighbors
        else:
            lsa = ospf.LinkStatePacket(self._hostname, 1, 1, neighbors)
        self._lsdb.insert(lsa)
        # Flood LSA to neighbors
        self._flood(lsa)
        # Update routing table
        self._update_routing_table()

    def iface_create(self, name, bandwidth, port):
        if name not in self._interfaces:
            self._interfaces[name] = Interface(name, bandwidth, port, self)

    def iface_config(self, name, address, netmask, host, port):
        iface = self._interfaces[name]
        iface.address = address
        iface.netmask = netmask
        iface.remote_end = (host, port)

    def start(self):
        # Bootstrap processes
        self._update_lsdb()
        self._refresh_lsa()
        self._hello()
        # start asyncore framework
        asyncore.loop()

    def stop(self):
        for t in self._timers.values():
            t.cancel()
        for iface in self._interfaces.values():
            iface.handle_close()


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
            neighbor_id = packet.router_id
            if neighbor_id in self.router._timers:
                self.router._timers[neighbor_id].cancel()
            t = Timer(ospf.DEAD_INTERVAL, self.router._break_adjacency, args=(neighbor_id, ))
            t.start()
            self.router._timers[neighbor_id] = t
            topology_changed = (neighbor_id not in self.router._neighbors)
            self.router._neighbors[neighbor_id] = (self.iface_name, packet.address, packet.netmask)
            if self.router._hostname not in self.router._lsdb:
                print 'Initial Link State advertisement'
                self.router._advertise()
            elif topology_changed:
                print 'Network topology changed'
                self.router._advertise()
                # Re-flood link state packets from currently re-upped neighbor
                if neighbor_id in self.router._lsdb:
                    packet = self.router._lsdb[neighbor_id]
                    self.router._flood(packet)
        elif isinstance(packet, ospf.LinkStatePacket):
            print 'Received LSA from %s' % (packet.adv_router)
            # Insert to Link State database
            if self.router._lsdb.insert(packet):
                self.router._flood(packet, self.iface_name)
                # Update routing table
                self.router._update_routing_table()
        self.handle_close()
        print self.router._lsdb.values()
        print '\n'

    def handle_close(self):
        if self._fileno in self.connections:
            del self.connections[self._fileno]
        self.close()
        #self.log('Connection closed: %s' % (self.addr, ))


class Route(object):

    def __init__(self, dest, gateway, netmask, metric, iface):
        self.dest = dest
        self.gateway = gateway
        self.netmask = netmask
        self.metric = metric
        self.iface = iface


class RoutingTable(list):

    def __repr__(self):
        routes = ['Dest\tGateway\tNetmask\tMetric\tInterface']
        for r in self:
            routes.append("%s\t%s\t%s\t%.2f\t%s" % (r.dest, r.gateway, r.netmask, r.metric, r.iface))
        return '\n'.join(routes)

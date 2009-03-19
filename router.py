# -*- coding: utf-8 -*-

import socket
import asyncore
import asynchat
try:
    import cPickle as pickle
except ImportError:
    import pickle

import ospf


_terminator = '\0E\0O\0F\0'


poll = asyncore.poll


def mktimer(interval, callback, args=(), single_shot=False):
    raise NotImplementedError('specify your own function')


def log(msg):
    print 'log:', msg


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

    def clear(self):
        del self[:]


class Router(object):

    def __init__(self, hostname):
        self._hostname = hostname
        self._table = RoutingTable()
        self._lsdb = ospf.Database()
        self._interfaces = {}
        self._neighbors = {}
        self._seen = {}
        self._init_timers()

    def __del__(self):
        self.stop()

    @staticmethod
    def _get_netadd(addr, netmask):
        addr = addr.split('.')
        netmask = netmask.split('.')
        netadd = []
        for i in xrange(4):
            netadd.append(str(int(addr[i]) & int(netmask[i])))
        return '.'.join(netadd)

    def _init_timers(self):
        self._dead_timer = None
        self._timers = {}
        self._timers['lsdb'] = mktimer(ospf.AGE_INTERVAL, self._update_lsdb)
        self._timers['refresh_lsa'] = mktimer(ospf.LS_REFRESH_TIME, self._refresh_lsa)
        self._timers['hello'] = mktimer(ospf.HELLO_INTERVAL, self._hello)

    def _update_lsdb(self):
        flushed = self._lsdb.update()
        if flushed:
            log('LSA(s) of %s reached MaxAge and was/were flushed from the LSDB' % (', '.join(flushed), ))

    def _refresh_lsa(self):
        if self._hostname in self._lsdb:
            log('Refreshing own LSA')
            lsa = self._lsdb[self._hostname]
            # reset age
            lsa.age = 1
            # and flood to network
            self._advertise()

    def _hello(self):
        """Establish adjacency"""
        seen = self._seen.keys()
        for iface in self._interfaces.values():
            packet = ospf.HelloPacket(self._hostname, iface.address, iface.netmask, seen)
            iface.transmit(packet)
        for neighbor_id in self._seen:
            if neighbor_id not in self._neighbors:
                self._sync_lsdb(neighbor_id)

    def _update_routing_table(self):
        log('Recalculating shortest paths and updating routing table')
        self._table.clear()
        for path in self._lsdb.get_shortest_paths(self._hostname):
            next_hop, before_dest, dest, cost = path
            iface, gateway = self._lsdb[self._hostname].neighbors[next_hop][:2]
            dest_addr, netmask = self._lsdb[before_dest].neighbors[dest][1:3]
            dest_net = self._get_netadd(dest_addr, netmask)
            r = Route(dest_net, gateway, netmask, cost, iface)
            self._table.append(r)

    def _break_adjacency(self, neighbor_id):
        # Save reference QObject errors
        self._dead_timer = self._timers[neighbor_id]
        del self._timers[neighbor_id]
        del self._neighbors[neighbor_id]
        del self._seen[neighbor_id]
        log(' '.join([neighbor_id, 'is down']))
        self._advertise()

    def _flood(self, packet, source_iface=None):
        """Flood received packet to other interfaces"""
        if packet.adv_router == self._hostname:
            log('Flooding own LSA')
        else:
            log('Flooding LSA of %s' % (packet.adv_router, ))
        interfaces = []
        for data in self._neighbors.values():
            interfaces.append(data[0])
        if source_iface in interfaces:
            interfaces.remove(source_iface)
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

    def _sync_lsdb(self, neighbor_id):
        topology_changed = (neighbor_id not in self._neighbors)
        if topology_changed:
            log('Adjacency established with %s' % (neighbor_id, ))
        self._neighbors[neighbor_id] = self._seen[neighbor_id]
        if self._hostname not in self._lsdb:
            log('Creating initial LSA')
            self._advertise()
        elif topology_changed:
            self._advertise()
            # Re-flood link state packets from currently re-upped neighbor
            if neighbor_id in self._lsdb:
                packet = self._lsdb[neighbor_id]
                self._flood(packet)
            # Sync LSDB with neighbor
            iface_name = self._neighbors[neighbor_id][0]
            iface = self._interfaces[iface_name]
            for lsa in self._lsdb.values():
                iface.transmit(lsa)

    def iface_create(self, name, bandwidth, port):
        if name not in self._interfaces:
            self._interfaces[name] = Interface(name, bandwidth, port, self)

    def iface_config(self, name, address, netmask, host, port):
        iface = self._interfaces[name]
        iface.address = address
        iface.netmask = netmask
        iface.remote_end = (host, port)

    def start(self):
        # Start timers
        for t in self._timers.values():
            t.start()
        self._hello()

    def stop(self):
        for t in self._timers.values():
            t.stop()
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
        log('%s up' % (self.name, ))

    @staticmethod
    def writable():
        return False

    def handle_close(self):
        self.close()
        for conn in self.connections.values():
            conn.handle_close()
        log('%s down' % (self.name, ))

    def handle_accept(self):
        conn, addr = self.accept()
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

    def __init__(self, address, connections):
        asynchat.async_chat.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.add_channel(connections)
        self.connect(address)
        self.connections = connections

    def handle_error(self):
        self.handle_close()

    @staticmethod
    def handle_connect():
        return

    def handle_close(self):
        if self._fileno in self.connections:
            del self.connections[self._fileno]
        self.close()


class IfaceRx(asynchat.async_chat):

    ac_out_buffer_size = 0

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
            # Reset Dead timer
            if neighbor_id in self.router._timers:
                self.router._timers[neighbor_id].stop()
            t = mktimer(ospf.DEAD_INTERVAL, self.router._break_adjacency, (neighbor_id, ), True)
            t.start()
            self.router._timers[neighbor_id] = t
            self.router._seen[neighbor_id] = (self.iface_name, packet.address, packet.netmask)
            if self.router._hostname in packet.seen:
                self.router._sync_lsdb(neighbor_id)
        elif isinstance(packet, ospf.LinkStatePacket):
            log('Received LSA of %s via %s' % (packet.adv_router, self.iface_name))
            # Insert to Link State database
            if self.router._lsdb.insert(packet):
                log('Merged LSA of %s to the LSDB' % (packet.adv_router, ))
                self.router._flood(packet, self.iface_name)
                # Update routing table
                self.router._update_routing_table()
            else:
                log('Discarded LSA of %s (outdated or already in the LSDB)' % (packet.adv_router, ))
        self.handle_close()

    def handle_close(self):
        if self._fileno in self.connections:
            del self.connections[self._fileno]
        self.close()

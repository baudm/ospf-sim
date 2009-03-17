# -*- coding: utf-8 -*-
# http://www.lincoln.edu/math/rmyrick/ComputerNetworks/InetReference/89.htm

from copy import copy
from threading import Timer

import dijkstra


TIME_SCALE = 60 # 1 minute is to 1 second


def _scale_time(minutes):
    return (60.0 * minutes / TIME_SCALE)


BANDWIDTH_BASE = 100000000 # 100M
HELLO_INTERVAL = 10 # 10 seconds
DEAD_INTERVAL = 4 * HELLO_INTERVAL # typical value is 4 times the HELLO_INTERVAL
AGE_INTERVAL = _scale_time(1) # 1 minute
LS_REFRESH_TIME = _scale_time(30) # 30 minutes
MAX_AGE = _scale_time(60) # 1 hour
MAX_AGE_DIFF = _scale_time(15) # 15 minutes


class LinkStatePacket(object):

    def __init__(self, router_id, age, seq_no, neighbors):
        self.adv_router = router_id
        self.age = age
        self.seq_no = seq_no
        self.neighbors = neighbors

    def __repr__(self):
        stat = '\nADV Router: %s\nAge: %d\nSeq No.: %d\nNeighbors: %s\n\n' % (self.adv_router, self.age, self.seq_no, self.neighbors)
        return stat


class HelloPacket(object):

    def __init__(self, router_id, address, netmask):
        self.router_id = router_id
        self.address = address
        self.netmask = netmask


class Database(dict):

    def insert(self, lsa):
        """Returns True if LSA was added/updated"""
        if lsa.adv_router not in self or \
           lsa.seq_no > self[lsa.adv_router].seq_no:
            self[lsa.adv_router] = lsa
            return True
        else:
            return False

    def remove(self, router_id):
        if router_id in self:
            del self[router_id]

    def flush(self):
        """Flush old entries"""
        for router_id in copy(self):
            if self[router_id].age > MAX_AGE:
                del self[router_id]

    def update(self):
        for adv_router in self:
            self[adv_router].age += 1
        self.flush()

    def get_shortest_paths(self, router_id):
        g = dijkstra.Graph()
        nodes = []
        paths = []
        for lsa in self.values():
            nodes.append(lsa.adv_router)
            for neighbor_id, cost in lsa.neighbors.iteritems():
                g.add_e(lsa.adv_router, neighbor_id, cost)
        if router_id in nodes:
            nodes.remove(router_id)
        # Find a shortest path from router_id to dest
        dist, prev = g.s_path(router_id)
        for dest in nodes:
            # Trace the path back using the prev array.
            path = []
            current = dest
            while current in prev:
                path.insert(0, prev[current])
                current = prev[current]
            try:
                cost = dist[dest]
            except KeyError:
                continue
            else:
                next_hop = (path[1] if len(path) > 1 else dest)
                entry = (dest, next_hop, cost)
                paths.append(entry)
        return paths

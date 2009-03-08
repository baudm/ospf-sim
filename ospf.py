# -*- coding: utf-8 -*-
# http://www.lincoln.edu/math/rmyrick/ComputerNetworks/InetReference/89.htm

import dijkstra


time_scale = 60 # 1 minute is to 1 hour
bandwidth_base = 100000000 # 100M


class Packet(object):

    def __init__(self, router_id, seq_no, age, neighbors):
        self.router_id = router_id
        self.seq_no = seq_no
        self.age = age
        self.neighbors = neighbors


class DbEntry(object):

    def __init__(self, router_id, host, port, bandwidth):
        cost = bandwidth_base / float(bandwidth)


class Database(object):

    def add_entry(self):
        pass

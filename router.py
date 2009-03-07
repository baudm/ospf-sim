# -*- coding: utf-8 -*-

import asyncore
import linkstate

#http://www.lincoln.edu/math/rmyrick/ComputerNetworks/InetReference/89.htm

time_scale = 60 # 1 minute is to 1 hour


class Router(object):

    def __init__(self, router_id, port):
        self.router_id = router_id
        self.port = port
        self.table = RoutingTable()
        self.lsdb = linkstate.Database()
        self.neighbors

    def add_neighbor(self, router_id, host, port, bandwidth):
        self.lsdb

    def hello(self):
        """Simple reachability check"""
        pass



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

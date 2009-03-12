# -*- coding: utf-8 -*-
# http://www.lincoln.edu/math/rmyrick/ComputerNetworks/InetReference/89.htm

from copy import copy
from threading import Timer

import dijkstra


time_scale = 60 # 1 minute is to 1 hour
bandwidth_base = 100000000 # 100M


class LsaPacket(object):

    def __init__(self, router_id, age, seq_no, neighbors):
        self.adv_router = router_id
        self.age = age
        self.seq_no = seq_no
        self.neighbors = neighbors


class HelloPacket(object):

    def __init__(self, router_id, neighbors):
        self.router_id = router_id
        self.neighbors = neighbors


class Database(dict):

    def __init__(self, maxage, age_interval):
        self.maxage = maxage
        self.age_interval = age_interval
        self._age_timer = None
        self._inc_age()

    def __del__(self):
        self.cleanup()

    def _inc_age(self):
        self._age_timer = Timer(self.age_interval, self._inc_age)
        self._age_timer.start()
        for adv_router in self:
            self[adv_router].age += 1
        self.flush()

    def cleanup(self):
        self._age_timer.cancel()

    def update(self, lsa):
        if lsa.adv_router not in self or \
           lsa.seq_no > self[lsa.adv_router].seq_no:
            self[lsa.adv_router] = lsa

    def flush(self, router_id=None):
        if router_id is not None:
            if router_id in self:
                del self[adv_router]
        else:
            for router_id in copy(self):
                if self[router_id] > self.maxage:
                    del self[router_id]

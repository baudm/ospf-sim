# -*- coding: utf-8 -*-
# From: http://en.wikipedia.org/wiki/Dijkstra's_algorithm

import heapq
from collections import defaultdict


class Edge(object):

    def __init__(self, start, end, weight):
        self.start = start
        self.end = end
        self.weight = weight

    # For heapq.
    def __cmp__(self, other):
        return cmp(self.weight, other.weight)


class Graph(object):

    def __init__(self):
        # The adjacency list.
        self.adj = defaultdict(list)

    def add_e(self, start, end, weight=0):
        self.adj[start].append(Edge(start, end, weight))

    def s_path(self, src):
        """
        Returns the distance to every vertex from the source and the
        array representing, at index i, the node visited before
        visiting node i. This is in the form (dist, previous).
        """
        dist = {src: 0}
        visited = {}
        previous = {}
        queue = []
        heapq.heappush(queue, (dist[src],src))
        while queue:
            distance, current = heapq.heappop(queue)
            if current in visited:
                continue
            visited[current] = True

            for edge in self.adj[current]:
                relaxed = dist[current] + edge.weight
                end = edge.end
                if end not in dist or relaxed < dist[end]:
                    previous[end] = current
                    dist[end] = relaxed
                    heapq.heappush(queue, (dist[end],end))
        return dist, previous

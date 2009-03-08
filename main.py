#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import signal
from ConfigParser import SafeConfigParser

from router import Router


def main():
    if len(sys.argv) < 2:
        print 'Specify configuration file'
        return
    config = SafeConfigParser()
    config.read(sys.argv[1])
    router_id = config.get('Router', 'id')
    port = int(config.get('Router', 'port'))
    router = Router(router_id, port)
    for neighbor in config.sections()[1:]:
        host = config.get(neighbor, 'host')
        port = int(config.get(neighbor, 'port'))
        bandwidth = int(config.get(neighbor, 'bandwidth'))
        router.add_neighbor(host, port, bandwidth)
    signal.signal(signal.SIGTERM, lambda s, f: router.stop())
    signal.signal(signal.SIGINT, lambda s, f: router.stop())
    router.start()


if __name__ == '__main__':
    main()

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
    cfg = SafeConfigParser()
    cfg.read(sys.argv[1])
    router = Router(cfg.get('Local', 'hostname'))
    # Create and configure Router interfaces
    for iface in [i for i in cfg.sections() if i.startswith('Local:')]:
        # Create
        name = iface.split(':')[1]
        bandwidth = cfg.get(iface, 'bandwidth')
        port = int(cfg.get(iface, 'port'))
        router.iface_create(name, bandwidth, port)
        # Configure
        address = cfg.get(iface, 'address')
        netmask = cfg.get(iface, 'netmask')
        link = cfg.get(iface, 'link')
        host = cfg.get(link, 'host')
        port = int(cfg.get(link, 'port'))
        router.iface_config(name, address, netmask, host, port)
    signal.signal(signal.SIGTERM, lambda s, f: router.stop())
    signal.signal(signal.SIGINT, lambda s, f: router.stop())
    router.start()


if __name__ == '__main__':
    main()

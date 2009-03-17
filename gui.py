#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
from threading import Thread
from ConfigParser import SafeConfigParser

from PyQt4 import QtCore, QtGui, uic

from router import Router


def main():
    app = QtGui.QApplication(sys.argv)
    w = uic.loadUi('sim.ui')
    configfile = QtGui.QFileDialog.getOpenFileName(w, 'Open router config file', '/home/darwin', '*.cfg')
    if not configfile:
        configfile = sys.argv[1]
    cfg = SafeConfigParser()
    cfg.read(str(configfile))
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

    iface_count = len(router._interfaces)
    w.tableWidget_3.setRowCount(iface_count)
    ifaces = router._interfaces.values()
    for i in xrange(iface_count):
        col_count = 0
        for col in ('name', 'address', 'netmask'):
            val = getattr(ifaces[i], col)
            item = QtGui.QTableWidgetItem(str(val))
            w.tableWidget_3.setItem(i, col_count, item)
            col_count += 1

    def update():
        rows = len(router._table)
        w.tableWidget.clearContents()
        w.tableWidget.setRowCount(rows)
        for i in xrange(rows):
            col_count = 0
            for col in ('dest', 'gateway', 'netmask', 'metric', 'iface'):
                val = getattr(router._table[i], col)
                item = QtGui.QTableWidgetItem(str(val))
                w.tableWidget.setItem(i, col_count, item)
                col_count += 1

        row_count = 0
        w.tableWidget_2.clearContents()
        for lsa in router._lsdb.values():
            for neighbor, data in lsa.neighbors.iteritems():
                w.tableWidget_2.setRowCount(row_count + 1)
                cost = data[3]
                col_count = 0
                for val in (lsa.adv_router, neighbor, cost):
                    item = QtGui.QTableWidgetItem(str(val))
                    w.tableWidget_2.setItem(row_count, col_count, item)
                    col_count += 1
                row_count += 1


    timer = QtCore.QTimer()
    timer.start(1000)

    QtCore.QObject.connect(timer, QtCore.SIGNAL('timeout()'), update)

    QtCore.QObject.connect(w, QtCore.SIGNAL('destroyed()'), router.stop)
    w.show()
    t = Thread(target=router.start)
    t.setDaemon(True)
    t.start()
    app.exec_()


if __name__ == '__main__':
    main()


#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import signal
import time
from ConfigParser import SafeConfigParser

from PyQt4 import QtCore, QtGui, uic

import router


def mktimer(interval, callback, args=(), single_shot=False):
    t = QtCore.QTimer()
    t.setInterval(1000 * interval)
    def timeout():
        callback(*args)
    t.setSingleShot(single_shot)
    QtCore.QObject.connect(t, QtCore.SIGNAL('timeout()'), timeout)
    return t


def main():
    app = QtGui.QApplication(sys.argv)
    ui = uic.loadUi('sim.ui')

    def log(msg):
        ui.messages.append('%s    %s' % (time.ctime().split()[3], msg))

    # Override default functions
    router.mktimer = mktimer
    router.log = log

    configfile = QtGui.QFileDialog.getOpenFileName(ui, 'Open router configuration file', '', '*.cfg')
    if not configfile:
        configfile = sys.argv[1]
    cfg = SafeConfigParser()
    cfg.read(str(configfile))

    hostname = cfg.get('Local', 'hostname')
    ui.setWindowTitle(hostname)
    r = router.Router(hostname)

    # Create and configure Router interfaces
    ifaces = [i for i in cfg.sections() if i.startswith('Local:')]
    ui.interfaces.setRowCount(len(ifaces))
    for iface in ifaces:
        # Create
        name = iface.split(':')[1]
        bandwidth = cfg.get(iface, 'bandwidth')
        port = int(cfg.get(iface, 'port'))
        r.iface_create(name, bandwidth, port)
        # Configure
        address = cfg.get(iface, 'address')
        netmask = cfg.get(iface, 'netmask')
        link = cfg.get(iface, 'link')
        host = cfg.get(link, 'host')
        port = int(cfg.get(link, 'port'))
        r.iface_config(name, address, netmask, host, port)
        cols = [name, address, netmask, bandwidth, link]
        for val in cols:
            item = QtGui.QTableWidgetItem(val)
            ui.interfaces.setItem(ifaces.index(iface), cols.index(val), item)

    def refresh_ui():
        rows = len(r._table)
        ui.routingTable.clearContents()
        ui.routingTable.setRowCount(rows)
        for i in xrange(rows):
            col_count = 0
            for col in ('dest', 'gateway', 'netmask', 'metric', 'iface'):
                val = getattr(r._table[i], col)
                item = QtGui.QTableWidgetItem(str(val))
                ui.routingTable.setItem(i, col_count, item)
                col_count += 1

        row_count = 0
        ui.linkStateDb.clearContents()
        for lsa in r._lsdb.values():
            for neighbor, data in lsa.neighbors.iteritems():
                ui.linkStateDb.setRowCount(row_count + 1)
                cost = data[3]
                col_count = 0
                for val in (lsa.adv_router, lsa.seq_no, lsa.age, neighbor, cost):
                    item = QtGui.QTableWidgetItem(str(val))
                    ui.linkStateDb.setItem(row_count, col_count, item)
                    col_count += 1
                row_count += 1
    # Create timers
    ui_timer = QtCore.QTimer()
    log_timer = QtCore.QTimer()
    router_timer = QtCore.QTimer()
    # Setup signal-slot connections
    QtCore.QObject.connect(app, QtCore.SIGNAL('lastWindowClosed()'), r.stop)
    QtCore.QObject.connect(ui_timer, QtCore.SIGNAL('timeout()'), refresh_ui)
    QtCore.QObject.connect(log_timer, QtCore.SIGNAL('timeout()'), ui.messages.clear)
    QtCore.QObject.connect(router_timer, QtCore.SIGNAL('timeout()'), router.poll)
    # Start timers
    ui_timer.start(1000)
    log_timer.start(120000)
    router_timer.start(500)
    # Start router and show UI
    r.start()
    ui.show()
    # Setup signal handlers
    signal.signal(signal.SIGTERM, lambda s, f: ui.close())
    signal.signal(signal.SIGINT, lambda s, f: ui.close())
    # Start event loop
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

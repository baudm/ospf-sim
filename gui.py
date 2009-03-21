# -*- coding: utf-8 -*-
# Copyright (c) 2009 Darwin M. Bautista
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import os
import sys
import signal
import time
from ConfigParser import SafeConfigParser

from PyQt4 import QtCore, QtGui, uic

import router


def mktimer(interval, callback, args=(), single_shot=False):
    t = QtCore.QTimer()
    t.setInterval(1000 * interval)
    if args:
        def timeout():
            callback(*args)
    else:
        timeout = callback
    t.setSingleShot(single_shot)
    QtCore.QObject.connect(t, QtCore.SIGNAL('timeout()'), timeout)
    return t


def main():
    app = QtGui.QApplication(sys.argv)
    os.chdir(os.path.dirname(__file__))
    ui = uic.loadUi('simulator.ui')

    def log(msg):
        ui.messages.appendPlainText('%s    %s' % (time.ctime().split()[3], msg))

    # Override default functions
    router.mktimer = mktimer
    router.log = log

    configfile = QtGui.QFileDialog.getOpenFileName(ui, 'Open router configuration file', '', '*.cfg')
    if not configfile:
        if len(sys.argv) != 2:
            sys.exit(1)
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
        if ui.routingTable.rowCount() != rows:
            ui.routingTable.setRowCount(rows)
        for i in xrange(rows):
            col_count = 0
            for col in ('dest', 'gateway', 'netmask', 'metric', 'iface'):
                val = getattr(r._table[i], col)
                item = QtGui.QTableWidgetItem(str(val))
                ui.routingTable.setItem(i, col_count, item)
                col_count += 1

        rows = sum([len(n.neighbors) for n in r._lsdb.values()])
        if ui.linkStateDb.rowCount() != rows:
            ui.linkStateDb.setRowCount(rows)
        row_count = 0
        for lsa in r._lsdb.values():
            for neighbor, data in lsa.neighbors.iteritems():
                cost = data[3]
                col_count = 0
                for val in (lsa.adv_router, lsa.seq_no, lsa.age, neighbor, cost):
                    item = QtGui.QTableWidgetItem(str(val))
                    ui.linkStateDb.setItem(row_count, col_count, item)
                    col_count += 1
                row_count += 1
    # Create timers
    ui_timer = QtCore.QTimer()
    router_timer = QtCore.QTimer()
    # Setup signal-slot connections
    QtCore.QObject.connect(app, QtCore.SIGNAL('lastWindowClosed()'), r.stop)
    QtCore.QObject.connect(ui_timer, QtCore.SIGNAL('timeout()'), refresh_ui)
    QtCore.QObject.connect(router_timer, QtCore.SIGNAL('timeout()'), router.poll)
    # Start timers
    ui_timer.start(1000)
    router_timer.start(500)
    # Start router and show UI
    r.start()
    ui.show()
    # Setup signal handlers
    signal.signal(signal.SIGTERM, lambda s, f: ui.close())
    signal.signal(signal.SIGINT, lambda s, f: ui.close())
    # Start event loop
    sys.exit(app.exec_())

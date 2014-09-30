#!/usr/bin/python3
from gi.repository import Gtk
from os.path import isfile
from desima import (sites_states, sdo, START, STOP, ISRUNNING, WWW, DB,
                    is_valid_site_id, find_site, install_site, find_unused_port,
                    mysql_log_file, apache2_log_file, list_applications)
from subprocess import Popen

def error_dialog(title, message):
    dialog = Gtk.MessageDialog(
        None,
        0,
        Gtk.MessageType.ERROR,
        Gtk.ButtonsType.CANCEL,
        title
    )

    dialog.format_secondary_text(message)
    dialog.run()

    dialog.destroy()

class DesimaHandler:
    def __init__(self, builder):
        self.bld = builder

        self.tvwSites = builder.get_object('tvwSites')
        self.stoSites = builder.get_object("stoSites")
        self.imgRunDB = builder.get_object('imgRunDB')
        self.imgRunWeb = builder.get_object('imgRunWeb')
        self.imgStopDB = builder.get_object('imgStopDB')
        self.imgStopWeb = builder.get_object('imgStopWeb')
        self.btnRunWeb = builder.get_object("btnRunWeb")
        self.btnRunDB = builder.get_object("btnRunDB")
        self.btnShowLog = builder.get_object("btnShowLog")
        self.dlgNew = builder.get_object("dlgNew")
        self.entSiteId = builder.get_object("entSiteId")
        self.cbtNewApplication = builder.get_object("cbtNewApplication")
        self.stoApplication = builder.get_object("stoApplication")

        self.initGUI()

    def initGUI(self):
        self.refreshSites()

    def getCurrentSite(self):
        selection = self.tvwSites.get_selection()
        (model, treeiter) = selection.get_selected()

        if treeiter != None:
            return model.get(treeiter, 0)[0]

        return None
    
    def setCurrentSite(self, site_id):
        if site_id == None:
            return

        # Search for a site_id in available rows
        model = self.tvwSites.get_model()
        treeiter = model.get_iter_first()
        while treeiter != None:
            if site_id == model.get_value(treeiter, 0):
                self.tvwSites.get_selection().select_iter(treeiter)
                break

            treeiter = model.iter_next(treeiter)

        self.onTvwSitesCursorChanged(self.tvwSites)

    def refreshSites(self):
        # Keep track of the current selected item
        current_site = self.getCurrentSite()

        # Prepare data for the rows
        text = { True: 'running', False: 'stopped' }
        rows = [
            [site_id, int(port), text[www_running], text[db_running]]
            for (site_id, port, www_running, db_running) in sites_states()
        ]

        # Update the listview
        self.stoSites.clear()
        for row in rows:
            self.stoSites.append(row)

        # Reselect the previously selected item
        self.setCurrentSite(current_site)

    def updateRunButton(self, button, btntype, current_state, message):
        assert current_state in [None, 'stopped', 'running']
        assert btntype in ['Web', 'DB']

        messages = {'stopped': 'Run ', 'running': 'Stop '}
        images = {'stopped': {'Web': self.imgRunWeb, 'DB': self.imgRunDB},
                  'running': {'Web': self.imgStopWeb, 'DB': self.imgStopDB}}

        if current_state != None:
            button.set_label(messages[current_state] + ' ' + message)
            button.set_image(images[current_state][btntype])

        button.set_sensitive(current_state != None)

    def updateRunButtons(self, wwwrun, dbrun):
        self.updateRunButton(self.btnRunWeb, 'Web', wwwrun, 'web server')
        self.updateRunButton(self.btnRunDB, 'DB', dbrun, 'DB server')
        self.btnShowLog.set_sensitive(wwwrun != None)

    def toggleServer(self, btntype, site_id, port):
        assert btntype in ['DB', 'Web']

        servers = {'DB': DB, 'Web': WWW}
        actions = {True: STOP, False: START}
        action = actions[sdo(ISRUNNING, servers[btntype], site_id, port)]
        sdo(action, servers[btntype], site_id, port)
        self.refreshSites()

    def onWinDesimaDelete(self, *args):
        Gtk.main_quit(*args)

    def validateNewForm(self):
        site_id = self.entSiteId.get_text()

        if not is_valid_site_id(site_id):
            error_dialog(
                'Invalid Site ID',
                'Site ID should be of the form [a-zA-Z][a-zA-Z0-9_]{0,23}'
            )
            return False

        if find_site(site_id) != None:
            error_dialog('Invalid Site ID', 'This site already exists !')
            return False

        return True

    def applyNewForm(self):
        site_id = self.entSiteId.get_text()
        application_file = None

        if self.cbtNewApplication.get_active() > 0:
            active = self.cbtNewApplication.get_active_iter()
            application_file = self.stoApplication.get(active, 1)[0]
    
        install_site(site_id, find_unused_port(), application_file)

    def updateApplicationList(self):
        self.stoApplication.clear()
        self.stoApplication.append(('None', ''))
        for application in list_applications():
            self.stoApplication.append(application)

        self.cbtNewApplication.set_active(0)

    def onBtnNewClicked(self, button):
        self.dlgNew.show_all()

        # Update list of applications
        self.updateApplicationList()

        while True:
            if self.dlgNew.run() == 0:
                break

            if self.validateNewForm():
                self.applyNewForm()
                break

        self.dlgNew.hide()
        self.refreshSites()

    def onBtnRefreshClicked(self, button):
        self.refreshSites()

    def onTvwSitesCursorChanged(self, tv):
        (store, treeiter) = tv.get_selection().get_selected()
        (wwwrun, dbrun) = (None, None)

        # Test if a row is actually selected
        if treeiter != None:
            wwwrun = store.get_value(treeiter, 2)
            dbrun = store.get_value(treeiter, 3)

        self.updateRunButtons(wwwrun, dbrun)

    def onBtnRunClicked(self, button):
        btntypes = { True: 'Web', False: 'DB' }
        btntype = btntypes[button.get_label().find('web') >= 0]
 
        (store, treeiter) = self.tvwSites.get_selection().get_selected()

        if treeiter != None:
            site_id = store.get_value(treeiter, 0)
            port = store.get_value(treeiter, 1)
            self.toggleServer(btntype, site_id, port)

    def onBtnShowLog(self, button):
        btntypes = { True: 'Web', False: 'DB' }
        btntype = btntypes[button.get_label().find('web') >= 0]
 
        (store, treeiter) = self.tvwSites.get_selection().get_selected()

        if treeiter != None:
            site_id = store.get_value(treeiter, 0)
            port = store.get_value(treeiter, 1)
            logs = [log for log in mysql_log_file(site_id, port) +
                                   apache2_log_file(site_id, port)
                        if isfile(log)]
            Popen(["gnome-system-log"] + logs)

def main(gladeFile, winID):
    # Show images on buttons
    settings = Gtk.Settings.get_default()
    settings.props.gtk_button_images = True

    # Build the interface
    builder = Gtk.Builder()
    builder.add_from_file(gladeFile)
    builder.connect_signals(DesimaHandler(builder))

    # Show the window
    window = builder.get_object(winID)
    window.show_all()

    Gtk.main()

if __name__ == '__main__':
    main("desima-gui.glade", "winDesima")


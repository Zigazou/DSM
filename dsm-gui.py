#!/usr/bin/python3
from gi.repository import Gtk
from dsm import (sites_states, sdo, START, STOP, ISRUNNING, WWW, DB,
                 is_valid_site_id, find_site, install_site, find_unused_port)

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

class DSMHandler:
    def __init__(self, builder):
        self.currentSite = None
        self.bld = builder
        self.initGUI()

    def initGUI(self):
        self.refreshSites()

    def refreshSites(self):
        # Prepare data for the rows
        text = { True: 'running', False: 'stopped' }
        rows = [
            [site_id, int(port), text[www_running], text[db_running]]
            for (site_id, port, www_running, db_running) in sites_states()
        ]

        # Update the listview
        store = self.bld.get_object("stoSites")
        store.clear()
        for row in rows:
            store.append(row)

        if self.currentSite != None:
            self.bld.get_object("tvwSites").set_cursor(self.currentSite)

    def updateRunButton(self, button, btntype, current_state, message):
        assert current_state in [None, 'stopped', 'running']
        assert btntype in ['Web', 'DB']

        messages = {'stopped': 'Run ', 'running': 'Stop '}
        images = {'stopped': self.bld.get_object('imgRun' + btntype),
                  'running': self.bld.get_object('imgStop' + btntype)}

        if current_state != None:
            button.set_label(messages[current_state] + ' ' + message)
            button.set_image(images[current_state])

        button.set_sensitive(current_state != None)

    def updateRunButtons(self, wwwrun, dbrun):
        btnRunWeb = self.bld.get_object("btnRunWeb")
        btnRunDB = self.bld.get_object("btnRunDB")

        self.updateRunButton(btnRunWeb, 'Web', wwwrun, 'web server')
        self.updateRunButton(btnRunDB, 'DB', dbrun, 'DB server')

    def toggleServer(self, btntype, site_id, port):
        assert btntype in ['DB', 'Web']

        servers = {'DB': DB, 'Web': WWW}
        actions = {True: STOP, False: START}
        action = actions[sdo(ISRUNNING, servers[btntype], site_id, port)]
        sdo(action, servers[btntype], site_id, port)

    def onWinDsmDelete(self, *args):
        Gtk.main_quit(*args)

    def onBtnNewClicked(self, button):
        dia = self.bld.get_object("dlgNew")
        dia.show_all()

        ent_site_id = self.bld.get_object("entSiteId")

        while True:
            rc = dia.run()

            if rc == 0:
                break

            site_id = ent_site_id.get_text()

            if not is_valid_site_id(site_id):
                error_dialog(
                    'Invalid Site ID',
                    'Site ID should be of the form [a-zA-Z][a-zA-Z0-9_]{0,23}'
                )
                continue

            if find_site(site_id) != None:
                error_dialog('Invalid Site ID', 'This site already exists !')
                continue
        
            install_site(site_id, find_unused_port())
            break

        dia.hide()
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
            self.currentSite = tv.get_cursor()
        else:
            self.currentSite = None

        self.updateRunButtons(wwwrun, dbrun)

    def onBtnRunClicked(self, button):
        btntypes = { True: 'Web', False: 'DB' }
        btntype = btntypes[button.get_label().find('web') >= 0]
 
        tv = self.bld.get_object('tvwSites')
        (store, treeiter) = tv.get_selection().get_selected()

        if treeiter != None:
            site_id = store.get_value(treeiter, 0)
            port = store.get_value(treeiter, 1)
            self.toggleServer(btntype, site_id, port)

def main(gladeFile, winID):
    # Show images on buttons
    settings = Gtk.Settings.get_default()
    settings.props.gtk_button_images = True

    # Build the interface
    builder = Gtk.Builder()
    builder.add_from_file(gladeFile)
    builder.connect_signals(DSMHandler(builder))

    # Show the window
    window = builder.get_object(winID)
    window.show_all()

    Gtk.main()

if __name__ == '__main__':
    main("dsm-gui.glade", "winDSM")


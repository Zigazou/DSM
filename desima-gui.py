#!/usr/bin/python3
"""Operate a GUI frontend to the desima module"""
from gi.repository import Gtk
from os.path import isfile
from desima import (sites_states, sdo, START, STOP, ISRUNNING, WWW, DB,
                    is_valid_site_id, find_site, site_install,
                    find_unused_port, mysql_log_file, apache2_log_file,
                    list_applications, remove_site)
from subprocess import Popen

def get_combobox_value(combobox, default):
    """Return the currently active value of a combobox."""
    if combobox.get_active() > 0:
        active = combobox.get_active_iter()
        return combobox.get_model().get(active, 1)[0]
    else:
        return default

def error_dialog(title, message):
    """Show an error dialog to the user."""
    dialog = Gtk.MessageDialog(
        None,
        Gtk.DialogFlags.MODAL,
        Gtk.MessageType.ERROR,
        Gtk.ButtonsType.CANCEL,
        title
    )

    dialog.format_secondary_text(message)
    dialog.run()

    dialog.destroy()

def confirmation_dialog(question):
    """Show a confirmation dialog to the user asking for a choice."""
    dialog = Gtk.MessageDialog(
        None,
        Gtk.DialogFlags.MODAL,
        Gtk.MessageType.QUESTION,
        Gtk.ButtonsType.YES_NO,
        question
    )

    response = dialog.run()
    dialog.destroy()

    return response == Gtk.ResponseType.YES

class DesimaHandler(object):
    """Handles every callbacks from the Desima window."""

    def __init__(self, builder):
        """ Get all the needed widgets."""
        self.bld = builder

        self.tvw_sites = builder.get_object('tvwSites')
        self.sto_sites = builder.get_object("stoSites")
        self.img_run_db = builder.get_object('imgRunDB')
        self.img_run_web = builder.get_object('imgRunWeb')
        self.img_stop_db = builder.get_object('imgStopDB')
        self.img_stop_web = builder.get_object('imgStopWeb')
        self.btn_run_web = builder.get_object("btnRunWeb")
        self.btn_run_db = builder.get_object("btnRunDB")
        self.btn_show_log = builder.get_object("btnShowLog")
        self.btn_remove = builder.get_object("btnRemove")
        self.dlg_new = builder.get_object("dlgNew")
        self.ent_site_id = builder.get_object("entSiteId")
        self.cbt_new_application = builder.get_object("cbtNewApplication")
        self.cbt_new_web_server = builder.get_object("cbtNewWebServer")
        self.cbt_new_db_server = builder.get_object("cbtNewDbServer")
        self.sto_application = builder.get_object("stoApplication")

        self.refresh_sites()

    def get_current_site(self):
        """Return the currently selected site."""
        selection = self.tvw_sites.get_selection()
        (model, treeiter) = selection.get_selected()

        if treeiter != None:
            return model.get(treeiter, 0)[0]

        return None

    def set_current_site(self, site_id):
        """Set the selected site."""
        if site_id == None:
            return

        # Search for a site_id in available rows
        model = self.tvw_sites.get_model()
        treeiter = model.get_iter_first()
        while treeiter != None:
            if site_id == model.get_value(treeiter, 0):
                self.tvw_sites.get_selection().select_iter(treeiter)
                break

            treeiter = model.iter_next(treeiter)

        self.on_tvw_sites_cursor_changed(self.tvw_sites)

    def refresh_sites(self):
        """Refresh the sites list."""
        # Keep track of the current selected item
        current_site = self.get_current_site()

        # Prepare data for the rows
        text = {True: 'running', False: 'stopped'}
        rows = [
            [site_id, int(port), text[www_running], text[db_running]]
            for (site_id, port, www_running, db_running) in sites_states()
        ]

        # Update the listview
        self.sto_sites.clear()
        for row in rows:
            self.sto_sites.append(row)

        # Reselect the previously selected item
        self.set_current_site(current_site)

    def update_run_button(self, button, btntype, current_state, message):
        """Update a Run/Stop button."""
        assert current_state in [None, 'stopped', 'running']
        assert btntype in ['Web', 'DB']

        messages = {'stopped': 'Run ', 'running': 'Stop '}
        images = {'stopped': {'Web': self.img_run_web, 'DB': self.img_run_db},
                  'running': {'Web': self.img_stop_web, 'DB': self.img_stop_db}}

        if current_state != None:
            button.set_label(messages[current_state] + ' ' + message)
            button.set_image(images[current_state][btntype])

        button.set_sensitive(current_state != None)

    def update_run_buttons(self, wwwrun, dbrun):
        """Update all run buttons."""
        self.update_run_button(self.btn_run_web, 'Web', wwwrun, 'web server')
        self.update_run_button(self.btn_run_db, 'DB', dbrun, 'DB server')
        self.btn_show_log.set_sensitive(wwwrun != None)

    def toggle_server(self, btntype, site_id):
        """Run an action based on a Run/Stop button."""
        assert btntype in ['DB', 'Web']

        servers = {'DB': DB, 'Web': WWW}
        actions = {True: STOP, False: START}
        action = actions[sdo(ISRUNNING, servers[btntype], site_id)]
        sdo(action, servers[btntype], site_id)
        self.refresh_sites()

    def on_win_desima_delete(self, *args):
        """Handler for the delete event."""
        Gtk.main_quit(*args)

    def validate_new_form(self):
        """Validate values from the new form."""
        site_id = self.ent_site_id.get_text()

        if not is_valid_site_id(site_id):
            error_dialog(
                'Invalid Site ID',
                'Site ID should be of the form [a-zA-Z][a-zA-Z0-9_]{0,23}'
            )
            return False

        if find_site(site_id):
            error_dialog('Invalid Site ID', 'This site already exists !')
            return False

        return True

    def apply_new_form(self):
        """Create a new site based on the new form."""
        site_id = self.ent_site_id.get_text()
        www_server = get_combobox_value(self.cbt_new_web_server, 'apache2')
        db_server = get_combobox_value(self.cbt_new_db_server, 'mysql')
        application_file = get_combobox_value(self.cbt_new_application, None)

        site_install(
            site_id,
            find_unused_port(),
            www_server,
            db_server,
            application_file
        )

    def update_application_list(self):
        """Update the applications list in the combo box widget."""
        self.sto_application.clear()
        self.sto_application.append(('None', ''))
        for application in list_applications():
            self.sto_application.append(application)

        self.cbt_new_application.set_active(0)

    def on_btn_new_clicked(self, _):
        """Handler when the user clicks on the new button."""
        self.dlg_new.show_all()

        # Update list of applications
        self.update_application_list()

        while True:
            if self.dlg_new.run() == 0:
                break

            if self.validate_new_form():
                self.apply_new_form()
                break

        self.dlg_new.hide()
        self.refresh_sites()

    def on_btn_remove_clicked(self, _):
        """Handler when the user clicks on the remove button."""
        site_id = self.get_current_site()
        if site_id == None:
            return

        confirmation = confirmation_dialog(
            'Do you really want to remove "{id}" ?'.format(id=site_id)
        )

        if confirmation:
            remove_site(site_id)
            self.refresh_sites()

    def on_btn_refresh_clicked(self, _):
        """Handler when the user clicks on the refresh button."""
        self.refresh_sites()

    def on_tvw_sites_cursor_changed(self, treeview):
        """Handler when the selection of the sites list has changed."""
        (store, treeiter) = treeview.get_selection().get_selected()
        (wwwrun, dbrun) = (None, None)

        # Test if a row is actually selected
        if treeiter != None:
            wwwrun = store.get_value(treeiter, 2)
            dbrun = store.get_value(treeiter, 3)

        self.btn_remove.set_sensitive(treeiter != None)
        self.update_run_buttons(wwwrun, dbrun)

    def on_btn_run_clicked(self, button):
        """Handler when a run button is clicked."""
        site_id = self.get_current_site()

        if site_id != None:
            btntypes = {True: 'Web', False: 'DB'}
            btntype = btntypes[button.get_label().find('web') >= 0]
            self.toggle_server(btntype, site_id)

    def on_btn_show_log(self, _):
        """Handler when the user clicks on the show log button."""
        site_id = self.get_current_site()

        if site_id != None:
            logs = [
                log
                for log in mysql_log_file(site_id) + apache2_log_file(site_id)
                if isfile(log)
            ]

            Popen(["gnome-system-log"] + logs)

def main(glade_file, win_id):
    """Setup the window and run !"""
    # Show images on buttons
    settings = Gtk.Settings.get_default()
    settings.props.gtk_button_images = True

    # Build the interface
    builder = Gtk.Builder()
    builder.add_from_file(glade_file)
    builder.connect_signals(DesimaHandler(builder))

    # Show the window
    window = builder.get_object(win_id)
    window.show_all()

    Gtk.main()

if __name__ == '__main__':
    main("desima-gui.glade", "winDesima")


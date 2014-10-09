#!/usr/bin/env python3
"""Create a custom installation of Apache and MySQL for the current user"""

from os.path import join
from os import mkdir
from subprocess import check_call

from .utils import (is_valid_site_id, sdo, DB, STOP, find_site, site_directory,
                    find_site, ISRUNNING, WWW)

from .mysql import mysql_install
from .pgsql import pgsql_install
from .apache2 import apache2_install
from .application import application_install

def site_install(site_id, port, www_type, db_type, application_file):
    """Create a site with standalone Apache2 and MySQL installation"""
    assert db_type in ['mysql', 'pgsql']
    assert www_type in ['apache2']

    if not is_valid_site_id(site_id):
        raise ValueError('Invalid site ID, must be [a-zA-Z][a-zA-Z0-9_]{0,23}')

    if find_site(site_id):
        raise ValueError("Site {site} already exists".format(site=site_id))

    # Create directory for the new site
    directory_name = site_directory(site_id)
    mkdir(directory_name)

    # Create the port file
    with open(join(directory_name, 'PORT'), 'w') as port_file:
        port_file.write(str(port))

    # Select the specified database and www server
    db_install = {
        'mysql': mysql_install,
        'pgsql': pgsql_install
    }[db_type]

    www_install = {
        'apache2': apache2_install
    }[www_type]

    db_install(site_id, port, directory_name)
    www_install(site_id, port, directory_name)

    if application_file != None:
        application_install(site_id, application_file)

def remove_site(site_id):
    """Completely remove a site after ensuring the servers were stopped."""
    if not is_valid_site_id(site_id):
        raise ValueError('Invalid site ID, must be [a-zA-Z][a-zA-Z0-9_]{0,23}')

    if not find_site(site_id):
        raise ValueError("Site {site} unknown".format(site=site_id))

    # Stop servers
    if sdo(ISRUNNING, WWW, site_id):
        sdo(STOP, WWW, site_id)

    if sdo(ISRUNNING, DB, site_id):
        sdo(STOP, DB, site_id)

    # Delete all files belonging to the site
    directory_name = site_directory(site_id)

    # Ensures that everything can be deleted inside the directory
    check_call(['chmod', '-R', 'u+w', directory_name])
    check_call(['rm', '-Rf', directory_name])


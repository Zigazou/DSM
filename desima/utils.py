#!/usr/bin/env python3
"""Create a custom installation of Apache and MySQL for the current user"""

from os.path import expanduser, isdir, join, dirname
from os import listdir, getuid, chmod, devnull, environ, pathsep
from pwd import getpwuid
from subprocess import call
from glob import glob
from re import compile as rcompile
from zipfile import is_zipfile, ZipFile
from tarfile import is_tarfile, open as taropen
from string import Template
from itertools import chain

DEVNULL = open(devnull, "w")
BASE = expanduser("~/www")
USERNAME = getpwuid(getuid())[0]
(PORT_MIN, PORT_MAX, PORT_STEP) = (10000, 10100, 3) # 0=HTTP, 1=HTTPS, 2=DB

(START, STOP, ISRUNNING) = ('start', 'stop', 'isrunning')
(WWW, DB) = ('www', 'db')

SITE_FORMAT = rcompile(r'^site-\w+$')
VALID_SITE_ID = rcompile(r'^[a-zA-Z]\w{0,23}$')
APPLICATION_FORMAT = rcompile(r'^(.*)\.(tar\.gz|tar\.bz2|zip)$')

def is_valid_site_id(site_id):
    """Check if a site identifier is valid."""
    return VALID_SITE_ID.match(site_id)

def bash_prelude():
    """Returns the full path to the Bash prelude script."""
    return join(BASE, 'bin', 'bashprelude')

def get_bin_directory(executable, hints):
    """Try to find the directory of an executable event if it's not in PATH."""
    bin_paths = environ["PATH"].split(pathsep)
    full_paths = [glob(join(path, executable)) for path in bin_paths + hints]
    founds = list(chain(*full_paths))

    if not founds:
        return None
    else:
        return dirname(founds[0])

def list_sites():
    """Return a list of sites"""
    return [entry.split('-')[1]
            for entry in listdir(BASE)
            if isdir(entry) and SITE_FORMAT.match(entry)]

def site_directory(site_id):
    """Returns the full path to a directory site"""
    return join(BASE, "site-{i}".format(i=site_id))

def site_port(site_id):
    """Returns the port of a site given its site_id"""
    return int(open(join(site_directory(site_id), 'PORT')).read(1000))

def sdo(action, server, site_id):
    """Execute an action (start, stop, isrunning) script on a server
       (db, www)"""
    assert server in ['db', 'www']
    assert action in ['start', 'stop', 'isrunning']
    assert is_valid_site_id(site_id)

    return 0 == call([join(site_directory(site_id), server + '.' + action)])

def sites_states():
    """Returns a list of sites with their states"""
    return [
        (site_id,
         site_port(site_id),
         sdo(ISRUNNING, WWW, site_id),
         sdo(ISRUNNING, DB, site_id)
        )
        for site_id in list_sites()
    ]

def find_unused_port():
    """Find the first unused port among the authorized ports and the already
       used ports."""

    used_ports = [port for (_, port, _, _) in sites_states()]
    port_range = range(PORT_MIN, PORT_MAX, PORT_STEP)

    return next(port for port in port_range if port not in used_ports)

def find_site(site_id):
    """Find a site given its site_id"""
    return site_id in list_sites()

def get_template(template):
    """Returns a Template object from a template file in the template dir"""
    return Template(open(join(BASE, 'template', template)).read(65536))

def template_to_file(template, dest, values, mode):
    """Generate a file based on a template and a list of (key, values)"""
    with open(dest, 'w') as dest_file:
        dest_file.write(get_template(template).safe_substitute(values))

    chmod(dest, mode)

def templates_to_files(files, tokens, directory_name):
    """Apply template_to_file to a list of templates"""
    tokens['BASHPRELUDE'] = bash_prelude()
    for (template, destination, rights) in files:
        template_to_file(
            template,
            join(directory_name, destination),
            tokens,
            rights
        )

def get_root_directory(filename):
    """Detects if the archive has a root directory or not"""
    if is_zipfile(filename):
        members = [member.filename for member in ZipFile(filename).infolist()]
    elif is_tarfile(filename):
        members = [member.name for member in taropen(filename).getmembers()]
    else:
        return None

    root_directory = members[0]
    if root_directory[-1] != '/':
        root_directory = root_directory + '/'

    for member in members[1:]:
        if not member.startswith(root_directory):
            return None

    return root_directory


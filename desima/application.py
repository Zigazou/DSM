#!/usr/bin/env python3
"""Create a custom installation of Apache and MySQL for the current user"""

from os.path import isfile, join, splitext
from os import listdir, rmdir, rename
from subprocess import check_call
from string import capwords

from .utils import (APPLICATION_FORMAT, BASE, is_valid_site_id, DEVNULL,
                    get_root_directory, site_directory)

def extract_application(filename, base_dir):
    """Given an archive filename and a directory, returns a tuple containing
       a human name for the archive and the absolute path of it."""
    result = APPLICATION_FORMAT.match(filename)
    if result == None:
        return None

    human_name = result.group(1).replace('-', ' ').replace('_', ' ')
    human_name = capwords(human_name)

    return (human_name, join(base_dir, filename))

def list_applications():
    """Return a list of applications in the application subdirectory."""
    base_dir = join(BASE, 'application')
    return [extract_application(application, base_dir)
            for application in listdir(base_dir)
            if isfile(join(base_dir, application))
            and extract_application(application, base_dir) != None
           ]

def application_install(site_id, application_file):
    """Extract contents of an archive into the doc subdirectory of the web
       server."""
    assert isfile(application_file)
    assert splitext(application_file)[1] in ['.gz', '.bz2', '.zip']
    assert is_valid_site_id(site_id)

    # Identifies the archive type
    arc_types = {
        '.gz': {'cmd': 'tar', 'opt': 'xzf', 'dest': '--directory'},
        '.bz2': {'cmd': 'tar', 'opt': 'xjf', 'dest': '--directory'},
        '.zip': {'cmd': 'unzip', 'opt': '-q', 'dest': '-d'}
    }

    arc_type = arc_types[splitext(application_file)[1]]
    root_directory = get_root_directory(application_file)
    www_dir = join(site_directory(site_id), 'www')
    doc_dir = join(www_dir, 'doc')

    if root_directory == None:
        destination = doc_dir
    else:
        destination = www_dir

    # Extract application
    check_call(
        [arc_type['cmd'],
         arc_type['opt'],
         application_file,
         arc_type['dest'], destination],
        stdout=DEVNULL
    )

    if root_directory != None:
        # Move application to the doc directory
        rmdir(doc_dir)
        rename(join(destination, root_directory), doc_dir)


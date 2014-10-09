#!/usr/bin/env python3
"""Create a custom installation of Apache and MySQL for the current user"""

from os.path import join
from os import mkdir
from stat import S_IRUSR, S_IWUSR, S_IXUSR
from subprocess import check_output

from .utils import (get_bin_directory, is_valid_site_id, site_directory,
                    USERNAME, templates_to_files)

def apache_version():
    """Return the Apache version (2.2 configuration is slightly different from
       2.4 configuration)
    """
    output = str(check_output(['apache2', '-v']))

    versions = {True: '2.2', False: '2.4'}
    return versions[output.find('Apache/2.2.') >= 0]

def apache2_bin_directory():
    """Return Apache2 bin directory"""
    return get_bin_directory('apache2', ['/usr/sbin'])

def apache2_log_file(site_id):
    """Return a list of full path to Apache2 log files."""
    assert is_valid_site_id(site_id)

    directory_name = site_directory(site_id)
    return [join(directory_name, 'www', 'log', 'apache2_error.log'),
            join(directory_name, 'www', 'log', 'apache2_access.log')]

def apache2_install(site_id, port, directory_name):
    """Create a standalone Apache2 installation"""
    assert is_valid_site_id(site_id)

    # Define directories
    serverroot = join(directory_name, 'www')
    logdir = join(serverroot, 'log')
    lockdir = join(serverroot, 'lock')
    rundir = join(serverroot, 'run')
    docdir = join(serverroot, 'doc')

    # Create directories
    for directory in [serverroot, logdir, lockdir, rundir, docdir]:
        mkdir(directory)

    # Tokens
    tokens = {
        'DAEMON': join(apache2_bin_directory(), 'apache2'),
        'SERVERROOT': serverroot,
        'SERVERNAME': '{user}-{site}'.format(user=USERNAME, site=site_id),
        'HTTP_PORT': port,
        'HTTPS_PORT': port + 1,
        'USER': USERNAME,
        'GROUP': USERNAME,
        'LOCKDIR': lockdir,
        'LOCKFILE': 'accept.lock',
        'PIDPATH': join(rundir, 'apache.pid'),
        'LOGDIR': logdir,
        'ERRLOGFILE': 'apache2_error.log',
        'ACCLOGFILE': 'apache2_access.log',
        'SITE': site_id,
        'CONFPATH': join(directory_name, 'apache2.conf')
    }

    template_filename = 'apache2/{v}.conf.template'.format(v=apache_version())

    rewr = S_IRUSR | S_IWUSR
    rewx = rewr | S_IXUSR

    files = [
        (template_filename, 'apache2.conf', rewr),
        ('apache2/start.template', 'www.start', rewx),
        ('apache2/stop.template', 'www.stop', rewx),
        ('apache2/isrunning.template', 'www.isrunning', rewx)
    ]

    templates_to_files(files, tokens, directory_name)


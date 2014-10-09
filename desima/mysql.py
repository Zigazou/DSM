#!/usr/bin/env python3
"""Create a custom installation of Apache and MySQL for the current user"""

from os.path import join
from os import mkdir
from stat import S_IREAD, S_IEXEC
from subprocess import check_call, Popen, PIPE

from .utils import (is_valid_site_id, get_template, sdo, START, DB, DEVNULL,
                    STOP, site_directory, BASE, USERNAME, templates_to_files)

def mysql_create_user(site_id, mysql_config_filename):
    """Create default database with default user"""
    assert is_valid_site_id(site_id)

    tokens = {'DATABASE': site_id, 'USER': site_id, 'PASSWORD': site_id}
    script = get_template('mysql/create.template').safe_substitute(tokens)

    # Start the server
    sdo(START, DB, site_id)

    # Create the default database
    mysql = Popen(
        ['mysql', '--defaults-file=' + mysql_config_filename, '--user=root'],
        stdout=DEVNULL,
        stdin=PIPE,
        stderr=DEVNULL
    )

    mysql.communicate(input=bytes(script, 'ASCII'))

    # Stop the server
    sdo(STOP, DB, site_id)

def mysql_log_file(site_id):
    """Return a list of full path to MySQL log files."""
    assert is_valid_site_id(site_id)

    directory_name = site_directory(site_id)
    return [join(directory_name, 'db', 'log', 'mysql_error.log')]

def mysql_install(site_id, port, directory_name):
    """Create a standalone MySQL installation"""
    assert is_valid_site_id(site_id)

    dbdir = join(directory_name, 'db')
    logdir = join(dbdir, 'log')
    rundir = join(dbdir, 'run')
    datadir = join(dbdir, 'data')
    mysql_config_filename = join(directory_name, 'mysql.conf')

    # Create directories
    for directory in (dbdir, rundir, logdir, datadir):
        mkdir(directory)

    # Tokens
    tokens = {
        'DAEMON': join(BASE, 'bin', 'mysqld'),
        'CONFPATH': mysql_config_filename,
        'SITE': site_id,
        'LOGDIR': logdir,
        'LOGFILE': 'mysql_error.log',
        'LOGPATH': join(logdir, 'mysql_error.log'),
        'SOCKPATH': join(rundir, 'mysqld.sock'),
        'PIDPATH': join(rundir, 'mysqld.pid'),
        'DATADIR': datadir,
        'PORT': port + 2,
        'USER': USERNAME,
        'DBDIR' : dbdir,
        'DIRECTORY': directory_name,
        'ID': port
    }

    files = [
        ('mysql/conf.template', 'mysql.conf', S_IREAD),
        ('mysql/start.template', 'db.start', S_IREAD | S_IEXEC),
        ('mysql/stop.template', 'db.stop', S_IREAD | S_IEXEC),
        ('mysql/isrunning.template', 'db.isrunning', S_IREAD | S_IEXEC)
    ]

    templates_to_files(files, tokens, directory_name)

    # Install MySQL system tables
    mysql_install_db = join(BASE, 'bin', 'mysql_install_db')

    check_call(
        [mysql_install_db, '--defaults-file=' + mysql_config_filename],
        stdout=DEVNULL
    )

    mysql_create_user(site_id, mysql_config_filename)


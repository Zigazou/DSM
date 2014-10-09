#!/usr/bin/env python3
"""Create a custom installation of Apache and MySQL for the current user"""

from os.path import join
from os import mkdir
from stat import S_IRUSR, S_IXUSR, S_IWUSR
from subprocess import check_call, Popen, PIPE

from .utils import (is_valid_site_id, get_template, sdo, START, DB, DEVNULL,
                    STOP, USERNAME, templates_to_files, get_bin_directory)

def pgsql_bin_directory():
    """Return PostgreSQL bin directory"""
    return get_bin_directory(
        'postgres',
        ['/usr/local/pgsql/bin',
         '/usr/lib/postgresql/*/bin',
         '/opt/pgsql-*/bin',
         '/Library/PostgreSQL/*',
         '/Applications/Postgres.app/Contents/MacOS/bin',
         '/opt/local/lib/postgresql*/bin']
    )

def pgsql_install(site_id, port, directory_name):
    """Create a standalone MySQL installation"""
    assert is_valid_site_id(site_id)

    pgsql_bin_dir = pgsql_bin_directory()
    if pgsql_bin_dir == None:
        return

    dbdir = join(directory_name, 'db')
    logdir = join(dbdir, 'log')
    rundir = join(dbdir, 'run')
    datadir = join(dbdir, 'data')
    pgsql_config_filename = join(directory_name, 'pgsql.conf')

    # Create directories
    for directory in (dbdir, rundir, logdir, datadir):
        mkdir(directory)

    # Tokens
    tokens = {
        'DAEMON': join(pgsql_bin_dir, 'postgres'),
        'CONFPATH': pgsql_config_filename,
        'SITE': site_id,
        'RUNDIR': rundir,
        'LOGDIR': logdir,
        'LOGFILE': 'pgsql_error.log',
        'LOGPATH': join(logdir, 'pgsql_error.log'),
        'SOCKPATH': join(rundir, 'pgsqld.sock'),
        'PIDPATH': join(rundir, 'pgsqld.pid'),
        'DATADIR': datadir,
        'PORT': port + 2,
        'USER': USERNAME,
        'DBDIR' : dbdir,
        'DIRECTORY': directory_name,
        'ID': port
    }

    # Install MySQL system tables
    check_call(
        [join(pgsql_bin_dir, 'initdb'),
         '--pgdata=' + datadir,
         '--username=' + USERNAME],
        stdout=DEVNULL
    )

    rewr = S_IRUSR | S_IWUSR
    rewx = rewr | S_IXUSR

    files = [
        ('pgsql/conf.template', 'db/data/postgresql.conf', rewr),
        ('pgsql/pg_ident.conf.template', 'db/data/pg_ident.conf', rewr),
        ('pgsql/pg_hba.conf.template', 'db/data/pg_hba.conf', rewr),
        ('pgsql/start.template', 'db.start', rewx),
        ('pgsql/stop.template', 'db.stop', rewx),
        ('pgsql/isrunning.template', 'db.isrunning', rewx)
    ]

    templates_to_files(files, tokens, directory_name)


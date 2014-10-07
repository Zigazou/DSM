#!/usr/bin/env python3
"""Create a custom installation of Apache and MySQL for the current user"""

from os.path import expanduser, isdir, isfile, join, splitext, dirname
from os import (listdir, mkdir, rmdir, getuid, chmod, devnull, rename, X_OK,
                environ, pathsep)
from stat import S_IREAD, S_IEXEC
from pwd import getpwuid
from subprocess import check_call, check_output, call, Popen, PIPE
from glob import glob
from sys import argv, exit as sysexit
from re import compile as rcompile
from string import capwords
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

def is_valid_site_id(site_id):
    """Check if a site identifier is valid."""
    return VALID_SITE_ID.match(site_id)

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
    for (template, destination, rights) in files:
        template_to_file(
            template,
            join(directory_name, destination),
            tokens,
            rights
        )

def apache_version():
    """Return the Apache version (2.2 configuration is slightly different from
       2.4 configuration)
    """
    output = str(check_output(['apache2', '-v']))

    versions = {True: '2.2', False: '2.4'}
    return versions[output.find('Apache/2.2.') >= 0]

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

def pgsql_bin_directory():
    return get_bin_directory(
        'postgres',
        ['/usr/local/pgsql/bin',
         '/usr/lib/postgresql/*/bin',
         '/opt/pgsql-*/bin',
         '/Library/PostgreSQL/*',
         '/Applications/Postgres.app/Contents/MacOS/bin',
         '/opt/local/lib/postgresql*/bin']
    )

def pgsql_create_user(site_id, pgsql_config_filename):
    """Create default database with default user"""
    assert is_valid_site_id(site_id)

    tokens = {'DATABASE': site_id, 'USER': site_id, 'PASSWORD': site_id}
    script = get_template('pgsql/create.template').safe_substitute(tokens)

    # Start the server
    sdo(START, DB, site_id)

    # Create the default database
    pgsql = Popen(
        ['psql', '--defaults-file=' + pgsql_config_filename, '--user=root'],
        stdout=DEVNULL,
        stdin=PIPE,
        stderr=DEVNULL
    )

    pgsql.communicate(input=bytes(script, 'ASCII'))

    # Stop the server
    sdo(STOP, DB, site_id)

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

    files = [
        ('pgsql/conf.template', 'db/data/postgresql.conf', S_IREAD),
        ('pgsql/pg_ident.conf.template', 'db/data/pg_ident.conf', S_IREAD),
        ('pgsql/pg_hba.conf.template', 'db/data/pg_hba.conf', S_IREAD),
        ('pgsql/start.template', 'db.start', S_IREAD | S_IEXEC),
        ('pgsql/stop.template', 'db.stop', S_IREAD | S_IEXEC),
        ('pgsql/isrunning.template', 'db.isrunning', S_IREAD | S_IEXEC)
    ]

    templates_to_files(files, tokens, directory_name)

    #pgsql_create_user(site_id, pgsql_config_filename)

def apache2_bin_directory():
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

    files = [
        (template_filename, 'apache2.conf', S_IREAD),
        ('apache2/start.template', 'www.start', S_IREAD | S_IEXEC),
        ('apache2/stop.template', 'www.stop', S_IREAD | S_IEXEC),
        ('apache2/isrunning.template', 'www.isrunning', S_IREAD | S_IEXEC)
    ]

    templates_to_files(files, tokens, directory_name)

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

def command_list(_):
    """Show a list of servers and their states to the user."""
    server_state = {True: 'running', False: 'stopped'}
    for (site_id, port, www, database) in sites_states():
        print('{id}({port}): www {www}, db {db}'.format(
            id=site_id,
            port=port,
            www=server_state[www],
            db=server_state[database]
        ))

def command_remove(args):
    """Remove a site specified by the user."""
    if len(args) != 1:
        raise ValueError('The remove command needs a site identifier')

    remove_site(args[0])

def command_help(_):
    """Show help to the user."""
    tokens = {
        'PORTMINI': PORT_MIN,
        'PORTMAXI': PORT_MAX,
        'SITEID': VALID_SITE_ID.pattern
    }

    print(get_template('help.template').safe_substitute(tokens))

def command_install(args):
    """Install a new site as specified by the user."""
    if len(args) < 3 or len(args) > 4:
        raise ValueError('The install command needs a new site identifier')

    application_file = None
    if len(args) == 4:
        application_file = args[3]

    site_install(
        args[0],
        find_unused_port(),
        args[1],
        args[2],
        application_file
    )

def command_line(command_args):
    """Interpret command line"""
    commands = {
        'list': command_list,
        'install': command_install,
        'remove': command_remove,
        'help': command_help
    }

    (command, args) = ('help', [])
    if len(command_args) >= 1 and command_args[0] in commands:
        (command, args) = (command_args[0], command_args[1:])

    try:
        commands[command](args)
    except ValueError as err:
        print('ERROR: {message}'.format(message=err.args[0]))
        sysexit(1)

if __name__ == '__main__':
    command_line(argv[1:])
    sysexit(0)


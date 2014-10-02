#!/usr/bin/env python3
"""Create a custom installation of Apache and MySQL for the current user"""

from os.path import expanduser, isdir, isfile, join, splitext
from os import listdir, mkdir, rmdir, getuid, chmod, devnull, rename
from stat import S_IREAD, S_IEXEC
from pwd import getpwuid
from subprocess import check_call, check_output, call, Popen, PIPE
from sys import argv, exit as sysexit
from re import compile as rcompile
from string import capwords
from zipfile import is_zipfile, ZipFile
from tarfile import is_tarfile, open as taropen

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

def generate_configuration(template, values):
    """Replace tags in string with their actual value"""

    for (key, value) in values:
        template = template.replace('***{key}***'.format(key=key), str(value))

    return template

def template_to_file(template, dest, values, mode):
    """Generate a file based on a template and a list of (key, values)"""
    template = join(BASE, 'template', template)

    with open(dest, 'w') as dest_file:
        dest_file.write(
            generate_configuration(open(template).read(65536), values)
        )

    chmod(dest, mode)

def apache_version():
    """Return the Apache version (2.2 configuration is slightly different from
       2.4 configuration)
    """
    output = str(check_output(['apache2', '-v']))

    versions = {True: '2.2', False: '2.4'}
    return versions[output.find('Apache/2.2.') >= 0]

def create_default_user(site_id, mysql_config_filename):
    """Create default database with default user"""
    script = "\n".join([
        "CREATE DATABASE {db};",
        "GRANT ALL ON {db}.* TO {user}@127.0.0.1 IDENTIFIED BY '{pwd}';",
        "FLUSH PRIVILEGES;",
        ""
    ]).format(db=site_id, user=site_id, pwd=site_id)

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
    directory_name = site_directory(site_id)
    return [join(directory_name, 'db', 'log', 'mysql_error.log')]

def install_mysql(site_id, port, directory_name):
    """Create a standalone MySQL installation"""

    # Create directories
    mkdir(join(directory_name, 'db'))
    mkdir(join(directory_name, 'db', 'run'))
    mkdir(join(directory_name, 'db', 'log'))

    mysql_config_filename = join(directory_name, 'mysql.conf')

    # Tokens
    tokens = [
        ('MYSQLD', join(BASE, 'bin', 'mysqld')),
        ('MYSQLCONF', mysql_config_filename),
        ('SITE', site_id),
        ('LOGFILE', join(directory_name, 'db', 'log', 'mysqld.log')),
        ('PIDFILE', join(directory_name, 'db', 'run', 'mysqld.pid')),
        ('PORT', port + 2),
        ('USER', USERNAME),
        ('DIRECTORY', directory_name),
        ('ID', port)
    ]

    files = [
        ('mysql.conf.template', 'mysql.conf', S_IREAD),
        ('mysql.start.template', 'db.start', S_IREAD | S_IEXEC),
        ('mysql.stop.template', 'db.stop', S_IREAD | S_IEXEC),
        ('mysql.isrunning.template', 'db.isrunning', S_IREAD | S_IEXEC)
    ]

    for (template, destination, rights) in files:
        template_to_file(
            template,
            join(directory_name, destination),
            tokens,
            rights
        )

    # Install MySQL system tables
    mysql_install_db = join(BASE, 'bin', 'mysql_install_db')

    check_call(
        [mysql_install_db, '--defaults-file=' + mysql_config_filename],
        stdout=DEVNULL
    )

    create_default_user(site_id, mysql_config_filename)

def apache2_log_file(site_id):
    """Return a list of full path to Apache2 log files."""
    directory_name = site_directory(site_id)
    return [join(directory_name, 'www', 'log', 'apache2_error.log'),
            join(directory_name, 'www', 'log', 'apache2_access.log')]

def install_apache2(site_id, port, directory_name):
    """Create a standalone Apache2 installation"""

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
    tokens = [
        ('SERVERROOT', serverroot),
        ('SERVERNAME', '{user}-{site}'.format(user=USERNAME, site=site_id)),
        ('HTTP_PORT', port),
        ('HTTPS_PORT', port + 1),
        ('USER', USERNAME),
        ('GROUP', USERNAME),
        ('LOCKDIR', lockdir),
        ('PIDFILE', join(rundir, 'apache.pid')),
        ('LOGDIR', logdir),
        ('SITE', site_id),
        ('APACHECONF', join(directory_name, 'apache2.conf'))
    ]

    template_filename = 'apache{v}.conf.template'.format(v=apache_version())

    files = [
        (template_filename, 'apache2.conf', S_IREAD),
        ('apache2.start.template', 'www.start', S_IREAD | S_IEXEC),
        ('apache2.stop.template', 'www.stop', S_IREAD | S_IEXEC),
        ('apache2.isrunning.template', 'www.isrunning', S_IREAD | S_IEXEC)
    ]

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
        return None

    for member in members:
        if not member.startswith(root_directory):
            return None

    return root_directory

def install_application(site_id, application_file):
    """Extract contents of an archive into the doc subdirectory of the web
       server."""
    assert isfile(application_file)
    assert splitext(application_file)[1] in ['.gz', '.bz2', '.zip']

    # Identifies the archive type
    arc_types = {
        '.gz': {'cmd': 'tar', 'opt': 'xzf', 'dest': '--directory'},
        '.bz2': {'cmd': 'tar', 'opt': 'xjf', 'dest': '--directory'},
        '.zip': {'cmd': 'unzip', 'opt': '-q', 'dest': '-d'}
    }

    arc_type = arc_types[splitext(application_file)[1]]
    root_directory = get_root_directory(application_file)
    destination = join(site_directory(site_id), 'www')

    if root_directory == None:
        destination = join(destination, 'doc')

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
        doc_dir = join(destination, 'doc')
        rmdir(doc_dir)
        rename(join(destination, root_directory), doc_dir)

def install_site(site_id, port, application_file):
    """Create a site with standalone Apache2 and MySQL installation"""
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

    install_mysql(site_id, port, directory_name)
    install_apache2(site_id, port, directory_name)

    if application_file != None:
        install_application(site_id, application_file)

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
    help_message = [
        "DeSiMa is for Dev Sites Manager: it manages developer's sites.",
        "",
        "It creates Apache2 (2.2 and 2.4) and MySQL instances running as the",
        "current user. It thus does not require the developer to modify its",
        "system configuration. The sites created with DSM use port numbers",
        "between {mini} and {maxi}.".format(mini=PORT_MIN, maxi=PORT_MAX),
        "",
        "DeSiMa contains special code to get around AppArmor limitations on",
        "MySQL under Ubuntu. It also keeps WWW files and DB files under the",
        "same directory. It requires Python3 to run.",
        "",
        "It is command driven:",
        "    - help              --> this help",
        "    - list              --> list all sites and their running states",
        "    - install <site_id> --> create a new site (HTTP and DB)",
        "    - remove <site_id>  --> remove a site",
        "",
        "WARNING: DeSiMa is for developer's environment ONLY! It must not be",
        "         used in production environment.",
        ""
    ]

    print('\n'.join(help_message))

def command_install(args):
    """Install a new site as specified by the user."""
    if len(args) != 1:
        raise ValueError('The install command needs a new site identifier')

    install_site(args[0], find_unused_port(), None)

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


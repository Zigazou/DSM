#!/usr/bin/env python3
"""Create a custom installation of Apache and MySQL for the current user"""

from os.path import expanduser, isdir, join
from os import listdir, mkdir, getuid, chmod, devnull
from stat import S_IREAD, S_IEXEC
from pwd import getpwuid
from subprocess import check_call, check_output, call, Popen, PIPE
from sys import argv, exit
from re import compile as rcompile

DEVNULL = open(devnull, "w")
BASE = expanduser("~/www")
USERNAME = getpwuid(getuid())[0]
(PORT_MIN, PORT_MAX, PORT_STEP) = (10000, 10100, 3) # 0=HTTP, 1=HTTPS, 2=DB

(START, STOP, ISRUNNING) = ('start', 'stop', 'isrunning')
(WWW, DB) = ('www', 'db')

SITE_FORMAT = rcompile(r'^site-\w+-\d{4,5}$')
VALID_SITE_ID = rcompile(r'^[a-zA-Z]\w{0,23}$')

def is_valid_site_id(site_id):
    return VALID_SITE_ID.match(site_id)

def list_sites():
    """Return a list of sites"""
    return [(entry.split('-')[1], int(entry.split('-')[2]))
            for entry in listdir(BASE)
            if isdir(entry) and SITE_FORMAT.match(entry)]

def site_directory(site_id, port):
    """Returns the full path to a directory site"""
    return join(BASE, "site-{i}-{p}".format(i=site_id, p=port))

def sdo(action, server, site_id, port):
    """Execute an action (start, stop, isrunning) script on a server
       (db, www)"""
    assert server in ['db', 'www']
    assert action in ['start', 'stop', 'isrunning']

    return 0 == call([join(
        site_directory(site_id, port),
        server + '.' + action
    )])

def sites_states():
    """Returns a list of sites with their states"""
    return [
        (site_id,
         port,
         sdo(ISRUNNING, WWW, site_id, port),
         sdo(ISRUNNING, DB, site_id, port)
        )
        for (site_id, port) in list_sites()
    ]

def find_unused_port():
    """Find the first unused port among the authorized ports and the already
       used ports."""

    used_ports = [port for (_, port) in list_sites()]
    port_range = range(PORT_MIN, PORT_MAX, PORT_STEP)

    return next(port for port in port_range if port not in used_ports)

def find_site(identifier):
    """Find a site given its site_id"""
    sites = [(site_id, port) for (site_id, port) in list_sites()
                             if site_id == identifier]

    if len(sites) == 1:
        return sites[0]
    else:
        return None

def generate_configuration(template, values):
    """Replace tags in string with their actual value"""

    for (key, value) in values:
        template = template.replace('***{key}***'.format(key=key), str(value))

    return template

def template_to_file(template, dest, values, mode):
    """Generate a file based on a template and a list of (key, values)"""
    template = join(BASE, 'template', template)

    dest_file = open(dest, 'w')
    dest_file.write(generate_configuration(open(template).read(65536), values))
    dest_file.close()
    chmod(dest, mode)

def apache_version():
    """Return the Apache version (2.2 configuration is slightly different from
       2.4 configuration)
    """
    output = str(check_output(['apache2', '-v']))

    versions = {True: '2.2', False: '2.4'}
    return versions[output.find('Apache/2.2.') >= 0]

def create_default_user(site_id, port, mysql_config_filename):
    """Create default database with default user"""
    script = "\n".join([
        "CREATE DATABASE {db};",
        "GRANT ALL ON {db}.* TO {user}@127.0.0.1 IDENTIFIED BY '{pwd}';",
        "FLUSH PRIVILEGES;",
        ""
    ]).format(db=site_id, user=site_id, pwd=site_id)

    # Start the server
    sdo(START, DB, site_id, port)

    # Create the default database
    mysql = Popen(
        ['mysql', '--defaults-file=' + mysql_config_filename, '--user=root'],
        stdout=DEVNULL,
        stdin=PIPE,
        stderr=DEVNULL
    )

    mysql.communicate(input=bytes(script, 'ASCII'))

    # Stop the server
    sdo(STOP, DB, site_id, port)

def mysql_log_file(site_id, port):
    directory_name = site_directory(site_id, port)
    return [join(directory_name, 'db', 'log', 'mysql_error.log')]

def install_mysql(site_id, port, directory_name):
    """Create a standalone MySQL installation"""

    # Create directories
    mkdir(join(directory_name, 'db'))
    mkdir(join(directory_name, 'db', 'run'))
    mkdir(join(directory_name, 'db', 'log'))

    pidfile = join(directory_name, 'db', 'run', 'mysqld.pid')
    logfile = join(directory_name, 'db', 'log', 'mysqld.log')

    # Create MySQL configuration file
    mysql_config_filename = join(directory_name, 'mysql.conf')
    template_to_file(
        'mysql.conf.template',
        mysql_config_filename,
        [('PORT', port + 2),
         ('USER', USERNAME),
         ('DIRECTORY', directory_name),
         ('ID', port)
        ],
        S_IREAD
    )

    # Install MySQL system tables
    mysql_install_db = join(BASE, 'bin', 'mysql_install_db')

    check_call(
        [mysql_install_db, '--defaults-file=' + mysql_config_filename],
        stdout=DEVNULL
    )

    # Tokens
    tokens = [
        ('MYSQLD', join(BASE, 'bin', 'mysqld')),
        ('MYSQLCONF', mysql_config_filename),
        ('SITE', site_id),
        ('LOGFILE', logfile),
        ('PIDFILE', pidfile)
    ]

    files = [
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

    create_default_user(site_id, port, mysql_config_filename)

def apache2_log_file(site_id, port):
    directory_name = site_directory(site_id, port)
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

    pidfile = join(rundir, 'apache.pid')

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
        ('PIDFILE', pidfile),
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

def install_site(site_id, port):
    """Create a site with standalone Apache2 and MySQL installation"""
    if not is_valid_site_id(site_id):
        raise ValueError('Invalid site ID, must be [a-zA-Z][a-zA-Z0-9_]{0,23}')

    site = find_site(site_id)

    if site != None:
        raise ValueError("Site {site} already exists".format(site=site_id))

    # Create directory for the new site
    directory_name = site_directory(site_id, port)
    mkdir(directory_name)

    install_mysql(site_id, port, directory_name)
    install_apache2(site_id, port, directory_name)

def remove_site(site_id):
    if not is_valid_site_id(site_id):
        raise ValueError('Invalid site ID, must be [a-zA-Z][a-zA-Z0-9_]{0,23}')

    site = find_site(site_id)

    if site == None:
        raise ValueError("Site {site} unknown".format(site=site_id))

    # Stop servers

    # Delete all files belonging to the site

def command_list(args):
    server_state = { True: 'running', False: 'stopped'}
    for (site_id, port, www, db) in sites_states():
        print('{id}({port}): www {www}, db {db}'.format(
            id=site_id,
            port=port,
            www=server_state[www],
            db=server_state[db]
        ))

def command_remove(args):
    raise NotImplementedError('remove command not implemented')

def command_help(args):
    help = [
        'DSM is for Dev Sites Manager: it manages developer’s sites.',
        '',
        'It creates Apache2 (2.2 and 2.4) and MySQL instances running as the',
        'current user. It thus does not require the developer to modify its',
        'system configuration. The sites created with DSM use port numbers',
        'between {mini} and {maxi}.'.format(mini=PORT_MIN, maxi=PORT_MAX),
        '',
        'DSM contains special code to get around AppArmor limitations on',
        'MySQL under Ubuntu. It also keeps WWW files and DB files under the',
        'same directory. It requires Python3 to run.',
        '',
        'It is command driven:',
        '    - help              --> this help',
        '    - list              --> list all sites and their running states',
        '    - install <site_id> --> create a new site (HTTP and DB)',
        '    - remove <site_id>  --> remove a site',
        '',
        'WARNING: DSM is for developer’s environment ONLY ! It must not be',
        '         used in production environment.',
        ''
    ]

    print('\n'.join(help))

def command_install(args):
    if len(args) != 1:
        raise ValueError('The install command needs a new site identifier')

    install_site(args[0], find_unused_port())

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
        exit(1)

if __name__ == '__main__':
    command_line(argv[1:])
    exit(0)


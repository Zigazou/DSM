DSM
===

developer’s Sites Manager (or DSM) allows the developer to manage a
collection of sites meant for development purposes

**WARNING**: DSM is for developer’s environment ONLY! It must not be
used in production environment, you’ve been warned.

Requirements
------------

DSM has been developped under Ubuntu 12.04/14.04 and is targeted at Linux
platform.

It uses :

- Python 3.2+
- MySQL
- Apache 2.2 or 2.4
- Notify-send

You can do a basic verification by running the requirements script.

At the moment, DSM works only in the ~/www directory (right at the root of your
home directory).

Before running DSM, you must populate the bin directory by running

    instbin bin

in the ~/www directory.

How it works
------------

It creates Apache2 (2.2 and 2.4) and MySQL instances running as the current
user (1 site = 1 Apache2 instance + 1 MySQL instance). It thus does not require
the developer to modify its system configuration. The sites created with DSM
use port numbers between 10000 and 10100.

It also creates a default database with the site identifier, using it also as
the database user and password.

DSM contains special code to get around AppArmor limitations on MySQL under 
Ubuntu. It also keeps WWW files and DB files under the same directory. It
requires Python3 to run.

It is command driven:

- help → this help
- list → list all sites and their running states
- install <site_id> → create a new site (HTTP and DB)
- remove <site_id> → remove a site (not yet implemented)

Example
-------

Place yourself in the ~/www directory:

    ./dsm.py install site1
    ./dsm.py install site2

You should have 2 directories created:

- site-site1-10000
- site-site2-10003

You may verify it with the following command:

    ./dsm.py list

In each of these directories are scripts for running and stopping servers:

- db.start: start the database
- db.stop: stop the database
- www.start: start the web server
- www.stop: stop the web server

You will also find subdirectories:

- db: will hold everything related to the database (tables, log…)
- www: will hold everything related to the web server (files, log…)

You should place PHP and HTML files in the www/doc subdirectory.

GUI
---

You can use dsm-gui.py to have a GUI for DSM.

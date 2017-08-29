#!/usr/bin/env python
# -*- coding: utf-8 -*-

""":Mod: fabfile

:Synopsis:

    eval `ssh-agent`
    ssh-add $HOME/.ssh/<priv_key>
    fab deploy_gmn -H <host>

    or

    Fabric script to deploy a DataONE Metacat Member Node
    $ fab deploy_metacat -I -i /home/<user>/.ssh/id_rsa -H <host>

:Author:
    servilla
  
:Created:
    04/24/17
"""
from __future__ import print_function

from fabric.operations import *
from fabric.context_managers import *
from fabric.utils import puts

quiet = False
use_local_CA = True
metacat_version = 'metacat-bin-2.8.4'


def server_reboot():
    puts('Doing Ubuntu system reboot...')
    with settings(warn_only=True):
        reboot(wait=60)

def do_patch():
    puts('Doing Ubuntu system patch and reboot...')
    sudo('apt update --yes', quiet=quiet)
    sudo('apt dist-upgrade --yes', quiet=quiet)
    sudo('apt autoremove --yes', quiet=quiet)
    with settings(warn_only=True):
        reboot(wait=60)

def add_tool_chain():
    puts('Adding operating system tools...')
    tool_chain = 'build-essential openjdk-8-jdk tomcat7 apache2 libapache2-mod-jk ' \
                 'postgresql-9.5 openssl curl'
    sudo('apt install --yes ' + tool_chain, quiet=quiet)

def add_metacat_user():
    puts('Adding user metacat...')
    sudo('adduser --ingroup tomcat7 --gecos "Metacat" metacat', quiet=False)
    sudo('adduser metacat www-data', quiet=False)

def add_metacat_sudo():
    puts('Adding sudo to user Metacat...')
    local('cp 01_metacat.template 01_metacat')
    local('sed -i \'s/USER/' + env.user + '/\' 01_metacat')
    put('./01_metacat', '/etc/sudoers.d/01_metacat', use_sudo=True)
    sudo('chown root:root /etc/sudoers.d/01_metacat', quiet=quiet)
    sudo('chmod 644 /etc/sudoers.d/01_metacat', quiet=quiet)

def download_metacat():
    puts('Downloading ' + metacat_version + '...')
    with settings(sudo_user='metacat'):
        sudo('mkdir -p /home/metacat/' + metacat_version)
        with cd('/home/metacat/' + metacat_version):
            sudo('wget https://knb.ecoinformatics.org/software/dist/' + metacat_version + '.tar.gz')
            sudo('tar xfz ' + metacat_version + '.tar.gz')
        with cd ('/home/metacat/' + metacat_version + '/debian'):
            sudo('sed -i \'s/tomcat6/tomcat7/\' metacat-site-ssl.conf')

def configure_postgres():
    puts('Configuring Postgresql...')
    sudo('passwd -d postgres', quiet=quiet)
    with settings(sudo_user='postgres'):
        sudo('passwd', quiet=False)
        sudo('createuser metacat', quiet=quiet)
        sudo('createdb -E UTF8 metacat', quiet=quiet)
        sudo('cp /etc/postgresql/9.5/main/pg_hba.conf /etc/postgresql/9.5/main/pg_hba.conf.original')
        sudo('echo "host metacat metacat 127.0.0.1 255.255.255.255 password" >> /etc/postgresql/9.5/main/pg_hba.conf')

def configure_tomcat7():
    puts('Configuring Tomcat7...')
    with cd('/var/lib/tomcat7/conf'):
        sudo('cp server.xml server.xml.original')
        sudo('sed \'/<!-- Define an AJP 1.3 Connector on port 8009 -->/q\' server.xml > server-tmp.xml')
        sudo('sed -n \'/<Connector port="8009" protocol="AJP\/1.3" redirectPort="8443" \/>/p\' server.xml >> server-tmp.xml')
        sudo('echo "" >> server-tmp.xml')
        sudo('sed \'/<!-- An Engine represents the entry point (within Catalina) that processes/,$!d\' server.xml >> server-tmp.xml')
        sudo('mv server-tmp.xml server.xml')
    with cd('/etc/tomcat7'):
        sudo('cp catalina.properties catalina.properties.original')
        sudo('echo "" >> catalina.properties')
        sudo('echo "org.apache.tomcat.util.buf.UDecoder.ALLOW_ENCODED_SLASH=true" >> catalina.properties')
        sudo('echo "org.apache.catalina.connector.CoyoteAdapter.ALLOW_BACKSLASH=true" >> catalina.properties')

def configure_apache2():
    puts('Configuring Apache2...')
    with cd('/etc/apache2'):
        sudo('cp ./mods-available/jk.conf ./mods-available/jk.conf.original')
        sudo('cp /home/metacat/' + metacat_version + '/debian/jk.conf ./mods-available/jk.conf')
        sudo('cp /home/metacat/' + metacat_version + '/debian/workers.properties .')
        sudo('a2enmod --quiet ssl rewrite jk', quiet=quiet)
        sudo('a2dissite --quiet 000-default')
        sudo('cp /home/metacat/' + metacat_version + '/debian/metacat-site.conf ./sites-available/metacat-site.conf')
        sudo('cp /home/metacat/' + metacat_version + '/debian/metacat-site-ssl.conf ./sites-available/metacat-site-ssl.conf')
        sudo('a2ensite --quiet metacat-site', quiet=quiet)
        sudo('service apache2 restart')

def install_metacat():
    puts('Installing ' + metacat_version + '...')
    sudo('mkdir -p /var/metacat')
    sudo('chown -R tomcat7 /var/metacat')
    sudo('cp /home/metacat/' + metacat_version + '/metacat.war /var/lib/tomcat7/webapps')
    sudo('service tomcat7 restart')

def add_local_ca():
    puts('Making local CA...')
    sudo('mkdir -p /var/local/dataone/certs/local_ca/certs', quiet=quiet)
    sudo('mkdir -p /var/local/dataone/certs/local_ca/newcerts', quiet=quiet)
    sudo('mkdir -p /var/local/dataone/certs/local_ca/private', quiet=quiet)
    with cd('/var/local/dataone/certs/local_ca'):
        sudo('cp /var/local/dataone/gmn_venv/lib/python2.7/site-packages/d1_gmn/deployment/openssl.cnf .', quiet=quiet)
        sudo('touch index.txt', quiet=quiet)
        sudo('openssl req -config ./openssl.cnf -new -newkey rsa:2048 -keyout private/ca_key.pem -out ca_csr.pem', quiet=False)
        sudo('openssl ca -config ./openssl.cnf -create_serial -keyfile private/ca_key.pem -selfsign -extensions v3_ca_has_san -out ca_cert.pem -infiles ca_csr.pem', quiet=False)
        sudo('rm ca_csr.pem')

def add_client_cert():
    puts('Making self-signed client certificate...')
    with cd('/var/local/dataone/certs/local_ca'):
        sudo('openssl req -config ./openssl.cnf -new -newkey rsa:2048 -nodes -keyout private/client_key.pem -out client_csr.pem', quiet=False)
        sudo('openssl rsa -in private/client_key.pem -out private/client_key_nopassword.pem', quiet=False)
        sudo('openssl rsa -in private/client_key_nopassword.pem -pubout -out client_public_key.pem', quiet=False)
        sudo('openssl ca -config ./openssl.cnf -in client_csr.pem -out client_cert.pem', quiet=False)
        get('private/client_key_nopassword.pem', 'client_key_nopassword.pem', use_sudo=True)
        get('client_cert.pem', 'client_cert.pem', use_sudo=True)
        sudo('rm client_csr.pem', quiet=quiet)

def add_trust_local_ca():
    puts('Installing local CA to GMN...')
    with cd('/var/local/dataone/certs/local_ca'):
        sudo('mkdir -p ../ca', quiet=quiet)
        sudo('cp ca_cert.pem ../ca/local_ca.pem', quiet=quiet)
        sudo('c_rehash ../ca', quiet=quiet)

def install_non_trusted_client():
    puts('Installing self-signed client certificate...')
    with cd('/var/local/dataone/certs/local_ca'):
        sudo('mkdir -p ../client', quiet=quiet)
        sudo('cp client_cert.pem private/client_key_nopassword.pem ../client', quiet=quiet)

def install_non_trusted_server():
    puts('Installing self-signed server certificate...')
    sudo('apt install --yes ssl-cert', quiet=quiet)
    sudo('mkdir -p /var/local/dataone/certs/server', quiet=quiet)
    sudo('cp /etc/ssl/certs/ssl-cert-snakeoil.pem /var/local/dataone/certs/server/server_cert.pem', quiet=quiet)
    sudo('cp /etc/ssl/private/ssl-cert-snakeoil.key /var/local/dataone/certs/server/server_key_nopassword.pem', quiet=quiet)

def make_ssl_cert():
    # Only run if the server name or IP address changes.
    # Then, copy the new versions to the GMN standard locations as described above.
    sudo('make-ssl-cert generate-default-snakeoil --force-overwrite', quiet=quiet)

def deploy_metacat():
    do_patch()
    add_tool_chain()
    add_metacat_user()
    add_metacat_sudo()
    download_metacat()
    configure_postgres()
    configure_apache2()
    configure_tomcat7()
    install_metacat()

def main():
    return 0

if __name__ == "__main__":
    main()
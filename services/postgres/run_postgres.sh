#!/bin/bash

# This script is run by Supervisor to start PostgreSQL 11 in foreground mode
# https://github.com/Karumi/docker-sentry/blob/master/conf/run_postgres.sh

if [ -d /var/run/postgresql ]; then
    chmod 2775 /var/run/postgresql
else
    install -d -m 2775 -o postgres -g postgres /var/run/postgresql
fi

exec su postgres -c "/usr/lib/postgresql/11/bin/postgres -D /var/lib/postgresql/11/main -c config_file=/etc/postgresql/11/main/postgresql.conf"
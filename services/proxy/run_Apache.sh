#!/bin/bash

# Source env
source /env.sh

# Make sure that we have MAIN_DOMAIN_NAME and BACKEND_DOMAIN_NAME setup to something:
if [ "x$MAIN_DOMAIN_NAME" == "x" ]; then 
    export MAIN_DOMAIN_NAME="localhost"
fi
if [ "x$BACKEND_DOMAIN_NAME" == "x" ]; then 
    export BACKEND_DOMAIN_NAME="localhost"
fi

# Exec Apache in foreground
exec /usr/sbin/apache2ctl -DFOREGROUND

# Or just use in supervisord:
#/bin/bash -c "source /etc/apache2/envvars && source /env.sh && exec /usr/sbin/apache2 -DFOREGROUND"


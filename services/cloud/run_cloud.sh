#!/bin/bash

DATE=$(date)

echo ""
echo "==================================================="
echo "  Starting Cloud @ $DATE"
echo "==================================================="
echo ""

echo "Loading/sourcing env and settings..."
echo ""

# Load env
source /env.sh

# Database conf
source /db_conf.sh

# Stay quiet
export PYTHONWARNINGS=ignore

# To Python3 unbuffered. P.s. "python3 -u" does not work..
export PYTHONUNBUFFERED=on

# Check if there is something to migrate or populate
# Note: this will also indirectly wait for the DB to become up and reachable
echo "Applying migrations if any..."
cd /opt/code && fab migrate
EXIT_CODE=$?
echo "Exit code: $EXIT_CODE"
if [[ "x$EXIT_CODE" != "x0" ]] ; then
    echo "This exit code is an error, sleeping 5s and exiting." 
    sleep 5
    exit $?
fi
echo ""

# Run the (development) server
echo "Now starting the server and logging in /var/log/cloud/backend.log."
cd /opt/code/ && exec fab runserver 2>> /var/log/cloud/backend.log

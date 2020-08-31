#!/bin/bash

# Exit on any error. More complex thing could be done in future
# (see https://stackoverflow.com/questions/4381618/exit-a-script-on-error)
set -e

echo ""
echo "[INFO] Executing entrypoint..."


#---------------------
#  Prestartup scripts
#---------------------

if [ "x$SAFEMODE" == "xTrue" ]; then
    echo "[INFO] Not executing prestartup scripts as we are in safemode"
else
    echo "[INFO] Executing  prestartup scripts (parents + current):"
    python /prestartup.py
fi


#---------------------
#   Save env
#---------------------
echo "[INFO] Dumping env"

# Save env vars for later usage (e.g. ssh)

env | \
while read env_var; do
  if [[ $env_var == HOME\=* ]]; then
      : # Skip HOME var
  elif [[ $env_var == PWD\=* ]]; then
      : # Skip PWD var
  else
      echo "export $env_var" >> /env.sh
  fi
done

#---------------------
#  Entrypoint command
#---------------------


if [[ "x$@" == "x" ]] ; then
    ENTRYPOINT_COMMAND="supervisord"
else
    ENTRYPOINT_COMMAND=$@
fi

echo -n "[INFO] Executing Docker entrypoint command: "
echo $ENTRYPOINT_COMMAND
exec "$ENTRYPOINT_COMMAND"

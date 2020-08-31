#!/bin/bash
set -e

# Fix missing link if mounting App code as volume for development (dists)
if [ ! -L /opt/code/backend/pythings_app/static/dist ]; then
    ln -s /opt/PythingsOS-dist /opt/code/backend/pythings_app/static/dist
fi

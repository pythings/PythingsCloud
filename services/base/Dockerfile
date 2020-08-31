FROM ubuntu:18.04
MAINTAINER Stefano Alberto Russo <stefano.russo@gmail.com>

#----------------------
# Basics
#----------------------

# Set non-interactive
ENV DEBIAN_FRONTEND noninteractive

# Update
RUN apt-get update

# Utilities
RUN apt-get install -y nano telnet unzip wget supervisor openssh-server

# Devel
RUN apt-get install -y build-essential python-dev git-core

# Java
RUN apt-get install -y openjdk-8-jre

# IP utilities
RUN apt-get install net-tools iproute2 iputils-ping -y


#------------------------
# Pythings user
#------------------------

# Add group. We chose GID 65527 to try avoiding conflicts.
RUN groupadd -g 65527 pythings

# Add user. We chose UID 65527 to try avoiding conflicts.
RUN useradd pythings -d /pythings -u 65527 -g 65527 -m -s /bin/bash

# Add pythings user to sudoers
RUN adduser pythings sudo

# Install suodo
RUN apt-get install sudo -y

# No pass sudo (for everyone, actually)
COPY sudoers /etc/sudoers

# bash_profile for loading correct env (/env.sh created by entrypoint.sh)
RUN echo "source /env.sh" > /pythings/.bash_profile


#------------------------
# Data, logs and opt dirs
#------------------------

# Create dirs
RUN mkdir /data && mkdir /opt/pythings && mkdir /var/log/pythings 

# Give right permissions
RUN chown -R pythings:pythings /data && chown -R pythings:pythings /opt/pythings && chown -R pythings:pythings /var/log/pythings


#----------------------
#  Supervisord conf
#----------------------

COPY supervisord.conf /etc/supervisor/


#----------------------
# Prestartup scripts
#----------------------

# Create dir for prestartup scripts and copy main script
RUN mkdir /prestartup
COPY prestartup.py /


#----------------------
# Entrypoint
#----------------------

# Copy entrypoint
COPY entrypoint.sh /

# Give right permissions
RUN chmod 755 /entrypoint.sh

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]



FROM pythingscloud/base
MAINTAINER Stefano Alberto Russo <stefano.russo@gmail.com>

# Always start with an apt-get update when extending base images
RUN apt-get update

#----------------------------------
# Libraries
#----------------------------------

# Disable strict host checking for Github
RUN mkdir -p ~/.ssh && echo "Host github.com\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config

#----------------------------------
# Libraries deps.
#----------------------------------

# Curl.
RUN apt-get install curl -y

# Download get-pip script for Python 3.6
RUN curl -O https://bootstrap.pypa.io/pip/3.6/get-pip.py

# Install Python and pip in this order (first Python 3 and then Python 2), or 
# you will end ap with python defaulting to python2 and pip defaulting to pip3
# Otherwise, do somethign like "ln -s /usr/local/bin/pip3 /usr/local/bin/pip"

# Install Python3 and Pip3 (python3-distutils required for pip3)
RUN  apt-get install python3 python3-distutils -y 
RUN  python3 get-pip.py 'pip==21.3.1'

# Required for building pycrypto for Python3
RUN apt-get install build-essential python-dev python3-dev libssl-dev -y

# Install postgres driver required for psycopg2
RUN apt-get install libpq-dev -y


#------------------------------
# Install  requirements
#------------------------------

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt


#----------------------------------
# Pythings OS
#----------------------------------

# Clone
RUN cd /opt && git clone https://github.com/pythings/PythingsOS

# Checkout
RUN cd /opt/PythingsOS && git pull && git checkout 1acc266e245eaa7d3b7e6d0318970f39538b0bc8


#----------------------------------
# Create PythingsOS releases trees
#----------------------------------

# Install /un)zip and rsync
RUN apt-get install rsync zip -y

RUN cd /opt/PythingsOS && utilities/create_releases_tree.sh  /opt/PythingsOS-dist/ 



#----------------------------------
# Supervisord
#----------------------------------

COPY run_cloud.sh /etc/supervisor/conf.d/
RUN chmod 755 /etc/supervisor/conf.d/run_cloud.sh
COPY supervisord_cloud.conf /etc/supervisor/conf.d/


#----------------------------------
# Logs
#----------------------------------

# Create dirs
RUN mkdir /var/log/cloud  && chown -R pythings:pythings /data && chown -R pythings:pythings /var/log/cloud


#------------------------------
# Copy cloud code
#------------------------------

# Copy code over
COPY code /opt/code

# Fix permissions
RUN chown -R pythings:pythings /opt/code

# Link Pythings dist files (remove first as a link might be already present due to development mode). See also prestartup.sh.
RUN rm -f /opt/code/backend/pythings_app/static/dist && ln -s /opt/PythingsOS-dist /opt/code/backend/pythings_app/static/dist

# Copy keys
COPY privkey.key /opt/code/backend/pythings_app/privkey.key
COPY pubkey.key /opt/code/backend/pythings_app/pubkey.key

# Copy db conf
COPY db_conf.sh /db_conf.sh

#----------------------------------
# Prestartup 
#----------------------------------

# Copy, give right permissions & unique name to container prestartup
COPY prestartup_cloud.sh /prestartup/








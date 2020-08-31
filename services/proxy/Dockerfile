FROM pythingscloud/base
MAINTAINER Stefano Alberto Russo <stefano.russo@gmail.com>

# Always start with an apt-get update when extending base images
RUN apt-get update

# Install Apache
RUN apt-get install -y apache2
RUN apt-get install apache2-utils

# Copy conf
COPY supervisord_apache.conf /etc/supervisor/conf.d/
COPY run_Apache.sh /etc/supervisor/conf.d/
RUN chmod 755 /etc/supervisor/conf.d/run_Apache.sh

# Enable mod_proxy and SSL
RUN a2enmod proxy
RUN a2enmod proxy_http
RUN sudo a2enmod ssl
RUN a2enmod rewrite
RUN a2enmod headers
RUN a2enmod proxy_wstunnel
 
# Copy and enable conf for proxy
COPY 001-proxy.conf /etc/apache2/sites-available/
RUN ln -s /etc/apache2/sites-available/001-proxy.conf /etc/apache2/sites-enabled/001-proxy.conf

# We overwrite default Apache conf as we force https
COPY 000-default.conf /etc/apache2/sites-available/

# Copy and enable conf for ssl. Not enabling ssl default site causes the first ssl
# site in sites-avaialbe to be used as default. "Check with apachectl -t -D DUMP_VHOSTS".
# A custom conf is not really necessary as defaults are ok (it is the original file)
# Note: not naming this file with "000" causes to load other sites-available before, same problem.
COPY default-ssl.conf /etc/apache2/sites-available/
RUN ln -s /etc/apache2/sites-available/default-ssl.conf /etc/apache2/sites-enabled/000-default-ssl.conf

# Copy main and backend certificates (snakeoil or real)
RUN mkdir /certificates
COPY certificates/main.crt /root/certificates/main.crt
COPY certificates/main.key /root/certificates/main.key
COPY certificates/main.ca-bundle /root/certificates/main.ca-bundle
COPY certificates/backend.crt /root/certificates/backend.crt
COPY certificates/backend.key /root/certificates/backend.key
COPY certificates/backend.ca-bundle /root/certificates/backend.ca-bundle

# Copy index and norobots.txt
COPY index.html /var/www/html/
COPY norobots.txt /var/www/html/

# Prestartup
COPY prestartup_proxy.sh /prestartup/

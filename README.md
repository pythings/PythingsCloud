

# Pythings Cloud

This software is licensed under the Apache License 2.0 unless otherwise specificed.


## Quickstart

Requirements:
    
    Bash, Python, Git and Docker. Runs on Linux, Mac or Windows*.

*Windows not fully supported in development mode due to lack of support for symbolic links.

Setup

	$ pythingscloud/setup

Build

    $ pythingscloud/build

Run

	$ pythingscloud/run		

Play

	$ pythingscloud/populate
	
    # ...you can now point your browser to localhost or the server address
    #    and login using user=testuser@pythings.local, pass=testpass.

Clean

	# pythingscloud/clean


## More commands


View service logs

    $ pythingscloud/logs cloud | proxy | postgres

Cloud startup and backend logs the cloud service:
    
    $ pythingscloud/logs cloud startup
    $ pythingscloud/logs cloud backend


Update cycle:

    $ git pull
    $ pythingscloud/setup
    $ pythingscloud/build
    $ pythingscloud/clean
    $ pythingscloud/run

Daemon (monitors for git changes every minute and applies the update cycle)

    pythingscloud/daemon



### Usage for development

If you set DEBUG=True, Django will use its development server which allows to live-monitor code and static filed changes. To enable live code changes, you also need to mount the code from services/cloud/code as as a volume inside the cloud service container, see the docker-compose-dev.yml for and example.

To run unit tests (in a running "cloud" service):

    $ pythingscloud/test


When you edit the ORM model, remember that you need to make the migrations and migrate the DB:

    $ pythingscloud/makemigrations
    $ pythingscloud/migrate
    


### Environments variables

In the cloud service, you can configure things like project name, database parameters, log levels and email service via environment variables. A list of the configurable environments variables with their default values is shown below. Note that the accepted log levels are: DEBUG, INFO, WARNING, ERROR, CRITICAL.


    # General conf
    BACKEND_EMAIL_FROM="Pythings Cloud Local <cloud@pythings.local>"
    BACKEND_EMAIL_SERVICE="Sendgrid"
    BACKEND_EMAIL_APIKEY=
    MAIN_DOMAIN_NAME="http://localhost"
    WEBSETUP_DOMAIN_NAME="http://localhost"
    FAVICONS_PATH=
    LOGO_FILE=
    CONTACT_EMAIL="contact@pythings.local"
    INVITATION_CODE="tryme"
    
    # Django conf
    DJANGO_SECRET_KEY="#k%566hw@w%1((_&=640_4w#p)piwt$m4%#(9x^+it5(h1b6zy"
    DJANGO_DEBUG=False

    # Dabase conf (usually overrided by sourcing the db_conf.sh script)
    DJANGO_DB_ENGINE="django.db.backends.sqlite3"
    DJANGO_DB_NAME="../db-backend.sqlite3"
    DJANGO_DB_USER=
    DJANGO_DB_PASSWORD=
    DJANGO_DB_HOST=
    DJANGO_DB_PORT=

    # Logging
    DJANGO_LOG_LEVEL=CRITICAL
    BACKEND_LOG_LEVEL=ERROR
	
	

Setting the DJANGO_DEBUG mode causes to enable the development server in full mode, to have much more verbose 500 error pages with all the stack traces and context (the classic Django yellow page) and to have stack-traces logged on more than one line (by default they are logged one per line to play nice with log aggregation tools)



	














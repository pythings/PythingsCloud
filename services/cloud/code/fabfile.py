from fabric.api import local, task
from backend.common.utils import booleanize
from backend.common.utils import discover_apps
import os


# Try to understand where we are
if not os.path.isfile('manage.py'):
    if os.path.isfile('../../manage.py'):
        os.chdir('../../')
    else:
        raise Exception('Sorry, could not find fabfile. Are you in the root directory or in an app directory?')

# Set Python executable
PYTHON = 'python3'

#--------------------
# Utility functions
#--------------------

def run(command):
    local(command)


#--------------------
# Run
#--------------------

@task
def shell():
    run('{} manage.py shell'.format(PYTHON))


@task
def runserver(noreload=False):
    if isinstance(noreload,str) and noreload.upper()=='FALSE':
        noreload=False
    if noreload:
        run('{} manage.py runserver 0.0.0.0:8080 --noreload'.format(PYTHON))
    else:
        run('{} manage.py runserver 0.0.0.0:8080'.format(PYTHON))


#-----------------------------
#   Install
#-----------------------------

@task
def install(what=None, env="local", noinput=False):    
    if noinput:
        run('{} manage.py makemigrations --noinput'.format(PYTHON))
        run('{} manage.py migrate --noinput'.format(PYTHON))
    else:
        run('{} manage.py makemigrations'.format(PYTHON))
        run('{} manage.py migrate'.format(PYTHON))


#-----------------------------
#   Populate
#-----------------------------
@task
def populate(env="local"):

    for app in discover_apps('backend', only_names=True):

        # Check if we have the populate:
        populate_file = 'backend/{}/management/commands/{}_populate.py'.format(app,app)
        if os.path.isfile(populate_file):
            print('Poulate found for {} and executing...'.format(app))
            run('{} manage.py {}_populate'.format(PYTHON, app))
        else:
            print('No poulate found for {}... ({})'.format(app,populate_file))


#-----------------------------
#   Custom management
#-----------------------------
@task
def management(app=None, command=None, env="local"):
    if not app or not command:
        raise Exception('app and command are required!')
    run("{} manage.py {}_{}".format(PYTHON,app,command))

#-----------------------------
#   Migrations
#-----------------------------
@task
def makemigrations(what=None, env="local", noinput=False):
    if noinput:
        run('{} manage.py makemigrations --noinput'.format(PYTHON))
    else:
        run('{} manage.py makemigrations'.format(PYTHON))

@task
def migrate(app=None, noinput=False):
    if noinput:
        run('{} manage.py migrate --noinput'.format(PYTHON))
    else:
        run('{} manage.py migrate'.format(PYTHON))


#-----------------------------
#   Tests
#-----------------------------
@task
def test(what=None):
    if what:
        run('{} manage.py test {}'.format(PYTHON, what))
    else:
        run('{} manage.py test'.format(PYTHON))


#-----------------------------
#   Deploy
#-----------------------------
@task
def collect():
    run('{} manage.py collectstatic'.format(PYTHON))









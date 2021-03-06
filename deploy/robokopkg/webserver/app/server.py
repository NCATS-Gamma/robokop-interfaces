from flask import Flask, request
from flask import render_template
import os
from flask_cors import CORS
from logging import Logger

logger = Logger(__name__)
app = Flask(__name__)
static_file_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static')
dumps_dir = os.path.join(os.environ.get('HOME'), 'dumps')
change_logs_dir = os.path.join(os.environ.get('HOME'), 'change_logs')
CORS(app)

def get_domain_name_from_env():
    domain_name = os.environ.get('SERVER_DOMAIN')
    proto = request.environ.get('HTTP_X_FORWARDED_PROTO','https')
    return f'{proto}://{domain_name}'

def get_list_of_neo4j_files():
    files = []
    for dirname, dirnames, filenames in os.walk(dumps_dir):
        for filename in filenames:
            files.append(filename)
    # return sorted so recent files show up first on UI
    # select *.dump.db as the neo4j dumps
    files = list(filter(lambda x : x.endswith('.dump.db'), files))
    return sorted(files, reverse= True)

def get_change_log(dump_file_name):
    change_logs = []
    try:
        with open(os.path.join(change_logs_dir, f'{dump_file_name}.changelog')) as diff_file:
            change_logs = diff_file.readlines()
    except:
        logger.warning(f'Change log for {dump_file_name} not found. Ignoring...')    
    return change_logs

@app.route('/guide')
def guide():
    return render_template('guide/index.html', **{'host': get_domain_name_from_env()})

@app.route('/guide/dumps')
def dumps():
    files = get_list_of_neo4j_files()
    
    y = {'files' : [{'filename': x ,'changelog': get_change_log(x)} for x in files]}
    print(y)
    logger.debug(y)
    y['host'] = get_domain_name_from_env()
    return render_template('guide/dump.html', **y)

@app.route('/guide/learn')
def about():
    return render_template('guide/about.html',**{'host': get_domain_name_from_env()})

@app.route('/guide/methods')
def methods():
    return render_template('guide/methods.html',**{'host': get_domain_name_from_env()})

@app.route('/guide/queries')
def queries():
    return render_template('guide/queries.html',**{'host': get_domain_name_from_env()})

@app.route('/guide/licenses')
def licenses():
    return render_template('guide/licenses.html',**{'host': get_domain_name_from_env()})

@app.route('/guide/redis_dump')
def redis_dump():
    return render_template('guide/redis.html', **{'host': get_domain_name_from_env()})

@app.route('/guide/omnicorp_dump')
def omni_dump():
    return render_template('guide/omnicorp.html', **{'host': get_domain_name_from_env()})

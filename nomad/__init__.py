#!/usr/bin/env python

import os, os.path as op, sys

from opster import Dispatcher
from termcolor import cprint, colored

from nomad.repo import Repository
from nomad.engine import DBError
from nomad.utils import abort, NomadError, NomadIniNotFound


__version__ = '1.7'


GLOBAL = [
    ('c', 'config', 'nomad.ini', 'path to config file'),
    ('D', 'define', {}, 'override config values'),
    ]


EXAMPLE_INI = '''
  [nomad]
  engine = dbapi
  url = sqlite://data.db
'''


def getconfig(func):
    if func.__name__.startswith('help') or func.__name__ in ('version',):
        return func
    def inner(*args, **kwargs):
        try:
            repo = Repository(kwargs['config'], kwargs['define'])
        except NomadIniNotFound, e:
            sys.stderr.write("Create '%s' to use nomad, example:\n%s\n" %
                             (e, EXAMPLE_INI))
            abort('config file not found')
        except (IOError, NomadError), e:
            abort(e)

        return func(repo=repo, *args, **kwargs)
    return inner

app = Dispatcher(globaloptions=GLOBAL, middleware=getconfig)


@app.command()
def init(**opts):
    '''Initialize database migration management
    '''
    opts['repo'].init_db()
    print 'Versioning table initialized successfully'


@app.command(name='list', aliases=('ls',))
def list_(all=('a', False, 'show all migrations (default: only non-applied)'),
         **opts):
    '''List migrations
    '''
    repo = opts['repo']
    for m in repo.available:
        if m in repo.applied:
            if all:
                cprint(m, 'magenta')
        else:
            out = colored(m, 'green')
            deps = []
            for dep in m.dependencies:
                if dep not in repo.applied:
                    deps.append(dep)
            if deps:
                out += ' (%s)' % ', '.join(map(str, deps))
            print out


@app.command()
def create(name,
           dependencies=('d', [], 'migration dependencies'),
           **opts):
    '''Create new migration
    '''
    repo = opts['repo']
    deps = map(repo.get, dependencies)

    path = op.join(repo.path, name)
    try:
        os.mkdir(path)
    except OSError, e:
        if e.errno == 17:
            abort('directory %s already exists' % path)
        raise

    with open(op.join(path, 'migration.ini'), 'w') as f:
        f.write('[nomad]\n')
        f.write('dependencies = %s\n' % ', '.join(d.name for d in deps))
    with open(op.join(path, 'up.sql'), 'w') as f:
        f.write('-- SQL ALTER statements for database migration\n')


@app.command()
def apply(all=('a', False, 'apply all available migrations'),
          init=('', False, 'init if not initialized yet'),
          env=('e', [], 'list of additional environment variables'),
          *names,
          **opts):
    '''Apply migration and all of it dependencies

    You can pass additional environment variables to your migrations scripts
    using option `-e` (in addition to NOMAD_DBURL, which is passed by default):

        nomad apply -e ONE=one -e TWO=two -a
    '''
    repo = opts['repo']
    if init:
        try:
            repo.init_db()
        except DBError:
            pass

    if names:
        migrations = map(repo.get, names)
    elif all:
        migrations = [x for x in repo.available if x not in repo.applied]
    else:
        abort('Supply names of migrations to apply')

    if env:
        env = dict(x.split('=', 1) for x in env)

    for m in migrations:
        if m in repo.applied:
            abort('migration %s is already applied' % m)
    for m in migrations:
        if not m.applied:
            m.apply(env=env)


@app.command()
def info(**opts):
    '''Show information about repository
    '''
    repo = opts['repo']
    print '%s:' % repo
    print '  %s' % repo.engine
    try:
        print '  %s applied' % len(repo.applied)
        print '  %s unapplied' % (len(repo.available) - len(repo.applied))
    except DBError:
        print '  Uninitialized repository'


@app.command()
def version(**opts):
    '''Show app version
    '''
    print 'Nomad v%s' % __version__


if __name__ == '__main__':
    app.dispatch()

import logging
import os

try:
    import jinja2
except ImportError:
    pass


logging.basicConfig(level=logging.INFO)

"""

WIP Abstract templating system for the OpenStack charms.

The idea is that an openstack charm can register a number of config files
associated with common context generators.  The context generators are
responsible for inspecting charm config/relation data/deployment state
and presenting correct context to the template. Generic context generators
could live somewhere in charmhelpers.contrib.openstack, and each
charm can implement their own specific ones as well.

Ideally a charm would register all its config files somewhere in its namespace,
eg cinder_utils.py:

from charmhelpers.contrib.openstack import templating, context

config_files = {
    '/etc/cinder/cinder.conf': [context.shared_db,
                                context.amqp,
                                context.ceph],
    '/etc/cinder/api-paste.ini': [context.identity_service]
}

configs = templating.OSConfigRenderer(template_dir='templates/')

[configs.register(k, v) for k, v in config_files.iteritems()]

Hooks can then render config files as need, eg:

def config_changed():
    configs.render_all()

def db_changed():
    configs.render('/etc/cinder/cinder.conf')
    check_call(['cinder-manage', 'db', 'sync'])

This would look very similar for nova/glance/etc.


The OSTemplteLoader is responsible for creating a jinja2.ChoiceLoader that should
help reduce fragmentation of a charms' templates across OpenStack releases, so we
do not need to maintain many copies of templates or juggle symlinks. The constructed
loader lets the template be loaded from the most recent OS release-specific template
dir or a base template dir.

For example, say cinder has no changes in config structure across any OS releases,
all OS releases share the same templates from the base directory:


templates/api-paste.ini
templates/cinder.conf

Then, since Grizzly and beyond, cinder.conf's format has changed:

templates/api-paste.ini
templates/cinder.conf
templates/grizzly/cinder.conf


Grizzly and beyond will load from templates/grizzly, but any release prior will
load from templates/.   If some change in Icehouse breaks config format again:

templates/api-paste.ini
templates/cinder.conf
templates/grizzly/cinder.conf
templates/icehouse/cinder.conf

Icehouse and beyond will load from icehouse/, Grizzly + Havan from grizzly/, previous
releases from the base templates/

"""
class OSConfigException(Exception):
    pass

def get_loader(templates_dir, os_release):
    """
    Create a jinja2.ChoiceLoader containing template dirs up to
    and including os_release.  If directory template directory
    is missing at templates_dir, it will be omitted from the loader.
    templates_dir is added to the bottom of the search list as a base
    loading dir.

    :param templates_dir: str: Base template directory containing release
                               sub-directories.
    :param os_release   : str: OpenStack release codename to construct template
                               loader.

    :returns            : jinja2.ChoiceLoader constructed with a list of
                          jinja2.FilesystemLoaders, ordered in descending
                          order by OpenStack release.
    """
    tmpl_dirs = (
        ('essex', os.path.join(templates_dir, 'essex')),
        ('folsom', os.path.join(templates_dir, 'folsom')),
        ('grizzly', os.path.join(templates_dir, 'grizzly')),
        ('havana', os.path.join(templates_dir, 'havana')),
        ('icehouse', os.path.join(templates_dir, 'icehouse')),
    )
    if not os.path.isdir(templates_dir):
        logging.error('Templates directory not found @ %s.' % templates_dir)
        raise OSConfigException
    loaders = [jinja2.FileSystemLoader(templates_dir)]
    for rel, tmpl_dir in tmpl_dirs:
        if os.path.isdir(tmpl_dir):
            loaders.insert(0, jinja2.FileSystemLoader(tmpl_dir))
        if rel == os_release:
            break
    logging.info('Creating choice loader with dirs: %s' %\
                 [l.searchpath for l in loaders])
    return jinja2.ChoiceLoader(loaders)

class OSConfigTemplate(object):
    def __init__(self, config_file, contexts):
        self.config_file = config_file
        if hasattr(contexts, '__call__'):
            self.contexts = [contexts]
        else:
            self.contexts = contexts

    def context(self):
        ctxt = {}
        for context in self.contexts:
            _ctxt = context()
            if _ctxt:
                ctxt.update(_ctxt)
        return ctxt

class OSConfigRenderer(object):
    def __init__(self, templates_dir, openstack_release):
        if not os.path.isdir(templates_dir):
            logging.error('Could not locate templates dir %s' % templates_dir)
            raise OSConfigException
        self.templates_dir = templates_dir
        self.openstack_release = openstack_release
        self.templates = {}
        self._tmpl_env = None

    def register(self, config_file, contexts):
        self.templates[config_file] = OSConfigTemplate(config_file=config_file,
                                                       contexts=contexts)
        logging.info('Registered config file: %s' % config_file)

    def _get_tmpl_env(self):
        if not self._tmpl_env:
            loader = get_loader(self.templates_dir, self.openstack_release)
            self._tmpl_env = jinja2.Environment(loader=loader)

    def render(self, config_file):
        if config_file not in self.templates:
            logging.error('Config not registered: %s' % config_file)
            raise OSConfigException
        ctxt = self.templates[config_file].context()
        _tmpl = os.path.basename(config_file)
        logging.info('Rendering from template: %s' % _tmpl)
        self._get_tmpl_env()
        _tmpl = self._tmpl_env.get_template(_tmpl)
        logging.info('Loaded template from %s' % _tmpl.filename)
        return _tmpl.render(ctxt)

    def write(self, config_file):
        if config_file not in self.templates:
            logging.error('Config not registered: %s' % config_file)
            raise OSConfigException
        with open(config_file, 'wb') as out:
            out.write(self.render(config_file))
        logging.info('Wrote template %s.' % config_file)

    def write_all(self):
        [self.write(k) for k in self.templates.iterkeys()]

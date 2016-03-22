# Copyright 2016 Canonical Limited.
#
# This file is part of charm-helpers.
#
# charm-helpers is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3 as
# published by the Free Software Foundation.
#
# charm-helpers is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with charm-helpers.  If not, see <http://www.gnu.org/licenses/>.

import os

from charmhelpers.core.hookenv import (
    log,
    DEBUG,
    WARNING,
)

try:
    from jinja2 import FileSystemLoader, Environment
except ImportError:
    from charmhelpers.fetch import apt_install
    from charmhelpers.fetch import apt_update
    apt_update(fatal=True)
    apt_install('python-jinja2', fatal=True)
    from jinja2 import FileSystemLoader, Environment


# NOTE: function separated from main rendering code to facilitate easier
#       mocking in unit tests.
def write(path, data):
    with open(path, 'wb') as out:
        out.write(data)


def get_template_path(template_dir, path):
    """Returns the template file which would be used to render the path.

    The path to the template file is returned.
    :param template_dir: the directory the templates are located in
    :param path: the file path to be written to.
    :returns: path to the template file
    """
    return os.path.join(template_dir, os.path.basename(path))


def render_and_write(template_dir, path, context):
    """Renders the specified template into the file.

    :param template_dir: the directory to load the template from
    :param path: the path to write the templated contents to
    :param context: the parameters to pass to the rendering engine
    """
    env = Environment(loader=FileSystemLoader(template_dir))
    template_file = os.path.basename(path)
    template = env.get_template(template_file)
    log('Rendering from template: %s' % template.name, level=DEBUG)
    rendered_content = template.render(context)
    if not rendered_content:
        log("Render returned None - skipping '%s'" % path,
            level=WARNING)
        return

    write(path, rendered_content.encode('utf-8').strip())
    log('Wrote template %s' % path, level=DEBUG)

# Copyright 2014-2015 Canonical Limited.
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

import amulet
import ConfigParser
import distro_info
import io
import logging
import os
import re
import six
import sys
import time
import urlparse


class AmuletUtils(object):
    """Amulet utilities.

       This class provides common utility functions that are used by Amulet
       tests.
       """

    def __init__(self, log_level=logging.ERROR):
        self.log = self.get_logger(level=log_level)
        self.ubuntu_releases = self.get_ubuntu_releases()

    def get_logger(self, name="amulet-logger", level=logging.DEBUG):
        """Get a logger object that will log to stdout."""
        log = logging
        logger = log.getLogger(name)
        fmt = log.Formatter("%(asctime)s %(funcName)s "
                            "%(levelname)s: %(message)s")

        handler = log.StreamHandler(stream=sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(fmt)

        logger.addHandler(handler)
        logger.setLevel(level)

        return logger

    def valid_ip(self, ip):
        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
            return True
        else:
            return False

    def valid_url(self, url):
        p = re.compile(
            r'^(?:http|ftp)s?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # noqa
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$',
            re.IGNORECASE)
        if p.match(url):
            return True
        else:
            return False

    def get_ubuntu_release_from_sentry(self, sentry_unit):
        """Get Ubuntu release codename from sentry unit.

        :param sentry_unit: amulet sentry/service unit pointer
        :returns: list of strings - release codename, failure message
        """
        msg = None
        cmd = 'lsb_release -cs'
        release, code = sentry_unit.run(cmd)
        if code == 0:
            self.log.debug('{} lsb_release: {}'.format(
                sentry_unit.info['unit_name'], release))
        else:
            msg = ('{} `{}` returned {} '
                   '{}'.format(sentry_unit.info['unit_name'],
                               cmd, release, code))
        if release not in self.ubuntu_releases:
            msg = ("Release ({}) not found in Ubuntu releases "
                   "({})".format(release, self.ubuntu_releases))
        return release, msg

    def validate_services(self, commands):
        """Validate that lists of commands succeed on service units.  Can be
           used to verify system services are running on the corresponding
           service units.

        :param commands: dict with sentry keys and arbitrary command list vals
        :returns: None if successful, Failure string message otherwise
        """
        self.log.debug('Checking status of system services...')

        # /!\ DEPRECATION WARNING (beisner):
        # New and existing tests should be rewritten to use
        # validate_services_by_name() as it is aware of init systems.
        self.log.warn('/!\\ DEPRECATION WARNING:  use '
                      'validate_services_by_name instead of validate_services '
                      'due to init system differences.')

        for k, v in six.iteritems(commands):
            for cmd in v:
                output, code = k.run(cmd)
                self.log.debug('{} `{}` returned '
                               '{}'.format(k.info['unit_name'],
                                           cmd, code))
                if code != 0:
                    return "command `{}` returned {}".format(cmd, str(code))
        return None

    def validate_services_by_name(self, sentry_services):
        """Validate system service status by service name, automatically
           detecting init system based on Ubuntu release codename.

        :param sentry_services: dict with sentry keys and svc list values
        :returns: None if successful, Failure string message otherwise
        """
        self.log.debug('Checking status of system services...')

        # Point at which systemd became a thing
        systemd_switch = self.ubuntu_releases.index('vivid')

        for sentry_unit, services_list in six.iteritems(sentry_services):
            # Get lsb_release codename from unit
            release, ret = self.get_ubuntu_release_from_sentry(sentry_unit)
            if ret:
                return ret

            for service_name in services_list:
                if (self.ubuntu_releases.index(release) >= systemd_switch or
                        service_name == "rabbitmq-server"):
                    # init is systemd
                    cmd = 'sudo service {} status'.format(service_name)
                elif self.ubuntu_releases.index(release) < systemd_switch:
                    # init is upstart
                    cmd = 'sudo status {}'.format(service_name)

                output, code = sentry_unit.run(cmd)
                self.log.debug('{} `{}` returned '
                               '{}'.format(sentry_unit.info['unit_name'],
                                           cmd, code))
                if code != 0:
                    return "command `{}` returned {}".format(cmd, str(code))
        return None

    def _get_config(self, unit, filename):
        """Get a ConfigParser object for parsing a unit's config file."""
        file_contents = unit.file_contents(filename)

        # NOTE(beisner):  by default, ConfigParser does not handle options
        # with no value, such as the flags used in the mysql my.cnf file.
        # https://bugs.python.org/issue7005
        config = ConfigParser.ConfigParser(allow_no_value=True)
        config.readfp(io.StringIO(file_contents))
        return config

    def validate_config_data(self, sentry_unit, config_file, section,
                             expected):
        """Validate config file data.

           Verify that the specified section of the config file contains
           the expected option key:value pairs.

           Compare expected dictionary data vs actual dictionary data.
           The values in the 'expected' dictionary can be strings, bools, ints,
           longs, or can be a function that evaluates a variable and returns a
           bool.
           """
        self.log.debug('Validating config file data ({} in {} on {})'
                       '...'.format(section, config_file,
                                    sentry_unit.info['unit_name']))
        config = self._get_config(sentry_unit, config_file)

        if section != 'DEFAULT' and not config.has_section(section):
            return "section [{}] does not exist".format(section)

        for k in expected.keys():
            if not config.has_option(section, k):
                return "section [{}] is missing option {}".format(section, k)

            actual = config.get(section, k)
            v = expected[k]
            if (isinstance(v, six.string_types) or
                    isinstance(v, bool) or
                    isinstance(v, six.integer_types)):
                # handle explicit values
                if actual != v:
                    return "section [{}] {}:{} != expected {}:{}".format(
                           section, k, actual, k, expected[k])
            # handle function pointers, such as not_null or valid_ip
            elif not v(actual):
                return "section [{}] {}:{} != expected {}:{}".format(
                       section, k, actual, k, expected[k])
        return None

    def _validate_dict_data(self, expected, actual):
        """Validate dictionary data.

           Compare expected dictionary data vs actual dictionary data.
           The values in the 'expected' dictionary can be strings, bools, ints,
           longs, or can be a function that evaluates a variable and returns a
           bool.
           """
        self.log.debug('actual: {}'.format(repr(actual)))
        self.log.debug('expected: {}'.format(repr(expected)))

        for k, v in six.iteritems(expected):
            if k in actual:
                if (isinstance(v, six.string_types) or
                        isinstance(v, bool) or
                        isinstance(v, six.integer_types)):
                    # handle explicit values
                    if v != actual[k]:
                        return "{}:{}".format(k, actual[k])
                # handle function pointers, such as not_null or valid_ip
                elif not v(actual[k]):
                    return "{}:{}".format(k, actual[k])
            else:
                return "key '{}' does not exist".format(k)
        return None

    def validate_relation_data(self, sentry_unit, relation, expected):
        """Validate actual relation data based on expected relation data."""
        actual = sentry_unit.relation(relation[0], relation[1])
        return self._validate_dict_data(expected, actual)

    def _validate_list_data(self, expected, actual):
        """Compare expected list vs actual list data."""
        for e in expected:
            if e not in actual:
                return "expected item {} not found in actual list".format(e)
        return None

    def not_null(self, string):
        if string is not None:
            return True
        else:
            return False

    def _get_file_mtime(self, sentry_unit, filename):
        """Get last modification time of file."""
        return sentry_unit.file_stat(filename)['mtime']

    def _get_dir_mtime(self, sentry_unit, directory):
        """Get last modification time of directory."""
        return sentry_unit.directory_stat(directory)['mtime']

    def _get_proc_start_time(self, sentry_unit, service, pgrep_full=False):
        """Get process' start time.

           Determine start time of the process based on the last modification
           time of the /proc/pid directory. If pgrep_full is True, the process
           name is matched against the full command line.
           """
        if pgrep_full:
            cmd = 'pgrep -o -f {}'.format(service)
        else:
            cmd = 'pgrep -o {}'.format(service)
        cmd = cmd + '  | grep  -v pgrep || exit 0'
        cmd_out = sentry_unit.run(cmd)
        self.log.debug('CMDout: ' + str(cmd_out))
        if cmd_out[0]:
            self.log.debug('Pid for %s %s' % (service, str(cmd_out[0])))
            proc_dir = '/proc/{}'.format(cmd_out[0].strip())
            return self._get_dir_mtime(sentry_unit, proc_dir)

    def service_restarted(self, sentry_unit, service, filename,
                          pgrep_full=False, sleep_time=20):
        """Check if service was restarted.

           Compare a service's start time vs a file's last modification time
           (such as a config file for that service) to determine if the service
           has been restarted.
           """
        time.sleep(sleep_time)
        if (self._get_proc_start_time(sentry_unit, service, pgrep_full) >=
                self._get_file_mtime(sentry_unit, filename)):
            return True
        else:
            return False

    def service_restarted_since(self, sentry_unit, mtime, service,
                                pgrep_full=False, sleep_time=20,
                                retry_count=2):
        """Check if service was been started after a given time.

        Args:
          sentry_unit (sentry): The sentry unit to check for the service on
          mtime (float): The epoch time to check against
          service (string): service name to look for in process table
          pgrep_full (boolean): Use full command line search mode with pgrep
          sleep_time (int): Seconds to sleep before looking for process
          retry_count (int): If service is not found, how many times to retry

        Returns:
          bool: True if service found and its start time it newer than mtime,
                False if service is older than mtime or if service was
                not found.
        """
        self.log.debug('Checking %s restarted since %s' % (service, mtime))
        time.sleep(sleep_time)
        proc_start_time = self._get_proc_start_time(sentry_unit, service,
                                                    pgrep_full)
        while retry_count > 0 and not proc_start_time:
            self.log.debug('No pid file found for service %s, will retry %i '
                           'more times' % (service, retry_count))
            time.sleep(30)
            proc_start_time = self._get_proc_start_time(sentry_unit, service,
                                                        pgrep_full)
            retry_count = retry_count - 1

        if not proc_start_time:
            self.log.warn('No proc start time found, assuming service did '
                          'not start')
            return False
        if proc_start_time >= mtime:
            self.log.debug('proc start time is newer than provided mtime'
                           '(%s >= %s)' % (proc_start_time, mtime))
            return True
        else:
            self.log.warn('proc start time (%s) is older than provided mtime '
                          '(%s), service did not restart' % (proc_start_time,
                                                             mtime))
            return False

    def config_updated_since(self, sentry_unit, filename, mtime,
                             sleep_time=20):
        """Check if file was modified after a given time.

        Args:
          sentry_unit (sentry): The sentry unit to check the file mtime on
          filename (string): The file to check mtime of
          mtime (float): The epoch time to check against
          sleep_time (int): Seconds to sleep before looking for process

        Returns:
          bool: True if file was modified more recently than mtime, False if
                file was modified before mtime,
        """
        self.log.debug('Checking %s updated since %s' % (filename, mtime))
        time.sleep(sleep_time)
        file_mtime = self._get_file_mtime(sentry_unit, filename)
        if file_mtime >= mtime:
            self.log.debug('File mtime is newer than provided mtime '
                           '(%s >= %s)' % (file_mtime, mtime))
            return True
        else:
            self.log.warn('File mtime %s is older than provided mtime %s'
                          % (file_mtime, mtime))
            return False

    def validate_service_config_changed(self, sentry_unit, mtime, service,
                                        filename, pgrep_full=False,
                                        sleep_time=20, retry_count=2):
        """Check service and file were updated after mtime

        Args:
          sentry_unit (sentry): The sentry unit to check for the service on
          mtime (float): The epoch time to check against
          service (string): service name to look for in process table
          filename (string): The file to check mtime of
          pgrep_full (boolean): Use full command line search mode with pgrep
          sleep_time (int): Seconds to sleep before looking for process
          retry_count (int): If service is not found, how many times to retry

        Typical Usage:
            u = OpenStackAmuletUtils(ERROR)
            ...
            mtime = u.get_sentry_time(self.cinder_sentry)
            self.d.configure('cinder', {'verbose': 'True', 'debug': 'True'})
            if not u.validate_service_config_changed(self.cinder_sentry,
                                                     mtime,
                                                     'cinder-api',
                                                     '/etc/cinder/cinder.conf')
                amulet.raise_status(amulet.FAIL, msg='update failed')
        Returns:
          bool: True if both service and file where updated/restarted after
                mtime, False if service is older than mtime or if service was
                not found or if filename was modified before mtime.
        """
        self.log.debug('Checking %s restarted since %s' % (service, mtime))
        time.sleep(sleep_time)
        service_restart = self.service_restarted_since(sentry_unit, mtime,
                                                       service,
                                                       pgrep_full=pgrep_full,
                                                       sleep_time=0,
                                                       retry_count=retry_count)
        config_update = self.config_updated_since(sentry_unit, filename, mtime,
                                                  sleep_time=0)
        return service_restart and config_update

    def get_sentry_time(self, sentry_unit):
        """Return current epoch time on a sentry"""
        cmd = "date +'%s'"
        return float(sentry_unit.run(cmd)[0])

    def relation_error(self, name, data):
        return 'unexpected relation data in {} - {}'.format(name, data)

    def endpoint_error(self, name, data):
        return 'unexpected endpoint data in {} - {}'.format(name, data)

    def get_ubuntu_releases(self):
        """Return a list of all Ubuntu releases in order of release."""
        _d = distro_info.UbuntuDistroInfo()
        _release_list = _d.all
        self.log.debug('Ubuntu release list: {}'.format(_release_list))
        return _release_list

    def file_to_url(self, file_rel_path):
        """Convert a relative file path to a file URL."""
        _abs_path = os.path.abspath(file_rel_path)
        return urlparse.urlparse(_abs_path, scheme='file').geturl()

    def check_commands_on_units(self, commands, sentry_units):
        """Check that all commands in a list exit zero on all
        sentry units in a list.

        :param commands:  list of bash commands
        :param sentry_units:  list of sentry unit pointers
        :returns: None if successful; Failure message otherwise
        """
        self.log.debug('Checking exit codes for {} commands on {} '
                       'sentry units...'.format(len(commands),
                                                len(sentry_units)))
        for sentry_unit in sentry_units:
            for cmd in commands:
                output, code = sentry_unit.run(cmd)
                if code == 0:
                    self.log.debug('{} `{}` returned {} '
                                   '(OK)'.format(sentry_unit.info['unit_name'],
                                                 cmd, code))
                else:
                    return ('{} `{}` returned {} '
                            '{}'.format(sentry_unit.info['unit_name'],
                                        cmd, code, output))
        return None

    def get_process_id_list(self, sentry_unit, process_name):
        """Get a list of process ID(s) from a single sentry juju unit
        for a single process name.

        :param sentry_unit: Pointer to amulet sentry instance (juju unit)
        :param process_name: Process name
        :returns: List of process IDs
        """
        cmd = 'pidof {}'.format(process_name)
        output, code = sentry_unit.run(cmd)
        if code != 0:
            msg = ('{} `{}` returned {} '
                   '{}'.format(sentry_unit.info['unit_name'],
                               cmd, code, output))
            amulet.raise_status(amulet.FAIL, msg=msg)
        return str(output).split()

    def get_unit_process_ids(self, unit_processes):
        """Construct a dict containing unit sentries, process names, and
        process IDs."""
        pid_dict = {}
        for sentry_unit, process_list in unit_processes.iteritems():
            pid_dict[sentry_unit] = {}
            for process in process_list:
                pids = self.get_process_id_list(sentry_unit, process)
                pid_dict[sentry_unit].update({process: pids})
        return pid_dict

    def validate_unit_process_ids(self, expected, actual):
        """Validate process id quantities for services on units."""
        self.log.debug('Checking units for running processes...')
        self.log.debug('Expected PIDs: {}'.format(expected))
        self.log.debug('Actual PIDs: {}'.format(actual))

        if len(actual) != len(expected):
            return ('Unit count mismatch.  expected, actual: {}, '
                    '{} '.format(len(expected), len(actual)))

        for (e_sentry, e_proc_names) in expected.iteritems():
            e_sentry_name = e_sentry.info['unit_name']
            if e_sentry in actual.keys():
                a_proc_names = actual[e_sentry]
            else:
                return ('Expected sentry ({}) not found in actual dict data.'
                        '{}'.format(e_sentry_name, e_sentry))

            if len(e_proc_names.keys()) != len(a_proc_names.keys()):
                return ('Process name count mismatch.  expected, actual: {}, '
                        '{}'.format(len(expected), len(actual)))

            for (e_proc_name, e_pids_length), (a_proc_name, a_pids) in \
                    zip(e_proc_names.items(), a_proc_names.items()):
                if e_proc_name != a_proc_name:
                    return ('Process name mismatch.  expected, actual: {}, '
                            '{}'.format(e_proc_name, a_proc_name))

                a_pids_length = len(a_pids)
                if e_pids_length != a_pids_length:
                    return ('PID count mismatch. {} ({}) expected, actual: '
                            '{}, {} ({})'.format(e_sentry_name, e_proc_name,
                                                 e_pids_length, a_pids_length,
                                                 a_pids))
                else:
                    self.log.debug('PID check OK: {} {} {}: '
                                   '{}'.format(e_sentry_name, e_proc_name,
                                               e_pids_length, a_pids))
        return None

    def validate_list_of_identical_dicts(self, list_of_dicts):
        """Check that all dicts within a list are identical."""
        hashes = []
        for _dict in list_of_dicts:
            hashes.append(hash(frozenset(_dict.items())))

        self.log.debug('Hashes: {}'.format(hashes))
        if len(set(hashes)) == 1:
            self.log.debug('Dicts within list are identical')
        else:
            return 'Dicts within list are not identical'

        return None

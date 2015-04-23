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

import ConfigParser
import io
import logging
import re
import sys
import time

import six


class AmuletUtils(object):
    """Amulet utilities.

       This class provides common utility functions that are used by Amulet
       tests.
       """

    def __init__(self, log_level=logging.ERROR):
        self.log = self.get_logger(level=log_level)

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

    def validate_services(self, commands):
        """Validate services.

           Verify the specified services are running on the corresponding
           service units.
           """
        for k, v in six.iteritems(commands):
            for cmd in v:
                output, code = k.run(cmd)
                self.log.debug('{} `{}` returned '
                               '{}'.format(k.info['unit_name'],
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
           """
        config = self._get_config(sentry_unit, config_file)

        if section != 'DEFAULT' and not config.has_section(section):
            return "section [{}] does not exist".format(section)

        for k in expected.keys():
            if not config.has_option(section, k):
                return "section [{}] is missing option {}".format(section, k)
            if config.get(section, k) != expected[k]:
                return "section [{}] {}:{} != expected {}:{}".format(
                       section, k, config.get(section, k), k, expected[k])
        return None

    def _validate_dict_data(self, expected, actual):
        """Validate dictionary data.

           Compare expected dictionary data vs actual dictionary data.
           The values in the 'expected' dictionary can be strings, bools, ints,
           longs, or can be a function that evaluate a variable and returns a
           bool.
           """
        self.log.debug('actual: {}'.format(repr(actual)))
        self.log.debug('expected: {}'.format(repr(expected)))

        for k, v in six.iteritems(expected):
            if k in actual:
                if (isinstance(v, six.string_types) or
                        isinstance(v, bool) or
                        isinstance(v, six.integer_types)):
                    if v != actual[k]:
                        return "{}:{}".format(k, actual[k])
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

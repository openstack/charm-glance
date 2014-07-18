import amulet
import re


class AmuletDeployment(object):
    """This class provides generic Amulet deployment and test runner
       methods."""

    def __init__(self, series):
        """Initialize the deployment environment."""
        self.series = series
        self.d = amulet.Deployment(series=self.series)

    def _get_charm_name(self, service_name):
        """Gets the charm name from the service name. Unique service names can
           be specified with a '-service#' suffix (e.g. mysql-service1)."""
        if re.match(r"^.*-service\d{1,3}$", service_name):
            charm_name = re.sub('\-service\d{1,3}$', '', service_name)
        else:
            charm_name = service_name
        return charm_name

    def _add_services(self, this_service, other_services):
        """Add services to the deployment where this_service is the local charm
           that we're focused on testing and other_services are the other
           charms that come from the charm store."""
        name, units = range(2)

        charm_name = self._get_charm_name(this_service[name])
        self.d.add(this_service[name],
                   units=this_service[units])

        for svc in other_services:
            charm_name = self._get_charm_name(svc[name])
            self.d.add(svc[name],
                       charm='cs:{}/{}'.format(self.series, charm_name),
                       units=svc[units])

    def _add_relations(self, relations):
        """Add all of the relations for the services."""
        for k, v in relations.iteritems():
            self.d.relate(k, v)

    def _configure_services(self, configs):
        """Configure all of the services."""
        for service, config in configs.iteritems():
            self.d.configure(service, config)

    def _deploy(self):
        """Deploy environment and wait for all hooks to finish executing."""
        try:
            self.d.setup()
            self.d.sentry.wait()
        except amulet.helpers.TimeoutError:
            amulet.raise_status(amulet.FAIL, msg="Deployment timed out")
        except:
            raise

    def run_tests(self):
        """Run all of the methods that are prefixed with 'test_'."""
        for test in dir(self):
            if test.startswith('test_'):
                getattr(self, test)()

import amulet

import os


class AmuletDeployment(object):
    """Amulet deployment.

       This class provides generic Amulet deployment and test runner
       methods.
       """

    def __init__(self, series=None):
        """Initialize the deployment environment."""
        self.series = None

        if series:
            self.series = series
            self.d = amulet.Deployment(series=self.series)
        else:
            self.d = amulet.Deployment()

    def _add_services(self, this_service, other_services):
        """Add services.

           Add services to the deployment where this_service is the local charm
           that we're focused on testing and other_services are the other
           charms that come from the charm store.
           """
        name, units = range(2)

        if this_service[name] != os.path.basename(os.getcwd()):
            s = this_service[name]
            msg = "The charm's root directory name needs to be {}".format(s)
            amulet.raise_status(amulet.FAIL, msg=msg)

        self.d.add(this_service[name], units=this_service[units])

        for svc in other_services:
            if self.series:
                self.d.add(svc[name],
                           charm='cs:{}/{}'.format(self.series, svc[name]),
                           units=svc[units])
            else:
                self.d.add(svc[name], units=svc[units])

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
            self.d.sentry.wait(timeout=900)
        except amulet.helpers.TimeoutError:
            amulet.raise_status(amulet.FAIL, msg="Deployment timed out")
        except Exception:
            raise

    def run_tests(self):
        """Run all of the methods that are prefixed with 'test_'."""
        for test in dir(self):
            if test.startswith('test_'):
                getattr(self, test)()

import os
import mock

os.environ['JUJU_UNIT_NAME'] = 'glance'

from test_utils import CharmTestCase

import actions.actions


class PauseTestCase(CharmTestCase):

    def setUp(self):
        super(PauseTestCase, self).setUp(
            actions.actions, ["service_pause", "status_set"])

    def test_pauses_services(self):
        """Pause action pauses all Glance services."""
        pause_calls = []

        def fake_service_pause(svc):
            pause_calls.append(svc)
            return True

        self.service_pause.side_effect = fake_service_pause

        actions.actions.pause([])
        self.assertItemsEqual(
            pause_calls,
            ['glance-api', 'glance-registry', 'haproxy', 'apache2'])

    def test_bails_out_early_on_error(self):
        """Pause action fails early if there are errors stopping a service."""
        pause_calls = []

        def maybe_kill(svc):
            if svc == "glance-registry":
                return False
            else:
                pause_calls.append(svc)
                return True

        self.service_pause.side_effect = maybe_kill
        self.assertRaisesRegexp(
            Exception, "glance-registry didn't stop cleanly.",
            actions.actions.pause, [])
        self.assertEqual(pause_calls, ['haproxy', 'glance-api'])

    def test_status_mode(self):
        """Pause action sets the status to maintenance."""
        status_calls = []
        self.status_set.side_effect = lambda state, msg: status_calls.append(
            state)

        actions.actions.pause([])
        self.assertEqual(status_calls, ["maintenance"])

    def test_status_message(self):
        """Pause action sets a status message reflecting that it's paused."""
        status_calls = []
        self.status_set.side_effect = lambda state, msg: status_calls.append(
            msg)

        actions.actions.pause([])
        self.assertEqual(
            status_calls, ["Paused. "
                           "Use 'resume' action to resume normal service."])


class ResumeTestCase(CharmTestCase):

    def setUp(self):
        super(ResumeTestCase, self).setUp(
            actions.actions, ["service_resume", "status_set"])

    def test_resumes_services(self):
        """Resume action resumes all Glance services."""
        resume_calls = []

        def fake_service_resume(svc):
            resume_calls.append(svc)
            return True

        self.service_resume.side_effect = fake_service_resume
        actions.actions.resume([])
        self.assertItemsEqual(
            resume_calls,
            ['glance-api', 'glance-registry', 'haproxy', 'apache2'])

    def test_bails_out_early_on_error(self):
        """Resume action fails early if there are errors starting a service."""
        resume_calls = []

        def maybe_kill(svc):
            if svc == "glance-registry":
                return False
            else:
                resume_calls.append(svc)
                return True

        self.service_resume.side_effect = maybe_kill
        self.assertRaisesRegexp(
            Exception, "glance-registry didn't start cleanly.",
            actions.actions.resume, [])
        self.assertEqual(resume_calls, ['haproxy', 'glance-api'])

    def test_status_mode(self):
        """Resume action sets the status to active."""
        status_calls = []
        self.status_set.side_effect = lambda state, msg: status_calls.append(
            state)

        actions.actions.resume([])
        self.assertEqual(status_calls, ["active"])

    def test_status_message(self):
        """Resume action sets an empty status message."""
        status_calls = []
        self.status_set.side_effect = lambda state, msg: status_calls.append(
            msg)

        actions.actions.resume([])
        self.assertEqual(status_calls, [""])


class MainTestCase(CharmTestCase):

    def setUp(self):
        super(MainTestCase, self).setUp(actions.actions, ["action_fail"])

    def test_invokes_action(self):
        dummy_calls = []

        def dummy_action(args):
            dummy_calls.append(True)

        with mock.patch.dict(actions.actions.ACTIONS, {"foo": dummy_action}):
            actions.actions.main(["foo"])
        self.assertEqual(dummy_calls, [True])

    def test_unknown_action(self):
        """Unknown actions aren't a traceback."""
        exit_string = actions.actions.main(["foo"])
        self.assertEqual("Action foo undefined", exit_string)

    def test_failing_action(self):
        """Actions which traceback trigger action_fail() calls."""
        dummy_calls = []

        self.action_fail.side_effect = dummy_calls.append

        def dummy_action(args):
            raise ValueError("uh oh")

        with mock.patch.dict(actions.actions.ACTIONS, {"foo": dummy_action}):
            actions.actions.main(["foo"])
        self.assertEqual(dummy_calls, ["uh oh"])

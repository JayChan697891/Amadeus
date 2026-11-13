"""Exercise the actual controller freshness function without credentials or a VM."""
import importlib.util
import io
import json
import time
import unittest
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

base = Path(__file__).parent
spec = importlib.util.spec_from_file_location('controller', base / 'run-once.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


class Freshness(unittest.TestCase):
    def ready(self, offset=0, **changes):
        return {'online': True, 'plan_sha256': 'expected', 'heartbeat_age_seconds': 6,
            'session_remaining_seconds': 3500,
            'timestamp': datetime.fromtimestamp(time.time() + offset, UTC).isoformat(), **changes}

    def test_remote_clock_ahead(self):
        with patch.object(controller.time, 'monotonic', return_value=113):
            controller.require_ready(self.ready(86400), 'expected', 100)

    def test_remote_clock_behind(self):
        with patch.object(controller.time, 'monotonic', return_value=113):
            controller.require_ready(self.ready(-86400), 'expected', 100)

    def rejected(self, elapsed=13, **changes):
        with patch.object(controller.time, 'monotonic', return_value=100 + elapsed):
            with self.assertRaises(AssertionError):
                controller.require_ready(self.ready(**changes), 'expected', 100)

    def test_slow_ready_at_limit(self):
        self.rejected(elapsed=20)

    def test_delay_before_copy(self):
        with patch.object(controller.time, 'monotonic', side_effect=[113, 121]):
            controller.require_ready(self.ready(), 'expected', 100)
            with self.assertRaises(AssertionError):
                controller.require_ready(self.ready(), 'expected', 100)

    def test_negative_monotonic_elapsed(self):
        self.rejected(elapsed=-1)

    def test_other_plan(self):
        self.rejected(plan_sha256='other')

    def test_offline(self):
        self.rejected(online=False)

    def test_stale_guest_heartbeat(self):
        self.rejected(heartbeat_age_seconds=20)

    def test_expiring_guest_session(self):
        self.rejected(session_remaining_seconds=120)

    def test_invalid_guest_heartbeat(self):
        self.rejected(heartbeat_age_seconds=float('nan'))


class Recorded(unittest.TextTestResult):
    def startTest(self, test):
        super().startTest(test)
        self.cases.append(ET.SubElement(self.xml, 'testcase', classname='controller.Freshness', name=test.id()))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        ET.SubElement(self.cases[-1], 'failure').text = self._exc_info_to_string(err, test)

    def addError(self, test, err):
        super().addError(test, err)
        ET.SubElement(self.cases[-1], 'error').text = self._exc_info_to_string(err, test)


Recorded.xml = ET.Element('testsuite', name='controller-monotonic-readiness')
Recorded.cases = []
stream = io.StringIO()
start = time.monotonic()
result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Recorded).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(Freshness))
elapsed = time.monotonic() - start
Recorded.xml.attrib.update(tests=str(result.testsRun), failures=str(len(result.failures)),
    errors=str(len(result.errors)), skipped=str(len(result.skipped)), time=str(elapsed))
with (base / 'readiness-tests.xml').open('xb') as out:
    ET.ElementTree(Recorded.xml).write(out, encoding='utf-8', xml_declaration=True)
with (base / 'readiness-tests.log').open('x', encoding='utf-8') as out:
    out.write(stream.getvalue())
print(json.dumps({'tests': result.testsRun, 'failures': len(result.failures),
    'errors': len(result.errors), 'model_calls': 0, 'credential_access': False}))
raise SystemExit(not result.wasSuccessful())

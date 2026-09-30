"""A neighboring Cadence install or a modified source cannot become the actor."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from . import core_runtime as core

class CoreTests(unittest.TestCase):
    def test_exact_source_set_and_changed_module_refusal(self):
        manifest=json.loads((core.RUNTIME/'manifest.json').read_text())
        self.assertEqual(core.verify_source(core.RUNTIME,manifest),core.RUNTIME)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);shutil.copytree(core.RUNTIME/'cadence',root/'cadence',ignore=shutil.ignore_patterns('__pycache__'))
            with (root/'cadence/brain.py').open('a') as f:f.write('\n# changed\n')
            with self.assertRaisesRegex(ValueError,'source changed: brain.py'):
                core.verify_source(root,manifest)
            (root/'cadence/extra.py').write_text('')
            with self.assertRaisesRegex(ValueError,'missing or extra'):
                core.verify_source(root,manifest)

if __name__=='__main__':unittest.main()

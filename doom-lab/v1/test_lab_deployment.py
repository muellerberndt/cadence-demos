"""Small source/data packaging checks; no server or cloud resource is launched."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from . import lab_deployment as deployment
from .brain import build, genome_spec, make_bundle, write_bundle
from .interface import fixed_normalizer
from .practice import attach_seed_replay
from .test_practice import seed_row
from .training import target_contract


class DeploymentTests(unittest.TestCase):
    def test_package_is_allowlisted_sources_only_and_manifest_matches_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'source'
            result = deployment.pack(root)
            actual = {str(path.relative_to(root)) for path in root.rglob('*') if path.is_file()}
            self.assertEqual(actual, set(deployment.SOURCES)|{'source_manifest.json'})
            self.assertFalse(result['credentials_included'])
            self.assertFalse(result['data_included'])
            self.assertLess(result['bytes'], 5*1024*1024)
            for name, metadata in result['files'].items():
                self.assertEqual(deployment.sha_file(root/name), metadata['sha256'])

    def test_initializer_requires_replay_and_refuses_existing_data(self):
        gene = genome_spec(topology_version=2, recursion_depth=2)
        bundle = make_bundle(build(device='python', **gene), fixed_normalizer(),
            model_id='unit/deep', genome=gene, target_contract=target_contract('centered'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'bundle.json'; write_bundle(source, bundle)
            with self.assertRaisesRegex(ValueError, 'hash-bound bootstrap'):
                deployment.initialize(source, root=root)
            self.assertFalse((root/'data').exists())
            bundle = attach_seed_replay(bundle, [seed_row()])
            platform = {'system': 'test', 'machine': 'test', 'engine_binary_sha256': '0'*64}
            bundle['metadata'].update(source_platform=platform, deployment_validation={'target_platform': platform})
            write_bundle(source, bundle)
            with patch('v1.runtime.prepare_staging_bundle', return_value=bundle), patch('v1.runtime.validate_deployment'):
                result = deployment.initialize(source, root=root)
            self.assertFalse(result['process_started'])
            self.assertEqual(result['registry_id'], 'baby-unit-deep')
            self.assertEqual(json.loads((root/'data/current_model.json').read_text())['id'], 'baby-unit-deep')
            self.assertFalse((root/'data/live_norms.json').exists())
            with self.assertRaisesRegex(FileExistsError, 'existing Lab data'):
                deployment.initialize(source, root=root)


if __name__ == '__main__':
    unittest.main()

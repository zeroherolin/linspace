import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import codex_catalog
import siteconfig


class CodexCatalogTests(unittest.TestCase):
    def setUp(self):
        self.data, self.catalog = codex_catalog.load_catalog()
        self.settings = siteconfig.tomllib.loads((ROOT / 'config/codex/config.toml').read_text())

    def test_current_preset_is_consistent_with_catalog(self):
        codex_catalog.validate_settings(self.settings, self.catalog)
        self.assertEqual(list(codex_catalog.validate_catalog(self.catalog)), ['gpt-6-astra', 'gpt-5.6-sol'])

    def test_invalid_catalog_model_ids_windows_and_reasoning_are_rejected(self):
        for field, value in [('context_window', -1), ('max_context_window', 10), ('effective_context_window_percent', 101), ('default_reasoning_level', 'unsupported')]:
            catalog = copy.deepcopy(self.catalog)
            catalog['models'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                codex_catalog.validate_catalog(catalog)
        catalog = copy.deepcopy(self.catalog)
        catalog['models'].append(copy.deepcopy(catalog['models'][0]))
        with self.assertRaisesRegex(ValueError, 'unique'):
            codex_catalog.validate_catalog(catalog)

    def test_invalid_cross_file_settings_are_rejected(self):
        for field, value in [('model', 'missing-model'), ('model_reasoning_effort', 'unsupported'), ('model_context_window', 2000000), ('model_auto_compact_token_limit', 1000001), ('model_provider', 'undefined-provider'), ('model_catalog_json', [])]:
            settings = copy.deepcopy(self.settings)
            settings[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                codex_catalog.validate_settings(settings, self.catalog)
        # An unrelated, operator-managed catalog is not checked against our IDs.
        codex_catalog.validate_settings({'model_catalog_json': 'other.json', 'model': 'other-model'}, self.catalog)

    def test_compaction_checks_effective_window_and_allows_omitted_defaults(self):
        catalog = copy.deepcopy(self.catalog)
        catalog['models'][0]['effective_context_window_percent'] = 95
        settings = copy.deepcopy(self.settings)
        settings['model_auto_compact_token_limit'] = 960000
        with self.assertRaisesRegex(ValueError, 'usable context'):
            codex_catalog.validate_settings(settings, catalog)
        codex_catalog.validate_settings({}, self.catalog)

    def test_refresh_keeps_each_models_instructions_and_only_changes_window_policy(self):
        source = copy.deepcopy(self.catalog)
        source['models'][0]['base_instructions'] = 'Astra-specific instructions'
        source['models'][1]['base_instructions'] = 'Sol-specific instructions'
        for model in source['models']:
            model.update(context_window=272000, max_context_window=872000, effective_context_window_percent=95)
        snapshot = copy.deepcopy(source)
        data, manifest = codex_catalog.generate(json.dumps(source).encode(), 'test-version')
        self.assertEqual(source, snapshot)
        generated = json.loads(data)
        for actual, original in zip(generated['models'], source['models']):
            self.assertEqual(actual['base_instructions'], original['base_instructions'])
            differing = {key for key in actual if actual[key] != original.get(key)}
            self.assertEqual(differing, set(codex_catalog.OVERRIDES))
        self.assertEqual(manifest['models'], list(codex_catalog.MODEL_IDS))
        with self.assertRaisesRegex(ValueError, 'both configured models'):
            codex_catalog.generate(json.dumps({'models': source['models'][:1]}).encode(), 'test-version')

    def test_source_checksum_rejects_catalog_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'config/codex'
            folder.mkdir(parents=True)
            (folder / 'models-1m.json').write_bytes(self.data)
            (folder / 'catalog-source.json').write_bytes((ROOT / 'config/codex/catalog-source.json').read_bytes())
            codex_catalog.load_catalog(root)
            (folder / 'models-1m.json').write_bytes(self.data + b'\n')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                codex_catalog.load_catalog(root)

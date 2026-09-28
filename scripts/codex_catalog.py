"""Maintain the public Codex catalog and validate its configuration contract."""
from linspace_console import linspace_log
import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_IDS = ('gpt-6-astra', 'gpt-5.6-sol')
OVERRIDES = {'context_window': 1000000, 'max_context_window': 1050000, 'effective_context_window_percent': 100}


def positive_integer(value):
    return type(value) is int and value > 0


def validate_catalog(catalog):
    entries = catalog.get('models') if isinstance(catalog, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError('Codex model catalog must contain a nonempty models array')
    models = {}
    for model in entries:
        slug = model.get('slug') if isinstance(model, dict) else None
        if not isinstance(slug, str) or not slug or slug in models:
            raise ValueError('Codex catalog model IDs must be nonempty and unique')
        window, maximum, percent = (model.get(k) for k in ('context_window', 'max_context_window', 'effective_context_window_percent'))
        if not positive_integer(window) or not positive_integer(maximum) or window > maximum or type(percent) is not int or not 1 <= percent <= 100:
            raise ValueError('Codex catalog has invalid context-window limits')
        levels = model.get('supported_reasoning_levels')
        if not isinstance(levels, list) or not levels or any(not isinstance(item, dict) or not isinstance(item.get('effort'), str) or not item['effort'] for item in levels):
            raise ValueError('Codex catalog must advertise reasoning levels')
        efforts = [item['effort'] for item in levels]
        if len(set(efforts)) != len(efforts) or model.get('default_reasoning_level') not in efforts:
            raise ValueError('Codex catalog default reasoning level must be advertised without duplicates')
        models[slug] = model
    return models


def load_catalog(root=ROOT):
    directory = root / 'config/codex'
    data = (directory / 'models-1m.json').read_bytes()
    source = json.loads((directory / 'catalog-source.json').read_text())
    if not isinstance(source, dict):
        raise ValueError('Codex catalog source record must be a JSON object')
    if hashlib.sha256(data).hexdigest() != source.get('catalog_sha256'):
        raise ValueError('Codex catalog checksum mismatch; regenerate it with scripts/codex_catalog.py --refresh')
    catalog = json.loads(data)
    models = validate_catalog(catalog)
    if list(models) != list(MODEL_IDS) or list(models) != source.get('models') or source.get('overrides') != OVERRIDES:
        raise ValueError('Codex catalog and its source record disagree')
    if any(any(model.get(key) != value for key, value in OVERRIDES.items()) for model in models.values()):
        raise ValueError('Codex catalog does not match the declared 1M overrides')
    return data, catalog


def validate_settings(settings, catalog):
    """Check what can be verified offline without imposing every CLI default."""
    models = validate_catalog(catalog)
    for key in ('model', 'model_provider', 'model_catalog_json', 'model_reasoning_effort'):
        if key in settings and (not isinstance(settings[key], str) or not settings[key]):
            raise ValueError(f'Codex {key} must be a nonempty string')
    linked = settings.get('model_catalog_json') in {'models-1m.json', './models-1m.json'}
    selected = settings.get('model')
    if linked and selected is not None and selected not in models:
        raise ValueError('Selected Codex model is absent from the bundled catalog')
    model = models.get(selected) if linked else None
    if model and 'model_reasoning_effort' in settings:
        if settings['model_reasoning_effort'] not in {level['effort'] for level in model['supported_reasoning_levels']}:
            raise ValueError('Codex reasoning effort is not supported by the selected catalog model')
    window = settings.get('model_context_window', model['context_window'] if model else None)
    limit = settings.get('model_auto_compact_token_limit')
    if window is not None and (not positive_integer(window) or model and window > model['max_context_window']):
        raise ValueError('Codex context window exceeds the selected model limit or is invalid')
    usable = window * (model['effective_context_window_percent'] if model else 100) // 100 if window is not None else None
    if limit is not None and (not positive_integer(limit) or usable is not None and limit > usable):
        raise ValueError('Codex auto-compaction threshold exceeds the usable context window or is invalid')
    provider = settings.get('model_provider', 'openai')
    if provider not in {'openai', 'ollama', 'lmstudio', 'amazon-bedrock'}:
        providers = settings.get('model_providers', {})
        if not isinstance(providers, dict) or not isinstance(providers.get(provider), dict):
            raise ValueError('Selected custom Codex provider has no definition')


def generate(source_data, version):
    """Preserve each official model entry, overriding only the window policy."""
    source = json.loads(source_data)
    entries = source.get('models') if isinstance(source, dict) else source
    if not isinstance(entries, list):
        raise ValueError('Expected a catalog exported by codex debug models --bundled')
    if any(not isinstance(model, dict) or not isinstance(model.get('slug'), str) for model in entries):
        raise ValueError('The exported Codex catalog has invalid model entries')
    by_id = {model['slug']: model for model in entries}
    if len(by_id) != len(entries):
        raise ValueError('The exported Codex catalog has duplicate model IDs')
    if any(slug not in by_id for slug in MODEL_IDS):
        raise ValueError('The installed Codex catalog does not include both configured models')
    models = []
    for slug in MODEL_IDS:
        model = copy.deepcopy(by_id[slug])
        model.update(OVERRIDES)
        models.append(model)
    catalog = {'models': models}
    validate_catalog(catalog)
    data = (json.dumps(catalog, ensure_ascii=False, indent=2) + '\n').encode()
    manifest = {'codex_cli_version': version, 'source_command': 'codex debug models --bundled',
                'source_sha256': hashlib.sha256(source_data).hexdigest(), 'models': list(MODEL_IDS),
                'overrides': OVERRIDES, 'catalog_sha256': hashlib.sha256(data).hexdigest()}
    return data, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='regenerate from the installed official Codex CLI; review the diff before deployment')
    parser.add_argument('--codex', default='codex', help='Codex executable used only by --refresh')
    args = parser.parse_args()
    if args.refresh:
        version = subprocess.check_output([args.codex, '--version'], text=True, timeout=30).strip().removeprefix('codex-cli ')
        source = subprocess.check_output([args.codex, 'debug', 'models', '--bundled'], timeout=30)
        data, manifest = generate(source, version)
        directory = ROOT / 'config/codex'
        (directory / 'models-1m.json').write_bytes(data)
        (directory / 'catalog-source.json').write_text(json.dumps(manifest, indent=2) + '\n')
    _, catalog = load_catalog()
    linspace_log('OK', 'Codex catalog checked: ' + ', '.join(validate_catalog(catalog)))


if __name__ == '__main__':
    main()

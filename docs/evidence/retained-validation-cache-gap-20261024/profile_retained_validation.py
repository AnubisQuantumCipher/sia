"""Measure actual private-fixture warm and fresh validation; not acceptance."""
import cProfile
import hashlib
import json
from pathlib import Path
import pstats
import resource
import time

import siasourcebatch as batches
import siasourcecheckpoint as captures
from tests.test_retained_validation_context import RetainedValidationContext
from tests.test_retained_validation_context import clear_validation_memos


ROOT = Path('/tmp/sia-review-source')


def measure(label, validate, owner, image):
    profile = cProfile.Profile()
    started = time.perf_counter_ns()
    result = profile.runcall(validate, owner, image, image['batch_sha256'])
    elapsed = time.perf_counter_ns() - started
    if result is not None:
        raise AssertionError('retained validator returned an unexpected value')
    stats = pstats.Stats(profile).stats
    if len(stats) > 8192:
        raise ValueError('profile entry capacity')
    rows = []
    for (filename, line, name), (primitive, calls, own, cumulative, _callers) in stats.items():
        rows.append({'file': filename, 'line': line, 'name': name,
                     'primitive_calls': primitive, 'calls': calls,
                     'own_seconds': own, 'cumulative_seconds': cumulative})
    rows.sort(key=lambda row: row['cumulative_seconds'], reverse=True)
    return {'mode': label, 'elapsed_ns': elapsed,
            'process_peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'functions': rows}


def observed_sources(records):
    paths = set()
    for record in records:
        for row in record['measurements']:
            for entry in row['functions']:
                path = Path(entry['file'])
                if path.is_relative_to(ROOT) and path.is_file():
                    paths.add(path)
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def main():
    case = RetainedValidationContext(methodName='runTest')
    case.setUp()
    records = []
    try:
        with case.images() as (owner, images):
            for validate, image in images:
                clear_validation_memos()
                if validate(owner, image, image['batch_sha256']) is not None:
                    raise AssertionError('initial validation failed')
                fresh = batches._validate_batch_image if validate is batches.validate_batch \
                    else captures._validate_capture_image
                records.append({'schema': image['schema'],
                    'image_native_bytes': len(batches.native_bytes(owner, image)),
                    'measurements': [measure('warm', validate, owner, image),
                                     measure('fresh', fresh, owner, image)]})
    finally:
        case.doCleanups()
    print(json.dumps({'status': 'OBSERVED_SMALL_PRIVATE_FIXTURE_ONLY',
        'scope': 'cProfile wall time and process cumulative peak RSS; no full-capacity or unprofiled deadline claim',
        'records': records, 'observed_source_sha256': observed_sources(records)}, indent=2))


if __name__ == '__main__':
    main()

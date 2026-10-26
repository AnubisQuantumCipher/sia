"""Original preflight order remains observable before fresh admission."""
import unittest
from unittest import mock

import siasourcebatch as batch


class Preflight(unittest.TestCase):
    def tearDown(self):
        batch._VALIDATED_BATCHES.clear()

    def test_initial_digest_refusal_precedes_image_validator(self):
        with mock.patch.object(batch, 'native_sha', side_effect=ValueError('digest refusal')), \
                mock.patch.object(batch, '_validate_batch_image') as full:
            with self.assertRaisesRegex(ValueError, '^digest refusal$'):
                batch.validate_batch({'MAX_STATE_JSON_BYTES': 128}, {}, '0' * 64)
        full.assert_not_called()

    def test_preflight_retains_original_owner_reads(self):
        trace = []

        class Owner(dict):
            def get(self, key, default=None):
                trace.append(('get', key))
                return super().get(key, default)

        owner = Owner(MAX_STATE_JSON_BYTES=128, VERSION='diagnostic')

        def digest(_owner, _image):
            trace.append(('digest',))
            return '1' * 64

        def validate(_owner, _image, _pin):
            trace.append(('full',))
            return None

        with mock.patch.object(batch, 'native_sha', digest), \
                mock.patch.object(batch, '_validate_batch_image', validate):
            batch.validate_batch(owner, {}, '0' * 64)
        self.assertEqual(trace, [('digest',), ('get', 'MAX_STATE_JSON_BYTES'),
                                 ('get', 'VERSION'), ('full',)])

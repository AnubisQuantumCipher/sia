"""Independent DESIGN-vector checks; crypto validity is not authorization.

No generator import. OpenSSL CLI is a separate interface but may share the
OpenSSL backend used by cryptography; this is not implementation diversity.
"""
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

FIXTURE = Path(__file__).with_name('protected_slot_vectors.json')
LABELS = {
    'operation_digest': b'SIA-SLOT-OP-DIGEST/1\0',
    'publish_current_digest': b'SIA-SLOT-REQUEST-DIGEST/1\0',
    'query_current_digest': b'SIA-SLOT-REQUEST-DIGEST/1\0',
    'historical_publish_digest': b'SIA-SLOT-PUBLISH-DIGEST/1\0',
}
SIGN_LABEL = b'SIA-SLOT-GRANT-SIGNATURE/1\0'


def sha(data):
    return hashlib.sha256(data).digest()


def number(value):
    return value.to_bytes(8, 'big')


def repeated(value):
    return bytes([value]) * 32


class ProtectedSlotVectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with FIXTURE.open('rb') as stream:
            raw = stream.read(262145)
        if len(raw) > 262144:
            raise ValueError('fixture exceeds review bound')
        cls.document = json.loads(raw)
        cls.openssl = shutil.which('openssl')
        if cls.openssl is None:
            raise RuntimeError('OpenSSL required; no silent crypto skip')
        cls.temporary = tempfile.TemporaryDirectory(prefix='sia-slot-vectors-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        if len(cls.document['cases']) != 3:
            raise ValueError('unsupported fixture count')

    def raw(self, case, name, size):
        text = case[name]
        self.assertEqual(len(text), size * 2)
        self.assertTrue(all(c in '0123456789abcdef' for c in text))
        return bytes.fromhex(text)

    def auth(self, public, query):
        values = (21, 22, 24, 25, 26) if query else (1, 2, 4, 5, 6)
        issuer, capability, clock, boot, service = [repeated(v) for v in values]
        return issuer + capability + sha(public) + clock + boot + service + number(2000 if query else 1000)

    def expected_operation(self, public, payload):
        return (repeated(7) + repeated(8) + sha(b'SIA-PROTECTED-SLOT-OPERATION/1')
                + repeated(1) + sha(public) + repeated(4) + repeated(5)
                + repeated(6) + repeated(2) + repeated(9) + sha(payload)
                + number(1000) + number(7) + number(8) + number(len(payload)))

    def check_prefix(self, raw, kind, size):
        self.assertEqual(raw[:8], b'SIASLOT1')
        self.assertEqual(raw[8:12], bytes((kind, 1, 0, 0)))
        self.assertEqual(int.from_bytes(raw[12:16], 'big'), size)
        self.assertEqual(len(raw), size)

    def check_request(self, raw, kind, auth, operation, target, payload):
        self.check_prefix(raw, kind, 4728)
        self.assertEqual(raw[16:216], auth)
        self.assertEqual(raw[216:600], operation)
        self.assertEqual(raw[600:632], target)
        area = payload + bytes(4096 - len(payload)) if kind == 1 else bytes(4096)
        self.assertEqual(raw[632:], area)
        for start in (208, 568):
            self.assertEqual(raw[start:start + 4], bytes(4))
            self.assertGreater(int.from_bytes(raw[start:start + 8], 'big'), 0)
        for start in (576, 584):
            self.assertLess(raw[start], 128)
        self.assertEqual(int.from_bytes(raw[592:600], 'big'), len(payload))

    def check_grant(self, raw, auth, operation, target, action):
        self.check_prefix(raw, 3, 720)
        self.assertEqual(raw[16:216], auth)
        self.assertEqual(raw[216:600], operation)
        self.assertEqual(raw[600:632], target)
        self.assertEqual(raw[632:640], number(10))
        self.assertEqual(raw[640:648], number(20))
        self.assertEqual(raw[648:656], bytes((action, 1)) + bytes(6))
        self.assertLess(raw[632], 128)
        self.assertLess(raw[640], 128)

    def test_exact_bytes_and_hash_domains(self):
        public = bytes.fromhex(self.document['publication_public_key_hex'])
        reader = bytes.fromhex(self.document['read_public_key_hex'])
        expected = {'empty': b'', 'nonempty': b'abc', 'capacity': bytes(range(256)) * 16}
        self.assertEqual({c['name'] for c in self.document['cases']}, set(expected))
        for case in self.document['cases']:
            payload = expected[case['name']]
            self.assertEqual(bytes.fromhex(case['payload_hex']), payload)
            operation = self.expected_operation(public, payload)
            publish = self.raw(case, 'publish_hex', 4728)
            query = self.raw(case, 'query_hex', 4728)
            target = sha(LABELS['historical_publish_digest'] + publish)
            self.check_request(publish, 1, self.auth(public, False), operation, bytes(32), payload)
            self.check_request(query, 2, self.auth(reader, True), operation, target, payload)
            self.assertNotEqual(publish[16:216], query[16:216])
            self.assertEqual(publish[216:600], query[216:600])
            values = (operation, publish, query, publish)
            hashes = []
            for (name, label), value in zip(LABELS.items(), values):
                result = sha(label + value)
                self.assertEqual(result.hex(), case[name])
                hashes.append(result)
            self.assertEqual(len(set(hashes)), 4)
            self.check_grant(self.raw(case, 'publication_grant_hex', 720), self.auth(public, False), operation, bytes(32), 1)
            self.check_grant(self.raw(case, 'read_grant_hex', 720), self.auth(reader, True), operation, target, 2)

    def test_public_fixture_seeds_match_openssl_keys(self):
        for role, seed in (('publication', bytes(range(32))),
                           ('read', bytes(reversed(range(32))))):
            self.assertEqual(self.document[role + '_seed_hex'], seed.hex())
            private = self.root / 'public-test-seed.der'
            private.write_bytes(bytes.fromhex('302e020100300506032b657004220420') + seed)
            result = subprocess.run([self.openssl, 'pkey', '-inform', 'DER',
                                     '-in', str(private), '-pubout', '-outform', 'DER'],
                                    capture_output=True, timeout=3, check=True)
            expected = bytes.fromhex('302a300506032b6570032100')
            expected += bytes.fromhex(self.document[role + '_public_key_hex'])
            self.assertEqual(result.stdout, expected)

    _run_openssl = staticmethod(subprocess.run)

    def verify(self, public, signature, message):
        # RFC 8410 SubjectPublicKeyInfo wrapper; public fixture material only.
        (self.root / 'key.der').write_bytes(bytes.fromhex('302a300506032b6570032100') + public)
        (self.root / 'sig').write_bytes(signature)
        (self.root / 'message').write_bytes(message)
        result = self._run_openssl([self.openssl, 'pkeyutl', '-verify', '-pubin', '-keyform', 'DER',
                                 '-inkey', str(self.root / 'key.der'), '-rawin',
                                 '-in', str(self.root / 'message'), '-sigfile', str(self.root / 'sig')],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
        if (result.returncode, result.stdout, result.stderr) == (
                0, b'Signature Verified Successfully\n', b''):
            return True
        rejection = (rb'[0-9A-F]{16}:error:030000EA:digital envelope routines:'
                     rb'EVP_DigestVerify:provider signature failure:'
                     rb'crypto/evp/m_sigver.c:785:ED25519 digest_verify:\n')
        if (result.returncode == 1 and
                result.stdout == b'Signature Verification Failure\n' and
                re.fullmatch(rejection, result.stderr) is not None):
            return False
        raise RuntimeError('unexpected OpenSSL verification result: ' +
                           repr((result.returncode, result.stdout, result.stderr)))

    def test_unrelated_openssl_failure_is_not_signature_rejection(self):
        public = bytes.fromhex(self.document['publication_public_key_hex'])
        failures = ((-9, b'', b''), (127, b'', b'missing library\n'),
                    (1, b'Signature Verification Failure\n', b'unrelated failure\n'),
                    (0, b'unexpected success output\n', b''))
        for code, stdout, stderr in failures:
            result = subprocess.CompletedProcess([], code, stdout, stderr)
            with self.subTest(code=code, stderr=stderr), \
                    mock.patch.object(self, '_run_openssl', return_value=result), \
                    self.assertRaisesRegex(RuntimeError, 'unexpected OpenSSL'):
                self.verify(public, bytes(64), b'public fixture input')

    def test_openssl_signatures_and_each_signed_byte_mutation(self):
        for case in self.document['cases']:
            for field, key in (('publication_grant_hex', 'publication_public_key_hex'),
                               ('read_grant_hex', 'read_public_key_hex')):
                grant = self.raw(case, field, 720)
                public = bytes.fromhex(self.document[key])
                message, signature = SIGN_LABEL + grant[:656], grant[656:]
                self.assertTrue(self.verify(public, signature, message))
                for index in range(len(message)):
                    changed = bytearray(message)
                    changed[index] ^= 1
                    self.assertFalse(self.verify(public, signature, changed),
                                     (case['name'], field, index))
                wrong_key = bytes.fromhex(self.document['read_public_key_hex' if field == 'publication_grant_hex' else 'publication_public_key_hex'])
                self.assertFalse(self.verify(wrong_key, signature, message))
                for bad in (grant[:656], SIGN_LABEL[:-1] + grant[:656],
                            b'SIA-SLOT-REQUEST-DIGEST/1\0' + grant[:656],
                            sha(message), message[:-1], message + b'\0'):
                    self.assertFalse(self.verify(public, signature, bad))
                for bad_signature in (signature[:-1], signature + b'\0'):
                    self.assertFalse(self.verify(public, bad_signature, message))
                changed_signature = bytearray(signature)
                changed_signature[0] ^= 1
                self.assertFalse(self.verify(public, changed_signature, message))


if __name__ == '__main__':
    unittest.main()

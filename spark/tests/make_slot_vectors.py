"""Deterministic DESIGN fixtures. Public test keys; no authority or live I/O."""
import hashlib
import json
import struct

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def digest(raw):
    return hashlib.sha256(raw).digest()


def tagged(label, raw):
    return digest(label.encode("ascii") + b"\0" + raw)


def identity(value):
    return bytes([value]) * 32


def key(seed):
    private = Ed25519PrivateKey.from_private_bytes(seed)
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, public


def context(public, query):
    values = (21, 22, 24, 25, 26) if query else (1, 2, 4, 5, 6)
    issuer, capability, clock, boot, service = map(identity, values)
    uid = 2000 if query else 1000
    return (issuer + capability + digest(public) + clock + boot + service
            + struct.pack(">Q", uid))


def operation(publication_context, payload):
    issuer, capability, pubkey, clock, boot, service, uid = struct.unpack(
        ">32s32s32s32s32s32sQ", publication_context)
    return (identity(7) + identity(8)
            + digest(b"SIA-PROTECTED-SLOT-OPERATION/1")
            + issuer + pubkey + clock + boot + service
            + capability + identity(9) + digest(payload)
            + struct.pack(">QQQQ", uid, 7, 8, len(payload)))


def prefix(kind, size):
    return b"SIASLOT1" + struct.pack(">BBHI", kind, 1, 0, size)


def request(kind, auth, op, target, payload):
    if kind not in (1, 2) or len(payload) > 4096:
        raise ValueError("fixture input outside fixed domain")
    area = payload.ljust(4096, b"\0") if kind == 1 else bytes(4096)
    raw = prefix(kind, 4728) + auth + op + target + area
    if len(raw) != 4728:
        raise ValueError("fixture request layout mismatch")
    return raw


def grant(private, auth, op, target, action):
    body = (prefix(3, 720) + auth + op + target
            + struct.pack(">QQBB6x", 10, 20, action, 1))
    if len(body) != 656:
        raise ValueError("fixture grant layout mismatch")
    signature = private.sign(b"SIA-SLOT-GRANT-SIGNATURE/1\0" + body)
    if len(signature) != 64:
        raise ValueError("fixture signature size mismatch")
    return body + signature


def case(name, payload, publisher, reader):
    pub_private, pub_public = publisher
    read_private, read_public = reader
    pub_auth, read_auth = context(pub_public, False), context(read_public, True)
    op = operation(pub_auth, payload)
    publish = request(1, pub_auth, op, bytes(32), payload)
    target = tagged("SIA-SLOT-PUBLISH-DIGEST/1", publish)
    query = request(2, read_auth, op, target, b"")
    return {
        "name": name, "payload_hex": payload.hex(),
        "publish_hex": publish.hex(), "query_hex": query.hex(),
        "publication_grant_hex": grant(pub_private, pub_auth, op, bytes(32), 1).hex(),
        "read_grant_hex": grant(read_private, read_auth, op, target, 2).hex(),
        "operation_digest": tagged("SIA-SLOT-OP-DIGEST/1", op).hex(),
        "publish_current_digest": tagged("SIA-SLOT-REQUEST-DIGEST/1", publish).hex(),
        "query_current_digest": tagged("SIA-SLOT-REQUEST-DIGEST/1", query).hex(),
        "historical_publish_digest": target.hex(),
    }


def main():
    publication_seed, read_seed = bytes(range(32)), bytes(reversed(range(32)))
    publisher, reader = key(publication_seed), key(read_seed)
    fixtures = (
        ("empty", b""), ("nonempty", b"abc"),
        ("capacity", bytes(range(256)) * 16),
    )
    document = {
        "status": "DESIGN fixtures; not authorized operations",
        "warning": "PUBLIC TEST SEEDS: never provision these keys or grants",
        "publication_seed_hex": publication_seed.hex(),
        "read_seed_hex": read_seed.hex(),
        "publication_public_key_hex": publisher[1].hex(),
        "read_public_key_hex": reader[1].hex(),
        "cases": [case(name, payload, publisher, reader) for name, payload in fixtures],
    }
    print(json.dumps(document, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

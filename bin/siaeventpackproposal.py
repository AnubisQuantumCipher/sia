"""Inactive pack proposal representation; hashes do not authorize effects."""
import hashlib

import siaeventpack as codec
import siaeventpackplan as planner

FRAME_BYTES = 16_384
MANIFEST_TAG = b"SIA-PACK-RECORDS-v1\0"
PLAN_TAG = b"SIA-PACK-PLAN-BINDING-v1\0"
ZERO = bytes(32)


def digest(label, raw):
    """Domain separation is part of the versioned representation contract."""
    return hashlib.sha256(b"SIA-PACK-" + label + b"-v1\0" + raw).digest()


def request(value):
    if type(value) is not tuple or len(value) != 4:
        raise ValueError("pack proposal request shape")
    epoch, transaction, revision, permission = value
    if type(epoch) is not int or not 1 <= epoch <= 2**63 - 1:
        raise ValueError("pack proposal epoch range")
    if any(type(item) is not bytes or len(item) != 32
           for item in (transaction, revision, permission)):
        raise ValueError("pack proposal request digest shape")


def references(organ, prefix, records):
    # Reuse the original complete native-input admission, without a prior pack.
    planner._inputs(organ, prefix, records, None,
                    (planner.MAX_INPUT_RECORDS, planner.MAX_RECORD_BYTES,
                     planner.MAX_INPUT_BYTES))
    return tuple(bytes.fromhex(identifier.decode("ascii"))
                 + hashlib.sha256(raw).digest() + len(raw).to_bytes(8, "big")
                 for identifier, raw in records)


def _reference_shape(value, maximum):
    if type(value) is not tuple or len(value) > maximum or any(
            type(item) is not bytes or len(item) != 72 for item in value):
        raise ValueError("pack proposal reference shape")


def manifest(references_value):
    _reference_shape(references_value, planner.MAX_INPUT_RECORDS)
    return MANIFEST_TAG + len(references_value).to_bytes(8, "big") + b"".join(references_value)


def roster(references_value):
    _reference_shape(references_value, codec.MAX_RECORDS)
    return (len(references_value).to_bytes(8, "big") + b"".join(references_value)
            + bytes((codec.MAX_RECORDS - len(references_value)) * 72))


def identity(frame):
    """Byte binding only; producer identity and policy admission are external."""
    if type(frame) is not bytes or len(frame) != FRAME_BYTES:
        raise ValueError("pack proposal frame shape")
    hasher = hashlib.sha256(PLAN_TAG)
    hasher.update(frame[:8])
    hasher.update(frame[40:])
    return hasher.digest()


def identity_matches(frame):
    return identity(frame) == frame[8:40]


def encode(organ, prefix, operation, scope, prior, target, represented,
           selected_count, fallback_count, originals):
    """Marshal an internal proposal; SPARK remains the policy decision path."""
    request(operation)
    if type(scope) is not tuple or len(scope) != 6:
        raise ValueError("pack proposal scope shape")
    for rows in (prior, target, represented):
        _reference_shape(rows, codec.MAX_RECORDS)
    organ_raw, _ = codec._route(organ, prefix)
    epoch, transaction, revision, permission = operation
    corpus, capture, selection, fallback, old_target, new_target = scope
    context = (transaction, corpus, digest(b"ORGAN", organ_raw),
               digest(b"PREFIX", prefix.encode("ascii")), revision, capture,
               selection, fallback, old_target, new_target, permission)
    if any(type(item) is not bytes or len(item) != 32 for item in context):
        raise ValueError("pack proposal scope digest shape")
    if any(type(count) is not int or not 0 <= count <= planner.MAX_INPUT_RECORDS
           for count in (selected_count, fallback_count)):
        raise ValueError("pack proposal selection count")
    if type(originals) is not tuple or len(originals) != len(represented):
        raise ValueError("pack proposal original roster")
    flags, generations = bytearray(64), bytearray(64 * 32)
    for index, item in enumerate(originals):
        if type(item) is not tuple or len(item) != 2:
            raise ValueError("pack proposal original shape")
        present, generation = item
        if type(present) is not bool or type(generation) is not bytes or len(generation) != 32:
            raise ValueError("pack proposal original shape")
        flags[index] = int(present)
        generations[index * 32:(index + 1) * 32] = generation
    frame = (b"\x01" + bytes(39) + epoch.to_bytes(8, "big") + b"".join(context)
             + len(organ_raw).to_bytes(8, "big") + selected_count.to_bytes(8, "big")
             + fallback_count.to_bytes(8, "big") + roster(prior) + roster(target)
             + roster(represented) + bytes(flags) + bytes(generations))
    return frame[:8] + identity(frame) + frame[40:]

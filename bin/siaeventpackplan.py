"""Unactivated exact-coverage transport planner; no source or effect authority.

The immutable result is (pack bytes or None, represented inputs, fallback inputs).
Represented means byte coverage only, never permission to delete a source.
Current lineage, full inventory, generations, durable intent and protected
authorization must be established by a future applying transaction.
"""

import siaeventpack as codec

# Current source ceilings, not an option to increase the owner's live policy.
MAX_INPUT_RECORDS = 65_536
MAX_RECORD_BYTES = 65_536
MAX_INPUT_BYTES = 16_777_216


def _limits(limits):
    if type(limits) is not tuple or len(limits) != 3:
        raise ValueError("event pack plan limits are invalid")
    ceilings = (MAX_INPUT_RECORDS, MAX_RECORD_BYTES, MAX_INPUT_BYTES)
    for value, ceiling in zip(limits, ceilings, strict=True):
        if type(value) is not int or not 1 <= value <= ceiling:
            raise ValueError("event pack plan limit is invalid")


def _inputs(organ, prefix, records, prior_pack, limits):
    _limits(limits)
    framing = codec.header_size(organ, prefix)
    if type(records) is not tuple or len(records) > limits[0]:
        raise ValueError("event pack plan input count is invalid")
    if prior_pack is not None and type(prior_pack) is not bytes:
        raise ValueError("event pack plan prior frame is invalid")
    if prior_pack is not None and len(prior_pack) > codec.MAX_BYTES:
        raise ValueError("event pack plan prior frame exceeds capacity")
    amount = framing + (0 if prior_pack is None else len(prior_pack))
    if amount > limits[2]:
        raise ValueError("event pack plan input byte capacity")
    previous, route = b"", prefix.encode("ascii")
    for item in records:
        if type(item) is not tuple or len(item) != 2:
            raise ValueError("event pack plan record shape is invalid")
        identifier, raw = item
        codec._record(identifier, raw, route, previous)
        if len(raw) > limits[1]:
            raise ValueError("event pack plan record exceeds current capacity")
        amount += 68 + len(raw)
        if amount > limits[2]:
            raise ValueError("event pack plan input byte capacity")
        previous = identifier
    prior = () if prior_pack is None else codec.decode(prior_pack, organ, prefix)
    if any(len(raw) > limits[1] for _identifier, raw in prior):
        raise ValueError("event pack plan prior record exceeds current capacity")
    return framing, prior


def _overlap(records, selected):
    for identifier, raw in records:
        if identifier in selected and selected[identifier] != raw:
            raise ValueError("event pack plan representations conflict")


def plan(organ, prefix, records, prior_pack, *, limits):
    """Partition every admitted input without mutating or discarding records.

    Limits are native (input count, per-record bytes, logical input bytes).
    Logical input includes a header, prior frame and each input's 68-byte
    record framing plus payload. Output is separately bounded by codec caps;
    neither figure is a proof of Python object or allocator memory bounds.
    Limits are caller-supplied observations, not permission or policy custody.
    """
    framing, prior = _inputs(organ, prefix, records, prior_pack, limits)
    selected = dict(prior)
    _overlap(records, selected)
    represented, fallback = [], []
    size = framing if prior_pack is None else len(prior_pack)
    for item in records:
        identifier, raw = item
        if identifier in selected:
            represented.append(item)
        elif len(selected) < codec.MAX_RECORDS and size + 68 + len(raw) <= codec.MAX_BYTES:
            selected[identifier] = raw
            size += 68 + len(raw)
            represented.append(item)
        else:
            fallback.append(item)
    if len(selected) == len(prior):
        packed = prior_pack
    else:
        packed = codec.encode(organ, prefix, tuple(sorted(selected.items())))
    return packed, tuple(represented), tuple(fallback)

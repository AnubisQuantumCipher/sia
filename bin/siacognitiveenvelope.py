"""Bound closed multi-document calls without widening any document's ceiling.

Layouts are fixed by the calling component's versioned contract, never taken
from an evidence artifact. None marks a complete document or scalar pin;
dictionary nodes specify every permitted envelope field. Admission neither
authenticates these documents nor replaces their semantic/source replay gates.
No partial envelope, ignored field, shared-reference discount or copied result
is produced. Existing single-artifact and v1 APIs remain unchanged.
"""

import siacognitivebaseline as baseline


MAX_INPUT_BYTES = 67108864
MAX_DOCUMENT_BYTES = baseline.MAX_ARTIFACT_BYTES
MAX_LAYOUT_BYTES = 16384


class EnvelopeRefusal(ValueError):
    """The complete envelope or a constituent document exceeds its contract."""


def _fail(reason):
    raise EnvelopeRefusal("cognitive envelope refused: " + reason)


def admit_compound(*, envelope, layout, max_input_bytes, max_document_bytes):
    """Admit a caller-declared closed topology; return no data or assurance."""
    try:
        for limit, ceiling in ((max_input_bytes, MAX_INPUT_BYTES),
                               (max_document_bytes, MAX_DOCUMENT_BYTES)):
            if type(limit) is not int or not 0 < limit <= ceiling:
                _fail("a declared limit is invalid or exceeds its hard ceiling")
        if max_document_bytes > max_input_bytes:
            _fail("document limit exceeds the complete envelope limit")
        if type(layout) is not dict:
            _fail("layout root must be a closed dictionary")
        baseline._bounded(layout, MAX_LAYOUT_BYTES)
        # Complete shape/domain admission precedes all serialization, including
        # earlier documents when a later branch is cyclic or nonfinite.
        baseline._bounded(envelope, max_input_bytes)
        documents = []

        def visit(value, node):
            if node is None:
                baseline._bounded(value, max_document_bytes)
                documents.append(value)
                return
            if type(node) is not dict or type(value) is not dict or set(value) != set(node):
                _fail("envelope differs from its complete closed document layout")
            for key, child in node.items():
                visit(value[key], child)

        visit(envelope, layout)
        # Structural work bounds are not exact JSON byte counts. Enforce both
        # original document wire limits and the declared aggregate wire limit.
        # Shared document references are counted each time they occur on wire.
        for document in documents:
            baseline._canonical(document, max_document_bytes)
        baseline._canonical(envelope, max_input_bytes)
    except EnvelopeRefusal:
        raise
    except (baseline.BaselineRefusal, ValueError, TypeError, KeyError,
            OverflowError, RecursionError) as exc:
        raise EnvelopeRefusal("cognitive envelope could not be admitted: " + str(exc)) from exc

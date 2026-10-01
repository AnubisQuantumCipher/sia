"""Private, externally pinned command transport for the committed baseline.

The request owns every baseline input except the independently supplied output
directory. It is an exact owner-private ordinary file, copied to a sealed
descriptor, with its named generation checked before and after invocation.
No resident readiness, corpus, index, model or alternate source-root fallback
is part of this capability. The command emits only a small receipt; private
rows and answer material remain in the baseline's independently published file.
"""

import copy
import fcntl
import hashlib
import json
import os
import re
import stat

import sialib
import siaqueue
import siavector


MAX_REQUEST_BYTES = sialib.MAX_STATE_JSON_BYTES
REQUEST_SCHEMA = "sia-cognitive-command-request-v1"
RECEIPT_SCHEMA = "sia-cognitive-command-observation-v1"
REQUEST_SCHEMA_V2 = "sia-cognitive-command-request-v2"
RECEIPT_SCHEMA_V2 = "sia-cognitive-command-observation-v2"
REFUSAL_SCHEMA = "sia-cognitive-baseline-refusal-v1"
NON_CLAIMS = (
    "The request SHA-256 binds caller-supplied bytes, not their authorship or the truth of supplied history.",
    "The private command does not consult resident memory readiness, corpus, index, or an ambient model.",
    "Baseline and upstream nonclaims remain controlling; this receipt adds no metric, significance, or cognitive-win authority.",
    "Lifecycle locking and descriptor checks do not establish protection against a hostile same-user process.",
)
_DIGEST = re.compile(r"[0-9a-f]{64}")
_KWARGS = frozenset({
    "capture", "expected_capture_sha256", "selection_policy", "expected_policy_sha256",
    "selection", "expected_selection_sha256", "split", "preparer", "adapter", "embedding",
    "model_expectations", "shared_runtime", "code_expectations", "limit", "timeout",
    "scratch_parent", "parameter_freeze", "expected_parameter_freeze_sha256",
})
_KWARGS_V2 = _KWARGS | {"embedding_input_policy", "expected_embedding_input_policy_sha256"}
_RESULT_KEYS = frozenset({
    "schema", "status", "lane", "split", "capture_sha256", "policy_sha256", "selection_sha256",
    "pages_sha256", "query_roster_sha256", "baseline_contract_sha256", "parameter_freeze_sha256",
    "parameter_freeze", "contract", "queries", "pages", "answer_key", "preparation", "observation",
    "retrieval_rows", "archive", "source_non_claims", "non_claims", "artifact_sha256",
})
_RESULT_KEYS_V2 = _RESULT_KEYS | {"embedding_input_policy", "embedding_input_policy_sha256"}
_STAT_FIELDS = (
    "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size",
    "st_mtime_ns", "st_ctime_ns",
)


class CommandRefusal(RuntimeError):
    """Canonical public refusal; no raw private exception text is exposed."""


def _refusal_text(reason, **retained):
    return json.dumps({"schema": REFUSAL_SCHEMA, "status": "refused", "reason": reason,
                       "consequence_ceiling": "informational", "non_claims": list(NON_CLAIMS),
                       **retained}, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


_PINNED_REQUEST_REQUIRED_JSON = _refusal_text("pinned-request-required")


def _fail(reason, **retained):
    raise CommandRefusal(_refusal_text(reason, **retained))


def _digest(value):
    return type(value) is str and len(value) == 64 and _DIGEST.fullmatch(value) is not None


def _path(value):
    return type(value) is str and 0 < len(value) <= sialib.MAX_CONFIG_BYTES \
        and os.path.isabs(value) and value != "/" and os.path.normpath(value) == value \
        and "\x00" not in value and ".gbrain" not in value.split("/")


def _generation(info):
    return tuple(getattr(info, field) for field in _STAT_FIELDS)


def _private(info):
    return stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() \
        and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600 \
        and 0 < info.st_size <= MAX_REQUEST_BYTES


class _RequestPin:
    """Keep a private sealed request and its original nofollow generation."""

    def __init__(self, path, expected_sha256):
        self.path = path
        self.source_fd = self.sealed_fd = None
        try:
            self.source_fd = sialib._open_source_nofollow(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
            info = os.fstat(self.source_fd)
            if not _private(info):
                _fail("request-file-not-admitted")
            self.generation = _generation(info)
            self.size = info.st_size
            self.sealed_fd = os.memfd_create("sia-cognitive-command", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            digest, consumed = hashlib.sha256(), 0
            while True:
                block = os.read(self.source_fd, min(sialib.MAX_CONFIG_BYTES, MAX_REQUEST_BYTES + 1 - consumed))
                if not block:
                    break
                consumed += len(block)
                if consumed > MAX_REQUEST_BYTES:
                    _fail("request-file-not-admitted")
                digest.update(block)
                siavector._write_all(self.sealed_fd, block)
            if consumed != self.size or digest.hexdigest() != expected_sha256:
                _fail("request-file-not-admitted")
            os.fchmod(self.sealed_fd, 0o400)
            siavector._seal(self.sealed_fd)
            self.current()
        except BaseException:
            self.close()
            raise

    def current(self):
        rebound = None
        try:
            info = os.fstat(self.source_fd)
            if not _private(info) or _generation(info) != self.generation:
                _fail("request-generation-changed")
            rebound = sialib._open_source_nofollow(self.path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
            named = os.fstat(rebound)
            if not _private(named) or _generation(named) != self.generation:
                _fail("request-generation-changed")
            if fcntl.fcntl(self.sealed_fd, fcntl.F_GET_SEALS) & siavector._SEALS != siavector._SEALS:
                _fail("request-generation-changed")
        except (OSError, ValueError, TypeError):
            _fail("request-generation-changed")
        finally:
            if rebound is not None:
                os.close(rebound)

    def read(self):
        raw = os.pread(self.sealed_fd, self.size + 1, 0)
        if len(raw) != self.size:
            _fail("request-generation-changed")
        return raw

    def close(self):
        for name in ("sealed_fd", "source_fd"):
            descriptor = getattr(self, name, None)
            if descriptor is not None:
                setattr(self, name, None)
                os.close(descriptor)


def _request(raw):
    import siacognitivebaseline as baseline
    try:
        document = siaqueue.strict_json_loads(raw)
        # Bound the whole decoded shape before copying anything or handing
        # caller values to the baseline. Its deeper semantic checks remain
        # solely the committed baseline's responsibility.
        baseline._bounded(document, MAX_REQUEST_BYTES)
        if type(document) is not dict or set(document) != {"schema", "baseline"} \
                or type(document["schema"]) is not str \
                or document["schema"] not in (REQUEST_SCHEMA, REQUEST_SCHEMA_V2) \
                or type(document["baseline"]) is not dict:
            _fail("request-schema-not-admitted")
        expected = _KWARGS if document["schema"] == REQUEST_SCHEMA else _KWARGS_V2
        if set(document["baseline"]) != expected:
            _fail("request-schema-not-admitted")
        return copy.deepcopy(document["baseline"])
    except CommandRefusal:
        raise
    except (baseline.BaselineRefusal, ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        _fail("request-json-not-admitted")


def _admit_result(result, inputs):
    import siacognitivebaseline as baseline
    try:
        baseline._bounded(result)
        v2 = "embedding_input_policy" in inputs
        result_keys = _RESULT_KEYS_V2 if v2 else _RESULT_KEYS
        result_schema = "sia-cognitive-baseline-v2" if v2 else "sia-cognitive-baseline-v1"
        nonclaims = baseline.NON_CLAIMS_V2 if v2 else baseline.NON_CLAIMS
        if type(result) is not dict or set(result) != result_keys \
                or result["schema"] != result_schema \
                or result["status"] != "observed" or result["lane"] != "raw_vector" \
                or result["split"] != inputs["split"]:
            _fail("baseline-result-not-admitted")
        for result_key, input_key in (("capture_sha256", "expected_capture_sha256"),
                                      ("policy_sha256", "expected_policy_sha256"),
                                      ("selection_sha256", "expected_selection_sha256")):
            if not _digest(result[result_key]) or result[result_key] != inputs[input_key]:
                _fail("baseline-result-not-admitted")
        for key in ("artifact_sha256", "pages_sha256", "query_roster_sha256", "baseline_contract_sha256"):
            if not _digest(result[key]):
                _fail("baseline-result-not-admitted")
        if result["pages_sha256"] != inputs["selection"]["pages_sha256"] \
                or result["parameter_freeze_sha256"] != inputs["expected_parameter_freeze_sha256"] \
                or not baseline._same(result["parameter_freeze"], inputs["parameter_freeze"]):
            _fail("baseline-result-not-admitted")
        for key in ("contract", "preparation", "observation", "archive", "source_non_claims"):
            if type(result[key]) is not dict:
                _fail("baseline-result-not-admitted")
        for key in ("queries", "pages", "answer_key", "retrieval_rows", "non_claims"):
            if type(result[key]) is not list:
                _fail("baseline-result-not-admitted")
        if v2:
            policy_sha = inputs["expected_embedding_input_policy_sha256"]
            if not _digest(policy_sha) or result["embedding_input_policy_sha256"] != policy_sha \
                    or not baseline._same(result["embedding_input_policy"], inputs["embedding_input_policy"]) \
                    or hashlib.sha256(baseline._canonical(result["embedding_input_policy"])).hexdigest() != policy_sha \
                    or result["contract"].get("schema") != "sia-cognitive-baseline-contract-v2" \
                    or result["contract"].get("embedding_input_policy_sha256") != policy_sha \
                    or not baseline._same(result["contract"].get("embedding_input_policy"), inputs["embedding_input_policy"]):
                _fail("baseline-result-not-admitted")
        if result["non_claims"] != nonclaims \
                or result["query_roster_sha256"] != hashlib.sha256(baseline._canonical(result["queries"])).hexdigest() \
                or result["baseline_contract_sha256"] != hashlib.sha256(baseline._canonical(result["contract"])).hexdigest():
            _fail("baseline-result-not-admitted")
        body = {key: value for key, value in result.items() if key != "artifact_sha256"}
        if hashlib.sha256(baseline._canonical(body)).hexdigest() != result["artifact_sha256"]:
            _fail("baseline-result-not-admitted")
        return result["artifact_sha256"], list(result["non_claims"])
    except CommandRefusal:
        raise
    except (baseline.BaselineRefusal, ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        _fail("baseline-result-not-admitted")


def _baseline_refusal(error, *, v2=False):
    import siacognitivebaseline as baseline
    # Error text may contain source paths or private data. Retain only the
    # explicitly reportable nonclaim fields, after bounding their structure.
    nonclaims = baseline.NON_CLAIMS_V2 if v2 else baseline.NON_CLAIMS
    retained = {"baseline_non_claims": list(nonclaims),
                "upstream_non_claims": getattr(error, "upstream_non_claims", [])}
    declared = getattr(error, "non_claims", [])
    if declared and declared != nonclaims:
        retained["exception_non_claims"] = declared
    try:
        baseline._bounded(retained)
        retained = copy.deepcopy(retained)
    except (baseline.BaselineRefusal, ValueError, TypeError, RecursionError, UnicodeError, OverflowError):
        _fail("baseline-refusal-not-admitted")
    _fail("baseline-refused", **retained)


def run_command(out_dir, *, repo=None, request_file=None, request_sha256=None):
    """Invoke only the committed private baseline and return its hash receipt.

    A request generation changing during execution withdraws command success,
    not any independently published baseline file. This transport neither
    publishes a second success file nor deletes baseline-owned artifacts.
    """
    if repo is not None:
        _fail("unsupported-alternate-source-root")
    if request_file is None or request_sha256 is None:
        raise CommandRefusal(_PINNED_REQUEST_REQUIRED_JSON)
    if out_dir is None:
        _fail("output-directory-required")
    if not _path(out_dir):
        _fail("output-directory-not-admitted")
    if not _path(request_file) or not _digest(request_sha256):
        _fail("request-file-not-admitted")
    # Selection imports siabench for its signed-ledger contract. Import the
    # baseline only after module initialization and early transport refusal,
    # so exposing the immutable no-request envelope cannot create a cycle.
    import siacognitivebaseline as baseline
    pin = None
    try:
        pin = _RequestPin(request_file, request_sha256)
        inputs = _request(pin.read())
        pin.current()
        # The closed decoded roster follows an explicit wire schema. Missing
        # v2 policy fields never fall back to the v1 execution capability.
        v2 = "embedding_input_policy" in inputs
        execute = baseline.run_baseline_v2 if v2 else baseline.run_baseline
        try:
            result = execute(**inputs, output_directory=out_dir)
        except baseline.BaselineRefusal as error:
            pin.current()
            _baseline_refusal(error, v2=v2)
        pin.current()
        artifact_sha256, retained = _admit_result(result, inputs)
        receipt = {"schema": RECEIPT_SCHEMA_V2 if v2 else RECEIPT_SCHEMA,
                   "status": "observed", "request_sha256": request_sha256,
                   "baseline_artifact_sha256": artifact_sha256, "output_directory": out_dir,
                   "artifact": "baseline.json", "baseline_non_claims": retained, "non_claims": list(NON_CLAIMS)}
        if v2:
            receipt["embedding_input_policy_sha256"] = inputs["expected_embedding_input_policy_sha256"]
        pin.current()
        return receipt
    except CommandRefusal:
        raise
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError, siavector.VectorRefusal):
        _fail("request-file-not-admitted")
    finally:
        if pin is not None:
            pin.close()

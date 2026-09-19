"""Pure represented GET projection admission, synthetic premises only.

Every projection receipt in this module is authored test input. No receipt
was emitted by an engine, no source/current-page authority is acquired, and
no output or acknowledgment is observed. Separate held-source and installed
transport tests own those joins. Root alone may execute this private draft.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import contextlib
import copy
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))


PARAMETERS = (
    "owner", "source_version", "expected_source_version_native_sha256",
    "get_stdout", "expected_get_stdout_sha256", "projection_stdout",
    "expected_projection_stdout_sha256", "input_current",
)
PROJECTION_SCHEMA = "sia-gbrain-get-render-projection-v1"
PROJECTION_NON_CLAIMS = [
    "This receipt compares supplied retained-source bytes and supplied GET stdout with one current local engine page projection; supplied source/version pins and origin are not independently authenticated here.",
    "The logical contentHash comparison keeps gbrain's existing exclusions; the separate complete-display comparison does not discard timestamp or gate-derived frontmatter.",
    "Serialized GET Markdown is a canonical rendering, not the original source-file byte representation; the original content, source, version and origin bindings remain unchanged.",
    "The no-write flags describe this probe operation, not request scratch, the preceding ordinary GET, database connection bookkeeping, or every process and storage-layer effect.",
    "A matching projection is not output delivery, human reading, successful use, controller readiness, acknowledgment, historical completeness, or a new observation clock.",
    "This receipt grants no JACKAL status, biological cognition claim, cognitive-mechanism warrant, or held-out retrieval win.",
]
SUBJECT = "notes/pure-projection-premise"
RAW = ("---\n# unchanged source comment\ntype: note\norigin: model\n"
       "title: 'Pure premise'\n---\n\r\nFixture café and cafe\u0301.\r\n").encode("utf-8")
GET_STDOUT = ("---\ntype: note\ntitle: Pure premise\norigin: model\n---\n\n"
              "Fixture café and cafe\u0301.\n")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def native(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def component(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def source_version(*, raw=RAW, origin="model", subject=SUBJECT):
    page = {"subject": subject, "content": raw.decode("utf-8", "strict"),
            "origin": origin, "source_sha256": sha(raw), "content_sha256": sha(raw)}
    page["version_sha256"] = sha(component({
        key: page[key] for key in ("content_sha256", "origin", "source_sha256", "subject")
    }))
    return page


def projection_premise(page, *, get_stdout=GET_STDOUT, type_basis="source-explicit"):
    # This digest is deliberately a declared synthetic projection premise.
    # It is not obtained from a Python imitation of gbrain's parser/hash.
    logical = sha(b"synthetic logical projection equality premise")
    return {
        "schema": PROJECTION_SCHEMA, "status": "matched", "source_id": "sia",
        "source_reference": {key: value for key, value in page.items() if key != "content"},
        "get_stdout_sha256": sha(get_stdout.encode("utf-8")),
        "page_state": "live", "parse_error_codes": [], "type_basis": type_basis,
        "expected_projection_sha256": logical, "current_projection_sha256": logical,
        "current_content_hash": logical, "current_content_hash_match": True,
        "projection_match": True, "display_fields_match": True,
        "current_get_stdout_sha256": sha(get_stdout.encode("utf-8")),
        "get_stdout_match": True, "mismatch_reasons": [],
        "retrieval_bookkeeping_updated": False, "operation_writes_performed": False,
        "non_claims": list(PROJECTION_NON_CLAIMS),
    }


def projection_text(value):
    # Exact supplied stdout bytes, not a requirement that TS uses this spacing.
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"


class InputStop(BaseException):
    pass


class StringSubclass(str):
    pass


class _NoAmbient:
    def __getattr__(self, name):
        raise AssertionError("pure admission accessed ambient provider: " + name)


class _ModuleShim:
    def __init__(self, module, **overrides):
        self.module, self.overrides = module, overrides

    def __getattr__(self, name):
        return self.overrides[name] if name in self.overrides else getattr(self.module, name)


class DictSubclass(dict):
    pass


RESULT_KEYS = {
    "schema", "status", "source_id", "source_version",
    "source_version_native_sha256", "get_stdout", "get_stdout_sha256",
    "projection_stdout", "projection_stdout_sha256", "projection_receipt",
    "projection_receipt_native_sha256", "non_claims", "consistency_sha256",
}
CAPACITIES = {
    # Observed existing SIA owner ceilings, not measured runtime headroom.
    "MAX_STATE_JSON_BYTES": 16777216,
    "MAX_CONFIG_BYTES": 65536,
    "MAX_EXTERNAL_OUTPUT_BYTES": 16777216,
}


class GetRenderAdmission(unittest.TestCase):
    def setUp(self):
        try:
            self.admission = importlib.import_module("siagetrenderadmit")
        except ModuleNotFoundError as error:
            if error.name != "siagetrenderadmit":
                raise
            self.fail("missing pure siagetrenderadmit component")
        self.assertTrue(callable(getattr(self.admission, "admit", None)),
                        "missing pure siagetrenderadmit.admit API")
        self.owner = dict(CAPACITIES)

    def request(self, *, page=None, receipt=None, get_stdout=GET_STDOUT):
        page = source_version() if page is None else page
        receipt = projection_premise(page, get_stdout=get_stdout) if receipt is None else receipt
        stdout = projection_text(receipt)
        return {
            "source_version": page,
            "expected_source_version_native_sha256": sha(native(page)),
            "get_stdout": get_stdout,
            "expected_get_stdout_sha256": sha(get_stdout.encode("utf-8")),
            "projection_stdout": stdout,
            "expected_projection_stdout_sha256": sha(stdout.encode("utf-8")),
            "input_current": lambda: None,
        }

    def call(self, request=None, *, owner=None):
        return self.admission.admit(
            self.owner if owner is None else owner,
            **(self.request() if request is None else request))

    def refuse(self, request=None, *, owner=None):
        with self.assertRaises(self.admission.GetRenderAdmissionRefusal) as caught:
            self.call(request, owner=owner)
        error = caught.exception
        self.assertIs(type(error.reason), str)
        self.assertTrue(error.reason, "refusal needs a named reason")
        self.assertEqual(error.non_claims, list(self.admission.NON_CLAIMS))
        self.assertEqual(error.upstream_non_claims, PROJECTION_NON_CLAIMS)
        self.assertIn(error.upstream_status, (None, "mismatch"))
        self.assertIs(type(error.upstream_mismatch_reasons), list)
        return error

    @contextlib.contextmanager
    def no_ambient(self):
        # Module-local names only: no process-wide os attribute patches.
        # This positive owner contains only capacities, no storage/provider
        # callable or authority helper from which an observation can be made.
        with contextlib.ExitStack() as stack:
            for name in ("os", "pathlib", "subprocess", "time", "datetime"):
                stack.enter_context(mock.patch.object(
                    self.admission, name, _NoAmbient(), create=True))
            for name in ("open", "gbrain", "utcnow", "read_completed",
                         "capture_native_history", "_capture_corpus_page_version"):
                stack.enter_context(mock.patch.object(
                    self.admission, name,
                    mock.Mock(side_effect=AssertionError("pure admission called " + name)),
                    create=True))
            yield

    def assert_result(self, result, request, receipt):
        self.assertIs(type(result), dict)
        self.assertEqual(set(result), RESULT_KEYS)
        self.assertEqual(result["schema"], "sia-get-render-consistency-v1")
        self.assertEqual(result["status"], "supplied-match-consistent-not-observed")
        self.assertEqual(result["source_id"], "sia")
        self.assertEqual(result["source_version"], request["source_version"])
        self.assertIsNot(result["source_version"], request["source_version"])
        self.assertEqual(result["source_version_native_sha256"],
                         request["expected_source_version_native_sha256"])
        self.assertEqual(result["get_stdout"], request["get_stdout"])
        self.assertEqual(result["get_stdout_sha256"], request["expected_get_stdout_sha256"])
        self.assertEqual(result["projection_stdout"], request["projection_stdout"])
        self.assertEqual(result["projection_stdout_sha256"],
                         request["expected_projection_stdout_sha256"])
        self.assertEqual(result["projection_receipt"], receipt)
        self.assertEqual(result["projection_receipt"]["non_claims"], PROJECTION_NON_CLAIMS)
        self.assertEqual(result["projection_receipt_native_sha256"], sha(native(receipt)))
        self.assertEqual(result["non_claims"], list(self.admission.NON_CLAIMS))
        without_pin = {key: value for key, value in result.items() if key != "consistency_sha256"}
        self.assertEqual(result["consistency_sha256"], sha(native(without_pin)))

    def test_explicit_signature_and_complete_detached_synthetic_match_without_io(self):
        signature = inspect.signature(self.admission.admit)
        self.assertEqual(tuple(signature.parameters), PARAMETERS)
        self.assertEqual(signature.parameters["owner"].kind,
                         inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for name in PARAMETERS:
            parameter = signature.parameters[name]
            self.assertIs(parameter.default, inspect.Parameter.empty)
            if name != "owner":
                self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
        request = self.request()
        receipt = json.loads(request["projection_stdout"])
        calls = []
        request["input_current"] = lambda: calls.append("caller-premise-current")
        with self.no_ambient():
            result = self.call(request)
            again = self.admission.admit(owner=self.owner, **request)
        self.assertTrue(calls, "caller-supplied currentness premise was not consulted")
        self.assert_result(result, request, receipt)
        self.assertEqual(again, result)
        self.assertIsNot(again, result)
        self.assertNotEqual(request["source_version"]["content"], request["get_stdout"])
        self.assertNotEqual(sha(native(request["source_version"])),
                            sha(component(request["source_version"])))
        self.assertNotEqual(request["source_version"]["version_sha256"],
                            request["expected_source_version_native_sha256"])
        result["source_version"]["content"] = "caller changed returned data"
        result["projection_receipt"]["non_claims"].clear()
        result["non_claims"].clear()
        self.assertEqual(again["source_version"], source_version())
        self.assertEqual(again["projection_receipt"]["non_claims"], PROJECTION_NON_CLAIMS)
        self.assert_result(self.call(request), request, receipt)

    def test_nonclaims_deny_authority_and_biological_or_benchmark_promotion(self):
        claims = self.call()["non_claims"]
        self.assertIs(type(claims), list)
        self.assertTrue(all(type(item) is str and item for item in claims))
        prose = " ".join(claims).lower()
        for concepts in (
            ("supplied", "premise"), ("process", "engine"),
            ("callback", "input_current"), ("raw", "original"),
            ("logical", "contenthash"), ("type",),
            ("probe",), ("write", "bookkeeping"),
            ("output", "delivery"), ("read", "use"),
            ("ack", "readiness"), ("clock",),
            ("jackal",), ("biological", "cognition"), ("held-out",),
        ):
            self.assertTrue(any(word in prose for word in concepts), concepts)
        self.assertIn("not-observed", self.call()["status"])

    def test_type_basis_is_explicit_premise_not_python_yaml_or_origin_authentication(self):
        # The actual TS parser owns this classification. This pure component
        # checks the allowed classification, but must not invent a parser.
        raw = RAW.replace(b"type: note\n", b"")
        page = source_version(raw=raw)
        receipt = projection_premise(page, type_basis="current-index-preserved")
        request = self.request(page=page, receipt=receipt)
        self.assert_result(self.call(request), request, receipt)
        for basis in (None, False, "parse-refused", "source-inferred-without-current-page",
                      "inferred", "source-explicit "):
            with self.subTest(basis=basis):
                changed = copy.deepcopy(receipt)
                changed["type_basis"] = basis
                self.refuse(self.request(page=page, receipt=changed))
        for origin in ("evidence", "derived", "model", "legacy-unlabeled"):
            # RAW's frontmatter still says model. This deliberately proves
            # only the explicit origin/ref join; it does not grant a label.
            with self.subTest(explicit_origin_premise=origin):
                declared = source_version(origin=origin)
                declared_receipt = projection_premise(declared)
                declared_request = self.request(page=declared, receipt=declared_receipt)
                self.assert_result(self.call(declared_request), declared_request, declared_receipt)

    def test_closed_receipt_reference_source_and_nonclaim_rosters(self):
        page = source_version()
        receipt = projection_premise(page)
        for key in receipt:
            with self.subTest(missing_receipt_key=key):
                changed = copy.deepcopy(receipt)
                del changed[key]
                self.refuse(self.request(page=page, receipt=changed))
        changed = copy.deepcopy(receipt)
        changed["unexpected"] = None
        self.refuse(self.request(page=page, receipt=changed))
        for container in ("source_reference", "source_version"):
            original = receipt["source_reference"] if container == "source_reference" else page
            for key in (*original, "unexpected"):
                with self.subTest(container=container, key=key):
                    altered = copy.deepcopy(original)
                    if key == "unexpected":
                        altered[key] = None
                    else:
                        del altered[key]
                    changed = copy.deepcopy(receipt)
                    if container == "source_reference":
                        changed[container] = altered
                        request = self.request(page=page, receipt=changed)
                    else:
                        request = self.request(page=altered, receipt=changed)
                    self.refuse(request)
        for nonclaims in ([], PROJECTION_NON_CLAIMS[:-1],
                          list(reversed(PROJECTION_NON_CLAIMS)),
                          PROJECTION_NON_CLAIMS + ["new authority claim"], None):
            with self.subTest(nonclaims=nonclaims):
                changed = copy.deepcopy(receipt)
                changed["non_claims"] = nonclaims
                self.refuse(self.request(page=page, receipt=changed))

    def test_foreign_source_origin_subject_and_reference_pins_refuse(self):
        page = source_version()
        receipt = projection_premise(page)
        for field, values in {
            "schema": ["sia-gbrain-page-projection-v1", ""],
            "source_id": ["other", "SIA", ""],
            "page_state": ["missing_or_deleted", "live "],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    changed = copy.deepcopy(receipt)
                    changed[field] = value
                    self.refuse(self.request(page=page, receipt=changed))
        for field in receipt["source_reference"]:
            with self.subTest(reference_field=field):
                changed = copy.deepcopy(receipt)
                changed["source_reference"][field] = (
                    "evidence" if field == "origin" else
                    "notes/foreign-page" if field == "subject" else sha(b"foreign reference"))
                self.refuse(self.request(page=page, receipt=changed))
        for subject in ("../escape", "/absolute", "--source", "Notes/upper", "notes//empty", "notes/x\n"):
            with self.subTest(subject=subject):
                self.refuse(self.request(page=source_version(subject=subject)))
        for origin in ("human", "verified", "MODEL", None, True):
            with self.subTest(origin=origin):
                self.refuse(self.request(page=source_version(origin=origin)))

    def test_external_pins_are_mandatory_exact_and_hash_families_not_interchangeable(self):
        request = self.request()
        for field in ("expected_source_version_native_sha256", "expected_get_stdout_sha256",
                      "expected_projection_stdout_sha256"):
            missing = dict(request)
            del missing[field]
            with self.subTest(missing_pin=field), self.assertRaises(TypeError):
                self.call(missing)
            for pin in (None, True, "", sha(b"foreign"), request[field].upper(),
                        StringSubclass(request[field])):
                with self.subTest(pin_field=field, pin=pin):
                    changed = dict(request)
                    changed[field] = pin
                    self.refuse(changed)
        for wrong in (request["source_version"]["version_sha256"],
                      request["source_version"]["source_sha256"],
                      sha(component(request["source_version"]))):
            changed = dict(request)
            changed["expected_source_version_native_sha256"] = wrong
            self.refuse(changed)
        # Projection wire bytes, not the parsed object, are externally pinned.
        changed = dict(request)
        receipt = json.loads(request["projection_stdout"])
        changed["expected_projection_stdout_sha256"] = sha(native(receipt))
        self.refuse(changed)
        changed = dict(request)
        changed["projection_stdout"] = json.dumps(receipt, ensure_ascii=False)
        self.refuse(changed)
        changed["expected_projection_stdout_sha256"] = sha(changed["projection_stdout"].encode("utf-8"))
        self.assert_result(self.call(changed), changed, receipt)

    def test_original_bytes_never_replaced_by_normalized_source_or_raw_as_get(self):
        request = self.request()
        for raw in (RAW.replace(b"\r\n", b"\n"),
                    RAW.replace("cafe\u0301".encode("utf-8"), "café".encode("utf-8"))):
            with self.subTest(normalized_raw=raw):
                altered = dict(request)
                altered["source_version"] = source_version(raw=raw)
                altered["expected_source_version_native_sha256"] = sha(native(altered["source_version"]))
                # Receipt still names the original retained byte/version pins.
                self.refuse(altered)
        for field in ("source_sha256", "content_sha256", "version_sha256"):
            altered = copy.deepcopy(request)
            altered["source_version"][field] = sha(b"synthetic logical projection equality premise")
            altered["expected_source_version_native_sha256"] = sha(native(altered["source_version"]))
            receipt = projection_premise(altered["source_version"])
            altered["projection_stdout"] = projection_text(receipt)
            altered["expected_projection_stdout_sha256"] = sha(altered["projection_stdout"].encode("utf-8"))
            with self.subTest(source_hash_field=field):
                self.refuse(altered)
        altered = dict(request)
        altered["get_stdout"] = RAW.decode("utf-8")
        altered["expected_get_stdout_sha256"] = sha(RAW)
        self.refuse(altered)
        # A valid live version digest alone is insufficient for this more
        # specific full-file GET contract: source_sha must pin these raw bytes.
        page = source_version()
        page["source_sha256"] = sha(b"different raw source")
        page["version_sha256"] = sha(component({
            key: page[key] for key in ("content_sha256", "origin", "source_sha256", "subject")
        }))
        self.refuse(self.request(page=page))

    def test_native_boolean_match_flags_no_write_flags_and_logical_joins(self):
        page = source_version()
        receipt = projection_premise(page)
        for field in ("current_content_hash_match", "projection_match", "display_fields_match", "get_stdout_match"):
            for value in (False, 1, 1.0, "true", None):
                with self.subTest(field=field, value=value, kind=type(value).__name__):
                    changed = copy.deepcopy(receipt)
                    changed[field] = value
                    self.refuse(self.request(page=page, receipt=changed))
        for field in ("retrieval_bookkeeping_updated", "operation_writes_performed"):
            for value in (True, 0, 0.0, "false", None):
                with self.subTest(field=field, value=value, kind=type(value).__name__):
                    changed = copy.deepcopy(receipt)
                    changed[field] = value
                    self.refuse(self.request(page=page, receipt=changed))
        for field in ("expected_projection_sha256", "current_projection_sha256", "current_content_hash",
                      "get_stdout_sha256", "current_get_stdout_sha256"):
            for value in (None, sha(b"different digest"), True):
                with self.subTest(field=field, value=value):
                    changed = copy.deepcopy(receipt)
                    changed[field] = value
                    self.refuse(self.request(page=page, receipt=changed))
        for field, value in (("parse_error_codes", ["YAML_PARSE"]),
                             ("mismatch_reasons", ["complete-display-fields-mismatch"]),
                             ("status", "computed-unverified")):
            changed = copy.deepcopy(receipt)
            changed[field] = value
            self.refuse(self.request(page=page, receipt=changed))

    def test_valid_upstream_mismatch_remains_a_named_refusal_with_reasons(self):
        page = source_version()
        receipt = projection_premise(page)
        receipt.update(status="mismatch", display_fields_match=False,
                       get_stdout_match=False,
                       current_get_stdout_sha256=sha(b"different actual display premise"),
                       mismatch_reasons=["complete-display-fields-mismatch", "get-stdout-mismatch"])
        error = self.refuse(self.request(page=page, receipt=receipt))
        self.assertEqual(error.reason, "upstream-non-match")
        self.assertEqual(error.upstream_status, "mismatch")
        self.assertEqual(error.upstream_mismatch_reasons, receipt["mismatch_reasons"])
        error.upstream_mismatch_reasons.clear()
        self.assertTrue(receipt["mismatch_reasons"])
        parsed_refusal = projection_premise(page)
        parsed_refusal.update(
            status="mismatch", parse_error_codes=["YAML_PARSE"], type_basis="parse-refused",
            expected_projection_sha256=None, current_projection_sha256=None,
            current_content_hash_match=False, projection_match=False, display_fields_match=False,
            mismatch_reasons=["source-parse-refused"])
        # No invented empty template or stored-hash mismatch is introduced.
        # A supplied parse refusal still cannot become an admitted match.
        parse_error = self.refuse(self.request(page=page, receipt=parsed_refusal))
        self.assertEqual(parse_error.reason, "upstream-non-match")
        self.assertEqual(parse_error.upstream_mismatch_reasons, ["source-parse-refused"])

    def test_strict_json_rejects_duplicate_ambiguous_nonfinite_or_nonobject_stdout(self):
        request = self.request()
        valid = request["projection_stdout"]
        duplicate_top = valid.replace('{\n', '{\n"status":"matched",\n', 1)
        duplicate_nested = valid.replace('"source_reference": {',
                                         '"source_reference": {"origin":"model",', 1)
        for stdout in ("", "{", "null", "[]", "true", "0", '"text"',
                       valid + "{}", duplicate_top, duplicate_nested,
                       '{"unrecognized":NaN}', '{"unrecognized":Infinity}',
                       '{"unrecognized":-Infinity}', '{"unrecognized":1e999}'):
            with self.subTest(stdout=stdout[:80]):
                changed = dict(request)
                changed["projection_stdout"] = stdout
                changed["expected_projection_stdout_sha256"] = sha(stdout.encode("utf-8"))
                self.refuse(changed)
        for field in ("get_stdout", "projection_stdout"):
            for value in (b"bytes are not decoded implicitly", StringSubclass(request[field]), "\ud800"):
                with self.subTest(field=field, value_kind=type(value).__name__):
                    changed = dict(request)
                    changed[field] = value
                    self.refuse(changed)
        changed = dict(request)
        changed["source_version"] = DictSubclass(request["source_version"])
        self.refuse(changed)

    def test_capacity_and_native_owner_gate_before_final_copy(self):
        def copy_forbidden(*args, **kwargs):
            raise AssertionError("capacity refusal reached allocating result deepcopy")

        # These probes narrow actual declared capacities, not test machine RSS.
        owners = []
        for key in CAPACITIES:
            for value in (True, False, 0, -1, 1.0, "65536", None):
                owner = dict(CAPACITIES)
                owner[key] = value
                owners.append(owner)
            absent = dict(CAPACITIES)
            del absent[key]
            owners.append(absent)
            tiny = dict(CAPACITIES)
            tiny[key] = len("{}")
            owners.append(tiny)
        owners.extend((DictSubclass(CAPACITIES), SimpleNamespace(**CAPACITIES)))
        with mock.patch.object(self.admission, "copy", _ModuleShim(copy, deepcopy=copy_forbidden)):
            for owner in owners:
                with self.subTest(owner_type=type(owner).__name__, owner=owner):
                    self.refuse(owner=owner)
            # Content ceiling observed in sialiveloop.MAX_CONTENT_BYTES.
            too_long = "x" * 1048576 + "x"
            for field in ("get_stdout", "source_content"):
                request = self.request()
                if field == "source_content":
                    request["source_version"] = dict(request["source_version"], content=too_long)
                else:
                    request[field] = too_long
                with self.subTest(field=field):
                    self.refuse(request)
            # Native character count fits the observed content ceiling;
            # exact UTF-8 byte count does not. All external pins are genuine
            # hashes of this authored premise, so a stale pin is no substitute
            # for the content-byte refusal before final copy.
            self.refuse(self.request(get_stdout="é" * 1048576))
            # The original complete request fits exactly; the final compound
            # request/receipt/result/copy reservation does not fit this limit.
            request = self.request()
            owner = dict(CAPACITIES)
            owner["MAX_STATE_JSON_BYTES"] = len(native({
                key: value for key, value in request.items() if key != "input_current"
            }))
            self.refuse(request, owner=owner)

    def test_callback_is_explicit_none_only_and_preserves_arbitrary_exception_identity(self):
        for callback in (None, False, "not callable"):
            request = self.request()
            request["input_current"] = callback
            self.refuse(request)
        for returned in (False, True, "current", {}, []):
            request = self.request()
            request["input_current"] = lambda value=returned: value
            with self.subTest(callback_return=returned):
                self.refuse(request)
        for stop in (InputStop("caller-scope-stop"), RuntimeError("caller-currentness-error")):
            request = self.request()
            def interrupt():
                raise stop
            request["input_current"] = interrupt
            with self.assertRaises(type(stop)) as caught:
                self.call(request)
            self.assertIs(caught.exception, stop)

    def test_callback_mutation_and_late_copy_mutation_cannot_restore_success(self):
        for target in ("source", "owner"):
            request = self.request()
            owner = dict(CAPACITIES)
            def change():
                if target == "source":
                    request["source_version"]["content"] = "changed during caller currentness"
                else:
                    owner["MAX_CONFIG_BYTES"] = len("{}")
            request["input_current"] = change
            with self.subTest(callback_mutates=target):
                self.refuse(request, owner=owner)
        original_copy = copy.deepcopy
        for target in ("returned", "input", "owner"):
            request = self.request()
            owner = dict(CAPACITIES)
            copied = []
            def changed_copy(value, *args, **kwargs):
                detached = original_copy(value, *args, **kwargs)
                if type(value) is dict and value.get("schema") == "sia-get-render-consistency-v1":
                    copied.append(value["schema"])
                    if target == "returned":
                        detached["projection_receipt"]["display_fields_match"] = False
                    elif target == "input":
                        request["source_version"]["origin"] = "evidence"
                    else:
                        owner["MAX_CONFIG_BYTES"] = len("{}")
                return detached
            with self.subTest(copy_mutates=target), mock.patch.object(
                    self.admission, "copy", _ModuleShim(copy, deepcopy=changed_copy)):
                self.refuse(request, owner=owner)
            self.assertTrue(copied, "mutation must reach actual final consistency-result copy")
        request = self.request()
        copied = []
        callbacks = []
        def mark_copy(value, *args, **kwargs):
            detached = original_copy(value, *args, **kwargs)
            if type(value) is dict and value.get("schema") == "sia-get-render-consistency-v1":
                copied.append("copied")
            return detached
        def late_change():
            callbacks.append(bool(copied))
            if copied:
                request["source_version"]["content"] = "changed after detached copy"
        request["input_current"] = late_change
        with mock.patch.object(self.admission, "copy", _ModuleShim(copy, deepcopy=mark_copy)):
            self.refuse(request)
        self.assertIn(False, callbacks, "real input_current must run before final copy")
        self.assertIn(True, callbacks, "real input_current must run after final copy")

    def test_final_copy_must_be_native_exact_and_fully_detached(self):
        original_copy = copy.deepcopy
        for replacement in ("none", "same-object", "shallow-alias", "numeric-bool-alias"):
            copied = []
            def replace_copy(value, *args, **kwargs):
                if type(value) is not dict or value.get("schema") != "sia-get-render-consistency-v1":
                    return original_copy(value, *args, **kwargs)
                copied.append(value["schema"])
                if replacement == "none":
                    return None
                if replacement == "same-object":
                    return value
                if replacement == "shallow-alias":
                    return dict(value)
                result = original_copy(value, *args, **kwargs)
                result["projection_receipt"]["projection_match"] = 1
                return result
            with self.subTest(replacement=replacement), mock.patch.object(
                    self.admission, "copy", _ModuleShim(copy, deepcopy=replace_copy)):
                self.refuse()
            self.assertTrue(copied, "replacement must reach actual final consistency-result copy")

"""Actual ranked-prefix rendering inside the source-authorized writer hold.

The acknowledged source, full generation, adoption, rank and journal completion
are real controlled-fixture operations. Caller rows come from retained current
versions; a same-origin pair with different RETAINED activation scores is
presented in reverse retained order. No setup rerank, trace rewrite, policy
change, mocked rank result or relabeled source is used to make ordering pass.

The renderer is explicit test code, not an engine/query adapter or evidence
that arbitrary rendering prose is faithful. Its returned bytes must be the
bytes actually flushed and recorded, with the exact displayed rank prefix.
These checks establish neither deployment, human receipt, biological cognition
nor held-out retrieval improvement. Root alone runs tests sequentially.
"""

import base64
import contextlib
import copy
import importlib
import inspect
import itertools
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import test_controller_delivery_writer as writer_tests
from tests import test_delivery_journal as journal_tests


PARAMETERS = (
    "owner", "memo", "admitted_status", "retained_batch", "committed",
    "journal_limits", "expected_journal_limits_sha256", "expected_adoption_sha256",
    "rows", "expected_rows_sha256", "observed_at", "render_config",
    "expected_render_config_sha256", "renderer", "request_id", "consumer",
    "binary_sink", "clock",
)
CONFIG_SCHEMA = "sia-controller-delivery-render-config-v1"


class ControllerDeliveryRenderWriter(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("siacontrollerdeliverywriter")
        self.assertTrue(callable(getattr(self.module, "render_and_deliver", None)),
                        "missing held rank-prefix render-and-deliver entry point")
        self.fixture = writer_tests.ControllerDeliveryWriter(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    def select_reversed_real_rows(self, f):
        state = f.generation["transition"]["state"]
        current = state["intake"]["current_versions"]
        pages = {page["subject"]: page for page in state["intake"]["pages"]
                 if page["version_sha256"] in current and page["content"]}
        scores = {entry["subject"]: entry["score"]
                  for entry in state["activation"]["activations"]}
        ordered = [pages[subject] for subject in state["activation"]["order"]
                   if subject in pages]
        pairs = [(high, low) for high, low in itertools.combinations(ordered, 2)
                 if high["origin"] == low["origin"]
                 and scores[high["subject"]] != scores[low["subject"]]]
        self.assertTrue(pairs,
            "actual ACKed fixture needs a genuine distinct-score same-origin pair; do not synthesize rank authority")
        high, low = pairs[0]
        rows = [{
            "row_ref": reference, "version_sha256": page["version_sha256"],
            "row": {"slug": page["subject"], "chunk_text": page["content"],
                    "origin": page["origin"], "fixture_backend": "caller-premise-not-engine-result"},
        } for reference, page in (("rank-later-input-first", low), ("rank-first-input-later", high))]
        f.rows = rows
        f.writer_request.update(rows=rows, expected_rows_sha256=self.fixture.live._sha(rows),
                                observed_at=state["observed_at"])
        f.expected_rank_order = ["rank-first-input-later", "rank-later-input-first"]
        f.render_config = {
            "schema": CONFIG_SCHEMA, "selection": "rank-prefix-v1",
            "display_limit": 1, "max_body_bytes": self.fixture.epoch.limits["max_body_bytes"],
        }

    @contextlib.contextmanager
    def completed(self):
        with self.fixture.completed() as f:
            self.select_reversed_real_rows(f)
            yield f

    def call(self, f, owner, *, renderer, sink, clock, **changes):
        arguments = {key: value for key, value in f.writer_request.items()
                     if key not in ("emitted_row_refs", "output_utf8")}
        arguments.update(render_config=f.render_config,
            expected_render_config_sha256=self.fixture.live._sha(f.render_config),
            renderer=renderer, binary_sink=sink, clock=clock)
        arguments.update(changes)
        return self.module.render_and_deliver(owner.__dict__, **arguments)

    @contextlib.contextmanager
    def one_actual_rank(self):
        original = self.fixture.live.rank_recall
        calls = []

        def rank(**kwargs):
            self.assertEqual(calls, [], "rendering reranked inside one writer operation")
            result = original(**kwargs)
            calls.append(result)
            return result

        with mock.patch.object(self.fixture.live, "rank_recall", side_effect=rank), \
                mock.patch.object(self.module, "deliver", side_effect=AssertionError(
                    "rendering released ownership and called premised-body deliver")):
            yield calls

    @staticmethod
    def rendered(ranked, config):
        refs = ranked["order"][:config["display_limit"]]
        by_ref = {entry["row_ref"]: entry["row"] for entry in ranked["rows"]}
        text = "".join(reference + "\n" + by_ref[reference]["slug"] + "\n"
                       + by_ref[reference]["chunk_text"] + "\n" for reference in refs)
        return {"emitted_row_refs": list(refs), "output_utf8": text.encode("utf-8")}

    def assert_renderer_inputs(self, f, owner, trace, ranks, *, ranked,
                               expected_ranked_sha256, config, expected_config_sha256):
        self.assertTrue(ranks, "renderer ran before the actual rank result")
        self.assertEqual(ranks, [ranks[0]])
        actual = ranks[0]
        self.assertIsNot(ranked, actual)
        self.assertIsNot(ranked["rows"], actual["rows"])
        self.assertIsNot(ranked["rows"][0]["row"], actual["rows"][0]["row"])
        self.assertEqual(ranked, actual)
        self.assertEqual(expected_ranked_sha256, actual["rank_sha256"])
        self.assertEqual(ranked["order"], f.expected_rank_order)
        self.assertNotEqual(ranked["order"], [row["row_ref"] for row in f.rows])
        self.assertEqual(ranked["rows"], f.rows)
        self.assertEqual(ranked["state_sha256"], f.generation["state_sha256"])
        self.assertIsNot(config, f.render_config)
        self.assertEqual(config, f.render_config)
        self.assertEqual(expected_config_sha256, self.fixture.live._sha(f.render_config))
        self.assertTrue(trace.epochs)
        self.assertTrue(trace.journals)
        self.assertEqual(trace.epochs, [trace.epochs[0]])
        self.assertEqual(trace.journals, [trace.journals[0]])
        for held in (*trace.epochs, *trace.journals):
            held.current()
        f.case.source.pages.assert_owned()
        self.assertIsNone(owner._BRAINSTEM_OWNER_FD.get())

    def assert_no_output(self, f, caught, sink, clock, records):
        self.assertEqual(caught.exception.output_state, "not-started")
        self.assertEqual(caught.exception.non_claims, list(self.module.NON_CLAIMS))
        sink.write.assert_not_called()
        sink.flush.assert_not_called()
        clock.assert_not_called()
        self.assertEqual(self.fixture.record_images(f), records)

    def test_exact_additive_render_contract_preserves_old_deliver_parameters(self):
        for operation, expected in ((self.module.render_and_deliver, PARAMETERS),
                                    (self.module.deliver, writer_tests.PARAMETERS)):
            parameters = inspect.signature(operation).parameters
            self.assertEqual(tuple(parameters), expected)
            for name, parameter in parameters.items():
                self.assertEqual(parameter.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD
                                 if name == "owner" else inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(parameter.default, inspect.Parameter.empty)

    def test_actual_changed_rank_order_is_rendered_once_and_recorded_under_same_holds(self):
        fixture = self.fixture
        with self.completed() as f:
            authority = f.case.images()
            rows = copy.deepcopy(f.rows)
            rendered = []
            sink = journal_tests.ByteSink()

            def clock():
                self.assertEqual(sink.events, ["write", "flush"])
                self.assertEqual(bytes(sink.body), rendered[0]["output_utf8"])
                return writer_tests.COMPLETED_AT

            with fixture.writer_owner(f) as owner, fixture.boundary(f, owner) as trace, \
                    self.one_actual_rank() as ranks:
                def renderer(*, ranked, expected_ranked_sha256, config, expected_config_sha256):
                    self.assert_renderer_inputs(f, owner, trace, ranks, ranked=ranked,
                        expected_ranked_sha256=expected_ranked_sha256, config=config,
                        expected_config_sha256=expected_config_sha256)
                    self.assertEqual(rendered, [])
                    result = self.rendered(ranked, config)
                    rendered.append(copy.deepcopy(result))
                    return result

                completed = self.call(f, owner, renderer=renderer, sink=sink, clock=clock)
            self.assertEqual(f.rows, rows)
            self.assertEqual(bytes(sink.body), rendered[0]["output_utf8"])
            record = completed["record"]
            self.assertEqual(record["emitted_row_refs"], rendered[0]["emitted_row_refs"])
            self.assertEqual(record["emitted_row_refs"], f.expected_rank_order[:f.render_config["display_limit"]])
            self.assertEqual(record["rows"], [rows[-1]])
            self.assertEqual(record["rows"][0]["row"]["origin"], rows[-1]["row"]["origin"])
            self.assertEqual(record["rank_sha256"], ranks[0]["rank_sha256"])
            self.assertEqual(base64.b64decode(record["output_utf8_base64"], validate=True), rendered[0]["output_utf8"])
            self.assertEqual(fixture.inspect(f)["records"], [record])
            self.assertEqual(f.case.images(), authority)

    def test_wrong_prefix_and_invalid_renderer_body_refuse_before_any_intent(self):
        fixture = self.fixture
        with self.completed() as f:
            for fault in ("input-order-prefix", "empty-prefix", "nonbytes-body",
                          "invalid-utf8", "body-capacity", "extra-result-key"):
                with self.subTest(renderer_fault=fault):
                    config = copy.deepcopy(f.render_config)
                    if fault == "body-capacity":
                        config["max_body_bytes"] = 1
                    sink = mock.Mock()
                    clock = fixture.forbidden("invalid rendering sampled output clock")
                    records, authority = fixture.record_images(f), f.case.images()
                    rendered = []
                    with mock.patch.object(f, "render_config", config), \
                            fixture.writer_owner(f) as owner, \
                            fixture.boundary(f, owner, forbid_records=True) as trace, \
                            self.one_actual_rank() as ranks, \
                            self.assertRaises(self.module.ControllerDeliveryWriterRefusal) as caught:
                        def renderer(*, ranked, expected_ranked_sha256, config, expected_config_sha256):
                            self.assert_renderer_inputs(f, owner, trace, ranks, ranked=ranked,
                                expected_ranked_sha256=expected_ranked_sha256, config=config,
                                expected_config_sha256=expected_config_sha256)
                            result = self.rendered(ranked, config)
                            if fault == "input-order-prefix":
                                result["emitted_row_refs"] = [ranked["rows"][0]["row_ref"]]
                            elif fault == "empty-prefix":
                                result["emitted_row_refs"] = []
                            elif fault == "nonbytes-body":
                                result["output_utf8"] = bytearray(result["output_utf8"])
                            elif fault == "invalid-utf8":
                                result["output_utf8"] = b"\xff"
                            elif fault == "body-capacity":
                                self.assertGreater(len(result["output_utf8"]), config["max_body_bytes"])
                            elif fault == "extra-result-key":
                                result["unadmitted"] = True
                            rendered.append(True)
                            return result

                        self.call(f, owner, renderer=renderer, sink=sink, clock=clock)
                    self.assertEqual(rendered, [True])
                    self.assert_no_output(f, caught, sink, clock, records)
                    self.assertEqual(f.case.images(), authority)

    def test_bad_render_configuration_or_pin_never_calls_renderer_or_publishes_intent(self):
        fixture = self.fixture
        with self.completed() as f:
            configs = [
                {**f.render_config, "schema": "unadmitted-render-config"},
                {**f.render_config, "selection": "input-prefix"},
                {**f.render_config, "display_limit": True},
                {**f.render_config, "display_limit": 0},
                {**f.render_config, "display_limit": fixture.live.MAX_INPUT_BYTES},
                {**f.render_config, "max_body_bytes": 0},
                {**f.render_config, "max_body_bytes": fixture.live.MAX_INPUT_BYTES},
                {**f.render_config, "unadmitted": True},
            ]
            requests = [{"render_config": config,
                         "expected_render_config_sha256": fixture.live._sha(config)}
                        for config in configs]
            self.assertNotEqual(fixture.live._sha(f.render_config), "0" * 64)
            requests.append({"expected_render_config_sha256": "0" * 64})
            for request in requests:
                with self.subTest(request=request):
                    records, authority = fixture.record_images(f), f.case.images()
                    renderer = fixture.forbidden("invalid render configuration reached renderer")
                    sink = mock.Mock()
                    clock = fixture.forbidden("invalid render configuration sampled clock")
                    with fixture.writer_owner(f) as owner, \
                            fixture.boundary(f, owner, forbid_records=True), \
                            self.assertRaises(self.module.ControllerDeliveryWriterRefusal) as caught:
                        self.call(f, owner, renderer=renderer, sink=sink, clock=clock, **request)
                    renderer.assert_not_called()
                    self.assert_no_output(f, caught, sink, clock, records)
                    self.assertEqual(f.case.images(), authority)

    def test_callback_copy_caller_and_owner_mutations_cannot_be_laundered_before_intent(self):
        fixture = self.fixture
        with self.completed() as f:
            for fault in ("ranked-copy", "config-copy", "caller-rows", "owner-operation"):
                with self.subTest(callback_fault=fault):
                    records, authority = fixture.record_images(f), f.case.images()
                    rows = copy.deepcopy(f.rows)
                    config_before = copy.deepcopy(f.render_config)
                    sink = mock.Mock()
                    clock = fixture.forbidden("mutated rendering sampled output clock")
                    rendered = []
                    replacement = fixture.forbidden("rendering called replaced owner operation")
                    with fixture.writer_owner(f) as owner:
                        original_operation = owner._canonical_utc_timestamp
                        try:
                            with fixture.boundary(f, owner, forbid_records=True) as trace, \
                                    self.one_actual_rank() as ranks, \
                                    self.assertRaises(self.module.ControllerDeliveryWriterRefusal) as caught:
                                def renderer(*, ranked, expected_ranked_sha256, config, expected_config_sha256):
                                    self.assert_renderer_inputs(f, owner, trace, ranks, ranked=ranked,
                                        expected_ranked_sha256=expected_ranked_sha256, config=config,
                                        expected_config_sha256=expected_config_sha256)
                                    result = self.rendered(ranked, config)
                                    if fault == "ranked-copy":
                                        ranked["rows"][0]["row"]["unadmitted_renderer_copy"] = True
                                        ranked["rank_sha256"] = fixture.live._own(ranked, "rank_sha256")
                                    elif fault == "config-copy":
                                        config["selection"] = "unadmitted-callback-selection"
                                    elif fault == "caller-rows":
                                        f.rows[0]["row"]["unadmitted_caller_drift"] = True
                                    elif fault == "owner-operation":
                                        owner._canonical_utc_timestamp = replacement
                                    rendered.append(True)
                                    return result

                                self.call(f, owner, renderer=renderer, sink=sink, clock=clock)
                        finally:
                            # Restore only explicitly changed in-memory
                            # caller premises/operation identity, no artifacts.
                            f.rows[:] = rows
                            owner._canonical_utc_timestamp = original_operation
                    self.assertEqual(rendered, [True])
                    self.assertEqual(f.render_config, config_before)
                    replacement.assert_not_called()
                    self.assert_no_output(f, caught, sink, clock, records)
                    self.assertEqual(f.case.images(), authority)

    def test_actual_source_memo_drift_during_renderer_refuses_before_intent(self):
        fixture = self.fixture
        with self.completed() as f:
            records, authority = fixture.record_images(f), f.case.images()
            sink = mock.Mock()
            clock = fixture.forbidden("changed source authority sampled output clock")
            rendered = []
            with fixture.writer_owner(f) as owner, \
                    fixture.boundary(f, owner, forbid_records=True) as trace, \
                    self.one_actual_rank() as ranks, \
                    self.assertRaises(self.module.ControllerDeliveryWriterRefusal) as caught:
                def renderer(*, ranked, expected_ranked_sha256, config, expected_config_sha256):
                    self.assert_renderer_inputs(f, owner, trace, ranks, ranked=ranked,
                        expected_ranked_sha256=expected_ranked_sha256, config=config,
                        expected_config_sha256=expected_config_sha256)
                    result = self.rendered(ranked, config)
                    changed = f.case.live._read("MEMO_PATH")
                    changed["render_fixture_source_drift"] = "after-actual-rank"
                    # Deliberate isolated fixture authority mutation, not a
                    # mocked current() refusal or an admitted writer action.
                    f.case.live._write(f.case.live.paths["MEMO_PATH"], changed)
                    rendered.append(True)
                    return result

                self.call(f, owner, renderer=renderer, sink=sink, clock=clock)
            self.assertEqual(rendered, [True])
            self.assert_no_output(f, caught, sink, clock, records)
            self.assertNotEqual(f.case.images(), authority)
            self.assertEqual(f.case.live._read("MEMO_PATH")["render_fixture_source_drift"],
                             "after-actual-rank")
            self.assertNotIn("render_fixture_source_drift", f.case.live.memo)
            self.assertEqual(fixture.inspect(f)["records"], [])

    def test_actual_source_drift_during_rank_copy_refuses_before_renderer_or_intent(self):
        fixture = self.fixture
        with self.completed() as f:
            records = fixture.record_images(f)
            sink = mock.Mock()
            clock = fixture.forbidden("rank-copy authority loss sampled output clock")
            renderer = fixture.forbidden("rank-copy authority loss reached renderer")
            copied = []
            actual_copy = self.module.copy.deepcopy
            with fixture.writer_owner(f) as owner, \
                    fixture.boundary(f, owner, forbid_records=True), \
                    self.one_actual_rank() as ranks:
                def copy_then_change_source(value, *args, **kwargs):
                    result = actual_copy(value, *args, **kwargs)
                    if ranks and value is ranks[0]:
                        self.assertEqual(copied, [])
                        self.assertIsNot(value, result)
                        self.assertEqual(result, ranks[0])
                        changed = f.case.live._read("MEMO_PATH")
                        changed["render_fixture_source_drift"] = "after-real-rank-copy"
                        f.case.live._write(f.case.live.paths["MEMO_PATH"], changed)
                        copied.append(True)
                    return result

                # Only this writer's copy reference changes. The actual
                # ranker, source readers and held writer remain untouched.
                isolated_copy = SimpleNamespace(deepcopy=copy_then_change_source)
                with mock.patch.object(self.module, "copy", isolated_copy), \
                        self.assertRaises(self.module.ControllerDeliveryWriterRefusal) as caught:
                    self.call(f, owner, renderer=renderer, sink=sink, clock=clock)
            self.assertEqual(copied, [True])
            renderer.assert_not_called()
            self.assert_no_output(f, caught, sink, clock, records)
            self.assertEqual(f.case.live._read("MEMO_PATH")["render_fixture_source_drift"],
                             "after-real-rank-copy")
            self.assertNotIn("render_fixture_source_drift", f.case.live.memo)
            self.assertEqual(fixture.inspect(f)["records"], [])


if __name__ == "__main__":
    unittest.main()

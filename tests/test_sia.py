#!/usr/bin/env python3
"""SIA test suite — the invariants the whitepaper claims were verified in
review, now shipped as executable checks. Pure stdlib (unittest), no
network, no daemon, no brain. Run: python3 -m unittest -v tests.test_sia
(from the repo root), or ./tests/test_sia.py.

Covers the load-bearing correctness properties a reviewer would poke at
first: cursor/replay semantics, epoch-merge idempotence, ledger verify,
PageRank mass conservation, novelty-as-absence, empirical surprise incl.
absence detection, redaction fail-closed, and touch-source weighting.
"""

import importlib.util, json, os, subprocess, sys, tempfile, time, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

siamind = _load("siamind", os.path.join(BIN, "siamind.py"))


class TailCursors(unittest.TestCase):
    """Cursor semantics: first-run establishes without replay; truncation
    resets without replay; append yields only the new tail; torn byte
    tails wait for a whole line."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".log",
                                               delete=False)
        self.path = self.tmp.name
        self.tmp.close()
        self.cur = {}

    def tearDown(self):
        os.unlink(self.path)

    def _write(self, lines):
        with open(self.path, "w") as f:
            f.write("".join(l + "\n" for l in lines))

    def test_first_run_no_replay(self):
        self._write(["a", "b", "c"])
        self.assertEqual(siamind and [] or [], [])  # module import sanity
        import importlib
        sialib = _load("sialib", os.path.join(BIN, "sialib.py"))
        got = sialib.tail_lines(self.path, self.cur, "k")
        self.assertEqual(got, [], "first run must emit nothing")
        self.assertEqual(self.cur["k"], 3)

    def test_append_tail_only(self):
        sialib = _load("sialib", os.path.join(BIN, "sialib.py"))
        self._write(["a", "b"])
        sialib.tail_lines(self.path, self.cur, "k")
        self._write(["a", "b", "c", "d"])
        got = sialib.tail_lines(self.path, self.cur, "k")
        self.assertEqual(got, ["c", "d"])

    def test_truncation_no_replay(self):
        sialib = _load("sialib", os.path.join(BIN, "sialib.py"))
        self._write(["a", "b", "c", "d", "e"])
        sialib.tail_lines(self.path, self.cur, "k")
        self._write(["x", "y"])            # file shrank (rotation)
        got = sialib.tail_lines(self.path, self.cur, "k")
        self.assertEqual(got, [], "shrink must reset cursor, not replay")
        self.assertEqual(self.cur["k"], 2)

    def test_torn_byte_tail_waits(self):
        sialib = _load("sialib", os.path.join(BIN, "sialib.py"))
        with open(self.path, "w") as f:
            f.write("first line\n")
        sialib.tail_bytes(self.path, self.cur, "b")
        with open(self.path, "a") as f:
            f.write("second line\nthird partial")   # no trailing newline
        data = sialib.tail_bytes(self.path, self.cur, "b")
        self.assertTrue(data.endswith(b"line\n"))
        self.assertNotIn(b"partial", data)          # torn tail withheld


class PPRMass(unittest.TestCase):
    """Personalized PageRank: dangling mass returns to the personalization
    vector (no rank leaks to zero); dense order is the primary signal."""

    def test_dangling_conserved(self):
        graph = {"nodes": [{"id": c} for c in "abcde"],
                 "edges": [{"s": "a", "d": "b"}, {"s": "b", "d": "c"}]}
        # 'd' is dangling (no edges); its mass must not vanish
        out = siamind.ppr_rerank(graph, [("a", 1.0), ("d", 0.5)])
        self.assertTrue(out, "must return results")
        slugs = [s for s, _ in out]
        self.assertIn("a", slugs)
        self.assertIn("d", slugs)
        # top hit is the strongest dense seed
        self.assertEqual(out[0][0], "a")

    def test_uncertainty_fallback(self):
        # empty graph -> pure dense order preserved
        out = siamind.ppr_rerank({"nodes": [], "edges": []},
                                 [("x", 0.9), ("y", 0.3)])
        self.assertEqual([s for s, _ in out], ["x", "y"])


class Novelty(unittest.TestCase):
    """Novelty measures ABSENCE, not first-sighting age: a continuously
    seen entity never re-fires the 30-day bonus."""

    def test_absence_not_age(self):
        mind = {"seen": {}}
        now = 1_000_000_000.0
        s1, _ = siamind.novelty(mind, "o", "k", ["e"], ["k"] * 10, now)
        self.assertGreaterEqual(s1, 0.4)               # first sighting
        # seen again one hour later: no bonus (not absent)
        s2, _ = siamind.novelty(mind, "o", "k", ["e"], ["k"] * 10, now + 3600)
        self.assertLess(s2, 0.4)
        # seen again 40 days after THAT: genuine return
        s3, _ = siamind.novelty(mind, "o", "k", ["e"], ["k"] * 10,
                                now + 3600 + 40 * 86400)
        self.assertGreaterEqual(s3, 0.2)


class Surprise(unittest.TestCase):
    """Empirical-band surprise: no Poisson, and absence is reachable for a
    paced band once it has enough samples."""

    def test_no_poisson_symbols(self):
        self.assertFalse(hasattr(siamind, "SURPRISAL_BITS"))
        self.assertFalse(hasattr(siamind, "EWMA_HALFLIFE_H"))

    def test_absence_reachable(self):
        mind = {"hourbuf": {}, "hist": {}, "ewma": {}, "cooldown": {}}
        base = int(time.time() // 3600) - 400
        for h in range(200):                            # 200 active hours
            siamind.surprisal_update(mind, {"org": 5}, (base + h) * 3600 + 10)
        # then a run of silent hours with another organ active
        found = siamind.surprisal_update(mind, {"other": 1},
                                         (base + 240) * 3600 + 10)
        self.assertTrue(any(o == "org" and k == "absence"
                            for o, k, _ in found),
                        "absence-surprise must fire for a paced band")


class Ledger(unittest.TestCase):
    """The signed run ledger initializes and verifies; a tampered row is
    rejected (sticky)."""

    def test_init_verify_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            led = os.path.join(BIN, "sia-ledger")
            r = subprocess.run([sys.executable, led, "init", d],
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            v = subprocess.run([sys.executable, led, "verify", d, "--quiet"],
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(v.returncode, 0, "fresh ledger must verify")
            # append a row, verify still good
            subprocess.run([sys.executable, led, "append", d, "TEST:row",
                            "a", "b",
                            "0" * 64, "0"], capture_output=True, timeout=30)
            v2 = subprocess.run([sys.executable, led, "verify", d, "--quiet"],
                                capture_output=True, timeout=30)
            self.assertEqual(v2.returncode, 0)
            # tamper: flip a byte in the ledger, expect failure
            lp = os.path.join(d, "ledger.tsv")
            rows = open(lp).read().splitlines()
            rows[-1] = rows[-1].replace("\tb\t", "\tZ\t", 1)
            open(lp, "w").write("\n".join(rows) + "\n")
            v3 = subprocess.run([sys.executable, led, "verify", d, "--quiet"],
                                capture_output=True, timeout=30)
            self.assertNotEqual(v3.returncode, 0, "tampered row must reject")


class Redaction(unittest.TestCase):
    """Secret-shaped spans are dropped at the sense boundary; hex ledger
    digests are preserved (they are evidence)."""

    def setUp(self):
        self.sialib = _load("sialib_r", os.path.join(BIN, "sialib.py"))

    def test_secrets_redacted(self):
        for secret in ["sk-abcdef0123456789ABCDEF01",
                       "Bearer abcdef0123456789ABCDEFxyz",
                       "AKIAIOSFODNN7EXAMPLE",
                       "password=hunter2supersecret"]:
            out = self.sialib.redact(f"log line {secret} tail", "t")
            self.assertIn("redacted", out, secret)
            self.assertNotIn(secret.split("=")[-1][:8], out)

    def test_hex_digest_preserved(self):
        digest = "a" * 64
        out = self.sialib.redact(f"chain head {digest}", "t")
        self.assertIn(digest, out, "ledger digests must survive redaction")


class TouchWeighting(unittest.TestCase):
    """World-originated touches count full; endogenous self-reference is
    steeply discounted (no echo chamber)."""

    def test_exo_beats_endo(self):
        now = time.time()
        exo = {"nodes": {}}
        endo = {"nodes": {}}
        for _ in range(5):
            siamind.touch(exo, "p", now, src="organ")
            siamind.touch(endo, "p", now, src="ponder")
        b_exo = siamind.actr_base(exo["nodes"]["p"], now + 60)
        b_endo = siamind.actr_base(endo["nodes"]["p"], now + 60)
        self.assertGreater(b_exo, b_endo,
                           "organ touches must outweigh self-reference")


class EpochMerge(unittest.TestCase):
    """Consolidation is idempotent: re-running against an existing epoch
    page EXTENDS it (sums counts), never atomically overwrites — the
    data-loss regression a reviewer would probe."""

    def test_merge_extends_not_overwrites(self):
        sialib = _load("sialib_e", os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as d:
            sialib.CORPUS = d
            sialib.log = lambda *a: None
            subprocess.run(["git", "init", "-q", d], check=True)
            os.makedirs(os.path.join(d, "events/org"))
            # two old day pages, same ISO week, well past the window
            for day, obs in (("2026-01-05", 4), ("2026-01-06", 3)):
                p = os.path.join(d, f"events/org/{day}.md")
                open(p, "w").write(
                    f'---\ntype: event-day\ntitle: "org {day}"\n'
                    f'tags: [org, obs]\ndate: {day}\n'
                    f'sia_counts: {{"obs": {obs}}}\n---\n# org\n\n## Log\n'
                    f'- 01:00:00Z obs thing\n\n## Timeline\n'
                    f'- **{day}** — {obs}\n')
            subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                            "-c", "user.name=t", "add", "-A"], check=True)
            subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                            "-c", "user.name=t", "commit", "-qm", "x"],
                           check=True)
            os.environ["SIA_EPISODIC_DAYS"] = "1"
            n1, e1, _ = sialib.consolidate_corpus()
            self.assertGreaterEqual(n1, 2)
            epoch = None
            for root, _, files in os.walk(os.path.join(d, "epochs")):
                for f in files:
                    epoch = os.path.join(root, f)
            self.assertIsNotNone(epoch, "epoch page must exist")
            import re
            c1 = json.loads(re.search(r"^sia_counts: (.*)$",
                                      open(epoch).read(), re.M).group(1))
            self.assertEqual(c1["obs"], 7)
            # add another old day for the SAME week, commit, re-consolidate
            p = os.path.join(d, "events/org/2026-01-07.md")
            open(p, "w").write(
                '---\ntype: event-day\ntitle: "org 2026-01-07"\n'
                'tags: [org, obs]\ndate: 2026-01-07\n'
                'sia_counts: {"obs": 5}\n---\n# org\n\n## Log\n'
                '- 01:00:00Z obs thing\n\n## Timeline\n'
                '- **2026-01-07** — 5\n')
            subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                            "-c", "user.name=t", "add", "-A"], check=True)
            subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                            "-c", "user.name=t", "commit", "-qm", "y"],
                           check=True)
            sialib.consolidate_corpus()
            c2 = json.loads(re.search(r"^sia_counts: (.*)$",
                                      open(epoch).read(), re.M).group(1))
            self.assertEqual(c2["obs"], 12, "merge must sum, not replace")


class HealHoldRate(unittest.TestCase):
    """Auto-proposed take confidence is arithmetic over the corpus's own
    heal history — thin history falls to the prior, never a model."""

    def _mk(self, d, days):
        droot = os.path.join(d, "events/sekhmet")
        os.makedirs(droot, exist_ok=True)
        for day in days:
            open(os.path.join(droot, day + ".md"), "w").write(
                "# sekhmet\n- 01:00Z outcome OUTCOME:restart_wireplumber "
                "- ok\n")

    def test_hold_rate_arithmetic(self):
        st = _load("siatakes_h", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            # heal 01-05 repeats on 01-08 (broken); the other three hold
            self._mk(d, ["2026-01-05", "2026-01-08", "2026-02-01",
                         "2026-03-01"])
            conf, judged, held = st.heal_hold_rate("restart_wireplumber",
                                                   corpus=d)
            self.assertEqual((judged, held), (4, 3))
            self.assertAlmostEqual(conf, 0.75)

    def test_thin_history_prior(self):
        st = _load("siatakes_h2", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            self._mk(d, ["2026-01-05"])
            conf, judged, held = st.heal_hold_rate("restart_wireplumber",
                                                   corpus=d)
            self.assertEqual(conf, st.HEAL_PRIOR)


class AutoPropose(unittest.TestCase):
    """Heals become PROPOSALS in the queue — never committed takes — and
    the same action is not proposed twice while one is pending."""

    class Ev:
        def __init__(self, organ, summary):
            self.organ, self.summary = organ, summary

    def test_propose_and_dedup(self):
        st = _load("siatakes_a", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            st.CORPUS = d
            st.TAKES_DIR = os.path.join(d, "takes")
            state = os.path.join(d, "state")
            os.makedirs(state)
            evs = [self.Ev("sekhmet", "OUTCOME:restart_wireplumber - ok"),
                   self.Ev("pacman", "OUTCOME:not_a_heal ok"),
                   self.Ev("sekhmet", "INTENT:restart_wireplumber - -")]
            p1 = st.auto_propose_heals(evs, state)
            self.assertEqual(len(p1), 1)
            self.assertIn("`restart_wireplumber`", p1[0]["claim"])
            self.assertTrue(p1[0]["proposed"].startswith("auto:heal-hold"))
            # queued now -> second pulse with same heal proposes nothing
            p2 = st.auto_propose_heals(evs, state)
            self.assertEqual(p2, [])
            # queue holds exactly one; no take page was minted
            q = json.load(open(os.path.join(state,
                                            "take-proposals.json")))
            self.assertEqual(len(q), 1)
            self.assertFalse(os.path.isdir(st.TAKES_DIR))

    def test_hyphenated_action_never_truncates(self):
        st = _load("siatakes_a2", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            st.CORPUS = d
            st.TAKES_DIR = os.path.join(d, "takes")
            state = os.path.join(d, "state")
            os.makedirs(state)
            # "ok" inside the action name must not truncate the capture
            p = st.auto_propose_heals(
                [self.Ev("sekhmet", "OUTCOME:probe-ok-net unit ok")],
                state)
            self.assertEqual(len(p), 1)
            self.assertIn("`probe-ok-net`", p[0]["claim"])

    def test_locked_proposals_serializes(self):
        st = _load("siatakes_l", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            st.locked_proposals(d, lambda cur: cur + [{"claim": "a"}])
            out = st.locked_proposals(d, lambda cur: cur + [{"claim": "b"}])
            self.assertEqual([p["claim"] for p in out], ["a", "b"])


def _intent_page(st):
    for name in os.listdir(st.INTENTS_DIR):
        if name.endswith(".md"):
            return os.path.join(st.INTENTS_DIR, name)
    raise AssertionError("no intent page")


class Intents(unittest.TestCase):
    """Prospective memory: create, surface by deadline, close on the
    operator's word only."""

    def test_lifecycle(self):
        st = _load("siatakes_i", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            st.CORPUS = d
            st.INTENTS_DIR = os.path.join(d, "intents")
            it = st.create_intent("rotate ledger keys", "2099-01-01")
            self.assertEqual(it["status"], "open")
            opened = st.open_intents()
            self.assertEqual(len(opened), 1)
            self.assertGreater(opened[0]["days_left"], 0)
            done = st.close_intent(it["id"][:6], "rotated")
            self.assertEqual(done["status"], "done")
            self.assertEqual(st.open_intents(), [])
            body = open(_intent_page(st)).read()
            self.assertIn("tags: [intent, done]", body)

    def test_bad_date_raises(self):
        st = _load("siatakes_i2", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            st.CORPUS = d
            st.INTENTS_DIR = os.path.join(d, "intents")
            with self.assertRaises(ValueError):
                st.create_intent("x", "not-a-date")

    def test_non_ascii_and_backslash_survive_close(self):
        # regression: re.sub once treated the JSON as a template — em
        # dashes crashed the close and backslashes were silently halved
        st = _load("siatakes_i3", os.path.join(BIN, "siatakes.py"))
        with tempfile.TemporaryDirectory() as d:
            st.CORPUS = d
            st.INTENTS_DIR = os.path.join(d, "intents")
            it = st.create_intent("réviser — clean C:\\temp \\d dir",
                                  "2099-01-01")
            done = st.close_intent(it["id"][:6], "done — rotated ☑")
            self.assertEqual(done["status"], "done")
            self.assertEqual(done["text"], "réviser — clean C:\\temp \\d dir")
            # page must round-trip: reload sees the closed intent intact
            loaded = st.load_intents()
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["text"], done["text"])
            self.assertEqual(loaded[0]["note"], "done — rotated ☑")


class Coincidence(unittest.TestCase):
    """Two organs spiking in the same window is an observation; the
    thought states the coincidence and the sighting count, no cause."""

    def test_pairs_counted(self):
        sialib = _load("sialib_c", os.path.join(BIN, "sialib.py"))
        mind = {}
        f1 = [("journal", "spike", "x"), ("pacman", "spike", "y"),
              ("jackal", "absence", "z")]
        out = sialib.coincidence_findings(mind, f1, now=1000.0)
        self.assertEqual(len(out), 1)
        self.assertIn("first sighting", out[0][0])
        self.assertIn("not a cause", out[0][0])
        self.assertEqual(sorted(out[0][1]),
                         ["organs/journal", "organs/pacman"])
        out2 = sialib.coincidence_findings(mind, f1, now=2000.0)
        self.assertIn("2nd sighting", out2[0][0])
        self.assertEqual(mind["coincide"]["journal|pacman"]["n"], 2)

    def test_single_organ_none(self):
        sialib = _load("sialib_c2", os.path.join(BIN, "sialib.py"))
        self.assertEqual(sialib.coincidence_findings(
            {}, [("journal", "spike", "x")], now=1.0), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""sialib — core of SIA, the Omarchy Brain.

“Brain” is a product metaphor for auditable local machine memory; it is not a
biological brain and does not establish cognition or neuroscience.

The brainstem daemon tails enabled base/optional/configured evidence streams
into a markdown corpus, syncs it into SIA's local gbrain (PGLite) index, checks
configured signed chains through their keeper verifiers, and derives
deterministic generated entries alongside origin-labeled user/model prose.
Everything the widget shows comes from the JSON snapshots exported here.
The persisted ``organ``, ``cortex``, ``mind``, ``thought``, and ``dream``
spellings are compatibility namespaces, not biological classifications or
claims about mental processes.

Honesty rules (house style):
  - Ledger rows elsewhere are recall; each keeper verifier is its evidence path.
  - Generated entries cite sources; user/model prose stays origin-labeled.
  - Built-in senses do not read private keys, message bodies, or clipboards;
    custom senses read exactly the operator-configured record path/field.
"""

import bisect, collections, contextlib, contextvars, copy, ctypes, errno, fcntl, functools, html, json, math, os, re, selectors, signal, sqlite3, stat, subprocess, sys, tempfile, time, hashlib, datetime, glob, unicodedata, uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import siamind
import siarestoreadmit
import siatakes
import siaqueue

HOME = os.path.expanduser("~")
SHARE = os.path.join(HOME, ".local/share/sia")
STATE = os.path.join(HOME, ".local/state/sia")
CORPUS = os.path.join(SHARE, "corpus")
BIN = os.path.join(SHARE, "bin")
TOOLCHAIN = os.path.join(SHARE, "toolchain")

BRAIN_METAPHOR_BOUNDARY = "“Brain” is a product metaphor for auditable local machine memory; it is not a biological brain and does not establish cognition or neuroscience."
CORTEX_BOUNDARY_REPAIR_SCHEMA = "sia-cortex-boundary-repair-v1"
CORTEX_BOUNDARY_REPAIR_JOURNAL_SCHEMA = (
    "sia-cortex-boundary-repair-journal-v1")
CORTEX_BOUNDARY_REPAIR_JOURNAL = os.path.join(
    STATE, "cortex-boundary-repair.journal.json")
CORTEX_BOUNDARY_REPAIR_RECEIPT = os.path.join(
    STATE, "cortex-boundary-repair.receipt.json")
CORTEX_BOUNDARY_REPAIR_SUFFIX = (
    "\n\n## Current product-metaphor boundary\n\n"
    + BRAIN_METAPHOR_BOUNDARY + "\n\n"
    "The preceding wording is retained historical product prose. This "
    "boundary governs the current claim.\n")
GBRAIN = os.path.join(TOOLCHAIN, "gbrain", "bin", "gbrain")
GBRAIN_OWNER_LOCK = os.path.join(STATE, "gbrain-owner.lock")
CORPUS_OWNER_LOCK = os.path.join(STATE, "corpus-owner.lock")
BRAINSTEM_OWNER_LOCK = os.path.join(STATE, "brainstem-owner.lock")
LIFECYCLE_LOCK = os.path.join(HOME, ".local/state/sia.lifecycle.lock")
LIFECYCLE_TOMBSTONE = os.path.join(
    HOME, ".local/state/sia.lifecycle-removed")
RESTORE_BARRIER_PATH = os.path.join(
    HOME, ".local/state/sia-continuity/restore-in-progress.json")
RESTORE_MASK_PATH = os.path.join(
    HOME, ".local/state/sia-continuity/restore-runtime-mask")
RESTORE_SUPERVISOR_PATH = os.path.join(
    HOME, ".local/state/sia-continuity/restore-supervisor.json")
THOUGHT_INBOX_PATH = os.path.join(STATE, "thought-inbox.json")
THOUGHT_INBOX_LOCK = os.path.join(STATE, "thought-inbox.lock")
THOUGHT_INBOX_CLAIM = os.path.join(STATE, "thought-inbox.draining.json")
ATTEST = os.path.join(HOME, ".local/bin/attest")
BUN_DIR = os.path.join(TOOLCHAIN, "bun", "bin")

GBRAIN_ENV = dict(os.environ,
                  GBRAIN_HOME=SHARE,
                  GBRAIN_SKIP_STARTUP_HOOKS="1",
                  PATH=BUN_DIR + ":" + os.environ.get("PATH", ""))

# gbrain registers this corpus under one named source. Every page-addressed
# invocation must name it: without --source the lookup lands in gbrain's
# "default" source and fails with "Page not found" even though the page is
# synced and embedded.
GBRAIN_SOURCE = "sia"

# ---- instance configuration (~/.config/sia/config.json) --------------
# SIA is generic: a base set of senses every Linux/Omarchy box has, plus
# OPTIONAL integrations that activate only when their data exists on this
# machine, plus user-defined custom senses. Nothing machine-specific
# lives in the code.
CONFIG_PATH = os.path.join(HOME, ".config/sia/config.json")
MAX_CONFIG_BYTES = 65_536
MAX_CONFIG_PATH_CHARS = 4096
MAX_CONFIG_TEXT_CHARS = 2000
MAX_SOURCE_NAME_CHARS = 200
MAX_CONFIG_TAGS = 8
MAX_CONFIGURED_CHAINS = MAX_CONFIG_TAGS
MAX_STATE_JSON_BYTES = 16_777_216
MAX_LEDGER_PENDING_RECORDS = 1024
# Arithmetic evidence: status=exact, parsed=2^53-1, exact=9007199254740991.
# Exact rational arithmetic outside the Lean certificate chain; NOT
# formal-bounded. This is the largest integer JSON/JavaScript can carry
# without changing its value.
MAX_JSON_SAFE_INTEGER = 9_007_199_254_740_991
DEFAULT_SKILL_ROOTS = [
    ".claude/skills", ".agents/skills", ".omp/skills",
    ".copilot/skills", ".config/agents/skills"]

CONFIG_ERRORS = []

_strict_json_loads = siaqueue.strict_json_loads


def _record_config_error(code):
    if not isinstance(code, str) or not code \
            or len(code) > MAX_SOURCE_NAME_CHARS:
        code = "invalid-configuration"
    row = {"config": "config.json", "error": code}
    if row not in CONFIG_ERRORS and len(CONFIG_ERRORS) < MAX_CONFIG_TAGS:
        CONFIG_ERRORS.append(row)


def _strict_config_string(value, *, nonempty=False, limit=None):
    if not isinstance(value, str) \
            or limit is not None and len(value) > limit \
            or nonempty and not value.strip():
        return False
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        return False
    return True


_CUSTOM_SENSE_ENTRY_KEYS = frozenset({
    "_comment", "name", "organ", "description", "path", "type",
    "enabled", "match", "exclude", "field", "kind", "tags",
})

_CONFIG_TOP_LEVEL_KEYS = frozenset({
    "_comment", "_egress_trust_boundary", "judge", "senses", "skills",
    "custom_senses", "chains", "retrieval",
})


def _validated_custom_match_literals(value, *, field="match"):
    """Return the one finite literal grammar shared by every config user."""
    if field not in {"match", "exclude"}:
        raise ValueError("custom literal field is invalid")
    if value is None or value == "":
        return ()
    if not _strict_config_string(value, limit=MAX_CONFIG_TEXT_CHARS):
        raise ValueError(f"{field} must be a bounded string")
    alternatives = value.split("|")
    if len(alternatives) > MAX_CONFIG_TAGS \
            or any(not literal for literal in alternatives):
        raise ValueError(
            f"{field} must contain bounded non-empty literal alternatives")
    regex_operators = set(r"\.^$*+?{}[]()")
    if any(regex_operators.intersection(literal)
           for literal in alternatives):
        raise ValueError(
            f"{field} supports literal alternatives only, not regex syntax")
    return tuple(alternatives)


def _validated_custom_sense_entry(value):
    """Validate one custom source and its compatibility ``organ`` label."""
    if not isinstance(value, dict):
        raise ValueError("configuration entry must be an object")
    if any(key not in _CUSTOM_SENSE_ENTRY_KEYS for key in value):
        raise ValueError("configuration entry has unknown keys")
    if "enabled" in value and not isinstance(value["enabled"], bool):
        raise ValueError("enabled must be boolean")
    if value.get("enabled") is False:
        return None

    description = value.get("description", "custom evidence stream")
    if not _strict_config_string(
            description, limit=MAX_CONFIG_TEXT_CHARS):
        raise ValueError("description must be a bounded string")
    if not _strict_config_string(
            value.get("name"), nonempty=True,
            limit=MAX_CONFIG_TEXT_CHARS):
        raise ValueError("name must be a non-empty string")
    name = sanitize_slugpart(value["name"])
    source_id = f"sense_custom:{name}"
    if len(name) > MAX_SOURCE_NAME_CHARS \
            or len(source_id) > MAX_SOURCE_NAME_CHARS:
        raise ValueError("name exceeds its canonical source bound")

    organ_value = value.get("organ", name)
    if not _strict_config_string(
            organ_value, nonempty=True, limit=MAX_CONFIG_TEXT_CHARS):
        raise ValueError("organ must be a non-empty string")
    organ = sanitize_slugpart(organ_value)
    if len(organ) > MAX_SOURCE_NAME_CHARS:
        raise ValueError("organ exceeds its canonical bound")

    path_value = value.get("path")
    if not _strict_config_string(
            path_value, nonempty=True, limit=MAX_CONFIG_PATH_CHARS):
        raise ValueError("path must be a non-empty string")
    stream_type = value.get("type", "lines")
    if stream_type not in {"lines", "jsonl"}:
        raise ValueError("type must be lines or jsonl")
    match_literals = _validated_custom_match_literals(value.get("match"))
    exclude_literals = _validated_custom_match_literals(
        value.get("exclude"), field="exclude")

    field = value.get("field", "message")
    if not _strict_config_string(
            field, nonempty=True, limit=MAX_SOURCE_NAME_CHARS):
        raise ValueError("field must be a non-empty string")
    kind_value = value.get("kind", "event")
    if not _strict_config_string(
            kind_value, nonempty=True, limit=MAX_CONFIG_TEXT_CHARS):
        raise ValueError("kind must be a non-empty string")
    kind = sanitize_slugpart(kind_value)
    if len(kind) > MAX_SOURCE_NAME_CHARS:
        raise ValueError("kind exceeds its canonical bound")

    tags_value = value.get("tags", [])
    if not isinstance(tags_value, list) \
            or len(tags_value) > MAX_CONFIG_TAGS \
            or any(not _strict_config_string(
                       tag, nonempty=True, limit=MAX_CONFIG_TEXT_CHARS)
                   for tag in tags_value):
        raise ValueError("tags must be a list of non-empty strings")
    tags = {sanitize_slugpart(tag) for tag in tags_value} | {organ}
    if any(len(tag) > MAX_SOURCE_NAME_CHARS for tag in tags):
        raise ValueError("tag exceeds its canonical bound")

    return {
        "name": name,
        "source_id": source_id,
        "organ": organ,
        "description": description,
        "path": os.path.expanduser(path_value),
        "stream_type": stream_type,
        "match_literals": match_literals,
        "exclude_literals": exclude_literals,
        "field": field,
        "kind": kind,
        "tags": tags,
    }

_LAST_LOADED_CONFIG = None
_LAST_CONFIG_LOAD_VALID = True


def _loaded_config(value, valid):
    """Bind parse provenance to the exact object returned by load_config."""
    global _LAST_LOADED_CONFIG, _LAST_CONFIG_LOAD_VALID
    _LAST_LOADED_CONFIG = value
    _LAST_CONFIG_LOAD_VALID = valid
    return value


def _active_config_load_valid():
    """Whether active CONFIG came from a complete read or explicit override."""
    return CONFIG is not _LAST_LOADED_CONFIG or _LAST_CONFIG_LOAD_VALID


def _file_generation(info):
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _exact_int(value, expected):
    return type(value) is int and value == expected


def load_config():
    CONFIG_ERRORS.clear()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(CONFIG_PATH, flags)
    except FileNotFoundError:
        return _loaded_config({}, True)
    except OSError:
        _record_config_error("config-open-refused")
        return _loaded_config({}, False)
    try:
        with siaqueue.regular_file_stream(fd, error_type=OSError) as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) \
                    or before.st_uid != os.geteuid() \
                    or before.st_nlink != 1 \
                    or before.st_size > MAX_CONFIG_BYTES:
                _record_config_error("config-file-refused")
                return _loaded_config({}, False)
            raw = stream.read(MAX_CONFIG_BYTES + 1)
            after = os.fstat(stream.fileno())
        observed = _file_generation(before)
        finished = _file_generation(after)
        if observed != finished or len(raw) > MAX_CONFIG_BYTES \
                or after.st_uid != os.geteuid() or after.st_nlink != 1:
            _record_config_error("config-changed-or-over-bound")
            return _loaded_config({}, False)
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeError:
            _record_config_error("config-invalid-utf8")
            return _loaded_config({}, False)
        try:
            value = _strict_json_loads(text)
        except (UnicodeError, ValueError, RecursionError):
            _record_config_error("config-invalid-json")
            return _loaded_config({}, False)
        try:
            target = os.lstat(CONFIG_PATH)
        except OSError:
            _record_config_error("config-changed-or-over-bound")
            return _loaded_config({}, False)
        current = _file_generation(target)
        if not stat.S_ISREG(target.st_mode) \
                or target.st_uid != os.geteuid() \
                or target.st_nlink != 1 or current != finished:
            _record_config_error("config-changed-or-over-bound")
            return _loaded_config({}, False)
        if not isinstance(value, dict):
            _record_config_error("config-must-be-object")
            return _loaded_config({}, False)
        if set(value) - _CONFIG_TOP_LEVEL_KEYS:
            # A misspelled policy key is not an ignorable extension: treating
            # e.g. ``sense`` as absent would silently restore the default
            # source roster and invert the operator's disable intent.
            _record_config_error("config-unknown-key")
            return _loaded_config({}, False)
        for comment_key in ("_comment", "_egress_trust_boundary"):
            if comment_key in value and not _strict_config_string(
                    value[comment_key], limit=MAX_CONFIG_TEXT_CHARS):
                _record_config_error("config-comment-must-be-string")
                return _loaded_config({}, False)
        senses = value.get("senses", {})
        if not isinstance(senses, dict):
            _record_config_error("senses-must-be-object")
        else:
            if set(senses) - {"_comment", "disable"}:
                _record_config_error("senses-unknown-key")
            if "_comment" in senses and not _strict_config_string(
                    senses["_comment"], limit=MAX_CONFIG_TEXT_CHARS):
                _record_config_error("senses-comment-must-be-string")
            disabled = senses.get("disable", [])
            if not isinstance(disabled, list):
                _record_config_error("senses-disable-must-be-list")
            elif len(disabled) > MAX_CONFIG_BYTES or any(
                    not _strict_config_string(
                        item, nonempty=True, limit=MAX_SOURCE_NAME_CHARS)
                    for item in disabled):
                _record_config_error("senses-disable-entry-invalid")
        skills = value.get("skills", {})
        if not isinstance(skills, dict):
            _record_config_error("skills-must-be-object")
        else:
            if set(skills) - {"_comment", "roots"}:
                _record_config_error("skills-unknown-key")
            if "_comment" in skills and not _strict_config_string(
                    skills["_comment"], limit=MAX_CONFIG_TEXT_CHARS):
                _record_config_error("skills-comment-must-be-string")
        custom = value.get("custom_senses", [])
        if not isinstance(custom, list):
            _record_config_error("custom-senses-must-be-list")
        elif len(custom) > MAX_LEDGER_PENDING_RECORDS:
            _record_config_error("custom-senses-over-bound")
        chains = value.get("chains", [])
        if not isinstance(chains, list):
            _record_config_error("chains-must-be-list")
        elif len(chains) > MAX_CONFIGURED_CHAINS:
            _record_config_error("chains-over-bound")
        retrieval = value.get("retrieval", {})
        if not isinstance(retrieval, dict):
            _record_config_error("retrieval-must-be-object")
        else:
            if set(retrieval) - {"_comment", "associative_rerank"}:
                _record_config_error("retrieval-unknown-key")
            if "_comment" in retrieval and not _strict_config_string(
                    retrieval["_comment"], limit=MAX_CONFIG_TEXT_CHARS):
                _record_config_error("retrieval-comment-must-be-string")
            if "associative_rerank" in retrieval \
                    and not isinstance(retrieval["associative_rerank"], bool):
                _record_config_error("retrieval-associative-rerank-must-be-bool")
        return _loaded_config(value, True)
    except OSError:
        _record_config_error("config-read-refused")
        return _loaded_config({}, False)

CONFIG = load_config()


def _configured_skill_root_paths():
    """Return the one validated skill-root roster used by activation/scans."""
    if not _active_config_load_valid():
        return []
    skills = CONFIG.get("skills", {})
    if not isinstance(skills, dict):
        _record_config_error("skills-must-be-object")
        return []
    shape_valid = True
    if set(skills) - {"_comment", "roots"}:
        _record_config_error("skills-unknown-key")
        shape_valid = False
    if "_comment" in skills and not _strict_config_string(
            skills["_comment"], limit=MAX_CONFIG_TEXT_CHARS):
        _record_config_error("skills-comment-must-be-string")
        shape_valid = False
    if not shape_valid:
        return []
    roots = skills.get("roots", DEFAULT_SKILL_ROOTS)
    if not isinstance(roots, list) or len(roots) > MAX_CONFIG_TAGS \
            or any(not _strict_config_string(
                       root, nonempty=True, limit=MAX_CONFIG_PATH_CHARS)
                   or "\0" in root or os.path.isabs(root)
                   for root in roots):
        _record_config_error("skills-roots-invalid")
        return []
    home = os.path.abspath(HOME)
    resolved = [os.path.abspath(os.path.join(home, root)) for root in roots]
    try:
        contained = all(
            os.path.commonpath((home, root)) == home for root in resolved)
    except ValueError:
        contained = False
    if not contained:
        _record_config_error("skills-roots-outside-home")
        return []
    return resolved


def associative_rerank_enabled(config=None):
    """Whether `sia ask` applies the graph-influenced associative rerank.

    Default OFF by measurement, per the hypothesis-lane freeze rule: on the
    extended 22-probe tripwire set (2026-09-02) the blend scored uniformly
    below the unmodified hybrid query (slug match@5 0.86 vs 0.91, reciprocal
    rank 0.67 vs 0.71, match@1 0.50 vs 0.59), so graph influence must be enabled
    deliberately (`retrieval.associative_rerank: true`) and earns its default
    back only with a measured win. The nightly tripwire keeps measuring the
    blend lane either way, so the hypothesis stays under instrumentation.
    """
    source = CONFIG if config is None else config
    if not isinstance(source, dict):
        return False
    retrieval = source.get("retrieval", {})
    return isinstance(retrieval, dict) \
        and not set(retrieval) - {"_comment", "associative_rerank"} \
        and ("_comment" not in retrieval or _strict_config_string(
            retrieval["_comment"], limit=MAX_CONFIG_TEXT_CHARS)) \
        and retrieval.get("associative_rerank") is True


def _configured_obsidian_vault():
    """Absolute vault root for the optional Obsidian source.

    An absent environment override selects ``~/Obsidian``.  A present
    override must already be an absolute, bounded UTF-8 path.  Invalid
    overrides disable the source instead of silently falling back to a
    different vault.
    """
    if "OBSIDIAN_VAULT_PATH" not in os.environ:
        return os.path.join(HOME, "Obsidian")
    value = os.environ.get("OBSIDIAN_VAULT_PATH")
    if not _strict_config_string(
            value, nonempty=True, limit=MAX_CONFIG_PATH_CHARS) \
            or not os.path.isabs(value):
        _record_config_error("obsidian-vault-environment-invalid")
        return None
    return os.path.normpath(value)


OBSIDIAN_VAULT = _configured_obsidian_vault()

# Base sources, exposed through the persisted ``organ`` compatibility map.
BASE_ORGANS = {
    "sia":         ("SIA ledger",  "SIA's signed lifecycle transitions"),
    "pacman":      ("pacman",      "package manager"),
    "journal":     ("journal",     "systemd journal (errors and faults)"),
    "claude-code": ("Claude Code", "Claude agent sessions on this box"),
    "projects":    ("Projects",    "git activity under ~/Projects"),
    "notify":      ("Notifications", "desktop notification stream"),
    "agents":      ("Agents",       "AI-agent usage meters (Omarchy Quattro)"),
}
# Optional integrations activate when their data exists. Skills is the one
# stateful exception: a non-empty configured roster remains active through
# total source absence so its persisted removal guard can reconcile.
OPTIONAL_ORGANS = {
    "jackal":    ("JACKAL",    "deterministic mathematical evidence kernel",
                  ".local/state/jackal"),
    "sekhmet":   ("SEKHMET",   "SPARK-proved self-healing fabric",
                  ".local/share/sekhmet"),
    "custos":    ("Custos",    "proof-carrying Downloads custodian",
                  ".local/share/custos"),
    "aegis":     ("AEGIS",     "Anubis command-authority showcase",
                  ".local/share/aegis"),
    "worldline": ("WORLDLINE", "branchable-reality system",
                  ".local/state/worldline"),
    "guardian":  ("Guardian",  "Omarchy preflight and checkpoint tool",
                  ".local/state/omarchy-guardian"),
    "codex":     ("Codex",     "Codex CLI sessions on this box",
                  ".codex/sessions"),
    "skills":    ("Skills",    "agent skills installed on this box",
                  ".claude/skills"),
    # Records, not note bodies: the vault's git history only.  ``None`` is a
    # deliberate sentinel; activation uses the no-follow directory gate once
    # that helper has been defined below.
    "obsidian":  ("Obsidian",  "git-backed Obsidian vault (records, not notes)",
                  None),
}


def sanitize_slugpart(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-.")
    return s or "unknown"


def _configured_disabled_sense_policy():
    """Return (valid, canonical keys) for every native/custom source gate."""
    if not isinstance(CONFIG, dict):
        _record_config_error("config-must-be-object")
        return False, set()
    if not _active_config_load_valid():
        # A fatal read/parse failure cannot distinguish an intentional prior
        # disable from an absent policy. Run no configurable source until a
        # missing or valid configuration establishes the default roster.
        return False, set()
    senses = CONFIG.get("senses", {})
    if not isinstance(senses, dict):
        _record_config_error("senses-must-be-object")
        return False, set()
    if set(senses) - {"_comment", "disable"}:
        _record_config_error("senses-unknown-key")
        return False, set()
    if "_comment" in senses and not _strict_config_string(
            senses["_comment"], limit=MAX_CONFIG_TEXT_CHARS):
        _record_config_error("senses-comment-must-be-string")
        return False, set()
    disabled = senses.get("disable", [])
    if not isinstance(disabled, list):
        _record_config_error("senses-disable-must-be-list")
        return False, set()
    if len(disabled) > MAX_CONFIG_BYTES or any(
            not _strict_config_string(
                value, nonempty=True, limit=MAX_SOURCE_NAME_CHARS)
            for value in disabled):
        _record_config_error("senses-disable-entry-invalid")
        return False, set()
    return True, {sanitize_slugpart(value) for value in disabled}


def _configured_disabled_organs():
    """Compatibility view of the native-organ portion of disable policy."""
    valid, disabled = _configured_disabled_sense_policy()
    if not valid:
        return set(BASE_ORGANS) | set(OPTIONAL_ORGANS)
    return disabled


def _sense_disabled(key, policy):
    valid, disabled = policy
    return not valid or sanitize_slugpart(key) in disabled


def _custom_sense_disabled(normalized, policy):
    return (_sense_disabled(normalized["name"], policy)
            or _sense_disabled(normalized["organ"], policy))


def _build_organs():
    policy = _configured_disabled_sense_policy()
    organs = {
        key: value for key, value in BASE_ORGANS.items()
        if not _sense_disabled(key, policy)}
    for key, (name, desc, probe) in OPTIONAL_ORGANS.items():
        if _sense_disabled(key, policy):
            continue
        if key == "obsidian":
            try:
                active = (OBSIDIAN_VAULT is not None
                          and _nofollow_source_directory(os.path.join(
                              OBSIDIAN_VAULT, ".git")))
            except (OSError, RuntimeError, ValueError):
                active = False
        elif key == "skills":
            # Registration must survive a restart while every configured
            # root is absent. The sense owns the distinction between a clean
            # never-observed absence and a previously observed source loss;
            # omitting it here would strand its durable removal guard.
            active = bool(_configured_skill_root_paths())
        else:
            probe_path = (probe if os.path.isabs(probe)
                          else os.path.join(HOME, probe))
            active = os.path.exists(probe_path)
        if active:
            organs[key] = (name, desc)
    configured = (CONFIG.get("custom_senses", [])
                  if isinstance(CONFIG, dict) else [])
    if not isinstance(configured, list) \
            or len(configured) > MAX_LEDGER_PENDING_RECORDS:
        configured = []
    seen_custom_names = set()
    for cs in configured:
        try:
            normalized = _validated_custom_sense_entry(cs)
        except ValueError:
            continue
        if normalized is None or _custom_sense_disabled(
                normalized, policy) \
                or normalized["name"] in seen_custom_names:
            continue
        seen_custom_names.add(normalized["name"])
        organ = normalized["organ"]
        organs.setdefault(
            organ, (organ, normalized["description"]))
    return organs

# Tags that carry deterministic safety-priority weight (mirrored into gbrain config).
HIGH_TAGS = ["integrity-failure", "refusal", "crash", "coredump", "failed",
             "collapse", "healing", "urgent"]

VERSION = "1.7.8"


# Corpus bytes and their derived PGLite/graph projections form one publication
# unit. High-level transactions install a callback here so the first actual
# corpus mutation durably records publication debt *before* changing a page.
# A ContextVar makes nested helpers exception-safe without leaking a callback
# into a later daemon cycle.
_CORPUS_MUTATION_BARRIER = contextvars.ContextVar(
    "sia_corpus_mutation_barrier", default=None)
_CORPUS_OWNER_DEPTH = contextvars.ContextVar(
    "sia_corpus_owner_depth", default=0)
_CORPUS_OWNER_FD = contextvars.ContextVar(
    "sia_corpus_owner_fd", default=None)
_BRAINSTEM_OWNER_FD = contextvars.ContextVar(
    "sia_brainstem_owner_fd", default=None)
_GBRAIN_OWNER_FD = contextvars.ContextVar(
    "sia_gbrain_owner_fd", default=None)
_LIFECYCLE_READER_DEPTH = contextvars.ContextVar(
    "sia_lifecycle_reader_depth", default=0)
_INHERITED_LIFECYCLE_FD_ENV = "SIA_INHERITED_LIFECYCLE_FD"
_INHERITED_CORPUS_FD_ENV = "SIA_INHERITED_CORPUS_FD"
_LAUNCHER_ABI = "sia-launch-v1"
_LAUNCHER_ABI_ENV = "SIA_LAUNCHER_ABI"
_LAUNCHER_LIFECYCLE_FD_ENV = "SIA_LAUNCHER_LIFECYCLE_FD"
_LAUNCHER_TARGET_FD_ENV = "SIA_LAUNCHER_TARGET_FD"
_LAUNCHER_TARGET_PATH_ENV = "SIA_LAUNCHER_TARGET_PATH"
_RESTORE_LAUNCH_ABI_ENV = "SIA_RESTORE_LAUNCH_ABI"
_RESTORE_LAUNCH_ABI = "sia-restore-launch-v1"
_RESTORE_FINALIZE_ABI_ENV = "SIA_RESTORE_FINALIZE_ABI"
_RESTORE_FINALIZE_ADMIN_FD_ENV = "SIA_RESTORE_FINALIZE_ADMIN_FD"
_RESTORE_FINALIZE_ABI = "sia-restore-finalize-v1"


@contextlib.contextmanager
def corpus_mutation_barrier(before_mutation):
    if not callable(before_mutation):
        raise TypeError("corpus mutation barrier must be callable")
    token = _CORPUS_MUTATION_BARRIER.set(before_mutation)
    try:
        yield
    finally:
        _CORPUS_MUTATION_BARRIER.reset(token)


def _before_corpus_mutation():
    callback = _CORPUS_MUTATION_BARRIER.get()
    if callback is not None:
        callback()
        # Shipped mutation paths install this barrier. The projection marker
        # is durable before their page write or unlink and deliberately
        # records conservative scan debt rather than trusting a caller to
        # describe which derived node or edge changed.
        marker = globals().get("_mark_graph_projection_dirty")
        if marker is not None:
            marker()


# ---------------------------------------------------------------- utilities

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)

def iso(dt=None):
    return (dt or utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")

def today(dt=None):
    return (dt or utcnow()).strftime("%Y-%m-%d")

def ensure_dirs():
    for d in (SHARE, STATE, CORPUS, BIN):
        os.makedirs(d, exist_ok=True)

def atomic_write(path, data, *, mode=None):
    if mode is not None and (
            isinstance(mode, bool) or not isinstance(mode, int)
            or mode < 0 or mode > 0o777):
        raise ValueError("atomic-write mode must be an integer permission mode")
    selected_mode = 0o600 if mode is None else mode
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        current = None
    if current is not None:
        if not stat.S_ISREG(current.st_mode):
            raise ValueError("atomic-write target is not a regular file")
        if mode is None:
            selected_mode = stat.S_IMODE(current.st_mode)
    if not isinstance(data, str):
        raise TypeError("atomic-write data must be text")
    encoded = data.encode("utf-8", errors="strict")
    siaqueue.fixed_atomic_publish(
        path, encoded, mode=selected_mode,
        staging_dir=siaqueue.staging_dir_for(
            path, authority_roots=(CORPUS, STATE, SHARE)))


def _legacy_atomic_temp_name(name):
    return isinstance(name, str) and len(name) <= 255 \
        and re.fullmatch(r"\..+\.[A-Za-z0-9_-]{1,200}\.new", name) \
        is not None


def _remove_legacy_atomic_temp(descriptor, entry, label):
    info = entry.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
            or info.st_nlink != 1:
        raise ValueError(f"{label} has an unsafe legacy staging entry")
    os.unlink(entry.name, dir_fd=descriptor)


def ensure_durable_directory(path, mode=0o755):
    """Create a directory chain and persist every link in its parent.

    Parent fsync is repeated for an already-visible target so a retry closes
    the case where a prior creator linked the directory and then failed before
    that link reached stable storage.
    """
    target = os.path.abspath(path)
    missing = []
    cursor = target
    while not os.path.lexists(cursor):
        parent, name = os.path.split(cursor)
        if not name or parent == cursor:
            raise ValueError("durable directory has no existing ancestor")
        missing.append(name)
        cursor = parent
    ancestor = os.lstat(cursor)
    if not stat.S_ISDIR(ancestor.st_mode):
        raise ValueError("durable directory ancestor is not a real directory")

    def sync_directory_and_link(directory, *, require_owner):
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) \
            | getattr(os, "O_CLOEXEC", 0) \
            | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(directory, flags)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode) \
                    or (require_owner and info.st_uid != os.geteuid()):
                raise ValueError(
                    "durable directory is not an owned real directory")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        parent = os.path.dirname(directory) or os.path.sep
        parent_fd = os.open(parent, flags)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)

    # If this is a retry after a failed first creator, syncing the deepest
    # existing link before descending is what repairs that earlier window.
    sync_directory_and_link(cursor, require_owner=(cursor == target))
    for name in reversed(missing):
        child = os.path.join(cursor, name)
        try:
            os.mkdir(child, mode)
        except FileExistsError:
            pass
        sync_directory_and_link(child, require_owner=True)
        cursor = child
    return target

def read_json(path, default):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except Exception:
        return default
    try:
        with siaqueue.regular_file_stream(fd, error_type=OSError) as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) \
                    or before.st_uid != os.geteuid() \
                    or before.st_nlink != 1 \
                    or before.st_size > MAX_STATE_JSON_BYTES:
                return default
            raw = stream.read(MAX_STATE_JSON_BYTES + 1)
            after = os.fstat(stream.fileno())
        observed = _file_generation(before)
        finished = _file_generation(after)
        if observed != finished or len(raw) > MAX_STATE_JSON_BYTES:
            return default
        value = _strict_json_loads(raw.decode("utf-8"))
        target = os.lstat(path)
        current = _file_generation(target)
        if not stat.S_ISREG(after.st_mode) \
                or after.st_uid != os.geteuid() or after.st_nlink != 1 \
                or not stat.S_ISREG(target.st_mode) \
                or target.st_uid != os.geteuid() \
                or target.st_nlink != 1 or current != finished:
            return default
        return value
    except (OSError, UnicodeError, ValueError, RecursionError):
        return default


def read_state_json(path, default, label, *, expected_type=None):
    """Read daemon-owned JSON without following links or hiding damage.

    Missing state has a well-defined bootstrap value. Existing state is a
    durable cursor/transaction boundary, so malformed, unreadable, linked,
    or type-confused files must stop the writer instead of silently resetting
    it and laundering skipped evidence into a fresh snapshot.
    """
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return copy.deepcopy(default)
    except OSError as exc:
        raise RuntimeError(f"{label} state cannot be opened safely: {exc}") \
            from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) \
                or info.st_uid != os.geteuid() or info.st_nlink != 1:
            raise RuntimeError(
                f"{label} state is not an owned single-link regular file")
        try:
            with os.fdopen(fd, "rb") as stream:
                fd = -1
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) \
                        or before.st_uid != os.geteuid() \
                        or before.st_nlink != 1 \
                        or before.st_size > MAX_STATE_JSON_BYTES:
                    raise RuntimeError(
                        f"{label} state is not a bounded owned single-link "
                        "regular file")
                raw = stream.read(MAX_STATE_JSON_BYTES + 1)
                after = os.fstat(stream.fileno())
                observed = _file_generation(before)
                finished = _file_generation(after)
                if observed != finished or len(raw) > MAX_STATE_JSON_BYTES:
                    raise RuntimeError(
                        f"{label} state changed while read or exceeds its bound")
                value = _strict_json_loads(raw.decode("utf-8"))
                try:
                    target = os.lstat(path)
                except OSError as exc:
                    raise RuntimeError(
                        f"{label} state changed while read") from exc
                current = _file_generation(target)
                if not stat.S_ISREG(after.st_mode) \
                        or after.st_uid != os.geteuid() \
                        or after.st_nlink != 1 \
                        or not stat.S_ISREG(target.st_mode) \
                        or target.st_uid != os.geteuid() \
                        or target.st_nlink != 1 or current != finished:
                    raise RuntimeError(f"{label} state changed while read")
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            raise RuntimeError(
                f"{label} state is unreadable or malformed") from exc
    finally:
        if fd >= 0:
            os.close(fd)
    expected_type = type(default) if expected_type is None else expected_type
    if not isinstance(value, expected_type):
        raise RuntimeError(
            f"{label} state has type {type(value).__name__}; "
            f"expected {expected_type.__name__}")
    return value


class OwnerBusy(RuntimeError):
    """A shipped process already owns an operation's serialization lease."""


def _validated_inherited_lifecycle_fd():
    """Recognize only the installer's inherited exclusive lifecycle lease."""
    raw = os.environ.get(_INHERITED_LIFECYCLE_FD_ENV)
    if raw is None:
        return None
    if not raw or not raw.isascii() or not raw.isdigit():
        raise RuntimeError("invalid inherited SIA lifecycle descriptor")
    try:
        inherited_fd = int(raw, 10)
        inherited = os.fstat(inherited_fd)
        target = os.lstat(LIFECYCLE_LOCK)
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            "invalid inherited SIA lifecycle descriptor") from exc
    if not stat.S_ISREG(inherited.st_mode) \
            or inherited.st_uid != os.geteuid() \
            or not stat.S_ISREG(target.st_mode) \
            or target.st_uid != os.geteuid() \
            or (inherited.st_dev, inherited.st_ino) != \
               (target.st_dev, target.st_ino):
        raise RuntimeError(
            "inherited SIA lifecycle descriptor is not the owned lease")

    flags = (os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    try:
        probe_fd = os.open(LIFECYCLE_LOCK, flags)
    except OSError as exc:
        raise RuntimeError("could not probe inherited SIA lifecycle lease") \
            from exc
    try:
        probe = os.fstat(probe_fd)
        if not stat.S_ISREG(probe.st_mode) \
                or probe.st_uid != os.geteuid() \
                or (probe.st_dev, probe.st_ino) != \
                   (inherited.st_dev, inherited.st_ino):
            raise RuntimeError("SIA lifecycle lease changed during handoff")
        try:
            fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(probe_fd, fcntl.LOCK_UN)
            raise RuntimeError(
                "inherited SIA lifecycle descriptor has no conflicting lease")
        try:
            fcntl.flock(probe_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(probe_fd, fcntl.LOCK_UN)
            raise RuntimeError(
                "inherited SIA lifecycle descriptor is not exclusively held")
        try:
            fcntl.flock(inherited_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "inherited SIA lifecycle descriptor does not own the lease") \
                from exc
    finally:
        os.close(probe_fd)
    return inherited_fd


def _validated_inherited_corpus_fd():
    """Recognize only a parent's inherited exclusive corpus lease."""
    raw = os.environ.get(_INHERITED_CORPUS_FD_ENV)
    if raw is None:
        return None
    if not raw or not raw.isascii() or not raw.isdigit():
        raise RuntimeError("invalid inherited SIA corpus descriptor")
    try:
        inherited_fd = int(raw, 10)
        inherited = os.fstat(inherited_fd)
        target = os.lstat(CORPUS_OWNER_LOCK)
    except (OSError, ValueError) as exc:
        raise RuntimeError("invalid inherited SIA corpus descriptor") from exc
    if not stat.S_ISREG(inherited.st_mode) \
            or inherited.st_uid != os.geteuid() \
            or not stat.S_ISREG(target.st_mode) \
            or target.st_uid != os.geteuid() \
            or (inherited.st_dev, inherited.st_ino) != \
               (target.st_dev, target.st_ino):
        raise RuntimeError(
            "inherited SIA corpus descriptor is not the owned lease")

    flags = (os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    try:
        probe_fd = os.open(CORPUS_OWNER_LOCK, flags)
    except OSError as exc:
        raise RuntimeError("could not probe inherited SIA corpus lease") \
            from exc
    try:
        probe = os.fstat(probe_fd)
        if not stat.S_ISREG(probe.st_mode) \
                or probe.st_uid != os.geteuid() \
                or (probe.st_dev, probe.st_ino) != \
                   (inherited.st_dev, inherited.st_ino):
            raise RuntimeError("SIA corpus lease changed during handoff")
        try:
            fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(probe_fd, fcntl.LOCK_UN)
            raise RuntimeError(
                "inherited SIA corpus descriptor has no conflicting lease")
        try:
            fcntl.flock(probe_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(probe_fd, fcntl.LOCK_UN)
            raise RuntimeError(
                "inherited SIA corpus descriptor is not exclusively held")
        try:
            fcntl.flock(inherited_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "inherited SIA corpus descriptor does not own the lease") \
                from exc
    finally:
        os.close(probe_fd)
    return inherited_fd


def _validated_launcher_lifecycle_fd(expected_target):
    """Validate the stable launcher's shared lease and pinned target."""
    names = (_LAUNCHER_ABI_ENV, _LAUNCHER_LIFECYCLE_FD_ENV,
             _LAUNCHER_TARGET_FD_ENV, _LAUNCHER_TARGET_PATH_ENV)
    values = tuple(os.environ.get(name) for name in names)
    if all(value is None for value in values):
        return None
    abi, lifecycle_raw, target_raw, target_path = values
    if abi != _LAUNCHER_ABI \
            or lifecycle_raw is None or target_raw is None \
            or not lifecycle_raw.isascii() or not lifecycle_raw.isdigit() \
            or not target_raw.isascii() or not target_raw.isdigit() \
            or target_path is None \
            or os.path.abspath(target_path) != os.path.abspath(expected_target):
        raise RuntimeError("invalid SIA stable-launcher handoff")
    try:
        lifecycle_fd = int(lifecycle_raw, 10)
        target_fd = int(target_raw, 10)
        inherited = os.fstat(lifecycle_fd)
        lock_target = os.lstat(LIFECYCLE_LOCK)
        pinned_target = os.fstat(target_fd)
        current_target = os.lstat(expected_target)
    except (OSError, ValueError) as exc:
        raise RuntimeError("invalid SIA stable-launcher handoff") from exc
    if not stat.S_ISREG(inherited.st_mode) \
            or inherited.st_uid != os.geteuid() \
            or not stat.S_ISREG(lock_target.st_mode) \
            or lock_target.st_uid != os.geteuid() \
            or (inherited.st_dev, inherited.st_ino) != \
               (lock_target.st_dev, lock_target.st_ino) \
            or not stat.S_ISREG(pinned_target.st_mode) \
            or pinned_target.st_uid != os.geteuid() \
            or not stat.S_ISREG(current_target.st_mode) \
            or current_target.st_uid != os.geteuid() \
            or (pinned_target.st_dev, pinned_target.st_ino) != \
               (current_target.st_dev, current_target.st_ino):
        raise RuntimeError("SIA stable-launcher handoff changed generation")

    flags = (os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    try:
        probe_fd = os.open(LIFECYCLE_LOCK, flags)
    except OSError as exc:
        raise RuntimeError("could not probe SIA stable-launcher lease") \
            from exc
    try:
        probe = os.fstat(probe_fd)
        if not stat.S_ISREG(probe.st_mode) \
                or probe.st_uid != os.geteuid() \
                or (probe.st_dev, probe.st_ino) != \
                   (inherited.st_dev, inherited.st_ino):
            raise RuntimeError("SIA stable-launcher lease changed")
        try:
            fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(probe_fd, fcntl.LOCK_UN)
            raise RuntimeError("SIA stable launcher holds no shared lease")
        try:
            fcntl.flock(probe_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("SIA stable launcher inherited an exclusive lease") \
                from exc
        else:
            fcntl.flock(probe_fd, fcntl.LOCK_UN)
        try:
            fcntl.flock(lifecycle_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("SIA stable-launcher lease is not shared") \
                from exc
    finally:
        os.close(probe_fd)
    return lifecycle_fd


def _installed_launcher_context():
    main = sys.modules.get("__main__")
    loaded = os.path.abspath(str(getattr(main, "__file__", "")))
    cli_public = os.path.join(HOME, ".local", "bin", "sia")
    cli_target = os.path.join(BIN, "sia-cli")
    brainstem_public = os.path.join(BIN, "sia-brainstem")
    brainstem_target = os.path.join(BIN, "sia-brainstem.py")
    for public, target in ((cli_public, cli_target),
                           (brainstem_public, brainstem_target)):
        if loaded == os.path.abspath(public) \
                or loaded == os.path.abspath(target):
            return loaded, os.path.abspath(target)
    return None


def _require_installed_launcher_handoff():
    """Reject a loaded old/public launcher before it can use new modules."""
    context = _installed_launcher_context()
    if context is None:
        return
    loaded, expected_target = context
    if loaded != expected_target:
        raise RuntimeError(
            "installed SIA launcher did not pin its runtime before import")
    if _validated_launcher_lifecycle_fd(expected_target) is not None:
        if os.path.lexists(LIFECYCLE_TOMBSTONE):
            marker = os.lstat(LIFECYCLE_TOMBSTONE)
            if not stat.S_ISREG(marker.st_mode) \
                    or marker.st_uid != os.geteuid():
                raise RuntimeError("SIA lifecycle removal marker is unsafe")
            raise RuntimeError(
                "SIA runtime was removed; reinstall before using it")
        return
    # First light deliberately enters the target without the public wrapper.
    # Its separately validated inherited descriptor must still be exclusive.
    if expected_target == os.path.abspath(os.path.join(BIN, "sia-cli")) \
            and _validated_inherited_lifecycle_fd() is not None:
        return
    raise RuntimeError("installed SIA target lacks a stable-launcher handoff")


_require_installed_launcher_handoff()


class _RestoreCoreView:
    """Resolve the owning dynamic sialib namespace without re-importing it."""

    def __getattr__(self, name):
        return globals()[name]


_RESTORE_CORE_VIEW = _RestoreCoreView()


def restore_barrier_active():
    return siarestoreadmit.restore_barrier_active(_RESTORE_CORE_VIEW)


def _require_restore_admission():
    return siarestoreadmit.require_restore_admission(_RESTORE_CORE_VIEW)


_require_restore_admission()


@contextlib.contextmanager
def _lifecycle_reader():
    """Keep runtime operations outside install/uninstall mutation windows."""
    depth = _LIFECYCLE_READER_DEPTH.get()
    if depth:
        token = _LIFECYCLE_READER_DEPTH.set(depth + 1)
        try:
            yield
        finally:
            _LIFECYCLE_READER_DEPTH.reset(token)
        return
    if _validated_inherited_lifecycle_fd() is not None:
        token = _LIFECYCLE_READER_DEPTH.set(1)
        try:
            yield
        finally:
            _LIFECYCLE_READER_DEPTH.reset(token)
        return
    parent = os.path.dirname(LIFECYCLE_LOCK)
    os.makedirs(parent, exist_ok=True)
    flags = (os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(LIFECYCLE_LOCK, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError("SIA lifecycle lease is not an owned regular file")
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_SH)
        try:
            if os.path.lexists(LIFECYCLE_TOMBSTONE):
                marker = os.lstat(LIFECYCLE_TOMBSTONE)
                if not stat.S_ISREG(marker.st_mode) \
                        or marker.st_uid != os.geteuid():
                    raise RuntimeError(
                        "SIA lifecycle removal marker is unsafe")
                raise RuntimeError(
                    "SIA runtime was removed; reinstall before using it")
            token = _LIFECYCLE_READER_DEPTH.set(1)
            try:
                yield
            finally:
                _LIFECYCLE_READER_DEPTH.reset(token)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


@contextlib.contextmanager
def _owner_lease(path, label, *, blocking=True):
    """Acquire one local regular-file flock without following symlinks."""
    with _lifecycle_reader():
        ensure_dirs()
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) \
            | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f"{label} owner lease is not a regular file")
            os.fchmod(fd, 0o600)
            operation = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            try:
                fcntl.flock(fd, operation)
            except BlockingIOError as exc:
                raise OwnerBusy(f"another {label} owner is active") from exc
            try:
                yield fd
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


@contextlib.contextmanager
def corpus_owner():
    """Serialize the transaction; remain reentrant in one Python context."""
    depth = _CORPUS_OWNER_DEPTH.get()
    if depth:
        token = _CORPUS_OWNER_DEPTH.set(depth + 1)
        try:
            yield _CORPUS_OWNER_FD.get()
        finally:
            _CORPUS_OWNER_DEPTH.reset(token)
        return
    inherited_fd = _validated_inherited_corpus_fd()
    if inherited_fd is not None:
        token = _CORPUS_OWNER_DEPTH.set(1)
        fd_token = _CORPUS_OWNER_FD.set(inherited_fd)
        try:
            yield inherited_fd
        finally:
            _CORPUS_OWNER_FD.reset(fd_token)
            _CORPUS_OWNER_DEPTH.reset(token)
        return
    with _owner_lease(
            CORPUS_OWNER_LOCK, "SIA corpus transaction") as owner_fd:
        token = _CORPUS_OWNER_DEPTH.set(1)
        fd_token = _CORPUS_OWNER_FD.set(owner_fd)
        try:
            yield owner_fd
        finally:
            _CORPUS_OWNER_FD.reset(fd_token)
            _CORPUS_OWNER_DEPTH.reset(token)


@contextlib.contextmanager
def brainstem_owner():
    """Refuse a second resident brainstem; nest in the owning context."""
    inherited = _BRAINSTEM_OWNER_FD.get()
    if inherited is not None:
        yield inherited
        return
    with _owner_lease(
            BRAINSTEM_OWNER_LOCK, "SIA brainstem", blocking=False) as owner_fd:
        token = _BRAINSTEM_OWNER_FD.set(owner_fd)
        try:
            yield owner_fd
        finally:
            _BRAINSTEM_OWNER_FD.reset(token)


MAX_THOUGHT_INBOX_ITEMS = 200
MAX_THOUGHT_INBOX_BYTES = 65_536
MAX_THOUGHT_INBOX_TEXT = 2000
THOUGHT_RECOVERY_SCHEMA = "sia-thought-recovery-v1"
THOUGHT_RECOVERY_CLAIM_SCHEMA = "sia-thought-recovery-claim-v3"
THOUGHT_LEGACY_INDEX_SCHEMA = "sia-thought-legacy-index-v1"
THOUGHT_LEGACY_SCAN_SCHEMA = "sia-thought-legacy-scan-v3"
THOUGHT_RECOVERY_DIRNAME = "thought-recovery"
THOUGHT_LEGACY_INDEX_DIRNAME = "thought-recovery-legacy-index"
THOUGHT_LEGACY_CATALOG_NAME = "thought-recovery-legacy-index.sqlite3"
THOUGHT_MIND_REPLAY_NAME = "thought-recovery-mind-replay.sqlite3"
THOUGHT_RECOVERY_CLAIM_NAME = "thought-recovery.draining.json"
THOUGHT_LEGACY_SCAN_NAME = "thought-recovery-scan.json"
THOUGHT_RECOVERY_LOCK_NAME = "thought-recovery.lock"
MAX_THOUGHT_RECOVERY_RECORDS = MAX_THOUGHT_INBOX_ITEMS
MAX_THOUGHT_RECOVERY_RECORD_BYTES = MAX_THOUGHT_INBOX_BYTES
MAX_THOUGHT_RECOVERY_BYTES = MAX_STATE_JSON_BYTES
MAX_THOUGHT_RECOVERY_SCAN_ENTRIES = 401


class ThoughtRecoveryPending(RuntimeError):
    """One bounded baseline generation committed; another remains."""


class ThoughtDirectoryGenerationChanged(ValueError):
    """The quiescent legacy directory changed around a durable cookie."""


# three bytes for the persisted `.md` suffix.
MAX_CORPUS_COMPONENT_BYTES = 255
MAX_CORPUS_LEAF_BYTES = 252
THOUGHT_ORIGINS = frozenset({"evidence", "derived", "model"})
LEGACY_MODEL_THOUGHT_KINDS = frozenset({
    "grade", "ponder", "note", "take",
})


def _canonical_thought_origin(value):
    if not isinstance(value, str) or value not in THOUGHT_ORIGINS:
        raise ValueError("thought origin must be evidence, derived, or model")
    return value


def _canonical_corpus_slug(value):
    """Return a lexical corpus slug or refuse traversal/ambiguous forms."""
    if not isinstance(value, str) or not value \
            or len(value) > MAX_THOUGHT_INBOX_TEXT:
        raise ValueError("corpus slug must be a bounded non-empty string")
    parts = value.split("/")
    if any(not re.fullmatch(r"[a-z0-9_][a-z0-9._-]*", part)
           for part in parts):
        raise ValueError("corpus slug is not canonical")
    if any(len(part.encode("utf-8")) > MAX_CORPUS_COMPONENT_BYTES
           for part in parts[:-1]) \
            or len(parts[-1].encode("utf-8")) > MAX_CORPUS_LEAF_BYTES:
        raise ValueError("corpus slug exceeds its component byte bound")
    root = os.path.abspath(CORPUS)
    target = os.path.abspath(os.path.join(root, value + ".md"))
    if os.path.commonpath((root, target)) != root:
        raise ValueError("corpus slug escapes the corpus")
    return value


def _canonical_utc_timestamp(value):
    if not isinstance(value, str):
        raise ValueError("thought timestamp must be a UTC string")
    try:
        parsed = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError("thought timestamp is invalid") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("thought timestamp is not canonical")
    return value


def _canonical_thought_inbox_item(item, *, queued):
    if not isinstance(item, dict):
        raise TypeError("thought inbox item must be an object")
    public_keys = {"kind", "text", "links", "urgent", "origin"}
    metadata_keys = {"_queue_id", "_queued_at"} if queued else set()
    if set(item) - public_keys - metadata_keys:
        raise ValueError("thought inbox item has unknown or reserved fields")
    if "kind" not in item or "text" not in item:
        raise ValueError("thought inbox item requires kind and text")
    kind = item["kind"]
    text = item["text"]
    links = item.get("links", [])
    urgent = item.get("urgent", False)
    if not isinstance(kind, str) or not kind \
            or len(kind) > MAX_THOUGHT_INBOX_TEXT \
            or sanitize_slugpart(kind) != kind:
        raise ValueError("thought kind is not canonical")
    # Newly appended unlabeled rows are deterministic by default and persist
    # that label. A pre-upgrade queued model-prose kind has stronger lexical
    # evidence, so recover it as model rather than laundering it as derived.
    default_origin = ("model" if queued and "origin" not in item
                      and kind in LEGACY_MODEL_THOUGHT_KINDS
                      else "derived")
    origin = _canonical_thought_origin(item.get("origin", default_origin))
    if not isinstance(text, str) or not text.strip() \
            or len(text) > MAX_THOUGHT_INBOX_TEXT:
        raise ValueError("thought text must be a bounded non-empty string")
    if not isinstance(links, list) \
            or len(links) > MAX_THOUGHT_INBOX_ITEMS:
        raise ValueError("thought links must be a bounded list")
    links = sorted({_canonical_corpus_slug(link) for link in links}) \
        or ["sia/cortex"]
    if not isinstance(urgent, bool):
        raise ValueError("thought urgency must be boolean")
    result = {"kind": kind, "text": inert_summary(text),
              "links": links, "urgent": urgent, "origin": origin}
    if queued:
        queue_id = item.get("_queue_id")
        if not isinstance(queue_id, str) \
                or re.fullmatch(r"[0-9a-f]{32}", queue_id) is None:
            raise ValueError("thought queue identity is invalid")
        result["_queue_id"] = queue_id
        result["_queued_at"] = _canonical_utc_timestamp(
            item.get("_queued_at"))
    return result


def _read_thought_inbox(path):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with siaqueue.regular_file_stream(fd, label="thought inbox") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_size > MAX_THOUGHT_INBOX_BYTES:
            raise ValueError("thought inbox is not a bounded regular file")
        raw = stream.read(MAX_THOUGHT_INBOX_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_mode, before.st_uid,
                before.st_size, before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_mode, after.st_uid,
                after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_THOUGHT_INBOX_BYTES:
        raise ValueError("thought inbox changed while read or exceeds its bound")
    try:
        inbox = _strict_json_loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("thought inbox is malformed") from exc
    if not isinstance(inbox, list) or len(inbox) > MAX_THOUGHT_INBOX_ITEMS:
        raise ValueError("thought inbox is not a bounded list")
    legacy_basis = None
    legacy_queued_at = None
    canonical = []
    for index, row in enumerate(inbox):
        if isinstance(row, dict):
            has_queue_id = "_queue_id" in row
            has_queued_at = "_queued_at" in row
            if has_queue_id != has_queued_at:
                raise ValueError("thought inbox metadata is incomplete")
            if not has_queue_id:
                if legacy_basis is None:
                    legacy_basis = hashlib.sha256(
                        b"sia-thought-inbox-legacy\0"
                        + str(before.st_mtime_ns).encode("ascii")
                        + b"\0" + raw).digest()
                    legacy_queued_at = time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ",
                        time.gmtime(before.st_mtime))
                row = dict(row)
                row["_queue_id"] = hashlib.sha256(
                    legacy_basis + b"\0"
                    + str(index).encode("ascii")).hexdigest()[:32]
                row["_queued_at"] = legacy_queued_at
        canonical.append(_canonical_thought_inbox_item(row, queued=True))
    return canonical


def append_thought_inbox(item):
    """Locked RMW for out-of-band generated entries from CLI workflows."""
    item = _canonical_thought_inbox_item(item, queued=False)
    item["_queue_id"] = uuid.uuid4().hex
    item["_queued_at"] = iso()
    with _owner_lease(THOUGHT_INBOX_LOCK, "thought inbox"):
        try:
            inbox = _read_thought_inbox(THOUGHT_INBOX_PATH)
        except FileNotFoundError:
            inbox = []
        if len(inbox) >= MAX_THOUGHT_INBOX_ITEMS:
            raise ValueError("thought inbox reached its item bound")
        inbox.append(item)
        encoded = json.dumps(inbox, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_THOUGHT_INBOX_BYTES:
            raise ValueError("thought inbox reached its byte bound")
        atomic_write(THOUGHT_INBOX_PATH, encoded)
        os.chmod(THOUGHT_INBOX_PATH, 0o600)
    return {"queue_id": item["_queue_id"], "queued_at": item["_queued_at"]}


def _thought_inbox_claim_path():
    stem, suffix = os.path.splitext(THOUGHT_INBOX_PATH)
    return stem + ".draining" + suffix


def acknowledge_thought_inbox(claim_path):
    expected = _thought_inbox_claim_path()
    if os.path.abspath(claim_path) != os.path.abspath(expected):
        raise ValueError("unexpected thought inbox claim path")
    with _owner_lease(THOUGHT_INBOX_LOCK, "thought inbox"):
        os.unlink(claim_path)
        dfd = os.open(os.path.dirname(claim_path) or ".",
                      os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)


def drain_thought_inbox(defer_ack=False):
    """Claim one durable CLI generated-entry batch until acknowledgment."""
    claim_path = _thought_inbox_claim_path()
    with _owner_lease(THOUGHT_INBOX_LOCK, "thought inbox"):
        if not os.path.lexists(claim_path) \
                and os.path.lexists(THOUGHT_INBOX_PATH):
            os.replace(THOUGHT_INBOX_PATH, claim_path)
            dfd = os.open(os.path.dirname(claim_path) or ".",
                          os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        if not os.path.lexists(claim_path):
            return ([], None) if defer_ack else []
        inbox = _read_thought_inbox(claim_path)
    if not defer_ack:
        acknowledge_thought_inbox(claim_path)
        return inbox
    return inbox, claim_path

def log(msg):
    line = f"{iso()} {msg}"
    print(line, flush=True)

def strip_controls(value):
    """Remove terminal/format controls while preserving ordinary whitespace."""
    out = []
    for char in str(value):
        if char in "\n\r\t":
            out.append(char)
            continue
        if unicodedata.category(char) not in {"Cc", "Cf", "Cs"}:
            out.append(char)
    return "".join(out)

def inert_summary(s):
    s = re.sub(r"\s+", " ", strip_controls(s)).strip()
    # Keep all externally sourced prose inert inside Markdown. SIA adds its
    # own corpus links structurally after this boundary; evidence text cannot
    # mint HTML, images, ordinary Markdown links, code, or wiki edges.
    s = (s.replace("<", "‹").replace(">", "›")
         .replace("[", "⟦").replace("]", "⟧")
         .replace("|", "¦").replace("`", "ˋ")
         .replace("*", "✱").replace("\t", " "))
    return s


def bounded_model_output(value, limit=MAX_THOUGHT_INBOX_BYTES):
    """Bound model prose by UTF-8 bytes while preserving readable lines."""
    value = unicodedata.normalize("NFC", str(value))
    value = strip_controls(value).replace("\r\n", "\n").replace("\r", "\n")
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    marker = "\n[model output truncated at the persistence boundary]"
    room = max(0, limit - len(marker.encode("utf-8")))
    return encoded[:room].decode("utf-8", errors="ignore") + marker


def inert_model_block(value):
    """Preserve model-output line structure without active markup syntax."""
    value = bounded_model_output(value)
    return (value.replace("&", "＆").replace("<", "‹").replace(">", "›")
            .replace("[", "⟦").replace("]", "⟧")
            .replace("|", "¦").replace("`", "ˋ")
            .replace("*", "✱").replace("_", "﹍")
            .replace("~", "∼").replace("#", "＃"))


def clip(s, n=110):
    s = inert_summary(s)
    return s[: n - 1] + "…" if len(s) > n else s


# ---- ingest redaction: metadata can still carry secrets (journal lines,
# commit subjects, notification summaries). Secret-shaped spans are dropped
# AT THE SENSE BOUNDARY — before anything reaches the corpus or git — and
# every redaction is counted so SOURCE HEALTH can say "sense X omitted N
# spans" instead of storing them forever. Hex digests are NOT redacted:
# chain hashes are evidence, and they are already public in the ledgers.
REDACT_PATTERNS = [
    re.compile(r"-----BEGIN[ A-Z]*-----.*?(?:-----END[ A-Z]*-----|$)", re.S),
    re.compile(r"\beyJ[A-Za-z0-9_-]{14,}\.?[A-Za-z0-9._-]*"),      # JWT
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),                    # github
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),                         # api keys
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),                  # slack
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                            # aws
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{15,}=*", re.I),
    re.compile(r"\b(?:password|passwd|secret|api[_-]?key|token)\s*[=:]\s*\S+",
               re.I),
    re.compile(r"~?/[^\s]*\.ssh/[^\s]*"),
    re.compile(r"\b[A-Za-z0-9+/]{40,}={1,2}(?=\s|$)"),              # base64
]
REDACTIONS = {}     # organ -> spans dropped this process (pulse exports it)

def _redaction_projection(text):
    out, n = strip_controls(text), 0
    for pat in REDACT_PATTERNS:
        out, k = pat.subn("⟦redacted⟧", out)
        n += k
    return out, n


def redact(text, organ="?"):
    out, n = _redaction_projection(text)
    if n:
        REDACTIONS[organ] = REDACTIONS.get(organ, 0) + n
    return out


def _validated_event_values(field, values, canonicalize):
    """Normalize one Event collection and refuse excess unique meaning."""
    normalized = set()
    for value in values:
        candidate = canonicalize(value)
        if candidate in normalized:
            continue
        if len(normalized) >= MAX_LEDGER_PENDING_RECORDS:
            raise ValueError(
                f"event {field} exceed their unique-value bound")
        normalized.add(candidate)
    return normalized


def _canonical_event_tag(value):
    tag = sanitize_slugpart(str(value))
    if len(tag) > MAX_SOURCE_NAME_CHARS:
        raise ValueError("event tag exceeds its canonical bound")
    return tag


class Event:
    """One observed happening. links are corpus slugs (no .md).
    Summaries pass the redaction boundary at construction — fail closed."""
    __slots__ = ("organ", "ts", "kind", "summary", "links", "tags",
                 "occurrence")

    def __init__(self, organ, ts, kind, summary, links=(), tags=(),
                 occurrence=""):
        raw_organ = str(organ)
        raw_kind = str(kind)
        if len(raw_organ) > MAX_CONFIG_TEXT_CHARS \
                or len(raw_kind) > MAX_CONFIG_TEXT_CHARS:
            raise ValueError("event organ or kind exceeds its input bound")
        self.organ = sanitize_slugpart(raw_organ)
        self.ts = ts                      # aware datetime UTC
        self.kind = sanitize_slugpart(raw_kind)
        if len(self.organ) > MAX_SOURCE_NAME_CHARS \
                or len(self.kind) > MAX_SOURCE_NAME_CHARS:
            raise ValueError("event organ or kind exceeds its canonical bound")
        self.summary = clip(redact(summary, self.organ),
                            MAX_THOUGHT_INBOX_TEXT)
        self.links = _validated_event_values(
            "links", links,
            lambda link: _canonical_corpus_slug(str(link)))
        self.tags = _validated_event_values(
            "tags", tags, _canonical_event_tag)
        if not isinstance(occurrence, str):
            raise ValueError("event occurrence identity is invalid")
        occurrence = strip_controls(occurrence)
        if len(occurrence.encode("utf-8")) > MAX_THOUGHT_INBOX_TEXT:
            raise ValueError("event occurrence identity is invalid")
        self.occurrence = occurrence


def event_memory_identity(event):
    """Bind policy replay state to one exact normalized event observation."""
    if not isinstance(event, Event):
        raise TypeError("event replay identity needs an Event")
    if event.occurrence:
        # A source-native occurrence key survives daemon retries even when
        # the ingestion clock crosses a second (or midnight). The rendered
        # bullet remains independently conflict-checked against this ID.
        basis = {"organ": event.organ, "occurrence": event.occurrence}
    else:
        basis = {
            "organ": event.organ, "ts": iso(event.ts), "kind": event.kind,
            "summary": event.summary, "links": sorted(event.links),
            "tags": sorted(event.tags),
        }
    return hashlib.sha256(json.dumps(
        basis, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()


def event_semantic_identity(event):
    """Bind count, safety, graph, and rendered meaning for one occurrence."""
    if not isinstance(event, Event):
        raise TypeError("event semantic identity needs an Event")
    basis = {"organ": event.organ, "kind": event.kind,
             "summary": event.summary, "links": sorted(event.links),
             "tags": sorted(event.tags)}
    return hashlib.sha256(json.dumps(
        basis, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()


def _dedupe_event_batch(events):
    """Admit one exact meaning for each source occurrence per pulse."""
    unique = []
    seen = {}
    for event in events:
        event_id = event_memory_identity(event)
        semantic_id = event_semantic_identity(event)
        prior = seen.get(event_id)
        if prior is not None:
            if prior != semantic_id:
                raise ValueError("event batch occurrence identity conflicts")
            continue
        seen[event_id] = semantic_id
        unique.append(event)
    return unique


def _event_replay_record(event):
    """Canonical memo representation of one exact sensed observation."""
    if not isinstance(event, Event):
        raise TypeError("event replay record needs an Event")
    if not isinstance(event.ts, datetime.datetime) \
            or event.ts.tzinfo is None:
        raise ValueError("event replay timestamp must be timezone-aware")
    record = {
        "organ": event.organ,
        "ts": iso(event.ts.astimezone(datetime.timezone.utc)),
        "kind": event.kind,
        "summary": event.summary,
        "links": sorted(event.links),
        "tags": sorted(event.tags),
        "occurrence": event.occurrence,
        "event_id": event_memory_identity(event),
        "semantic_id": event_semantic_identity(event),
    }
    # Round-trip validation keeps the write and recovery parsers identical.
    _event_from_replay_record(record)
    return record


def _event_from_replay_record(record):
    """Validate and reconstruct an exact memo-bound sensed observation."""
    required = {"organ", "ts", "kind", "summary", "links", "tags",
                "occurrence", "event_id", "semantic_id"}
    if not isinstance(record, dict) or set(record) != required \
            or not all(isinstance(record.get(key), str) for key in (
                "organ", "ts", "kind", "summary", "occurrence",
                "event_id", "semantic_id")) \
            or re.fullmatch(r"[0-9a-f]{64}", record["event_id"]) is None \
            or re.fullmatch(r"[0-9a-f]{64}",
                            record["semantic_id"]) is None:
        raise ValueError("event replay record is invalid")
    for field in ("links", "tags"):
        values = record.get(field)
        if not isinstance(values, list) \
                or len(values) > MAX_LEDGER_PENDING_RECORDS \
                or values != sorted(set(values)) \
                or any(not isinstance(value, str) for value in values):
            raise ValueError("event replay record is invalid")
    _canonical_utc_timestamp(record["ts"])
    timestamp = datetime.datetime.strptime(
        record["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    event = Event(record["organ"], timestamp, record["kind"],
                  record["summary"], record["links"], record["tags"],
                  occurrence=record["occurrence"])
    if event.organ != record["organ"] or event.kind != record["kind"] \
            or event.summary != record["summary"] \
            or sorted(event.links) != record["links"] \
            or sorted(event.tags) != record["tags"] \
            or event.occurrence != record["occurrence"] \
            or event_memory_identity(event) != record["event_id"] \
            or event_semantic_identity(event) != record["semantic_id"]:
        raise ValueError("event replay record is not canonical")
    return event


def _event_replay_batch_bytes(events):
    """Return the canonical JSON-list size for exact replay records."""
    encoded = [json.dumps(
        _event_replay_record(event), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8") for event in events]
    return 2 + sum(len(record) for record in encoded) \
        + max(0, len(encoded) - 1)


# ---------------------------------------------------------------- cursors

CURSORS_PATH = os.path.join(STATE, "cursors.json")

def load_cursors():
    return read_state_json(CURSORS_PATH, {}, "evidence cursor")

def save_cursors(c):
    encoded = json.dumps(c, indent=1, sort_keys=True, allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_STATE_JSON_BYTES:
        raise ValueError("evidence cursor state exceeds its byte bound")
    atomic_write(CURSORS_PATH, encoded)


MAX_SOURCE_TAIL_BYTES = 262_144
SOURCE_CURSOR_GUARD_BYTES = 65_536
MAX_SOURCE_TAIL_RECORDS = 1024
SOURCE_CURSOR_VERSION = 2
SOURCE_RECORD_REFUSALS_KEY = "__sia_source_record_refusals"
SOURCE_ENTRY_REFUSALS_KEY = "__sia_source_entry_refusals"


def _source_cursor_names(key):
    return {
        "version": f"{key}.cursor_v",
        "generation": f"{key}.generation",
        "offset": f"{key}.offset",
        "device": f"{key}.device",
        "inode": f"{key}.inode",
        "head_bytes": f"{key}.head_bytes",
        "head": f"{key}.head_sha256",
        "guard": f"{key}.prefix_sha256",
        "skip": f"{key}.overbound_skip",
    }


def _decode_lf_records(data, label):
    """Decode complete physical records separated only by literal LF."""
    if not data:
        return []
    if not data.endswith(b"\n"):
        raise ValueError(f"{label} returned an incomplete physical record")
    try:
        return [record.decode("utf-8") for record in data[:-1].split(b"\n")]
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} contains invalid UTF-8") from exc


def _source_skip_receipt(previous, fragment):
    """Extend a bounded chunk-chain receipt for one over-bound line."""
    if previous is None:
        seed = b"sia-source-record-skip-v1\0"
    else:
        if not isinstance(previous, str) \
                or re.fullmatch(r"[0-9a-f]{64}", previous) is None:
            raise ValueError("source record skip receipt is invalid")
        seed = bytes.fromhex(previous)
    return hashlib.sha256(seed + fragment).hexdigest()


def _open_source_nofollow(path, leaf_flags):
    """Open an absolute source path without following any path component."""
    absolute = os.path.abspath(path)
    parts = [part for part in absolute.split(os.sep) if part]
    directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                       | getattr(os, "O_NOFOLLOW", 0)
                       | getattr(os, "O_DIRECTORY", 0))
    descriptor = os.open(os.sep, directory_flags)
    try:
        for part in parts[:-1]:
            next_descriptor = os.open(
                part, directory_flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        if not parts:
            return descriptor
        result = os.open(
            parts[-1], leaf_flags | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0), dir_fd=descriptor)
    finally:
        if parts:
            os.close(descriptor)
    return result


def _source_path_identity(path, leaf_flags):
    descriptor = _open_source_nofollow(path, leaf_flags)
    try:
        return os.fstat(descriptor)
    finally:
        os.close(descriptor)


def _cursor_digest(stream, start, length):
    stream.seek(start)
    value = stream.read(length)
    if len(value) != length:
        raise RuntimeError("source changed while fingerprinting")
    return hashlib.sha256(value).hexdigest()


def _cursor_fingerprints(stream, size, offset, head_bytes):
    head_bytes = min(head_bytes, size, SOURCE_CURSOR_GUARD_BYTES)
    guard_start = max(0, offset - SOURCE_CURSOR_GUARD_BYTES)
    return (
        _cursor_digest(stream, 0, head_bytes),
        _cursor_digest(stream, guard_start, offset - guard_start),
    )


def _stable_tail_chunk(path, cursors, key, max_read, *, source_fd=None):
    """Return one bounded complete-line chunk from a stable file generation.

    Fixed head and cursor-boundary fingerprints catch rotations, truncations,
    and bounded-window rewrites without rescanning an ever-growing prefix.
    Exact occurrence IDs absorb conservative legacy/rotation replay. This is
    deliberately not a claim to detect an in-place rewrite wholly outside
    both retained fingerprint windows.
    """
    if isinstance(max_read, bool) or not isinstance(max_read, int) \
            or max_read <= 0 or max_read > MAX_SOURCE_TAIL_BYTES:
        raise ValueError(f"source read bound {key} is invalid")
    names = _source_cursor_names(key)
    ordinal = cursors.get(key)
    metadata_present = {
        name for name in names.values() if name in cursors}
    version_present = names["version"] in cursors
    version = cursors.get(names["version"])
    # A missing cursor is a legitimate first-run baseline, and the historical
    # ordinal-only shape is replayed once as a conservative migration.  Any
    # other partial or unknown-version shape is damage: treating it as a fresh
    # baseline would silently skip the source prefix it may have represented.
    if ordinal is None:
        if key in cursors or metadata_present:
            raise ValueError(f"line cursor metadata {key} is invalid")
    elif version_present:
        if isinstance(version, bool) or not isinstance(version, int) \
                or version != SOURCE_CURSOR_VERSION:
            raise ValueError(f"line cursor metadata {key} is invalid")
    elif metadata_present:
        raise ValueError(f"line cursor metadata {key} is invalid")
    generation = cursors.get(names["generation"], 0)
    if ordinal is not None and (isinstance(ordinal, bool)
                                or not isinstance(ordinal, int)
                                or ordinal < 0):
        raise ValueError(f"line cursor {key} is invalid")
    if isinstance(generation, bool) or not isinstance(generation, int) \
            or generation < 0:
        raise ValueError(f"line cursor generation {key} is invalid")
    skip_state = cursors.get(names["skip"])
    if skip_state is not None:
        if not isinstance(skip_state, dict) \
                or skip_state.get("schema") != "sia-source-record-skip-v1" \
                or any(isinstance(skip_state.get(field), bool)
                       or not isinstance(skip_state.get(field), int)
                       or skip_state.get(field) < 0
                       for field in ("generation", "start", "bytes")) \
                or not isinstance(skip_state.get("receipt"), str) \
                or re.fullmatch(
                    r"[0-9a-f]{64}", skip_state["receipt"]) is None:
            raise ValueError(f"line cursor skip state {key} is invalid")
    for digest_name in (names["head"], names["guard"]):
        digest = cursors.get(digest_name)
        if digest is not None and (not isinstance(digest, str)
                                   or re.fullmatch(
                                       r"[0-9a-f]{64}", digest) is None):
            raise ValueError(f"line cursor digest {key} is invalid")

    flags = os.O_RDONLY
    if source_fd is None:
        try:
            fd = _open_source_nofollow(path, flags)
        except FileNotFoundError:
            return generation, ordinal or 0, b""
    else:
        if isinstance(source_fd, bool) or not isinstance(source_fd, int) \
                or source_fd < 0:
            raise ValueError(f"line source descriptor {key} is invalid")
        fd = os.open(
            _chain_descriptor_path(source_fd),
            flags | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0))
    updates = {}
    record_refusal = None
    clear_skip = False
    with siaqueue.regular_file_stream(fd, label=f"line source {key}") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"line source {key} is not a regular file")
        size = before.st_size
        current_schema = version_present
        if current_schema:
            values = {
                field: cursors.get(names[field])
                for field in ("offset", "device", "inode", "head_bytes")}
            if any(isinstance(value, bool) or not isinstance(value, int)
                   or value < 0 for value in values.values()) \
                    or cursors.get(names["head"]) is None \
                    or cursors.get(names["guard"]) is None \
                    or ordinal is None:
                raise ValueError(f"line cursor metadata {key} is invalid")
            offset = values["offset"]
            head_bytes = values["head_bytes"]
            observed_head, observed_guard = _cursor_fingerprints(
                stream, size, min(offset, size), head_bytes)
            replaced = (
                values["device"] != before.st_dev
                or values["inode"] != before.st_ino
                or offset > size
                or observed_head != cursors[names["head"]]
                or observed_guard != cursors[names["guard"]])
            if replaced:
                generation += 1
                ordinal, offset, head_bytes = 0, 0, 0
                skip_state = None
                clear_skip = True
        elif ordinal is not None:
            # The v1 cursor requires whole-prefix hashing. Migrate safely by
            # starting a new replay generation instead of performing that
            # unbounded work once more.
            generation += 1
            ordinal, offset, head_bytes = 0, 0, 0
            skip_state = None
            clear_skip = True
        elif os.environ.get("SIA_BACKFILL") == "1":
            ordinal, offset, head_bytes = 0, 0, 0
        else:
            # Establish a baseline using only the bounded tail. A torn final
            # record remains pending and will be emitted once its newline is
            # durable.
            tail_size = min(size, max_read)
            stream.seek(size - tail_size)
            tail = stream.read(tail_size)
            if len(tail) != tail_size:
                raise RuntimeError(f"line source {key} changed while baselining")
            if not tail or tail.endswith(b"\n"):
                offset = size
            else:
                newline = tail.rfind(b"\n")
                if newline < 0 and size > max_read:
                    # Establish a bounded forward skip from a known record
                    # boundary. This rare baseline path may replay older
                    # complete lines, but cannot silently enter the middle of
                    # an oversized terminal record.
                    ordinal, offset, head_bytes = 0, 0, 0
                    skip_state = None
                else:
                    offset = (0 if newline < 0
                              else size - tail_size + newline + 1)
            tail_start = size - tail_size
            ordinal = tail[:max(0, offset - tail_start)].count(b"\n")
            head_bytes = min(offset, SOURCE_CURSOR_GUARD_BYTES)
            head_digest, guard_digest = _cursor_fingerprints(
                stream, size, offset, head_bytes)
            updates = {
                key: ordinal, names["version"]: SOURCE_CURSOR_VERSION,
                names["generation"]: generation,
                names["offset"]: offset, names["device"]: before.st_dev,
                names["inode"]: before.st_ino,
                names["head_bytes"]: head_bytes,
                names["head"]: head_digest,
                names["guard"]: guard_digest,
            }
            data = b""
        if skip_state is not None \
                and skip_state["generation"] != generation:
            raise ValueError(f"line cursor skip generation {key} is invalid")
        if not updates:
            stream.seek(offset)
            candidate = stream.read(max_read)
            next_skip = skip_state
            if skip_state is not None:
                newline = candidate.find(b"\n")
                if newline < 0:
                    # Retain the final unterminated fragment at the cursor;
                    # it is not a complete source-native record yet.
                    consumed = (len(candidate)
                                if offset + len(candidate) < size else 0)
                    records = 0
                    fragment = candidate[:consumed]
                    if fragment:
                        next_skip = dict(skip_state)
                        next_skip["bytes"] += len(fragment)
                        next_skip["receipt"] = _source_skip_receipt(
                            skip_state["receipt"], fragment)
                else:
                    consumed = newline + 1
                    records = 1
                    fragment = candidate[:consumed]
                    receipt = _source_skip_receipt(
                        skip_state["receipt"], fragment)
                    record_refusal = {
                        "schema": "sia-source-record-refusal-v1",
                        "key": key, "generation": generation,
                        "ordinal": ordinal,
                        "start": skip_state["start"],
                        "end": offset + consumed,
                        "bytes": skip_state["bytes"] + len(fragment),
                        "reason": "over-bound-record",
                        "chunk_chain_sha256": receipt,
                    }
                    next_skip = None
                    clear_skip = True
                data = b""
            else:
                consumed = 0
                records = 0
                while records < MAX_SOURCE_TAIL_RECORDS:
                    newline = candidate.find(b"\n", consumed)
                    if newline < 0:
                        break
                    consumed = newline + 1
                    records += 1
                if consumed == 0 and len(candidate) == max_read \
                        and offset + len(candidate) < size:
                    # Consume one bounded fragment into a durable skip state.
                    # The cursor has not passed the record until a later call
                    # observes its newline and signs the exact refusal.
                    consumed = len(candidate)
                    next_skip = {
                        "schema": "sia-source-record-skip-v1",
                        "generation": generation, "start": offset,
                        "bytes": consumed,
                        "receipt": _source_skip_receipt(None, candidate),
                    }
                    data = b""
                else:
                    data = candidate[:consumed]
            next_offset = offset + consumed
            next_ordinal = ordinal + records
            if head_bytes == 0 and next_offset:
                head_bytes = min(next_offset, SOURCE_CURSOR_GUARD_BYTES)
            head_digest, guard_digest = _cursor_fingerprints(
                stream, size, next_offset, head_bytes)
            updates = {
                key: next_ordinal,
                names["version"]: SOURCE_CURSOR_VERSION,
                names["generation"]: generation,
                names["offset"]: next_offset,
                names["device"]: before.st_dev,
                names["inode"]: before.st_ino,
                names["head_bytes"]: head_bytes,
                names["head"]: head_digest,
                names["guard"]: guard_digest,
            }
            if next_skip is not None:
                updates[names["skip"]] = next_skip
        after = os.fstat(stream.fileno())
        target = None
        if source_fd is None:
            try:
                target = _source_path_identity(path, flags)
            except FileNotFoundError as exc:
                raise RuntimeError(
                    f"line source {key} changed while cursoring") from exc
    observed = _file_generation(before)
    finished = _file_generation(after)
    if observed != finished or target is not None \
            and _file_generation(target) != finished:
        raise RuntimeError(f"line source {key} changed while cursoring")
    start_ordinal = updates[key] - data.count(b"\n")
    cursors.update(updates)
    if clear_skip:
        cursors.pop(names["skip"], None)
    if record_refusal is not None:
        pending = cursors.setdefault(SOURCE_RECORD_REFUSALS_KEY, [])
        if not isinstance(pending, list) \
                or len(pending) >= MAX_LEDGER_PENDING_RECORDS:
            raise ValueError("source record refusal state exceeds its bound")
        pending.append(record_refusal)
    return generation, start_ordinal, data


def tail_line_records(
        path, cursors, key, refusal_validator=None, *, source_fd=None):
    """Return valid physical rows, stopping after one exactly refused row.

    UTF-8 and optional source-native semantic validation happen one physical
    record at a time.  A bad row advances only through its own LF boundary and
    installs a digest/ordinal-bound refusal in the isolated cursor trial; the
    pulse signs that refusal before publishing the cursor.
    """
    names = _source_cursor_names(key)
    affected = [key, *names.values(), SOURCE_RECORD_REFUSALS_KEY]
    missing = object()
    prior = {name: (copy.deepcopy(cursors[name])
                    if name in cursors else missing)
             for name in affected}
    try:
        generation, ordinal, data = _stable_tail_chunk(
            path, cursors, key, MAX_SOURCE_TAIL_BYTES,
            source_fd=source_fd)
        if data and not data.endswith(b"\n"):
            raise ValueError(
                f"line source {key} returned an incomplete physical record")
        lines = []
        consumed = 0
        refused = None
        physical = data[:-1].split(b"\n") if data else []
        for index, raw_line in enumerate(physical):
            encoded_record = raw_line + b"\n"
            try:
                line = raw_line.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                reason = "invalid-utf8-record"
            else:
                reason = (None if refusal_validator is None
                          else refusal_validator(line))
                if reason is not None and reason not in {
                        "malformed-json-record", "non-object-json-record",
                        "missing-json-field",
                        "non-text-json-field", "invalid-utf8-json-field",
                        "over-bound-json-field"}:
                    raise ValueError(
                        f"line source {key} validator returned a bad reason")
            consumed += len(encoded_record)
            if reason is None:
                lines.append(line)
                continue
            refused = (index, encoded_record, consumed, reason)
            break
        if refused is not None:
            index, encoded_record, prefix_bytes, reason = refused
            # The first read may have advanced through a valid suffix. Replay
            # the same stable generation from the exact prior cursor using a
            # byte ceiling ending at the refused LF, so later rows remain due.
            for name, value in prior.items():
                if value is missing:
                    cursors.pop(name, None)
                else:
                    cursors[name] = value
            replay_generation, replay_ordinal, replay = _stable_tail_chunk(
                path, cursors, key, prefix_bytes, source_fd=source_fd)
            if replay_generation != generation or replay_ordinal != ordinal \
                    or replay != data[:prefix_bytes]:
                raise RuntimeError(
                    f"line source {key} changed while binding a refusal")
            names = _source_cursor_names(key)
            end = cursors[names["offset"]]
            row = {
                "schema": "sia-source-record-refusal-v1",
                "key": key, "generation": generation,
                "ordinal": ordinal + index,
                "start": end - len(encoded_record), "end": end,
                "bytes": len(encoded_record), "reason": reason,
                "chunk_chain_sha256": _source_skip_receipt(
                    None, encoded_record),
            }
            pending = cursors.setdefault(SOURCE_RECORD_REFUSALS_KEY, [])
            if not isinstance(pending, list) \
                    or len(pending) >= MAX_LEDGER_PENDING_RECORDS:
                raise ValueError(
                    "source record refusal state exceeds its bound")
            pending.append(row)
    except Exception:
        for name, value in prior.items():
            if value is missing:
                cursors.pop(name, None)
            else:
                cursors[name] = value
        raise
    return [(generation, ordinal + index, line)
            for index, line in enumerate(lines)]


def tail_lines(path, cursors, key, *, source_fd=None):
    return [line for _generation, _ordinal, line in tail_line_records(
        path, cursors, key, source_fd=source_fd)]


def tail_bytes(path, cursors, key, max_read=MAX_SOURCE_TAIL_BYTES):
    """Tail one bounded complete-line byte chunk from a stable generation."""
    _generation, _ordinal, data = _stable_tail_chunk(
        path, cursors, key, max_read)
    return data


# Snapshot sources are bounded independently from append-only line sources.
# Directory pages resume from durable cookies; per-entity state beyond this
# cap receives an explicit refusal, and partial pages never prove deletion.
MAX_SOURCE_SCAN_ENTRIES = MAX_SOURCE_TAIL_RECORDS


def _source_entity_token(value, namespace):
    """Return a collision-safe corpus token for a source-native identifier.

    Lower-case ASCII letters, digits, dots, and hyphens retain their readable
    spelling.  Every other UTF-8 byte uses an underscore escape; underscore
    itself is therefore never ambiguous with an escape.  Values whose exact
    reversible form exceeds the corpus bound use a reserved ``_h`` digest
    form.  In particular, lossy slug pairs such as ``a+b`` and ``a-b`` cannot
    share a cursor or occurrence identity.
    """
    raw = str(value)
    raw_bytes = os.fsencode(raw)
    encoded = []
    for byte in raw_bytes:
        if (ord("a") <= byte <= ord("z")) \
                or (ord("0") <= byte <= ord("9")) \
                or byte in (ord("."), ord("-")):
            encoded.append(chr(byte))
        else:
            encoded.append(f"_{byte:02x}")
    token = "".join(encoded) or "_e"
    if token[0] in ".-":
        token = f"_{ord(token[0]):02x}" + token[1:]
    if len(token) <= MAX_SOURCE_NAME_CHARS \
            and len(token.encode("utf-8")) <= MAX_CORPUS_LEAF_BYTES:
        return token
    prefix = _source_entity_token(namespace, "namespace")
    return prefix + "_h" + hashlib.sha256(raw_bytes).hexdigest()


def _source_entity_token_is_canonical(value, namespace):
    """Whether *value* is in the exact image of `_source_entity_token`."""
    if not isinstance(value, str) or not value \
            or len(value) > MAX_SOURCE_NAME_CHARS:
        return False
    try:
        if len(value.encode("utf-8")) > MAX_CORPUS_LEAF_BYTES:
            return False
    except UnicodeError:
        return False
    if value == "_e":
        return True
    hash_prefix = _source_entity_token(namespace, "namespace") + "_h"
    if value.startswith(hash_prefix) and re.fullmatch(
            r"[0-9a-f]{64}", value[len(hash_prefix):]) is not None:
        return True

    index = 0
    while index < len(value):
        character = value[index]
        if character == "_":
            encoded = value[index + 1:index + 3]
            if len(encoded) != 2 \
                    or re.fullmatch(r"[0-9a-f]{2}", encoded) is None:
                return False
            byte = int(encoded, 16)
            ordinarily_literal = (
                ord("a") <= byte <= ord("z")
                or ord("0") <= byte <= ord("9")
                or byte in (ord("."), ord("-")))
            if ordinarily_literal \
                    and not (index == 0 and byte in (
                        ord("."), ord("-"))):
                return False
            index += 3
            continue
        if not ("a" <= character <= "z"
                or "0" <= character <= "9"
                or character in ".-") \
                or index == 0 and character in ".-":
            return False
        index += 1
    return True


def _bounded_source_state(cursors, key, namespace, *, value_validator=None,
                          value_normalizer=None,
                          legacy_key_normalizer=None):
    """Load a bounded map, resolving only a unique higher-priority alias."""
    present = key in cursors
    raw = cursors.get(key)
    tagged = False
    if not present:
        entries = {}
    elif isinstance(raw, list) and len(raw) == 2 \
            and raw[0] == "sia-source-entity-state-v1" \
            and isinstance(raw[1], dict):
        entries = raw[1]
        tagged = True
    elif isinstance(raw, dict):
        # Pre-schema maps already persisted lossy canonical tokens. Preserve
        # each valid key exactly for a one-time conservative migration; the
        # next complete source snapshot retires stale legacy identities.
        entries = raw
    else:
        raise ValueError(f"source cursor {key} is invalid")
    candidates = []
    truncated = len(entries) > MAX_SOURCE_SCAN_ENTRIES
    for source_key, value in entries.items():
        if len(candidates) >= MAX_SOURCE_SCAN_ENTRIES:
            truncated = True
            break
        try:
            canonical_key = isinstance(source_key, str) \
                and re.fullmatch(
                    r"[a-z0-9_][a-z0-9._-]*", source_key) is not None \
                and len(source_key) <= MAX_SOURCE_NAME_CHARS \
                and len(source_key.encode("utf-8")) \
                <= MAX_CORPUS_LEAF_BYTES
            priority = 0
            if legacy_key_normalizer is not None:
                normalized_key = legacy_key_normalizer(
                    source_key, value, tagged)
                if not isinstance(normalized_key, tuple) \
                        or len(normalized_key) != 2 \
                        or isinstance(normalized_key[1], bool) \
                        or not isinstance(normalized_key[1], int) \
                        or normalized_key[1] < 0:
                    raise ValueError
                token, priority = normalized_key
            elif tagged and not canonical_key:
                raise ValueError
            elif not canonical_key:
                token = _source_entity_token(source_key, namespace)
            else:
                token = source_key
            if not isinstance(token, str) \
                    or re.fullmatch(
                        r"[a-z0-9_][a-z0-9._-]*", token) is None \
                    or len(token) > MAX_SOURCE_NAME_CHARS \
                    or len(token.encode("utf-8")) > MAX_CORPUS_LEAF_BYTES:
                raise ValueError
            normalized_value = value_normalizer(value) \
                if value_normalizer is not None else value
            if value_validator is not None \
                    and not value_validator(normalized_value):
                raise ValueError
        except (TypeError, UnicodeError, ValueError):
            raise ValueError(f"source cursor {key} is invalid") from None
        candidates.append((token, priority, normalized_value))

    grouped = {}
    for token, priority, normalized_value in candidates:
        grouped.setdefault(token, []).append((priority, normalized_value))
    state = {}
    for token, rows in grouped.items():
        highest = max(priority for priority, _value in rows)
        winners = [value for priority, value in rows
                   if priority == highest]
        if len(winners) != 1:
            raise ValueError(f"source cursor {key} is invalid")
        state[token] = winners[0]
    # A tagged list is structurally disjoint from every legacy map, so a pair
    # of unlucky source IDs cannot masquerade as the cursor wrapper itself.
    cursors[key] = ["sia-source-entity-state-v1", state]
    return state, truncated


def _bounded_seen_names(value):
    """Accept a legacy snapshot without expanding an unbounded cursor list."""
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("source snapshot cursor is invalid")
    names = []
    for name in value:
        if len(names) >= MAX_SOURCE_SCAN_ENTRIES:
            break
        if isinstance(name, str):
            names.append(name)
    return names


def _stable_bounded_source_tail(path, max_bytes=None):
    """Read only the bounded, complete-line tail of a stable regular file."""
    if max_bytes is None:
        max_bytes = MAX_SOURCE_TAIL_BYTES
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) \
            or max_bytes <= 0 or max_bytes > MAX_SOURCE_TAIL_BYTES:
        raise ValueError("source snapshot byte bound is invalid")
    flags = os.O_RDONLY
    try:
        fd = _open_source_nofollow(path, flags)
    except FileNotFoundError:
        return b"", False
    with siaqueue.regular_file_stream(fd, label="snapshot source") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("snapshot source is not a regular file")
        truncated = before.st_size > max_bytes
        start = max(0, before.st_size - max_bytes)
        stream.seek(start)
        data = stream.read(max_bytes)
        if len(data) != min(before.st_size, max_bytes):
            raise RuntimeError("snapshot source changed while reading")
        after = os.fstat(stream.fileno())
        try:
            target = _source_path_identity(path, flags)
        except FileNotFoundError as exc:
            raise RuntimeError("snapshot source changed while reading") \
                from exc
    observed = _file_generation(before)
    finished = _file_generation(after)
    if observed != finished or _file_generation(target) != finished:
        raise RuntimeError("snapshot source changed while reading")
    if truncated:
        newline = data.find(b"\n")
        data = b"" if newline < 0 else data[newline + 1:]
    if data and not data.endswith(b"\n"):
        newline = data.rfind(b"\n")
        data = b"" if newline < 0 else data[:newline + 1]
    return data, truncated


def _read_bounded_source_json(path, label):
    """Read one stable regular source record within the source byte budget."""
    flags = os.O_RDONLY
    fd = _open_source_nofollow(path, flags)
    with siaqueue.regular_file_stream(fd, label=label) as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_size > MAX_SOURCE_TAIL_BYTES:
            raise ValueError(f"{label} is not a bounded regular file")
        raw = stream.read(MAX_SOURCE_TAIL_BYTES)
        if len(raw) != before.st_size:
            raise RuntimeError(f"{label} changed while reading")
        after = os.fstat(stream.fileno())
        try:
            target = _source_path_identity(path, flags)
        except FileNotFoundError as exc:
            raise RuntimeError(f"{label} changed while reading") from exc
    observed = _file_generation(before)
    finished = _file_generation(after)
    if observed != finished or _file_generation(target) != finished:
        raise RuntimeError(f"{label} changed while reading")
    try:
        value = _strict_json_loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError(f"{label} is malformed") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not an object")
    return value


class _SourceDirent(ctypes.Structure):
    """Linux dirent ABI used to retain a seekable directory-page cookie."""
    _fields_ = [
        ("d_ino", ctypes.c_ulong), ("d_off", ctypes.c_long),
        ("d_reclen", ctypes.c_ushort), ("d_type", ctypes.c_ubyte),
        ("d_name", ctypes.c_char * (MAX_CORPUS_COMPONENT_BYTES + 1)),
    ]


_SOURCE_LIBC = ctypes.CDLL(None, use_errno=True)
_SOURCE_LIBC.fdopendir.argtypes = [ctypes.c_int]
_SOURCE_LIBC.fdopendir.restype = ctypes.c_void_p
_SOURCE_LIBC.readdir.argtypes = [ctypes.c_void_p]
_SOURCE_LIBC.readdir.restype = ctypes.POINTER(_SourceDirent)
_SOURCE_LIBC.telldir.argtypes = [ctypes.c_void_p]
_SOURCE_LIBC.telldir.restype = ctypes.c_long
_SOURCE_LIBC.seekdir.argtypes = [ctypes.c_void_p, ctypes.c_long]
_SOURCE_LIBC.seekdir.restype = None
_SOURCE_LIBC.closedir.argtypes = [ctypes.c_void_p]
_SOURCE_LIBC.closedir.restype = ctypes.c_int


def _validated_source_page_state(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("source directory page cursor is invalid")
    for name in ("device", "inode", "cookie", "size", "mtime_ns",
                 "ctime_ns"):
        field = value.get(name)
        if field is not None and (isinstance(field, bool)
                                  or not isinstance(field, int)
                                  or field < 0):
            raise ValueError("source directory page cursor is invalid")
    if "reset" in value and not isinstance(value["reset"], bool):
        raise ValueError("source directory page cursor is invalid")
    return value


def _bounded_source_entries(directory, page_state=None, limit=None,
                            cleanup_legacy_atomic=False):
    """Read one stable, no-follow, crash-resumable directory page.

    Linux directory cookies let the next pulse resume after this page instead
    of repeatedly inspecting a fixed prefix.  ``complete`` is true only on an
    observed EOF; callers must not infer deletion from a partial page.
    """
    if limit is None:
        limit = MAX_SOURCE_SCAN_ENTRIES
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0 \
            or limit > MAX_SOURCE_SCAN_ENTRIES:
        raise ValueError("source directory scan bound is invalid")
    page_state = _validated_source_page_state(page_state)
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_DIRECTORY", 0))
    descriptor = _open_source_nofollow(directory, flags)
    directory_pointer = None
    cleaned = False
    try:
        before = os.fstat(descriptor)
        if cleanup_legacy_atomic:
            try:
                inside_corpus = os.path.commonpath((
                    os.path.abspath(directory), os.path.abspath(CORPUS))) \
                    == os.path.abspath(CORPUS)
            except ValueError:
                inside_corpus = False
            if not inside_corpus or before.st_uid != os.geteuid():
                raise ValueError(
                    "legacy corpus staging cleanup requires an owned corpus directory")
        scan_descriptor = os.dup(descriptor)
        directory_pointer = _SOURCE_LIBC.fdopendir(scan_descriptor)
        if not directory_pointer:
            saved_errno = ctypes.get_errno()
            os.close(scan_descriptor)
            raise OSError(saved_errno, os.strerror(saved_errno), directory)
        same_generation = (
            page_state.get("device") == before.st_dev
            and page_state.get("inode") == before.st_ino
            and page_state.get("size") == before.st_size
            and page_state.get("mtime_ns") == before.st_mtime_ns
            and page_state.get("ctime_ns") == before.st_ctime_ns)
        reset = bool(page_state.get("cookie", 0) and not same_generation)
        if same_generation:
            _SOURCE_LIBC.seekdir(
                directory_pointer, page_state.get("cookie", 0))
        selected = []
        inspected = 0
        complete = False
        while inspected < limit:
            ctypes.set_errno(0)
            record = _SOURCE_LIBC.readdir(directory_pointer)
            if not record:
                saved_errno = ctypes.get_errno()
                if saved_errno:
                    raise OSError(saved_errno, os.strerror(saved_errno),
                                  directory)
                complete = True
                break
            raw_name = bytes(record.contents.d_name).split(b"\0", 1)[0]
            name = os.fsdecode(raw_name)
            if name in {".", ".."}:
                continue
            inspected += 1
            try:
                info = os.stat(name, dir_fd=descriptor,
                               follow_symlinks=False)
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "source directory changed while scanning") from exc
            if cleanup_legacy_atomic and _legacy_atomic_temp_name(name):
                if not stat.S_ISREG(info.st_mode) \
                        or info.st_uid != os.geteuid() \
                        or info.st_nlink != 1:
                    raise ValueError(
                        "corpus has an unsafe legacy staging entry")
                os.unlink(name, dir_fd=descriptor)
                cleaned = True
                continue
            selected.append({
                "name": name, "mode": info.st_mode,
                "size": info.st_size, "mtime": info.st_mtime,
                "mtime_ns": info.st_mtime_ns,
                "ctime_ns": info.st_ctime_ns,
                "device": info.st_dev, "inode": info.st_ino,
            })
        next_cookie = (0 if complete else
                       int(_SOURCE_LIBC.telldir(directory_pointer)))
        after = os.fstat(descriptor)
        try:
            target = _source_path_identity(directory, flags)
        except FileNotFoundError as exc:
            raise RuntimeError("source directory changed while scanning") \
                from exc
    finally:
        if directory_pointer:
            _SOURCE_LIBC.closedir(directory_pointer)
        if cleaned:
            os.fsync(descriptor)
        os.close(descriptor)
    observed = _file_generation(before)
    finished = _file_generation(after)
    if observed != finished or _file_generation(target) != finished:
        raise RuntimeError("source directory changed while scanning")
    selected.sort(key=lambda item: item["name"])
    next_state = {
        "device": before.st_dev, "inode": before.st_ino,
        "size": before.st_size,
        "mtime_ns": before.st_mtime_ns, "ctime_ns": before.st_ctime_ns,
        "cookie": next_cookie,
        "reset": reset,
    }
    return selected, complete, inspected, next_state


def _nofollow_source_directory(path):
    """Confirm one stable directory leaf without following that leaf."""
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_DIRECTORY", 0))
    try:
        descriptor = _open_source_nofollow(path, flags)
    except (FileNotFoundError, NotADirectoryError):
        return False
    try:
        before = os.fstat(descriptor)
        after = os.fstat(descriptor)
        current = _source_path_identity(path, flags)
    finally:
        os.close(descriptor)
    observed = _file_generation(before)
    finished = _file_generation(after)
    if observed != finished or _file_generation(current) != finished:
        raise RuntimeError("source directory changed while checking")
    return True


# Optional source discovery needs the no-follow directory gate above. Keep
# construction here so a symlinked vault or ``.git`` never activates merely
# because ``exists()`` followed it.
ORGANS = _build_organs()


SOURCE_TREE_SCHEMA = "sia-source-tree-v3"
SOURCE_TREE_GENERATION_FIELDS = (
    "device", "inode", "size", "mtime_ns", "ctime_ns")


def _source_tree_directory_generation(page_state):
    generation = {
        name: page_state.get(name)
        for name in SOURCE_TREE_GENERATION_FIELDS}
    if any(isinstance(value, bool) or not isinstance(value, int)
           or value < 0 for value in generation.values()):
        raise ValueError("source tree directory generation is invalid")
    return generation


def _source_tree_path_generation(path):
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_DIRECTORY", 0))
    descriptor = _open_source_nofollow(path, flags)
    try:
        before = os.fstat(descriptor)
        after = os.fstat(descriptor)
        target = _source_path_identity(path, flags)
    finally:
        os.close(descriptor)

    def generation(info):
        return {
            "device": info.st_dev, "inode": info.st_ino,
            "size": info.st_size, "mtime_ns": info.st_mtime_ns,
            "ctime_ns": info.st_ctime_ns,
        }

    observed = generation(before)
    if observed != generation(after) or observed != generation(target):
        raise RuntimeError("source tree directory changed while validating")
    return observed


def _validated_source_tree_state(value, directory_levels):
    initial_queue = [{"relative": "", "levels": directory_levels,
                      "page": {}}]
    if value is None:
        return {
            "schema": SOURCE_TREE_SCHEMA, "generation": 0,
            "phase": "scan", "coverage": True,
            "queue": initial_queue, "directories": [],
            "validation_cursor": 0}
    if not isinstance(value, dict) \
            or not isinstance(value.get("queue"), list):
        raise ValueError("source tree cursor is invalid")
    current_schema = value.get("schema") == SOURCE_TREE_SCHEMA
    if current_schema:
        if set(value) != {
                "schema", "generation", "phase", "coverage", "queue",
                "directories", "validation_cursor"}:
            raise ValueError("source tree cursor is invalid")
        generation = value.get("generation")
        phase = value.get("phase")
        coverage = value.get("coverage")
        if isinstance(generation, bool) or not isinstance(generation, int) \
                or generation < 0 or phase not in {"scan", "validate"} \
                or not isinstance(coverage, bool):
            raise ValueError("source tree cursor is invalid")
    else:
        # An old queue may already be mid-generation and did not retain a
        # prior missing/reset frame. Finish it without deletion authority,
        # then begin a clean v3 generation.
        generation = 0
        phase = "scan"
        coverage = False
    queue = []
    queued_relatives = set()
    for item in value["queue"]:
        if len(queue) >= MAX_SOURCE_SCAN_ENTRIES:
            raise ValueError("source tree cursor exceeds its queue bound")
        if not isinstance(item, dict) \
                or current_schema and set(item) != {
                    "relative", "levels", "page"}:
            raise ValueError("source tree cursor is invalid")
        relative = item.get("relative")
        levels = item.get("levels")
        parts = relative.split(os.sep) if isinstance(relative, str) \
            and relative else []
        if not isinstance(relative, str) or os.path.isabs(relative) \
                or (relative and any(part in {"", ".", ".."}
                                     for part in parts)) \
                or len(relative) > MAX_CONFIG_PATH_CHARS \
                or any(len(os.fsencode(part)) > MAX_CORPUS_COMPONENT_BYTES
                       for part in parts) \
                or (os.altsep and os.altsep in relative) \
                or isinstance(levels, bool) or not isinstance(levels, int) \
                or levels < 0 or levels > directory_levels \
                or current_schema and (
                    relative in queued_relatives
                    or levels != directory_levels - len(parts)):
            raise ValueError("source tree cursor is invalid")
        page = _validated_source_page_state(item.get("page"))
        page_fields = {
            "device", "inode", "cookie", "size", "mtime_ns", "ctime_ns",
            "reset"}
        if current_schema and page and (
                set(page) != page_fields
                or page["reset"] is not False
                or any(isinstance(page[name], bool)
                       or not isinstance(page[name], int)
                       or page[name] < 0
                       for name in page_fields - {"reset"})):
            raise ValueError("source tree page cursor is invalid")
        queued_relatives.add(relative)
        queue.append({"relative": relative, "levels": levels,
                      "page": page})
    if not queue:
        if phase == "scan":
            queue = initial_queue
            coverage = False
    raw_directories = value.get("directories", []) \
        if current_schema else []
    if not isinstance(raw_directories, list):
        raise ValueError("source tree cursor is invalid")
    directories = []
    directory_names = set()
    for item in raw_directories:
        if len(directories) >= MAX_SOURCE_SCAN_ENTRIES \
                or not isinstance(item, dict) \
                or current_schema and set(item) != {
                    "relative", "generation"}:
            raise ValueError("source tree directory catalog is invalid")
        relative = item.get("relative")
        parts = relative.split(os.sep) if relative else []
        if not isinstance(relative, str) or os.path.isabs(relative) \
                or (relative and any(part in {"", ".", ".."}
                                     for part in parts)) \
                or len(parts) > directory_levels \
                or len(relative) > MAX_CONFIG_PATH_CHARS \
                or any(len(os.fsencode(part)) > MAX_CORPUS_COMPONENT_BYTES
                       for part in parts) \
                or (os.altsep and os.altsep in relative) \
                or relative in directory_names \
                or not isinstance(item.get("generation"), dict) \
                or current_schema and set(item["generation"]) != set(
                    SOURCE_TREE_GENERATION_FIELDS):
            raise ValueError("source tree directory catalog is invalid")
        directory_names.add(relative)
        directories.append({
            "relative": relative,
            "generation": _source_tree_directory_generation(
                item["generation"])})
    validation_cursor = value.get("validation_cursor", 0) \
        if current_schema else 0
    if isinstance(validation_cursor, bool) \
            or not isinstance(validation_cursor, int) \
            or validation_cursor < 0 \
            or validation_cursor > len(directories) \
            or (phase == "scan" and validation_cursor != 0) \
            or (phase == "validate" and (queue or not directories)):
        raise ValueError("source tree validation cursor is invalid")
    return {
        "schema": SOURCE_TREE_SCHEMA, "generation": generation,
        "phase": phase, "coverage": coverage, "queue": queue,
        "directories": directories,
        "validation_cursor": validation_cursor}


def _bounded_source_tree_files(root, cursors, cursor_key,
                               directory_levels, suffix):
    """Advance one refusal-aware metadata-tree snapshot generation.

    A generation can authorize absence only after every queued frame reaches
    EOF without a missing frame, capacity refusal, or directory-page reset.
    The coverage bit survives pagination, so a later successful frame cannot
    erase an earlier hole in the same root-to-EOF traversal.
    """
    if isinstance(directory_levels, bool) \
            or not isinstance(directory_levels, int) \
            or directory_levels < 0:
        raise ValueError("source tree depth is invalid")
    tree = _validated_source_tree_state(cursors.get(cursor_key),
                                        directory_levels)
    phase = tree["phase"]
    queue = collections.deque(tree["queue"])
    generation = tree["generation"]
    coverage = tree["coverage"]
    directories = list(tree["directories"])
    directory_tokens = {
        item["relative"]: item["generation"] for item in directories}
    validation_cursor = tree["validation_cursor"]
    files = []
    refused = []
    remaining = MAX_SOURCE_SCAN_ENTRIES
    while phase == "scan" and queue and remaining:
        item = queue.popleft()
        directory = os.path.join(root, item["relative"])
        try:
            entries, complete, inspected, next_page = \
                _bounded_source_entries(directory, item["page"], remaining)
        except (OSError, RuntimeError):
            coverage = False
            refused.append(item["relative"] or ".")
            if item["relative"] == "":
                # Keep the failed generation and retry the root. If it
                # reappears, this generation still cannot authorize pruning;
                # the following clean generation establishes the baseline.
                queue.clear()
                queue.append({"relative": "", "levels": directory_levels,
                              "page": {}})
                cursors[cursor_key] = {
                    "schema": SOURCE_TREE_SCHEMA,
                    "generation": generation, "phase": "scan",
                    "coverage": False, "queue": list(queue),
                    "directories": directories,
                    "validation_cursor": 0}
                files.sort(key=lambda entry: entry["path"])
                return files, False, refused, generation
            continue
        remaining -= inspected
        directory_generation = _source_tree_directory_generation(next_page)
        prior_generation = directory_tokens.get(item["relative"])
        if prior_generation is None:
            if len(directories) >= MAX_SOURCE_SCAN_ENTRIES:
                coverage = False
                refused.append(item["relative"] or ".")
            else:
                catalog_item = {
                    "relative": item["relative"],
                    "generation": directory_generation}
                directories.append(catalog_item)
                directory_tokens[item["relative"]] = directory_generation
        elif prior_generation != directory_generation:
            coverage = False
            refused.append(item["relative"] or ".")
            for catalog_item in directories:
                if catalog_item["relative"] == item["relative"]:
                    catalog_item["generation"] = directory_generation
                    break
            directory_tokens[item["relative"]] = directory_generation
        if next_page.get("reset"):
            coverage = False
            refused.append(item["relative"] or ".")
        if not complete:
            item["page"] = next_page
            queue.append(item)
        if item["levels"]:
            for entry in entries:
                relative = os.path.join(item["relative"], entry["name"])
                if not stat.S_ISDIR(entry["mode"]):
                    if not stat.S_ISREG(entry["mode"]):
                        coverage = False
                        refused.append(relative)
                    continue
                child = {"relative": relative,
                         "levels": item["levels"] - 1, "page": {}}
                if len(queue) >= MAX_SOURCE_SCAN_ENTRIES:
                    coverage = False
                    refused.append(relative)
                else:
                    queue.append(child)
        else:
            for entry in entries:
                if not entry["name"].endswith(suffix):
                    continue
                relative = os.path.join(item["relative"], entry["name"])
                if not stat.S_ISREG(entry["mode"]):
                    coverage = False
                    refused.append(relative)
                    continue
                files.append(dict(entry, path=os.path.join(
                    directory, entry["name"])))
    if phase == "scan" and not queue:
        phase = "validate"
        directories.sort(key=lambda item: item["relative"])
        validation_cursor = 0

    complete_snapshot = False
    completed_generation = generation
    while phase == "validate" \
            and validation_cursor < len(directories) and remaining:
        catalog_item = directories[validation_cursor]
        remaining -= 1
        try:
            current = _source_tree_path_generation(os.path.join(
                root, catalog_item["relative"]))
        except (OSError, RuntimeError):
            current = None
        if current != catalog_item["generation"]:
            coverage = False
            refused.append(catalog_item["relative"] or ".")
        validation_cursor += 1
    if phase == "validate" and validation_cursor == len(directories):
        complete_snapshot = bool(coverage and directories
                                 and directories[0]["relative"] == "")
        generation += 1
        phase = "scan"
        queue.append({"relative": "", "levels": directory_levels,
                      "page": {}})
        coverage = True
        directories = []
        validation_cursor = 0
    cursors[cursor_key] = {
        "schema": SOURCE_TREE_SCHEMA, "generation": generation,
        "phase": phase, "coverage": coverage, "queue": list(queue),
        "directories": directories,
        "validation_cursor": validation_cursor}
    files.sort(key=lambda item: item["path"])
    return files, complete_snapshot, refused, completed_generation


def _source_truncation_event(organ, source):
    token = _source_entity_token(source, "source")
    return Event(
        organ, utcnow(), "source-truncated",
        f"{source} exceeded its bounded source scan; later entries were "
        "not inspected", {f"organs/{organ}"},
        {"source-truncated", "refusal"},
        occurrence=f"source-truncated:{organ}:{token}")


def _source_entry_refusal_event(organ, source):
    token = _source_entity_token(source, "source-entry")
    return Event(
        organ, utcnow(), "source-entry-refused",
        f"{source} could not be admitted within the bounded source state",
        {f"organs/{organ}"}, {"source-entry-refused", "refusal"},
        occurrence=f"source-entry-refused:{organ}:{token}")


# ---------------------------------------------------------------- senses

# Sensing is isolated in a normal, audited runtime module so marketplace
# static review can inspect every source file within its file-size ceiling.
# The core stays the sole owner of configuration, cursors, and mutable state:
# the child never imports sialib, because tests intentionally load sialib
# under dynamic aliases and must not create a second copy of that state.
WL_LOUD_KINDS = {"mission", "collapse-receipt", "agent-invocation",
                 "agent-invocation-result", "result", "done", "edit"}

WORLDLINE_CURSOR_TIME = "worldline.created_at"
WORLDLINE_CURSOR_EVENT = "worldline.event_id"
# Preserve WORLDLINE's source-native page size, but never select hostile TEXT
# whole. SQL exposes only type, exact BLOB byte length, and one cap-plus-one
# BLOB prefix; Python also enforces an aggregate selected-byte budget.
MAX_WORLDLINE_ROWS = 2000
MAX_WORLDLINE_PAGE_BYTES = MAX_SOURCE_TAIL_BYTES
MAX_WORLDLINE_REFUSALS = MAX_SOURCE_TAIL_RECORDS
WORLDLINE_FIELD_SPECS = (
    ("event_id", MAX_SOURCE_NAME_CHARS, False),
    ("kind", MAX_SOURCE_NAME_CHARS, False),
    ("actor", MAX_CONFIG_TEXT_CHARS, True),
    ("tool", MAX_CONFIG_TEXT_CHARS, True),
    ("reason", MAX_CONFIG_TEXT_CHARS, True),
    ("path_display", MAX_CONFIG_TEXT_CHARS, True),
    ("created_at", MAX_SOURCE_NAME_CHARS, False),
    ("world_instance", MAX_SOURCE_NAME_CHARS, False),
)
WORLDLINE_ORDER_SPECS = (
    WORLDLINE_FIELD_SPECS[0], WORLDLINE_FIELD_SPECS[6])
WORLDLINE_TIME_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?Z$")
WORLDLINE_VISIBLE_ID_RE = re.compile(r"[\x21-\x7e]+")

PACMAN_RE = re.compile(
    r"^\[([^\]]+)\] \[ALPM\] (installed|upgraded|removed) ([^ ]+) (.*)$")

# journalctl advances --cursor-file on disk at read time — before this pulse's
# pages exist. So each read runs against a TEMP copy; pulse() renames it over
# the real cursor only after the corpus write phase succeeded.
PENDING_CURSOR_RENAMES = []

# Journal output is hostile-sized input even though journalctl is asked for a
# bounded row count: one JSON record can contain an arbitrarily large field.
# Reuse the source/state bounds already enforced by the resident service.
MAX_JOURNAL_RECORD_BYTES = MAX_SOURCE_TAIL_BYTES
MAX_JOURNAL_OUTPUT_BYTES = MAX_STATE_JSON_BYTES
MAX_JOURNAL_STDERR_BYTES = MAX_CONFIG_BYTES
MAX_JOURNAL_CURSOR_BYTES = MAX_CONFIG_BYTES
MAX_JOURNAL_RECORDS = MAX_SOURCE_TAIL_RECORDS
MAX_JOURNAL_READ_BYTES = MAX_CONFIG_BYTES
JOURNAL_TIMEOUT_SECONDS = 30

# Personal skill roots, in the precedence order the agent loaders use.
# One graph node per skill NAME: the same slug in several roots is one
# skill installed in several places, not several skills.
MAX_SKILL_SNAPSHOT_ENTRIES = MAX_SOURCE_TAIL_RECORDS
MAX_SKILL_MANIFEST_HEAD_BYTES = 8192

import siasenses as _siasenses


def _sialib_sense_delegate(name):
    """Return a façade that binds this sialib instance before every call."""
    target = _siasenses._ORIGINAL_CHILD_FUNCTIONS[name]

    @functools.wraps(target)
    def delegated(*args, **kwargs):
        return _siasenses.invoke(globals(), name, *args, **kwargs)

    delegated._sia_senses_delegate = True
    return delegated


# Bind once during import for helpers reached while the registry is built, then
# expose parent-owned façades.  Child-to-child calls stay direct, avoiding
# recursive rebinding and preserving its internal implementation boundary.
_siasenses.bind(globals())
for _sialib_sense_name in _siasenses._EXPORTED_FUNCTIONS:
    globals()[_sialib_sense_name] = _sialib_sense_delegate(
        _sialib_sense_name)
del _sialib_sense_name

SKILL_ROOTS = _configured_skill_roots()

_SENSE_ORGAN = {
    "sense_sia": "sia", "sense_jackal": "jackal",
    "sense_sekhmet": "sekhmet",
    "sense_custos": "custos", "sense_aegis": "aegis",
    "sense_worldline": "worldline", "sense_guardian": "guardian",
    "sense_pacman": "pacman", "sense_journal": "journal",
    "sense_git": "projects", "sense_obsidian": "obsidian",
    "sense_claude": "claude-code",
    "sense_codex": "codex", "sense_notify": "notify",
    "sense_agents": "agents", "sense_skills": "skills",
}

_ALL_SENSES = [sense_sia, sense_jackal, sense_sekhmet, sense_custos, sense_aegis,
               sense_worldline, sense_pacman, sense_journal,
               sense_guardian, sense_git, sense_obsidian,
               sense_claude, sense_codex,
               sense_notify, sense_agents, sense_skills]

# Only senses whose source is active on this machine run.
SENSES = [s for s in _ALL_SENSES
          if _SENSE_ORGAN.get(s.__name__, "") in ORGANS] + [sense_custom]
# ---------------------------------------------------------------- corpus

FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)

def corpus_path(slug):
    return os.path.join(CORPUS, slug + ".md")

def page_exists(slug):
    try:
        return stat.S_ISREG(os.lstat(corpus_path(slug)).st_mode)
    except OSError:
        return False


def corpus_origin(slug, ptype=""):
    """Return a validated page origin, with an explicit legacy boundary.

    Origin is read from the corpus bytes rather than trusted from search
    snippets. Every nested component is opened no-follow. Missing, malformed,
    linked, oversized-frontmatter, or invalid-origin pages are conservatively
    ``legacy-unlabeled`` instead of being promoted to evidence.
    """
    try:
        slug = _canonical_corpus_slug(slug)
        # The JACKAL results ledger and receipt-directory observations are
        # recall surfaces, never mathematical evidence. This namespace rule
        # deliberately covers pre-origin-label pages as well as new pages.
        if slug.startswith(("events/jackal/", "epochs/jackal/")):
            return "derived"
        parts = slug.split("/")
        directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                           | getattr(os, "O_NOFOLLOW", 0)
                           | getattr(os, "O_DIRECTORY", 0))
        directory_fd = os.open(CORPUS, directory_flags)
        try:
            for part in parts[:-1]:
                next_fd = os.open(part, directory_flags,
                                  dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = next_fd
            fd = os.open(parts[-1] + ".md",
                         os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                         | getattr(os, "O_NOFOLLOW", 0),
                         dir_fd=directory_fd)
        finally:
            os.close(directory_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise OSError("corpus memory is not a regular file")
            raw = os.read(fd, MAX_THOUGHT_INBOX_BYTES + 1)
        finally:
            os.close(fd)
        if len(raw) > MAX_THOUGHT_INBOX_BYTES:
            raw = raw[:MAX_THOUGHT_INBOX_BYTES]
        text = raw.decode("utf-8")
        match = FM_RE.match(text)
        if not match:
            raise ValueError("page frontmatter is absent or malformed")
        frontmatter = match.group(1)
        type_values = re.findall(r"^type:\s*(.*?)\s*$", frontmatter, re.M)
        if len(type_values) != 1:
            raise ValueError("page type is missing or duplicated")
        ptype = _yaml_scalar(type_values[0])
        origin_values = re.findall(
            r"^origin:\s*(.*?)\s*$", frontmatter, re.M)
        if not origin_values:
            declared = None
        elif len(origin_values) == 1:
            declared = _yaml_scalar(origin_values[0])
        else:
            declared = "invalid-duplicate-origin"
        return siamind.origin_class(slug, ptype, declared)
    except Exception:
        return "legacy-unlabeled"


UNVERIFIED_JACKAL_RECALL_NOTICE = (
    "[unverified JACKAL ledger/file-presence observation suppressed; "
    "artifact presence is recall, not mathematical evidence]")
_LEGACY_JACKAL_ASSURANCE_TERMS = (
    "formal-receipt", "formal receipt", "lean-checked mathematics")


def _contains_legacy_jackal_assurance(value):
    if not isinstance(value, str):
        return False
    folded = value.casefold()
    return any(term in folded for term in _LEGACY_JACKAL_ASSURANCE_TERMS)


def unverified_jackal_recall_page(slug, text=None):
    """Identify old categorical JACKAL prose that must not be reasserted."""
    try:
        slug = _canonical_corpus_slug(slug)
    except ValueError:
        return True
    if not (slug.startswith(("events/jackal/", "epochs/jackal/"))
            or slug.startswith("thoughts/")):
        return False
    if _contains_legacy_jackal_assurance(text):
        return True
    try:
        _page, frontmatter, body = _read_graph_corpus_page(slug)
        text = frontmatter + "\n" + body
    except Exception:
        # A generated entry that cannot be stably classified must not bypass this
        # legacy-assurance boundary through an old search index entry.
        return True
    return _contains_legacy_jackal_assurance(text)


def neutralize_unverified_jackal_recall(slug, value):
    if unverified_jackal_recall_page(slug, value):
        return UNVERIFIED_JACKAL_RECALL_NOTICE
    return strip_controls(value)


def neutralize_unverified_jackal_output(value):
    """Remove categorical legacy assurance lines from unstructured recall."""
    clean = strip_controls(value)
    return "\n".join(
        UNVERIFIED_JACKAL_RECALL_NOTICE
        if _contains_legacy_jackal_assurance(line) else line
        for line in clean.split("\n"))

def write_page(slug, fm, body):
    path = corpus_path(slug)
    ensure_durable_directory(os.path.dirname(path))
    fml = "---\n" + "\n".join(fm) + "\n---\n"
    _before_corpus_mutation()
    atomic_write(path, fml + body)

def fm_title(title):
    # JSON string escaping is valid YAML double-quote style — colons etc. safe
    return "title: " + json.dumps(title, ensure_ascii=False)


_CORTEX_CURRENT_TITLE = "SIA root memory"
_CORTEX_CURRENT_BODY_LINES = (
    "SIA is the Omarchy Brain, a local machine-memory product.",
    BRAIN_METAPHOR_BOUNDARY,
    "Every enabled source below reports what it observes. The persisted",
    "organ/cortex names are compatibility namespaces. Each configured",
    "signed chain is checked by its own keeper verifier; Custos also uses",
    "the SPARK-proved `attest` verifier. Deterministic entry generators",
    "are evidence-derived; user/model prose is origin-labeled.",
    "",
)


def _current_cortex_root_bytes():
    """Return the one exact unwitnessed root emitted for a fresh corpus."""
    frontmatter = "---\ntype: organ\n" \
        + fm_title(_CORTEX_CURRENT_TITLE) + "\n---\n"
    body = "# " + _CORTEX_CURRENT_TITLE + "\n\n" \
        + "\n".join(_CORTEX_CURRENT_BODY_LINES) + "\n"
    return (frontmatter + body).encode("utf-8")


_CORTEX_REPAIR_RECEIPT_KEYS = frozenset({
    "schema", "slug", "operation", "source_sha256", "target_sha256",
    "appended_sha256", "source_bytes", "target_bytes", "boundary",
    "ledger_order",
})
_CORTEX_REPAIR_JOURNAL_KEYS = frozenset({
    "schema", "slug", "operation", "source_sha256", "target_sha256",
    "appended_sha256", "source_bytes", "target_bytes", "boundary",
    "ledger_order", "append_text", "order", "action", "arg1", "arg2",
    "content",
})


def _read_cortex_root_bytes():
    """Read the cortex root through one bounded, owner-controlled handle."""
    path = corpus_path("sia/cortex")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = _open_source_nofollow(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() or before.st_nlink != 1 \
                or before.st_mode & (stat.S_IWGRP | stat.S_IWOTH) \
                or before.st_size > MAX_CONFIG_BYTES:
            raise RuntimeError(
                "cortex root is not a bounded owner-controlled "
                "single-link regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw = stream.read(MAX_CONFIG_BYTES + 1)
            after = os.fstat(stream.fileno())
        if _file_generation(before) != _file_generation(after) \
                or len(raw) > MAX_CONFIG_BYTES:
            raise RuntimeError("cortex root changed while read")
        try:
            current = os.lstat(path)
        except OSError as exc:
            raise RuntimeError("cortex root changed while read") from exc
        if not stat.S_ISREG(current.st_mode) \
                or _file_generation(current) != _file_generation(after):
            raise RuntimeError("cortex root changed while read")
        return raw
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _validate_cortex_root(raw):
    """Admit only the canonical organ/H1 page shape before additive repair."""
    if not isinstance(raw, bytes) or len(raw) > MAX_CONFIG_BYTES:
        raise RuntimeError("cortex root bytes exceed their admission bound")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise RuntimeError("cortex root is not UTF-8") from exc
    match = FM_RE.match(text)
    if match is None:
        raise RuntimeError("cortex root frontmatter is malformed")
    type_rows = re.findall(r"^type:\s*(.*?)\s*$", match.group(1), re.M)
    if type_rows != ["organ"]:
        raise RuntimeError("cortex root is not one canonical organ page")
    body = text[match.end():]
    first_line = body.split("\n", 1)[0]
    if re.fullmatch(r"# [^#\r\n].*", first_line) is None:
        raise RuntimeError("cortex root has no canonical H1")
    return text


def _cortex_repair_receipt(source, target, appended, ledger_order):
    return {
        "schema": CORTEX_BOUNDARY_REPAIR_SCHEMA,
        "slug": "sia/cortex",
        "operation": "append-only",
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "target_sha256": hashlib.sha256(target).hexdigest(),
        "appended_sha256": hashlib.sha256(appended).hexdigest(),
        "source_bytes": len(source),
        "target_bytes": len(target),
        "boundary": BRAIN_METAPHOR_BOUNDARY,
        "ledger_order": ledger_order,
    }


def _validate_cortex_repair_receipt(value):
    if not isinstance(value, dict) \
            or set(value) != _CORTEX_REPAIR_RECEIPT_KEYS \
            or value.get("schema") != CORTEX_BOUNDARY_REPAIR_SCHEMA \
            or value.get("slug") != "sia/cortex" \
            or value.get("operation") != "append-only" \
            or value.get("boundary") != BRAIN_METAPHOR_BOUNDARY:
        raise RuntimeError("cortex boundary repair receipt is invalid")
    for field in ("source_sha256", "target_sha256", "appended_sha256"):
        if not isinstance(value.get(field), str) \
                or re.fullmatch(r"[0-9a-f]{64}", value[field]) is None:
            raise RuntimeError("cortex boundary repair receipt is invalid")
    for field in ("source_bytes", "target_bytes"):
        number = value.get(field)
        if isinstance(number, bool) or not isinstance(number, int) \
                or number < 0 or number > MAX_CONFIG_BYTES:
            raise RuntimeError("cortex boundary repair receipt is invalid")
    ledger_order = value.get("ledger_order")
    if isinstance(ledger_order, bool) or not isinstance(ledger_order, int) \
            or ledger_order < 0:
        raise RuntimeError("cortex boundary repair receipt is invalid")
    if value["source_bytes"] >= value["target_bytes"]:
        raise RuntimeError("cortex boundary repair receipt is invalid")
    return value


def _cortex_receipt_text(receipt):
    _validate_cortex_repair_receipt(receipt)
    return json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _load_cortex_repair_receipt():
    if not os.path.lexists(CORTEX_BOUNDARY_REPAIR_RECEIPT):
        return None
    value = read_state_json(
        CORTEX_BOUNDARY_REPAIR_RECEIPT, {},
        "cortex boundary repair receipt", expected_type=dict)
    return _validate_cortex_repair_receipt(value)


def _validate_cortex_repair_journal(value):
    if not isinstance(value, dict) \
            or set(value) != _CORTEX_REPAIR_JOURNAL_KEYS \
            or value.get("schema") \
            != CORTEX_BOUNDARY_REPAIR_JOURNAL_SCHEMA:
        raise RuntimeError("cortex boundary repair journal is invalid")
    receipt = {key: value[key] for key in _CORTEX_REPAIR_RECEIPT_KEYS
               if key != "schema"}
    receipt["schema"] = CORTEX_BOUNDARY_REPAIR_SCHEMA
    _validate_cortex_repair_receipt(receipt)
    append_text = value.get("append_text")
    if append_text != CORTEX_BOUNDARY_REPAIR_SUFFIX:
        raise RuntimeError("cortex boundary repair journal is invalid")
    appended = append_text.encode("utf-8", errors="strict")
    if hashlib.sha256(appended).hexdigest() != value["appended_sha256"] \
            or value["source_bytes"] + len(appended) \
            != value["target_bytes"]:
        raise RuntimeError("cortex boundary repair journal is invalid")
    order = value.get("order")
    if isinstance(order, bool) or not isinstance(order, int) or order < 0:
        raise RuntimeError("cortex boundary repair journal is invalid")
    if order != receipt["ledger_order"]:
        raise RuntimeError("cortex boundary repair journal is invalid")
    expected_action = "MIGRATE:cortex-boundary-repair"
    expected_arg1 = "sia/cortex"
    expected_arg2 = "product-metaphor-boundary-additive-v1"
    if value.get("action") != expected_action \
            or value.get("arg1") != expected_arg1 \
            or value.get("arg2") != expected_arg2 \
            or value.get("content") != _cortex_receipt_text(receipt):
        raise RuntimeError("cortex boundary repair journal is invalid")
    return value


def _load_cortex_repair_journal():
    if not os.path.lexists(CORTEX_BOUNDARY_REPAIR_JOURNAL):
        return None
    value = read_state_json(
        CORTEX_BOUNDARY_REPAIR_JOURNAL, {},
        "cortex boundary repair journal", expected_type=dict)
    return _validate_cortex_repair_journal(value)


def _write_cortex_repair_state(path, value):
    atomic_write(path, json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False))


def _ensure_cortex_repair_receipt(journal):
    expected = {key: journal[key] for key in _CORTEX_REPAIR_RECEIPT_KEYS
                if key != "schema"}
    expected["schema"] = CORTEX_BOUNDARY_REPAIR_SCHEMA
    current = _load_cortex_repair_receipt()
    if current is None:
        _write_cortex_repair_state(
            CORTEX_BOUNDARY_REPAIR_RECEIPT, expected)
        current = _load_cortex_repair_receipt()
    if current != expected:
        raise RuntimeError("cortex boundary repair receipt conflicts")
    return current


def _cortex_receipt_matches_target(receipt, target):
    _validate_cortex_repair_receipt(receipt)
    if len(target) != receipt["target_bytes"] \
            or hashlib.sha256(target).hexdigest() \
            != receipt["target_sha256"]:
        return False
    source = target[:receipt["source_bytes"]]
    appended = target[receipt["source_bytes"]:]
    return hashlib.sha256(source).hexdigest() \
        == receipt["source_sha256"] \
        and hashlib.sha256(appended).hexdigest() \
        == receipt["appended_sha256"] \
        and appended.decode("utf-8", errors="strict") \
        == CORTEX_BOUNDARY_REPAIR_SUFFIX


def _retire_cortex_repair_journal(journal):
    if _load_cortex_repair_journal() != journal:
        raise RuntimeError("cortex boundary repair journal changed")
    info = os.lstat(CORTEX_BOUNDARY_REPAIR_JOURNAL)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
            or info.st_nlink != 1:
        raise RuntimeError("cortex boundary repair journal changed")
    os.unlink(CORTEX_BOUNDARY_REPAIR_JOURNAL)
    descriptor = os.open(
        STATE, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _settle_cortex_boundary_repair(journal):
    journal = _validate_cortex_repair_journal(journal)
    _ensure_cortex_repair_receipt(journal)
    current = _read_cortex_root_bytes()
    current_digest = hashlib.sha256(current).hexdigest()
    if len(current) == journal["source_bytes"] \
            and current_digest == journal["source_sha256"]:
        _validate_cortex_root(current)
        target = current + journal["append_text"].encode("utf-8")
        if len(target) != journal["target_bytes"] \
                or hashlib.sha256(target).hexdigest() \
                != journal["target_sha256"]:
            raise RuntimeError("cortex boundary repair target is invalid")
        _before_corpus_mutation()
        if _read_cortex_root_bytes() != current:
            raise RuntimeError(
                "cortex root changed before repair publication")
        atomic_write(corpus_path("sia/cortex"), target.decode("utf-8"))
        current = _read_cortex_root_bytes()
    elif len(current) != journal["target_bytes"] \
            or current_digest != journal["target_sha256"]:
        raise RuntimeError(
            "cortex root matches neither repair source nor target")
    _validate_cortex_root(current)
    receipt = _load_cortex_repair_receipt()
    if receipt is None or not _cortex_receipt_matches_target(receipt, current):
        raise RuntimeError("cortex boundary repair target is not witnessed")
    durable_ledger_append(
        journal["action"], journal["arg1"], journal["arg2"],
        journal["content"], order=journal["order"])
    if not _cortex_receipt_matches_target(
            _load_cortex_repair_receipt(), _read_cortex_root_bytes()):
        raise RuntimeError("cortex boundary repair changed before retirement")
    _retire_cortex_repair_journal(journal)
    return True


def _cortex_boundary_status(*, require_ledger=True):
    """Return the read-only repair state used by the readiness boundary."""
    journal = _load_cortex_repair_journal()
    if journal is not None:
        return False, "cortex product-metaphor boundary repair is pending"
    if not page_exists("sia/cortex"):
        return False, "cortex product-metaphor boundary root is missing"
    raw = _read_cortex_root_bytes()
    _validate_cortex_root(raw)
    occurrences = raw.count(BRAIN_METAPHOR_BOUNDARY.encode("utf-8"))
    receipt = _load_cortex_repair_receipt()
    if raw == _current_cortex_root_bytes():
        if receipt is not None:
            return False, "cortex product-metaphor boundary receipt is orphaned"
        return True, ""
    if occurrences == 0:
        return False, "cortex product-metaphor boundary repair is required"
    if occurrences != 1:
        return False, "cortex product-metaphor boundary is ambiguous"
    if not raw.endswith(CORTEX_BOUNDARY_REPAIR_SUFFIX.encode("utf-8")):
        return False, (
            "cortex root is neither the current root nor a witnessed repair")
    if receipt is None or not _cortex_receipt_matches_target(receipt, raw):
        return False, "cortex product-metaphor boundary receipt is invalid"
    if require_ledger:
        action = "MIGRATE:cortex-boundary-repair"
        arg1 = "sia/cortex"
        arg2 = "product-metaphor-boundary-additive-v1"
        content = _cortex_receipt_text(receipt)
        basis = _pending_basis(
            receipt["ledger_order"], action, arg1, arg2, content)
        if not ledger_contains(
                action, arg1, arg2, content,
                occurrence_id=_pending_identity(basis)):
            return False, (
                "cortex product-metaphor boundary ledger receipt "
                "is missing")
    return True, ""


def ensure_cortex():
    """Create the current root or settle one append-only historical repair."""
    ensure_dirs()
    journal = _load_cortex_repair_journal()
    if journal is not None:
        return _settle_cortex_boundary_repair(journal)
    if not page_exists("sia/cortex"):
        if _load_cortex_repair_receipt() is not None:
            raise RuntimeError("cortex boundary repair receipt is orphaned")
        return ensure_entity(
            "sia/cortex", "organ", _CORTEX_CURRENT_TITLE,
            list(_CORTEX_CURRENT_BODY_LINES))
    source = _read_cortex_root_bytes()
    _validate_cortex_root(source)
    occurrences = source.count(BRAIN_METAPHOR_BOUNDARY.encode("utf-8"))
    if occurrences == 1:
        ready, reason = _cortex_boundary_status(require_ledger=False)
        if not ready:
            raise RuntimeError(reason)
        return False
    if occurrences != 0:
        raise RuntimeError("cortex product-metaphor boundary is ambiguous")
    if _load_cortex_repair_receipt() is not None:
        raise RuntimeError("cortex boundary repair receipt is orphaned")
    appended = CORTEX_BOUNDARY_REPAIR_SUFFIX.encode("utf-8")
    target = source + appended
    if len(target) > MAX_CONFIG_BYTES:
        raise RuntimeError("cortex boundary repair target exceeds its bound")
    order = time.time_ns()
    receipt = _cortex_repair_receipt(source, target, appended, order)
    journal = {
        **receipt,
        "schema": CORTEX_BOUNDARY_REPAIR_JOURNAL_SCHEMA,
        "append_text": CORTEX_BOUNDARY_REPAIR_SUFFIX,
        "order": order,
        "action": "MIGRATE:cortex-boundary-repair",
        "arg1": "sia/cortex",
        "arg2": "product-metaphor-boundary-additive-v1",
        "content": _cortex_receipt_text(receipt),
    }
    _validate_cortex_repair_journal(journal)
    _write_cortex_repair_state(CORTEX_BOUNDARY_REPAIR_JOURNAL, journal)
    if _load_cortex_repair_journal() != journal:
        raise RuntimeError("cortex boundary repair journal did not persist")
    return _settle_cortex_boundary_repair(journal)

def ensure_entity(slug, ptype, title, body_lines):
    if page_exists(slug):
        return False
    write_page(slug,
               [f"type: {ptype}", fm_title(title)],
               f"# {title}\n\n" + "\n".join(body_lines) + "\n")
    return True

def ensure_organs():
    made = ensure_cortex()
    for key, (name, desc) in ORGANS.items():
        organ_slug = _canonical_corpus_slug(f"organs/{key}")
        safe_desc = inert_summary(desc)
        made |= ensure_entity(organ_slug, "organ", name, [
            f"{safe_desc}. Source adapter for [[sia/cortex]].", ""])
    return made


def day_slug(organ, date):
    return f"events/{organ}/{date}"


MAX_EVENT_BULLETS = 400
MAX_EVENT_SHARDS = 1024
MAX_EVENT_LOOKUP_PAGES = 4096
# directory inspection distinguishes a complete ceiling-sized snapshot from
# a source that exceeds the supported complete-snapshot capacity.
MAX_EVENT_DIRECTORY_INSPECTIONS = 4097
MAX_EVENT_PAGE_BYTES = 1_048_576
MAX_EVENT_INDEX_BYTES = 65_536
MAX_EVENT_INDEX_RECORDS = 65_536
MAX_EPOCH_SOURCE_RECORDS = MAX_EVENT_LOOKUP_PAGES
MAX_EPOCH_EVENT_IDS = MAX_EVENT_INDEX_RECORDS
MAX_EPOCH_PAGE_BYTES = MAX_EVENT_PAGE_BYTES
MAX_EPOCH_SOURCE_MANIFEST_BYTES = MAX_EPOCH_PAGE_BYTES
CONSOLIDATION_SCAN_SCHEMA = "sia-consolidation-scan-v1"
MAX_CONSOLIDATION_DAYS_PER_RUN = MAX_CONFIG_TAGS
MAX_CONSOLIDATION_DIRECTORY_QUEUE = MAX_EVENT_LOOKUP_PAGES
# one directory level below the events root.
MAX_CONSOLIDATION_TREE_LEVELS = 1
EVENT_INDEX_SCHEMA = "sia-consolidated-event-v1"
EPOCH_PAGE_NAME_RE = re.compile(
    r"^[0-9]{4}-w(?:0[1-9]|[1-4][0-9]|5[0-3])\.md$")
EVENT_MARKER_RE = re.compile(
    r"^- (?P<stamp>[0-9]{2}:[0-9]{2}:[0-9]{2}Z) (?P<payload>.*) "
    r"<!-- sia-event:(?P<id>[0-9a-f]{64})"
    r"(?::(?P<semantic>[0-9a-f]{64}))? -->$")
EVENT_SOURCE_RE = re.compile(
    r"^events/(?P<organ>[a-z0-9][a-z0-9._-]{0,199})/"
    r"(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})"
    r"(?:-part-(?P<part>[2-9][0-9]*))?\.md$")


class ConsolidationCapacityError(RuntimeError):
    """A bounded epoch cannot admit this group; retain its source days."""


class ConsolidationCompletenessError(RuntimeError):
    """An epoch cannot honestly extend without retained source evidence."""


def _parse_sia_counts(raw, label):
    try:
        counts = _strict_json_loads(raw)
    except (TypeError, UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError(f"{label} sia_counts is malformed") from exc
    if not isinstance(counts, dict) or any(
            not isinstance(key, str) or not key
            or sanitize_slugpart(key) != key
            or isinstance(value, bool) or not isinstance(value, int)
            or value < 0
            for key, value in counts.items()):
        raise ValueError(f"{label} sia_counts is invalid")
    return counts


def _event_shard_slug(organ, date, part):
    if isinstance(part, bool) or not isinstance(part, int) or part < 1:
        raise ValueError("event shard number is invalid")
    base = day_slug(organ, date)
    return base if part == 1 else f"{base}-part-{part}"


def _read_event_page(slug, *, expected_generation=None):
    """Read one bounded regular event page without following its leaf."""
    path = corpus_path(slug)
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        fd = (_open_source_nofollow(path, flags)
              if expected_generation is not None else os.open(path, flags))
    except OSError as exc:
        if expected_generation is not None:
            raise ValueError(f"event page changed before read: {slug}") from exc
        raise
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_size > MAX_EVENT_PAGE_BYTES:
            raise ValueError(f"event page is not a bounded regular file: {slug}")
        if expected_generation is not None \
                and _file_generation(before) != expected_generation:
            raise ValueError(f"event page changed before read: {slug}")
    except Exception:
        os.close(fd)
        raise
    with os.fdopen(fd, "rb") as stream:
        raw = stream.read(MAX_EVENT_PAGE_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_EVENT_PAGE_BYTES:
        raise ValueError(f"event page changed while read: {slug}")
    if expected_generation is not None:
        try:
            target = _source_path_identity(path, flags)
        except OSError as exc:
            raise ValueError(f"event page changed after read: {slug}") from exc
        if _file_generation(target) != expected_generation:
            raise ValueError(f"event page changed after read: {slug}")
    return raw.decode("utf-8", errors="strict")


def _bounded_event_directory_snapshot(
        directory, *, cleanup_legacy_atomic=False):
    """Return one complete event-directory snapshot or refuse its ceiling.

    Each raw directory page is independently bounded and generation-bound.
    The aggregate never crosses the event occurrence lookup ceiling; a
    mutation between pages refuses instead of turning a partial cycle into an
    absence or deletion claim.
    """
    entries = []
    page_state = None
    inspected_total = 0
    try:
        while True:
            remaining = MAX_EVENT_DIRECTORY_INSPECTIONS - inspected_total
            if remaining <= 0:
                raise ValueError(
                    "event occurrence lookup exceeds its page bound")
            page, complete, inspected, next_state = _bounded_source_entries(
                directory, page_state,
                min(remaining, MAX_SOURCE_SCAN_ENTRIES),
                cleanup_legacy_atomic=cleanup_legacy_atomic)
            if page_state is not None and next_state.get("reset", False):
                raise RuntimeError(
                    "event directory changed during its bounded snapshot")
            inspected_total += inspected
            entries.extend(page)
            if inspected_total > MAX_EVENT_LOOKUP_PAGES:
                raise ValueError(
                    "event occurrence lookup exceeds its page bound")
            if complete:
                break
            page_state = next_state
    except FileNotFoundError as exc:
        if page_state is None and not entries:
            return []
        raise RuntimeError(
            "event directory disappeared during its bounded snapshot") \
            from exc
    names = [entry["name"] for entry in entries]
    if len(names) != len(set(names)):
        raise RuntimeError("event directory snapshot repeated an entry")
    return sorted(entries, key=lambda entry: entry["name"])


def _event_page_state(organ, date, part, *, expected_generation=None):
    slug = _event_shard_slug(organ, date, part)
    text = _read_event_page(slug, expected_generation=expected_generation)
    match = FM_RE.match(text)
    if match is None:
        raise ValueError(f"existing event page lacks frontmatter: {slug}")
    fmtext = match.group(1)
    types = re.findall(r"^type:\s*(.*?)\s*$", fmtext, re.M)
    dates = re.findall(r"^date:\s*(.*?)\s*$", fmtext, re.M)
    if types != ["event-day"] or dates != [date]:
        raise ValueError(f"existing event page identity is invalid: {slug}")
    shard_values = re.findall(r"^sia_shard:\s*(.*?)\s*$", fmtext, re.M)
    if shard_values and shard_values != [str(part)]:
        raise ValueError(f"existing event page shard is invalid: {slug}")
    cm = re.search(r"^sia_counts: (.*)$", fmtext, re.M)
    if cm is None:
        raise ValueError(f"existing event page lacks sia_counts: {slug}")
    counts = _parse_sia_counts(cm.group(1), slug)
    tags = {organ}
    tm = re.search(r"^tags: \[(.*)\]$", fmtext, re.M)
    if tm:
        tags |= {tag.strip() for tag in tm.group(1).split(",")
                 if tag.strip()}
    body = text[match.end():]
    log_part = body.split("## Timeline", 1)[0]
    if "## Log" in log_part:
        log_part = log_part.split("## Log", 1)[1]
    bullets = [line for line in log_part.splitlines()
               if line.startswith("- ")]
    if len(bullets) > MAX_EVENT_BULLETS:
        raise ValueError(f"existing event shard exceeds its bound: {slug}")
    return {"slug": slug, "part": part, "counts": counts, "tags": tags,
            "bullets": bullets, "dirty": False}


def _event_day_shards(organ, date):
    base = day_slug(organ, date)
    base_path = corpus_path(base)
    root = os.path.dirname(base_path)
    entries = _bounded_event_directory_snapshot(root, cleanup_legacy_atomic=True)
    part_re = re.compile(
        rf"^{re.escape(os.path.basename(base_path[:-3]))}"
        r"-part-([2-9][0-9]*)\.md$")
    parts, generations = [], {}
    base_present = False
    for entry in entries:
        is_base = entry["name"] == os.path.basename(base_path)
        match = part_re.fullmatch(entry["name"])
        if not is_base and match is None:
            continue
        if not stat.S_ISREG(entry["mode"]):
            raise ValueError("event day page is not a regular file")
        part = 1 if is_base else int(match.group(1))
        generations[part] = tuple(entry[key] for key in (
            "device", "inode", "size", "mtime_ns", "ctime_ns"))
        if is_base:
            base_present = True
        else:
            parts.append(part)
    if len(parts) != len(set(parts)) or len(parts) >= MAX_EVENT_SHARDS \
            or any(part > MAX_EVENT_SHARDS for part in parts):
        raise ValueError("event day shard set is invalid or exceeds its bound")
    parts.sort()
    if base_present:
        if any(part != position for position, part in
               enumerate(parts, start=2)):
            raise ValueError("event day shards are not contiguous")
        return [_event_page_state(
            organ, date, part, expected_generation=generations[part])
            for part in [1] + parts]
    if parts:
        raise ValueError("event day has shards without its base page")
    return []


def _event_line(ev, event_id, semantic_id):
    stamp = ev.ts.strftime("%H:%M:%SZ")
    links = " ".join(
        f"[[{link}]]" for link in sorted(ev.links)
        if not link.startswith("organs/")
        and f"[[{link}" not in ev.summary)
    payload = ev.summary + (f" {links}" if links else "")
    base_line = f"- {stamp} {payload}"
    return (base_line
            + f" <!-- sia-event:{event_id}:{semantic_id} -->", payload,
            base_line)


def _render_event_shard(organ, date, shard):
    name = ORGANS.get(organ, (organ, ""))[0]
    part = shard["part"]
    title = f"{name} — {date}" + (f" — part {part}" if part > 1 else "")
    total = sum(shard["counts"].values())
    aggregate = ", ".join(
        f"{value}× {kind}" for kind, value in sorted(
            shard["counts"].items(), key=lambda item: -item[1])[:6])
    fm = ["type: event-day", fm_title(title),
          f"tags: [{', '.join(sorted(shard['tags']))}]", f"date: {date}",
          f"sia_shard: {part}",
          f"sia_counts: {json.dumps(shard['counts'], sort_keys=True)}"]
    if organ == "jackal":
        fm.insert(1, "origin: derived")
    body = (f"# {title}\n\n"
            f"What [[organs/{organ}]] reported to [[sia/cortex]] on {date}.\n\n"
            f"## Log\n" + "\n".join(shard["bullets"]) + "\n\n"
            f"## Timeline\n- **{date}** — {total} events in this shard: "
            f"{aggregate}\n")
    encoded = ("---\n" + "\n".join(fm) + "\n---\n" + body).encode(
        "utf-8")
    if len(encoded) > MAX_EVENT_PAGE_BYTES:
        raise ValueError("rendered event shard exceeds its byte bound")
    return fm, body


def _event_shard_trial(organ, date, shard, ev, line):
    trial = {"slug": shard["slug"], "part": shard["part"],
             "counts": dict(shard["counts"]), "tags": set(shard["tags"]),
             "bullets": list(shard["bullets"]), "dirty": True}
    trial["bullets"].append(line)
    trial["counts"][ev.kind] = trial["counts"].get(ev.kind, 0) + 1
    trial["tags"] |= ev.tags
    try:
        _render_event_shard(organ, date, trial)
    except ValueError as exc:
        if str(exc) == "rendered event shard exceeds its byte bound":
            return None
        raise
    return trial


def _event_source_parts(relative):
    """Return the canonical source/day/shard identity of an event source."""
    if not isinstance(relative, str):
        raise ValueError("event source path is invalid")
    match = EVENT_SOURCE_RE.fullmatch(relative)
    if match is None:
        raise ValueError("event source path is invalid")
    try:
        parsed = datetime.date.fromisoformat(match.group("date"))
    except ValueError as exc:
        raise ValueError("event source date is invalid") from exc
    if parsed.isoformat() != match.group("date"):
        raise ValueError("event source date is invalid")
    part = int(match.group("part") or "1")
    if part > MAX_EVENT_SHARDS:
        raise ValueError("event source shard exceeds its bound")
    return match.group("organ"), match.group("date"), part


def _event_payload_digest(payload):
    if not isinstance(payload, str):
        raise ValueError("event payload is invalid")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _event_index_relative(organ, event_id):
    if not isinstance(organ, str) \
            or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,199}", organ) is None \
            or not isinstance(event_id, str) \
            or re.fullmatch(r"[0-9a-f]{64}", event_id) is None:
        raise ValueError("consolidated event lookup identity is invalid")
    return os.path.join(
        "event-index", organ, event_id[:2], event_id + ".json")


def _canonical_event_index_entry(entry):
    required = {"schema", "organ", "event_id", "semantic_id",
                "payload_sha256", "source_rel", "source_sha256",
                "epoch_slug"}
    if not isinstance(entry, dict) or set(entry) != required \
            or entry.get("schema") != EVENT_INDEX_SCHEMA \
            or any(not isinstance(entry.get(key), str) for key in (
                "organ", "event_id", "payload_sha256", "source_rel",
                "source_sha256", "epoch_slug")) \
            or re.fullmatch(r"[0-9a-f]{64}", entry["event_id"]) is None \
            or re.fullmatch(
                r"[0-9a-f]{64}", entry["payload_sha256"]) is None \
            or re.fullmatch(
                r"[0-9a-f]{64}", entry["source_sha256"]) is None \
            or (entry["semantic_id"] is not None
                and (not isinstance(entry["semantic_id"], str)
                     or re.fullmatch(
                         r"[0-9a-f]{64}", entry["semantic_id"]) is None)):
        raise ValueError("consolidated event index entry is invalid")
    source_organ, source_date, _part = _event_source_parts(
        entry["source_rel"])
    year, week, _weekday = datetime.date.fromisoformat(
        source_date).isocalendar()
    expected_epoch = f"epochs/{source_organ}/{year}-w{week:02d}"
    if entry["organ"] != source_organ \
            or entry["epoch_slug"] != expected_epoch:
        raise ValueError("consolidated event index binding is invalid")
    return dict(entry)


def _event_index_encoded(entry):
    entry = _canonical_event_index_entry(entry)
    encoded = (json.dumps(
        entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n").encode("utf-8")
    if len(encoded) > MAX_EVENT_INDEX_BYTES:
        raise ValueError("consolidated event index entry exceeds its bound")
    return encoded


def _read_event_index_entry(organ, event_id):
    relative = _event_index_relative(organ, event_id)
    path = os.path.join(CORPUS, relative)
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None
    with siaqueue.regular_file_stream(
            fd, label="consolidated event index entry") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_size > MAX_EVENT_INDEX_BYTES:
            raise ValueError(
                "consolidated event index entry is not a bounded regular file")
        raw = stream.read(MAX_EVENT_INDEX_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_EVENT_INDEX_BYTES:
        raise ValueError("consolidated event index entry changed while read")
    try:
        entry = _strict_json_loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("consolidated event index entry is malformed") from exc
    entry = _canonical_event_index_entry(entry)
    if entry["organ"] != organ or entry["event_id"] != event_id \
            or raw != _event_index_encoded(entry):
        raise ValueError("consolidated event index path binding is invalid")
    epoch = _read_epoch_state(entry["epoch_slug"])
    source_record = {"rel": entry["source_rel"],
                     "sha256": entry["source_sha256"]}
    if entry["source_sha256"] not in epoch["sources"] \
            or source_record not in epoch["source_manifest"]:
        raise ValueError(
            "consolidated event index lacks exact epoch lineage")
    if epoch["event_ids_declared"] \
            and entry["event_id"] not in epoch["event_ids"]:
        raise ValueError(
            "consolidated event index lacks epoch completeness lineage")
    try:
        target = _source_path_identity(path, flags)
    except OSError as exc:
        raise ValueError("consolidated event index changed while validating") from exc
    if _file_generation(target) != finished:
        raise ValueError("consolidated event index changed while validating")
    return entry


def _preflight_event_index_entries(entries):
    if not isinstance(entries, list) \
            or len(entries) > MAX_EVENT_INDEX_RECORDS:
        raise ValueError("consolidated event index batch exceeds its bound")
    for entry in entries:
        entry = _canonical_event_index_entry(entry)
        existing = _read_event_index_entry(
            entry["organ"], entry["event_id"])
        if existing is not None and existing != entry:
            raise ValueError(
                "event identity conflicts with durable consolidation index")


def _publish_event_index_entries(entries):
    """Write every exact index entry before its source page may be unlinked."""
    _preflight_event_index_entries(entries)
    for entry in entries:
        existing = _read_event_index_entry(
            entry["organ"], entry["event_id"])
        if existing is not None:
            continue
        encoded = _event_index_encoded(entry)
        relative = _event_index_relative(entry["organ"], entry["event_id"])
        path = os.path.join(CORPUS, relative)
        _before_corpus_mutation()
        ensure_durable_directory(os.path.dirname(path))
        atomic_write(path, encoded.decode("utf-8"))


def _missing_event_index_expectations(organ, wanted):
    """Resolve missing leaves only from complete, bounded epoch manifests."""
    if not wanted:
        return {}
    if not isinstance(wanted, set) \
            or len(wanted) > MAX_EVENT_INDEX_RECORDS \
            or any(not isinstance(event_id, str)
                   or re.fullmatch(r"[0-9a-f]{64}", event_id) is None
                   for event_id in wanted):
        raise ValueError("event completeness lookup identity is invalid")
    root = os.path.join(CORPUS, "epochs", organ)
    entries = _bounded_event_directory_snapshot(root)
    found = {}
    for directory_entry in entries:
        name = directory_entry["name"]
        if EPOCH_PAGE_NAME_RE.fullmatch(name) is None:
            continue
        if not stat.S_ISREG(directory_entry["mode"]):
            raise ValueError(
                "epoch completeness source is not a regular file")
        slug = f"epochs/{organ}/{name[:-3]}"
        expected_generation = tuple(directory_entry[key] for key in (
            "device", "inode", "size", "mtime_ns", "ctime_ns"))
        epoch = _read_epoch_state(slug, expected_generation=expected_generation)
        if not epoch["source_manifest_declared"]:
            # Epochs predating exact source/index lineage cannot make a
            # completeness claim. They remain readable legacy summaries.
            continue
        if not epoch["event_ids_declared"]:
            raise ValueError(
                f"event-index completeness is unavailable: {slug}")
        for event_id in wanted.intersection(epoch["event_ids"]):
            prior = found.get(event_id)
            if prior is not None and prior != slug:
                raise ValueError(
                    "consolidated event identity occurs in multiple epochs")
            found[event_id] = slug
    return found


def _other_event_occurrences(organ, wanted, excluded):
    """Find source-native IDs already admitted on another recent day."""
    if not wanted:
        return {}
    if len(wanted) > MAX_EVENT_INDEX_RECORDS:
        raise ValueError("event occurrence lookup exceeds its identity bound")
    root = os.path.join(CORPUS, "events", organ)
    entries = _bounded_event_directory_snapshot(root, cleanup_legacy_atomic=True)
    found = {}
    page_re = re.compile(
        rf"^events/{re.escape(organ)}/[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}"
        r"(?:-part-[2-9][0-9]*)?$")
    for entry in entries:
        if not entry["name"].endswith(".md"):
            continue
        slug = f"events/{organ}/{entry['name'][:-3]}"
        if page_re.fullmatch(slug) is None:
            continue
        if not stat.S_ISREG(entry["mode"]):
            raise ValueError("event occurrence source is not a regular file")
        if slug in excluded:
            continue
        generation = tuple(entry[key] for key in (
            "device", "inode", "size", "mtime_ns", "ctime_ns"))
        text = _read_event_page(slug, expected_generation=generation)
        for line in text.splitlines():
            marker = EVENT_MARKER_RE.fullmatch(line)
            if marker is None:
                if "sia-event:" in line:
                    raise ValueError("event page contains a malformed identity")
                continue
            if marker.group("id") not in wanted:
                continue
            event_id = marker.group("id")
            prior = found.get(event_id)
            value = (slug, _event_payload_digest(marker.group("payload")),
                     marker.group("semantic"))
            if prior is not None and prior != value:
                raise ValueError("event identity occurs with conflicting bytes")
            found[event_id] = value
    missing = set()
    for event_id in sorted(wanted):
        entry = _read_event_index_entry(organ, event_id)
        if entry is None:
            missing.add(event_id)
            continue
        if event_id in found:
            raise ValueError(
                "event identity occurs in live and consolidated evidence")
        found[event_id] = (
            entry["epoch_slug"], entry["payload_sha256"],
            entry["semantic_id"])
    expected = _missing_event_index_expectations(organ, missing)
    if expected:
        event_id = sorted(expected)[0]
        raise ValueError(
            f"consolidated event index leaf is missing: {event_id}")
    return found


def _preflight_event_lookup(events):
    organs = {event.organ for event in events if event.occurrence}
    for organ in organs:
        root = os.path.join(CORPUS, "events", organ)
        _bounded_event_directory_snapshot(root, cleanup_legacy_atomic=True)


def _preflight_event_path_plan(planned_paths_by_organ):
    """Bound the union of every day planned for each source in this pulse."""
    for organ, planned_paths in planned_paths_by_organ.items():
        root = os.path.join(CORPUS, "events", organ)
        live_paths = {
            os.path.abspath(os.path.join(root, entry["name"]))
            for entry in _bounded_event_directory_snapshot(
                root, cleanup_legacy_atomic=True)
            if stat.S_ISREG(entry["mode"])
            and entry["name"].endswith(".md")}
        if len(live_paths | set(planned_paths)) > MAX_EVENT_LOOKUP_PAGES:
            raise ValueError(
                "event batch would exceed its bounded occurrence index")


def update_day_page(organ, date, new_events, *, dry_run=False):
    """Plan or append observations to immutable bounded day shards."""
    shards = _event_day_shards(organ, date)
    if not shards:
        shards = [{"slug": _event_shard_slug(organ, date, 1), "part": 1,
                   "counts": {}, "tags": {organ}, "bullets": [],
                   "dirty": False}]
    known_ids, legacy = {}, collections.defaultdict(list)
    for shard in shards:
        for index, line in enumerate(shard["bullets"]):
            marker = EVENT_MARKER_RE.fullmatch(line)
            if marker is None:
                if "sia-event:" in line:
                    raise ValueError("event page contains a malformed identity")
                legacy[line].append((shard, index))
                continue
            event_id = marker.group("id")
            if event_id in known_ids:
                raise ValueError("event identity is duplicated in day shards")
            known_ids[event_id] = (
                shard, marker.group("payload"), marker.group("semantic"))

    prepared = []
    stable_wanted = set()
    for ev in new_events:
        if not isinstance(ev, Event) or ev.organ != organ:
            raise ValueError("event does not belong to its day page")
        event_id = event_memory_identity(ev)
        semantic_id = event_semantic_identity(ev)
        line, payload, base_line = _event_line(ev, event_id, semantic_id)
        prepared.append((ev, event_id, semantic_id, line, payload, base_line))
        if ev.occurrence and event_id not in known_ids:
            stable_wanted.add(event_id)
    other_ids = _other_event_occurrences(
        organ, stable_wanted, {shard["slug"] for shard in shards})

    appended, admitted_pages, admitted_ids = [], [], set()
    batch_payloads = {}
    for ev, event_id, semantic_id, line, payload, base_line in prepared:
        prior_payload = batch_payloads.get(event_id)
        if prior_payload is not None \
                and prior_payload != (payload, semantic_id):
            raise ValueError("event identity conflicts within the input batch")
        batch_payloads[event_id] = (payload, semantic_id)
        existing = known_ids.get(event_id)
        if existing is not None:
            shard, stored_payload, stored_semantic = existing
            if stored_payload != payload or stored_semantic != semantic_id:
                raise ValueError("event identity conflicts with its day page")
            admitted_slug = shard["slug"]
        elif event_id in other_ids:
            admitted_slug, stored_payload_digest, stored_semantic = \
                other_ids[event_id]
            if stored_payload_digest != _event_payload_digest(payload) \
                    or stored_semantic != semantic_id:
                raise ValueError("event identity conflicts with another day page")
        elif legacy.get(base_line):
            raise ValueError(
                "legacy event cannot be identity-upgraded automatically")
        else:
            shard = shards[-1]
            if len(shard["bullets"]) >= MAX_EVENT_BULLETS:
                part = shard["part"] + 1
                if part > MAX_EVENT_SHARDS:
                    raise ValueError("event day exceeds its shard bound")
                shard = {"slug": _event_shard_slug(organ, date, part),
                         "part": part, "counts": {}, "tags": {organ},
                         "bullets": [], "dirty": False}
                shards.append(shard)
            trial = _event_shard_trial(organ, date, shard, ev, line)
            if trial is None and shard["bullets"]:
                part = shard["part"] + 1
                if part > MAX_EVENT_SHARDS:
                    raise ValueError("event day exceeds its shard bound")
                shard = {"slug": _event_shard_slug(organ, date, part),
                         "part": part, "counts": {}, "tags": {organ},
                         "bullets": [], "dirty": False}
                shards.append(shard)
                trial = _event_shard_trial(organ, date, shard, ev, line)
            if trial is None:
                raise ValueError("one event exceeds the event shard byte bound")
            shard.update(trial)
            known_ids[event_id] = (shard, payload, semantic_id)
            appended.append(ev)
            admitted_slug = shard["slug"]
        if event_id not in admitted_ids:
            admitted_ids.add(event_id)
            admitted_pages.append((ev, admitted_slug))

    # Render every target before the first mutation. Sequential atomic writes
    # are then replayable: an interrupted prefix already contains exact IDs.
    organ_root = os.path.join(CORPUS, "events", organ)
    live_paths = {
        os.path.abspath(os.path.join(organ_root, entry["name"]))
        for entry in _bounded_event_directory_snapshot(
            organ_root, cleanup_legacy_atomic=True)
        if stat.S_ISREG(entry["mode"])
        and entry["name"].endswith(".md")}
    planned_paths = {
        os.path.abspath(corpus_path(shard["slug"])) for shard in shards}
    if len(live_paths | planned_paths) > MAX_EVENT_LOOKUP_PAGES:
        raise ValueError(
            "event organ would exceed its bounded occurrence index")
    rendered = [(shard, _render_event_shard(organ, date, shard))
                for shard in shards if shard["dirty"]]
    if not dry_run:
        for shard, (frontmatter, body) in rendered:
            write_page(shard["slug"], frontmatter, body)
    return [shard["slug"] for shard in shards], appended, admitted_pages


def ensure_event_entities(events):
    """Create referenced entity pages (units/packages/projects) lazily."""
    made = False
    for ev in events:
        for l in ev.links:
            if l.startswith("units/"):
                made |= ensure_entity(l, "unit", l.split("/", 1)[1],
                                      [f"systemd unit observed by [[organs/{ev.organ}]].", ""])
            elif l.startswith("packages/"):
                made |= ensure_entity(l, "package", l.split("/", 1)[1],
                                      ["Arch package seen in [[organs/pacman]] events.", ""])
            elif l.startswith("projects/"):
                made |= ensure_entity(l, "project", l.split("/", 1)[1],
                                      ["Repository under ~/Projects. Watched by [[organs/projects]].", ""])
            elif l.startswith("skills/"):
                name = l.split("/", 1)[1]
                made |= ensure_entity(l, "skill", name,
                                      ["Agent skill installed on this box. "
                                       "Watched by [[organs/skills]].", ""])
    return made




# Generated-entry/epoch materialization, compaction, recovery, and legacy replay
# live in `siathought` (see its docstring and docs/ARCHITECTURE.md). Its façade
# preserves parent-owned state, constants and exception identity. Generator
# contexts bind at both protocol boundaries, and the legacy directory reader
# reuses the generic parent-owned `_SOURCE_LIBC` through the same binding seam.
import siathought as _siathought


def _sialib_thought_delegate(name):
    """Return a façade that binds this sialib instance before every call."""
    target = _siathought._ORIGINAL_CHILD_FUNCTIONS[name]

    @functools.wraps(target)
    def delegated(*args, **kwargs):
        return _siathought.invoke(globals(), name, *args, **kwargs)

    delegated._sia_senses_delegate = True
    return delegated


_siathought.bind(globals())
for _sialib_thought_name in _siathought._EXPORTED_FUNCTIONS:
    globals()[_sialib_thought_name] = _sialib_thought_delegate(
        _sialib_thought_name)
del _sialib_thought_name




# ---------------------------------------------------------------- gbrain

class _FailedRun:
    returncode = -1
    stdout = ""

    def __init__(self, reason="subprocess failed/timed out"):
        self.stderr = str(reason)[:240]


# Alias the exact state ceiling declared above; stdout and stderr share
# this one aggregate budget rather than receiving independent allowances.
MAX_EXTERNAL_OUTPUT_BYTES = MAX_STATE_JSON_BYTES
MAX_GBRAIN_OUTPUT_BYTES = MAX_EXTERNAL_OUTPUT_BYTES


def _run_bounded_text_process(command, *, env, timeout, cwd, pass_fds=(),
                              label="subprocess", output_limit=None,
                              isolate_process_tree=False,
                              retain_output=True):
    """Run one external reader with bounded combined output and lifetime.

    stdout and stderr are drained concurrently so neither pipe can deadlock the
    other.  Every producer runs in a fresh process group.  Callers accepting an
    operator-supplied executable can additionally request a private PID
    namespace: its init process dying removes descendants even if one calls
    ``setsid()`` and closes the inherited pipes.  Without that namespace, only
    the original process group is contained. Retained text is admitted as
    strict UTF-8; discard mode drains and counts bytes without accumulating or
    decoding them.
    """
    if not isinstance(command, (list, tuple)) or not command \
            or any(not isinstance(part, (str, bytes, os.PathLike))
                   for part in command):
        raise ValueError("bounded subprocess command is invalid")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) \
            or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("bounded subprocess timeout is invalid")
    if not isinstance(label, str) or not label \
            or len(label) > MAX_SOURCE_NAME_CHARS:
        raise ValueError("bounded subprocess label is invalid")
    if output_limit is None:
        output_limit = MAX_EXTERNAL_OUTPUT_BYTES
    if isinstance(output_limit, bool) or not isinstance(output_limit, int) \
            or output_limit <= 0 or output_limit > MAX_STATE_JSON_BYTES:
        raise ValueError("bounded subprocess output limit is invalid")
    if not isinstance(isolate_process_tree, bool):
        raise ValueError("bounded subprocess isolation mode is invalid")
    if not isinstance(retain_output, bool):
        raise ValueError("bounded subprocess output-retention mode is invalid")
    original_command = list(command)
    launch_command = original_command
    if isolate_process_tree:
        launch_command = [
            "/usr/bin/unshare", "--user", "--map-root-user", "--pid",
            "--fork", "--kill-child", "--mount-proc", "--",
            *original_command]
    process = None
    group_reaped = False
    selector = selectors.DefaultSelector()
    streams = {}
    try:
        process = subprocess.Popen(
            launch_command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, cwd=cwd,
            pass_fds=tuple(pass_fds), close_fds=True,
            start_new_session=True, text=False)
        if process.stdout is None or process.stderr is None:
            raise RuntimeError("bounded subprocess did not provide output pipes")
        streams = {
            process.stdout: bytearray() if retain_output else None,
            process.stderr: bytearray() if retain_output else None,
        }
        for stream in streams:
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        captured = 0
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(original_command, timeout)
            ready = selector.select(remaining)
            if not ready:
                raise subprocess.TimeoutExpired(original_command, timeout)
            for key, _events in ready:
                stream = key.fileobj
                budget = output_limit - captured
                try:
                    block = os.read(
                        stream.fileno(), min(MAX_CONFIG_BYTES, budget + 1))
                except BlockingIOError:
                    continue
                if not block:
                    selector.unregister(stream)
                    stream.close()
                    continue
                if len(block) > budget:
                    raise OverflowError(
                        f"{label} output exceeded its combined byte limit")
                if retain_output:
                    streams[stream].extend(block)
                captured += len(block)
        _await_process_exit_unreaped(
            process, deadline, original_command, timeout)
        returncode = _signal_and_reap_process_group(
            process, JOURNAL_TIMEOUT_SECONDS)
        group_reaped = True
        if returncode is None:
            raise subprocess.TimeoutExpired(original_command, timeout)
        stdout = (bytes(streams[process.stdout]).decode(
            "utf-8", errors="strict") if retain_output else "")
        stderr = (bytes(streams[process.stderr]).decode(
            "utf-8", errors="strict") if retain_output else "")
        return subprocess.CompletedProcess(
            original_command, returncode, stdout=stdout, stderr=stderr)
    finally:
        selector.close()
        if process is not None and not group_reaped:
            # Signal while the unreaped leader still owns its PID/PGID.  This
            # avoids both descendant escape and a post-reap PID-reuse race.
            _signal_and_reap_process_group(
                process, JOURNAL_TIMEOUT_SECONDS)


@contextlib.contextmanager
def gbrain_owner():
    """One cross-process owner for every SIA-managed PGLite invocation.

    The daemon, CLI, benchmark, and MCP-derived reads all enter through this
    lease. Agent writes never do: they spool requests for the daemon. Advisory
    locking cannot constrain unrelated programs that bypass SIA, but it closes
    contention among every runtime shipped by this project.
    """
    inherited = _GBRAIN_OWNER_FD.get()
    if inherited is not None:
        yield inherited
        return
    with _owner_lease(GBRAIN_OWNER_LOCK, "SIA PGLite") as owner_fd:
        token = _GBRAIN_OWNER_FD.set(owner_fd)
        try:
            yield owner_fd
        finally:
            _GBRAIN_OWNER_FD.reset(token)

def gbrain(args, timeout=120, json_out=False):
    try:
        with gbrain_owner() as owner_fd:
            r = _run_bounded_text_process(
                [GBRAIN] + args, env=GBRAIN_ENV, timeout=timeout, cwd=CORPUS,
                pass_fds=(owner_fd,), label="gbrain",
                output_limit=MAX_GBRAIN_OUTPUT_BYTES)
    except Exception as exc:
        if isinstance(exc, UnicodeError):
            reason = "gbrain output is not valid UTF-8"
        elif isinstance(exc, subprocess.TimeoutExpired):
            reason = "gbrain subprocess timed out"
        else:
            reason = str(exc) or "gbrain subprocess failed"
        r = _FailedRun(reason)
    if json_out:
        try:
            return _strict_json_loads(
                r.stdout[r.stdout.index("["):] if "[" in r.stdout
                else r.stdout)
        except Exception:
            try:
                return _strict_json_loads(r.stdout[r.stdout.index("{"):])
            except Exception:
                return None
    return r


def _gbrain_call_unlocked(op, params, timeout=120, owner_fd=None):
    """Call one gbrain operation while the caller owns the engine lease."""
    try:
        r = _run_bounded_text_process(
            [GBRAIN, "call", "--source", GBRAIN_SOURCE, op,
             json.dumps(params)],
            env=GBRAIN_ENV, timeout=timeout, cwd=CORPUS,
            pass_fds=((owner_fd,) if owner_fd is not None else ()),
            label="gbrain", output_limit=MAX_GBRAIN_OUTPUT_BYTES)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    out = r.stdout
    for opener in ("[", "{"):
        i = out.find(opener)
        if i >= 0:
            try:
                return _strict_json_loads(out[i:])
            except Exception:
                continue
    return None


def gbrain_call(op, params, timeout=120):
    with gbrain_owner() as owner_fd:
        return _gbrain_call_unlocked(
            op, params, timeout=timeout, owner_fd=owner_fd)


def gbrain_all_pages(batch_size=500):
    """Advance and return SIA's bounded corpus-native graph window.

    The former implementation held the PGLite lease while materializing every
    page.  A resident corpus has no natural upper bound, so graph publication
    now advances one durable corpus directory page and retains only the fixed
    cockpit window.  The compatibility tuple remains ``(pages, complete,
    failure_reason)``; ``complete`` refers to the current projection
    generation, never to a partial scan being treated as absence.
    """
    return _graph_projection_pages(batch_size)


def corpus_commit(msg):
    """Tri-state: 'committed' | 'clean' (nothing to commit) | 'error'."""
    try:
        staged = _run_bounded_text_process(
            ["git", "add", "-A"], env=None, timeout=60, cwd=CORPUS,
            label="git add")
        if staged.returncode != 0:
            return "error"
        # After add, the cached diff exit status answers clean/dirty without
        # materializing one path per corpus page in the resident process.
        staged_diff = _run_bounded_text_process(
            ["git", "diff", "--cached", "--quiet", "--no-ext-diff", "--"],
            env=None, timeout=60, cwd=CORPUS, label="git staged diff")
        if staged_diff.returncode == 0:
            return "clean"
        if staged_diff.returncode != 1:
            return "error"
        r = _run_bounded_text_process(
            ["git", "-c", "user.email=sia@omarchy.local",
             "-c", "user.name=SIA", "commit", "-q", "-m", msg],
            env=None, timeout=60, cwd=CORPUS, label="git commit")
        return "committed" if r.returncode == 0 else "error"
    except Exception:
        return "error"


def corpus_dirty():
    """Whether the corpus has a staged, modified, deleted, or untracked page."""
    try:
        status = _run_bounded_text_process(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            env=None, timeout=60, cwd=CORPUS, label="git status")
        return bool(status.stdout.strip()) if status.returncode == 0 else None
    except Exception:
        return None


def brain_sync():
    args = ["sync", "--source", "sia"]
    if os.environ.get("SIA_RESTORE_FULL_SYNC") == "1":
        # A restored Git history may be older than, or unrelated to, the
        # destination PGLite bookmark. Incremental sync is not a recovery
        # proof; the restore worker requests one complete reconciliation.
        args.append("--full")
    r = gbrain(args, timeout=300)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout)[-400:]
    # sync does not run link extraction — materialize explicit corpus links
    # first, then retain gbrain's built-in gazetteer lane for unlinked
    # person/company/organization/entity mentions.  SIA-specific entity types
    # are handled from explicit wikilinks by corpus_edges below; neither lane
    # weakens or impersonates the other.
    x = gbrain(["extract", "links", "--source", "db", "--stale", "--json"],
               timeout=300)
    if x.returncode != 0:
        return False, "extract: " + (x.stderr or x.stdout)[-300:]
    n = gbrain(["extract", "links", "--by-mention", "--ner",
                "--source", "db", "--source-id", "sia", "--json"],
               timeout=300)
    if n.returncode != 0:
        return False, "ner: " + (n.stderr or n.stdout)[-300:]
    return True, ""


# ---------------------------------------------------------------- integrity

AEGIS_LEDGER_TOOL = os.path.join(
    HOME, ".config/omarchy/plugins/khephri.aegis/bin/aegis-ledger")
INVALID_CHAIN_SENTINEL = "__sia_invalid_chain_config__"


def _invalid_chain_binding(chains, entry, reason):
    """Materialize a configured-chain refusal instead of shrinking scope."""
    encoded = json.dumps(entry, sort_keys=True, default=str,
                         separators=(",", ":")).encode()
    name = "config-error-" + hashlib.sha256(encoded).hexdigest()[:12]
    while name in chains:
        name += "-duplicate"
    chains[name] = ("", "", [INVALID_CHAIN_SENTINEL, reason])


def _chain_verifier_binding_error(tool, command):
    """Return a refusal reason unless ``tool`` is what ``command`` executes.

    A digest can bind the direct executable, or a Python script passed as the
    interpreter's immediate script operand.  Merely mentioning the verifier
    later in argv does not bind the program whose exit status is trusted.
    Exact path spelling also keeps an unobserved alias out of the execution
    path; the benchmark separately observes ``tool`` without following its
    final path component.
    """
    if not isinstance(tool, str) or not tool or not os.path.isabs(tool):
        return "verifier must be an absolute path"
    if not isinstance(command, (list, tuple)) or not command \
            or any(not isinstance(arg, str) or not arg for arg in command):
        return "verify must be a non-empty string argv list"
    positions = [index for index, arg in enumerate(command) if arg == tool]
    if positions == [0]:
        return None
    python = sys.executable
    if positions == [1] and python and os.path.isabs(python) \
            and os.path.isabs(command[0]) \
            and os.path.realpath(command[0]) == os.path.realpath(python):
        return None
    return ("verifier must be exactly the executed program or the immediate "
            "script operand of the current Python interpreter")


_CHAIN_INPUT_KEYS = frozenset({"argv_index", "path", "prefix"})


def _normalize_chain_binding(binding):
    """Return one registry binding with an explicit auxiliary-input tuple."""
    if not isinstance(binding, (list, tuple)) or len(binding) not in (3, 4):
        raise ValueError("chain binding must contain three or four fields")
    ledger, tool, command = binding[:3]
    inputs = () if len(binding) == 3 else binding[3]
    return ledger, tool, command, inputs


def _chain_reserved_argv_indexes(ledger, tool, command):
    """Classify executable, ledger, and admitted state-root argv positions."""
    if not isinstance(ledger, str) or not ledger or not os.path.isabs(ledger):
        raise ValueError("chain ledger must be an absolute path")
    if _chain_verifier_binding_error(tool, command):
        raise ValueError(_chain_verifier_binding_error(tool, command))
    python_script = len(command) > 1 and command[1] == tool
    executable = {0, 1} if python_script else {0}
    ledger_indexes = {
        index for index, part in enumerate(command) if part == ledger}
    if len(ledger_indexes) > 1:
        raise ValueError("chain ledger argv occurrence is duplicated")
    if ledger_indexes & executable:
        raise ValueError(
            "chain ledger argv occurrence collides with executable")
    state_directory = os.path.dirname(os.path.abspath(ledger))
    state_indexes = {
        index for index, part in enumerate(command)
        if part == state_directory}
    if len(state_indexes) > 1:
        raise ValueError("chain state argv occurrence is duplicated")
    return executable | ledger_indexes | state_indexes, state_directory


def _validated_chain_inputs(inputs, command, reserved_indexes=()):
    """Validate and canonicalize exact auxiliary-file argv declarations."""
    if not isinstance(inputs, (list, tuple)):
        raise ValueError("inputs must be a list")
    if len(inputs) > MAX_CONFIG_TAGS:
        raise ValueError("inputs exceed their configured count bound")
    indexes = set()
    paths = set()
    canonical = []
    for entry in inputs:
        if not isinstance(entry, dict):
            raise ValueError("input entry must be an object")
        unknown = sorted(set(entry) - _CHAIN_INPUT_KEYS)
        if unknown:
            raise ValueError(
                "input entry has unknown keys: "
                + ", ".join(str(key) for key in unknown))
        if "argv_index" not in entry or "path" not in entry:
            raise ValueError("input entry requires argv_index and path")
        index = entry["argv_index"]
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError("argv_index must be an integer")
        if index < 0 or index >= len(command):
            raise ValueError("argv_index is out of range")
        if index in indexes:
            raise ValueError("argv_index is duplicated")
        if index in reserved_indexes:
            raise ValueError("input index is reserved")
        raw_path = entry["path"]
        prefix = entry.get("prefix", "")
        if not _strict_config_string(
                raw_path, nonempty=True, limit=MAX_CONFIG_PATH_CHARS) \
                or "\x00" in raw_path:
            raise ValueError("input path must be a bounded string")
        if not _strict_config_string(
                prefix, limit=MAX_CONFIG_TEXT_CHARS) or "\x00" in prefix:
            raise ValueError("input prefix must be a bounded string")
        if prefix and re.fullmatch(
                r"--[a-z][a-z0-9-]*=", prefix) is None:
            raise ValueError(
                "input prefix must be empty or match --long-option=")
        path = os.path.expanduser(raw_path)
        if not os.path.isabs(path):
            raise ValueError("input path must be absolute")
        if len(path) > MAX_CONFIG_PATH_CHARS:
            raise ValueError("input path exceeds its configured bound")
        if command[index] != prefix + raw_path:
            raise ValueError("input entry does not match verify argv")
        normalized = os.path.normpath(path)
        if normalized != path:
            raise ValueError("input path must use canonical absolute spelling")
        if normalized in paths:
            raise ValueError("input path is duplicated")
        indexes.add(index)
        paths.add(normalized)
        canonical.append({
            "argv_index": index, "path": path, "prefix": prefix})
    return tuple(sorted(canonical, key=lambda entry: entry["argv_index"]))


def _chain_operand_is_closed_literal(value):
    """Admit only slashless, unambiguous non-file verifier literals."""
    return isinstance(value, str) and re.fullmatch(
        r"(?:--?[A-Za-z0-9][A-Za-z0-9-]*|[A-Za-z0-9][A-Za-z0-9_-]*)",
        value) is not None


def _canonical_chain_launch_contract(name, ledger, tool, command, inputs):
    """Admit one verifier argv and return its explicit launch roles."""
    binding_error = _chain_verifier_binding_error(tool, command)
    if binding_error:
        raise ValueError(binding_error)
    original = list(command)
    reserved, state_directory = _chain_reserved_argv_indexes(
        ledger, tool, original)
    manifest = _validated_chain_inputs(inputs, original, reserved)
    declared = {entry["argv_index"] for entry in manifest}
    for index, part in enumerate(original):
        if index in reserved or index in declared:
            continue
        if not _chain_operand_is_closed_literal(part):
            raise ValueError(
                "verify argv path operand must be declared in inputs")
    implicit = _is_implicit_sekhmet_chain(name, ledger, tool, original)
    return original, manifest, reserved, state_directory, implicit


def _chain_launch_provenance(name, ledger, tool, command, inputs=()):
    """Return a path-redacted canonical description of admitted verifier argv."""
    original, manifest, _reserved, state_directory, implicit = \
        _canonical_chain_launch_contract(
            name, ledger, tool, command, inputs)
    python_script = len(original) > 1 and original[1] == tool
    declared = {entry["argv_index"]: entry for entry in manifest}
    argv = []
    for index, part in enumerate(original):
        if index == 0:
            role = ("current-python-interpreter"
                    if python_script else "verifier")
            argv.append({"role": role})
        elif python_script and index == 1:
            argv.append({"role": "verifier"})
        elif index in declared:
            argv.append({
                "role": "declared-input",
                "argv_index": index,
                "prefix": declared[index]["prefix"],
            })
        elif part == ledger:
            argv.append({"role": "ledger"})
        elif os.path.isabs(part) \
                and os.path.abspath(part) == state_directory:
            argv.append({"role": "state-directory"})
        else:
            argv.append({"literal": part})
    return {
        "schema": "sia-chain-launch-contract-v1",
        "execution": ("current-python-script" if python_script else "direct"),
        "implicit_private_state": implicit,
        "argv": argv,
    }


_CHAIN_GENERATION_STAT_FIELDS = (
    "st_dev", "st_ino", "st_mode", "st_uid", "st_size", "st_mtime_ns",
    "st_ctime_ns")


def _open_chain_generation(path, label):
    """Pin one regular chain file and return its mutation-sensitive identity."""
    flags = getattr(os, "O_PATH", os.O_RDONLY) \
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = _open_source_nofollow(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(f"{label} is not a regular file")
        generation = tuple(
            getattr(info, field) for field in _CHAIN_GENERATION_STAT_FIELDS)
        return descriptor, generation
    except Exception:
        os.close(descriptor)
        raise


def _open_chain_directory_generation(path, label):
    """Pin one no-follow directory ancestry used by a chain verifier."""
    flags = getattr(os, "O_PATH", os.O_RDONLY) \
        | getattr(os, "O_DIRECTORY", 0) \
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = _open_source_nofollow(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode):
            raise OSError(f"{label} is not a directory")
        generation = tuple(
            getattr(info, field) for field in _CHAIN_GENERATION_STAT_FIELDS)
        return descriptor, generation
    except Exception:
        os.close(descriptor)
        raise


def _chain_descriptor_path(descriptor):
    """Name an inherited descriptor without returning to its source path."""
    path = f"/proc/self/fd/{descriptor}"
    if not os.path.exists(path):
        raise OSError("descriptor-backed chain execution is unavailable")
    return path


def _chain_generation_matches(record, *, rebind=True):
    """Check a pinned object and, optionally, its original no-follow name."""
    current = tuple(
        getattr(os.fstat(record["fd"]), field)
        for field in _CHAIN_GENERATION_STAT_FIELDS)
    if current != record["generation"]:
        return False
    if not rebind:
        return True
    opener = (_open_chain_directory_generation
              if record["directory"] else _open_chain_generation)
    rebound = None
    try:
        rebound, generation = opener(record["path"], record["label"])
        return generation == record["generation"]
    except Exception:
        return False
    finally:
        if rebound is not None:
            os.close(rebound)


def _chain_generation_still_named(record):
    """Re-open one retained generation after the complete verifier batch."""
    opener = (_open_chain_directory_generation
              if record["directory"] else _open_chain_generation)
    descriptor = None
    try:
        descriptor, generation = opener(record["path"], record["label"])
        return generation == record["generation"]
    except Exception:
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _copy_chain_snapshot_file(record, destination, remaining):
    """Copy exact bytes from a pinned file into one private verifier view."""
    if isinstance(remaining, bool) or not isinstance(remaining, int) \
            or remaining < 0:
        raise ValueError("chain snapshot byte budget is invalid")
    source = os.open(
        _chain_descriptor_path(record["fd"]), os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0))
    target = None
    total = 0
    try:
        before = os.fstat(source)
        if tuple(getattr(before, field)
                 for field in _CHAIN_GENERATION_STAT_FIELDS) \
                != record["generation"] or before.st_size > remaining:
            raise OSError("chain snapshot source changed or exceeds its bound")
        if before.st_uid != os.geteuid():
            raise OSError("chain snapshot source is not owner-controlled")
        if before.st_nlink != 1:
            raise OSError("chain snapshot source is not single-link")
        target = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0),
            stat.S_IMODE(before.st_mode))
        os.fchmod(target, stat.S_IMODE(before.st_mode))
        while total <= remaining:
            block = os.read(source, min(MAX_CONFIG_BYTES,
                                        remaining + 1 - total))
            if not block:
                break
            view = memoryview(block)
            while view:
                written = os.write(target, view)
                if written <= 0:
                    raise OSError("short write while copying chain snapshot")
                view = view[written:]
            total += len(block)
        if total > remaining:
            raise OSError("chain snapshot source exceeds its byte bound")
        os.fsync(target)
        after = os.fstat(source)
        if tuple(getattr(after, field)
                 for field in _CHAIN_GENERATION_STAT_FIELDS) \
                != record["generation"] or total != before.st_size:
            raise OSError("chain snapshot source changed while copied")
        return total
    finally:
        os.close(source)
        if target is not None:
            os.close(target)


def _is_implicit_sekhmet_chain(name, ledger, tool, command):
    expected_tool = os.path.join(HOME, ".local/bin/sekhmet")
    expected_ledger = os.path.join(
        HOME, ".local/share/sekhmet/ledger.tsv")
    return name == "sekhmet" and tool == expected_tool \
        and ledger == expected_ledger and list(command[:3]) == [
            tool, "ledger", "verify"]


@contextlib.contextmanager
def _bound_chain_verification(name, ledger, tool, command, inputs=()):
    """Bind the verifier launch to the objects observed by its caller.

    Direct executables, current-Python scripts, and explicit file operands are
    named through inherited pinned descriptors. State-directory operands get
    a private byte-for-byte view copied from pinned descriptors. The built-in
    verifier with an implicit HOME-relative state directory receives the same
    private view, because its successful check rewrites its rollback pin.
    Directory ancestry, declared files, and every known sidecar generation are
    held and checked before the result is admitted. This does not remove the
    documented same-user in-place ABA boundary between observations.
    """
    original_command, input_manifest, _reserved_indexes, \
        state_directory, implicit_sekhmet = \
        _canonical_chain_launch_contract(
            name, ledger, tool, command, inputs)
    if any(part.startswith("/proc/self/fd/")
           for part in original_command):
        raise ValueError("chain verifier argv contains an opaque descriptor")
    command = list(original_command)
    descriptors = []
    child_descriptors = []
    records = []
    bound_records = {}
    temporary = None

    def bind(path, label, *, directory=False, aggregate=True,
             inherit=False):
        key = (path, directory)
        if key in bound_records:
            record = bound_records[key]
            if inherit and record["fd"] not in child_descriptors:
                child_descriptors.append(record["fd"])
            return record
        opener = (_open_chain_directory_generation
                  if directory else _open_chain_generation)
        descriptor, generation = opener(path, label)
        descriptors.append(descriptor)
        record = {
            "path": path, "label": label, "directory": directory,
            "fd": descriptor, "generation": generation,
            "aggregate": aggregate,
        }
        records.append(record)
        bound_records[key] = record
        if inherit:
            child_descriptors.append(descriptor)
        return record

    def bind_existing_sidecars(state_directory):
        for basename in ("pub.hex", "head.pin", "ledger.pending",
                         "ledger.lock"):
            path = os.path.join(state_directory, basename)
            try:
                bind(path, f"{name} chain {basename}")
            except FileNotFoundError:
                continue

    try:
        temporary = tempfile.TemporaryDirectory(prefix="sia-chain-")
        private_home = os.path.join(temporary.name, "home")
        private_tmp = os.path.join(temporary.name, "tmp")
        private_cwd = os.path.join(temporary.name, "cwd")
        private_inputs = os.path.join(temporary.name, "inputs")
        for directory in (
                private_home, private_tmp, private_cwd, private_inputs):
            os.makedirs(directory, mode=0o700)
        private_input_remaining = MAX_LEDGER_PENDING_BYTES
        environment = {
            "HOME": private_home,
            "TMPDIR": private_tmp,
            "PATH": os.defpath,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        tool_record = bind(
            tool, f"{name} chain verifier", inherit=True)
        ledger_record = bind(
            ledger, f"{name} chain ledger")
        tool_fd_path = _chain_descriptor_path(tool_record["fd"])
        ledger_launch_record = ledger_record
        if ledger in original_command:
            private_ledger = os.path.join(private_inputs, "ledger")
            used = _copy_chain_snapshot_file(
                ledger_record, private_ledger, private_input_remaining)
            private_input_remaining -= used
            ledger_launch_record = bind(
                private_ledger, f"{name} private ledger",
                aggregate=False, inherit=True)
        ledger_fd_path = _chain_descriptor_path(ledger_launch_record["fd"])

        python_script = len(command) > 1 and command[1] == tool
        if python_script:
            interpreter_path = os.path.realpath(sys.executable)
            interpreter_record = bind(
                interpreter_path, "current Python interpreter", inherit=True)
            running = os.stat("/proc/self/exe")
            pinned = os.fstat(interpreter_record["fd"])
            if (running.st_dev, running.st_ino) != (
                    pinned.st_dev, pinned.st_ino):
                raise OSError("current Python interpreter identity changed")
            command[0] = _chain_descriptor_path(interpreter_record["fd"])
            command[1] = tool_fd_path
        else:
            command[0] = tool_fd_path

        state_arguments = {
            part for part in original_command
            if os.path.isabs(part)
            and os.path.abspath(part) == state_directory
        }
        state_argument = bool(state_arguments)
        snapshot_state = None
        if state_argument or implicit_sekhmet:
            state_record = bind(
                state_directory, f"{name} chain state", directory=True)
            state_info = os.fstat(state_record["fd"])
            if state_info.st_uid != os.geteuid():
                raise OSError("chain state is not owned by this user")
            bind_existing_sidecars(state_directory)
            snapshot_home = private_home
            snapshot_state = (os.path.join(
                snapshot_home, ".local", "share", "sekhmet")
                if implicit_sekhmet
                else os.path.join(temporary.name, "state"))
            os.makedirs(snapshot_state, mode=0o700)
            remaining = MAX_LEDGER_PENDING_BYTES
            for basename in (
                    "ledger.tsv", "pub.hex", "head.pin",
                    "ledger.pending", "ledger.lock"):
                source = bound_records.get(
                    (os.path.join(state_directory, basename), False))
                if source is None:
                    continue
                destination = os.path.join(snapshot_state, basename)
                used = _copy_chain_snapshot_file(
                    source, destination, remaining)
                remaining -= used
                # The implicit verifier advances its rollback pin after a
                # successful replay. Other captured inputs must remain the
                # exact private generation supplied to the child.
                if basename != "ledger.lock" \
                        and not (implicit_sekhmet
                                 and basename == "head.pin"):
                    bind(destination, f"{name} private {basename}",
                         aggregate=False)
            lock_path = os.path.join(snapshot_state, "ledger.lock")
            if not os.path.exists(lock_path):
                lock_fd = os.open(
                    lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0), 0o600)
                os.close(lock_fd)
            os.chmod(snapshot_state, stat.S_IMODE(state_info.st_mode))
            if not implicit_sekhmet:
                bind(snapshot_state, f"{name} private state",
                     directory=True, aggregate=False)
                command = [snapshot_state if part in state_arguments else part
                           for part in command]

        command = [ledger_fd_path if part == ledger else part
                   for part in command]
        identities = {
            (os.fstat(record["fd"]).st_dev, os.fstat(record["fd"]).st_ino)
            for record in records if not record["directory"]}
        for declared in input_manifest:
            operand = bind(
                declared["path"], f"{name} declared chain input")
            info = os.fstat(operand["fd"])
            identity = (info.st_dev, info.st_ino)
            if info.st_uid != os.geteuid() or info.st_nlink != 1:
                raise OSError(
                    "declared chain input is not an owned single-link file")
            if identity in identities:
                raise OSError("declared chain input aliases another authority")
            identities.add(identity)
            private_operand = os.path.join(
                private_inputs, f"input-{declared['argv_index']}")
            used = _copy_chain_snapshot_file(
                operand, private_operand, private_input_remaining)
            private_input_remaining -= used
            launch_operand = bind(
                private_operand, f"{name} private declared chain input",
                aggregate=False, inherit=True)
            command[declared["argv_index"]] = (
                declared["prefix"]
                + _chain_descriptor_path(launch_operand["fd"]))

        yield {
            "command": command,
            "env": environment,
            "cwd": private_cwd,
            "pass_fds": tuple(child_descriptors),
            "records": records,
            "inputs": input_manifest,
        }
    finally:
        try:
            if temporary is not None:
                temporary.cleanup()
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)


def _chain_cmds():
    """Chain registry: SIA's own signed ledger always; known keeper chains
    auto-detected when present on this machine (each verified by ITS OWN
    verifier); user-defined chains from config `chains` entries of the
    form {name, ledger, verify: [argv...]}."""
    chains = {
        "sia": (os.path.join(SHARE, "ledger.tsv"),
                os.path.join(BIN, "sia-ledger"),
                [sys.executable, os.path.join(BIN, "sia-ledger"), "verify",
                 SHARE, "--quiet"]),
    }
    custos_dir = os.path.join(HOME, ".local/share/custos")
    sekhmet_bin = os.path.join(HOME, ".local/bin/sekhmet")
    known = {
        "custos": (custos_dir, os.path.join(custos_dir, "ledger.tsv"), ATTEST,
                   [ATTEST, "verify-custos",
                    os.path.join(custos_dir, "ledger.tsv"),
                    os.path.join(custos_dir, "pub.hex"), "--quiet"]),
        "sekhmet": (os.path.join(HOME, ".local/share/sekhmet"),
                    os.path.join(HOME, ".local/share/sekhmet/ledger.tsv"),
                    sekhmet_bin,
                    [sekhmet_bin, "ledger", "verify", "--quiet"]),
        "aegis": (os.path.join(HOME, ".local/share/aegis"),
                  os.path.join(HOME, ".local/share/aegis/ledger.tsv"),
                  AEGIS_LEDGER_TOOL,
                  [sys.executable, AEGIS_LEDGER_TOOL, "verify",
                   os.path.join(HOME, ".local/share/aegis"), "--quiet"]),
    }
    for name, (root, ledger, tool, cmd) in known.items():
        # Once any integration component exists it remains in scope. Missing
        # counterparts must surface as absent/refused, never make a damaged
        # installed chain disappear from verification and benchmarking.
        if any(os.path.lexists(path) for path in (root, ledger, tool)):
            if name == "custos":
                chains[name] = (
                    ledger, tool, cmd,
                    ({"argv_index": 3,
                      "path": os.path.join(custos_dir, "pub.hex"),
                      "prefix": ""},))
            else:
                chains[name] = (ledger, tool, cmd)
    if not _active_config_load_valid():
        _invalid_chain_binding(
            chains, {"config": "active-load-invalid"},
            "active configuration provenance is invalid")
        return chains
    configured = CONFIG.get("chains", [])
    if not isinstance(configured, list):
        _invalid_chain_binding(
            chains, {"chains_type": type(configured).__name__},
            "chains must be a list")
        return chains
    if len(configured) > MAX_CONFIGURED_CHAINS:
        _invalid_chain_binding(
            chains, {"chains_count": len(configured)},
            "chains exceed their configured count bound")
        return chains
    for c in configured:
        if not isinstance(c, dict):
            _invalid_chain_binding(chains, c,
                                   "chain entry must be an object")
            continue
        allowed = {
            "_comment", "name", "ledger", "verifier", "verify", "inputs",
            "enabled"}
        unknown = sorted(set(c) - allowed)
        if unknown:
            _invalid_chain_binding(
                chains, c, "chain entry has unknown keys: "
                + ", ".join(str(key) for key in unknown))
            continue
        if c.get("enabled") is False:
            continue
        if "enabled" in c and not isinstance(c["enabled"], bool):
            _invalid_chain_binding(chains, c,
                                   "enabled must be true or false")
            continue
        try:
            raw_name = c["name"]
            if not isinstance(raw_name, str) or not raw_name.strip():
                raise ValueError("name must be a non-empty string")
            chain_name = sanitize_slugpart(raw_name)
            if chain_name.startswith("config-error-"):
                raise ValueError("name uses the reserved diagnostic prefix")
            raw_ledger = c["ledger"]
            if not _strict_config_string(
                    raw_ledger, nonempty=True,
                    limit=MAX_CONFIG_PATH_CHARS) or "\x00" in raw_ledger:
                raise ValueError("ledger must be a bounded path string")
            ledger = os.path.expanduser(raw_ledger)
            raw_cmd = c["verify"]
            if not isinstance(raw_cmd, list) or not raw_cmd \
                    or len(raw_cmd) > MAX_CONFIG_PATH_CHARS \
                    or any(not _strict_config_string(
                        a, nonempty=True, limit=MAX_CONFIG_PATH_CHARS)
                        or "\x00" in a for a in raw_cmd):
                raise ValueError("verify must be a non-empty string argv list")
            cmd = [os.path.expanduser(a) if a.startswith("~") else a
                   for a in raw_cmd]
            if not cmd:
                raise ValueError("verify argv is empty")
            supplied = c.get("verifier")
            if not _strict_config_string(
                    supplied, nonempty=True,
                    limit=MAX_CONFIG_PATH_CHARS) or "\x00" in supplied:
                # Custom command shapes are unbounded (`env`, shell wrappers,
                # alternate interpreters). Never guess which argv element is
                # the mutable verifier whose digest must be bound.
                raise ValueError("verifier must explicitly name executed code")
            tool = os.path.expanduser(supplied)
            if not os.path.isabs(ledger) or not os.path.isabs(tool):
                raise ValueError("ledger and verifier must be absolute paths")
            if not os.path.isfile(tool):
                raise ValueError("verifier is not a file")
            binding_error = _chain_verifier_binding_error(tool, cmd)
            if binding_error:
                raise ValueError(binding_error)
            if ledger not in cmd:
                raise ValueError("ledger is not an explicit path in verify argv")
            reserved, _state_directory = _chain_reserved_argv_indexes(
                ledger, tool, cmd)
            if "inputs" in c and not isinstance(c["inputs"], list):
                raise ValueError("inputs must be a list")
            inputs = _validated_chain_inputs(
                c.get("inputs", ()), raw_cmd, reserved)
            for declared in inputs:
                cmd[declared["argv_index"]] = (
                    declared["prefix"] + declared["path"])
            _command, inputs, _reserved, _state, _implicit = \
                _canonical_chain_launch_contract(
                    chain_name, ledger, tool, cmd, inputs)
            if not chain_name or chain_name in chains:
                # Built-ins are reserved and the first valid custom binding
                # owns its name; ambiguity must never shadow a keeper.
                raise ValueError("chain name is reserved or duplicated")
            chains[chain_name] = (ledger, tool, cmd, inputs)
        except Exception as exc:
            _invalid_chain_binding(chains, c, str(exc)[:160])
    return chains


def verify_chains():
    """Returns {name: 'pass'|'fail'|'absent'}."""
    out = {}
    passed_generations = {}
    for name, binding in _chain_cmds().items():
        try:
            ledger, tool, cmd, inputs = _normalize_chain_binding(binding)
        except ValueError:
            out[name] = "fail"
            continue
        if cmd and cmd[0] == INVALID_CHAIN_SENTINEL:
            out[name] = "fail"
            continue
        if _chain_verifier_binding_error(tool, cmd):
            out[name] = "fail"
            continue
        if not os.path.exists(ledger) or not os.path.exists(tool):
            out[name] = "absent"
            continue
        try:
            with _bound_chain_verification(
                    name, ledger, tool, cmd, inputs) as launch:
                # Verifier prose is not an evidence product here; only its
                # exit status is. The private PID namespace gives an
                # operator-supplied verifier a bounded descendant lifetime.
                r = _run_bounded_text_process(
                    launch["command"], env=launch["env"], timeout=60,
                    cwd=launch["cwd"], pass_fds=launch["pass_fds"],
                    label=f"{name} chain verifier",
                    output_limit=MAX_CONFIG_BYTES,
                    isolate_process_tree=True, retain_output=False)
                stable = all(_chain_generation_matches(record)
                             for record in launch["records"])
                out[name] = (
                    "pass" if r.returncode == 0 and stable else "fail")
                if out[name] == "pass":
                    passed_generations[name] = [
                        {key: record[key] for key in (
                            "path", "label", "directory", "generation")}
                        for record in launch["records"]
                        if record["aggregate"]]
        except Exception:
            out[name] = "fail"
    # A later keeper may run long enough for an earlier chain to advance.
    # Rebind every successful executable, input, state root, and sidecar once
    # more before returning the aggregate; otherwise an all-pass result need
    # never have described one completed verification batch.
    for name, records in passed_generations.items():
        if not all(_chain_generation_still_named(record)
                   for record in records):
            out[name] = "fail"
    return out


def chain_verdict(chains):
    """Aggregate without laundering a retained absent chain into PASS."""
    if not chains:
        return "unknown"
    if any(status == "fail" for status in chains.values()):
        return "fail"
    if any(status != "pass" for status in chains.values()):
        return "degraded"
    return "pass"


def _ledger_bound_content(content, occurrence_id=None):
    content = str(content)
    if occurrence_id is None:
        return content
    if not isinstance(occurrence_id, str) \
            or re.fullmatch(r"[0-9a-f]{64}", occurrence_id) is None:
        raise ValueError("ledger occurrence identity is invalid")
    return json.dumps({
        "schema": "sia-ledger-occurrence-v1",
        "record_id": occurrence_id,
        "content": content,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _durable_status_log_message(value, limit=400):
    """Redact one daemon-visible diagnostic and checkpoint its omissions."""
    detail = clip(redact(value, "status-error"), limit)
    if not REDACTIONS:
        return detail
    try:
        if _CORPUS_OWNER_DEPTH.get() > 0:
            _checkpoint_status_error_redactions(load_memo())
        else:
            with corpus_owner():
                _checkpoint_status_error_redactions(load_memo())
    except Exception:
        # Never route the original secret-bearing exception around a failed
        # accounting write. A later safe pulse may still checkpoint the
        # retained in-process counter.
        return "diagnostic detail suppressed; redaction accounting refused"
    return detail


def ledger_append(action, arg1, arg2, content="", required=False,
                  occurrence_id=None):
    """Append one signed transition; optionally fail the parent operation."""
    try:
        bound_content = _ledger_bound_content(content, occurrence_id)
        sha = hashlib.sha256(bound_content.encode()).hexdigest()
        result = _run_bounded_text_process(
            [sys.executable, os.path.join(BIN, "sia-ledger"),
             "append", SHARE, action, str(arg1)[:120],
             str(arg2)[:120], sha, str(len(bound_content.encode()))],
            env=None, timeout=30, cwd=None, label="signed ledger append")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "keeper refused")[-240:]
            raise RuntimeError(detail)
        return True
    except Exception as exc:
        log(_durable_status_log_message(
            f"ledger append failed for {action}: {exc}"))
        if required:
            raise RuntimeError(
                f"signed ledger refused {action}; transition not published") \
                from exc
        return False


def ledger_contains(action, arg1, arg2, content, occurrence_id=None):
    """Ask the signed keeper whether an exact transition already exists."""
    encoded = _ledger_bound_content(content, occurrence_id).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    result = _run_bounded_text_process(
        [sys.executable, os.path.join(BIN, "sia-ledger"), "contains", SHARE,
         action, str(arg1)[:120], str(arg2)[:120], digest,
         str(len(encoded))],
        env=None, timeout=30, cwd=None, label="signed ledger presence")
    if result.returncode == 0:
        return True
    if result.returncode == 3:
        return False
    detail = (result.stderr or result.stdout or "keeper refused")[-240:]
    raise RuntimeError(f"signed ledger presence check refused: {detail}")


def ledger_settle(action, arg1, arg2, content, occurrence_id=None):
    """Atomically append an exact occurrence unless the keeper has it."""
    encoded = _ledger_bound_content(content, occurrence_id).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    result = _run_bounded_text_process(
        [sys.executable, os.path.join(BIN, "sia-ledger"), "settle", SHARE,
         action, str(arg1)[:120], str(arg2)[:120], digest,
         str(len(encoded))],
        env=None, timeout=30, cwd=None, label="signed ledger settlement")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "keeper refused")[-240:]
        raise RuntimeError(f"signed ledger settlement refused: {detail}")
    return True


LEDGER_PENDING_SCHEMA_V1 = "sia-ledger-pending-v1"
LEDGER_PENDING_SCHEMA = "sia-ledger-pending-v2"
# parsed=1024*65536, exact=67108864; parsed=1024*2, exact=2048;
MAX_LEDGER_PENDING_RECORD_BYTES = 65_536
MAX_LEDGER_PENDING_BYTES = 67_108_864
MAX_LEDGER_PENDING_SCAN_ENTRIES = 2_049


def _ledger_pending_dir():
    return os.path.join(STATE, "ledger-pending")


def _ensure_ledger_pending_dir():
    path = _ledger_pending_dir()
    ensure_durable_directory(path, mode=0o700)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError(
                "ledger recovery queue is not an owned real directory")
        os.fchmod(descriptor, 0o700)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def _scan_ledger_pending_names(directory):
    """Bound queue discovery before names or byte totals can accumulate."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    names = []
    total = 0
    inspected = 0
    cleaned = False
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError(
                "ledger recovery queue is not an owned real directory")
        with os.scandir(descriptor) as entries:
            for entry in entries:
                inspected += 1
                if inspected >= MAX_LEDGER_PENDING_SCAN_ENTRIES:
                    raise ValueError(
                        "ledger recovery directory exceeds scan limit")
                name = entry.name
                if _legacy_atomic_temp_name(name):
                    _remove_legacy_atomic_temp(
                        descriptor, entry, "ledger recovery directory")
                    cleaned = True
                    continue
                if not name.endswith(".json") or name.startswith("."):
                    continue
                if len(names) >= MAX_LEDGER_PENDING_RECORDS:
                    raise ValueError(
                        "ledger recovery queue exceeds record limit")
                entry_info = entry.stat(follow_symlinks=False)
                if entry_info.st_size > MAX_LEDGER_PENDING_BYTES - total:
                    raise ValueError(
                        "ledger recovery queue exceeds byte limit")
                total += entry_info.st_size
                names.append(name)
    finally:
        if cleaned:
            os.fsync(descriptor)
        os.close(descriptor)
    names.sort()
    return names, total


def _pending_basis(order, action, arg1, arg2, content):
    if isinstance(order, bool) or not isinstance(order, int) or order < 0:
        raise ValueError("ledger recovery order is invalid")
    basis = {"order": order, "action": str(action),
             "arg1": str(arg1), "arg2": str(arg2),
             "content": str(content)}
    if any("\t" in basis[key] or "\n" in basis[key]
           for key in ("action", "arg1", "arg2")):
        raise ValueError("ledger recovery fields contain control separators")
    if any(len(basis[key]) > 120 for key in ("action", "arg1", "arg2")):
        raise ValueError("ledger recovery field exceeds keeper bounds")
    return basis


def _pending_identity(basis):
    return hashlib.sha256(json.dumps(
        basis, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode()).hexdigest()


def _read_pending_record(path):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with siaqueue.regular_file_stream(fd, label="ledger recovery record") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_size > MAX_LEDGER_PENDING_RECORD_BYTES \
                or before.st_mode & 0o077:
            raise ValueError("ledger recovery record is not a bounded private file")
        raw = stream.read(MAX_LEDGER_PENDING_RECORD_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_LEDGER_PENDING_RECORD_BYTES:
        raise ValueError("ledger recovery record changed while read")
    try:
        record = _strict_json_loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("ledger recovery record is malformed") from exc
    if not isinstance(record, dict) or record.get("schema") not in {
            LEDGER_PENDING_SCHEMA_V1, LEDGER_PENDING_SCHEMA}:
        raise ValueError("ledger recovery record schema is invalid")
    queued_at = record.get("queued_at")
    try:
        if not isinstance(queued_at, str):
            raise ValueError
        datetime.datetime.strptime(queued_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("ledger recovery timestamp is invalid") from None
    basis = _pending_basis(record.get("order"), record.get("action"),
                           record.get("arg1"), record.get("arg2"),
                           record.get("content"))
    identity = _pending_identity(basis)
    if record.get("record_id") != identity \
            or os.path.basename(path) != identity + ".json":
        raise ValueError("ledger recovery record identity is invalid")
    return record, observed


def queue_ledger_transition(order, action, arg1, arg2, content):
    """Persist one exact signed transition before asking the keeper."""
    basis = _pending_basis(order, action, arg1, arg2, content)
    identity = _pending_identity(basis)
    record = {"schema": LEDGER_PENDING_SCHEMA, "record_id": identity,
              "queued_at": iso(), **basis}
    encoded = (json.dumps(record, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_LEDGER_PENDING_RECORD_BYTES:
        raise ValueError("ledger recovery record exceeds byte limit")
    directory = _ensure_ledger_pending_dir()
    path = os.path.join(directory, identity + ".json")
    if os.path.lexists(path):
        existing, _observed = _read_pending_record(path)
        # Schema and queued_at are intentionally not identity-bearing. This
        # also lets an exact pre-upgrade v1 request settle before any v2 retry.
        existing_basis = {key: existing.get(key) for key in
                          ("order", "action", "arg1", "arg2", "content")}
        if existing.get("record_id") != identity \
                or existing_basis != basis:
            raise ValueError("ledger recovery identity collision")
        return path
    names, total = _scan_ledger_pending_names(directory)
    if len(names) >= MAX_LEDGER_PENDING_RECORDS \
            or total + len(encoded) > MAX_LEDGER_PENDING_BYTES:
        raise ValueError("ledger recovery queue is at capacity")
    atomic_write(path, encoded.decode("utf-8"))
    return path


def _settle_ledger_transition(path):
    record, observed = _read_pending_record(path)
    action, arg1, arg2, content = (record[key] for key in
                                   ("action", "arg1", "arg2", "content"))
    occurrence_id = (record["record_id"]
                     if record["schema"] == LEDGER_PENDING_SCHEMA else None)
    ledger_settle(action, arg1, arg2, content, occurrence_id)
    current = os.lstat(path)
    identity = (current.st_dev, current.st_ino, current.st_size,
                current.st_mtime_ns, current.st_ctime_ns)
    if identity != observed:
        raise RuntimeError("ledger recovery record changed before acknowledgment")
    os.unlink(path)
    dfd = os.open(os.path.dirname(path),
                  os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    return record


def recover_ledger_transitions():
    """Settle queued transitions in their original pulse order."""
    directory = _ledger_pending_dir()
    try:
        info = os.lstat(directory)
    except FileNotFoundError:
        return [], []
    if not stat.S_ISDIR(info.st_mode):
        return [], [{"file": os.path.basename(directory),
                     "error": "ledger recovery queue is not a directory"}]
    pending, errors = [], []
    try:
        names, _total = _scan_ledger_pending_names(directory)
    except Exception as exc:
        return [], [{"file": os.path.basename(directory),
                     "error": str(exc)[:160]}]
    total = 0
    for name in names:
        path = os.path.join(directory, name)
        try:
            total += os.lstat(path).st_size
            if total > MAX_LEDGER_PENDING_BYTES:
                raise ValueError("ledger recovery queue exceeds byte limit")
            record, _observed = _read_pending_record(path)
            pending.append((record["order"], record["queued_at"], path))
        except Exception as exc:
            errors.append({"file": name, "error": str(exc)[:160]})
    if errors:
        return [], errors
    recovered = []
    for _order, _queued_at, path in sorted(pending):
        try:
            recovered.append(_settle_ledger_transition(path))
        except Exception as exc:
            errors.append({"file": os.path.basename(path),
                           "error": str(exc)[:160]})
            break
    return recovered, errors


class LedgerTransitionError(RuntimeError):
    """A named lifecycle transition could not reach the signed keeper."""


def durable_ledger_append(action, arg1, arg2, content="", order=None):
    """Journal, keeper-sign, and acknowledge one exact transition."""
    try:
        order = time.time_ns() if order is None else order
        path = queue_ledger_transition(order, action, arg1, arg2, content)
        _settle_ledger_transition(path)
    except Exception as exc:
        raise LedgerTransitionError(
            f"signed keeper refused {action}: {exc}") from exc
    return True


def ledger_head():
    try:
        r = _run_bounded_text_process(
            [sys.executable, os.path.join(BIN, "sia-ledger"), "head", SHARE],
            env=None, timeout=30, cwd=None, label="signed ledger head")
        if r.returncode != 0:
            raise RuntimeError("signed ledger keeper refused its head")
        n, h = r.stdout.split()
        if re.fullmatch(r"0|[1-9][0-9]*", n) is None \
                or re.fullmatch(r"[0-9a-f]{64}", h) is None:
            raise ValueError("signed ledger head is malformed")
        count = int(n)
        if count > MAX_JSON_SAFE_INTEGER:
            raise ValueError("signed ledger count exceeds its status bound")
        return count, h
    except Exception:
        return 0, ""


# ---------------------------------------------------------------- thoughts

THOUGHTS_PATH = os.path.join(STATE, "thoughts.json")


def _thought_store_slug_matches(record):
    """Whether a queue-owned projection binds its deterministic page name."""
    slug = record["slug"]
    queue_id = record.get("queue_id")
    if queue_id is not None:
        return slug == _queued_thought_slug(queue_id)
    # Baseline-recovered pre-metadata pages have canonical but historical
    # names. Their recovery record proves exact page bytes; only queued rows
    # have a name derived from an identity that can be checked here.
    return True


def _validated_thought_store_row(value):
    """Admit only one exact bounded current or known legacy projection."""
    if not isinstance(value, dict):
        raise ValueError("thought projection row is not an object")
    keys = set(value)
    if keys == {"kind", "text"}:
        kind = value.get("kind")
        text = value.get("text")
        if not _strict_config_string(
                kind, nonempty=True, limit=MAX_THOUGHT_INBOX_TEXT) \
                or sanitize_slugpart(kind) != kind \
                or not _strict_config_string(
                    text, nonempty=True, limit=MAX_THOUGHT_INBOX_TEXT) \
                or inert_summary(text) != text:
            raise ValueError("legacy thought projection row is invalid")
        result = dict(value)
        if kind in LEGACY_MODEL_THOUGHT_KINDS:
            result["origin"] = "model"
        return result

    required = {"ts", "kind", "text", "links", "urgent", "slug"}
    optional = {"origin", "queue_id"}
    if not required.issubset(keys) or keys - required - optional:
        raise ValueError("thought projection row has an unsupported shape")
    candidate = dict(value)
    candidate.setdefault("origin", "derived")
    canonical = _canonical_thought_page_record(candidate)
    expected = dict(canonical)
    if "origin" not in value:
        expected.pop("origin")
    if expected != value or not _strict_config_string(
            value["kind"], nonempty=True, limit=MAX_THOUGHT_INBOX_TEXT) \
            or not _strict_config_string(
                value["text"], nonempty=True,
                limit=MAX_THOUGHT_INBOX_TEXT) \
            or not _thought_store_slug_matches(canonical):
        raise ValueError("thought projection row is noncanonical")
    result = dict(value)
    if "origin" not in value and value["kind"] in LEGACY_MODEL_THOUGHT_KINDS:
        result["origin"] = "model"
    return result


def load_thoughts():
    store = read_state_json(
        THOUGHTS_PATH, {"v": 1, "thoughts": []}, "thought store")
    if not isinstance(store, dict) \
            or set(store) not in ({"v", "thoughts"},
                                  {"v", "thoughts", "thought_recovery"}) \
            or not _exact_int(store.get("v"), 1) \
            or not isinstance(store.get("thoughts"), list) \
            or len(store["thoughts"]) > MAX_THOUGHT_INBOX_ITEMS:
        raise RuntimeError("thought store schema is invalid")
    try:
        canonical = []
        slugs = set()
        queue_ids = set()
        for value in store["thoughts"]:
            item = _validated_thought_store_row(value)
            slug = item.get("slug")
            queue_id = item.get("queue_id")
            if slug is not None and slug in slugs \
                    or queue_id is not None and queue_id in queue_ids:
                raise ValueError("thought projection identity is duplicated")
            if slug is not None:
                slugs.add(slug)
            if queue_id is not None:
                queue_ids.add(queue_id)
            canonical.append(item)
        _validated_thought_recovery_receipt(store)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("thought store schema is invalid") from exc
    store["thoughts"] = canonical
    return store


def _thought_reinforcement_ts(thought):
    """Return the epoch projection of a canonical generated-entry clock."""
    canonical_ts = _canonical_utc_timestamp(thought["ts"])
    return datetime.datetime.strptime(
        canonical_ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc).timestamp()


def _thought_reinforcement_id(thought):
    """Bind queued rehearsal to the durable self-described page."""
    slug = _canonical_corpus_slug(thought["slug"])
    return "thought-page-" + hashlib.sha256(slug.encode("utf-8")).hexdigest()


def add_thought(store, kind, text, links=(), urgent=False, queue_id=None,
                thought_ts=None, origin="derived"):
    if not isinstance(kind, str) or sanitize_slugpart(kind) != kind:
        raise ValueError("thought kind is not canonical")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("thought text must be a non-empty string")
    if not isinstance(links, (list, tuple, set)):
        raise ValueError("thought links must be a sequence")
    timestamp = _canonical_utc_timestamp(thought_ts or iso())
    origin = _canonical_thought_origin(origin)
    text = inert_summary(text)
    links = sorted({_canonical_corpus_slug(link) for link in links}) \
        or ["sia/cortex"]
    candidate = {"ts": timestamp, "kind": kind, "text": text,
                 "links": links, "urgent": bool(urgent), "origin": origin}
    if queue_id is not None:
        candidate["queue_id"] = queue_id
        candidate = _canonical_thought_page_record(candidate)
    if queue_id is not None:
        for existing in store.get("thoughts", []):
            if existing.get("queue_id") == queue_id:
                # A prior attempt may have updated the state snapshot before
                # older code failed to publish its deterministic page. Repair
                # or verify the exact bound page before treating it as done.
                if existing.get("origin") not in THOUGHT_ORIGINS:
                    raise ValueError(
                        "queued thought state has no canonical origin")
                existing_record = _canonical_thought_page_record(existing)
                if _thought_queue_binding(existing_record) \
                        != _thought_queue_binding(candidate):
                    raise ValueError(
                        "queued thought identity conflicts with its state")
                durable_record = _persist_thought(existing_record)
                existing.clear()
                existing.update(durable_record)
                return existing
    t = _persist_thought(candidate)
    # Publish first, then mutate/truncate the in-memory projection. A failed
    # page write leaves the prior store byte-for-byte eligible for retry.
    store["thoughts"].append(t)
    store["thoughts"] = store["thoughts"][-MAX_THOUGHT_INBOX_ITEMS:]
    # The bounded intent journal, rather than a second best-effort queue,
    # projects this page into daemon-owned compatibility policy state at the transaction's
    # settlement boundary.
    log(f"thought[{kind}] {text}")
    return t


def thought_queue_identity(scope, kind, text, links=(), urgent=False,
                           day=None, extra=None):
    """Return a stable queue ID for a deterministic generated-entry projection."""
    canonical_links = sorted(
        {_canonical_corpus_slug(link) for link in links}) \
        or ["sia/cortex"]
    basis = {"scope": scope, "day": today() if day is None else day,
             "kind": kind, "text": inert_summary(text),
             "links": canonical_links, "urgent": bool(urgent),
             "origin": "derived", "extra": extra}
    return hashlib.sha256(json.dumps(
        basis, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()[:32]


def think(store, memo, events, chains, salience, anomalies, event_day=None):
    """Run deterministic entry generators; the API name is compatibility."""
    new = []
    day = today()
    event_day = day if event_day is None else event_day
    if not isinstance(event_day, str) \
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", event_day) is None:
        raise ValueError("thought event day is invalid")

    def generated(kind, text, links=(), urgent=False, identity_day=None,
                  identity_extra=None):
        canonical_links = sorted(
            {_canonical_corpus_slug(link) for link in links}) \
            or ["sia/cortex"]
        canonical_text = inert_summary(text)
        identity = thought_queue_identity(
            "think.generated", kind, canonical_text, canonical_links,
            urgent, day="" if identity_day is None else identity_day,
            extra=identity_extra)
        return add_thought(
            store, kind, canonical_text, canonical_links, urgent,
            queue_id=identity, origin="derived")

    # 1. chain integrity transitions.  Treat a formerly observed optional
    # chain that disappears from the registry as absent for this transition;
    # then let an intentionally deconfigured chain leave the active scope.
    prev = memo.get("chains", {})
    observed = dict(chains)
    for name in prev:
        observed.setdefault(name, "absent")
    if chains != prev:
        transition_identity = {
            "previous": prev, "observed": observed, "configured": chains}
        failing = sorted(name for name, status in observed.items()
                         if status == "fail" and prev.get(name) != "fail")
        gone = sorted(name for name, status in observed.items()
                      if status == "absent" and prev.get(name) != "absent")
        recovered = sorted(name for name, status in observed.items()
                           if status == "pass"
                           and prev.get(name) in {"fail", "absent"})
        discovered = sorted(name for name, status in observed.items()
                            if status == "pass" and name not in prev)
        if failing:
            new.append(generated("integrity",
                f"Evidence chain FAILED verification: {', '.join(failing)}. "
                f"The keeper's own verifier rejected the chain.",
                [f"organs/{f}" for f in failing if f in ORGANS], urgent=True,
                identity_extra=transition_identity))
        if gone:
            new.append(generated("integrity",
                f"Evidence chain no longer verifiable: {', '.join(gone)} "
                f"(ledger or verifier missing).", ["sia/cortex"], urgent=True,
                identity_extra=transition_identity))
        if recovered:
            passing = sorted(name for name, status in observed.items()
                             if status == "pass")
            if all(status == "pass" for status in observed.values()):
                text = ("All evidence chains verify again: "
                        f"{', '.join(passing)}.")
            else:
                text = f"Evidence chain verifies again: {', '.join(recovered)}."
            new.append(generated(
                "integrity", text, ["sia/cortex"],
                identity_extra=transition_identity))
        if discovered:
            if prev:
                new.append(generated("integrity",
                    f"Newly observed evidence chain verifies: "
                    f"{', '.join(discovered)}.", ["sia/cortex"],
                    identity_extra=transition_identity))
            else:
                new.append(generated("integrity",
                    f"First integrity sweep: {len(discovered)} signed chains "
                    f"verified with their registered verifiers "
                    f"({', '.join(discovered)}).", ["sia/cortex"],
                    identity_extra=transition_identity))
        memo["chains"] = dict(chains)

    # 2. per-source rules (deduplicate identical generated entries within a pulse)
    pulse_seen = set()
    def once(kind, text):
        if (kind, text) in pulse_seen:
            return False
        pulse_seen.add((kind, text))
        return True
    for ev in events:
        if "refusal" in ev.tags \
                and memo.get("last_refusal_day") != event_day:
            memo["last_refusal_day"] = event_day
            if ev.organ == "jackal":
                refusal_text = (
                    f"The unverified JACKAL recall ledger reports a refusal "
                    f"({ev.summary}); this observation was not front-door "
                    f"reverified as a mathematical artifact.")
                refusal_links = ["organs/jackal"]
            else:
                refusal_text = (
                    f"The {ev.organ} source refused an observation "
                    f"({ev.summary}).")
                refusal_links = sorted(ev.links) or [f"organs/{ev.organ}"]
            new.append(generated(
                "refusal", refusal_text, refusal_links,
                identity_day=event_day))
        if ev.organ == "sekhmet" and ev.kind == "outcome":
            t = f"SEKHMET reported a completed fabric heal: {ev.summary}."
            if once("healing", t):
                new.append(generated(
                    "healing", t, sorted(ev.links), identity_day=event_day))
        if "collapse" in ev.tags:
            t = f"WORLDLINE collapsed a reality: {ev.summary}."
            if once("collapse", t):
                new.append(generated("collapse", t,
                                       ["organs/worldline"],
                                       identity_day=event_day))
        if "coredump" in ev.tags:
            t = f"Something crashed: {ev.summary}."
            if once("crash", t):
                new.append(generated("crash", t, sorted(ev.links),
                                       urgent=True,
                                       identity_day=event_day))
    # 3. anomaly cohorts (statistical, from gbrain) — a zero baseline means
    # "no history yet", not "anomaly"; require a real baseline and cap per pulse
    seen = set(memo.get("anomaly_keys", []))
    emitted = 0
    for a in (anomalies or []):
        if float(a.get("baseline_mean") or 0) <= 0 or \
           float(a.get("baseline_stddev") or 0) <= 0 or emitted >= 3:
            continue
        key = f"{a.get('cohort_kind')}:{a.get('cohort_value')}:{day}"
        if key in seen:
            continue
        seen.add(key)
        emitted += 1
        new.append(generated("anomaly",
            f"Unusual activity in {a.get('cohort_kind')} "
            f"“{a.get('cohort_value')}”: {a.get('count')} pages touched vs "
            f"baseline μ={round(a.get('baseline_mean', 0), 1)} "
            f"σ={round(a.get('baseline_stddev', 0), 1)}.", ["sia/cortex"],
            identity_day=day))
    memo["anomaly_keys"] = sorted(seen)[-100:]

    # 4. retrieval-salience shift
    if salience:
        top = salience[0].get("slug", "")
        if top and top != memo.get("salience_top") and not top.startswith("thoughts/"):
            previous_top = memo.get("salience_top", "")
            memo["salience_top"] = top
            new.append(generated("attention",
                f"Retrieval salience shifted: the highest-ranked page is now "
                f"“{salience[0].get('title', top)}”.", [top],
                identity_day=day,
                identity_extra={"previous": previous_top, "observed": top}))

    return new


# ---------------------------------------------------------------- exports

STATUS_PATH = os.path.join(STATE, "status.json")
GRAPH_PATH = os.path.join(STATE, "graph.json")
GRAPH_PROJECTION_SCHEMA = "sia-graph-projection-v1"
LEGACY_GRAPH_README_FAILURE = (
    "graph_page_refused:README:corpus slug is not canonical")
MAX_GRAPH_NODES = 260
MAX_GRAPH_EDGES = MAX_EVENT_LOOKUP_PAGES
MAX_GRAPH_SCAN_ENTRIES = MAX_SOURCE_SCAN_ENTRIES
MAX_GRAPH_DIRECTORY_QUEUE = MAX_EVENT_LOOKUP_PAGES
# three path components, hence two directory levels below its root.
MAX_GRAPH_TREE_LEVELS = 2


class GraphProjectionPending(RuntimeError):
    """A bounded graph generation still has durable scan or refusal debt."""


_GAZETTEER_ENTITY_TYPES = frozenset(
    ("person", "company", "organization", "entity"))
_WIKILINK_RE = re.compile(r"\[\[([a-z0-9/._-]+)(?:\|[^\]]*)?\]\]")
_DOMAIN_CONTEXT_MAX_CHARS = 64_000
_DOMAIN_REGEX_MAX_CHARS = 512
_DOMAIN_REGEX_MAX_BOUND = 256
_DOMAIN_REGEX_MAX_OPTIONALS = 16
_DOMAIN_BOUNDED_DOT_RE = re.compile(r"\.\{([0-9]+),([0-9]+)\}")
MAX_SCHEMA_PACK_BYTES = 65_536
MAX_SCHEMA_PACK_LINES = 4_096
MAX_SCHEMA_PACK_LINE_BYTES = 4_096
MAX_DOMAIN_EDGE_RULES = 256
MAX_DOMAIN_ENTITY_TYPES = 256
_DOMAIN_THOUGHT_KINDS = frozenset(
    ("integrity", "healing", "crash", "refusal"))
_DOMAIN_NEUTRAL_PAGE_TYPES = frozenset(
    ("note", "synthesis", "take", "intent"))
_DOMAIN_EVIDENCE_PAGE_TYPES = frozenset(("event-day", "epoch"))



# The graph-projection, domain-edge, and export implementation lives in the
# bounded child module `siagraph` (see its docstring and docs/ARCHITECTURE.md);
# the core stays sole owner of the constants above, GraphProjectionPending,
# and the published files.  The same bind/invoke façade siasenses uses keeps
# one runtime state under dynamic test aliases and mirrors explicit test
# patches of these helpers into intra-module calls.
import siagraph as _siagraph


def _sialib_graph_delegate(name):
    """Return a façade that binds this sialib instance before every call."""
    target = _siagraph._ORIGINAL_CHILD_FUNCTIONS[name]

    @functools.wraps(target)
    def delegated(*args, **kwargs):
        return _siagraph.invoke(globals(), name, *args, **kwargs)

    delegated._sia_senses_delegate = True
    return delegated


_siagraph.bind(globals())
for _sialib_graph_name in _siagraph._EXPORTED_FUNCTIONS:
    globals()[_sialib_graph_name] = _sialib_graph_delegate(
        _sialib_graph_name)
del _sialib_graph_name


def _require_recoverable_graph_snapshot(value):
    """Admit graph bytes before ranking or measurement uses."""
    if _recoverable_graph_snapshot(value) is None:
        raise RuntimeError("resident graph snapshot is invalid")
    # A failed bounded scan is still a useful, explicitly partial display
    # artifact, but it is not authority for ranking or measurement.
    if value["snapshot"]["complete"] is not True:
        raise RuntimeError("resident graph snapshot is incomplete")
    return value


def _require_musing_graph_snapshot(value):
    """Require enough graph authority to make a negative direct-link claim."""
    value = _require_recoverable_graph_snapshot(value)
    if value["snapshot"]["omitted_edges"]:
        raise RuntimeError("resident graph omits edges needed for the seeded walk")
    return value


def export_status(st):
    snapshot = dict(st)
    snapshot["version"] = VERSION
    atomic_write(STATUS_PATH, json.dumps(snapshot, allow_nan=False))


def export_thoughts(store):
    atomic_write(THOUGHTS_PATH, json.dumps(store, allow_nan=False))


# ---------------------------------------------------------------- pulse

MEMO_PATH = os.path.join(STATE, "memo.json")
MAX_MEMO_BYTES = 16_777_216
MAX_SOURCE_REPLAY_EVENTS = 65_536
MAX_SOURCE_REPLAY_SOURCES = 2001
MAX_SOURCE_REPLAY_RECORD_BYTES = 4_194_304
# A legacy trend may contain more history than the current cockpit window,
# parsed=4*1024*1024, exact=4194304; parsed=16*256, exact=4096;
MAX_BENCH_TREND_BYTES = 4_194_304
MAX_BENCH_TREND_INPUT_LINES = 4_096
MAX_BENCH_TREND_LINE_BYTES = 65_536
MAX_BENCH_TREND_ROWS = 30
MAX_PULSE_HISTORY_ROWS = 120
MAX_STATUS_INTENTS = 5


def load_memo():
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        fd = os.open(MEMO_PATH, flags)
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise RuntimeError(f"brainstem memo cannot be opened safely: {exc}") \
            from exc
    with siaqueue.regular_file_stream(
            fd, label="brainstem memo", error_type=RuntimeError) as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_nlink != 1:
            raise RuntimeError(
                "brainstem memo is not an owned single-link regular file")
        if before.st_size > MAX_MEMO_BYTES:
            raise RuntimeError("brainstem memo is not a bounded regular file")
        raw = stream.read(MAX_MEMO_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = _file_generation(before)
    finished = _file_generation(after)
    if observed != finished or len(raw) > MAX_MEMO_BYTES:
        raise RuntimeError("brainstem memo changed while read")
    try:
        value = _strict_json_loads(raw)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise RuntimeError("brainstem memo is unreadable or malformed") \
            from exc
    if not isinstance(value, dict):
        raise RuntimeError("brainstem memo must be an object")
    try:
        target = os.lstat(MEMO_PATH)
    except OSError as exc:
        raise RuntimeError("brainstem memo changed while read") from exc
    current = _file_generation(target)
    if not stat.S_ISREG(after.st_mode) \
            or after.st_uid != os.geteuid() or after.st_nlink != 1 \
            or not stat.S_ISREG(target.st_mode) \
            or target.st_uid != os.geteuid() or target.st_nlink != 1 \
            or current != finished:
        raise RuntimeError("brainstem memo changed while read")
    return value


def _memo_text(value):
    encoded = json.dumps(value, allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_MEMO_BYTES:
        raise ValueError("brainstem memo exceeds its byte bound")
    return encoded


def _write_memo(value):
    encoded = _memo_text(value)
    atomic_write(MEMO_PATH, encoded)


def _ready_receipt(memo):
    receipt = memo.get("ready")
    if receipt is None:
        return None
    if not isinstance(receipt, dict) or set(receipt) != {
            "v", "completed_at", "kind", "identity"} \
            or not _exact_int(receipt.get("v"), 1) \
            or receipt.get("kind") not in {"pulse", "dream", "recovery"} \
            or not isinstance(receipt.get("identity"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", receipt["identity"]) is None \
            or not isinstance(receipt.get("completed_at"), str):
        raise RuntimeError("memory readiness receipt is invalid")
    try:
        if _canonical_utc_timestamp(receipt["completed_at"]) \
                != receipt["completed_at"]:
            raise ValueError
    except ValueError:
        raise RuntimeError("memory readiness receipt is invalid") from None
    return receipt


def _with_ready_receipt(value, kind, identity=None):
    if kind not in {"pulse", "dream", "recovery"}:
        raise ValueError("memory readiness receipt kind is invalid")
    identity = uuid.uuid4().hex if identity is None else identity
    if not isinstance(identity, str) \
            or re.fullmatch(r"[0-9a-f]{32}", identity) is None:
        raise ValueError("memory readiness receipt identity is invalid")
    updated = dict(value, ready={
        "v": 1, "completed_at": iso(), "kind": kind,
        "identity": identity})
    _ready_receipt(updated)
    return updated


def _discard_pending_cursor_renames(start=0):
    if isinstance(start, bool) or not isinstance(start, int) \
            or start < 0 or start > len(PENDING_CURSOR_RENAMES):
        raise ValueError("pending cursor cleanup boundary is invalid")
    for tmp, _real in PENDING_CURSOR_RENAMES[start:]:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    del PENDING_CURSOR_RENAMES[start:]


def _commit_sense_cursors(cursors):
    """Publish evidence offsets only after corresponding policy-state saves."""
    rename_errors = []
    for tmp, real in PENDING_CURSOR_RENAMES:
        try:
            info = os.lstat(tmp)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                raise RuntimeError("temporary cursor is not an owned file")
            try:
                target = os.lstat(real)
            except FileNotFoundError:
                target = None
            if target is not None and not stat.S_ISREG(target.st_mode):
                raise RuntimeError("cursor target is not a regular file")
            os.replace(tmp, real)
            dfd = os.open(os.path.dirname(real) or ".", os.O_RDONLY
                          | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except Exception as exc:
            rename_errors.append({
                "file": os.path.basename(real), "error": str(exc)[:160]})
            try:
                os.unlink(tmp)
            except OSError:
                pass
    PENDING_CURSOR_RENAMES.clear()
    save_error = None
    try:
        save_cursors(cursors)
    except Exception as exc:
        save_error = str(exc)[:160]
    return rename_errors, save_error


def memory_readiness():
    """Return whether corpus, PGLite, and graph provenance are reconciled."""
    def blocked(reason):
        # This reason is printed by ``sia ready`` and rendered verbatim by the
        # cockpit.  Treat it as the same persistence/display boundary as a
        # status error: controls and secret-shaped spans may not cross it, and
        # any omission must join the durable cumulative accounting first.
        return False, _durable_status_log_message(reason, 400)

    try:
        # The migrator holds this same lease from its first marker write
        # through PGLite/graph reconciliation.  Reading both the marker and
        # take store under one lease prevents a false-ready TOCTOU snapshot.
        with corpus_owner():
            memo = load_memo()
            cortex_ready, cortex_reason = _cortex_boundary_status()
            if not cortex_ready:
                return blocked(cortex_reason)
            if _pending_notify_baseline_attempt(memo) is not None:
                return False, "notification baseline recovery is pending"
            source_pending = _pending_source_replay_marker(memo)
            if source_pending is not None:
                try:
                    _authorize_pending_source_replay(
                        source_pending, load_cursors())
                except SourceReplayQuarantine as exc:
                    return blocked(exc)
            sync_needed = memo.get("sync_needed", False)
            if not isinstance(sync_needed, bool):
                return False, "brainstem sync marker is malformed"
            pulse_pending = _pending_pulse_marker(memo)
            if pulse_pending is not None:
                return False, "pulse publication recovery is pending"
            dream_pending = _pending_dream_marker(memo)
            if dream_pending is not None:
                return False, "dream publication recovery is pending"
            consolidation_pending = _pending_consolidation_marker(memo)
            if consolidation_pending is not None:
                return False, "corpus consolidation recovery is pending"
            consolidation_debt = _consolidation_scan_debt()
            if consolidation_debt:
                return blocked(consolidation_debt)
            if source_pending is not None:
                return False, "evidence source replay is pending"
            if _pending_pulse_status_effects(memo) is not None:
                return False, "pulse status-effects recovery is pending"
            thought_debt = _thought_recovery_debt()
            if thought_debt:
                return blocked(thought_debt)
            if sync_needed:
                return False, "a corpus publication is still pending"
            graph_debt = _graph_projection_debt()
            if graph_debt:
                return blocked(graph_debt)
            if _ready_receipt(memo) is None:
                return False, "no successful memory publication is recorded"
            mind_state = siamind.load_mind()
            if mind_state.get("event_applied") \
                    or mind_state.get("event_batch_applied") is not None:
                return False, "evidence cursor replay guard is pending"
            if _pending_dream_unit(mind_state) is not None:
                return False, "a scheduled-maintenance policy transition is pending recovery"
            if siatakes.natural_history_recovery_required():
                return False, "a take/intent projection transaction is pending recovery"
            if siatakes.grade_recovery_required():
                return False, "a signed grade transaction is pending recovery"
            if siatakes.take_migration_required():
                return False, "legacy model-grade provenance migration is pending"
            if siatakes.intent_history_required():
                return False, "legacy intent history projection is pending"
            try:
                _require_recoverable_graph_snapshot(
                    read_json(GRAPH_PATH, {}))
            except RuntimeError as exc:
                return blocked(exc)
    except Exception as exc:
        return blocked(f"memory readiness check refused: {exc}")
    return True, ""


def _read_existing_agent_note(slug):
    """Read one deterministic note page through a bounded stable handle."""
    slug = _canonical_corpus_slug(slug)
    path = corpus_path(slug)
    fd = _open_source_nofollow(path, os.O_RDONLY)
    with siaqueue.regular_file_stream(fd, label="agent note") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_size > MAX_THOUGHT_INBOX_BYTES:
            raise ValueError(
                "deterministic note page is not a bounded owner file")
        raw = stream.read(MAX_THOUGHT_INBOX_BYTES + 1)
        after = os.fstat(stream.fileno())
        try:
            target = _source_path_identity(path, os.O_RDONLY)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "deterministic note page changed while reading") from exc
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    current = (target.st_dev, target.st_ino, target.st_size,
               target.st_mtime_ns, target.st_ctime_ns)
    if observed != finished or finished != current \
            or len(raw) > MAX_THOUGHT_INBOX_BYTES:
        raise RuntimeError("deterministic note page changed while reading")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError("deterministic note page is not valid UTF-8") \
            from exc


def _account_agent_note_redactions(memo, requests, queue_errors):
    """Move queue-bound secret omissions into cumulative memo state once."""
    if memo is None:
        if any(request.get("redactions") for _path, request, _identity
               in requests):
            raise RuntimeError(
                "agent-note redaction accounting needs the durable memo")
        return
    receipts = _agent_note_redaction_receipts(
        memo.get("agent_note_redaction_receipts"))
    active = {request["request_id"] for _path, request, _identity in requests}
    changed = False
    if not queue_errors:
        retained = {request_id: count for request_id, count in receipts.items()
                    if request_id in active}
        if retained != receipts:
            receipts = retained
            changed = True
    totals = _canonical_pulse_redactions(memo.get("redactions", {}))
    for _path, request, _identity in requests:
        bound = request.get("redactions")
        count = bound.get("agent-note") if isinstance(bound, dict) else None
        request_id = request["request_id"]
        payload = request.get("payload", {})
        if count is not None and any(
                _redaction_projection(payload.get(field, ""))[1]
                for field in ("author", "text")):
            raise RuntimeError(
                "counted agent-note request still contains secret material")
        if count is None:
            if request_id in receipts:
                raise RuntimeError(
                    "agent-note redaction receipt conflicts with its request")
            continue
        if request_id in receipts:
            if receipts[request_id] != count:
                raise RuntimeError(
                    "agent-note redaction receipt conflicts with its request")
            continue
        current = totals.get("agent-note", 0)
        if current > MAX_JSON_SAFE_INTEGER - count:
            raise RuntimeError("pulse publication redactions are invalid")
        totals["agent-note"] = current + count
        receipts[request_id] = count
        changed = True
    if not changed:
        return
    updated = dict(memo, redactions=totals)
    if receipts:
        updated["agent_note_redaction_receipts"] = receipts
    else:
        updated.pop("agent_note_redaction_receipts", None)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)


def materialize_agent_notes(store, memo=None):
    """Materialize valid agent-note requests without acknowledging them.

    The caller acknowledges returned paths only after corpus commit and gbrain
    sync succeed. Existing deterministic pages make retry idempotent if a
    daemon dies after writing but before acknowledgment.
    """
    requests, queue_errors = siaqueue.pending(STATE)
    _account_agent_note_redactions(memo, requests, queue_errors)
    processed, pages, thoughts, errors = [], [], [], list(queue_errors)
    for path, request, identity in requests:
        try:
            payload = request["payload"]
            author = clip(redact(payload["author"], "agent-note"), 40)
            body = redact(payload["text"], "agent-note").strip()[:2000]
            if not body:
                raise ValueError("note is empty after redaction")
            # Notes are intentionally model-origin prose. Keep their body
            # visually readable while making Markdown/wiki-link syntax inert,
            # so a resident agent cannot mint graph edges or page structure.
            inert_body = html.escape(body, quote=False) \
                .replace("[", "&#91;").replace("]", "&#93;")
            queued = datetime.datetime.strptime(
                request["queued_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=datetime.timezone.utc)
            slug = (f"notes/{queued.strftime('%Y-%m-%d-%H%M%S')}-"
                    f"{sanitize_slugpart(author)}-{request['request_id']}")
            request_digest = identity.get("sha256", "")
            if not re.fullmatch(r"[0-9a-f]{64}", request_digest):
                raise ValueError("agent request has no observed content digest")
            frontmatter_lines = [
                "type: note", fm_title(clip(body, 70)),
                f"tags: [note, agent, {sanitize_slugpart(author)}]",
                f"date: {queued.strftime('%Y-%m-%d')}",
                "origin: model",
                f"request_id: {request['request_id']}",
                f"request_sha256: {request_digest}",
            ]
            page_body = (
                f"# note · from {author} · "
                f"{queued.strftime('%Y-%m-%d %H:%MZ')}\n\n"
                f"**Agent-authored memory — model-origin, not evidence. "
                f"A message from one session to the next.**\n\n"
                f"<pre class=\"sia-agent-note\">{inert_body}</pre>\n\n"
                f"[[organs/agents]] [[sia/cortex]]\n")
            expected_page = ("---\n" + "\n".join(frontmatter_lines)
                             + "\n---\n" + page_body)
            if page_exists(slug):
                existing = _read_existing_agent_note(slug)
                legacy_lines = [line for line in frontmatter_lines
                                if line != "origin: model"]
                legacy_page = ("---\n" + "\n".join(legacy_lines)
                               + "\n---\n" + page_body)
                if existing == legacy_page:
                    _before_corpus_mutation()
                    atomic_write(corpus_path(slug), expected_page)
                elif existing != expected_page:
                    raise ValueError(
                        "deterministic note page differs from exact request")
            else:
                ensure_durable_directory(
                    os.path.dirname(corpus_path(slug)))
                _before_corpus_mutation()
                atomic_write(corpus_path(slug), expected_page)
            already_materialized = any(
                item.get("queue_id") == request["request_id"]
                for item in store.get("thoughts", []))
            thought = add_thought(
                store, "note",
                f"{author} left a note for future sessions: "
                f"{clip(body, 100)} (⟦{slug}⟧)",
                [slug, "organs/agents"], queue_id=request["request_id"],
                thought_ts=request["queued_at"], origin="model")
            if not already_materialized:
                thoughts.append(thought)
            processed.append((path, identity))
            pages.append(slug)
        except Exception as exc:
            errors.append({"file": os.path.basename(path),
                           "error": str(exc)})
    return processed, pages, thoughts, errors


def acknowledge_agent_notes(paths, commit_status, synced, after_ack=None):
    """Acknowledge only requests whose corpus transaction reached gbrain.

    Return the successful count and per-request errors so a partial unlink
    failure remains visible and retryable rather than being reported as an
    all-or-nothing result.
    """
    if commit_status == "error" or not synced:
        return 0, []
    acknowledged, errors = 0, []
    for path, identity in paths:
        try:
            siaqueue.acknowledge(path, identity)
            if after_ack is not None:
                after_ack(identity)
            acknowledged += 1
        except Exception as exc:
            errors.append({"file": os.path.basename(path),
                           "error": str(exc)})
    return acknowledged, errors


def _forget_agent_note_redaction_receipt(memo, identity):
    """Retire an accounted request only after its durable queue unlink."""
    request_id = identity.get("request_id") \
        if isinstance(identity, dict) else None
    receipts = memo.get("agent_note_redaction_receipts") \
        if isinstance(memo, dict) else None
    if not isinstance(receipts, dict) or request_id not in receipts:
        return
    receipts.pop(request_id)
    if not receipts:
        memo.pop("agent_note_redaction_receipts", None)

def coincidence_findings(mind, findings, now=None):
    """Cross-source coincidence: two or more DISTINCT sources exceeding
    their bands in the same detection pass is itself an observation
    worth a generated notice. Deterministic and causal-free: the notice
    states the coincidence and the occurrence count, never a cause. Pair
    history accumulates in the ``coincide`` compatibility field — input a
    future (measured) hypothesis lane would build on."""
    spikes = {o: t for o, k, t in findings if k == "spike"}
    spiked = sorted(spikes)
    if len(spiked) < 2:
        return []
    now = now or time.time()
    co = mind.setdefault("coincide", {})

    def _counts(organ):
        # Preserve counts from current intake and historical spike receipts.
        m = re.search(r"(?:admitted|produced) (\d+) events.*previous max (\d+)",
                      spikes.get(organ, ""))
        return f" ({m.group(1)} vs max {m.group(2)})" if m else ""

    out = []
    for i in range(len(spiked)):
        for j in range(i + 1, len(spiked)):
            key = f"{spiked[i]}|{spiked[j]}"
            rec = co.setdefault(key, {"n": 0, "last": 0})
            rec["n"] += 1
            rec["last"] = now
            nth = {1: "first", 2: "2nd", 3: "3rd"}.get(
                rec["n"], f"{rec['n']}th")
            out.append((
                f"Coincidence: {spiked[i]}{_counts(spiked[i])} and "
                f"{spiked[j]}{_counts(spiked[j])} both went "
                f"out-of-band in the same detection pass — {nth} recorded occurrence "
                f"of this pair. This does not establish simultaneous "
                f"source activity. "
                f"Observed coincidence only; no cause is inferred.",
                [f"organs/{spiked[i]}", f"organs/{spiked[j]}"]))
    return out[:2]                      # cap per pulse; pairs still counted


def _event_transition_receipt(value, batch_identity):
    """Validate the bounded generated-entry projection bound to a policy batch."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
            "id", "novelty_thoughts", "findings", "coincidences"} \
            or value.get("id") != batch_identity:
        raise RuntimeError("event policy-transition receipt is invalid")
    collections_to_bound = (
        value.get("novelty_thoughts"), value.get("findings"),
        value.get("coincidences"))
    if any(not isinstance(items, list)
           or len(items) > MAX_SOURCE_REPLAY_EVENTS
           for items in collections_to_bound):
        raise RuntimeError("event policy-transition receipt is invalid")
    for item in value["novelty_thoughts"]:
        if not isinstance(item, list) or len(item) != 4 \
                or not all(isinstance(field, str)
                           for field in (item[0], item[1], item[3])) \
                or len(item[1]) > MAX_THOUGHT_INBOX_TEXT \
                or not isinstance(item[2], list) \
                or any(_canonical_corpus_slug(link) != link
                       for link in item[2]) \
                or re.fullmatch(r"[0-9a-f]{32}", item[3]) is None:
            raise RuntimeError("event policy-transition receipt is invalid")
    for item in value["findings"]:
        if not isinstance(item, list) or len(item) != 3 \
                or not all(isinstance(field, str) for field in item) \
                or any(len(field) > MAX_THOUGHT_INBOX_TEXT for field in item):
            raise RuntimeError("event policy-transition receipt is invalid")
    for item in value["coincidences"]:
        if not isinstance(item, list) or len(item) != 2 \
                or not isinstance(item[0], str) \
                or len(item[0]) > MAX_THOUGHT_INBOX_TEXT \
                or not isinstance(item[1], list) \
                or any(_canonical_corpus_slug(link) != link
                       for link in item[1]):
            raise RuntimeError("event policy-transition receipt is invalid")
    return value


def _event_cognitive_transition(
        mind, admitted_events, now_ts, day, source_batch_identity):
    """Apply one exact source batch to a private retrieval-policy candidate.

    The caller runs this before source staging and later persists this same
    admitted candidate. Corpus generated entries are returned as inert specifications;
    this function itself has no corpus or queue side effects.

    The function name is retained for compatibility; the behavior is the
    retrieval-policy update described above.
    """
    batch_already_applied = siamind.event_batch_was_applied(
        mind, source_batch_identity)
    pending_transition = _event_transition_receipt(
        mind.get("event_transition_pending"), source_batch_identity)
    if batch_already_applied and pending_transition is not None:
        return {
            "workspace": list(mind.get("workspace", [])),
            "memory_state": siamind.memory_summary_view(mind, now=now_ts),
            "novelty_thoughts": copy.deepcopy(
                pending_transition["novelty_thoughts"]),
            "findings": copy.deepcopy(pending_transition["findings"]),
            "coincidences": copy.deepcopy(
                pending_transition["coincidences"]),
            "already_applied": True,
        }
    if pending_transition is not None:
        raise RuntimeError(
            "event policy-transition receipt has no batch replay guard")
    ingest = []
    ingest_ids = {}
    for event, day_slug in admitted_events:
        event_id = event_memory_identity(event)
        if batch_already_applied \
                or siamind.event_was_applied(mind, day_slug, event_id):
            continue
        ingest.append(event)
        ingest_ids[id(event)] = (day_slug, event_id)
    batch_kinds = [event.kind for event in ingest]
    organ_counts, organ_arousal = {}, {}
    novelty_thoughts = []
    novelty_emitted = 0
    for event in ingest:
        day_slug, applied_id = ingest_ids[id(event)]
        organ_counts[event.organ] = organ_counts.get(event.organ, 0) + 1
        arousal = siamind.arousal_of(event.tags)
        organ_arousal[event.organ] = max(
            organ_arousal.get(event.organ, 0.0), arousal)
        siamind.bump_kind(mind, event.organ, event.kind, event.tags)
        score, reasons = siamind.novelty(
            mind, event.organ, event.kind, sorted(event.links), batch_kinds,
            event.ts.timestamp())
        safety = bool(event.tags & siamind.SAFETY_TAGS)
        siamind.touch(
            mind, day_slug, event.ts.timestamp(), src="organ",
            arousal=arousal, novelty_score=score, pin=safety)
        for link in event.links:
            siamind.touch(mind, link, event.ts.timestamp(), src="organ")
            siamind.hebb(
                mind, day_slug, link, ts=event.ts.timestamp(),
                arousal=arousal, novelty_score=score, pin=safety)
        if score >= 0.6 and novelty_emitted < 2:
            novelty_emitted += 1
            text = (
                f"Novel: {event.summary} — {'; '.join(reasons[:2])} "
                f"(novelty {score:.2f}).")
            links = sorted(event.links)
            novelty_thoughts.append((
                "novelty", text, links,
                thought_queue_identity(
                    "pulse.mind.novelty", "novelty", text, links,
                    day=day, extra=applied_id)))
    findings = ([] if batch_already_applied else
                siamind.surprisal_update(
                    mind, organ_counts, ts=now_ts))
    coincidences = coincidence_findings(mind, findings, now=now_ts)
    workspace = siamind.rebuild_workspace(
        mind, organ_arousal, now=now_ts)
    memory_state = siamind.memory_summary(mind, now=now_ts)
    if not batch_already_applied:
        siamind.mark_event_batch_applied(mind, source_batch_identity)
        receipt = {
            "id": source_batch_identity,
            "novelty_thoughts": [list(item) for item in novelty_thoughts],
            "findings": [list(item) for item in findings],
            "coincidences": [list(item) for item in coincidences],
        }
        mind["event_transition_pending"] = _event_transition_receipt(
            receipt, source_batch_identity)
    return {
        "workspace": workspace,
        "memory_state": memory_state,
        "novelty_thoughts": novelty_thoughts,
        "findings": findings,
        "coincidences": coincidences,
        "already_applied": batch_already_applied,
    }


def _select_cognitive_admissions(
        admitted_events, appended_event_ids, pending_replay_ids):
    """Select exact observations that may change retrieval-policy state.

    The function name is retained for compatibility; the behavior is only the
    exact admission selection described above.
    """
    selected = []
    seen = set()
    allowed = set(appended_event_ids) | set(pending_replay_ids)
    for event, day_slug in admitted_events:
        event_id = event_memory_identity(event)
        if event_id not in allowed or event_id in seen:
            continue
        seen.add(event_id)
        selected.append((event, day_slug))
    return selected


def _drain_recovery_unpins(mind, now_ts):
    """Persist and acknowledge the reducing queue independently of sources."""
    queue_path = siamind.recovery_unpin_queue_path()
    drained, claim, refused = siamind.drain_touch_queue(
        mind, now=now_ts, queue_path=queue_path, defer_ack=True,
        page_exists=page_exists,
        claim_field="recovery_unpin_claim_sha256",
        report_capacity=True)
    if claim:
        siamind.save_mind(mind)
        siamind.acknowledge_touch_queue(claim, queue_path=queue_path)
        siamind.clear_touch_queue_claim(
            mind, "recovery_unpin_claim_sha256")
        siamind.save_mind(mind)
    return drained, refused


def _drain_ordinary_touches(mind, now_ts):
    """Settle one touch/pin generation independently of source admission."""
    had_receipt = "touch_queue_claim_sha256" in mind
    drained, claim, refused = siamind.drain_touch_queue(
        mind, now=now_ts, defer_ack=True, page_exists=page_exists,
        report_capacity=True)
    if claim:
        # The first save is the exact replay receipt for the claimed bytes.
        # A crash before acknowledgement reopens the same generation as an
        # idempotent no-op; the second save removes only its replay metadata.
        siamind.save_mind(mind)
        siamind.acknowledge_touch_queue(claim)
        siamind.clear_touch_queue_claim(mind)
        siamind.save_mind(mind)
    elif had_receipt and "touch_queue_claim_sha256" not in mind:
        # Repair an interrupted receipt cleanup even when its claimed file was
        # already durably removed.
        siamind.save_mind(mind)
    return drained, refused


def _record_touch_queue_health(errors, touch_usage):
    """Expose bounded producer pressure and retained physical refusals."""
    if touch_usage.get("at_capacity"):
        errors["touch_queue"] = (
            "recall reinforcement queue reached its bounded capacity")
    if touch_usage.get("refusal_count"):
        last_refusal = touch_usage.get("last_refusal") or "unknown"
        errors["touch_queue_tail_refusal"] = (
            f"{touch_usage['refusal_count']} touch queue physical "
            f"record(s) refused; last={last_refusal}")


def _read_bench_trend_tail(path, *, max_bytes=None):
    """Read only complete recent trend rows from a stable owned handle.

    The pre-bounded writer could leave arbitrarily large derived display
    history.  Upgrade therefore reads a fixed tail, discards a possibly torn
    leading/trailing record, and retains at most the declared physical-line
    window.  Unsafe path identity still refuses; legacy content truncation is
    returned to the caller instead of blocking authoritative DREAM recovery.
    """
    if max_bytes is None:
        max_bytes = MAX_BENCH_TREND_BYTES
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) \
            or max_bytes <= 0 or max_bytes > MAX_BENCH_TREND_BYTES:
        raise ValueError("benchmark trend tail bound is invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with siaqueue.regular_file_stream(fd, label="benchmark trend") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_mode & 0o022:
            raise ValueError(
                "benchmark trend is not an owned regular file")
        read_size = min(before.st_size, max_bytes)
        start = before.st_size - read_size
        stream.seek(start)
        raw = stream.read(read_size)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    try:
        rebound = os.lstat(path)
        if not stat.S_ISREG(rebound.st_mode) \
                or rebound.st_uid != os.geteuid() \
                or rebound.st_mode & 0o022:
            raise ValueError("benchmark trend changed while read")
        current = (rebound.st_dev, rebound.st_ino, rebound.st_size,
                   rebound.st_mtime_ns, rebound.st_ctime_ns)
    except OSError as exc:
        raise ValueError("benchmark trend changed while read") from exc
    if len(raw) != read_size or observed != finished or current != observed:
        raise ValueError("benchmark trend changed while read")

    legacy_truncated = start > 0
    if start:
        newline = raw.find(b"\n")
        raw = b"" if newline < 0 else raw[newline + 1:]
    if raw and not raw.endswith(b"\n"):
        legacy_truncated = True
        newline = raw.rfind(b"\n")
        raw = b"" if newline < 0 else raw[:newline + 1]
    raw_lines = raw.rsplit(b"\n", MAX_BENCH_TREND_INPUT_LINES + 1)
    if raw_lines and raw_lines[-1] == b"":
        raw_lines.pop()
    if len(raw_lines) > MAX_BENCH_TREND_INPUT_LINES:
        legacy_truncated = True
        raw_lines = raw_lines[-MAX_BENCH_TREND_INPUT_LINES:]

    lines = []
    for raw_line in raw_lines:
        if len(raw_line) > MAX_BENCH_TREND_LINE_BYTES:
            legacy_truncated = True
            continue
        try:
            lines.append(raw_line.decode("utf-8", errors="strict"))
        except UnicodeError:
            legacy_truncated = True
    return tuple(lines), legacy_truncated


def _bench_trend_snapshot(path=None, include_metadata=False):
    """Project bounded, validated heuristic-trend rows for the cockpit.

    Older releases used ``hit5_blend`` for the same slug-family proxy. That
    spelling is accepted only as an input migration; the exported contract is
    the explicit ``slug_match_at_5`` field.
    """
    if not isinstance(include_metadata, bool):
        raise ValueError("benchmark trend metadata mode is invalid")
    path = path or os.path.join(STATE, "bench-trend.jsonl")
    rows = []
    try:
        lines, legacy_truncated = _read_bench_trend_tail(path)
    except FileNotFoundError:
        lines = ()
        legacy_truncated = False
    for line in lines:
        try:
            record = _strict_json_loads(line)
            date = record.get("date")
            metric = record.get("slug_match_at_5_blend")
            if metric is None:
                metric = record.get("hit5_blend")
            if (not _status_calendar_date(date)
                    or not isinstance(metric, (int, float))
                    or isinstance(metric, bool) or not 0 <= metric <= 1):
                legacy_truncated = True
                continue
            if record.get("legacy_history_truncated") is True:
                legacy_truncated = True
            rows.append({"date": date,
                         "slug_match_at_5": float(metric),
                         "kind": "heuristic-slug-retrieval-drift-tripwire"})
            del rows[:-MAX_BENCH_TREND_ROWS]
        except (AttributeError, TypeError, UnicodeError, ValueError,
                RecursionError):
            legacy_truncated = True
    if include_metadata:
        return rows, {"legacy_truncated": bool(legacy_truncated)}
    return rows


def pulse(seq, opts=None):
    """Run one whole pulse cycle under the corpus transaction lease."""
    with corpus_owner():
        return _pulse_transaction(seq, opts)


def _mark_sync_needed(memo):
    """Durably record that corpus bytes must be published before reads."""
    if memo.get("sync_needed") is not True:
        updated = dict(memo, sync_needed=True)
        _write_memo(updated)
        memo.clear()
        memo.update(updated)


def _mark_external_corpus_mutation(memo):
    """Fence a corpus writer that does not call ``write_page`` itself."""
    _mark_sync_needed(memo)
    _mark_graph_projection_dirty()


def _canonical_pulse_effects(day, events_pulse, organs):
    effects = {"day": day, "events_pulse": events_pulse,
               "organs": copy.deepcopy(organs)}
    max_organs = MAX_LEDGER_PENDING_RECORDS \
        + len(BASE_ORGANS) + len(OPTIONAL_ORGANS)
    if not _status_calendar_date(effects["day"]) \
            or isinstance(effects["events_pulse"], bool) \
            or not isinstance(effects["events_pulse"], int) \
            or not 0 <= effects["events_pulse"] <= MAX_JSON_SAFE_INTEGER \
            or not isinstance(effects["organs"], dict) \
            or len(effects["organs"]) > max_organs:
        raise RuntimeError("pulse publication effects are invalid")
    for organ, state in effects["organs"].items():
        if not _strict_config_string(
                organ, nonempty=True, limit=MAX_SOURCE_NAME_CHARS) \
                or sanitize_slugpart(organ) != organ \
                or not isinstance(state, dict) or set(state) != {
                    "today", "last_ts"} \
                or isinstance(state.get("today"), bool) \
                or not isinstance(state.get("today"), int) \
                or not 0 <= state["today"] <= MAX_JSON_SAFE_INTEGER \
                or not isinstance(state.get("last_ts"), str):
            raise RuntimeError("pulse publication effects are invalid")
        if state["last_ts"]:
            try:
                _canonical_utc_timestamp(state["last_ts"])
            except ValueError:
                raise RuntimeError(
                    "pulse publication effects are invalid") from None
    return effects


def _canonical_pulse_redactions(value):
    """Return bounded cumulative redaction totals or refuse the projection."""
    if not _status_redactions_shape(value):
        raise RuntimeError("pulse publication redactions are invalid")
    return copy.deepcopy(value)


def _agent_note_redaction_receipts(value):
    """Return the bounded exactly-once queue accounting roster."""
    if value is None:
        return {}
    if not isinstance(value, dict) \
            or len(value) > siaqueue.MAX_PENDING_REQUESTS \
            or any(not isinstance(request_id, str)
                   or re.fullmatch(r"[0-9a-f]{32}", request_id) is None
                   or isinstance(count, bool) or not isinstance(count, int)
                   or not 1 <= count <= siaqueue.MAX_REQUEST_BYTES
                   for request_id, count in value.items()):
        raise RuntimeError("agent-note redaction receipts are invalid")
    return copy.deepcopy(value)


def _projected_pulse_redactions(memo):
    """Bind process-local increments to their exact cumulative memo target."""
    projected = _canonical_pulse_redactions(memo.get("redactions", {}))
    additions = _canonical_pulse_redactions(REDACTIONS)
    for organ, count in additions.items():
        projected[organ] = projected.get(organ, 0) + count
        if projected[organ] > MAX_JSON_SAFE_INTEGER:
            raise RuntimeError("pulse publication redactions are invalid")
    return projected


def _pulse_redactions_at_least_memo(memo, value):
    """Validate a cumulative target that cannot retract durable totals."""
    current = _canonical_pulse_redactions(memo.get("redactions", {}))
    candidate = _canonical_pulse_redactions(value)
    if any(candidate.get(organ, -1) < count
           for organ, count in current.items()):
        raise RuntimeError("pulse publication redactions are invalid")
    return candidate


def _recoverable_pulse_redactions(memo, value):
    """Total redaction-target validator for retained status recovery."""
    try:
        return _pulse_redactions_at_least_memo(memo, value)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None


def _pending_pulse_marker(memo):
    """Validate and return a crash-recovery identity for pulse publication."""
    marker = memo.get("pulse_publication")
    if marker is None:
        return None
    memo_seq = memo.get("pulse_seq")
    required = {"v", "seq", "id", "started_at"}
    optional = {"ledger", "effects", "history", "redactions"}
    if not isinstance(marker, dict) or not required.issubset(marker) \
            or set(marker) - required - optional \
            or not _exact_int(marker.get("v"), 1) \
            or not isinstance(memo_seq, int) \
            or isinstance(memo_seq, bool) \
            or not 0 <= memo_seq <= MAX_JSON_SAFE_INTEGER \
            or not isinstance(marker.get("seq"), int) \
            or isinstance(marker.get("seq"), bool) \
            or not 0 <= marker["seq"] <= MAX_JSON_SAFE_INTEGER \
            or marker["seq"] > memo_seq \
            or not isinstance(marker.get("id"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", marker["id"]) is None \
            or not isinstance(marker.get("started_at"), str):
        raise RuntimeError("pulse publication recovery marker is invalid")
    try:
        if _canonical_utc_timestamp(marker["started_at"]) \
                != marker["started_at"]:
            raise ValueError
    except ValueError:
        raise RuntimeError(
            "pulse publication recovery marker is invalid") from None
    if memo.get("sync_needed") is not True:
        raise RuntimeError("pulse publication marker has no publication debt")
    if "ledger" in marker:
        ledger = marker["ledger"]
        if not isinstance(ledger, dict) or set(ledger) != {
                "order", "action", "arg1", "arg2", "content",
                "record_id"}:
            raise RuntimeError("pulse publication ledger binding is invalid")
        try:
            basis = _pending_basis(
                ledger["order"], ledger["action"], ledger["arg1"],
                ledger["arg2"], ledger["content"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "pulse publication ledger binding is invalid") from exc
        expected_ledger = {**basis, "record_id": _pending_identity(basis)}
        if ledger != expected_ledger \
                or basis["action"] != "PULSE:ingest" \
                or not basis["arg1"].startswith(
                    f"pulse={marker['seq']} "):
            raise RuntimeError("pulse publication ledger binding is invalid")
    if "effects" in marker:
        effects = marker["effects"]
        if not isinstance(effects, dict) or set(effects) != {
                "day", "events_pulse", "organs"}:
            raise RuntimeError("pulse publication effects are invalid")
        if _canonical_pulse_effects(
                effects["day"], effects["events_pulse"],
                effects["organs"]) != effects:
            raise RuntimeError("pulse publication effects are invalid")
    if "history" in marker:
        if not _status_history_shape([marker["history"]]) \
                or not _status_history_shape(memo.get("pulse_history")) \
                or not memo["pulse_history"] \
                or memo["pulse_history"][-1] != marker["history"] \
                or "effects" not in marker \
                or marker["history"][0] != marker["started_at"] \
                or marker["history"][1] \
                != marker["effects"]["events_pulse"]:
            raise RuntimeError("pulse publication history binding is invalid")
    if "redactions" in marker \
            and _recoverable_pulse_redactions(
                memo, marker["redactions"]) is None:
        raise RuntimeError(
            "pulse publication redactions binding is invalid")
    return marker


def _mark_pulse_publication(memo, seq, effects=None, redactions=None):
    """Persist one pulse transaction identity before its first corpus byte."""
    if effects is not None:
        if not isinstance(effects, dict) or set(effects) != {
                "day", "events_pulse", "organs"}:
            raise RuntimeError("pulse publication effects are invalid")
        effects = _canonical_pulse_effects(
            effects["day"], effects["events_pulse"], effects["organs"])
    if redactions is not None:
        redactions = _pulse_redactions_at_least_memo(memo, redactions)
    marker = _pending_pulse_marker(memo)
    if marker is not None:
        if marker["seq"] != seq:
            raise RuntimeError("pulse publication sequence conflicts")
        if effects is not None and marker.get("effects") != effects:
            raise RuntimeError("pulse publication effects conflict")
        if redactions is not None and marker.get("redactions") != redactions:
            rebound = dict(marker, redactions=redactions)
            updated = dict(memo, pulse_publication=rebound)
            _write_memo(updated)
            memo.clear()
            memo.update(updated)
            return _pending_pulse_marker(memo)
        return marker
    if not isinstance(seq, int) or isinstance(seq, bool) \
            or not 0 <= seq <= MAX_JSON_SAFE_INTEGER:
        raise RuntimeError("pulse sequence is invalid")
    marker = {"v": 1, "seq": seq, "id": uuid.uuid4().hex,
              "started_at": iso()}
    if effects is not None:
        marker["effects"] = effects
    if redactions is not None:
        marker["redactions"] = redactions
    updated = dict(memo, pulse_publication=marker, sync_needed=True)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return marker


def _bind_pending_pulse_effects(memo, day, events_pulse, organs):
    marker = _pending_pulse_marker(memo)
    if marker is None:
        raise RuntimeError("pulse publication has no recovery identity")
    effects = _canonical_pulse_effects(day, events_pulse, organs)
    if marker.get("effects") is not None:
        if marker["effects"] != effects:
            raise RuntimeError("pulse publication effects conflict")
        return effects
    rebound = dict(marker, effects=effects)
    updated = dict(memo, pulse_publication=rebound)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    _pending_pulse_marker(memo)
    return effects


def _pending_pulse_status_effects(memo):
    """Validate durable counter state awaiting a full status publication."""
    marker = memo.get("pulse_status_effects_pending")
    if marker is None:
        return None
    if not isinstance(marker, dict) or set(marker) != {
            "v", "publication_id", "effects", "history"} \
            or not _exact_int(marker.get("v"), 1) \
            or not isinstance(marker.get("publication_id"), str) \
            or re.fullmatch(
                r"[0-9a-f]{32}", marker["publication_id"]) is None \
            or not _status_history_shape([marker.get("history")]) \
            or not _status_history_shape(memo.get("pulse_history")) \
            or not memo["pulse_history"] \
            or memo["pulse_history"][-1] != marker["history"]:
        raise RuntimeError("pulse status-effects handoff is invalid")
    effects = marker.get("effects")
    if not isinstance(effects, dict) or set(effects) != {
            "day", "events_pulse", "organs"}:
        raise RuntimeError("pulse status-effects handoff is invalid")
    try:
        if _canonical_pulse_effects(
                effects["day"], effects["events_pulse"],
                effects["organs"]) != effects \
                or marker["history"][1] != effects["events_pulse"]:
            raise ValueError
    except (TypeError, ValueError):
        raise RuntimeError("pulse status-effects handoff is invalid") \
            from None
    return marker


def _expected_pulse_publication_history(memo, marker, events_pulse):
    """Return the one history sequence a named publication can produce."""
    history = copy.deepcopy(memo.get("pulse_history", []))
    if not _status_history_shape(history):
        raise RuntimeError("pulse publication history is invalid")
    if marker.get("history") is None:
        history.append([marker["started_at"], events_pulse])
        history = history[-MAX_PULSE_HISTORY_ROWS:]
    return history


def _canonical_source_cognitive_ids(value):
    """Validate the compatibility-key IDs selected for policy updates."""
    if not isinstance(value, list) \
            or len(value) > MAX_SOURCE_REPLAY_EVENTS \
            or any(not isinstance(event_id, str)
                   or re.fullmatch(r"[0-9a-f]{64}", event_id) is None
                   for event_id in value) \
            or len(value) != len(set(value)):
        raise ValueError("source policy admission is invalid")
    return sorted(value)


def _pending_source_replay_marker(memo):
    """Validate exact evidence debt that must settle before consolidation."""
    marker = memo.get("source_replay_pending")
    if marker is None:
        return None
    if not isinstance(marker, dict) or set(marker) != {
            "v", "id", "started_at", "started_seq", "sources", "events",
            "effects", "cognitive_ids"} \
            or not _exact_int(marker.get("v"), 1) \
            or not isinstance(marker.get("id"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", marker["id"]) is None \
            or isinstance(marker.get("started_seq"), bool) \
            or not isinstance(marker.get("started_seq"), int) \
            or not 0 <= marker["started_seq"] <= MAX_JSON_SAFE_INTEGER \
            or not isinstance(marker.get("started_at"), str) \
            or not isinstance(marker.get("sources"), list) \
            or len(marker["sources"]) > MAX_SOURCE_REPLAY_SOURCES \
            or len(marker["sources"]) != len(set(marker["sources"])) \
            or marker["sources"] != sorted(marker["sources"]) \
            or any(not isinstance(source, str)
                   or len(source) > MAX_SOURCE_NAME_CHARS
                   or re.fullmatch(
                       r"sense_[a-z0-9_]+(?::[a-z0-9._-]+)?", source) is None
                   for source in marker["sources"]) \
            or not isinstance(marker.get("events"), list) \
            or not marker["events"] \
            or len(marker["events"]) > MAX_SOURCE_REPLAY_EVENTS \
            or not isinstance(marker.get("cognitive_ids"), list):
        raise RuntimeError("source replay marker is invalid")
    effects = marker.get("effects")
    if not isinstance(effects, dict) or set(effects) != {
            "day", "events_pulse", "organs"}:
        raise RuntimeError("source replay marker is invalid")
    try:
        if _canonical_utc_timestamp(marker["started_at"]) \
                != marker["started_at"]:
            raise ValueError
        if _canonical_pulse_effects(
                effects["day"], effects["events_pulse"],
                effects["organs"]) != effects:
            raise ValueError
        if _canonical_source_cognitive_ids(marker["cognitive_ids"]) \
                != marker["cognitive_ids"]:
            raise ValueError
    except ValueError:
        raise RuntimeError("source replay marker is invalid") from None
    seen = {}
    try:
        for record in marker["events"]:
            event = _event_from_replay_record(record)
            event_id = event_memory_identity(event)
            if event_id in seen:
                raise ValueError("event replay identity is duplicated")
            seen[event_id] = event_semantic_identity(event)
        if not set(marker["cognitive_ids"]).issubset(seen):
            raise ValueError("policy admission is not a source event")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("source replay marker is invalid") from exc
    return marker


class SourceReplayQuarantine(RuntimeError):
    """A durable source batch whose historical authority is unknowable."""


NOTIFY_BASELINE_ATTEMPT_KEY = "notify_baseline_attempt"


def _pending_notify_baseline_attempt(memo):
    """Validate the write-ahead fence for a first notification baseline."""
    marker = memo.get(NOTIFY_BASELINE_ATTEMPT_KEY)
    if marker is None:
        return None
    if not isinstance(marker, dict) or set(marker) != {
            "v", "id", "started_at"} \
            or not _exact_int(marker.get("v"), 1) \
            or not isinstance(marker.get("id"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", marker["id"]) is None \
            or not isinstance(marker.get("started_at"), str):
        raise RuntimeError(
            "notification baseline recovery marker is invalid")
    try:
        if _canonical_utc_timestamp(marker["started_at"]) \
                != marker["started_at"]:
            raise ValueError
    except ValueError:
        raise RuntimeError(
            "notification baseline recovery marker is invalid") from None
    return marker


def _mark_notify_baseline_attempt(memo):
    marker = _pending_notify_baseline_attempt(memo)
    if marker is not None:
        return marker
    marker = {"v": 1, "id": uuid.uuid4().hex, "started_at": iso()}
    updated = dict(memo, **{NOTIFY_BASELINE_ATTEMPT_KEY: marker})
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return marker


def _clear_notify_baseline_attempt(memo):
    if _pending_notify_baseline_attempt(memo) is None:
        return False
    updated = dict(memo)
    updated.pop(NOTIFY_BASELINE_ATTEMPT_KEY, None)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return True


def _recover_notify_baseline_attempt(memo, cursors):
    """Recover a first scan that may have run before cursor publication."""
    if _pending_notify_baseline_attempt(memo) is None:
        return cursors
    try:
        recovered = _notify_recover_interrupted_baseline(cursors)
    except (TypeError, ValueError):
        raise SourceReplayQuarantine(
            "source replay quarantine: notification baseline recovery "
            "cursor is ambiguous") from None
    cursors.clear()
    cursors.update(recovered)
    return cursors


def _authorize_pending_source_replay(marker, cursors):
    """Refuse an old notification batch before any recovery can mutate it."""
    if marker is None:
        return None
    events = _source_replay_events(marker)
    notifications = [
        event for event in events
        if event.organ == "notify" and event.kind == "notification"
        and event.occurrence.startswith("notification:")]
    if any(not _source_entity_token_is_canonical(
            event.occurrence.removeprefix("notification:"), "notification")
            for event in notifications):
        raise SourceReplayQuarantine(
            "source replay quarantine: notification event identity is "
            "invalid")
    owns_notification_source = "sense_notify" in marker["sources"]
    if notifications and not owns_notification_source:
        raise SourceReplayQuarantine(
            "source replay quarantine: notification event has no "
            "notification-source ownership")
    if not owns_notification_source:
        return marker
    try:
        _notify_replay_authority(
            cursors, allow_opaque=not notifications)
    except (TypeError, ValueError):
        raise SourceReplayQuarantine(
            "source replay quarantine: notification cursor authority is "
            "ambiguous") from None
    return marker


def _source_replay_events(marker):
    return [_event_from_replay_record(record) for record in marker["events"]]


def _source_replay_clock(marker):
    """Return the immutable policy timestamp/day bound by a source batch."""
    if not isinstance(marker, dict) \
            or not isinstance(marker.get("started_at"), str):
        raise RuntimeError("source replay clock is invalid")
    stamp = _canonical_utc_timestamp(marker["started_at"])
    if stamp != marker["started_at"]:
        raise RuntimeError("source replay clock is invalid")
    value = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc)
    return value.timestamp(), value.strftime("%Y-%m-%d")


def _source_replay_marker_value(
        memo, seq, sources, events, effects, cognitive_ids=None):
    if not isinstance(seq, int) or isinstance(seq, bool) \
            or not 0 <= seq <= MAX_JSON_SAFE_INTEGER:
        raise ValueError("source replay sequence is invalid")
    sources = sorted(set(sources))
    events = list(events)
    effects = _canonical_pulse_effects(
        effects["day"], effects["events_pulse"], effects["organs"])
    if not sources and not events:
        return _pending_source_replay_marker(memo)
    if len(sources) > MAX_SOURCE_REPLAY_SOURCES \
            or any(not isinstance(source, str)
                   or len(source) > MAX_SOURCE_NAME_CHARS
                   or re.fullmatch(
                       r"sense_[a-z0-9_]+(?::[a-z0-9._-]+)?", source) is None
                   for source in sources):
        raise ValueError("source replay marker names an invalid sense")
    marker = _pending_source_replay_marker(memo)
    records = {} if marker is None else {
        record["event_id"]: record for record in marker["events"]}
    for event in events:
        record = _event_replay_record(event)
        prior = records.get(record["event_id"])
        if prior is not None:
            if prior["semantic_id"] != record["semantic_id"]:
                raise ValueError("source replay event identity conflicts")
            continue
        records[record["event_id"]] = record
    if not records or len(records) > MAX_SOURCE_REPLAY_EVENTS:
        raise ValueError("source replay event batch exceeds its bound")
    if cognitive_ids is None:
        cognitive_ids = (sorted(records) if marker is None
                         else marker["cognitive_ids"])
    else:
        cognitive_ids = _canonical_source_cognitive_ids(cognitive_ids)
    if not set(cognitive_ids).issubset(records):
        raise ValueError("source policy admission is invalid")
    if marker is None:
        marker = {"v": 1, "id": uuid.uuid4().hex, "started_at": iso(),
                  "started_seq": seq, "sources": sources,
                  "events": list(records.values()), "effects": effects,
                  "cognitive_ids": cognitive_ids}
    else:
        if marker["effects"] != effects:
            raise ValueError("source replay effects conflict")
        if marker["cognitive_ids"] != cognitive_ids:
            raise ValueError("source policy admission conflicts")
        combined_sources = sorted(set(marker["sources"]) | set(sources))
        if len(combined_sources) > MAX_SOURCE_REPLAY_SOURCES:
            raise ValueError("source replay source batch exceeds its bound")
        marker = dict(marker, sources=combined_sources,
                      events=list(records.values()))
    return marker


def _mark_source_replay_pending(
        memo, seq, sources, events, effects, cognitive_ids=None):
    marker = _source_replay_marker_value(
        memo, seq, sources, events, effects, cognitive_ids)
    if marker is None:
        return None
    updated = dict(memo, source_replay_pending=marker)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    _pending_source_replay_marker(memo)
    return marker


def _stage_pulse_source_publication(
        memo, seq, sources, events, day, events_pulse, organs,
        *, source_effects=None, prepared_source=None, cognitive_ids=None,
        dry_run=False):
    """Atomically bind event redo and its exact projected status effects."""
    effects = _canonical_pulse_effects(day, events_pulse, organs)
    redactions = _projected_pulse_redactions(memo)
    pulse = _pending_pulse_marker(memo)
    if pulse is None:
        pulse = {"v": 1, "seq": seq, "id": uuid.uuid4().hex,
                 "started_at": iso(), "effects": effects,
                 "redactions": redactions}
    elif pulse["seq"] != seq:
        raise RuntimeError("pulse publication sequence conflicts")
    elif pulse.get("effects") not in (None, effects):
        raise RuntimeError("pulse publication effects conflict")
    else:
        pulse = dict(pulse, effects=effects, redactions=redactions)
    source_memo = memo
    if prepared_source is not None:
        # Revalidate the exact in-memory admission identity through the same
        # marker parser, then make the canonical merger prove that it binds
        # precisely this event/effect batch.
        _pending_source_replay_marker(
            {"source_replay_pending": prepared_source})
        source_memo = dict(memo, source_replay_pending=prepared_source)
    source = _source_replay_marker_value(
        source_memo, seq, sources, events, source_effects or effects,
        cognitive_ids)
    if source is None:
        raise RuntimeError("event pulse has no source replay identity")
    if prepared_source is not None and source != prepared_source:
        raise RuntimeError("prepared source replay identity conflicts")
    updated = dict(
        memo, pulse_publication=pulse, source_replay_pending=source,
        sync_needed=True)
    _memo_text(updated)
    if dry_run:
        return pulse, source
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    _pending_pulse_marker(memo)
    _pending_source_replay_marker(memo)
    return pulse, source


def _preflight_source_admission_image(
        memo, seq, sources, events, day, organs):
    """Render the exact source/memo candidate without publishing bytes."""
    events = _dedupe_event_batch(events)
    if not events:
        return
    _preflight_event_lookup(events)
    by_day = {}
    for event in events:
        by_day.setdefault(
            (event.organ, event.ts.strftime("%Y-%m-%d")), []).append(event)
    planned_organs = copy.deepcopy(organs)
    admitted = []
    appended_ids = set()
    planned_paths = collections.defaultdict(set)
    for (organ, event_day), grouped in by_day.items():
        day_pages, appended, day_admitted = update_day_page(
            organ, event_day, grouped, dry_run=True)
        admitted.extend(day_admitted)
        appended_ids.update(event_memory_identity(event) for event in appended)
        planned_paths[organ].update(
            os.path.abspath(corpus_path(slug)) for slug in day_pages)
        projected = planned_organs.setdefault(
            organ, {"today": 0, "last_ts": ""})
        if event_day == day:
            projected["today"] += len(appended)
        if appended:
            projected["last_ts"] = max(
                projected["last_ts"],
                iso(max(event.ts for event in appended)))
    _preflight_event_path_plan(planned_paths)
    cognitive = _select_cognitive_admissions(
        admitted, appended_ids, set())
    cognitive_ids = [
        event_memory_identity(event) for event, _slug in cognitive]
    effects = _canonical_pulse_effects(
        day, len(events), planned_organs)
    prepared = _source_replay_marker_value(
        memo, seq, sources, events, effects, cognitive_ids)
    _stage_pulse_source_publication(
        memo, seq, sources, events, day, len(events), planned_organs,
        prepared_source=prepared, cognitive_ids=cognitive_ids,
        dry_run=True)


def _source_refusal_code(exc):
    message = str(exc)
    if message == "legacy event cannot be identity-upgraded automatically":
        return "legacy-event-identity"
    if "brainstem memo exceeds its byte bound" in message:
        return "memo-capacity"
    if any(fragment in message for fragment in (
            "event day exceeds its shard bound",
            "one event exceeds the event shard byte bound",
            "bounded occurrence index",
            "event organ would exceed its bounded occurrence index",
            "occurrence lookup exceeds")):
        return "event-capacity"
    return None


def _source_refusal_field(source):
    try:
        encoded = source.encode("utf-8")
    except UnicodeEncodeError:
        encoded = os.fsencode(source)
        return "source-" + hashlib.sha256(encoded).hexdigest()
    if len(source) <= 120:
        return source
    return "source-" + hashlib.sha256(encoded).hexdigest()


def _settle_source_refusals(source, events, reason):
    """Sign exact refusal identities before authorizing cursor progress."""
    source = str(source)
    for event in _dedupe_event_batch(events):
        event_id = event_memory_identity(event)
        content = json.dumps({
            "source": source,
            "reason": reason,
            "event_id": event_id,
            "semantic_id": event_semantic_identity(event),
            "organ": event.organ,
            "timestamp": iso(event.ts),
            "occurrence_sha256": hashlib.sha256(
                event.occurrence.encode("utf-8")).hexdigest(),
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        durable_ledger_append(
            "SOURCE:refuse", _source_refusal_field(source), reason,
            content, order=int(event_id, 16))


def _take_source_record_refusals(cursors):
    """Remove and validate exact physical-record refusals from a trial."""
    rows = cursors.pop(SOURCE_RECORD_REFUSALS_KEY, [])
    if not isinstance(rows, list) \
            or len(rows) > MAX_LEDGER_PENDING_RECORDS:
        raise ValueError("source record refusal state exceeds its bound")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("source record refusal state is invalid")
        if row.get("schema") == "sia-journal-record-refusal-v1":
            if set(row) != {
                    "schema", "key", "scope", "cursor", "cursor_sha256",
                    "ordinal", "observed_bytes", "record_sha256", "reason",
                    "complete"} \
                    or not isinstance(row.get("key"), str) \
                    or row.get("scope") not in {"sys", "user"} \
                    or row["key"] != "journal." + row["scope"] \
                    or not isinstance(row.get("cursor"), str) \
                    or not row["cursor"] \
                    or len(row["cursor"].encode("utf-8")) \
                    > MAX_JOURNAL_CURSOR_BYTES \
                    or hashlib.sha256(row["cursor"].encode("utf-8")
                                      ).hexdigest() \
                    != row.get("cursor_sha256") \
                    or any(isinstance(row.get(field), bool)
                           or not isinstance(row.get(field), int)
                           or row[field] < 0
                           for field in ("ordinal", "observed_bytes")) \
                    or not isinstance(row.get("record_sha256"), str) \
                    or re.fullmatch(
                        r"[0-9a-f]{64}", row["record_sha256"]) is None \
                    or row.get("reason") not in {
                        "journal-record-over-bound",
                        "journal-record-over-aggregate",
                        "journal-record-malformed",
                        "journal-record-non-object"} \
                    or not isinstance(row.get("complete"), bool):
                raise ValueError("journal record refusal state is invalid")
            continue
        if row.get("schema") != "sia-source-record-refusal-v1" \
                or set(row) != {
                    "schema", "key", "generation", "ordinal", "start",
                    "end", "bytes", "reason", "chunk_chain_sha256"} \
                or not isinstance(row.get("key"), str) \
                or len(row["key"]) > MAX_SOURCE_NAME_CHARS \
                or any(isinstance(row.get(field), bool)
                       or not isinstance(row.get(field), int)
                       or row[field] < 0
                       for field in (
                           "generation", "ordinal", "start", "end",
                           "bytes")) \
                or row["end"] - row["start"] != row["bytes"] \
                or row.get("reason") not in {
                    "over-bound-record", "invalid-utf8-record",
                    "malformed-json-record", "non-object-json-record",
                    "missing-json-field",
                    "non-text-json-field", "invalid-utf8-json-field",
                    "over-bound-json-field"} \
                or not isinstance(row.get("chunk_chain_sha256"), str) \
                or re.fullmatch(
                    r"[0-9a-f]{64}", row["chunk_chain_sha256"]) is None:
            raise ValueError("source record refusal state is invalid")
    return rows


def _settle_source_record_refusals(source, rows):
    """Sign exact refused records before their cursor may publish."""
    source = str(source)
    for row in rows:
        content = json.dumps({
            "source": source,
            **row,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        refusal_id = hashlib.sha256(content.encode("utf-8")).hexdigest()
        durable_ledger_append(
            "SOURCE:refuse", _source_refusal_field(source),
            row["reason"], content, order=int(refusal_id, 16))


def _take_source_entry_refusals(cursors, source):
    """Remove bounded native-entry refusals from an isolated cursor trial."""
    rows = cursors.pop(SOURCE_ENTRY_REFUSALS_KEY, [])
    if not isinstance(rows, list) or len(rows) > MAX_WORLDLINE_REFUSALS:
        raise ValueError("source entry refusal state exceeds its bound")
    required = {"schema", "source", "reason", "entry_sha256",
                "observation_sha256", "created_at"}
    for row in rows:
        if not isinstance(row, dict) or set(row) != required \
                or row.get("schema") != "sia-source-entry-refusal-v1" \
                or row.get("source") != source \
                or not isinstance(row.get("reason"), str) \
                or re.fullmatch(
                    r"worldline-[a-z0-9_-]+", row["reason"]) is None \
                or len(row["reason"]) > MAX_SOURCE_NAME_CHARS \
                or any(not isinstance(row.get(field), str)
                       or re.fullmatch(r"[0-9a-f]{64}", row[field]) is None
                       for field in ("entry_sha256", "observation_sha256")):
            raise ValueError("source entry refusal state is invalid")
        _worldline_time(row["created_at"])
    return rows


def _settle_source_entry_refusals(source, rows):
    """Sign native-entry refusals before their trial cursor may publish."""
    source = str(source)
    for row in rows:
        if row.get("source") != source:
            raise ValueError("source entry refusal source is invalid")
        content = json.dumps(
            row, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False)
        refusal_id = hashlib.sha256(content.encode("utf-8")).hexdigest()
        durable_ledger_append(
            "SOURCE:refuse", _source_refusal_field(source), row["reason"],
            content, order=int(refusal_id, 16))


def _take_owned_source_entry_refusals(
        sense, trial, prior_present, prior_value):
    """Let only WORLDLINE consume its cursor-resident refusal queue."""
    if sense is sense_worldline:
        return _take_source_entry_refusals(trial, "sense_worldline")
    unchanged = ((SOURCE_ENTRY_REFUSALS_KEY in trial) == prior_present
                 and (not prior_present
                      or trial[SOURCE_ENTRY_REFUSALS_KEY] == prior_value))
    if not unchanged:
        raise ValueError(
            "source-entry refusal namespace is reserved for sense_worldline")
    return []


def _clear_source_replay_pending(memo):
    if _pending_source_replay_marker(memo) is None:
        return False
    updated = dict(memo)
    updated.pop("source_replay_pending", None)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return True


def _bind_pending_pulse_ledger(memo, arg1, arg2, content, *, replace=False):
    """Durably bind recovery to one exact idempotent keeper occurrence."""
    marker = _pending_pulse_marker(memo)
    if marker is None:
        raise RuntimeError("pulse publication has no recovery identity")
    if "ledger" in marker and not replace:
        return marker["ledger"]
    basis = _pending_basis(
        time.time_ns(), "PULSE:ingest", arg1, arg2, content)
    ledger = {**basis, "record_id": _pending_identity(basis)}
    probe = {"schema": LEDGER_PENDING_SCHEMA,
             "record_id": ledger["record_id"], "queued_at": iso(), **basis}
    encoded_probe = (json.dumps(
        probe, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False) + "\n").encode("utf-8")
    if len(encoded_probe) > MAX_LEDGER_PENDING_RECORD_BYTES:
        raise ValueError("pulse ledger binding exceeds recovery record bound")
    rebound = {key: value for key, value in marker.items()
               if key != "ledger"}
    rebound["ledger"] = ledger
    updated = dict(memo, pulse_publication=rebound)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return ledger


def _settle_pending_pulse_ledger(memo):
    marker = _pending_pulse_marker(memo)
    if marker is None or "ledger" not in marker:
        raise RuntimeError("pulse publication ledger binding is absent")
    ledger = marker["ledger"]
    path = queue_ledger_transition(
        ledger["order"], ledger["action"], ledger["arg1"],
        ledger["arg2"], ledger["content"])
    _settle_ledger_transition(path)
    return ledger


def _pending_dream_marker(memo):
    marker = memo.get("dream_publication")
    if marker is None:
        return None
    required = {"v", "id", "started_at"}
    optional = {"ledger", "cycle", "redactions"}
    if not isinstance(marker, dict) \
            or not required.issubset(marker) \
            or set(marker) - required - optional \
            or not _exact_int(marker.get("v"), 1) \
            or not isinstance(marker.get("id"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", marker["id"]) is None \
            or not isinstance(marker.get("started_at"), str):
        raise RuntimeError("dream publication recovery marker is invalid")
    try:
        if _canonical_utc_timestamp(marker["started_at"]) \
                != marker["started_at"]:
            raise ValueError
    except ValueError:
        raise RuntimeError(
            "dream publication recovery marker is invalid") from None
    if memo.get("sync_needed") is not True:
        raise RuntimeError("dream publication marker has no publication debt")
    if "redactions" in marker \
            and _recoverable_pulse_redactions(
                memo, marker["redactions"]) is None:
        raise RuntimeError(
            "dream publication redactions binding is invalid")
    if "ledger" in marker:
        ledger = marker["ledger"]
        if not isinstance(ledger, dict) or set(ledger) != {
                "order", "action", "arg1", "arg2", "content",
                "record_id"}:
            raise RuntimeError("dream publication ledger binding is invalid")
        try:
            basis = _pending_basis(
                ledger["order"], ledger["action"], ledger["arg1"],
                ledger["arg2"], ledger["content"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "dream publication ledger binding is invalid") from exc
        expected = {**basis, "record_id": _pending_identity(basis)}
        if ledger != expected or basis["action"] != "DREAM:publish":
            raise RuntimeError("dream publication ledger binding is invalid")
    if "cycle" in marker:
        cycle = marker["cycle"]
        if not isinstance(cycle, dict) or set(cycle) != {
                "ledger", "thought"}:
            raise RuntimeError("dream cycle recovery binding is invalid")
        ledger = cycle["ledger"]
        if not isinstance(ledger, dict) or set(ledger) != {
                "order", "action", "arg1", "arg2", "content",
                "record_id"}:
            raise RuntimeError("dream cycle recovery binding is invalid")
        try:
            basis = _pending_basis(
                ledger["order"], ledger["action"], ledger["arg1"],
                ledger["arg2"], ledger["content"])
            thought = _canonical_thought_page_record(cycle["thought"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError("dream cycle recovery binding is invalid") \
                from exc
        expected = {**basis, "record_id": _pending_identity(basis)}
        if ledger != expected or basis["action"] != "DREAM:cycle" \
                or thought != cycle["thought"] \
                or thought.get("queue_id") != marker["id"] \
                or thought.get("kind") != "dream" \
                or thought.get("origin") != "derived":
            raise RuntimeError("dream cycle recovery binding is invalid")
    return marker


def _mark_dream_publication(memo, redactions=None):
    if redactions is not None:
        redactions = _pulse_redactions_at_least_memo(memo, redactions)
    marker = _pending_dream_marker(memo)
    if marker is not None:
        if redactions is not None and marker.get("redactions") != redactions:
            rebound = dict(marker, redactions=redactions)
            updated = dict(memo, dream_publication=rebound)
            _write_memo(updated)
            memo.clear()
            memo.update(updated)
            return _pending_dream_marker(memo)
        return marker
    marker = {"v": 1, "id": uuid.uuid4().hex, "started_at": iso()}
    if redactions is not None:
        marker["redactions"] = redactions
    updated = dict(memo, dream_publication=marker, sync_needed=True)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return marker


def _checkpoint_dream_redactions(memo):
    """Bind diagnostic omissions before any maintenance sink can persist."""
    marker = _pending_dream_marker(memo)
    if not REDACTIONS:
        return marker
    target = _projected_pulse_redactions(memo)
    if marker is None:
        # Independent pre-cycle units have no named publication marker yet.
        # Make their cumulative omission count durable before their ledger or
        # generated-entry sink. Once the gbrain cycle starts, the named marker below
        # provides the stronger crash handoff used by publication recovery.
        updated = dict(memo, redactions=copy.deepcopy(target))
        _write_memo(updated)
        memo.clear()
        memo.update(updated)
    else:
        marker = _mark_dream_publication(memo, target)
        memo["redactions"] = copy.deepcopy(target)
        if marker.get("redactions") != memo["redactions"]:
            raise RuntimeError(
                "dream publication redactions binding is invalid")
    REDACTIONS.clear()
    return marker


def _dream_diagnostic(memo, value, limit):
    """Return inert secret-free detail with a durable cumulative receipt."""
    detail = clip(redact(value, "status-error"), limit)
    _checkpoint_dream_redactions(memo)
    return detail


def _bind_pending_dream_ledger(memo, arg1, arg2, content, *, replace=False):
    marker = _pending_dream_marker(memo)
    if marker is None:
        raise RuntimeError("dream publication has no recovery identity")
    if "ledger" in marker and not replace:
        return marker["ledger"]
    basis = _pending_basis(
        time.time_ns(), "DREAM:publish", arg1, arg2, content)
    ledger = {**basis, "record_id": _pending_identity(basis)}
    probe = {"schema": LEDGER_PENDING_SCHEMA,
             "record_id": ledger["record_id"], "queued_at": iso(), **basis}
    encoded_probe = (json.dumps(
        probe, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False) + "\n").encode("utf-8")
    if len(encoded_probe) > MAX_LEDGER_PENDING_RECORD_BYTES:
        raise ValueError("dream ledger binding exceeds recovery record bound")
    rebound = {key: value for key, value in marker.items()
               if key != "ledger"}
    rebound["ledger"] = ledger
    updated = dict(memo, dream_publication=rebound)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return ledger


def _settle_pending_dream_ledger(memo):
    marker = _pending_dream_marker(memo)
    if marker is None or "ledger" not in marker:
        raise RuntimeError("dream publication ledger binding is absent")
    ledger = marker["ledger"]
    path = queue_ledger_transition(
        ledger["order"], ledger["action"], ledger["arg1"],
        ledger["arg2"], ledger["content"])
    _settle_ledger_transition(path)
    return ledger


def _bind_pending_dream_cycle(memo, dream_state, arg1, arg2, content,
                              thought_text, *, urgent=False):
    """Persist one exact cycle result before status, ledger, or generated entry."""
    marker = _pending_dream_marker(memo)
    if marker is None:
        raise RuntimeError("dream cycle has no publication identity")
    if "cycle" in marker:
        return marker["cycle"]
    if not isinstance(dream_state, dict):
        raise ValueError("dream cycle status must be an object")
    thought = _canonical_thought_page_record({
        "ts": iso(), "kind": "dream", "text": thought_text,
        "links": ["sia/cortex"], "urgent": bool(urgent),
        "origin": "derived", "queue_id": marker["id"],
    })
    basis = _pending_basis(
        time.time_ns(), "DREAM:cycle", arg1, arg2, content)
    ledger = {**basis, "record_id": _pending_identity(basis)}
    probe = {"schema": LEDGER_PENDING_SCHEMA,
             "record_id": ledger["record_id"], "queued_at": iso(), **basis}
    if len((json.dumps(
            probe, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False) + "\n").encode("utf-8")) \
            > MAX_LEDGER_PENDING_RECORD_BYTES:
        raise ValueError("dream cycle ledger binding exceeds record bound")
    cycle = {"ledger": ledger, "thought": thought}
    rebound = dict(marker, cycle=cycle)
    updated = dict(memo, dream=dream_state,
                   dream_publication=rebound, sync_needed=True)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return cycle


def _complete_pending_dream_cycle(memo, store):
    """Idempotently finish a marker-bound cycle row and generated result."""
    marker = _pending_dream_marker(memo)
    if marker is None or "cycle" not in marker:
        return False
    cycle = marker["cycle"]
    ledger = cycle["ledger"]
    path = queue_ledger_transition(
        ledger["order"], ledger["action"], ledger["arg1"],
        ledger["arg2"], ledger["content"])
    _settle_ledger_transition(path)
    thought = cycle["thought"]
    add_thought(
        store, thought["kind"], thought["text"], thought["links"],
        thought["urgent"], queue_id=thought["queue_id"],
        thought_ts=thought["ts"], origin=thought["origin"])
    export_thoughts(store)
    current = _pending_dream_marker(memo)
    completed_marker = {key: value for key, value in current.items()
                        if key != "cycle"}
    updated = dict(memo, dream_publication=completed_marker)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return True


def _recover_pending_dream_publication(memo):
    """Sign and clear interrupted maintenance after projections are current."""
    marker = _pending_dream_marker(memo)
    if marker is None:
        return False
    if "cycle" in marker:
        raise RuntimeError("dream cycle recovery must complete before publish")
    if "redactions" in marker:
        memo["redactions"] = copy.deepcopy(
            _pulse_redactions_at_least_memo(memo, marker["redactions"]))
    ledger = marker.get("ledger")
    if ledger is not None:
        _settle_pending_dream_ledger(memo)
    if ledger is None or ledger["arg1"] not in {"ok", "recovered"}:
        marker_content = json.dumps(
            {key: value for key, value in marker.items() if key != "ledger"},
            sort_keys=True, separators=(",", ":"))
        _bind_pending_dream_ledger(
            memo, "recovered", marker["id"], marker_content, replace=True)
        _settle_pending_dream_ledger(memo)
    updated = dict(memo)
    updated.pop("dream_publication", None)
    if "pulse_publication" not in updated:
        updated.pop("sync_needed", None)
        updated = _with_ready_receipt(updated, "dream", marker["id"])
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return True



_EPOCH_EXEMPLAR_KIND_RE = re.compile(
    r"^- (?:[0-9]{4}-[0-9]{2}-[0-9]{2} · )?\S+ ([A-Z][A-Z_]*):")
MAX_EPOCH_EXEMPLARS = 8
MAX_WEEKLY_EPOCH_EXEMPLARS = 24


@contextlib.contextmanager
def corpus_publication(memo=None):
    """Yield a write-ahead callback for a caller holding corpus_owner()."""
    memo = load_memo() if memo is None else memo
    if not isinstance(memo, dict) \
            or not isinstance(memo.get("sync_needed", False), bool):
        raise RuntimeError("brainstem memo sync-needed state is invalid")
    before_publish = lambda: _mark_external_corpus_mutation(memo)
    with corpus_mutation_barrier(before_publish):
        yield before_publish


def _settle_pending_publication(memo, message, *, clear=True):
    """Publish owed bytes before a query; optionally retain crash debt."""
    if memo.get("sync_needed") is not True:
        return
    if clear and (memo.get("pulse_publication") is not None
                  or memo.get("dream_publication") is not None):
        raise RuntimeError(
            "named publication recovery must settle before debt can clear")
    commit = corpus_commit(message)
    if commit == "error":
        raise RuntimeError("pending corpus git commit failed")
    synced, sync_note = brain_sync()
    if not synced:
        raise RuntimeError(f"pending index sync failed: {sync_note}")
    try:
        _export_graph_publication()
    except Exception as exc:
        raise RuntimeError(
            f"pending graph publication failed: {exc}") from exc
    if clear:
        updated = dict(memo)
        updated.pop("sync_needed", None)
        updated = _with_ready_receipt(updated, "recovery")
        _write_memo(updated)
        memo.clear()
        memo.update(updated)


_RECOVERABLE_STATUS_KEYS = frozenset({
    "v", "version", "ts", "state", "pulse_seq", "day",
    "publication_id", "graph_publication_id", "events_pulse",
    "events_today", "organs", "errors", "pages", "graph_nodes",
    "graph_edges", "integrity", "ledger", "ledger_transition", "thought",
    "dream", "history", "workspace", "mind", "takes", "intents",
    "bench_trend", "bench_trend_boundary", "projection_debt",
    "agent_queue", "redactions", "sync_note",
})
_EFFECTLESS_STATUS_VERSIONS = frozenset({"1.7.7", "1.7.8"})
_LEGACY_EFFECTLESS_STATUS_KEYS = (
    _RECOVERABLE_STATUS_KEYS - {"graph_publication_id"})
_STATUS_MIND_COUNT_KEYS = frozenset({
    "nodes", "edges", "decay_active", "decay_demoted",
    "rehearsal_eligible", "rehearsal_due", "pinned",
})
_STATUS_AGENT_QUEUE_KEYS = frozenset({
    "materialized", "refused", "acknowledged",
})
_STATUS_TAKE_KEYS = frozenset({
    "open", "due", "resolved", "brier", "calibration_status",
    "monitoring_display_eligible", "unresolvable", "invalid_resolved",
    "invalid_records",
})
_STATUS_TAKE_COUNT_KEYS = _STATUS_TAKE_KEYS - {
    "brier", "calibration_status", "monitoring_display_eligible",
}
_STATUS_CALIBRATION_STATES = frozenset({
    "no-resolved-outcomes", "single-case", "descriptive-series",
    "outcome-imbalanced", "monitoring-population",
})
_STATUS_THOUGHT_ORIGINS = THOUGHT_ORIGINS | {"legacy-unlabeled"}


def _nonnegative_status_integer(value):
    return not isinstance(value, bool) and isinstance(value, int) \
        and 0 <= value <= MAX_JSON_SAFE_INTEGER


def _status_calendar_date(value):
    if not isinstance(value, str) \
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        return False
    try:
        return datetime.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _status_history_shape(value):
    if not isinstance(value, list) \
            or len(value) > MAX_PULSE_HISTORY_ROWS:
        return False
    for row in value:
        if not isinstance(row, list) or len(row) != 2 \
                or not _nonnegative_status_integer(row[1]):
            return False
        try:
            if _canonical_utc_timestamp(row[0]) != row[0]:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _status_chains_shape(value):
    # Every configured row yields at most one chain or refusal, alongside the
    # four possible built-in chains.  Reject pre-bound cached rosters too so an
    # oversized legacy memo cannot keep expanding status and CLI consumers.
    max_rows = MAX_CONFIGURED_CHAINS + len(
        {"sia", "custos", "sekhmet", "aegis"})
    return isinstance(value, dict) and "sia" in value \
        and len(value) <= max_rows and all(
        _strict_config_string(
            name, nonempty=True, limit=MAX_SOURCE_NAME_CHARS)
        and sanitize_slugpart(name) == name
        and isinstance(verdict, str)
        and verdict in {"pass", "fail", "absent"}
        for name, verdict in value.items())


def _cached_chain_sweep(memo):
    """Return a complete cached sweep and its real observation time."""
    chains = memo.get("chains") if isinstance(memo, dict) else None
    checked_at = (
        memo.get("chains_checked_at") if isinstance(memo, dict) else None)
    if not _status_chains_shape(chains):
        return None
    try:
        if _canonical_utc_timestamp(checked_at) != checked_at:
            return None
    except (TypeError, ValueError):
        return None
    return copy.deepcopy(chains), checked_at


def _status_publication_id(value, *, empty=False):
    return isinstance(value, str) and (
        empty and value == ""
        or re.fullmatch(r"[0-9a-f]{32}", value) is not None)


def _status_ledger_shape(value):
    if not isinstance(value, dict) or set(value) != {"seq", "head"} \
            or not _nonnegative_status_integer(value.get("seq")) \
            or not isinstance(value.get("head"), str):
        return False
    return (value["seq"] == 0 and value["head"] == "") \
        or (value["seq"] > 0
            and re.fullmatch(r"[0-9a-f]{12}", value["head"]) is not None)


def _status_thought_shape(value):
    if not isinstance(value, dict) \
            or set(value) != {"ts", "kind", "text", "origin"} \
            or value.get("origin") not in _STATUS_THOUGHT_ORIGINS:
        return False
    if value["ts"] == "":
        return value["kind"] == "" and value["text"] == "" \
            and value["origin"] == "legacy-unlabeled"
    if not _status_display_string(
            value.get("kind"), nonempty=True,
            limit=MAX_THOUGHT_INBOX_TEXT) \
            or sanitize_slugpart(value["kind"]) != value["kind"] \
            or not _status_display_string(
                value.get("text"), nonempty=True,
                limit=MAX_THOUGHT_INBOX_TEXT):
        return False
    try:
        return _canonical_utc_timestamp(value["ts"]) == value["ts"]
    except (TypeError, ValueError):
        return False


def _status_thought_projection(value):
    """Project a store row, or expose the exact unlabeled-empty boundary."""
    value = value if isinstance(value, dict) else {}
    origin = value.get("origin")
    if origin not in THOUGHT_ORIGINS:
        origin = "legacy-unlabeled"
    projected = {
        "ts": value.get("ts", ""), "kind": value.get("kind", ""),
        "text": value.get("text", ""), "origin": origin,
    }
    if _status_thought_shape(projected):
        return projected
    return {"ts": "", "kind": "", "text": "",
            "origin": "legacy-unlabeled"}


def _status_dream_shape(value):
    if value == {}:
        return True
    if not isinstance(value, dict):
        return False
    keys = set(value)
    if keys == {"last", "status", "summary"}:
        try:
            return _canonical_utc_timestamp(value["last"]) == value["last"] \
                and value.get("status") in {"ok", "clean", "partial"} \
                and _status_display_string(
                    value.get("summary"), limit=400)
        except (TypeError, ValueError):
            return False
    if keys != {"last", "attempt", "status", "summary"} \
            or not _status_display_string(
                value.get("status"), nonempty=True, limit=80) \
            or not _status_display_string(
                value.get("summary"), limit=160):
        return False
    try:
        if value["last"] and _canonical_utc_timestamp(value["last"]) \
                != value["last"]:
            return False
        return _canonical_utc_timestamp(value["attempt"]) == value["attempt"]
    except (TypeError, ValueError):
        return False


def _status_takes_shape(value):
    if value == {}:
        return True
    if not isinstance(value, dict) or set(value) != _STATUS_TAKE_KEYS \
            or any(not _nonnegative_status_integer(value.get(key))
                   for key in _STATUS_TAKE_COUNT_KEYS) \
            or value["due"] > value["open"] \
            or value.get("calibration_status") \
                not in _STATUS_CALIBRATION_STATES \
            or not isinstance(value.get("monitoring_display_eligible"), bool):
        return False
    brier = value.get("brier")
    if brier is not None and (
            isinstance(brier, bool) or not isinstance(brier, (int, float))
            or not math.isfinite(brier) or not 0 <= brier <= 1):
        return False
    status = value["calibration_status"]
    resolved = value["resolved"]
    if (status == "no-resolved-outcomes") != (resolved == 0) \
            or (brier is None) != (resolved == 0) \
            or (status == "single-case") != (resolved == 1) \
            or value["monitoring_display_eligible"] \
                != (status == "monitoring-population"):
        return False
    if resolved < siatakes.CALIBRATION_MIN_RESOLVED:
        expected = ("no-resolved-outcomes" if resolved == 0 else
                    "single-case" if resolved == 1 else
                    "descriptive-series")
        if status != expected:
            return False
    elif status not in {"outcome-imbalanced", "monitoring-population"}:
        return False
    return True


def _status_display_string(value, *, nonempty=False, limit):
    """Recognize a bounded inert string with no omitted secret-shaped span."""
    return _strict_config_string(
        value, nonempty=nonempty, limit=limit) \
        and inert_summary(value) == value \
        and _redaction_projection(value) == (value, 0)


def _status_errors_shape(value):
    if not isinstance(value, dict) \
            or len(value) > MAX_LEDGER_PENDING_RECORDS:
        return False
    for name, detail in value.items():
        if not _status_display_string(
                name, nonempty=True, limit=MAX_SOURCE_NAME_CHARS):
            return False
        if isinstance(detail, str):
            if not _status_display_string(detail, limit=160):
                return False
            continue
        if not isinstance(detail, list) \
                or len(detail) > MAX_LEDGER_PENDING_RECORDS:
            return False
        for row in detail:
            if not isinstance(row, dict) \
                    or set(row) not in ({"file", "error"},
                                        {"config", "error"}):
                return False
            label = row.get("file", row.get("config"))
            if not _status_display_string(
                    label, nonempty=True, limit=MAX_CONFIG_PATH_CHARS) \
                    or not _status_display_string(
                        row.get("error"), limit=160):
                return False
    return True


def _redacted_status_errors(value):
    """Sanitize the producer's bounded error union before publication."""
    refused = {"status_projection":
               "malformed status error detail refused"}
    if not isinstance(value, dict) \
            or len(value) > MAX_LEDGER_PENDING_RECORDS:
        return refused
    result = {}
    for name, detail in value.items():
        if not isinstance(name, str):
            return refused
        safe_name = clip(redact(name, "status-error"),
                         MAX_SOURCE_NAME_CHARS)
        if not _status_display_string(
                safe_name, nonempty=True, limit=MAX_SOURCE_NAME_CHARS) \
                or safe_name in result:
            return refused
        if isinstance(detail, str):
            result[safe_name] = clip(
                redact(detail, "status-error"), 160)
            continue
        if not isinstance(detail, list):
            return refused
        if len(detail) > MAX_LEDGER_PENDING_RECORDS:
            return refused
        rows = []
        for row in detail:
            if not isinstance(row, dict) \
                    or set(row) not in ({"file", "error"},
                                        {"config", "error"}):
                return refused
            sanitized = {}
            for field, raw in row.items():
                if not isinstance(raw, str):
                    return refused
                limit = MAX_CONFIG_PATH_CHARS if field != "error" else 160
                sanitized[field] = clip(
                    redact(raw, "status-error"), limit)
            rows.append(sanitized)
        result[safe_name] = rows
    return result if _status_errors_shape(result) else refused


def _status_redactions_shape(value):
    return isinstance(value, dict) \
        and len(value) <= MAX_LEDGER_PENDING_RECORDS \
        and all(_strict_config_string(
                    organ, nonempty=True, limit=MAX_SOURCE_NAME_CHARS)
                and sanitize_slugpart(organ) == organ
                and _nonnegative_status_integer(count)
                for organ, count in value.items())


def _status_workspace_shape(value):
    if not isinstance(value, list) or len(value) > siamind.WORKSPACE_K:
        return False
    seen = set()
    for row in value:
        try:
            if _canonical_corpus_slug(row) != row or row in seen:
                return False
        except (TypeError, ValueError):
            return False
        seen.add(row)
    return True


def _status_intents_shape(value):
    if not isinstance(value, list) or len(value) > MAX_STATUS_INTENTS:
        return False
    for row in value:
        if not isinstance(row, dict) or set(row) != {
                "id", "text", "due", "days_left"} \
                or not isinstance(row.get("id"), str) \
                or re.fullmatch(r"[0-9a-f]{10}", row["id"]) is None \
                or not _status_display_string(
                    row.get("text"), nonempty=True, limit=70) \
                or not _status_calendar_date(row.get("due")) \
                or isinstance(row.get("days_left"), bool) \
                or not isinstance(row.get("days_left"), int) \
                or abs(row["days_left"]) > MAX_JSON_SAFE_INTEGER:
            return False
    return True


def _status_bench_trend_shape(value):
    if not isinstance(value, list) or len(value) > MAX_BENCH_TREND_ROWS:
        return False
    for row in value:
        metric = row.get("slug_match_at_5") if isinstance(row, dict) else None
        if not isinstance(row, dict) or set(row) != {
                "date", "slug_match_at_5", "kind"} \
                or not _status_calendar_date(row.get("date")) \
                or not isinstance(metric, (int, float)) \
                or isinstance(metric, bool) or not math.isfinite(metric) \
                or not 0 <= metric <= 1 \
                or row.get("kind") != \
                "heuristic-slug-retrieval-drift-tripwire":
            return False
    return True


def _recoverable_status_integrity_checked(value):
    """Return a valid retained verdict, else refuse a hybrid status overlay."""
    if not isinstance(value, dict) \
            or set(value) != _RECOVERABLE_STATUS_KEYS \
            or type(value.get("v")) is not int or value["v"] not in {1, 2} \
            or value.get("version") != VERSION \
            or not isinstance(value.get("state"), str) \
            or value.get("state") not in {
                "failed", "degraded", "thinking", "ok"} \
            or not _status_calendar_date(value.get("day")) \
            or any(not _nonnegative_status_integer(value.get(key))
                   for key in (
                       "pulse_seq", "events_pulse", "events_today", "pages",
                       "graph_nodes", "graph_edges")) \
            or not _status_publication_id(value.get("publication_id")) \
            or not _status_publication_id(
                value.get("graph_publication_id"), empty=True) \
            or value.get("graph_nodes") > MAX_GRAPH_NODES \
            or value.get("graph_edges") > MAX_GRAPH_EDGES \
            or value.get("graph_nodes") > value.get("pages") \
            or value.get("graph_nodes") == 0 \
            and value.get("graph_edges") != 0 \
            or value.get("graph_publication_id") == "" and any(
                value.get(key) != 0
                for key in ("pages", "graph_nodes", "graph_edges")) \
            or not isinstance(value.get("organs"), dict) \
            or not _status_errors_shape(value.get("errors")) \
            or not _status_display_string(
                value.get("sync_note"), limit=400):
        return None
    try:
        if _canonical_pulse_effects(
                value["day"], value["events_pulse"],
                value["organs"]) != {
                    "day": value["day"],
                    "events_pulse": value["events_pulse"],
                    "organs": value["organs"],
                } or value["events_today"] != sum(
                    state["today"] for state in value["organs"].values()):
            return None
    except (TypeError, ValueError, RuntimeError):
        return None
    try:
        if _canonical_utc_timestamp(value["ts"]) != value["ts"]:
            return None
    except (TypeError, ValueError):
        return None
    projection = value.get("projection_debt")
    mind = value.get("mind")
    agent_queue = value.get("agent_queue")
    ledger = value.get("ledger")
    ledger_transition = value.get("ledger_transition")
    if not isinstance(projection, dict) \
            or set(projection) != {"graph", "consolidation"} \
            or any(not _status_display_string(projection[key], limit=400)
                   for key in projection) \
            or not isinstance(mind, dict) \
            or set(mind) != (_STATUS_MIND_COUNT_KEYS | (
                {"familiarity_status"} if value["v"] == 2 else set())) \
            or any(not _nonnegative_status_integer(mind[key])
                   for key in _STATUS_MIND_COUNT_KEYS) \
            or value["v"] == 2 and (
                not isinstance(mind.get("familiarity_status"), str)
                or mind["familiarity_status"] not in {
                    "complete", "incomplete", "bootstrap-pending"}) \
            or mind["decay_active"] + mind["decay_demoted"] \
                != mind["edges"] \
            or mind["rehearsal_due"] > mind["rehearsal_eligible"] \
            or mind["rehearsal_eligible"] > mind["nodes"] \
            or mind["pinned"] > mind["nodes"] \
            or not isinstance(agent_queue, dict) \
            or set(agent_queue) != _STATUS_AGENT_QUEUE_KEYS \
            or any(not _nonnegative_status_integer(agent_queue[key])
                   for key in agent_queue) \
            or agent_queue["materialized"] \
                > siaqueue.MAX_PENDING_REQUESTS \
            or agent_queue["acknowledged"] \
                > agent_queue["materialized"] \
            or agent_queue["refused"] \
                > siaqueue.MAX_PENDING_REQUESTS + 1 \
            or not _status_ledger_shape(ledger) \
            or not isinstance(ledger_transition, dict) \
            or set(ledger_transition) != {
                "state", "recovered", "pending_errors"} \
            or not isinstance(ledger_transition.get("state"), str) \
            or ledger_transition.get("state") not in {
                "not-required", "signed", "pending"} \
            or not _nonnegative_status_integer(
                ledger_transition.get("recovered")) \
            or not _nonnegative_status_integer(
                ledger_transition.get("pending_errors")) \
            or ledger_transition["recovered"] \
                > MAX_LEDGER_PENDING_RECORDS \
            or ledger_transition["pending_errors"] != 0 \
            or ledger_transition["state"] == "pending" \
                and not value["errors"] \
            or not _status_thought_shape(value.get("thought")) \
            or not _status_dream_shape(value.get("dream")) \
            or not _status_history_shape(value.get("history")) \
            or not _status_workspace_shape(value.get("workspace")) \
            or not _status_takes_shape(value.get("takes")) \
            or not _status_intents_shape(value.get("intents")) \
            or not _status_bench_trend_shape(value.get("bench_trend")) \
            or not isinstance(value.get("bench_trend_boundary"), dict) \
            or set(value["bench_trend_boundary"]) != {
                "legacy_truncated"} \
            or not isinstance(
                value["bench_trend_boundary"].get("legacy_truncated"), bool) \
            or not _status_redactions_shape(value.get("redactions")):
        return None
    integrity = value.get("integrity")
    if not isinstance(integrity, dict) \
            or set(integrity) != {"chains", "verdict", "checked_at"} \
            or not _status_chains_shape(integrity.get("chains")):
        return None
    try:
        if _canonical_utc_timestamp(integrity["checked_at"]) \
                != integrity["checked_at"]:
            return None
    except (TypeError, ValueError):
        return None
    chain_values = set(integrity["chains"].values())
    verdict = ("fail" if "fail" in chain_values else
               "degraded" if "absent" in chain_values else "pass")
    if integrity.get("verdict") != verdict \
            or integrity["chains"].get("sia") == "pass" \
            and ledger["seq"] == 0 \
            or verdict == "fail" and value["state"] != "failed" \
            or value["state"] in {"ok", "thinking"} and verdict != "pass" \
            or value["state"] in {"ok", "thinking"} \
            and (value["errors"] or value["sync_note"]):
        return None
    return verdict


def _recoverable_status_integrity(value):
    """Total retained-status validator for arbitrary strict-JSON values."""
    try:
        return _recoverable_status_integrity_checked(value)
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
        return None


def _recoverable_legacy_effectless_status_integrity(value):
    """Validate only the frozen status roster emitted by effectless markers."""
    if not isinstance(value, dict) \
            or set(value) != _LEGACY_EFFECTLESS_STATUS_KEYS \
            or not isinstance(value.get("version"), str) \
            or value["version"] not in _EFFECTLESS_STATUS_VERSIONS:
        return None
    legacy_ledger = value.get("ledger")
    recoverable_empty_ledger = (
        isinstance(legacy_ledger, dict)
        and set(legacy_ledger) == {"seq", "head"}
        and _exact_int(legacy_ledger.get("seq"), 0)
        and legacy_ledger.get("head") == "")
    # Frozen producers predate graph-generation identities but could still
    # report nonempty graph counts.  Supply a canonical validation-only
    # identity so the current empty-ID/zero-count invariant does not erase
    # that exact historical shape; recovery below still cannot treat those
    # unbound counts as a published current graph generation.
    normalized = dict(
        value, version=VERSION,
        graph_publication_id=value.get("publication_id"))
    if recoverable_empty_ledger \
            and normalized.get("integrity", {}).get("chains", {}).get(
                "sia") == "pass":
        # The frozen producer could independently verify the keeper and then
        # swallow a second head-read failure. Preserve that exact historical
        # crash image without admitting the mismatch for current publishers.
        normalized["ledger"] = {"seq": 1, "head": "0" * 12}
    return _recoverable_status_integrity(normalized)


def _expected_legacy_effectless_history(memo, status, events_pulse):
    """Bind a frozen-runtime status row to its exact durable memo prefix."""
    history = copy.deepcopy(memo.get("pulse_history", []))
    status_history = status.get("history")
    if not _status_history_shape(history) \
            or not _status_history_shape(status_history) \
            or not status_history \
            or status_history[-1][1] != events_pulse:
        raise RuntimeError(
            "effectless pulse publication recovery is ambiguous")
    history.append(copy.deepcopy(status_history[-1]))
    history = history[-MAX_PULSE_HISTORY_ROWS:]
    if status_history != history:
        raise RuntimeError(
            "effectless pulse publication recovery is ambiguous")
    return history


def _status_release_tuple(value):
    if not _strict_config_string(
            value, nonempty=True, limit=MAX_SOURCE_NAME_CHARS):
        return None
    match = re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value)
    if match is None:
        return None
    parts = tuple(int(part) for part in match.groups())
    return parts if all(part <= MAX_JSON_SAFE_INTEGER for part in parts) \
        else None


def _pending_brainstem_failure_publication(memo):
    """Validate a current replay or a narrowly retireable older journal."""
    marker = memo.get("brainstem_failure_pending") \
        if isinstance(memo, dict) else None
    if marker is None:
        return None
    status = marker.get("status") if isinstance(marker, dict) else None
    if isinstance(marker, dict) and set(marker) == {"v", "status"} \
            and _exact_int(marker.get("v"), 1):
        if _recoverable_status_integrity(status) is None \
                or status.get("state") != "failed" \
                or status.get("redactions") != memo.get("redactions", {}):
            raise RuntimeError(
                "brainstem failure publication marker is invalid")
        return marker
    if not isinstance(marker, dict) \
            or set(marker) != {"v", "producer_version", "status"} \
            or not _exact_int(marker.get("v"), 2):
        raise RuntimeError("brainstem failure publication marker is invalid")
    producer = marker.get("producer_version")
    producer_release = _status_release_tuple(producer)
    current_release = _status_release_tuple(VERSION)
    if producer_release is None or current_release is None \
            or not isinstance(status, dict) \
            or type(status.get("v")) is not int or status["v"] not in {1, 2} \
            or status.get("version") != producer \
            or status.get("state") != "failed" \
            or not _nonnegative_status_integer(status.get("pulse_seq")) \
            or not _status_publication_id(status.get("publication_id")) \
            or not _status_redactions_shape(status.get("redactions")) \
            or status.get("redactions") != memo.get("redactions", {}):
        raise RuntimeError("brainstem failure publication marker is invalid")
    try:
        if _canonical_utc_timestamp(status["ts"]) != status["ts"]:
            raise RuntimeError(
                "brainstem failure publication marker is invalid")
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "brainstem failure publication marker is invalid") from exc
    if producer_release > current_release:
        raise RuntimeError(
            "brainstem failure publication marker is from a newer runtime")
    if producer_release == current_release \
            and _recoverable_status_integrity(status) is None:
        raise RuntimeError("brainstem failure publication marker is invalid")
    return marker


def _finish_brainstem_failure_publication(memo, marker):
    """Replay this schema, or retire an older failure before new work."""
    if marker is None:
        return False
    producer = marker.get("producer_version", VERSION)
    if producer == VERSION:
        export_status(marker["status"])
    updated = dict(memo)
    updated.pop("brainstem_failure_pending", None)
    # A superseded failure still requires a successful current pulse before
    # memory readiness can return, even though its incompatible display bytes
    # cannot safely be republished by this runtime.
    if producer != VERSION:
        updated.pop("ready", None)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    if producer != VERSION:
        log("retired superseded brainstem failure publication from "
            + producer)
    return True


def _settle_pending_brainstem_failure_publication(memo):
    marker = _pending_brainstem_failure_publication(memo)
    return _finish_brainstem_failure_publication(memo, marker)


def _checkpoint_status_error_redactions(memo):
    """Atomically bind late daemon-log omissions to every active journal."""
    if not REDACTIONS:
        return False
    target = _projected_pulse_redactions(memo)
    updated = dict(memo, redactions=copy.deepcopy(target))
    pulse_marker = _pending_pulse_marker(memo)
    if pulse_marker is not None:
        updated["pulse_publication"] = dict(
            pulse_marker, redactions=copy.deepcopy(target))
    dream_marker = _pending_dream_marker(memo)
    if dream_marker is not None:
        updated["dream_publication"] = dict(
            dream_marker, redactions=copy.deepcopy(target))
    failure_marker = _pending_brainstem_failure_publication(memo)
    if failure_marker is not None:
        producer = failure_marker.get("producer_version", VERSION)
        if producer != VERSION:
            raise RuntimeError(
                "cannot rebind a superseded failure publication")
        status = dict(
            failure_marker["status"], redactions=copy.deepcopy(target),
            publication_id=uuid.uuid4().hex, ts=iso())
        if _recoverable_status_integrity(status) is None:
            raise RuntimeError(
                "rebound failure status projection is invalid")
        updated["brainstem_failure_pending"] = dict(
            failure_marker, status=status)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    REDACTIONS.clear()
    return True


def _require_status_memo_fields(memo):
    """Withdraw readiness before refusing memo fields copied into status."""
    history = memo.get("pulse_history", []) if isinstance(memo, dict) else None
    dream_state = memo.get("dream", {}) if isinstance(memo, dict) else None
    redactions = memo.get("redactions", {}) if isinstance(memo, dict) else None
    note_receipts = memo.get("agent_note_redaction_receipts") \
        if isinstance(memo, dict) else None
    valid = (
        isinstance(memo, dict)
        and "brainstem_failure_pending" not in memo
        and _status_history_shape(history)
        and _status_dream_shape(dream_state)
        and _status_redactions_shape(redactions))
    if valid:
        try:
            _agent_note_redaction_receipts(note_receipts)
        except RuntimeError:
            valid = False
    if valid:
        return
    if isinstance(memo, dict) and "ready" in memo:
        updated = dict(memo)
        updated.pop("ready", None)
        _write_memo(updated)
        memo.clear()
        memo.update(updated)
    raise RuntimeError("brainstem status memo fields are invalid")


_STATUS_ADMISSION_REQUIRED = object()


def _require_status_sequence_not_ahead(memo_sequence):
    """Refuse a retained publication that outruns the durable allocator."""
    if not _nonnegative_status_integer(memo_sequence):
        raise ValueError("brainstem pulse sequence is invalid")
    try:
        status = read_state_json(
            STATUS_PATH, None, "resident status", expected_type=dict)
    except RuntimeError as exc:
        raise ValueError("resident status cannot be admitted") from exc
    if status is None:
        return None
    current = _recoverable_status_integrity(status)
    legacy = _recoverable_legacy_effectless_status_integrity(status)
    if current is None and legacy is None:
        raise ValueError("resident status cannot be admitted")
    if status["pulse_seq"] > memo_sequence:
        raise ValueError(
            "resident status pulse sequence exceeds the durable memo")
    return status


def _require_status_admission_unchanged(admitted_status):
    if admitted_status is not None \
            and _recoverable_status_integrity(admitted_status) is None \
            and _recoverable_legacy_effectless_status_integrity(
                admitted_status) is None:
        raise RuntimeError("resident status admission is invalid")
    try:
        current = read_state_json(
            STATUS_PATH, None, "resident status", expected_type=dict)
    except RuntimeError as exc:
        raise RuntimeError(
            "resident status changed after admission") from exc
    if current != admitted_status:
        raise RuntimeError("resident status changed after admission")
    return copy.deepcopy(admitted_status) if admitted_status is not None else {}


def _recover_pending_thought_projection(memo, store):
    """Rejoin every page-first generated entry and its review before new work."""
    pending = memo.get("sync_needed", False)
    if not isinstance(pending, bool):
        raise RuntimeError("brainstem memo sync-needed state is invalid")
    while True:
        try:
            recovered, _reinforced = _settle_thought_page_signals(store)
            return recovered
        except ThoughtRecoveryPending:
            # The installer invokes one fatal first-light transaction while
            # the old daemon is stopped. Drain every individually bounded
            # baseline generation there so a large upgrade does not require
            # an unknown number of manual installer reruns. Ordinary daemon
            # pulses commit one generation and visibly retry next pulse cycle.
            if os.environ.get("SIA_BACKFILL") != "1":
                raise
            continue


def _settle_thought_page_signals(store, mind=None):
    """Commit bounded generated-entry records to both states before acknowledgment."""
    if _CORPUS_OWNER_DEPTH.get() <= 0:
        with corpus_owner():
            return _settle_thought_page_signals(store, mind=mind)
    mind = siamind.load_mind() if mind is None else mind
    recovered_total = reinforced_total = 0
    while True:
        claim = _prepare_thought_recovery_claim()
        if claim is None:
            state = _load_thought_legacy_scan()
            if state["phase"] != "complete":
                raise ThoughtRecoveryPending(
                    "bounded legacy thought recovery remains pending")
            return recovered_total, reinforced_total
        recovered, reinforced = _apply_thought_recovery_claim(
            store, mind, claim)
        recovered_total += recovered
        reinforced_total += reinforced
        # Either write can fail independently. The immutable claim remains in
        # place, and its receipt lets the successful sibling skip exact replay
        # while the failed sibling catches up on the next attempt.
        siamind.save_mind(mind)
        export_thoughts(store)
        legacy = claim.get("legacy")
        generation_change = None
        if legacy is not None:
            try:
                _assert_legacy_thought_directory_generation(
                    legacy["directory"])
            except ThoughtDirectoryGenerationChanged as exc:
                generation_change = exc
        _commit_thought_legacy_claim(claim)
        _acknowledge_thought_recovery_claim(claim)
        if legacy is not None and generation_change is None:
            try:
                _assert_legacy_thought_directory_generation(
                    legacy["directory"])
            except ThoughtDirectoryGenerationChanged as exc:
                generation_change = exc
        if generation_change is not None:
            with _owner_lease(
                    _thought_recovery_lock_path(), "thought recovery"):
                _schedule_legacy_thought_reset_locked(
                    _load_thought_legacy_scan())
            raise RuntimeError(
                "legacy thought directory changed; durable reset scheduled; "
                "retry after corpus writers are quiescent") \
                from generation_change
        if legacy is None:
            return recovered_total, reinforced_total
        if not legacy["complete"]:
            raise ThoughtRecoveryPending(
                "bounded legacy thought recovery remains pending")
        # A final legacy batch may have coexisted with already-journaled native
        # pages. The legacy index is now chronological and complete, so settle
        # that one bounded native generation before allowing new work.


def _recover_pending_pulse_publication(memo):
    """Sign and clear an interrupted pulse after projections are current."""
    _pending_pulse_status_effects(memo)
    marker = _pending_pulse_marker(memo)
    if marker is None:
        return False
    ledger = marker.get("ledger")
    if ledger is not None:
        _settle_pending_pulse_ledger(memo)
    if ledger is None or ledger["arg2"] not in {
            "ok", "published-after-recovery",
            "partial-published-after-recovery"}:
        mind_replay = siamind.load_mind()
        partial = (_pending_source_replay_marker(memo) is not None
                   or bool(mind_replay.get("event_applied"))
                   or mind_replay.get("event_batch_applied") is not None
                   or (ledger is not None and ledger["arg2"] in {
                       "write-fail", "cursor-fail", "source-pending"}))
        recovery_result = ("partial-published-after-recovery"
                           if partial else "published-after-recovery")
        marker_content = json.dumps(
            {key: value for key, value in marker.items() if key != "ledger"},
            sort_keys=True, separators=(",", ":"))
        _bind_pending_pulse_ledger(
            memo, f"pulse={marker['seq']} recovery",
            recovery_result, marker_content, replace=True)
        _settle_pending_pulse_ledger(memo)
    marker = _pending_pulse_marker(memo)
    source_pending = _pending_source_replay_marker(memo) is not None
    effects = marker.get("effects")
    recovered_redactions = copy.deepcopy(marker.get("redactions"))
    current = None
    expected_history = None
    if effects is None and not source_pending:
        # Pre-contract runtimes could create a named publication marker
        # without binding its status effects. Recover those effects only from
        # a complete status carrying the exact marker identity and sequence;
        # without that durable binding, clearing the marker would silently
        # bless unknown counters.
        current = read_json(STATUS_PATH, {})
        retained_verdict = _recoverable_status_integrity(current)
        legacy_effectless = False
        if retained_verdict is None:
            retained_verdict = \
                _recoverable_legacy_effectless_status_integrity(current)
            legacy_effectless = retained_verdict is not None
        if retained_verdict is None \
                or current.get("publication_id") != marker["id"] \
                or current.get("pulse_seq") != marker["seq"]:
            raise RuntimeError(
                "effectless pulse publication recovery is ambiguous")
        effects = _canonical_pulse_effects(
            current["day"], current["events_pulse"], current["organs"])
        if legacy_effectless:
            expected_history = _expected_legacy_effectless_history(
                memo, current, effects["events_pulse"])
            recovered_redactions = _recoverable_pulse_redactions(
                memo, current.get("redactions"))
            if recovered_redactions is None:
                raise RuntimeError(
                    "effectless pulse publication recovery is ambiguous")
        else:
            expected_history = _expected_pulse_publication_history(
                memo, marker, effects["events_pulse"])
        if current.get("history") != expected_history:
            raise RuntimeError(
                "effectless pulse publication recovery is ambiguous")
    effects_published = False
    published_history = None
    # A page-prefix crash still has exact source work to replay. Its planned
    # counters are authoritative only after that batch reaches every page,
    # policy-state and cursor boundary; applying them here would make the isolated
    # replay count the missing suffix twice.
    if effects is not None and not source_pending:
        if expected_history is None:
            expected_history = _expected_pulse_publication_history(
                memo, marker, effects["events_pulse"])
        if current is None:
            current = read_json(STATUS_PATH, {})
        graph = read_json(GRAPH_PATH, {})
        retained_verdict = _recoverable_status_integrity(current)
        history = current.get("history")
        status_redactions = (
            _recoverable_pulse_redactions(memo, current.get("redactions"))
            if retained_verdict is not None else None)
        status_effects_bound = (
            retained_verdict is not None
            and current.get("publication_id") == marker["id"]
            and current.get("pulse_seq") == marker["seq"]
            and current.get("day") == effects["day"]
            and current.get("events_pulse") == effects["events_pulse"]
            and current.get("organs") == effects["organs"]
            and history == expected_history
            and status_redactions is not None
            and (marker.get("redactions") is None
                 or current.get("redactions") == marker["redactions"]))
        graph_generation = _recoverable_graph_snapshot(graph)
        effects_published = (
            status_effects_bound and graph_generation is not None
            and current.get("graph_publication_id")
                == graph_generation["publication_id"]
            and current.get("graph_nodes") == graph_generation["nodes"]
            and current.get("graph_edges") == graph_generation["edges"]
            and current.get("pages") == graph_generation["pages"])
        if effects_published:
            published_history = copy.deepcopy(expected_history)
            if recovered_redactions is None:
                recovered_redactions = status_redactions
    updated = dict(memo)
    updated.pop("pulse_publication", None)
    if recovered_redactions is not None:
        updated["redactions"] = copy.deepcopy(recovered_redactions)
    if effects is not None and not source_pending:
        if effects_published:
            updated.pop("pulse_status_effects_pending", None)
            updated["pulse_history"] = published_history
        else:
            history = copy.deepcopy(expected_history)
            marker_history = history[-1]
            updated["pulse_history"] = history
            updated["pulse_status_effects_pending"] = {
                "v": 1, "publication_id": marker["id"],
                "effects": copy.deepcopy(effects),
                "history": copy.deepcopy(marker_history),
            }
            _pending_pulse_status_effects(updated)
            # Recovery has already reconciled corpus, PGLite, and graph. This
            # handoff is status-only debt; it blocks readiness itself and the
            # consuming pulse will install a fresh named sync publication.
            updated.pop("sync_needed", None)
            updated.pop("ready", None)
    handoff_pending = _pending_pulse_status_effects(updated) is not None
    if "dream_publication" not in updated and not source_pending \
            and not handoff_pending:
        updated.pop("sync_needed", None)
        updated = _with_ready_receipt(updated, "pulse", marker["id"])
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return True


def _pulse_transaction(
        seq, opts=None, *, admitted_status=_STATUS_ADMISSION_REQUIRED):
    """Install the write-ahead publication barrier for one pulse cycle."""
    memo = load_memo()
    _require_status_memo_fields(memo)
    if not isinstance(seq, int) or isinstance(seq, bool) \
            or not 0 <= seq <= MAX_JSON_SAFE_INTEGER \
            or memo.get("pulse_seq") != seq:
        raise RuntimeError("pulse sequence reservation is invalid")
    if admitted_status is _STATUS_ADMISSION_REQUIRED:
        admitted_status = _require_status_sequence_not_ahead(seq)
    _pending_pulse_marker(memo)
    _pending_pulse_status_effects(memo)
    cursors = load_cursors()
    _recover_notify_baseline_attempt(memo, cursors)
    source_marker = _authorize_pending_source_replay(
        _pending_source_replay_marker(memo), cursors)
    ensure_dirs()
    if _ready_receipt(memo) is None \
            and memo.get("sync_needed", False) is False \
            and _pending_pulse_status_effects(memo) is None:
        _mark_sync_needed(memo)
    store = load_thoughts()
    # Prior transactions recover under generic publication debt. Installing
    # the new sequence marker before this phase would misattribute their
    # corpus repairs to the new pulse and allow two keeper rows for one seq.
    with corpus_mutation_barrier(lambda: _mark_sync_needed(memo)):
        recovery = _recover_before_pulse(
            memo, store, cursors=cursors, source_marker=source_marker)
    publication_effects = {}

    def mark_named_pulse_before_mutation():
        marker = _pending_pulse_marker(memo)
        if marker is not None and marker.get("effects") is not None:
            return _mark_pulse_publication(
                memo, seq, marker["effects"],
                _projected_pulse_redactions(memo))
        effects = publication_effects.get("effects")
        if effects is None:
            raise RuntimeError(
                "pulse effects unavailable before corpus mutation")
        return _mark_pulse_publication(
            memo, seq, effects, _projected_pulse_redactions(memo))

    with corpus_mutation_barrier(mark_named_pulse_before_mutation):
        return _pulse_transaction_guarded(
            seq, opts, memo, store, recovery, cursors=cursors,
            source_marker=source_marker,
            publication_effects=publication_effects,
            admitted_status=admitted_status)


def _recover_before_pulse(
        memo, store, *, cursors=None, source_marker=None):
    """Finish older journals before the next named pulse may begin."""
    cursors = load_cursors() if cursors is None else cursors
    _recover_notify_baseline_attempt(memo, cursors)
    current_source_marker = _pending_source_replay_marker(memo)
    if source_marker is not None and current_source_marker != source_marker:
        raise SourceReplayQuarantine(
            "source replay quarantine: marker changed before recovery")
    source_marker = _authorize_pending_source_replay(
        current_source_marker, cursors)
    _pending_pulse_status_effects(memo)
    _recover_pending_thought_projection(memo, store)
    _ledger_recovered, ledger_recovery_errors = recover_ledger_transitions()
    if ledger_recovery_errors:
        raise RuntimeError(
            f"ledger recovery refused: {ledger_recovery_errors}")
    if _settle_pending_dream_unit(store) is not None:
        export_thoughts(store)
    _complete_pending_dream_cycle(memo, store)
    _history_recovered, history_recovery_errors = \
        siatakes.recover_natural_history_transactions(
            before_publish=lambda: _mark_external_corpus_mutation(memo))
    if history_recovery_errors:
        raise RuntimeError(
            f"natural-history recovery refused: {history_recovery_errors}")
    _grade_recovered, grade_recovery_errors = \
        siatakes.recover_grade_transactions(
            before_publish=lambda: _mark_external_corpus_mutation(memo))
    if grade_recovery_errors:
        raise RuntimeError(
            f"grade recovery refused: {grade_recovery_errors}")
    _reconcile_legacy_memory_authority(memo)
    mind_replay = siamind.load_mind()
    if _pending_source_replay_marker(memo) is None \
            and (mind_replay.get("event_applied")
                 or mind_replay.get("event_batch_applied") is not None):
        # Source debt clears only after its evidence cursors publish. A crash
        # in the following guard cleanup is therefore safe to finish here.
        siamind.clear_event_replay(mind_replay)
        siamind.save_mind(mind_replay)
    mind_replay = siamind.load_mind()
    if _pending_source_replay_marker(memo) is None \
            and not mind_replay.get("event_applied") \
            and mind_replay.get("event_batch_applied") is None:
        if _pending_consolidation_marker(memo) is None \
                and _consolidation_scan_debt():
            # Adopt marker-free debt from an older runtime into the same named,
            # recoverable transaction shape used by current DREAM runs.
            _mark_consolidation_pending(memo)
        _recover_pending_consolidation(memo)
    if _pending_pulse_marker(memo) is not None:
        _settle_pending_publication(
            memo, "publish interrupted pulse before recovery", clear=False)
        _recover_pending_pulse_publication(memo)
    if _pending_dream_marker(memo) is not None:
        _settle_pending_publication(
            memo, "publish interrupted dream before recovery", clear=False)
        _recover_pending_dream_publication(memo)
    if _pending_pulse_status_effects(memo) is None:
        _settle_pending_publication(
            memo, "publish pending corpus migration before pulse")
    return _ledger_recovered, []


def _reconcile_legacy_memory_authority(memo):
    """Advance upgrade provenance once, or converge it at first light."""
    attempts = 0
    while True:
        _take_migrated, take_migration_errors = \
            siatakes.migrate_legacy_take_pages(
                before_publish=lambda: _mark_external_corpus_mutation(memo))
        if take_migration_errors:
            raise RuntimeError(
                f"legacy take migration refused: {take_migration_errors}")
        _intent_imported, intent_history_errors = \
            siatakes.advance_intent_history(
                before_publish=lambda: _mark_external_corpus_mutation(memo),
                start_audit_cycle=False)
        if intent_history_errors:
            raise RuntimeError(
                f"legacy intent projection refused: {intent_history_errors}")
        if os.environ.get("SIA_BACKFILL") != "1" \
                or not (siatakes.take_migration_required()
                        or siatakes.intent_history_required()):
            return
        attempts += 1
        if attempts >= MAX_EVENT_LOOKUP_PAGES:
            raise RuntimeError(
                "legacy memory authority backfill exceeded its generation "
                "ceiling")


def _pulse_transaction_guarded(
        seq, opts, memo, store=None, recovery=None, *, cursors=None,
        source_marker=None, publication_effects=None,
        admitted_status=_STATUS_ADMISSION_REQUIRED):
    """Run one pulse cycle and return the status dict it exported."""
    cursors = load_cursors() if cursors is None else cursors
    _recover_notify_baseline_attempt(memo, cursors)
    current_source_marker = _pending_source_replay_marker(memo)
    if source_marker is not None and current_source_marker != source_marker:
        raise SourceReplayQuarantine(
            "source replay quarantine: marker changed before replay")
    source_marker = _authorize_pending_source_replay(
        current_source_marker, cursors)
    status_effects = _pending_pulse_status_effects(memo)
    opts = opts or {}
    now_ts = float(opts.get("now", time.time()))
    store = load_thoughts() if store is None else store
    sync_needed = memo.get("sync_needed", False)
    if not isinstance(sync_needed, bool):
        raise RuntimeError("brainstem memo sync-needed state is invalid")
    if admitted_status is _STATUS_ADMISSION_REQUIRED:
        admitted_status = _require_status_sequence_not_ahead(seq)
    stnow = _require_status_admission_unchanged(admitted_status)
    if _recoverable_status_integrity(stnow) is None \
            and _recoverable_legacy_effectless_status_integrity(stnow) is None:
        stnow = {}
    day = today()
    if status_effects is not None:
        organs_st = copy.deepcopy(status_effects["effects"]["organs"])
        status_day = status_effects["effects"]["day"]
    else:
        organs_st = stnow.get("organs", {})
        status_day = stnow.get("day")
    if status_day != day:
        # Keep the source roster stable across midnight; zero the counters.
        organs_st = {k: {**v, "today": 0} for k, v in organs_st.items()}

    # Each sense runs on an isolated cursor copy, merged back only on
    # success — a raising sense never persists cursor advances for events
    # it dropped. Cursors are made durable only AFTER the corpus writes.
    PENDING_CURSOR_RENAMES.clear()
    cognitive_now_ts, cognitive_day = now_ts, day
    if source_marker is not None:
        cognitive_now_ts, cognitive_day = _source_replay_clock(source_marker)
    source_batch_identity = (source_marker["id"]
                             if source_marker is not None else None)
    replay_events = (_source_replay_events(source_marker)
                     if source_marker is not None else [])
    pending_replay_ids = (set(source_marker["cognitive_ids"])
                          if source_marker is not None else set())
    events, errors = list(replay_events), {}
    successful_sources = set()
    event_sources = (set(source_marker["sources"])
                     if source_marker is not None else set())
    ledger_recovered, ledger_recovery_errors = recovery or ([], [])
    sync_needed = False
    replay_record_bytes = _event_replay_batch_bytes(events)
    # A durable exact batch settles in isolation. Mixing newly arrived source
    # rows into recovery can let one later over-bound record head-of-line block
    # an older valid batch forever; normal sensing resumes next pulse cycle.
    sense_runs = []
    if source_marker is None:
        for sense in SENSES:
            if sense is not sense_custom:
                sense_runs.append((sense, None))
                continue
            configured = CONFIG.get("custom_senses", [])
            if isinstance(configured, list) \
                    and len(configured) <= MAX_LEDGER_PENDING_RECORDS:
                if configured:
                    sense_runs.extend(
                        (sense, index) for index in range(len(configured)))
                elif CONFIG_ERRORS:
                    # A parser/shape error may safely disable every custom
                    # entry, but it must still reach SOURCE HEALTH.
                    sense_runs.append((sense, None))
            else:
                # Preserve one visible configuration error for a malformed or
                # over-bound aggregate without attempting unbounded expansion.
                sense_runs.append((sense, None))
    custom_seen_names = set()
    for sense, custom_index in sense_runs:
        trial = copy.deepcopy(cursors)
        entry_refusals_present = SOURCE_ENTRY_REFUSALS_KEY in trial
        entry_refusals_before = copy.deepcopy(
            trial.get(SOURCE_ENTRY_REFUSALS_KEY))
        rename_boundary = len(PENDING_CURSOR_RENAMES)
        sense_key = (sense.__name__ if custom_index is None else
                     f"{sense.__name__}:{custom_index}")
        try:
            if sense is sense_custom:
                kwargs = {"include_sources": True,
                          "seen_names": custom_seen_names}
                if custom_index is not None:
                    kwargs["entry_index"] = custom_index
                result = sense(trial, **kwargs)
            elif sense is sense_notify:
                result = sense(
                    trial, before_initial_baseline=lambda:
                    _mark_notify_baseline_attempt(memo))
            else:
                result = sense(trial)
        except Exception as e:
            _discard_pending_cursor_renames(rename_boundary)
            errors[sense_key] = str(e)[:160]
            continue
        try:
            record_refusals = _take_source_record_refusals(trial)
            if record_refusals:
                _settle_source_record_refusals(sense_key, record_refusals)
                reasons = sorted({row["reason"]
                                  for row in record_refusals})
                errors[f"source_record_refusal:{sense_key}"] = (
                    "signed " + ",".join(reasons)
                    + " refusal; source cursor may advance")
        except Exception as exc:
            _discard_pending_cursor_renames(rename_boundary)
            errors[f"source_record_refusal:{sense_key}"] = str(exc)[:160]
            continue
        try:
            entry_refusals = _take_owned_source_entry_refusals(
                sense, trial, entry_refusals_present,
                entry_refusals_before)
            if entry_refusals:
                _settle_source_entry_refusals(
                    "sense_worldline", entry_refusals)
                errors["source_entry_refusal:sense_worldline"] = (
                    "signed source-entry refusal; source cursor may advance")
        except Exception as exc:
            _discard_pending_cursor_renames(rename_boundary)
            errors[f"source_entry_refusal:{sense_key}"] = str(exc)[:160]
            continue
        if sense is sense_custom:
            evs, sense_errors, evaluated_sources = result
            if sense_errors:
                errors[sense_key] = sense_errors
            candidate_sources = set(evaluated_sources)
            candidate_event_sources = set()
            for event in evs:
                match = re.match(r"^custom:([^:]+):", event.occurrence)
                if match is None:
                    raise RuntimeError(
                        "custom event has no source-native identity")
                token = f"sense_custom:{match.group(1)}"
                candidate_event_sources.add(token)
        else:
            evs = result
            candidate_sources = {sense.__name__}
            candidate_event_sources = {sense.__name__} if evs else set()
        try:
            candidate_bytes = _event_replay_batch_bytes(evs)
        except Exception as exc:
            _discard_pending_cursor_renames(rename_boundary)
            errors[sense_key] = str(exc)[:160]
            continue
        candidate_too_large = (
            len(evs) > MAX_SOURCE_REPLAY_EVENTS
            or candidate_bytes > MAX_SOURCE_REPLAY_RECORD_BYTES)
        combined_too_large = (
            len(events) + len(evs) > MAX_SOURCE_REPLAY_EVENTS
            or replay_record_bytes + candidate_bytes
            > MAX_SOURCE_REPLAY_RECORD_BYTES)
        refusal_source = sorted(
            candidate_event_sources or candidate_sources or {sense_key})[0]
        if candidate_too_large:
            try:
                _settle_source_refusals(
                    refusal_source, evs, "record-capacity")
            except Exception as exc:
                _discard_pending_cursor_renames(rename_boundary)
                errors[f"source_refusal:{sense_key}"] = str(exc)[:160]
                continue
            errors[f"source_refusal:{sense_key}"] = (
                "signed record-capacity refusal; source cursor may advance")
            cursors.clear()
            cursors.update(trial)
            continue
        if combined_too_large:
            _discard_pending_cursor_renames(rename_boundary)
            errors[f"source_budget:{sense_key}"] = (
                f"{sense_key} deferred to the next bounded pulse")
            continue
        tentative_events = events + list(evs)
        tentative_sources = event_sources | candidate_event_sources
        if evs:
            try:
                _preflight_source_admission_image(
                    memo, seq, tentative_sources, tentative_events,
                    day, organs_st)
            except Exception as exc:
                refusal = _source_refusal_code(exc)
                intrinsic = False
                if refusal is not None:
                    try:
                        _preflight_source_admission_image(
                            memo, seq, candidate_event_sources, evs,
                            day, organs_st)
                    except Exception as isolated_exc:
                        intrinsic = _source_refusal_code(isolated_exc) \
                            == refusal
                if intrinsic:
                    try:
                        _settle_source_refusals(
                            refusal_source, evs, refusal)
                    except Exception as refusal_exc:
                        _discard_pending_cursor_renames(rename_boundary)
                        errors[f"source_refusal:{sense_key}"] = \
                            str(refusal_exc)[:160]
                        continue
                    errors[f"source_refusal:{sense_key}"] = (
                        f"signed {refusal} refusal; source cursor may advance")
                    cursors.clear()
                    cursors.update(trial)
                    continue
                _discard_pending_cursor_renames(rename_boundary)
                errors[f"source_budget:{sense_key}"] = str(exc)[:160]
                continue
        successful_sources.update(candidate_sources)
        event_sources.update(candidate_event_sources)
        events.extend(evs)
        replay_record_bytes += candidate_bytes
        cursors.clear()
        cursors.update(trial)

    synced, sync_note = True, ""
    made_pages = []
    admitted_events = []           # events confirmed present in a day page
    appended_event_ids = set()
    prepared_event_mind = None
    prepared_event_transition = None
    write_ok = True
    try:
        if events:
            events = _dedupe_event_batch(events)
            _preflight_event_lookup(events)
            by_day = {}
            for ev in events:
                by_day.setdefault((ev.organ, ev.ts.strftime("%Y-%m-%d")),
                                  []).append(ev)
            # Fully render every target in memory before creating durable
            # replay debt. Intrinsically oversized events and exhausted days
            # remain a reported source refusal, not a permanent recovery loop.
            planned_organs = copy.deepcopy(organs_st)
            planned_appended = {}
            planned_admitted_events = []
            planned_paths_by_organ = collections.defaultdict(set)
            for (organ, d), evs in by_day.items():
                day_pages, appended, planned_admitted = update_day_page(
                    organ, d, evs, dry_run=True)
                planned_admitted_events.extend(planned_admitted)
                planned_paths_by_organ[organ].update(
                    os.path.abspath(corpus_path(slug)) for slug in day_pages)
                planned_appended[(organ, d)] = [
                    event_memory_identity(event) for event in appended]
                if source_marker is None:
                    planned = planned_organs.setdefault(
                        organ, {"today": 0, "last_ts": ""})
                    if d == day:
                        planned["today"] += len(appended)
                    if appended:
                        planned["last_ts"] = max(
                            planned["last_ts"],
                            iso(max(event.ts for event in appended)))
            _preflight_event_path_plan(planned_paths_by_organ)
            source_effects = None
            planned_events_pulse = len(events)
            if source_marker is not None:
                # Replaying after midnight keeps the original last-seen
                # timestamps but starts the new status day's counters at zero.
                source_effects = source_marker["effects"]
                planned_organs = copy.deepcopy(source_effects["organs"])
                if source_effects["day"] != day:
                    for state in planned_organs.values():
                        state["today"] = 0
                planned_events_pulse = source_effects["events_pulse"]
            planned_appended_ids = {
                event_id for identities in planned_appended.values()
                for event_id in identities}
            planned_cognitive_events = _select_cognitive_admissions(
                planned_admitted_events, planned_appended_ids,
                pending_replay_ids)
            cognitive_ids = [
                event_memory_identity(event)
                for event, _slug in planned_cognitive_events]
            prepared_source = _source_replay_marker_value(
                memo, seq, event_sources, events,
                source_effects or _canonical_pulse_effects(
                    day, planned_events_pulse, planned_organs),
                cognitive_ids)
            if prepared_source is None:
                raise RuntimeError("event pulse has no source replay identity")
            source_batch_identity = prepared_source["id"]
            cognitive_now_ts, cognitive_day = _source_replay_clock(
                prepared_source)

            # Recovery unpins have their own journaled lane and are allowed to
            # reduce protected state even while a source batch is pending.
            prepared_event_mind = siamind.load_mind()
            _unpinned, unpin_refused = _drain_recovery_unpins(
                prepared_event_mind, now_ts)
            if unpin_refused:
                errors["recovery_unpin"] = (
                    f"{unpin_refused} recovery unpin records refused")
            _touches, touch_refused = _drain_ordinary_touches(
                prepared_event_mind, now_ts)
            if touch_refused:
                errors["touch_queue_capacity"] = (
                    f"{touch_refused} touch/pin records refused")
            graph_before_source = _require_recoverable_graph_snapshot(
                read_json(GRAPH_PATH, {}))
            siamind.sync_graph_state(
                prepared_event_mind, graph_before_source, now=now_ts)
            siamind.baseline_graph_familiarity(
                prepared_event_mind, graph_before_source, now_ts)
            prepared_event_transition = _event_cognitive_transition(
                prepared_event_mind, planned_cognitive_events,
                cognitive_now_ts, cognitive_day,
                source_batch_identity)
            # This is exact admission of the complete retained transition,
            # including mutations to user-pinned nodes and the batch receipt.
            # The same candidate object is the one persisted after page writes.
            siamind.compact_mind_for_persistence(prepared_event_mind)
            prepared_event_transition["workspace"] = list(
                prepared_event_mind.get("workspace", []))
            prepared_event_transition["memory_state"] = \
                siamind.memory_summary_view(
                    prepared_event_mind, now=now_ts)

            # One atomic memo image binds the admitted policy transition,
            # exact source bytes, and projected status before corpus mutation.
            _pulse_marker, source_marker = _stage_pulse_source_publication(
                memo, seq, event_sources, events, day,
                planned_events_pulse, planned_organs,
                source_effects=source_effects,
                prepared_source=prepared_source,
                cognitive_ids=cognitive_ids)
            # Persist the exact policy candidate and its bounded generated-entry /
            # finding receipt before any source page can alter GRAPH_PATH.
            # A crash before this save sees the old graph and recomputes; a
            # crash after it reuses the receipt, so publication timing cannot
            # change first-sighting novelty or derived generated entries.
            siamind.save_mind(prepared_event_mind)
            ensure_organs()
            ensure_event_entities(events)
            for (organ, d), evs in by_day.items():
                day_pages, appended, admitted = update_day_page(
                    organ, d, evs)
                actual_appended = [
                    event_memory_identity(event) for event in appended]
                if actual_appended != planned_appended[(organ, d)]:
                    raise RuntimeError(
                        "event page changed between dry-run and publication")
                made_pages.extend(day_pages)
                admitted_events.extend(admitted)
                appended_event_ids.update(
                    event_memory_identity(event) for event in appended)
            organs_st = planned_organs
            # Freshly appended events are applied now. Events that were
            # already present are applied only when they came from the exact
            # crash-replay batch captured before this pulse began.
            admitted_events = _select_cognitive_admissions(
                admitted_events, appended_event_ids, pending_replay_ids)
            if [event_memory_identity(event)
                    for event, _slug in admitted_events] != [
                        event_memory_identity(event)
                        for event, _slug in planned_cognitive_events]:
                raise RuntimeError(
                    "event policy admission changed after dry-run")
    except Exception as e:
        write_ok = False
        # Retrieval-policy state is all-or-nothing for the exact source batch. A
        # page-prefix failure replays the complete marker on the next pulse.
        admitted_events = []
        prepared_event_mind = None
        prepared_event_transition = None
        source_marker = _pending_source_replay_marker(memo)
        source_batch_identity = (source_marker["id"]
                                 if source_marker is not None else None)
        errors["corpus_write"] = str(e)[:160]
    if not write_ok:
        _discard_pending_cursor_renames()

    marker_for_effects = _pending_pulse_marker(memo)
    if marker_for_effects is not None:
        bound_effects = marker_for_effects.get("effects")
        if bound_effects is None:
            raise RuntimeError("pulse publication has no bound effects")
    else:
        bound_effects = _canonical_pulse_effects(
            day, len(events), organs_st)
    if publication_effects is not None:
        publication_effects["effects"] = copy.deepcopy(bound_effects)

    # Event pages must be visible through PGLite and the graph before this
    # same pulse asks those surfaces for salience, anomalies, or associative
    # state. Keep the durable marker set: the final publication/signature
    # phase clears it only after all later generated-entry pages are reconciled too.
    _settle_pending_publication(
        memo, "publish pulse events before memory queries", clear=False)

    # generated entries may add corpus pages too — generate BEFORE commit+sync
    every = int(opts.get("integrity_every", 10))
    prior_chains = memo.get("chains")
    if not _status_chains_shape(prior_chains):
        # ``think`` compares the fresh sweep with the memo roster.  Quarantine
        # a malformed retained value before that comparison rather than
        # letting a list/scalar reach its mapping operations.  A valid roster
        # whose observation timestamp alone is bad remains useful as the
        # transition baseline, even though it cannot be reused as a sweep.
        memo["chains"] = {}
        prior_chains = {}
    cached_sweep = _cached_chain_sweep(memo)
    chains = copy.deepcopy(prior_chains) \
        if cached_sweep is None else cached_sweep[0]
    chains_checked_at = None if cached_sweep is None else cached_sweep[1]
    salience = anomalies = None
    if events or seq % every == 0 or cached_sweep is None:
        chains = verify_chains()
        if not _status_chains_shape(chains):
            raise RuntimeError("integrity sweep returned an invalid roster")
        chains_checked_at = iso()
        memo["chains_checked_at"] = chains_checked_at
        if seq % every == 0 or events:
            salience = gbrain_call("get_recent_salience", {"days": 7, "limit": 5})
            anomalies = gbrain_call("find_anomalies", {"sigma": 3.0})
            if isinstance(anomalies, dict):
                anomalies = anomalies.get("anomalies", anomalies.get("results", []))
    admitted_observations = [event for event, _slug in admitted_events]
    new_thoughts = think(store, memo, admitted_observations, chains,
                         salience if isinstance(salience, list) else [],
                         anomalies if isinstance(anomalies, list) else [],
                         event_day=cognitive_day)

    # Multi-writer agent notes enter as immutable per-request files.  Writing
    # the page is intentionally separate from acknowledging the request: the
    # latter happens only after the corpus commit and PGLite sync below.
    agent_paths, agent_pages, agent_thoughts, agent_queue_errors = \
        materialize_agent_notes(store, memo)
    new_thoughts.extend(agent_thoughts)
    made_pages.extend(agent_pages)
    agent_activity = bool(agent_paths)
    if agent_queue_errors:
        errors["agent_queue"] = agent_queue_errors

    # thoughts queued by out-of-band tools (e.g. `sia ponder` → the judge);
    # the inbox keeps thoughts.json single-writer (this daemon)
    inbox, inbox_claim = [], None
    thought_batch_ok = True
    try:
        inbox, inbox_claim = drain_thought_inbox(defer_ack=True)
    except Exception as exc:
        thought_batch_ok = False
        errors["thought_inbox"] = str(exc)[:160]
    if inbox:
        for t in inbox:
            try:
                queue_id = t.get("_queue_id")
                if not isinstance(queue_id, str) \
                        or not re.fullmatch(r"[0-9a-f]{32}", queue_id):
                    queue_id = hashlib.sha256(json.dumps(
                        t, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False).encode()).hexdigest()[:32]
                new_thoughts.append(add_thought(
                    store, t.get("kind", "note"), t.get("text", ""),
                    t.get("links", []), t.get("urgent", False),
                    queue_id=queue_id, thought_ts=t.get("_queued_at"),
                    origin=t.get("origin", "derived")))
            except Exception as exc:
                thought_batch_ok = False
                errors["thought_inbox_item"] = str(exc)[:160]
    _settle_pending_publication(
        memo, "publish pulse generated entries before graph reads",
        clear=False)
    # ---- deterministic retrieval policy (siamind): use touches, co-return
    # reinforcement, novelty and intake baselines, bounded attention window.
    # ``mind.json`` is a compatibility filename owned by this daemon alone.
    mind = (prepared_event_mind
            if write_ok and prepared_event_mind is not None
            else siamind.load_mind())
    ws = mind.get("workspace", [])
    memory_state = {}
    mind_ready = False
    try:
        touch_usage = siamind.touch_queue_usage()
        _record_touch_queue_health(errors, touch_usage)
        if prepared_event_mind is None or not write_ok:
            _unpinned, unpin_refused = _drain_recovery_unpins(mind, now_ts)
            if unpin_refused:
                errors["recovery_unpin"] = (
                    f"{unpin_refused} recovery unpin records refused")
            _touches, touch_refused = _drain_ordinary_touches(mind, now_ts)
            if touch_refused:
                errors["touch_queue_capacity"] = (
                    f"{touch_refused} touch/pin records refused")
            g0 = _require_recoverable_graph_snapshot(
                read_json(GRAPH_PATH, {}))
            siamind.sync_graph_state(mind, g0, now=now_ts)
            siamind.baseline_graph_familiarity(mind, g0, now_ts)
        transition = (prepared_event_transition
                      if write_ok and prepared_event_transition is not None
                      else None)
        if transition is None:
            findings = ([] if source_batch_identity is not None else
                        siamind.surprisal_update(mind, {}, ts=now_ts))
            coincidences = coincidence_findings(mind, findings, now=now_ts)
            siamind.rebuild_workspace(mind, {}, now=now_ts)
            # Materialize review and edge-decay state before the final
            # capacity decision.  The status projection after compaction is
            # deliberately read-only, so save_mind sees the exact generation
            # whose counts are published below.
            siamind.memory_summary(mind, now=now_ts)
            siamind.compact_mind_for_persistence(mind)
            ws = list(mind.get("workspace", []))
            memory_state = siamind.memory_summary_view(mind, now=now_ts)
            novelty_thoughts = []
        else:
            findings = transition["findings"]
            coincidences = transition["coincidences"]
            ws = transition["workspace"]
            memory_state = transition["memory_state"]
            novelty_thoughts = transition["novelty_thoughts"]
        for novelty_kind, novelty_text, novelty_links, queue_id in \
                novelty_thoughts:
            new_thoughts.append(add_thought(
                store, novelty_kind, novelty_text, novelty_links,
                queue_id=queue_id))
        for s_organ, s_kind, s_text in findings:
            surprise_links = [f"organs/{s_organ}"]
            new_thoughts.append(add_thought(
                store, "surprise", s_text, surprise_links,
                queue_id=thought_queue_identity(
                    "pulse.mind.surprise", "surprise", s_text,
                    surprise_links, day=cognitive_day,
                    extra={"organ": s_organ, "kind": s_kind})))
        for c_text, c_links in coincidences:
            new_thoughts.append(add_thought(
                store, "coincidence", c_text, c_links,
                queue_id=thought_queue_identity(
                    "pulse.mind.coincidence", "coincidence", c_text,
                    c_links, day=cognitive_day)))
        siamind.save_mind(mind)
        mind_ready = True
    except Exception as e:
        errors["siamind"] = str(e)[:160]
        _discard_pending_cursor_renames()

    # evidence-derived take proposals: successful fabric heals become
    # PROPOSED hold-predictions (deterministic confidence from the
    # action's own history; queue only — `sia take --accept` commits)
    try:
        if admitted_observations:
            props = siatakes.auto_propose_heals(
                admitted_observations, STATE)
            for p in props:
                proposal_text = (
                    f"Proposed from evidence ({p['proposed']}): "
                    f"“{p['claim']}” at {p['confidence']:.2f} — review "
                    f"with `sia takes`, commit with `sia take --accept`.")
                proposal_links = ["organs/sekhmet"]
                new_thoughts.append(add_thought(
                    store, "take", proposal_text, proposal_links,
                    queue_id=thought_queue_identity(
                        "pulse.auto-propose", "take", proposal_text,
                        proposal_links, day=day,
                        extra={key: p.get(key) for key in
                               ("proposed", "claim", "confidence")})))
    except Exception as e:
        errors["auto-propose"] = str(e)[:160]

    # dated intents: surface open commitments as deadlines approach
    # (once per stage: "soon" inside 48 h, then "overdue" once per day)
    open_ints = []
    try:
        nag = memo.setdefault("intent_nag", {})
        open_ints = siatakes.open_intents()
        for it in open_ints:
            st_i = nag.setdefault(it["id"], {})
            if 0 <= it["days_left"] <= 2 and not st_i.get("soon"):
                st_i["soon"] = day
                when = ("today" if it["days_left"] == 0
                        else f"in {it['days_left']}d")
                intent_text = (
                    f"Intent due {when}: “{it['text']}” — close with "
                    f"`sia intend --done {it['id'][:6]}`.")
                new_thoughts.append(add_thought(
                    store, "intent", intent_text, [it["slug"]],
                    queue_id=thought_queue_identity(
                        "pulse.intent", "intent", intent_text,
                        [it["slug"]], day=day,
                        extra={"id": it["id"], "stage": "soon"})))
            elif it["days_left"] < 0 and st_i.get("overdue") != day:
                st_i["overdue"] = day
                intent_text = (
                    f"Intent OVERDUE by {-it['days_left']}d: "
                    f"“{it['text']}”.")
                new_thoughts.append(add_thought(
                    store, "intent", intent_text, [it["slug"]], urgent=True,
                    queue_id=thought_queue_identity(
                        "pulse.intent", "intent", intent_text,
                        [it["slug"]], urgent=True, day=day,
                        extra={"id": it["id"], "stage": "overdue"})))
        for iid in list(nag):
            if iid not in {i2["id"] for i2 in open_ints}:
                del nag[iid]
    except Exception as e:
        errors["intents"] = str(e)[:160]

    # prediction grading: remind once a day when predictions come due
    takes_sum = {}
    try:
        takes_sum = siatakes.summary()
        if takes_sum.get("due") and memo.get("takes_reminder_day") != day:
            memo["takes_reminder_day"] = day
            reminder_text = (
                f"{takes_sum['due']} predictions are due for "
                f"grading — the nightly grade job evaluates up to 3, or run "
                f"`sia grade` now.")
            new_thoughts.append(add_thought(
                store, "take", reminder_text, ["sia/cortex"],
                queue_id=thought_queue_identity(
                    "pulse.take-reminder", "take", reminder_text,
                    ["sia/cortex"], day=day,
                    extra=takes_sum.get("due"))))
    except Exception as e:
        errors["siatakes"] = str(e)[:160]

    # A generated-entry page is the redo journal for its derived review signal.
    # Settle every page into daemon-owned compatibility policy state before evidence cursors or
    # the named publication marker can become irreversible. This also repairs
    # a bounded queue refusal in the same successful pulse, not merely after a
    # later interrupted-publication recovery.
    thought_reinforcement_ready = False
    if mind_ready:
        try:
            _recovered, reinforced = _settle_thought_page_signals(
                store, mind=mind)
            if reinforced:
                ws = list(mind.get("workspace", []))
                memory_state = siamind.memory_summary_view(mind, now=now_ts)
            thought_reinforcement_ready = True
        except Exception as exc:
            mind_ready = False
            errors["thought_reinforcement"] = str(exc)[:160]
            _discard_pending_cursor_renames()

    cursor_ready = False
    source_replay_resolved = _pending_source_replay_marker(memo) is None
    if write_ok and mind_ready:
        try:
            # Persist every in-memory generated-entry gate before making evidence
            # cursors irreversible. The named/source markers remain present
            # in this checkpoint, so a later failure still has a redo path.
            _write_memo(memo)
            cursor_commit_errors, cursor_save_error = \
                _commit_sense_cursors(cursors)
            if cursor_commit_errors:
                errors["journal_cursor_commit"] = cursor_commit_errors
            if cursor_save_error:
                errors["evidence_cursor_commit"] = cursor_save_error
            cursor_ready = not cursor_commit_errors and not cursor_save_error
            if cursor_ready:
                if _pending_notify_baseline_attempt(memo) is not None:
                    if not _notify_cursor_checkpoint_safe(cursors):
                        raise RuntimeError(
                            "notification baseline cursor checkpoint is "
                            "ambiguous")
                    # Clear only after the cursor image itself is durable. A
                    # crash before this write recovers it conservatively; a
                    # crash after it already has the exact safe checkpoint.
                    _clear_notify_baseline_attempt(memo)
                # Cursor publication and exact replay have both completed.
                # Clear the batch first; only then may its policy replay
                # guards be discarded. A failed clear leaves both redo paths.
                _clear_source_replay_pending(memo)
                source_replay_resolved = \
                    _pending_source_replay_marker(memo) is None
                if source_replay_resolved:
                    siamind.clear_event_replay(mind)
                    siamind.save_mind(mind)
        except Exception as exc:
            cursor_ready = False
            source_replay_resolved = False
            errors["cursor_checkpoint"] = str(exc)[:160]
            _discard_pending_cursor_renames()
    else:
        _discard_pending_cursor_renames()

    nodes = edges = pages_total = None
    agent_acknowledged = 0
    ledger_transition = "not-required"
    commit = "clean"
    completed_pulse = None
    organ_activity = ensure_organs()
    dirty = corpus_dirty()
    if dirty is None:
        errors["corpus_status"] = "git status failed; mutation not committed"
    publication_activity = bool(
        events or new_thoughts or agent_activity or organ_activity or dirty
        or status_effects is not None or REDACTIONS)
    sync_needed = memo.get("sync_needed", False)
    # Keep the post-publication acknowledgment predicate total even when a
    # valid but empty inbox claim reaches an otherwise idle pulse.
    graph_publication_failed = False
    if publication_activity:
        # Bind every publication to a durable pulse identity. If the daemon
        # dies after any page/commit but before its signed result, recovery
        # publishes the projections and signs that exact interrupted pulse
        # before either marker may clear.
        _mark_pulse_publication(
            memo, seq, bound_effects, _projected_pulse_redactions(memo))
        # Every named pulse carries the exact status effects it will publish,
        # including event-free agent/generated-entry/source-only work. Recovery may
        # never clear an effectless marker into a stale status/graph pair.
        sync_needed = True
    if sync_needed:
        commit = corpus_commit(f"pulse {seq}: {len(events)} events, "
                               f"{len(new_thoughts)} thoughts")
        if commit == "error":
            synced, sync_note = False, "corpus git commit failed"
        else:
            synced, sync_note = brain_sync()
        try:
            nodes, edges, pages_total = _export_graph_publication()
        except Exception as exc:
            graph_publication_failed = True
            errors["graph_export"] = str(exc)[:160]
        published = synced and not graph_publication_failed
        thought_pages = [row.get("slug") for row in new_thoughts
                         if isinstance(row, dict)
                         and isinstance(row.get("slug"), str)]
        published_pages = sorted(set(made_pages + thought_pages))
        page_manifest = json.dumps(
            published_pages,
            ensure_ascii=False, separators=(",", ":"))
        ledger_content = json.dumps({
            "page_count": len(published_pages),
            "pages_sha256": hashlib.sha256(
                page_manifest.encode("utf-8")).hexdigest(),
            "transaction": {
                key: value for key, value in
                _pending_pulse_marker(memo).items() if key != "ledger"},
        }, sort_keys=True, separators=(",", ":"))
        try:
            publication_result = (
                "write-fail" if not write_ok
                else "thought-signal-fail"
                if not thought_reinforcement_ready
                else "cursor-fail" if not cursor_ready
                else "source-pending" if not source_replay_resolved
                else "graph-fail" if graph_publication_failed
                else "ok" if synced else "sync-fail")
            _bind_pending_pulse_ledger(
                memo,
                f"pulse={seq} {len(events)}ev/{len(new_thoughts)}th",
                publication_result, ledger_content)
            _settle_pending_pulse_ledger(memo)
            ledger_transition = "signed"
        except Exception as exc:
            ledger_transition = "pending"
            errors["ledger_transition"] = str(exc)[:160]
        if published and ledger_transition == "signed" \
                and thought_reinforcement_ready:
            # Retain the durable marker/debt until every late diagnostic has
            # been redacted and rebound to it.  The marker and debt are
            # removed only in the in-memory final memo immediately before
            # status export; the last memo write remains the readiness point.
            completed_pulse = _pending_pulse_marker(memo)
            sync_needed = False
        if agent_activity and published and ledger_transition == "signed" \
                and thought_reinforcement_ready:
            agent_acknowledged, ack_errors = acknowledge_agent_notes(
                agent_paths, commit, synced,
                after_ack=lambda identity:
                    _forget_agent_note_redaction_receipt(memo, identity))
            if ack_errors:
                errors["agent_ack"] = ack_errors

    hist = memo.get("pulse_history", [])
    history_marker = completed_pulse or _pending_pulse_marker(memo)
    history_row = [
        history_marker["started_at"] if history_marker is not None else iso(),
        len(events),
    ]
    hist.append(history_row)
    memo["pulse_history"] = hist[-MAX_PULSE_HISTORY_ROWS:]
    pending_marker = _pending_pulse_marker(memo)
    if pending_marker is not None:
        memo["pulse_publication"] = dict(
            pending_marker, history=copy.deepcopy(history_row))
        _pending_pulse_marker(memo)
    export_thoughts(store)
    inbox_publication_ok = (not inbox or (
        commit != "error" and synced and not graph_publication_failed
        and ledger_transition == "signed"))
    if inbox_claim and thought_batch_ok and inbox_publication_ok:
        try:
            acknowledge_thought_inbox(inbox_claim)
            inbox_claim = None
        except Exception as exc:
            errors["thought_inbox_ack"] = str(exc)[:160]

    intents_open = open_ints
    try:
        bench_trend, bench_trend_boundary = _bench_trend_snapshot(
            include_metadata=True)
    except Exception as exc:
        bench_trend = []
        bench_trend_boundary = {"legacy_truncated": False}
        errors["bench_trend"] = str(exc)[:160]
    if graph_publication_failed:
        errors["graph_snapshot"] = (
            "graph publication failed; current graph claims withdrawn")
        graph_generation = {
            "publication_id": "", "nodes": 0, "edges": 0, "pages": 0}
    else:
        prev_graph = read_json(GRAPH_PATH, {})
        graph_generation = _recoverable_graph_snapshot(prev_graph)
        if graph_generation is None:
            errors["graph_snapshot"] = "resident graph snapshot is invalid"
            graph_generation = {
                "publication_id": "", "nodes": 0, "edges": 0,
                "pages": 0}
    errors = _redacted_status_errors(errors)
    sync_note = clip(redact(sync_note, "status-error"), 400)
    projection_debt = {
        "graph": clip(redact(
            _graph_projection_debt(), "status-error"), 400),
        "consolidation": clip(redact(
            _consolidation_scan_debt(), "status-error"), 400),
    }
    if REDACTIONS:
        target_redactions = _projected_pulse_redactions(memo)
        if _pending_pulse_marker(memo) is not None:
            _mark_pulse_publication(
                memo, seq, bound_effects, target_redactions)
        red = memo.setdefault("redactions", {})
        for organ, n in REDACTIONS.items():
            red[organ] = red.get(organ, 0) + n
        redaction_marker = _pending_pulse_marker(memo)
        if redaction_marker is not None \
                and redaction_marker.get("redactions") != red:
            raise RuntimeError(
                "pulse publication redactions binding is invalid")
        REDACTIONS.clear()

    lseq, lhead = ledger_head()
    chain_status = chain_verdict(chains)
    failing = [k for k, v in chains.items() if v == "fail"]
    state = ("failed" if failing else
             "degraded" if (errors or not synced
                            or chain_status != "pass") else
             "thinking" if (events or new_thoughts or agent_activity)
             else "ok")
    last_thought = _status_thought_projection(
        (store["thoughts"] or [{}])[-1])
    if completed_pulse is not None:
        completed_pulse = _pending_pulse_marker(memo)
        memo.pop("pulse_publication", None)
        memo.pop("sync_needed", None)
        memo.update(_with_ready_receipt(
            memo, "pulse", completed_pulse["id"]))
    status_marker = completed_pulse or _pending_pulse_marker(memo)
    status_publication_id = status_marker["id"] \
        if status_marker is not None else uuid.uuid4().hex
    st = {"v": 2, "version": VERSION, "ts": iso(), "state": state,
          "pulse_seq": seq, "day": day,
          "publication_id": status_publication_id,
          "graph_publication_id": graph_generation["publication_id"],
          "events_pulse": len(events),
          "events_today": sum(o.get("today", 0) for o in organs_st.values()),
          "organs": organs_st, "errors": errors,
          "pages": graph_generation["pages"],
          "graph_nodes": graph_generation["nodes"],
          "graph_edges": graph_generation["edges"],
          "integrity": {"chains": chains,
                        "verdict": chain_status,
                        "checked_at": chains_checked_at},
          "ledger": {"seq": lseq, "head": lhead[:12]},
          "ledger_transition": {
              "state": ledger_transition,
              "recovered": len(ledger_recovered),
              "pending_errors": len(ledger_recovery_errors)},
          "thought": last_thought,
          "dream": memo.get("dream", {}),
          "history": memo.get("pulse_history", []),
          "workspace": ws,
          "mind": {"nodes": len(mind.get("nodes", {})),
                   "familiarity_status": memory_state.get(
                       "familiarity_status", "bootstrap-pending"
                       if mind.get("familiarity_bootstrap_pending", False)
                       else "complete"
                       if mind.get("familiarity_complete", False)
                       else "incomplete"),
                   "edges": len(mind.get("edges", {})),
                   "decay_active": memory_state.get("active_edges", 0),
                   "decay_demoted": memory_state.get("demoted_edges", 0),
                   "rehearsal_eligible": memory_state.get("eligible", 0),
                   "rehearsal_due": memory_state.get("due", 0),
                   "pinned": memory_state.get("pinned", 0)},
          "takes": takes_sum,
          "intents": [{"id": it.get("id", "?"),
                       "text": clip(it.get("text", ""), 70),
                       "due": it.get("due", ""),
                       "days_left": it.get("days_left", 0)}
                      for it in intents_open[:MAX_STATUS_INTENTS]
                      if it.get("id") and it.get("text")],
          "bench_trend": bench_trend,
          "bench_trend_boundary": bench_trend_boundary,
          "projection_debt": projection_debt,
          "agent_queue": {"materialized": len(agent_paths),
                          "refused": len(agent_queue_errors),
                          "acknowledged": agent_acknowledged},
          "redactions": memo.get("redactions", {}),
          "sync_note": sync_note}
    if _recoverable_status_integrity(st) is None:
        # Never publish a current-version image that this same runtime would
        # refuse on recovery, and never leave a readiness receipt beside that
        # refusal. If corpus publication already completed, restore its named
        # marker so a later repaired pulse can publish the missing status.
        updated = dict(memo)
        updated.pop("ready", None)
        if status_marker is not None:
            updated.pop("pulse_status_effects_pending", None)
        if completed_pulse is not None:
            recovery_marker = copy.deepcopy(completed_pulse)
            if _status_history_shape(updated.get("pulse_history")) \
                    and updated["pulse_history"] \
                    and updated["pulse_history"][-1] == history_row:
                recovery_marker["history"] = copy.deepcopy(history_row)
            updated["pulse_publication"] = recovery_marker
            updated["sync_needed"] = True
        _write_memo(updated)
        memo.clear()
        memo.update(updated)
        raise RuntimeError("pulse status projection is invalid")
    if status_marker is None:
        # An idle pulse has no named corpus publication marker. Persist its
        # history and other memo-only state first so a crash after the atomic
        # status replacement cannot make the next status retract that row.
        _write_memo(memo)
    export_status(st)
    memo.pop("pulse_status_effects_pending", None)
    # The on-disk debt marker clears last, after every caller-visible derived
    # snapshot. If thoughts/status publication fails, readiness remains
    # blocked even though git, PGLite, and graph may already be current.
    _write_memo(memo)
    native_thought_transaction_final = (
        thought_reinforcement_ready
        and not memo.get("sync_needed", False)
        and _pending_pulse_marker(memo) is None)
    if native_thought_transaction_final:
        # This is deliberately after the final memo image. A crash before
        # here retains per-record receipts. Finalization scans the bounded
        # producer queues and retires only rows whose exact queue ID is gone;
        # failed acknowledgments and deferred new requests remain protected.
        _finalize_native_thought_mind_replay()
    return st


def _pending_dream_unit(mind):
    receipt = mind.get("dream_unit")
    if receipt is None:
        return None
    required = {"v", "id", "unit", "ledger", "thought", "trend"}
    if not isinstance(receipt, dict) or set(receipt) != required \
            or not _exact_int(receipt.get("v"), 1) \
            or not isinstance(receipt.get("id"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", receipt["id"]) is None \
            or receipt.get("unit") not in {"rehearse", "muse", "bench"}:
        raise RuntimeError("dream unit receipt is invalid")
    ledger = receipt.get("ledger")
    if not isinstance(ledger, dict) or set(ledger) != {
            "order", "action", "arg1", "arg2", "content", "record_id"}:
        raise RuntimeError("dream unit ledger binding is invalid")
    try:
        basis = _pending_basis(
            ledger["order"], ledger["action"], ledger["arg1"],
            ledger["arg2"], ledger["content"])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("dream unit ledger binding is invalid") from exc
    expected = {**basis, "record_id": _pending_identity(basis)}
    expected_action = {
        "rehearse": "DREAM:rehearse", "muse": "DREAM:muse",
        "bench": "DREAM:bench",
    }[receipt["unit"]]
    if ledger != expected or ledger["action"] != expected_action:
        raise RuntimeError("dream unit ledger binding is invalid")
    thought = receipt.get("thought")
    if thought is not None:
        if not isinstance(thought, dict) or set(thought) != {
                "kind", "text", "links", "urgent", "queue_id"} \
                or not isinstance(thought.get("kind"), str) \
                or not isinstance(thought.get("text"), str) \
                or not isinstance(thought.get("links"), list) \
                or any(not isinstance(link, str) for link in thought["links"]) \
                or not isinstance(thought.get("urgent"), bool) \
                or not isinstance(thought.get("queue_id"), str) \
                or re.fullmatch(
                    r"[0-9a-f]{32}", thought["queue_id"]) is None:
            raise RuntimeError("dream unit thought binding is invalid")
    trend = receipt.get("trend")
    if receipt["unit"] == "bench":
        if not isinstance(trend, dict):
            raise RuntimeError("dream benchmark trend binding is invalid")
        try:
            encoded = json.dumps(
                trend, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise RuntimeError("dream benchmark trend binding is invalid") \
                from exc
        if len(encoded) > MAX_THOUGHT_INBOX_BYTES:
            raise RuntimeError("dream benchmark trend binding is invalid")
    elif trend is not None:
        raise RuntimeError("dream unit has an unexpected trend binding")
    return receipt


def _stage_dream_unit(mind, unit, action, arg1, arg2, content,
                      thought=None, trend=None):
    if _pending_dream_unit(mind) is not None:
        raise RuntimeError("another dream unit is pending recovery")
    basis = _pending_basis(time.time_ns(), action, arg1, arg2, content)
    ledger = {**basis, "record_id": _pending_identity(basis)}
    probe = {"schema": LEDGER_PENDING_SCHEMA,
             "record_id": ledger["record_id"], "queued_at": iso(), **basis}
    if len((json.dumps(
            probe, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False) + "\n").encode("utf-8")) \
            > MAX_LEDGER_PENDING_RECORD_BYTES:
        raise ValueError("dream unit ledger binding exceeds record bound")
    receipt_id = uuid.uuid4().hex
    thought_binding = None
    if thought is not None:
        kind, text, links, urgent = thought
        thought_binding = {
            "kind": kind, "text": inert_summary(text),
            "links": sorted({_canonical_corpus_slug(link) for link in links})
                     or ["sia/cortex"],
            "urgent": bool(urgent),
            "queue_id": thought_queue_identity(
                f"dream.{unit}", kind, text, links, urgent,
                extra=receipt_id),
        }
    receipt = {"v": 1, "id": receipt_id, "unit": unit,
               "ledger": ledger, "thought": thought_binding,
               "trend": copy.deepcopy(trend)}
    mind["dream_unit"] = receipt
    _pending_dream_unit(mind)
    return receipt


def _append_bench_trend_once(record, receipt_id):
    """Atomically retain a bounded receipt-keyed heuristic trend window."""
    if not isinstance(receipt_id, str) \
            or re.fullmatch(r"[0-9a-f]{32}", receipt_id) is None:
        raise ValueError("benchmark receipt identity is invalid")
    if not isinstance(record, dict) \
            or "dream_unit_id" in record \
            or "legacy_history_truncated" in record:
        raise ValueError("benchmark trend record uses reserved metadata")
    candidate = dict(record, dream_unit_id=receipt_id)
    path = os.path.join(STATE, "bench-trend.jsonl")
    byte_limit = min(MAX_MEMO_BYTES, MAX_BENCH_TREND_BYTES)
    try:
        lines, legacy_truncated = _read_bench_trend_tail(
            path, max_bytes=byte_limit)
    except FileNotFoundError:
        lines = ()
        legacy_truncated = False
    valid_lines = []
    for line in lines:
        try:
            prior = _strict_json_loads(line)
        except (TypeError, UnicodeError, ValueError, RecursionError):
            legacy_truncated = True
            continue
        if not isinstance(prior, dict):
            legacy_truncated = True
            continue
        if prior.get("dream_unit_id") == receipt_id:
            comparable = dict(prior)
            comparable.pop("legacy_history_truncated", None)
            if comparable != candidate:
                raise RuntimeError("benchmark receipt conflicts with trend")
            return False
        valid_lines.append(line.encode("utf-8"))
    # The cockpit consumes only a recent projection. Rotate that derived
    # window before it can strand a durable maintenance-unit receipt at the file's
    # row and byte bounds.
    prior = collections.deque(
        valid_lines,
        maxlen=MAX_BENCH_TREND_ROWS - 1)
    stored_candidate = dict(candidate)
    if legacy_truncated:
        stored_candidate["legacy_history_truncated"] = True
    encoded = json.dumps(
        stored_candidate, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False)
    candidate_line = encoded.encode("utf-8")
    if len(candidate_line) > MAX_BENCH_TREND_LINE_BYTES:
        raise RuntimeError("benchmark trend record exceeds its line bound")
    payload = b"\n".join([*prior, candidate_line]) + b"\n"
    while len(payload) > byte_limit and prior:
        prior.popleft()
        payload = b"\n".join([*prior, candidate_line]) + b"\n"
    if len(payload) > byte_limit:
        raise RuntimeError("benchmark trend record exceeds its byte bound")
    atomic_write(path, payload.decode("utf-8", errors="strict"))
    return True


def _settle_pending_dream_unit(store, expected_unit=None):
    mind = siamind.load_mind()
    receipt = _pending_dream_unit(mind)
    if receipt is None:
        return None
    if expected_unit is not None and receipt["unit"] != expected_unit:
        raise LedgerTransitionError(
            "a different DREAM unit requires recovery first")
    try:
        if receipt["unit"] == "bench":
            _append_bench_trend_once(receipt["trend"], receipt["id"])
        ledger = receipt["ledger"]
        path = queue_ledger_transition(
            ledger["order"], ledger["action"], ledger["arg1"],
            ledger["arg2"], ledger["content"])
        _settle_ledger_transition(path)
        thought = receipt["thought"]
        if thought is not None:
            add_thought(
                store, thought["kind"], thought["text"], thought["links"],
                thought["urgent"], queue_id=thought["queue_id"],
                origin="derived")
        mind.pop("dream_unit", None)
        siamind.save_mind(mind)
    except Exception as exc:
        raise LedgerTransitionError(
            f"DREAM {receipt['unit']} recovery remains pending: {exc}") \
            from exc
    return receipt


def _embed_failure_reason(result):
    """One bounded line explaining a failed rehearsal embed subprocess."""
    text = ((getattr(result, "stderr", "") or "").strip()
            or (getattr(result, "stdout", "") or "").strip()
            or f"exit {getattr(result, 'returncode', '?')}")
    return clip(redact(" ".join(text.split()), "status-error"), 160)


def rehearse_memories(now=None, stage=None, redaction_checkpoint=None):
    """Embed due pages and atomically stage their policy/ledger transition."""
    now = time.time() if now is None else float(now)
    mind = siamind.load_mind(now=now)
    graph = _require_recoverable_graph_snapshot(
        read_json(GRAPH_PATH, {}))
    siamind.sync_graph_state(mind, graph, now=now)
    due = siamind.plan_rehearsal(mind, now=now)
    planned, next_cursor, deferred = siamind.select_rehearsal_window(
        due, mind.get("rehearsal_cursor", 0))
    reviewed, attempted = [], []
    embedded = failed = missing = 0
    for plan in planned:
        item = dict(plan)
        slug = plan["slug"]
        if not page_exists(slug):
            item["embed"] = "missing-corpus-page"
            missing += 1
            attempted.append(item)
            continue
        result = gbrain(["embed", slug, "--source", GBRAIN_SOURCE],
                        timeout=300)
        if result.returncode == 0:
            committed = siamind.apply_rehearsal(mind, plan, now=now)
            if committed is None:
                item["embed"] = "state-changed"
                failed += 1
            else:
                committed["embed"] = "ok"
                item = committed
                reviewed.append(committed)
                embedded += 1
        else:
            item["embed"] = "failed"
            item["error"] = _embed_failure_reason(result)
            failed += 1
        attempted.append(item)
    # Attempts advance the durable fairness cursor even when an embed fails
    # or its corpus page is absent. The stage callback binds that cursor and
    # report into the same pending receipt; the save below commits both before
    # production can publish the signed result from the receipt.
    mind["rehearsal_cursor"] = next_cursor
    decay = siamind.decay_sweep(mind, now=now)
    report = {"reviewed": reviewed, "embedded": embedded, "failed": failed,
              "missing": missing, "planned": attempted,
              "deferred": deferred, "decay": decay}
    if redaction_checkpoint is not None:
        redaction_checkpoint()
    if stage is not None:
        stage(mind, report)
    siamind.save_mind(mind)
    return report


def dream(memo_update=True, now=None):
    """Run the whole nightly workflow under the corpus transaction lease."""
    with corpus_owner():
        return _dream_transaction(memo_update=memo_update, now=now)


def _dream_transaction(memo_update=True, now=None):
    """Install the publication barrier for one scheduled-maintenance cycle."""
    memo = load_memo()
    _settle_pending_brainstem_failure_publication(memo)
    _require_status_memo_fields(memo)
    _pending_pulse_marker(memo)
    _pending_pulse_status_effects(memo)
    cursors = load_cursors()
    _recover_notify_baseline_attempt(memo, cursors)
    if _pending_notify_baseline_attempt(memo) is not None:
        raise RuntimeError(
            "dream refused while notification baseline recovery is pending")
    source_marker = _authorize_pending_source_replay(
        _pending_source_replay_marker(memo), cursors)
    ensure_dirs()
    if _ready_receipt(memo) is None \
            and memo.get("sync_needed", False) is False:
        _mark_sync_needed(memo)
    with corpus_mutation_barrier(lambda: _mark_sync_needed(memo)):
        return _dream_transaction_guarded(
            memo_update, now, memo, cursors=cursors,
            source_marker=source_marker)


def _dream_transaction_guarded(
        memo_update, now, memo, *, cursors=None, source_marker=None):
    """Run weekly compaction and gbrain's compatibility dream cycle."""
    _require_status_memo_fields(memo)
    _pending_pulse_marker(memo)
    _pending_pulse_status_effects(memo)
    cursors = load_cursors() if cursors is None else cursors
    _recover_notify_baseline_attempt(memo, cursors)
    if _pending_notify_baseline_attempt(memo) is not None:
        raise RuntimeError(
            "dream refused while notification baseline recovery is pending")
    current_source_marker = _pending_source_replay_marker(memo)
    if source_marker is not None and current_source_marker != source_marker:
        raise SourceReplayQuarantine(
            "source replay quarantine: marker changed before dream recovery")
    _authorize_pending_source_replay(current_source_marker, cursors)
    if _pending_pulse_status_effects(memo) is not None:
        raise RuntimeError(
            "dream refused while pulse status-effects recovery is pending")
    now = time.time() if now is None else float(now)
    if not isinstance(memo.get("sync_needed", False), bool):
        raise RuntimeError("brainstem memo sync-needed state is invalid")
    store0 = load_thoughts()
    _recover_pending_thought_projection(memo, store0)
    _ledger_recovered, ledger_recovery_errors = recover_ledger_transitions()
    if ledger_recovery_errors:
        raise RuntimeError(
            f"ledger recovery refused: {ledger_recovery_errors}")
    if _settle_pending_dream_unit(store0) is not None:
        export_thoughts(store0)
    _complete_pending_dream_cycle(memo, store0)
    _history_recovered, history_recovery_errors = \
        siatakes.recover_natural_history_transactions(
            before_publish=lambda: _mark_external_corpus_mutation(memo))
    if history_recovery_errors:
        raise RuntimeError(
            f"natural-history recovery refused: {history_recovery_errors}")
    _grade_recovered, grade_recovery_errors = \
        siatakes.recover_grade_transactions(
            before_publish=lambda: _mark_external_corpus_mutation(memo))
    if grade_recovery_errors:
        raise RuntimeError(f"grade recovery refused: {grade_recovery_errors}")
    _reconcile_legacy_memory_authority(memo)
    if _pending_source_replay_marker(memo) is not None:
        raise RuntimeError(
            "dream refused while evidence source replay is pending")
    mind_replay = siamind.load_mind()
    if mind_replay.get("event_applied") \
            or mind_replay.get("event_batch_applied") is not None:
        raise RuntimeError(
            "dream refused while evidence cursor replay is pending")
    _recover_pending_consolidation(memo)
    consolidation_recovery_active = \
        _pending_consolidation_marker(memo) is not None
    if _pending_pulse_marker(memo) is not None:
        _settle_pending_publication(
            memo, "publish interrupted pulse before dream recovery",
            clear=False)
        _recover_pending_pulse_publication(memo)
        if _pending_pulse_status_effects(memo) is not None:
            raise RuntimeError(
                "dream deferred until a pulse publishes recovered status "
                "effects")
    if _pending_dream_marker(memo) is not None:
        _settle_pending_publication(
            memo, "publish interrupted dream before dream recovery",
            clear=False)
        _recover_pending_dream_publication(memo)
    _settle_pending_publication(
        memo, "publish pending corpus migration before dream")
    # The nightly job is independent units with separate ledgers and
    # failure domains — a bad grade must never block an epoch merge, and a
    # failed heuristic drift tripwire must never block the gbrain cycle.
    ncomp = nepoch = nkept = 0
    if not consolidation_recovery_active:
        consolidation_marker = _mark_consolidation_pending(memo)
        _bind_consolidation_ledger(
            memo, "DREAM:consolidate", f"id={consolidation_marker['id']}",
            "completed")
        try:
            result = _recover_pending_consolidation(memo)
            if result is not None:
                ncomp, nepoch, nkept = result
        except Exception as e:
            detail = _dream_diagnostic(memo, e, 80)
            durable_ledger_append(
                "DREAM:consolidate", "error", detail)
            log(f"consolidation failed: {detail}")
            raise RuntimeError(
                f"dream consolidation requires recovery: {detail}") from e
    if ncomp:
        add_thought(store0, "dream",
            f"Weekly compaction combined {ncomp} day pages into {nepoch} epoch "
            f"pages; {nkept} protected day pages stay verbatim. "
            f"Original versions remain in corpus git history.", ["sia/cortex"])
    # Consolidation rewrites corpus topology. Rehearsal must never embed
    # against the pre-consolidation index or graph.
    export_thoughts(store0)
    _settle_thought_page_signals(store0)
    _settle_pending_publication(
        memo, "publish dream consolidation before rehearsal")
    try:
        def stage_rehearsal(mind, rehearsal):
            reviewed = rehearsal["reviewed"]
            thought = None
            deferred = rehearsal["deferred"]
            deferred_text = ("" if not deferred else
                f" {deferred} additional due "
                f"{'memory' if deferred == 1 else 'memories'} deferred "
                f"beyond this nightly window; their schedules remain due "
                f"for later rotating nightly windows.")
            failure_text = ("" if not (
                rehearsal["failed"] or rehearsal["missing"]) else
                f" {rehearsal['failed']} embed failure(s), "
                f"{rehearsal['missing']} missing page(s); those schedules "
                f"remain due.")
            if reviewed:
                qualities = {}
                for item in reviewed:
                    quality = item["quality"]
                    qualities[quality] = qualities.get(quality, 0) + 1
                quality_text = ", ".join(
                    f"q{quality}:{count}"
                    for quality, count in sorted(qualities.items()))
                thought_text = (
                    f"Scheduled re-embedding completed for {len(reviewed)} "
                    f"priority pages under SM-2 ({quality_text}); "
                    f"{rehearsal['embedded']} pages re-embedded. Decay "
                    f"only changes retrieval salience; it never deletes "
                    f"evidence.{failure_text}{deferred_text}")
                thought = (
                    "dream", thought_text,
                    [item["slug"] for item in reviewed[:5]],
                    bool(rehearsal["failed"] or rehearsal["missing"]))
            elif rehearsal["failed"] or rehearsal["missing"]:
                reasons = sorted({item["error"]
                                  for item in rehearsal["planned"]
                                  if item.get("error")})
                detail = f" First reason: {reasons[0]}" if reasons else ""
                thought = (
                    "dream",
                    f"Scheduled re-embedding did not complete for any of the "
                    f"{len(rehearsal['planned'])} due memories: "
                    f"{rehearsal['failed']} embed failure(s), "
                    f"{rehearsal['missing']} missing page(s). The SM-2 "
                    f"schedules for those attempted pages remain due."
                    f"{deferred_text}{detail}",
                    [item["slug"] for item in rehearsal["planned"][:5]],
                    True)
            _stage_dream_unit(
                mind, "rehearse", "DREAM:rehearse",
                f"reviewed={len(reviewed)}",
                f"embedded={rehearsal['embedded']} "
                f"failed={rehearsal['failed']} "
                f"missing={rehearsal['missing']} "
                f"deferred={deferred}",
                json.dumps(reviewed, sort_keys=True), thought=thought)

        rehearsal = rehearse_memories(
            now=now, stage=stage_rehearsal,
            redaction_checkpoint=lambda:
                _checkpoint_dream_redactions(memo))
        _settle_pending_dream_unit(store0, expected_unit="rehearse")
    except LedgerTransitionError as exc:
        detail = _dream_diagnostic(memo, exc, 160)
        raise LedgerTransitionError(detail) from exc
    except Exception as e:
        detail = _dream_diagnostic(memo, e, 80)
        durable_ledger_append("DREAM:rehearse", "error", detail)
        log(f"rehearsal failed: {detail}")
    export_thoughts(store0)
    _settle_thought_page_signals(store0)
    _settle_pending_publication(
        memo, "publish scheduled-review entries before graph walk")
    try:
        g = _require_musing_graph_snapshot(
            read_json(GRAPH_PATH, None))
        mind = siamind.load_mind()
        pruned = siamind.hebb_hygiene(mind, now=now)
        lseq, lhead = ledger_head()
        if isinstance(lseq, bool) or not isinstance(lseq, int) \
                or not 0 < lseq <= MAX_JSON_SAFE_INTEGER \
                or not isinstance(lhead, str) \
                or re.fullmatch(r"[0-9a-f]{64}", lhead) is None:
            raise RuntimeError("signed ledger head is unavailable for seeded graph walk")
        dream_day = datetime.datetime.fromtimestamp(
            now, datetime.timezone.utc).strftime("%Y-%m-%d")
        m = siamind.muse(mind, g, dream_day, lhead, now=now)
        thought = ("association", m[0], m[1], False) if m else None
        _stage_dream_unit(
            mind, "muse", "DREAM:muse", "1" if m else "0",
            f"edges-pruned={pruned}", "", thought=thought)
        siamind.save_mind(mind)
        _settle_pending_dream_unit(store0, expected_unit="muse")
    except LedgerTransitionError as exc:
        detail = _dream_diagnostic(memo, exc, 160)
        raise LedgerTransitionError(detail) from exc
    except Exception as e:
        detail = _dream_diagnostic(memo, e, 80)
        durable_ledger_append("DREAM:muse", "error", detail)
        log(f"seeded graph walk failed: {detail}")
    # prediction grading: grade due predictions (≤3/night; configured judge,
    # deterministic Brier), then restate calibration
    try:
        completed_grades = 0
        def persist_grade(row, verdict, justification, evidence_snapshots):
            siatakes.commit_grade_transition(
                row, verdict, justification, evidence_snapshots,
                before_publish=lambda: _mark_external_corpus_mutation(memo))
            _settle_pending_publication(
                memo, "publish dream grade before continuing")

        due_grades = siatakes.due_takes()[:3]
        for t in due_grades:
            export_thoughts(store0)
            _settle_thought_page_signals(store0)
            _settle_pending_publication(
                memo, "publish prior maintenance entries before grading")
            gt = siatakes.grade_take(t, persist=persist_grade)
            if not gt:
                continue
            completed_grades += 1
            mark = {"resolved-true": "TRUE",
                    "resolved-false": "FALSE"}.get(gt["status"],
                                                   "UNRESOLVABLE")
            brier = (f" · Brier {gt['brier']}"
                     if gt["brier"] is not None else "")
            add_thought(store0, "grade",
                f"Prediction graded: “{clip(gt['claim'], 80)}”: "
                f"{mark}{brier}.", [gt["slug"]], origin="model")
        if completed_grades:
            cal = siatakes.summary()
            if cal.get("resolved"):
                add_thought(store0, "calibration",
                    f"Descriptive calibration restated: {cal['resolved']} "
                    f"resolved take(s), mean Brier {cal['brier']}, "
                    f"population status {cal['calibration_status']}. "
                    f"Operator-selected and model-assisted; no world-truth "
                    f"or generalization claim.", ["sia/cortex"],
                    origin="model")
        attempted_grades = len(due_grades)
        refused_grades = attempted_grades - completed_grades
        if not attempted_grades:
            grade_state = "none-due"
            grade_detail = ""
        else:
            grade_state = "done" if completed_grades else "refused"
            grade_detail = (
                f"attempted={attempted_grades} "
                f"completed={completed_grades} refused={refused_grades}")
        durable_ledger_append("DREAM:grade", grade_state, grade_detail)
    except LedgerTransitionError as exc:
        detail = _dream_diagnostic(memo, exc, 160)
        raise LedgerTransitionError(detail) from exc
    except Exception as e:
        detail = _dream_diagnostic(memo, e, 80)
        durable_ledger_append("DREAM:grade", "error", detail)
        log(f"take grading failed: {detail}")
    # Heuristic drift tripwire: the historian retains a small date-seeded
    # observation of slug-family proximity. It does not run a reader or score
    # answer correctness; the full signed-ledger QA benchmark is separate.
    try:
        export_thoughts(store0)
        _settle_thought_page_signals(store0)
        _settle_pending_publication(
            memo, "publish dream grades before benchmark")
        import siabench
        q = siabench.run_quick()
        if q:
            blend = q["slug_match_at_5_blend"]
            keyword = q["slug_match_at_5_keyword"]
            probes = q["probe_count"]
            if (not isinstance(blend, (int, float))
                    or isinstance(blend, bool) or not 0 <= blend <= 1
                    or not isinstance(keyword, (int, float))
                    or isinstance(keyword, bool) or not 0 <= keyword <= 1
                    or not isinstance(probes, int) or isinstance(probes, bool)
                    or probes <= 0):
                raise ValueError("quick benchmark returned invalid metrics")
            thought_text = (
                f"Heuristic slug-family drift tripwire: blend match@5 "
                f"{blend:.2f}, keyword {keyword:.2f} over {probes} probes. "
                f"Slug proximity only; no answer correctness was evaluated.")
            mind = siamind.load_mind()
            _stage_dream_unit(
                mind, "bench", "DREAM:bench",
                f"blend-slug-match@5={blend}",
                f"keyword-slug-match@5={keyword} probes={probes}", "",
                thought=("bench", thought_text, ["sia/cortex"], False),
                trend=q)
            try:
                siamind.save_mind(mind)
            except Exception as exc:
                raise LedgerTransitionError(
                    f"DREAM benchmark staging remains uncertain: {exc}") \
                    from exc
            _settle_pending_dream_unit(store0, expected_unit="bench")
    except LedgerTransitionError as exc:
        detail = _dream_diagnostic(memo, exc, 160)
        raise LedgerTransitionError(detail) from exc
    except Exception as e:
        detail = _dream_diagnostic(memo, e, 80)
        durable_ledger_append("DREAM:bench", "error", detail)
        log(f"heuristic drift tripwire failed: {detail}")
    export_thoughts(store0)
    _settle_thought_page_signals(store0)
    _settle_pending_publication(
        memo, "publish dream benchmark before gbrain cycle")
    # gbrain's compatibility ``dream`` command mutates derived PGLite state. Publish a
    # recovery identity before launching it, so a kill during any phase keeps
    # readiness closed until corpus sync + graph export are reconciled.
    _mark_dream_publication(memo, _projected_pulse_redactions(memo))
    r = gbrain(["dream", "--json"], timeout=900)
    rep = None
    if r.returncode == 0:
        for opener in ("{",):
            i = r.stdout.find(opener)
            if i >= 0:
                try:
                    parsed = _strict_json_loads(r.stdout[i:])
                    if isinstance(parsed, dict):
                        rep = parsed
                except Exception:
                    pass
    store = load_thoughts()
    cycle_finished = (rep is not None and
                      rep.get("status") in {"ok", "clean", "partial"})
    if cycle_finished:
        tot = rep.get("totals", {})
        bits = _dream_diagnostic(memo, ", ".join(
            f"{v} {k.replace('_', ' ')}" for k, v in tot.items()
            if isinstance(k, str) and isinstance(v, (int, float)) and v),
            400)
        text = (f"Weekly maintenance finished with status "
                f"“{rep.get('status')}” in "
                f"{round(rep.get('duration_ms', 0) / 1000)}s"
                + (f" — {bits}." if bits else "."))
        dream_state = {"last": iso(), "status": rep.get("status"),
                       "summary": bits}
        totals_payload = json.dumps(
            tot, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False)
        cycle_content = json.dumps({
            "totals_sha256": hashlib.sha256(
                totals_payload.encode("utf-8")).hexdigest(),
            "transaction": _pending_dream_marker(memo)["id"],
        }, sort_keys=True, separators=(",", ":"))
        _bind_pending_dream_cycle(
            memo, dream_state, str(rep.get("status", "?"))[:80],
            bits[:100], cycle_content, text)
        _complete_pending_dream_cycle(memo, store)
    elif rep is not None:
        previous = memo.get("dream", {})
        status = _dream_diagnostic(
            memo, rep.get("status") or "invalid-status", 80)
        reason = _dream_diagnostic(
            memo, rep.get("reason") or "cycle did not finish", 400)
        dream_state = {
            "last": previous.get("last", ""), "attempt": iso(),
            "status": status, "summary": reason[-160:]}
        _bind_pending_dream_cycle(
            memo, dream_state, status, reason[:100], "",
            f"Weekly maintenance did not finish: {status} ({reason}).",
            urgent=True)
        _complete_pending_dream_cycle(memo, store)
    else:
        previous = memo.get("dream", {})
        failure_detail = _dream_diagnostic(
            memo, r.stderr or r.stdout or "no diagnostic output", 400)
        dream_state = {
            "last": previous.get("last", ""), "attempt": iso(),
            "status": "failed", "summary": failure_detail[-160:]}
        _bind_pending_dream_cycle(
            memo, dream_state, "failed", failure_detail[-100:], "",
            "Weekly maintenance failed to run.", urgent=True)
        _complete_pending_dream_cycle(memo, store)
    export_thoughts(store)
    _settle_thought_page_signals(store)
    commit = corpus_commit("dream")
    if commit == "error":
        _bind_pending_dream_ledger(
            memo, "error", "corpus git commit failed", "")
        _settle_pending_dream_ledger(memo)
        raise RuntimeError("dream corpus git commit failed")
    try:
        synced, sync_note = brain_sync()
        nodes, edges, pages_total = _export_graph_publication()
    except Exception as exc:
        detail = _dream_diagnostic(memo, exc, 120)
        _bind_pending_dream_ledger(
            memo, "error", detail, "projection exception")
        _settle_pending_dream_ledger(memo)
        raise RuntimeError(
            f"dream publication failed: {detail}") from exc
    sync_note = _dream_diagnostic(memo, sync_note, 400)
    _bind_pending_dream_ledger(
        memo, "ok" if synced else "sync-fail",
        f"commit={commit} graph={nodes}/{edges}/{pages_total}",
        sync_note)
    _settle_pending_dream_ledger(memo)
    if not synced:
        raise RuntimeError(f"scheduled-maintenance index sync failed: {sync_note}")
    cleared_memo = dict(memo)
    completed_dream = _pending_dream_marker(memo)
    if "redactions" in completed_dream:
        cleared_memo["redactions"] = copy.deepcopy(
            _pulse_redactions_at_least_memo(
                memo, completed_dream["redactions"]))
    cleared_memo.pop("dream_publication", None)
    cleared_memo.pop("sync_needed", None)
    cleared_memo = _with_ready_receipt(
        cleared_memo, "dream", completed_dream["id"])
    _write_memo(cleared_memo)
    memo.clear()
    memo.update(cleared_memo)
    # Scheduled maintenance state is durable, but an earlier pulse may
    # have left an external producer retryable. Selective finalization keeps
    # every queue-bound row whose exact producer still exists.
    _finalize_native_thought_mind_replay()
    if not cycle_finished:
        status = rep.get("status") if rep is not None else "failed"
        raise RuntimeError(f"gbrain dream cycle {status}")
    return rep

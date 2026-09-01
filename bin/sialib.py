"""sialib — core of SIA, the Omarchy Brain.

The brainstem daemon tails enabled base/optional/configured evidence streams
into a markdown corpus, syncs it into SIA's own gbrain (PGLite) brain, checks
configured signed chains through their keeper verifiers, and derives
deterministic generator thoughts alongside origin-labeled user/model prose.
Everything the widget shows comes from the JSON snapshots exported here.

Honesty rules (house style):
  - Ledger rows elsewhere are recall; each keeper verifier is its evidence path.
  - Generator thoughts cite sources; user/model prose stays origin-labeled.
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
# JACKAL status=exact, parsed=16*1024*1024, exact=16777216. Exact rational
# arithmetic outside the Lean certificate chain (NOT formal-bounded).
MAX_STATE_JSON_BYTES = 16_777_216

CONFIG_ERRORS = []


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

def load_config():
    CONFIG_ERRORS.clear()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(CONFIG_PATH, flags)
    except FileNotFoundError:
        return {}
    except OSError:
        _record_config_error("config-open-refused")
        return {}
    try:
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) \
                    or before.st_size > MAX_CONFIG_BYTES:
                _record_config_error("config-file-refused")
                return {}
            raw = stream.read(MAX_CONFIG_BYTES + 1)
            after = os.fstat(stream.fileno())
        observed = (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns)
        finished = (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns)
        if observed != finished or len(raw) > MAX_CONFIG_BYTES:
            _record_config_error("config-changed-or-over-bound")
            return {}
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeError:
            _record_config_error("config-invalid-utf8")
            return {}
        try:
            value = json.loads(text)
        except (UnicodeError, ValueError, RecursionError):
            _record_config_error("config-invalid-json")
            return {}
        if not isinstance(value, dict):
            _record_config_error("config-must-be-object")
            return {}
        senses = value.get("senses", {})
        if not isinstance(senses, dict):
            _record_config_error("senses-must-be-object")
        else:
            disabled = senses.get("disable", [])
            if not isinstance(disabled, list):
                _record_config_error("senses-disable-must-be-list")
            elif len(disabled) > MAX_CONFIG_BYTES or any(
                    not _strict_config_string(
                        item, nonempty=True, limit=MAX_SOURCE_NAME_CHARS)
                    for item in disabled):
                _record_config_error("senses-disable-entry-invalid")
        custom = value.get("custom_senses", [])
        if not isinstance(custom, list):
            _record_config_error("custom-senses-must-be-list")
        elif len(custom) > MAX_CONFIG_BYTES:
            _record_config_error("custom-senses-over-bound")
        return value
    except OSError:
        _record_config_error("config-read-refused")
        return {}

CONFIG = load_config()


def _configured_obsidian_vault():
    """Absolute vault root for the optional Obsidian organ.

    An absent environment override selects ``~/Obsidian``.  A present
    override must already be an absolute, bounded UTF-8 path.  Invalid
    overrides disable the organ instead of silently falling back to a
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

# organs every box has
BASE_ORGANS = {
    "sia":         ("SIA ledger",  "SIA's signed lifecycle transitions"),
    "pacman":      ("pacman",      "package manager"),
    "journal":     ("journal",     "systemd journal (errors and faults)"),
    "claude-code": ("Claude Code", "Claude agent sessions on this box"),
    "projects":    ("Projects",    "git activity under ~/Projects"),
    "notify":      ("Notifications", "desktop notification stream"),
    "agents":      ("Agents",       "AI-agent usage meters (Omarchy Quattro)"),
}
# optional integrations: active only when their data exists on this box
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


def _configured_disabled_organs():
    senses = CONFIG.get("senses", {})
    if not isinstance(senses, dict):
        return set()
    disabled = senses.get("disable", [])
    if not isinstance(disabled, list) \
            or len(disabled) > MAX_CONFIG_BYTES \
            or any(not _strict_config_string(
                       value, nonempty=True, limit=MAX_SOURCE_NAME_CHARS)
                   for value in disabled):
        return set()
    return set(disabled)


def _build_organs():
    organs = dict(BASE_ORGANS)
    disabled = _configured_disabled_organs()
    for key, (name, desc, probe) in OPTIONAL_ORGANS.items():
        if key in disabled:
            continue
        if key == "obsidian":
            try:
                active = (OBSIDIAN_VAULT is not None
                          and _nofollow_source_directory(os.path.join(
                              OBSIDIAN_VAULT, ".git")))
            except (OSError, RuntimeError, ValueError):
                active = False
        else:
            probe_path = (probe if os.path.isabs(probe)
                          else os.path.join(HOME, probe))
            active = os.path.exists(probe_path)
        if active:
            organs[key] = (name, desc)
    configured = CONFIG.get("custom_senses", [])
    if not isinstance(configured, list) \
            or len(configured) > MAX_CONFIG_BYTES:
        configured = []
    for cs in configured:
        if not isinstance(cs, dict) or cs.get("enabled") is False \
                or ("enabled" in cs
                    and not isinstance(cs.get("enabled"), bool)):
            continue
        name = cs.get("name")
        organ = cs.get("organ", name)
        description = cs.get("description", "custom evidence stream")
        if not _strict_config_string(
                name, nonempty=True, limit=MAX_CONFIG_TEXT_CHARS) \
                or not _strict_config_string(
                    organ, nonempty=True, limit=MAX_CONFIG_TEXT_CHARS) \
                or not _strict_config_string(
                    description, limit=MAX_CONFIG_TEXT_CHARS):
            continue
        o = sanitize_slugpart(organ)
        if len(o) > MAX_SOURCE_NAME_CHARS \
                or re.fullmatch(r"[a-z0-9_][a-z0-9._-]*", o) is None:
            continue
        organs.setdefault(o, (o, description))
    for key in disabled:
        organs.pop(key, None)
    return organs

# Tags that carry emotional weight for salience (mirrored into gbrain config).
HIGH_TAGS = ["integrity-failure", "refusal", "crash", "coredump", "failed",
             "collapse", "healing", "urgent"]

VERSION = "1.4.2"


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

def atomic_write(path, data):
    mode = 0o600
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        current = None
    if current is not None:
        if not stat.S_ISREG(current.st_mode):
            raise ValueError("atomic-write target is not a regular file")
        mode = stat.S_IMODE(current.st_mode)
    if not isinstance(data, str):
        raise TypeError("atomic-write data must be text")
    encoded = data.encode("utf-8", errors="strict")
    siaqueue.fixed_atomic_publish(
        path, encoded, mode=mode,
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
        | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except Exception:
        return default
    try:
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) \
                    or before.st_size > MAX_STATE_JSON_BYTES:
                return default
            raw = stream.read(MAX_STATE_JSON_BYTES + 1)
            after = os.fstat(stream.fileno())
        observed = (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns)
        finished = (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns)
        if observed != finished or len(raw) > MAX_STATE_JSON_BYTES:
            return default
        return json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError):
        return default


def _strict_json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def read_state_json(path, default, label):
    """Read daemon-owned JSON without following links or hiding damage.

    Missing state has a well-defined bootstrap value. Existing state is a
    durable cursor/transaction boundary, so malformed, unreadable, linked,
    or type-confused files must stop the writer instead of silently resetting
    it and laundering skipped evidence into a fresh snapshot.
    """
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return copy.deepcopy(default)
    except OSError as exc:
        raise RuntimeError(f"{label} state cannot be opened safely: {exc}") \
            from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError(f"{label} state is not a regular file")
        try:
            with os.fdopen(fd, "rb") as stream:
                fd = -1
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) \
                        or before.st_size > MAX_STATE_JSON_BYTES:
                    raise RuntimeError(
                        f"{label} state is not a bounded regular file")
                raw = stream.read(MAX_STATE_JSON_BYTES + 1)
                after = os.fstat(stream.fileno())
                observed = (before.st_dev, before.st_ino, before.st_size,
                            before.st_mtime_ns, before.st_ctime_ns)
                finished = (after.st_dev, after.st_ino, after.st_size,
                            after.st_mtime_ns, after.st_ctime_ns)
                if observed != finished or len(raw) > MAX_STATE_JSON_BYTES:
                    raise RuntimeError(
                        f"{label} state changed while read or exceeds its bound")
                value = json.loads(
                    raw.decode("utf-8"),
                    object_pairs_hook=_strict_json_object)
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            raise RuntimeError(
                f"{label} state is unreadable or malformed") from exc
    finally:
        if fd >= 0:
            os.close(fd)
    if not isinstance(value, type(default)):
        raise RuntimeError(
            f"{label} state has type {type(value).__name__}; "
            f"expected {type(default).__name__}")
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
# JACKAL status=exact: parsed=200*2+1, exact=401. Exact rational arithmetic
# outside the Lean certificate chain (NOT formal-bounded).
MAX_THOUGHT_RECOVERY_SCAN_ENTRIES = 401


class ThoughtRecoveryPending(RuntimeError):
    """One bounded baseline generation committed; another remains."""


class ThoughtDirectoryGenerationChanged(ValueError):
    """The quiescent legacy directory changed around a durable cookie."""


# JACKAL status=exact, parsed=255-3, exact=252. Exact rational arithmetic
# outside the Lean certificate chain (NOT formal-bounded). The leaf reserves
# three bytes for the persisted `.md` suffix.
MAX_CORPUS_COMPONENT_BYTES = 255
MAX_CORPUS_LEAF_BYTES = 252
THOUGHT_ORIGINS = frozenset({"evidence", "derived", "model"})


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
                      and kind in {"grade", "ponder", "note", "take"}
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
        | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
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
        inbox = json.loads(raw.decode("utf-8"))
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
    """Locked RMW for out-of-band thoughts produced by CLI workflows."""
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
    """Claim one durable CLI-thought batch; preserve it until acknowledged."""
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

def redact(text, organ="?"):
    out, n = strip_controls(text), 0
    for pat in REDACT_PATTERNS:
        out, k = pat.subn("⟦redacted⟧", out)
        n += k
    if n:
        REDACTIONS[organ] = REDACTIONS.get(organ, 0) + n
    return out


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
        self.links = set(sorted(
            {_canonical_corpus_slug(str(link)) for link in links})[
                :MAX_LEDGER_PENDING_RECORDS])
        normalized_tags = {sanitize_slugpart(str(tag)) for tag in tags}
        if any(len(tag) > MAX_SOURCE_NAME_CHARS for tag in normalized_tags):
            raise ValueError("event tag exceeds its canonical bound")
        self.tags = set(sorted(normalized_tags)[
            :MAX_LEDGER_PENDING_RECORDS])
        if not isinstance(occurrence, str):
            raise ValueError("event occurrence identity is invalid")
        occurrence = strip_controls(occurrence)
        if len(occurrence.encode("utf-8")) > MAX_THOUGHT_INBOX_TEXT:
            raise ValueError("event occurrence identity is invalid")
        self.occurrence = occurrence


def event_memory_identity(event):
    """Bind mind replay state to one exact normalized event observation."""
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
    """Admit one exact meaning for each organ/source occurrence per pulse."""
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
    encoded = json.dumps(c, indent=1, sort_keys=True)
    if len(encoded.encode("utf-8")) > MAX_STATE_JSON_BYTES:
        raise ValueError("evidence cursor state exceeds its byte bound")
    atomic_write(CURSORS_PATH, encoded)


# JACKAL status=exact, parsed=256*1024, exact=262144. This exact
# arithmetic is outside the Lean certificate chain (NOT formal-bounded).
MAX_SOURCE_TAIL_BYTES = 262_144
# JACKAL status=exact, parsed=64*1024, exact=65536. Same assurance boundary.
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
            | getattr(os, "O_NOFOLLOW", 0), dir_fd=descriptor)
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


def _stable_tail_chunk(path, cursors, key, max_read):
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
    try:
        fd = _open_source_nofollow(path, flags)
    except FileNotFoundError:
        return generation, ordinal or 0, b""
    updates = {}
    record_refusal = None
    clear_skip = False
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"line source {key} is not a regular file")
        size = before.st_size
        current_schema = cursors.get(names["version"]) == \
            SOURCE_CURSOR_VERSION
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
        try:
            target = _source_path_identity(path, flags)
        except FileNotFoundError as exc:
            raise RuntimeError(f"line source {key} changed while cursoring") \
                from exc
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or (target.st_dev, target.st_ino) != (
            after.st_dev, after.st_ino):
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


def tail_line_records(path, cursors, key, refusal_validator=None):
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
            path, cursors, key, MAX_SOURCE_TAIL_BYTES)
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
                path, cursors, key, prefix_bytes)
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


def tail_lines(path, cursors, key):
    return [line for _generation, _ordinal, line in tail_line_records(
        path, cursors, key)]


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


def _bounded_source_state(cursors, key, namespace):
    """Load a bounded versioned map whose keys are already canonical tokens."""
    raw = cursors.get(key)
    if raw is None:
        entries = {}
    elif isinstance(raw, list) and len(raw) == 2 \
            and raw[0] == "sia-source-entity-state-v1" \
            and isinstance(raw[1], dict):
        entries = raw[1]
    elif isinstance(raw, dict):
        # Pre-schema maps already persisted lossy canonical tokens. Preserve
        # each valid key exactly for a one-time conservative migration; the
        # next complete source snapshot retires stale legacy identities.
        entries = raw
    else:
        raise ValueError(f"source cursor {key} is invalid")
    state = {}
    truncated = len(entries) > MAX_SOURCE_SCAN_ENTRIES
    for source_key, value in entries.items():
        if len(state) >= MAX_SOURCE_SCAN_ENTRIES:
            truncated = True
            break
        if not isinstance(source_key, str) \
                or re.fullmatch(r"[a-z0-9_][a-z0-9._-]*", source_key) is None \
                or len(source_key) > MAX_SOURCE_NAME_CHARS \
                or len(source_key.encode("utf-8")) > MAX_CORPUS_LEAF_BYTES:
            token = _source_entity_token(source_key, namespace)
        else:
            token = source_key
        state.setdefault(token, value)
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
    with os.fdopen(fd, "rb") as stream:
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
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished \
            or (target.st_dev, target.st_ino) != (after.st_dev,
                                                  after.st_ino):
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
    with os.fdopen(fd, "rb") as stream:
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
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished \
            or (target.st_dev, target.st_ino) != (after.st_dev,
                                                  after.st_ino):
        raise RuntimeError(f"{label} changed while reading")
    try:
        value = json.loads(raw.decode("utf-8"))
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
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished \
            or (target.st_dev, target.st_ino) != (after.st_dev,
                                                  after.st_ino):
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
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished \
            or (current.st_dev, current.st_ino) != (after.st_dev,
                                                    after.st_ino):
        raise RuntimeError("source directory changed while checking")
    return True


# Optional organ discovery needs the no-follow directory gate above.  Keep
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
        generation = value.get("generation")
        phase = value.get("phase")
        coverage = value.get("coverage")
        if isinstance(generation, bool) or not isinstance(generation, int) \
                or generation < 0 or phase not in {"scan", "validate"} \
                or not isinstance(coverage, bool):
            raise ValueError("source tree cursor is invalid")
    else:
        # An old queue may already be mid-generation and did not remember a
        # prior missing/reset frame. Finish it without deletion authority,
        # then begin a clean v3 generation.
        generation = 0
        phase = "scan"
        coverage = False
    queue = []
    for item in value["queue"]:
        if len(queue) >= MAX_SOURCE_SCAN_ENTRIES:
            raise ValueError("source tree cursor exceeds its queue bound")
        if not isinstance(item, dict):
            raise ValueError("source tree cursor is invalid")
        relative = item.get("relative")
        levels = item.get("levels")
        parts = relative.split(os.sep) if relative else []
        if not isinstance(relative, str) or os.path.isabs(relative) \
                or (relative and any(part in {"", ".", ".."}
                                     for part in parts)) \
                or len(relative) > MAX_CONFIG_PATH_CHARS \
                or any(len(os.fsencode(part)) > MAX_CORPUS_COMPONENT_BYTES
                       for part in parts) \
                or (os.altsep and os.altsep in relative) \
                or isinstance(levels, bool) or not isinstance(levels, int) \
                or levels < 0 or levels > directory_levels:
            raise ValueError("source tree cursor is invalid")
        queue.append({"relative": relative, "levels": levels,
                      "page": _validated_source_page_state(
                          item.get("page"))})
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
                or not isinstance(item, dict):
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
                or not isinstance(item.get("generation"), dict):
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
                if not stat.S_ISDIR(entry["mode"]):
                    continue
                relative = os.path.join(item["relative"], entry["name"])
                child = {"relative": relative,
                         "levels": item["levels"] - 1, "page": {}}
                if len(queue) >= MAX_SOURCE_SCAN_ENTRIES:
                    coverage = False
                    refused.append(relative)
                else:
                    queue.append(child)
        else:
            for entry in entries:
                if stat.S_ISREG(entry["mode"]) \
                        and entry["name"].endswith(suffix):
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
# Reuse the source/state bounds already enforced by the rest of the brainstem.
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
DEFAULT_SKILL_ROOTS = [
    ".claude/skills", ".agents/skills", ".omp/skills",
    ".copilot/skills", ".config/agents/skills"]
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

# only senses whose organ is active on THIS machine run
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
        # A thought that cannot be stably classified must not bypass this
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

def ensure_entity(slug, ptype, title, body_lines):
    if page_exists(slug):
        return False
    write_page(slug,
               [f"type: {ptype}", fm_title(title)],
               f"# {title}\n\n" + "\n".join(body_lines) + "\n")
    return True

def ensure_organs():
    made = ensure_entity("sia/cortex", "organ", "SIA cortex", [
        "I am SIA, the Omarchy Brain — the associative memory of this machine.",
        "Every enabled organ below reports what it observes. Each configured",
        "signed chain is checked by its own keeper verifier; Custos also uses",
        "the SPARK-proved `attest` verifier. Deterministic thought generators",
        "are evidence-derived; user/model prose is origin-labeled.", ""])
    for key, (name, desc) in ORGANS.items():
        organ_slug = _canonical_corpus_slug(f"organs/{key}")
        safe_desc = inert_summary(desc)
        made |= ensure_entity(organ_slug, "organ", name, [
            f"{safe_desc}. Organ of [[sia/cortex]].", ""])
    return made


def day_slug(organ, date):
    return f"events/{organ}/{date}"


MAX_EVENT_BULLETS = 400
MAX_EVENT_SHARDS = 1024
MAX_EVENT_LOOKUP_PAGES = 4096
# JACKAL status=exact, parsed=4096+1, exact=4097. Exact rational arithmetic
# outside the Lean certificate chain (NOT formal-bounded). One extra raw
# directory inspection distinguishes a complete ceiling-sized snapshot from
# a source that exceeds the supported complete-snapshot capacity.
MAX_EVENT_DIRECTORY_INSPECTIONS = 4097
MAX_EVENT_PAGE_BYTES = 1_048_576
MAX_EVENT_INDEX_BYTES = 65_536
MAX_EVENT_INDEX_RECORDS = 65_536
MAX_EPOCH_SOURCE_RECORDS = MAX_EVENT_LOOKUP_PAGES
MAX_EPOCH_PAGE_BYTES = MAX_EVENT_PAGE_BYTES
MAX_EPOCH_SOURCE_MANIFEST_BYTES = MAX_EPOCH_PAGE_BYTES
CONSOLIDATION_SCAN_SCHEMA = "sia-consolidation-scan-v1"
MAX_CONSOLIDATION_DAYS_PER_RUN = MAX_CONFIG_TAGS
MAX_CONSOLIDATION_DIRECTORY_QUEUE = MAX_EVENT_LOOKUP_PAGES
# JACKAL status=exact, parsed=2-1, exact=1. Exact rational arithmetic outside
# the Lean certificate chain (NOT formal-bounded): events/<organ>/<page> has
# one directory level below the events root.
MAX_CONSOLIDATION_TREE_LEVELS = 1
EVENT_INDEX_SCHEMA = "sia-consolidated-event-v1"
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


def _parse_sia_counts(raw, label):
    try:
        counts = json.loads(raw)
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


def _read_event_page(slug):
    """Read one bounded regular event page without following its leaf."""
    path = corpus_path(slug)
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_size > MAX_EVENT_PAGE_BYTES:
            raise ValueError(f"event page is not a bounded regular file: {slug}")
        raw = stream.read(MAX_EVENT_PAGE_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_EVENT_PAGE_BYTES:
        raise ValueError(f"event page changed while read: {slug}")
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


def _event_page_state(organ, date, part):
    slug = _event_shard_slug(organ, date, part)
    text = _read_event_page(slug)
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
    candidates = [
        os.path.join(root, entry["name"])
        for entry in _bounded_event_directory_snapshot(
            root, cleanup_legacy_atomic=True)
        if stat.S_ISREG(entry["mode"])
        and entry["name"].startswith(os.path.basename(base_path[:-3])
                                     + "-part-")
        and entry["name"].endswith(".md")]
    part_re = re.compile(
        rf"^{re.escape(base_path[:-3])}-part-([2-9][0-9]*)\.md$")
    parts = []
    for path in candidates:
        match = part_re.fullmatch(path)
        if match is None:
            continue
        parts.append(int(match.group(1)))
    if len(parts) != len(set(parts)) or len(parts) >= MAX_EVENT_SHARDS \
            or any(part > MAX_EVENT_SHARDS for part in parts):
        raise ValueError("event day shard set is invalid or exceeds its bound")
    parts.sort()
    if page_exists(base):
        if any(part != position for position, part in
               enumerate(parts, start=2)):
            raise ValueError("event day shards are not contiguous")
        return [_event_page_state(organ, date, 1)] + [
            _event_page_state(organ, date, part) for part in parts]
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
    """Return the canonical organ/day/shard identity of an event source."""
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
             | getattr(os, "O_NOFOLLOW", 0))
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as stream:
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
        entry = json.loads(raw.decode("utf-8"))
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


def _other_event_occurrences(organ, wanted, excluded):
    """Find source-native IDs already admitted on another recent day."""
    if not wanted:
        return {}
    if len(wanted) > MAX_EVENT_INDEX_RECORDS:
        raise ValueError("event occurrence lookup exceeds its identity bound")
    root = os.path.join(CORPUS, "events", organ)
    paths = [os.path.join(root, entry["name"])
             for entry in _bounded_event_directory_snapshot(
                 root, cleanup_legacy_atomic=True)
             if stat.S_ISREG(entry["mode"])
             and entry["name"].endswith(".md")]
    found = {}
    page_re = re.compile(
        rf"^events/{re.escape(organ)}/[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}"
        r"(?:-part-[2-9][0-9]*)?$")
    for path in sorted(paths):
        slug = os.path.relpath(path, CORPUS)[:-3]
        if slug in excluded or page_re.fullmatch(slug) is None:
            continue
        text = _read_event_page(slug)
        for line in text.splitlines():
            marker = EVENT_MARKER_RE.fullmatch(line)
            if marker is None or marker.group("id") not in wanted:
                continue
            event_id = marker.group("id")
            prior = found.get(event_id)
            value = (slug, _event_payload_digest(marker.group("payload")),
                     marker.group("semantic"))
            if prior is not None and prior != value:
                raise ValueError("event identity occurs with conflicting bytes")
            found[event_id] = value
    for event_id in sorted(wanted):
        entry = _read_event_index_entry(organ, event_id)
        if entry is None:
            continue
        if event_id in found:
            raise ValueError(
                "event identity occurs in live and consolidated evidence")
        found[event_id] = (
            entry["epoch_slug"], entry["payload_sha256"],
            entry["semantic_id"])
    return found


def _preflight_event_lookup(events):
    organs = {event.organ for event in events if event.occurrence}
    for organ in organs:
        root = os.path.join(CORPUS, "events", organ)
        _bounded_event_directory_snapshot(root, cleanup_legacy_atomic=True)


def _preflight_event_path_plan(planned_paths_by_organ):
    """Bound the union of every day planned for each organ in this pulse."""
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


def _canonical_thought_page_record(thought):
    """Project a thought into the exact self-describing page record."""
    if not isinstance(thought, dict):
        raise ValueError("thought record must be an object")
    timestamp = _canonical_utc_timestamp(thought.get("ts"))
    kind = thought.get("kind")
    text = thought.get("text")
    origin = _canonical_thought_origin(thought.get("origin", "derived"))
    links_in = thought.get("links") or ["sia/cortex"]
    if not isinstance(kind, str) or sanitize_slugpart(kind) != kind:
        raise ValueError("thought kind is not canonical")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("thought text must be a non-empty string")
    if not isinstance(links_in, (list, tuple, set)):
        raise ValueError("thought links must be a sequence")
    links_in = sorted({_canonical_corpus_slug(link) for link in links_in})
    text = inert_summary(text)
    queue_id = thought.get("queue_id")
    if queue_id is not None and not re.fullmatch(r"[0-9a-f]{32}", queue_id):
        raise ValueError("invalid thought queue identity")
    record = {"ts": timestamp, "kind": kind, "text": text,
              "links": links_in, "urgent": bool(thought.get("urgent")),
              "origin": origin}
    if queue_id:
        record["queue_id"] = queue_id
    if "slug" in thought:
        record["slug"] = _canonical_corpus_slug(thought["slug"])
    return record


def _thought_page_parts(record):
    tags = ["thought", record["kind"]] \
        + (["urgent"] if record["urgent"] else [])
    links_in = record["links"] or ["sia/cortex"]
    links = " ".join(f"[[{link}]]" for link in links_in)
    fm = ["type: thought", fm_title(clip(record["text"], 70)),
          f"tags: [{', '.join(tags)}]", f"date: {record['ts'][:10]}",
          f"origin: {record['origin']}",
          "sia_thought: " + json.dumps(
              record, sort_keys=True, ensure_ascii=False)]
    if record.get("queue_id"):
        fm.append(f"queue_id: {record['queue_id']}")
    body = (f"# thought · {record['kind']}\n\n{record['text']}\n\n"
            f"{links}\n")
    return fm, body


def _queued_thought_slug(queue_id):
    """Name queue-owned thoughts solely from their durable identity."""
    if not isinstance(queue_id, str) \
            or re.fullmatch(r"[0-9a-f]{32}", queue_id) is None:
        raise ValueError("invalid thought queue identity")
    return f"thoughts/queue-{queue_id}"


def _thought_queue_binding(record):
    """Fields whose exact equality is promised by one queue identity.

    ``ts`` is deliberately excluded: it records the first successful
    materialization, while a retry can occur later.  The durable page supplies
    that original timestamp after every bounded projection has aged out.
    """
    return {key: record[key] for key in
            ("kind", "text", "links", "urgent", "origin", "queue_id")}


def _read_thought_page_text(slug):
    """Read one stable, bounded, no-follow thought page."""
    path = corpus_path(_canonical_corpus_slug(slug))
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_size > MAX_THOUGHT_INBOX_BYTES:
            raise RuntimeError("thought page is not a bounded regular file")
        raw = stream.read(MAX_THOUGHT_INBOX_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_THOUGHT_INBOX_BYTES:
        raise RuntimeError("thought page changed while read")
    try:
        return raw.decode("utf-8")
    except UnicodeError as exc:
        raise RuntimeError("thought page is not UTF-8") from exc


def _decode_exact_thought_page(slug, text_value):
    """Recover and byte-verify one self-described thought page."""
    metadata = re.findall(r"^sia_thought: (.*)$", text_value, re.M)
    if not metadata:
        raise RuntimeError("thought page has no recovery metadata")
    if len(metadata) != 1:
        raise RuntimeError("thought page has duplicate recovery metadata")
    try:
        encoded_record = json.loads(metadata[0])
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise RuntimeError("thought recovery metadata is malformed") from exc
    allowed = {"ts", "kind", "text", "links", "urgent", "origin",
               "queue_id", "slug"}
    if not isinstance(encoded_record, dict) \
            or set(encoded_record) - allowed:
        raise RuntimeError("thought recovery metadata is invalid")
    record = _canonical_thought_page_record(encoded_record)
    if record != encoded_record:
        raise RuntimeError("thought recovery metadata is noncanonical")
    if record.get("slug") != slug:
        raise RuntimeError("thought recovery metadata binds another page")
    if record.get("queue_id") \
            and slug != _queued_thought_slug(record["queue_id"]):
        raise RuntimeError("queued thought page has a noncanonical identity")
    fm, body = _thought_page_parts(record)
    expected = "---\n" + "\n".join(fm) + "\n---\n" + body
    if text_value != expected:
        raise RuntimeError("thought page differs from its recovery record")
    return record


def _thought_recovery_dir():
    return os.path.join(STATE, THOUGHT_RECOVERY_DIRNAME)


def _thought_legacy_index_dir():
    return os.path.join(STATE, THOUGHT_LEGACY_INDEX_DIRNAME)


def _thought_legacy_catalog_path():
    return os.path.join(STATE, THOUGHT_LEGACY_CATALOG_NAME)


def _thought_mind_replay_path():
    return os.path.join(STATE, THOUGHT_MIND_REPLAY_NAME)


def _thought_recovery_claim_path():
    return os.path.join(STATE, THOUGHT_RECOVERY_CLAIM_NAME)


def _thought_legacy_scan_path():
    return os.path.join(STATE, THOUGHT_LEGACY_SCAN_NAME)


def _thought_recovery_lock_path():
    return os.path.join(STATE, THOUGHT_RECOVERY_LOCK_NAME)


def _ensure_private_recovery_directory(path):
    ensure_durable_directory(path, mode=0o700)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError("thought recovery store is not an owned directory")
        os.fchmod(descriptor, 0o700)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def _thought_recovery_record(page_record):
    page = _canonical_thought_page_record(page_record)
    if "slug" not in page:
        raise ValueError("thought recovery record requires a page slug")
    payload = json.dumps(
        page, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf-8")
    record_id = hashlib.sha256(payload).hexdigest()
    return {"schema": THOUGHT_RECOVERY_SCHEMA,
            "record_id": record_id, "page": page}


def _thought_recovery_record_bytes(record):
    if not isinstance(record, dict) or set(record) != {
            "schema", "record_id", "page"} \
            or record.get("schema") != THOUGHT_RECOVERY_SCHEMA:
        raise ValueError("thought recovery record schema is invalid")
    expected = _thought_recovery_record(record.get("page"))
    if record != expected:
        raise ValueError("thought recovery record identity is invalid")
    encoded = (json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
        raise ValueError("thought recovery record exceeds its byte bound")
    return encoded


def _read_thought_recovery_record(path):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_mode & 0o077 \
                or before.st_size > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
            raise ValueError(
                "thought recovery record is not a bounded private file")
        raw = stream.read(MAX_THOUGHT_RECOVERY_RECORD_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
        raise ValueError("thought recovery record changed while read")
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("thought recovery record is malformed") from exc
    if raw != _thought_recovery_record_bytes(record) \
            or os.path.basename(path) != record["record_id"] + ".json":
        raise ValueError("thought recovery record path binding is invalid")
    return record, observed


def _list_thought_recovery_records_locked():
    directory = _thought_recovery_dir()
    try:
        info = os.lstat(directory)
    except FileNotFoundError:
        return []
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("thought recovery store is not a real directory")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    names = []
    total = 0
    inspected = 0
    cleaned = False
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode) \
                or opened.st_uid != os.geteuid():
            raise ValueError(
                "thought recovery store is not an owned directory")
        with os.scandir(descriptor) as entries:
            for entry in entries:
                inspected += 1
                if inspected >= MAX_THOUGHT_RECOVERY_SCAN_ENTRIES:
                    raise ValueError(
                        "thought recovery store exceeds its scan bound")
                name = entry.name
                if _legacy_atomic_temp_name(name):
                    _remove_legacy_atomic_temp(
                        descriptor, entry, "thought recovery store")
                    cleaned = True
                    continue
                if name.startswith("."):
                    continue
                if re.fullmatch(r"[0-9a-f]{64}\.json", name) is None:
                    raise ValueError(
                        "thought recovery store has an unexpected entry")
                if len(names) >= MAX_THOUGHT_RECOVERY_RECORDS:
                    raise ValueError(
                        "thought recovery queue exceeds its record bound")
                entry_info = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(entry_info.st_mode) \
                        or entry_info.st_size \
                        > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
                    raise ValueError(
                        "thought recovery queue has an invalid record")
                if entry_info.st_size > MAX_THOUGHT_RECOVERY_BYTES - total:
                    raise ValueError(
                        "thought recovery queue exceeds its byte bound")
                total += entry_info.st_size
                names.append(name)
    finally:
        if cleaned:
            os.fsync(descriptor)
        os.close(descriptor)
    records = []
    for name in sorted(names):
        record, _identity = _read_thought_recovery_record(
            os.path.join(directory, name))
        records.append(record)
    return records


def _thought_recovery_claim_basis(records, active_ids, legacy):
    canonical = [_thought_recovery_record(record["page"])
                 for record in records]
    canonical.sort(key=lambda record: (
        record["page"]["ts"], record["page"]["slug"],
        record["record_id"]))
    if not isinstance(active_ids, list) \
            or any(not isinstance(value, str)
                   or re.fullmatch(r"[0-9a-f]{64}", value) is None
                   for value in active_ids) \
            or sorted(set(active_ids)) != active_ids:
        raise ValueError("thought recovery claim active IDs are invalid")
    canonical_ids = {record["record_id"] for record in canonical}
    if any(value not in canonical_ids for value in active_ids):
        raise ValueError("thought recovery claim active ID is unbound")
    if legacy is not None:
        required = {"before", "after", "complete", "entries", "unindexed",
                    "directory", "discarded", "indexed_before",
                    "indexed_after"}
        if not isinstance(legacy, dict) or set(legacy) != required \
                or not isinstance(legacy.get("before"), str) \
                or not isinstance(legacy.get("after"), str) \
                or legacy["after"] <= legacy["before"] \
                or legacy["before"] and re.fullmatch(
                    r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{64}\.json",
                    legacy["before"]) is None \
                or not isinstance(legacy.get("complete"), bool) \
                or not isinstance(legacy.get("entries"), list) \
                or isinstance(legacy.get("unindexed"), bool) \
                or not isinstance(legacy.get("unindexed"), int) \
                or legacy["unindexed"] < 0 \
                or isinstance(legacy.get("indexed_before"), bool) \
                or not isinstance(legacy.get("indexed_before"), int) \
                or legacy["indexed_before"] <= 0 \
                or isinstance(legacy.get("indexed_after"), bool) \
                or not isinstance(legacy.get("indexed_after"), int) \
                or legacy["indexed_after"] < 0:
            raise ValueError("thought recovery legacy claim is invalid")
        directory = _validated_thought_directory_generation(
            legacy.get("directory"))
        if directory is None:
            raise ValueError("thought recovery legacy directory is invalid")
        discarded = legacy.get("discarded")
        if not isinstance(discarded, list) \
                or len(discarded) > MAX_THOUGHT_RECOVERY_RECORDS \
                or any(not isinstance(item, str)
                       or re.fullmatch(r"[0-9a-f]{32}", item) is None
                       for item in discarded) \
                or len(set(discarded)) != len(discarded):
            raise ValueError(
                "thought recovery legacy discarded generations are invalid")
        entries = []
        for entry in legacy["entries"]:
            _thought_legacy_index_bytes(entry)
            entries.append(dict(entry))
        names = [entry["index_name"] for entry in entries]
        if len(entries) != len(canonical) or names != sorted(set(names)) \
                or not names or names[0] <= legacy["before"] \
                or names[-1] != legacy["after"] \
                or legacy["indexed_before"] - len(entries) \
                != legacy["indexed_after"] \
                or legacy["complete"] \
                != (legacy["indexed_after"] == 0):
            raise ValueError("thought recovery legacy range is invalid")
        pages = {record["page"]["slug"]: record["page"]
                 for record in canonical}
        if len(pages) != len(canonical):
            raise ValueError("thought recovery legacy pages are duplicated")
        for entry in entries:
            page = pages.get(entry["slug"])
            if page is None or page["ts"] != entry["ts"]:
                raise ValueError("thought recovery legacy page is unbound")
            frontmatter, body = _thought_page_parts(page)
            rendered = "---\n" + "\n".join(frontmatter) + "\n---\n" + body
            if hashlib.sha256(rendered.encode("utf-8")).hexdigest() \
                    != entry["page_sha256"]:
                raise ValueError("thought recovery legacy digest is unbound")
        legacy = {**legacy, "entries": entries, "directory": directory,
                  "discarded": list(discarded)}
    return {"records": canonical, "active_ids": active_ids,
            "legacy": legacy}


def _thought_recovery_claim_document(
        records, active_ids, legacy, claim_id=None):
    basis = _thought_recovery_claim_basis(records, active_ids, legacy)
    payload = json.dumps(
        basis, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf-8")
    claim_id = uuid.uuid4().hex if claim_id is None else claim_id
    if not isinstance(claim_id, str) \
            or re.fullmatch(r"[0-9a-f]{32}", claim_id) is None:
        raise ValueError("thought recovery claim identity is invalid")
    return {"schema": THOUGHT_RECOVERY_CLAIM_SCHEMA,
            "claim_id": claim_id,
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            **basis}


def _thought_recovery_claim_bytes(claim):
    if not isinstance(claim, dict) or set(claim) != {
            "schema", "claim_id", "payload_sha256", "records",
            "active_ids", "legacy"} \
            or claim.get("schema") != THOUGHT_RECOVERY_CLAIM_SCHEMA:
        raise ValueError("thought recovery claim schema is invalid")
    expected = _thought_recovery_claim_document(
        claim.get("records"), claim.get("active_ids"), claim.get("legacy"),
        claim_id=claim.get("claim_id"))
    if claim != expected:
        raise ValueError("thought recovery claim binding is invalid")
    encoded = (json.dumps(
        claim, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_THOUGHT_RECOVERY_BYTES:
        raise ValueError("thought recovery claim exceeds its byte bound")
    return encoded


def _read_thought_recovery_claim():
    path = _thought_recovery_claim_path()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_mode & 0o077 \
                or before.st_size > MAX_THOUGHT_RECOVERY_BYTES:
            raise ValueError(
                "thought recovery claim is not a bounded private file")
        raw = stream.read(MAX_THOUGHT_RECOVERY_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_THOUGHT_RECOVERY_BYTES:
        raise ValueError("thought recovery claim changed while read")
    try:
        claim = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("thought recovery claim is malformed") from exc
    if raw != _thought_recovery_claim_bytes(claim):
        raise ValueError("thought recovery claim is noncanonical")
    return claim


def _queue_thought_recovery(page_record):
    """Durably bind a page intent before any corresponding corpus write."""
    record = _thought_recovery_record(page_record)
    encoded = _thought_recovery_record_bytes(record)
    ensure_durable_directory(STATE, mode=0o700)
    with _owner_lease(_thought_recovery_lock_path(), "thought recovery"):
        directory = _ensure_private_recovery_directory(
            _thought_recovery_dir())
        path = os.path.join(directory, record["record_id"] + ".json")
        if os.path.lexists(path):
            existing, _identity = _read_thought_recovery_record(path)
            if existing != record:
                raise ValueError("thought recovery identity collision")
            return record["record_id"]
        records = _list_thought_recovery_records_locked()
        if len(records) >= MAX_THOUGHT_RECOVERY_RECORDS:
            raise ValueError("thought recovery queue reached its record bound")
        candidate = records + [record]
        _thought_recovery_claim_bytes(_thought_recovery_claim_document(
            candidate,
            sorted(item["record_id"] for item in candidate), None,
            claim_id="0" * 32))
        atomic_write(path, encoded.decode("utf-8"))
        os.chmod(path, 0o600)
    return record["record_id"]


class _ThoughtRecoveryDirent(ctypes.Structure):
    """Linux dirent ABI for a durable legacy-baseline cookie."""
    _fields_ = [
        ("d_ino", ctypes.c_ulong), ("d_off", ctypes.c_long),
        ("d_reclen", ctypes.c_ushort), ("d_type", ctypes.c_ubyte),
        ("d_name", ctypes.c_char * (MAX_CORPUS_COMPONENT_BYTES + 1)),
    ]


_THOUGHT_RECOVERY_LIBC = ctypes.CDLL(None, use_errno=True)
_THOUGHT_RECOVERY_LIBC.fdopendir.argtypes = [ctypes.c_int]
_THOUGHT_RECOVERY_LIBC.fdopendir.restype = ctypes.c_void_p
_THOUGHT_RECOVERY_LIBC.readdir.argtypes = [ctypes.c_void_p]
_THOUGHT_RECOVERY_LIBC.readdir.restype = ctypes.POINTER(
    _ThoughtRecoveryDirent)
_THOUGHT_RECOVERY_LIBC.telldir.argtypes = [ctypes.c_void_p]
_THOUGHT_RECOVERY_LIBC.telldir.restype = ctypes.c_long
_THOUGHT_RECOVERY_LIBC.seekdir.argtypes = [ctypes.c_void_p, ctypes.c_long]
_THOUGHT_RECOVERY_LIBC.seekdir.restype = None
_THOUGHT_RECOVERY_LIBC.closedir.argtypes = [ctypes.c_void_p]
_THOUGHT_RECOVERY_LIBC.closedir.restype = ctypes.c_int


def _thought_directory_generation(info):
    return {"device": info.st_dev, "inode": info.st_ino,
            "size": info.st_size, "mtime_ns": info.st_mtime_ns,
            "ctime_ns": info.st_ctime_ns}


def _validated_thought_directory_generation(value):
    if value is None:
        return None
    required = {"device", "inode", "size", "mtime_ns", "ctime_ns"}
    if not isinstance(value, dict) or set(value) != required \
            or any(isinstance(value[name], bool)
                   or not isinstance(value[name], int)
                   or value[name] < 0 for name in required):
        raise ValueError("legacy thought directory generation is invalid")
    return dict(value)


def _read_legacy_thought_directory_page(
        directory, generation, cookie, limit):
    """Inspect at most ``limit`` raw entries and return a durable next cookie.

    The baseline runs while the corpus owner is held.  Its first page pins the
    directory generation; a replacement, addition, removal, or rename between
    pages refuses instead of allowing a new entry behind the opaque Linux
    cookie to escape.  Every native SIA write is separately journaled before
    touching the directory.
    """
    generation = _validated_thought_directory_generation(generation)
    if isinstance(cookie, bool) or not isinstance(cookie, int) or cookie < 0 \
            or isinstance(limit, bool) or not isinstance(limit, int) \
            or limit <= 0:
        raise ValueError("legacy thought directory cursor is invalid")
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_DIRECTORY", 0))
    try:
        descriptor = os.open(directory, flags)
    except FileNotFoundError:
        if generation is not None or cookie:
            raise ThoughtDirectoryGenerationChanged(
                "legacy thought directory disappeared during baseline")
        return [], True, 0, None, 0
    except OSError as exc:
        if generation is not None or cookie:
            raise ThoughtDirectoryGenerationChanged(
                "legacy thought directory changed between bounded pages") \
                from exc
        raise
    directory_pointer = None
    try:
        before = os.fstat(descriptor)
        observed_generation = _thought_directory_generation(before)
        if not stat.S_ISDIR(before.st_mode) \
                or before.st_uid != os.geteuid():
            raise ValueError(
                "legacy thought source is not an owned directory")
        if generation is not None and generation != observed_generation:
            raise ThoughtDirectoryGenerationChanged(
                "legacy thought directory changed between bounded pages")
        scan_descriptor = os.dup(descriptor)
        directory_pointer = _THOUGHT_RECOVERY_LIBC.fdopendir(scan_descriptor)
        if not directory_pointer:
            saved_errno = ctypes.get_errno()
            os.close(scan_descriptor)
            raise OSError(saved_errno, os.strerror(saved_errno), directory)
        if cookie:
            _THOUGHT_RECOVERY_LIBC.seekdir(directory_pointer, cookie)
        selected = []
        inspected = 0
        complete = False
        while inspected < limit:
            ctypes.set_errno(0)
            record = _THOUGHT_RECOVERY_LIBC.readdir(directory_pointer)
            if not record:
                saved_errno = ctypes.get_errno()
                if saved_errno:
                    raise OSError(
                        saved_errno, os.strerror(saved_errno), directory)
                complete = True
                break
            inspected += 1
            raw_name = bytes(record.contents.d_name).split(b"\0", 1)[0]
            name = os.fsdecode(raw_name)
            if name in {".", ".."}:
                continue
            try:
                info = os.stat(
                    name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError as exc:
                raise ThoughtDirectoryGenerationChanged(
                    "legacy thought directory changed while scanned") from exc
            selected.append({"name": name, "mode": info.st_mode,
                             "device": info.st_dev, "inode": info.st_ino,
                             "size": info.st_size,
                             "mtime_ns": info.st_mtime_ns,
                             "ctime_ns": info.st_ctime_ns})
        next_cookie = (0 if complete else int(
            _THOUGHT_RECOVERY_LIBC.telldir(directory_pointer)))
        if next_cookie < 0:
            raise ValueError("legacy thought directory cookie is invalid")
        after = os.fstat(descriptor)
        try:
            target = os.stat(directory, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise ThoughtDirectoryGenerationChanged(
                "legacy thought directory changed while scanned") from exc
    finally:
        if directory_pointer:
            _THOUGHT_RECOVERY_LIBC.closedir(directory_pointer)
        os.close(descriptor)
    finished_generation = _thought_directory_generation(after)
    target_generation = _thought_directory_generation(target)
    if observed_generation != finished_generation \
            or observed_generation != target_generation \
            or not stat.S_ISDIR(target.st_mode):
        raise ThoughtDirectoryGenerationChanged(
            "legacy thought directory changed while scanned")
    selected.sort(key=lambda item: item["name"])
    return (selected, complete, next_cookie,
            observed_generation, inspected)


def _assert_legacy_thought_directory_generation(generation):
    """Refuse between-page corpus mutations before applying the baseline."""
    generation = _validated_thought_directory_generation(generation)
    directory = os.path.join(CORPUS, "thoughts")
    if generation is None:
        if os.path.lexists(directory):
            raise ThoughtDirectoryGenerationChanged(
                "legacy thought directory appeared after baseline scan")
        return
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_DIRECTORY", 0))
    try:
        descriptor = os.open(directory, flags)
    except OSError as exc:
        raise ThoughtDirectoryGenerationChanged(
            "legacy thought directory changed after baseline scan") from exc
    try:
        info = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if not stat.S_ISDIR(info.st_mode) \
            or info.st_uid != os.geteuid() \
            or _thought_directory_generation(info) != generation:
        raise ThoughtDirectoryGenerationChanged(
            "legacy thought directory changed after baseline scan")


def _current_legacy_thought_directory_generation():
    """Return one owned no-follow directory generation, or absent."""
    directory = os.path.join(CORPUS, "thoughts")
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_DIRECTORY", 0))
    try:
        descriptor = os.open(directory, flags)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError("legacy thought source is not an owned directory")
    return _thought_directory_generation(info)


def _thought_legacy_index_entry(page_name, record, page_text):
    if not isinstance(page_name, str) \
            or re.fullmatch(r"[a-z0-9_.-]+\.md", page_name) is None:
        raise ValueError("legacy thought page name is invalid")
    page = _canonical_thought_page_record(record)
    if page.get("slug") != "thoughts/" + page_name[:-3]:
        raise ValueError("legacy thought page identity is invalid")
    if not isinstance(page_text, str):
        raise ValueError("legacy thought page text is invalid")
    stamp = page["ts"].replace("-", "").replace(":", "")
    index_name = (stamp + "-"
                  + hashlib.sha256(page["slug"].encode("utf-8")).hexdigest()
                  + ".json")
    return {"schema": THOUGHT_LEGACY_INDEX_SCHEMA,
            "index_name": index_name, "page_name": page_name,
            "slug": page["slug"], "ts": page["ts"],
            "page_sha256": hashlib.sha256(
                page_text.encode("utf-8")).hexdigest()}


def _thought_legacy_index_bytes(entry):
    required = {"schema", "index_name", "page_name", "slug", "ts",
                "page_sha256"}
    if not isinstance(entry, dict) or set(entry) != required \
            or entry.get("schema") != THOUGHT_LEGACY_INDEX_SCHEMA \
            or not isinstance(entry.get("index_name"), str) \
            or re.fullmatch(
                r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{64}\.json",
                entry["index_name"]) is None \
            or not isinstance(entry.get("page_name"), str) \
            or re.fullmatch(
                r"[a-z0-9_.-]+\.md", entry["page_name"]) is None \
            or not isinstance(entry.get("slug"), str) \
            or entry["slug"] != "thoughts/" + entry["page_name"][:-3] \
            or _canonical_corpus_slug(entry["slug"]) != entry["slug"] \
            or _canonical_utc_timestamp(entry.get("ts")) != entry["ts"] \
            or not isinstance(entry.get("page_sha256"), str) \
            or re.fullmatch(
                r"[0-9a-f]{64}", entry["page_sha256"]) is None:
        raise ValueError("legacy thought index entry is invalid")
    expected_name = (entry["ts"].replace("-", "").replace(":", "") + "-"
                     + hashlib.sha256(
                         entry["slug"].encode("utf-8")).hexdigest()
                     + ".json")
    if entry["index_name"] != expected_name:
        raise ValueError("legacy thought index identity is invalid")
    encoded = (json.dumps(
        entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
        raise ValueError("legacy thought index entry exceeds its byte bound")
    return encoded


def _read_thought_legacy_index_entry(path):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_mode & 0o077 \
                or before.st_size > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
            raise ValueError(
                "legacy thought index is not a bounded private file")
        raw = stream.read(MAX_THOUGHT_RECOVERY_RECORD_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
        raise ValueError("legacy thought index changed while read")
    try:
        entry = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("legacy thought index is malformed") from exc
    if raw != _thought_legacy_index_bytes(entry) \
            or os.path.basename(path) != entry["index_name"]:
        raise ValueError("legacy thought index path binding is invalid")
    return entry


def _write_thought_legacy_index(entry):
    encoded = _thought_legacy_index_bytes(entry)
    directory = _ensure_private_recovery_directory(
        _thought_legacy_index_dir())
    path = os.path.join(directory, entry["index_name"])
    if os.path.lexists(path):
        if _read_thought_legacy_index_entry(path) != entry:
            raise ValueError("legacy thought index identity collision")
        return path
    atomic_write(path, encoded.decode("utf-8"))
    os.chmod(path, 0o600)
    return path


@contextlib.contextmanager
def _thought_legacy_catalog():
    """Open the bounded-query catalog for canonical JSON index records."""
    ensure_durable_directory(STATE, mode=0o700)
    path = _thought_legacy_catalog_path()
    existed = os.path.lexists(path)
    if existed:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError("legacy thought catalog is not an owned file")
    connection = sqlite3.connect(path, timeout=2.0)
    try:
        if hasattr(connection, "setlimit"):
            connection.setlimit(
                sqlite3.SQLITE_LIMIT_LENGTH,
                MAX_THOUGHT_RECOVERY_RECORD_BYTES)
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS legacy_thought_index ("
            "index_name TEXT PRIMARY KEY NOT NULL, "
            "entry_json TEXT NOT NULL) WITHOUT ROWID")
        objects = connection.execute(
            "SELECT type, name FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()
        if objects != [("table", "legacy_thought_index")]:
            raise ValueError("legacy thought catalog schema is invalid")
        columns = connection.execute(
            "PRAGMA table_info(legacy_thought_index)").fetchall()
        column_shape = [(row[1], row[2], row[3], row[5])
                        for row in columns]
        if column_shape != [
                ("index_name", "TEXT", 1, 1),
                ("entry_json", "TEXT", 1, 0)]:
            raise ValueError("legacy thought catalog columns are invalid")
        connection.commit()
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError("legacy thought catalog changed while opened")
        os.chmod(path, 0o600)
        if not existed:
            _sync_directory(STATE)
        yield connection
    finally:
        connection.close()


@contextlib.contextmanager
def _thought_mind_replay_catalog():
    """Open exact, bounded-query replay journals for every thought source."""
    ensure_durable_directory(STATE, mode=0o700)
    path = _thought_mind_replay_path()
    existed = os.path.lexists(path)
    if existed:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError("thought mind replay journal is not an owned file")
    connection = sqlite3.connect(path, timeout=2.0)
    try:
        if hasattr(connection, "setlimit"):
            connection.setlimit(
                sqlite3.SQLITE_LIMIT_LENGTH,
                MAX_THOUGHT_RECOVERY_RECORD_BYTES)
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS thought_mind_replay ("
            "record_id TEXT PRIMARY KEY NOT NULL, "
            "claim_id TEXT NOT NULL, claim_sha256 TEXT NOT NULL, "
            "state TEXT NOT NULL) WITHOUT ROWID")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS native_thought_mind_replay ("
            "record_id TEXT PRIMARY KEY NOT NULL, "
            "claim_id TEXT NOT NULL, claim_sha256 TEXT NOT NULL, "
            "state TEXT NOT NULL, queue_id TEXT NOT NULL) WITHOUT ROWID")
        objects = connection.execute(
            "SELECT type, name FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()
        if objects != [
                ("table", "native_thought_mind_replay"),
                ("table", "thought_mind_replay")]:
            raise ValueError("thought mind replay journal schema is invalid")
        expected_legacy_columns = [
            ("record_id", "TEXT", 1, 1),
            ("claim_id", "TEXT", 1, 0),
            ("claim_sha256", "TEXT", 1, 0),
            ("state", "TEXT", 1, 0)]
        legacy_columns = connection.execute(
            "PRAGMA table_info(thought_mind_replay)").fetchall()
        legacy_shape = [(row[1], row[2], row[3], row[5])
                        for row in legacy_columns]
        native_columns = connection.execute(
            "PRAGMA table_info(native_thought_mind_replay)").fetchall()
        native_shape = [(row[1], row[2], row[3], row[5])
                        for row in native_columns]
        if legacy_shape != expected_legacy_columns \
                or native_shape != expected_legacy_columns + [
                    ("queue_id", "TEXT", 1, 0)]:
            raise ValueError(
                "thought mind replay journal columns are invalid")
        connection.commit()
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError("thought mind replay journal changed while opened")
        os.chmod(path, 0o600)
        if not existed:
            _sync_directory(STATE)
        yield connection
    finally:
        connection.close()


def _thought_mind_replay_records(claim):
    """Return one validated claim's exact replay identities and scope."""
    _thought_recovery_claim_bytes(claim)
    table = ("thought_mind_replay" if claim.get("legacy") is not None
             else "native_thought_mind_replay")
    return [(table, record["record_id"], claim["claim_id"],
             claim["payload_sha256"],
             record["page"].get("queue_id", ""))
            for record in claim["records"]]


def _thought_mind_replay_intent(claim):
    """Durably stage exact page IDs before changing their mind projection."""
    records = _thought_mind_replay_records(claim)
    if not records:
        return set()
    if claim.get("legacy") is None:
        # A prior transaction may have crashed after producer acknowledgment
        # but before end-of-pulse receipt retirement. Retire those now, before
        # enforcing capacity, while preserving every exact record in this
        # already-durable active claim.
        _finalize_native_thought_mind_replay(
            protected_record_ids={record["record_id"]
                                  for record in claim["records"]})
    applied = set()
    with _thought_mind_replay_catalog() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            native_rows = connection.execute(
                "SELECT COUNT(*) FROM native_thought_mind_replay"
                ).fetchone()[0]
            for table, record_id, claim_id, claim_sha256, queue_id in records:
                row = connection.execute(
                    "SELECT claim_id, claim_sha256, state"
                    + (", queue_id" if table ==
                       "native_thought_mind_replay" else "") + " "
                    f"FROM {table} "
                    "WHERE record_id = ?", (record_id,)).fetchone()
                if row is None:
                    if table == "native_thought_mind_replay" \
                            and native_rows >= MAX_THOUGHT_RECOVERY_RECORDS:
                        raise ValueError(
                            "thought mind replay journal reached its bound")
                    if table == "native_thought_mind_replay":
                        connection.execute(
                            "INSERT INTO native_thought_mind_replay "
                            "(record_id, claim_id, claim_sha256, state, "
                            "queue_id) VALUES (?, ?, ?, ?, ?)",
                            (record_id, claim_id, claim_sha256, "pending",
                             queue_id))
                    else:
                        connection.execute(
                            "INSERT INTO thought_mind_replay "
                            "(record_id, claim_id, claim_sha256, state) "
                            "VALUES (?, ?, ?, ?)",
                            (record_id, claim_id, claim_sha256, "pending"))
                    if table == "native_thought_mind_replay":
                        native_rows += 1
                    continue
                prior_claim, prior_sha256, state = row[:3]
                if not isinstance(prior_claim, str) \
                        or re.fullmatch(r"[0-9a-f]{32}", prior_claim) is None \
                        or not isinstance(prior_sha256, str) \
                        or re.fullmatch(
                            r"[0-9a-f]{64}", prior_sha256) is None \
                        or state not in {"pending", "applied"}:
                    raise ValueError(
                        "thought mind replay journal row is invalid")
                if table == "native_thought_mind_replay" \
                        and (row[3] != queue_id
                             or not isinstance(row[3], str)
                             or (row[3] and re.fullmatch(
                                 r"[0-9a-f]{32}", row[3]) is None)):
                    raise ValueError(
                        "thought mind replay queue binding is invalid")
                if state == "pending" and (
                        prior_claim != claim_id
                        or prior_sha256 != claim_sha256):
                    raise ValueError(
                        "another thought mind replay claim is pending")
                if state == "applied":
                    applied.add(record_id)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return applied


def _mark_thought_mind_replay_applied_locked(claim):
    """Commit staged page IDs only after mind and store are both durable."""
    records = _thought_mind_replay_records(claim)
    if not records:
        return
    with _thought_mind_replay_catalog() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for table, record_id, claim_id, claim_sha256, queue_id in records:
                row = connection.execute(
                    "SELECT claim_id, claim_sha256, state"
                    + (", queue_id" if table ==
                       "native_thought_mind_replay" else "") + " "
                    f"FROM {table} "
                    "WHERE record_id = ?", (record_id,)).fetchone()
                if row is None:
                    raise ValueError("thought mind replay intent is missing")
                prior_claim, prior_sha256, state = row[:3]
                if not isinstance(prior_claim, str) \
                        or re.fullmatch(r"[0-9a-f]{32}", prior_claim) is None \
                        or not isinstance(prior_sha256, str) \
                        or re.fullmatch(
                            r"[0-9a-f]{64}", prior_sha256) is None \
                        or state not in {"pending", "applied"}:
                    raise ValueError(
                        "thought mind replay journal row is invalid")
                if table == "native_thought_mind_replay" \
                        and row[3] != queue_id:
                    raise ValueError(
                        "thought mind replay queue binding is invalid")
                if state == "applied":
                    continue
                if state != "pending" or prior_claim != claim_id \
                        or prior_sha256 != claim_sha256:
                    raise ValueError("thought mind replay intent is misbound")
                connection.execute(
                    f"UPDATE {table} SET state = ? "
                    "WHERE record_id = ?", ("applied", record_id))
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _clear_thought_mind_replay_scope_locked(table):
    """Clear one finalized scope; unlink the journal only when wholly empty."""
    if table not in {"thought_mind_replay",
                     "native_thought_mind_replay"}:
        raise ValueError("thought mind replay scope is invalid")
    path = _thought_mind_replay_path()
    if not os.path.lexists(path):
        return
    with _thought_mind_replay_catalog() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(f"DELETE FROM {table}")
            remaining = sum(connection.execute(
                f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in ("thought_mind_replay",
                             "native_thought_mind_replay"))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    if remaining:
        return
    _remove_empty_thought_mind_replay_artifacts_locked()


def _remove_empty_thought_mind_replay_artifacts_locked():
    """Unlink an already-empty replay database and its private sidecars."""
    path = _thought_mind_replay_path()
    changed = False
    for suffix in ("", "-journal", "-wal", "-shm"):
        target = path + suffix
        if not os.path.lexists(target):
            continue
        info = os.lstat(target)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError("thought mind replay artifact is invalid")
        os.unlink(target)
        changed = True
    if changed:
        _sync_directory(STATE)


def _clear_legacy_thought_mind_replay_locked():
    _clear_thought_mind_replay_scope_locked("thought_mind_replay")


def _clear_native_thought_mind_replay_locked():
    _clear_thought_mind_replay_scope_locked(
        "native_thought_mind_replay")


def _pending_external_thought_queue_ids():
    """Return a bounded stable view of producers still able to requeue."""
    queue_dir = siaqueue._queue_dir(STATE)
    try:
        queue_info = os.lstat(queue_dir)
    except FileNotFoundError:
        agent_requests, agent_errors = [], []
    else:
        if not stat.S_ISDIR(queue_info.st_mode):
            raise ValueError("agent thought producer is not a directory")
        # ``pending`` owns the queue lease for its bounded snapshot.  Taking
        # the same flock here as well would open a second file description in
        # this process and block forever on our own exclusive lock.
        agent_requests, agent_errors = siaqueue.pending(STATE)
    serious_agent_errors = [
        row for row in agent_errors
        if row.get("error") != "agent queue reached its bounded capacity"]
    if serious_agent_errors:
        raise RuntimeError(
            "agent thought producer snapshot is incomplete")
    pending = {
        record["request_id"] for _path, record, _identity in agent_requests}
    if any(re.fullmatch(r"[0-9a-f]{32}", value) is None
           for value in pending):
        raise ValueError("agent thought producer identity is invalid")

    with _owner_lease(THOUGHT_INBOX_LOCK, "thought inbox"):
        for path in (THOUGHT_INBOX_PATH, _thought_inbox_claim_path()):
            if not os.path.lexists(path):
                continue
            for row in _read_thought_inbox(path):
                pending.add(row["_queue_id"])
    if len(pending) > (siaqueue.MAX_PENDING_REQUESTS
                       + MAX_THOUGHT_INBOX_ITEMS):
        raise ValueError("thought producer identity snapshot exceeds its bound")
    return pending


def _finalize_native_thought_mind_replay(protected_record_ids=()):
    """Retire only applied receipts whose exact producer is durably gone."""
    if not isinstance(protected_record_ids, (set, frozenset, list, tuple)):
        raise ValueError("native thought replay protection is invalid")
    protected = set(protected_record_ids)
    if len(protected) > MAX_THOUGHT_RECOVERY_RECORDS \
            or any(not isinstance(record_id, str)
                   or re.fullmatch(r"[0-9a-f]{64}", record_id) is None
                   for record_id in protected):
        raise ValueError("native thought replay protection is invalid")
    if not os.path.lexists(_thought_mind_replay_path()):
        return
    pending = _pending_external_thought_queue_ids()
    with _owner_lease(_thought_recovery_lock_path(), "thought recovery"):
        path = _thought_mind_replay_path()
        if not os.path.lexists(path):
            return
        with _thought_mind_replay_catalog() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                rows = connection.execute(
                    "SELECT record_id, queue_id, state "
                    "FROM native_thought_mind_replay "
                    "ORDER BY record_id LIMIT ?",
                    (MAX_THOUGHT_RECOVERY_RECORDS + 1,)).fetchall()
                if len(rows) > MAX_THOUGHT_RECOVERY_RECORDS:
                    raise ValueError(
                        "native thought replay journal exceeds its bound")
                for record_id, queue_id, state in rows:
                    if not isinstance(record_id, str) \
                            or re.fullmatch(
                                r"[0-9a-f]{64}", record_id) is None \
                            or not isinstance(queue_id, str) \
                            or (queue_id and re.fullmatch(
                                r"[0-9a-f]{32}", queue_id) is None) \
                            or state not in {"pending", "applied"}:
                        raise ValueError(
                            "native thought replay row is invalid")
                    if state != "applied" and record_id in protected:
                        continue
                    if state != "applied":
                        raise RuntimeError(
                            "native thought replay intent remains pending")
                    if record_id not in protected \
                            and (not queue_id or queue_id not in pending):
                        connection.execute(
                            "DELETE FROM native_thought_mind_replay "
                            "WHERE record_id = ?", (record_id,))
                remaining = sum(connection.execute(
                    f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                    for name in ("thought_mind_replay",
                                 "native_thought_mind_replay"))
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        if not remaining:
            _remove_empty_thought_mind_replay_artifacts_locked()


def _upsert_thought_legacy_catalog(entries):
    canonical = []
    for entry in entries:
        encoded = _thought_legacy_index_bytes(entry).decode("utf-8")
        canonical.append((entry["index_name"], encoded))
    if not canonical:
        return
    with _thought_legacy_catalog() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for name, encoded in canonical:
                row = connection.execute(
                    "SELECT entry_json FROM legacy_thought_index "
                    "WHERE index_name = ?", (name,)).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO legacy_thought_index "
                        "(index_name, entry_json) VALUES (?, ?)",
                        (name, encoded))
                elif row != (encoded,):
                    raise ValueError(
                        "legacy thought catalog identity collision")
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _thought_legacy_catalog_batch(after, limit):
    if not isinstance(after, str) or isinstance(limit, bool) \
            or not isinstance(limit, int) or limit <= 0:
        raise ValueError("legacy thought catalog cursor is invalid")
    with _thought_legacy_catalog() as connection:
        rows = connection.execute(
            "SELECT index_name, entry_json FROM legacy_thought_index "
            "WHERE index_name > ? ORDER BY index_name LIMIT ?",
            (after, limit)).fetchall()
        entries = []
        for name, encoded in rows:
            if not isinstance(name, str) or not isinstance(encoded, str) \
                    or len(encoded.encode("utf-8")) \
                    > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
                raise ValueError("legacy thought catalog row is invalid")
            try:
                entry = json.loads(encoded)
            except (UnicodeError, ValueError, RecursionError) as exc:
                raise ValueError("legacy thought catalog row is malformed") \
                    from exc
            if encoded.encode("utf-8") != _thought_legacy_index_bytes(entry) \
                    or entry["index_name"] != name:
                raise ValueError("legacy thought catalog row is misbound")
            entries.append(entry)
        more = False
        if entries:
            more = connection.execute(
                "SELECT 1 FROM legacy_thought_index "
                "WHERE index_name > ? LIMIT 1",
                (entries[-1]["index_name"],)).fetchone() is not None
    return entries, more


def _load_thought_legacy_scan():
    state = read_state_json(
        _thought_legacy_scan_path(),
        {"schema": THOUGHT_LEGACY_SCAN_SCHEMA,
         "phase": "index", "after": "", "unindexed": 0,
         "indexed": 0, "cookie": 0, "directory": None,
         "discarded": [], "reset_id": None},
        "legacy thought recovery scan")
    return _validated_thought_legacy_scan(state)


def _validated_thought_legacy_scan(state):
    if not isinstance(state, dict) or set(state) != {
            "schema", "phase", "after", "unindexed", "indexed",
            "cookie", "directory", "discarded", "reset_id"} \
            or state.get("schema") != THOUGHT_LEGACY_SCAN_SCHEMA \
            or state.get("phase") \
            not in {"index", "apply", "complete", "reset", "blocked"} \
            or not isinstance(state.get("after"), str) \
            or len(state["after"].encode("utf-8")) \
            > MAX_CORPUS_COMPONENT_BYTES \
            or isinstance(state.get("unindexed"), bool) \
            or not isinstance(state.get("unindexed"), int) \
            or state["unindexed"] < 0 \
            or isinstance(state.get("indexed"), bool) \
            or not isinstance(state.get("indexed"), int) \
            or state["indexed"] < 0 \
            or isinstance(state.get("cookie"), bool) \
            or not isinstance(state.get("cookie"), int) \
            or state["cookie"] < 0:
        raise ValueError("legacy thought recovery scan state is invalid")
    discarded = state.get("discarded")
    if not isinstance(discarded, list) \
            or len(discarded) > MAX_THOUGHT_RECOVERY_RECORDS \
            or any(not isinstance(item, str)
                   or re.fullmatch(r"[0-9a-f]{32}", item) is None
                   for item in discarded) \
            or len(set(discarded)) != len(discarded):
        raise ValueError("legacy thought discarded generations are invalid")
    reset_id = state.get("reset_id")
    if reset_id is not None and (not isinstance(reset_id, str)
                                 or re.fullmatch(
                                     r"[0-9a-f]{32}", reset_id) is None):
        raise ValueError("legacy thought reset identity is invalid")
    directory = _validated_thought_directory_generation(
        state.get("directory"))
    invalid_cursor = (
        (state["phase"] == "index" and bool(state["after"]))
        or (state["phase"] != "index" and bool(state["cookie"]))
        or (state["phase"] in {"apply", "reset"}
            and bool(state["after"])
            and re.fullmatch(
                r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{64}\.json",
                state["after"]) is None)
        or (state["phase"] == "complete"
            and bool(state["after"] or state["indexed"]))
        or (state["phase"] == "reset"
            and bool(state["indexed"] or state["cookie"]
                     or state["unindexed"]))
        or (state["phase"] == "blocked"
            and bool(state["after"] or state["indexed"]
                     or state["cookie"] or state["unindexed"]
                     or directory is not None))
        or (directory is None
            and bool(state["cookie"] or state["indexed"]))
        or (state["phase"] == "reset") != (reset_id is not None)
        or (reset_id is not None
            and (not discarded or discarded[-1] != reset_id)))
    if invalid_cursor:
        raise ValueError("legacy thought recovery scan cursor is invalid")
    return {**state, "directory": directory,
            "discarded": list(discarded), "reset_id": reset_id}


def _save_thought_legacy_scan(state):
    probe = _validated_thought_legacy_scan(dict(state))
    atomic_write(_thought_legacy_scan_path(), json.dumps(
        probe, sort_keys=True, separators=(",", ":"), allow_nan=False))
    os.chmod(_thought_legacy_scan_path(), 0o600)


def _schedule_legacy_thought_reset_locked(state):
    """Persist a new rebuild generation before reporting stale-cookie debt."""
    state = _validated_thought_legacy_scan(state)
    if state["phase"] == "reset":
        return state
    if len(state["discarded"]) >= MAX_THOUGHT_RECOVERY_RECORDS:
        _save_thought_legacy_scan({
            "schema": THOUGHT_LEGACY_SCAN_SCHEMA,
            "phase": "blocked", "after": "", "unindexed": 0,
            "indexed": 0, "cookie": 0, "directory": None,
            "discarded": state["discarded"], "reset_id": None})
        raise ValueError(
            "legacy thought recovery exhausted its reset generation bound")
    reset_id = uuid.uuid4().hex
    reset = {"schema": THOUGHT_LEGACY_SCAN_SCHEMA,
             "phase": "reset", "after": "", "unindexed": 0,
             "indexed": 0, "cookie": 0, "directory": None,
             "discarded": state["discarded"] + [reset_id],
             "reset_id": reset_id}
    _save_thought_legacy_scan(reset)
    return reset


def _archive_legacy_reset_path(source, destination, *, directory):
    """Idempotently rename one stale derived artifact for diagnostics."""
    source_exists = os.path.lexists(source)
    destination_exists = os.path.lexists(destination)
    if source_exists and destination_exists:
        raise ValueError("legacy thought reset artifacts are ambiguous")
    path = source if source_exists else destination
    if not os.path.lexists(path):
        return False
    info = os.lstat(path)
    expected = stat.S_ISDIR(info.st_mode) if directory \
        else stat.S_ISREG(info.st_mode)
    if not expected or info.st_uid != os.geteuid():
        raise ValueError("legacy thought reset artifact is invalid")
    if source_exists:
        os.rename(source, destination)
        return True
    return False


def _execute_legacy_thought_reset_locked(state):
    """Archive one stale derived baseline, then restart at cookie zero.

    The catalog and JSON index are rebuildable derivatives, not authority.
    Re-reading their old page paths would permanently wedge a legitimate
    quiescent delete, rename, or replacement. Immutable active claims are
    handled before reset scheduling, and acknowledged claims already reside in
    both authoritative projections. Preserve those projections, archive the
    stale derivatives for diagnosis, and bind a fresh scan to the directory's
    current generation. Fresh pages still pass the ordinary bounded no-follow,
    exact-metadata, and digest checks before they can produce another claim.
    """
    state = _validated_thought_legacy_scan(state)
    if state["phase"] != "reset":
        return state
    reset_id = state["reset_id"]
    catalog = _thought_legacy_catalog_path()
    catalog_archive = catalog + ".discarded-" + reset_id
    if os.path.lexists(catalog) and os.path.lexists(catalog_archive):
        raise ValueError("legacy thought reset catalogs are ambiguous")
    generation = _current_legacy_thought_directory_generation()
    changed = _archive_legacy_reset_path(
        _thought_legacy_index_dir(),
        _thought_legacy_index_dir() + ".discarded-" + reset_id,
        directory=True)
    changed = _archive_legacy_reset_path(
        catalog, catalog_archive, directory=False) or changed
    for suffix in ("-journal", "-wal", "-shm"):
        changed = _archive_legacy_reset_path(
            catalog + suffix, catalog_archive + suffix,
            directory=False) or changed
    if changed:
        _sync_directory(STATE)
    restarted = {"schema": THOUGHT_LEGACY_SCAN_SCHEMA,
                 "phase": "index", "after": "", "unindexed": 0,
                 "indexed": 0, "cookie": 0, "directory": generation,
                 "discarded": state["discarded"], "reset_id": None}
    _save_thought_legacy_scan(restarted)
    return restarted


def _index_legacy_thought_batch_locked(state):
    directory = os.path.join(CORPUS, "thoughts")
    entries, complete, next_cookie, generation, _inspected = \
        _read_legacy_thought_directory_page(
            directory, state["directory"], state["cookie"],
            MAX_THOUGHT_RECOVERY_RECORDS)
    indexed_entries = []
    unindexed = state["unindexed"]
    for observed in entries:
        name = observed["name"]
        if re.fullmatch(r"[a-z0-9_.-]+\.md", name) is None:
            continue
        if not stat.S_ISREG(observed["mode"]):
            raise ValueError("legacy thought page is not a regular file")
        slug = _canonical_corpus_slug("thoughts/" + name[:-3])
        page_text = _read_thought_page_text(slug)
        metadata = re.findall(r"^sia_thought: (.*)$", page_text, re.M)
        if not metadata:
            # Pre-self-describing pages have no exact record to replay. They
            # are not evidence of a missing signal, so preserve their origin
            # boundary, record the migration diagnostic, and advance only
            # after this page's bounded stable read has completed.
            unindexed += 1
            log(f"legacy thought page lacks recovery metadata: {slug}")
            continue
        record = _decode_exact_thought_page(slug, page_text)
        index_entry = _thought_legacy_index_entry(name, record, page_text)
        _write_thought_legacy_index(index_entry)
        indexed_entries.append(index_entry)
    _upsert_thought_legacy_catalog(indexed_entries)
    _assert_legacy_thought_directory_generation(generation)
    updated = {"schema": THOUGHT_LEGACY_SCAN_SCHEMA,
               "phase": "apply" if complete else "index",
               "after": "", "unindexed": unindexed,
               "indexed": state["indexed"] + len(indexed_entries),
               "cookie": 0 if complete else next_cookie,
               "directory": generation,
               "discarded": state["discarded"], "reset_id": None}
    # The opaque cookie follows every durable JSON index entry and its ordered
    # catalog row. A crash before this write merely revalidates the same
    # content-bound page of entries on retry.
    _save_thought_legacy_scan(updated)
    return updated


def _legacy_thought_claim_locked(state):
    _assert_legacy_thought_directory_generation(state["directory"])
    directory = _thought_legacy_index_dir()
    catalog_entries, more_entries = _thought_legacy_catalog_batch(
        state["after"], MAX_THOUGHT_RECOVERY_RECORDS)
    if not catalog_entries:
        if state["indexed"]:
            raise ValueError("legacy thought catalog lost indexed pages")
        _save_thought_legacy_scan({
            "schema": THOUGHT_LEGACY_SCAN_SCHEMA,
            "phase": "complete", "after": "",
            "unindexed": state["unindexed"], "indexed": 0,
            "cookie": 0, "directory": state["directory"],
            "discarded": state["discarded"], "reset_id": None})
        return None
    if len(catalog_entries) > state["indexed"] \
            or not more_entries \
            and len(catalog_entries) != state["indexed"] \
            or more_entries and len(catalog_entries) >= state["indexed"]:
        raise ValueError("legacy thought catalog count is inconsistent")
    entries = []
    records = []
    total = 0
    admitted_names = []
    for catalog_entry in catalog_entries:
        entry = _read_thought_legacy_index_entry(os.path.join(
            directory, catalog_entry["index_name"]))
        if entry != catalog_entry:
            raise ValueError("legacy thought catalog differs from its index")
        page_text = _read_thought_page_text(entry["slug"])
        page_bytes = len(page_text.encode("utf-8"))
        if page_bytes > MAX_THOUGHT_RECOVERY_BYTES - total:
            more_entries = True
            break
        if hashlib.sha256(page_text.encode("utf-8")).hexdigest() \
                != entry["page_sha256"]:
            raise ValueError("legacy thought page changed after indexing")
        page = _decode_exact_thought_page(entry["slug"], page_text)
        if page["ts"] != entry["ts"]:
            raise ValueError("legacy thought index timestamp is misbound")
        records.append(_thought_recovery_record(page))
        entries.append(entry)
        admitted_names.append(entry["index_name"])
        total += page_bytes
    if not records:
        raise ValueError("legacy thought apply batch cannot make progress")
    _assert_legacy_thought_directory_generation(state["directory"])
    indexed_after = state["indexed"] - len(entries)
    complete = not more_entries and indexed_after == 0
    if not complete and indexed_after <= 0:
        raise ValueError("legacy thought catalog cursor cannot make progress")
    legacy = {"before": state["after"], "after": admitted_names[-1],
              "complete": complete, "entries": entries,
              "unindexed": state["unindexed"],
              "directory": state["directory"],
              "discarded": state["discarded"],
              "indexed_before": state["indexed"],
              "indexed_after": indexed_after}
    return _thought_recovery_claim_document(records, [], legacy)


def _write_thought_recovery_claim_locked(claim):
    encoded = _thought_recovery_claim_bytes(claim)
    path = _thought_recovery_claim_path()
    if os.path.lexists(path):
        existing = _read_thought_recovery_claim()
        if existing != claim:
            raise ValueError("another thought recovery claim is active")
        return existing
    atomic_write(path, encoded.decode("utf-8"))
    os.chmod(path, 0o600)
    return claim


def _prepare_thought_recovery_claim():
    """Create at most one bounded immutable replay generation."""
    if _CORPUS_OWNER_DEPTH.get() <= 0:
        raise RuntimeError("thought recovery requires the corpus owner")
    ensure_durable_directory(STATE, mode=0o700)
    with _owner_lease(_thought_recovery_lock_path(), "thought recovery"):
        existing = _read_thought_recovery_claim()
        if existing is not None:
            return existing
        state = _load_thought_legacy_scan()
        if state["phase"] == "blocked":
            raise RuntimeError(
                "legacy thought recovery is blocked by reset capacity")
        if state["phase"] == "complete":
            # Once this cursor is durable, later native writes are protected by
            # their own pre-page intents and no legacy rescan can reopen a page.
            # The potentially corpus-sized exact replay journal is transient.
            _clear_legacy_thought_mind_replay_locked()
        try:
            if state["phase"] == "reset":
                state = _execute_legacy_thought_reset_locked(state)
                if state["phase"] == "reset":
                    return None
            if state["phase"] == "index":
                state = _index_legacy_thought_batch_locked(state)
                if state["phase"] == "index":
                    return None
            if state["phase"] == "apply":
                claim = _legacy_thought_claim_locked(state)
                if claim is not None:
                    return _write_thought_recovery_claim_locked(claim)
                state = _load_thought_legacy_scan()
        except ThoughtDirectoryGenerationChanged as exc:
            if state["phase"] == "reset":
                _save_thought_legacy_scan({
                    **state, "after": "", "directory": None})
            else:
                _schedule_legacy_thought_reset_locked(state)
            raise RuntimeError(
                "legacy thought directory changed; durable reset scheduled; "
                "retry after corpus writers are quiescent") from exc
        if state["phase"] != "complete":
            raise ValueError("legacy thought recovery did not reach a phase")
        records = _list_thought_recovery_records_locked()
        if not records:
            return None
        claim = _thought_recovery_claim_document(
            records, sorted(record["record_id"] for record in records), None)
        return _write_thought_recovery_claim_locked(claim)


def _thought_recovery_receipt(claim):
    return {"claim_id": claim["claim_id"],
            "payload_sha256": claim["payload_sha256"]}


def _validated_thought_recovery_receipt(target):
    receipt = target.get("thought_recovery")
    if receipt is None:
        return None
    if not isinstance(receipt, dict) or set(receipt) != {
            "claim_id", "payload_sha256"} \
            or not isinstance(receipt.get("claim_id"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", receipt["claim_id"]) is None \
            or not isinstance(receipt.get("payload_sha256"), str) \
            or re.fullmatch(
                r"[0-9a-f]{64}", receipt["payload_sha256"]) is None:
        raise ValueError("thought recovery receipt is invalid")
    return dict(receipt)


def _materialize_thought_recovery_page(record):
    page = record["page"]
    slug = page["slug"]
    try:
        existing = _read_thought_page_text(slug)
    except FileNotFoundError:
        frontmatter, body = _thought_page_parts(page)
        write_page(slug, frontmatter, body)
        existing = _read_thought_page_text(slug)
    durable = _decode_exact_thought_page(slug, existing)
    if durable != page:
        raise ValueError("thought recovery page conflicts with its intent")
    return durable


def _apply_thought_recovery_claim(store, mind, claim):
    """Apply one immutable claim independently to both projections."""
    _thought_recovery_claim_bytes(claim)
    if not isinstance(store, dict) or not isinstance(store.get("thoughts"), list):
        raise ValueError("thought recovery requires a thought store")
    if mind is not None and not isinstance(mind, dict):
        raise ValueError("thought recovery mind must be an object")
    mind_applied = _thought_mind_replay_intent(claim)
    pages = [_materialize_thought_recovery_page(record)
             for record in claim["records"]]
    receipt = _thought_recovery_receipt(claim)
    recovered = reinforced = 0

    if _validated_thought_recovery_receipt(store) != receipt:
        by_slug = {row.get("slug"): row for row in store["thoughts"]
                   if isinstance(row, dict)
                   and isinstance(row.get("slug"), str)}
        by_queue = {row.get("queue_id"): row for row in store["thoughts"]
                    if isinstance(row, dict)
                    and isinstance(row.get("queue_id"), str)}
        for page in pages:
            slug = page["slug"]
            existing = by_slug.get(slug)
            if existing is None and page.get("queue_id"):
                existing = by_queue.get(page["queue_id"])
            if existing is not None:
                comparable = {key: existing.get(key) for key in page
                              if key != "slug"}
                expected = {key: value for key, value in page.items()
                            if key != "slug"}
                if comparable != expected \
                        or existing.get("slug") not in (None, slug):
                    raise RuntimeError(
                        "thought state differs from its recovery page")
                if existing.get("slug") is None:
                    existing["slug"] = slug
                    recovered += 1
                continue
            row = dict(page)
            store["thoughts"].append(row)
            by_slug[slug] = row
            if page.get("queue_id"):
                by_queue[page["queue_id"]] = row
            recovered += 1
        store["thoughts"].sort(
            key=lambda row: (str(row.get("ts", "")),
                             str(row.get("slug", ""))))
        store["thoughts"] = store["thoughts"][
            -MAX_THOUGHT_INBOX_ITEMS:]
        store["thought_recovery"] = receipt

    if mind is not None \
            and _validated_thought_recovery_receipt(mind) != receipt:
        for record, page in zip(claim["records"], pages):
            if record["record_id"] in mind_applied:
                continue
            reinforced += siamind.apply_exact_thought_reinforcement(
                mind, page["links"], _thought_reinforcement_ts(page),
                record["record_id"])
        mind["thought_recovery"] = receipt
    return recovered, reinforced


def _commit_thought_legacy_claim(claim):
    legacy = claim.get("legacy")
    if legacy is None:
        return
    state = _load_thought_legacy_scan()
    expected = {"schema": THOUGHT_LEGACY_SCAN_SCHEMA,
                "phase": "apply", "after": legacy["before"],
                "unindexed": legacy["unindexed"],
                "indexed": legacy["indexed_before"], "cookie": 0,
                "directory": legacy["directory"],
                "discarded": legacy["discarded"], "reset_id": None}
    target = ({"schema": THOUGHT_LEGACY_SCAN_SCHEMA,
               "phase": "complete", "after": "",
               "unindexed": legacy["unindexed"], "indexed": 0,
               "cookie": 0, "directory": legacy["directory"],
               "discarded": legacy["discarded"], "reset_id": None}
              if legacy["complete"] else
              {"schema": THOUGHT_LEGACY_SCAN_SCHEMA,
               "phase": "apply", "after": legacy["after"],
               "unindexed": legacy["unindexed"],
               "indexed": legacy["indexed_after"], "cookie": 0,
               "directory": legacy["directory"],
               "discarded": legacy["discarded"], "reset_id": None})
    if state == target:
        return
    if state != expected:
        raise ValueError("legacy thought scan cursor conflicts with its claim")
    _save_thought_legacy_scan(target)


def _sync_directory(path):
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _acknowledge_thought_recovery_claim(claim):
    """Remove claimed inputs, then the self-contained claim, crash-safely."""
    with _owner_lease(_thought_recovery_lock_path(), "thought recovery"):
        durable = _read_thought_recovery_claim()
        if durable != claim:
            raise ValueError("thought recovery claim changed before acknowledgment")
        active_by_id = {record["record_id"]: record
                        for record in claim["records"]}
        active_directory = _thought_recovery_dir()
        active_changed = False
        for record_id in claim["active_ids"]:
            path = os.path.join(active_directory, record_id + ".json")
            try:
                observed, _identity = _read_thought_recovery_record(path)
            except FileNotFoundError:
                continue
            if observed != active_by_id[record_id]:
                raise ValueError(
                    "thought recovery record changed before acknowledgment")
            os.unlink(path)
            active_changed = True
        if active_changed:
            _sync_directory(active_directory)

        legacy = claim.get("legacy")
        if legacy is not None:
            index_directory = _thought_legacy_index_dir()
            for expected in legacy["entries"]:
                path = os.path.join(index_directory, expected["index_name"])
                try:
                    observed = _read_thought_legacy_index_entry(path)
                except FileNotFoundError:
                    continue
                if observed != expected:
                    raise ValueError(
                        "legacy thought index changed before acknowledgment")
            # Retain canonical JSON/catalog diagnostics through completion.
            # A reset archives these rebuildable derivatives; the exact mind
            # replay journal below, rather than a timestamp maximum or stale
            # page path, decides which earlier records already had effects.
        # Both native and baseline pages require an exact per-record receipt.
        # For native records this deliberately outlives the claim: an inbox
        # or agent request can be retried after this claim is acknowledged but
        # before its producer file is durably removed.
        _mark_thought_mind_replay_applied_locked(claim)

        # The claim contains every replay byte, so partial input deletion is
        # harmless: it remains the authoritative redo record until this last
        # unlink and state-directory fsync both succeed.
        os.unlink(_thought_recovery_claim_path())
        _sync_directory(STATE)


def _thought_recovery_debt():
    """Return a bounded readiness reason under the recovery generation lock."""
    ensure_durable_directory(STATE, mode=0o700)
    with _owner_lease(_thought_recovery_lock_path(), "thought recovery"):
        claim = _read_thought_recovery_claim()
        if claim is not None:
            return "a thought recovery claim is pending"
        records = _list_thought_recovery_records_locked()
        if records:
            return "thought page recovery intents are pending"
        scan = _load_thought_legacy_scan()
        if scan["phase"] != "complete":
            return "legacy thought recovery baseline is pending"
        if os.path.lexists(_thought_mind_replay_path()):
            return "thought mind replay finalization is pending"
    return ""


def _persist_thought(thought):
    """Persist a thought and return the page's exact canonical record."""
    record = _canonical_thought_page_record(thought)
    timestamp = record["ts"]
    kind = record["kind"]
    text = record["text"]
    queue_id = record.get("queue_id")
    dt = timestamp.replace(":", "").replace("-", "")[:13]
    base_slug = (f"thoughts/{timestamp[:10]}-{dt[9:13]}-"
                 f"{kind}")
    slug = base_slug
    if queue_id:
        slug = _queued_thought_slug(queue_id)
        if record.get("slug") not in (None, slug):
            raise ValueError("queued thought state binds a different corpus page")
    elif record.get("slug") is not None:
        slug = record["slug"]
        digest_slug = (base_slug + "-"
                       + hashlib.sha256(text.encode()).hexdigest()[:6])
        if slug != base_slug and re.fullmatch(
                re.escape(digest_slug)
                + r"(?:-(?:[2-9]|[1-9][0-9]+))?", slug) is None:
            raise ValueError("thought state binds a noncanonical corpus page")
    elif page_exists(slug):
        slug += "-" + hashlib.sha256(text.encode()).hexdigest()[:6]
        base, n = slug, 2
        collision_checks = 0
        while page_exists(slug):
            if collision_checks >= MAX_THOUGHT_RECOVERY_RECORDS:
                raise ValueError(
                    "thought page collision search reached its bound")
            collision_checks += 1
            slug = f"{base}-{n}"
            n += 1
    slug = _canonical_corpus_slug(slug)
    page_record = dict(record, slug=slug)
    fm, body = _thought_page_parts(page_record)
    if queue_id:
        try:
            existing = _read_thought_page_text(slug)
        except FileNotFoundError:
            # The content-bound intent is the redo log for both the corpus
            # page and its projections. Capacity refusal precedes page bytes.
            _queue_thought_recovery(page_record)
            write_page(slug, fm, body)
            return page_record
        expected = "---\n" + "\n".join(fm) + "\n---\n" + body
        pre_metadata_fm = [line for line in fm
                           if not line.startswith("sia_thought: ")]
        legacy_fm = [line for line in pre_metadata_fm
                     if not line.startswith("origin: ")]
        pre_metadata_expected = ("---\n" + "\n".join(pre_metadata_fm)
                                 + "\n---\n" + body)
        legacy_expected = ("---\n" + "\n".join(legacy_fm)
                           + "\n---\n" + body)
        if existing in (pre_metadata_expected, legacy_expected):
            # Exact pre-origin page from a crash between page creation and
            # inbox acknowledgement: upgrade only that known byte shape.
            _queue_thought_recovery(page_record)
            write_page(slug, fm, body)
            return page_record
        if existing == expected:
            _queue_thought_recovery(page_record)
            return page_record
        try:
            durable_record = _decode_exact_thought_page(slug, existing)
        except RuntimeError as exc:
            raise ValueError(
                "queued thought path differs from exact request") from exc
        if _thought_queue_binding(durable_record) \
                != _thought_queue_binding(page_record):
            raise ValueError("queued thought identity conflicts with its page")
        _queue_thought_recovery(durable_record)
        return durable_record
    else:
        try:
            existing = _read_thought_page_text(slug)
        except FileNotFoundError:
            _queue_thought_recovery(page_record)
            write_page(slug, fm, body)
            return page_record
        durable_record = _decode_exact_thought_page(slug, existing)
        if durable_record != page_record:
            raise ValueError("thought path differs from its exact record")
        _queue_thought_recovery(durable_record)
    return page_record


def write_thought(thought):
    """Persist one validated, origin-labeled thought corpus page."""
    return _persist_thought(thought)["slug"]


def reconcile_thought_pages(store, mind=None):
    """Prepare and apply one bounded, receipt-guarded recovery generation.

    This compatibility entry point deliberately does not acknowledge the
    immutable claim: only ``_settle_thought_page_signals`` may do that after
    both authoritative state files have reached durable storage.
    """
    def reconcile_owned():
        claim = _prepare_thought_recovery_claim()
        if claim is None:
            return (0, 0)
        return _apply_thought_recovery_claim(store, mind, claim)

    if _CORPUS_OWNER_DEPTH.get() > 0:
        recovered, reinforced = reconcile_owned()
    else:
        with corpus_owner():
            recovered, reinforced = reconcile_owned()
    return (recovered, reinforced) if mind is not None else recovered


# ---------------------------------------------------------------- gbrain

class _FailedRun:
    returncode = -1
    stdout = ""

    def __init__(self, reason="subprocess failed/timed out"):
        self.stderr = str(reason)[:240]


# Alias the JACKAL-exact state ceiling declared above; stdout and stderr share
# this one aggregate budget rather than receiving independent allowances.
MAX_EXTERNAL_OUTPUT_BYTES = MAX_STATE_JSON_BYTES
MAX_GBRAIN_OUTPUT_BYTES = MAX_EXTERNAL_OUTPUT_BYTES


def _run_bounded_text_process(command, *, env, timeout, cwd, pass_fds=(),
                              label="subprocess", output_limit=None):
    """Run one external reader with bounded combined output and descendants.

    stdout and stderr are drained concurrently so neither pipe can deadlock the
    other.  The producer runs in a fresh process group; every exit path removes
    surviving descendants, including the case where the direct parent exits
    after handing a pipe to a child.  Text is admitted only as strict UTF-8.
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
    process = None
    group_reaped = False
    selector = selectors.DefaultSelector()
    streams = {}
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, cwd=cwd,
            pass_fds=tuple(pass_fds), close_fds=True,
            start_new_session=True, text=False)
        if process.stdout is None or process.stderr is None:
            raise RuntimeError("bounded subprocess did not provide output pipes")
        streams = {process.stdout: bytearray(), process.stderr: bytearray()}
        for stream in streams:
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        captured = 0
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            ready = selector.select(remaining)
            if not ready:
                raise subprocess.TimeoutExpired(command, timeout)
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
                streams[stream].extend(block)
                captured += len(block)
        _await_process_exit_unreaped(process, deadline, command, timeout)
        returncode = _signal_and_reap_process_group(
            process, JOURNAL_TIMEOUT_SECONDS)
        group_reaped = True
        if returncode is None:
            raise subprocess.TimeoutExpired(command, timeout)
        stdout = bytes(streams[process.stdout]).decode(
            "utf-8", errors="strict")
        stderr = bytes(streams[process.stderr]).decode(
            "utf-8", errors="strict")
        return subprocess.CompletedProcess(
            command, returncode, stdout=stdout, stderr=stderr)
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
            return json.loads(r.stdout[r.stdout.index("["):] if "[" in r.stdout
                              else r.stdout)
        except Exception:
            try:
                return json.loads(r.stdout[r.stdout.index("{"):])
            except Exception:
                return None
    return r


def _gbrain_call_unlocked(op, params, timeout=120, owner_fd=None):
    """Call one gbrain operation while the caller owns the engine lease."""
    try:
        r = _run_bounded_text_process(
            [GBRAIN, "call", "--source", "sia", op, json.dumps(params)],
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
                return json.loads(out[i:])
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
            chains[name] = (ledger, tool, cmd)
    configured = CONFIG.get("chains", [])
    if not isinstance(configured, list):
        _invalid_chain_binding(
            chains, {"chains_type": type(configured).__name__},
            "chains must be a list")
        return chains
    for c in configured:
        if not isinstance(c, dict):
            _invalid_chain_binding(chains, c,
                                   "chain entry must be an object")
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
            ledger = os.path.expanduser(str(c["ledger"]))
            raw_cmd = c["verify"]
            if not isinstance(raw_cmd, list) or not raw_cmd \
                    or any(not isinstance(a, str) or not a for a in raw_cmd):
                raise ValueError("verify must be a non-empty string argv list")
            cmd = [os.path.expanduser(a) for a in raw_cmd]
            if not cmd:
                raise ValueError("verify argv is empty")
            supplied = c.get("verifier")
            if not isinstance(supplied, str) or not supplied:
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
            if not chain_name or chain_name in chains:
                # Built-ins are reserved and the first valid custom binding
                # owns its name; ambiguity must never shadow a keeper.
                raise ValueError("chain name is reserved or duplicated")
            chains[chain_name] = (ledger, tool, cmd)
        except Exception as exc:
            _invalid_chain_binding(chains, c, str(exc)[:160])
    return chains


def verify_chains():
    """Returns {name: 'pass'|'fail'|'absent'}."""
    out = {}
    for name, (ledger, tool, cmd) in _chain_cmds().items():
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
            # Verifier prose is not an evidence product here; only its exit
            # status is. Never let an operator-supplied verifier accumulate
            # unbounded stdout/stderr inside the resident brainstem.
            r = _run_bounded_text_process(
                cmd, env=None, timeout=60, cwd=None,
                label=f"{name} chain verifier",
                output_limit=MAX_CONFIG_BYTES)
            out[name] = "pass" if r.returncode == 0 else "fail"
        except Exception:
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
        log(f"ledger append failed for {action}: {exc}")
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
MAX_LEDGER_PENDING_RECORDS = 1024
# JACKAL exact: parsed=64*1024, exact=65536; and
# parsed=1024*65536, exact=67108864; parsed=1024*2, exact=2048;
# parsed=2048+1, exact=2049. Exact rational arithmetic outside the Lean
# certificate chain (NOT formal-bounded).
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
    basis = {"order": int(order), "action": str(action),
             "arg1": str(arg1), "arg2": str(arg2),
             "content": str(content)}
    if basis["order"] < 0:
        raise ValueError("ledger recovery order is invalid")
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
        | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
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
        record = json.loads(raw.decode("utf-8"))
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
        order = time.time_ns() if order is None else int(order)
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
        n, h = r.stdout.split()
        return int(n), h
    except Exception:
        return 0, ""


# ---------------------------------------------------------------- thoughts

THOUGHTS_PATH = os.path.join(STATE, "thoughts.json")

def load_thoughts():
    store = read_state_json(
        THOUGHTS_PATH, {"v": 1, "thoughts": []}, "thought store")
    if store.get("v") != 1 or not isinstance(store.get("thoughts"), list) \
            or any(not isinstance(item, dict)
                   for item in store.get("thoughts", [])):
        raise RuntimeError("thought store schema is invalid")
    try:
        for item in store["thoughts"]:
            if "origin" in item:
                item["origin"] = _canonical_thought_origin(item["origin"])
            elif item.get("kind") in {"grade", "ponder", "note"}:
                # These historical kinds are unambiguously model prose.
                # Other unlabeled legacy rows remain unlabeled so readers
                # expose the legacy boundary instead of laundering them as
                # newly classified derived content.
                item["origin"] = "model"
        _validated_thought_recovery_receipt(store)
    except ValueError as exc:
        raise RuntimeError("thought store metadata is invalid") from exc
    return store


def _thought_reinforcement_ts(thought):
    """Return the epoch projection of a canonical thought-page clock."""
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
    # projects this page into daemon-owned mind state at the transaction's
    # settlement boundary.
    log(f"thought[{kind}] {text}")
    return t


def thought_queue_identity(scope, kind, text, links=(), urgent=False,
                           day=None, extra=None):
    """Return a stable queue ID for a deterministic thought projection."""
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
    """Deterministic thought generators. memo persists across pulses."""
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

    # 2. per-organ rules (dedup identical thoughts within a pulse)
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
            t = f"I watched SEKHMET heal the fabric: {ev.summary}."
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

    # 4. salience shift
    if salience:
        top = salience[0].get("slug", "")
        if top and top != memo.get("salience_top") and not top.startswith("thoughts/"):
            previous_top = memo.get("salience_top", "")
            memo["salience_top"] = top
            new.append(generated("attention",
                f"My attention has shifted: the most salient memory is now "
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
# JACKAL status=exact, parsed=3-1, exact=2. Exact rational arithmetic outside
# the Lean certificate chain (NOT formal-bounded). Corpus Markdown has at most
# three path components, hence two directory levels below its root.
MAX_GRAPH_TREE_LEVELS = 2


class GraphProjectionPending(RuntimeError):
    """A bounded graph generation still has durable scan or refusal debt."""


def _graph_projection_state_path():
    return os.path.join(
        os.path.dirname(GRAPH_PATH) or STATE, "graph-projection.json")


def _fresh_graph_projection_state():
    cutoff = iso(utcnow() - datetime.timedelta(days=14))
    return {
        "schema": GRAPH_PROJECTION_SCHEMA,
        "generation": uuid.uuid4().hex,
        "phase": "scan",
        "started_at": iso(),
        "cutoff": cutoff,
        "queue": [{"relative": "", "levels": MAX_GRAPH_TREE_LEVELS,
                   "page": {}}],
        "candidates": [],
        "pages_seen": 0,
        "eligible_seen": 0,
        "failed_ops": [],
    }


def _append_graph_failure(failures, failure):
    """Retain bounded unique refusals plus one stable overflow marker."""
    failure = str(failure)[:MAX_CONFIG_TEXT_CHARS]
    if not failure or failure in failures \
            or "graph_failure_capacity" in failures:
        return
    if len(failures) < MAX_GRAPH_SCAN_ENTRIES:
        failures.append(failure)
        return
    failures[-1] = "graph_failure_capacity"


def _record_graph_failure(state, failure):
    _append_graph_failure(state["failed_ops"], failure)


def _canonical_graph_projection_state(value):
    if not isinstance(value, dict) \
            or value.get("schema") != GRAPH_PROJECTION_SCHEMA \
            or value.get("phase") not in {"scan", "ready"} \
            or not isinstance(value.get("generation"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", value["generation"]) is None \
            or not isinstance(value.get("started_at"), str) \
            or not isinstance(value.get("cutoff"), str) \
            or not isinstance(value.get("queue"), list) \
            or len(value["queue"]) > MAX_GRAPH_DIRECTORY_QUEUE \
            or not isinstance(value.get("candidates"), list) \
            or len(value["candidates"]) > MAX_GRAPH_NODES \
            or isinstance(value.get("pages_seen"), bool) \
            or not isinstance(value.get("pages_seen"), int) \
            or value["pages_seen"] < 0 \
            or isinstance(value.get("eligible_seen"), bool) \
            or not isinstance(value.get("eligible_seen"), int) \
            or value["eligible_seen"] < 0 \
            or not isinstance(value.get("failed_ops"), list) \
            or len(value["failed_ops"]) > MAX_GRAPH_SCAN_ENTRIES:
        raise RuntimeError("graph projection state is invalid")
    try:
        _canonical_utc_timestamp(value["started_at"])
        _canonical_utc_timestamp(value["cutoff"])
    except ValueError as exc:
        raise RuntimeError("graph projection state is invalid") from exc
    queue = []
    for frame in value["queue"]:
        if not isinstance(frame, dict) or set(frame) != {
                "relative", "levels", "page"}:
            raise RuntimeError("graph projection cursor is invalid")
        relative = frame["relative"]
        parts = relative.split("/") if isinstance(relative, str) \
            and relative else []
        if not isinstance(relative, str) or os.path.isabs(relative) \
                or any(part in {"", ".", ".."} for part in parts) \
                or (os.altsep and os.altsep in relative) \
                or isinstance(frame["levels"], bool) \
                or not isinstance(frame["levels"], int) \
                or frame["levels"] < 0 \
                or frame["levels"] > MAX_GRAPH_TREE_LEVELS:
            raise RuntimeError("graph projection cursor is invalid")
        queue.append({"relative": relative, "levels": frame["levels"],
                      "page": _validated_source_page_state(frame["page"])})
    candidates = []
    seen = set()
    for record in value["candidates"]:
        required = {"slug", "type", "title", "updated_at", "origin",
                    "sha256"}
        if not isinstance(record, dict) or set(record) != required \
                or not isinstance(record.get("slug"), str) \
                or not isinstance(record.get("type"), str) \
                or not isinstance(record.get("title"), str) \
                or not isinstance(record.get("updated_at"), str) \
                or not isinstance(record.get("origin"), str) \
                or not isinstance(record.get("sha256"), str) \
                or len(record["type"]) > MAX_SOURCE_NAME_CHARS \
                or re.fullmatch(
                    r"[a-z0-9][a-z0-9._-]*", record["type"]) is None \
                or len(record["title"]) > MAX_SOURCE_NAME_CHARS \
                or record["origin"] not in (
                    THOUGHT_ORIGINS | {"legacy-unlabeled"}) \
                or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None \
                or record["slug"] in seen:
            raise RuntimeError("graph projection candidate is invalid")
        try:
            _canonical_corpus_slug(record["slug"])
            _canonical_utc_timestamp(record["updated_at"])
        except ValueError as exc:
            raise RuntimeError("graph projection candidate is invalid") \
                from exc
        seen.add(record["slug"])
        candidates.append(dict(record))
    failed_ops = []
    for failure in value["failed_ops"]:
        if not isinstance(failure, str) or not failure \
                or len(failure) > MAX_CONFIG_TEXT_CHARS:
            raise RuntimeError("graph projection failure is invalid")
        if failure not in failed_ops:
            failed_ops.append(failure)
    if value["phase"] == "ready" and queue:
        raise RuntimeError("completed graph projection retains a cursor")
    return dict(value, queue=queue, candidates=candidates,
                failed_ops=failed_ops)


def _load_graph_projection_state():
    path = _graph_projection_state_path()
    try:
        value = read_state_json(path, {}, "graph projection")
    except RuntimeError:
        raise
    if not value:
        return _fresh_graph_projection_state()
    state = _canonical_graph_projection_state(value)
    failures = [failure for failure in state["failed_ops"]
                if failure != LEGACY_GRAPH_README_FAILURE]
    if failures != state["failed_ops"]:
        # Older first-light scans recorded the installer-owned root README as
        # refusal debt. It was never a page candidate, so removing only this
        # byte-exact obsolete diagnostic preserves the completed generation.
        state = _save_graph_projection_state(
            dict(state, failed_ops=failures))
    return state


def _save_graph_projection_state(value):
    value = _canonical_graph_projection_state(value)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_STATE_JSON_BYTES:
        raise RuntimeError("graph projection state exceeds its byte bound")
    ensure_durable_directory(os.path.dirname(
        _graph_projection_state_path()))
    atomic_write(_graph_projection_state_path(), encoded)
    return value


def _mark_graph_projection_dirty():
    """Durably restart the conservative corpus baseline before mutation."""
    _save_graph_projection_state(_fresh_graph_projection_state())


def _read_graph_corpus_page(slug):
    """Read and parse one bounded corpus page with a full no-follow walk."""
    slug = _canonical_corpus_slug(slug)
    path = corpus_path(slug)
    fd = _open_source_nofollow(path, os.O_RDONLY)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_size > MAX_EVENT_PAGE_BYTES:
            raise RuntimeError(
                f"graph source is not a bounded regular page: {slug}")
        raw = stream.read(MAX_EVENT_PAGE_BYTES + 1)
        after = os.fstat(stream.fileno())
        try:
            target = _source_path_identity(path, os.O_RDONLY)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"graph source changed while reading: {slug}") from exc
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_EVENT_PAGE_BYTES \
            or (target.st_dev, target.st_ino) != (after.st_dev,
                                                  after.st_ino):
        raise RuntimeError(f"graph source changed while reading: {slug}")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise RuntimeError(f"graph source is not valid UTF-8: {slug}") \
            from exc
    match = FM_RE.match(text)
    frontmatter = match.group(1) if match else ""
    body = text[match.end():] if match else text

    type_values = re.findall(r"^type:\s*(.*?)\s*$", frontmatter, re.M)
    if not type_values:
        page_type = "note"
    elif len(type_values) != 1:
        raise RuntimeError(f"graph source type is ambiguous: {slug}")
    else:
        try:
            page_type = _yaml_scalar(type_values[0])
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"graph source type is invalid: {slug}") \
                from exc
    if len(page_type) > MAX_SOURCE_NAME_CHARS or re.fullmatch(
            r"[a-z0-9][a-z0-9._-]*", page_type) is None:
        raise RuntimeError(f"graph source type is invalid: {slug}")
    title_values = re.findall(r"^title:\s*(.*?)\s*$", frontmatter, re.M)
    title = slug
    if len(title_values) == 1:
        try:
            title = _yaml_scalar(title_values[0])
        except (ValueError, json.JSONDecodeError):
            title = slug
    title = clip(title, MAX_SOURCE_NAME_CHARS)
    origin_values = re.findall(r"^origin:\s*(.*?)\s*$", frontmatter, re.M)
    if len(origin_values) > 1:
        raise RuntimeError(f"graph source origin is ambiguous: {slug}")
    declared_origin = ""
    if origin_values:
        try:
            declared_origin = _yaml_scalar(origin_values[0])
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"graph source origin is invalid: {slug}") \
                from exc
        if declared_origin not in THOUGHT_ORIGINS:
            raise RuntimeError(f"graph source origin is invalid: {slug}")
    updated_at = datetime.datetime.fromtimestamp(
        before.st_mtime, tz=datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
    return {
        "slug": slug,
        "type": page_type,
        "title": title,
        "updated_at": updated_at,
        "origin": siamind.origin_class(
            slug, page_type, declared_origin or None),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }, frontmatter, body


def _admit_graph_candidate(state, record):
    slug = record["slug"]
    if not (record["type"] == "organ" or slug == "sia/cortex"
            or record["updated_at"] >= state["cutoff"]):
        return
    if any(candidate["slug"] == slug for candidate in state["candidates"]):
        raise RuntimeError("graph scan repeated a page in one generation")
    state["eligible_seen"] += 1
    state["candidates"].append(record)
    state["candidates"].sort(
        key=lambda candidate: (
            candidate["type"] == "organ"
            or candidate["slug"] == "sia/cortex",
            candidate["updated_at"], candidate["slug"]),
        reverse=True)
    del state["candidates"][MAX_GRAPH_NODES:]


def _advance_graph_projection(state, limit):
    """Inspect one bounded recursive corpus page and persist its cursor."""
    state = _canonical_graph_projection_state(state)
    if state["phase"] == "ready":
        return state
    queue = collections.deque(state["queue"])
    remaining = limit
    while queue and remaining:
        frame = queue.popleft()
        directory = os.path.join(CORPUS, frame["relative"])
        try:
            entries, complete, inspected, next_page = \
                _bounded_source_entries(
                    directory, frame["page"], remaining,
                    cleanup_legacy_atomic=True)
        except FileNotFoundError:
            failure = ("corpus_root_missing" if not frame["relative"]
                       else "graph_directory_missing:" + frame["relative"])
            _record_graph_failure(state, failure)
            continue
        if next_page.get("reset"):
            # No candidate gathered before a directory-generation change may
            # prove that a page is absent. Restart the complete baseline.
            restarted = _fresh_graph_projection_state()
            _save_graph_projection_state(restarted)
            return restarted
        remaining -= inspected
        if not complete:
            frame["page"] = next_page
            queue.appendleft(frame)
        for entry in entries:
            relative = os.path.join(frame["relative"], entry["name"])
            if stat.S_ISDIR(entry["mode"]):
                if not frame["relative"] and (
                        entry["name"].startswith(".")
                        or entry["name"] == "event-index"):
                    continue
                if frame["levels"] <= 0:
                    failure = "graph_depth_refused:" + relative
                    _record_graph_failure(state, failure)
                    continue
                if len(queue) >= MAX_GRAPH_DIRECTORY_QUEUE:
                    failure = "graph_directory_queue_capacity:" + relative
                    _record_graph_failure(state, failure)
                    continue
                queue.append({"relative": relative,
                              "levels": frame["levels"] - 1,
                              "page": {}})
                continue
            if not entry["name"].endswith(".md"):
                continue
            if not frame["relative"] and entry["name"] == "README.md":
                # The installer-created corpus genesis document describes the
                # repository; it is not a typed memory page and deliberately
                # has no frontmatter or canonical lowercase page slug.
                continue
            if not stat.S_ISREG(entry["mode"]):
                failure = "graph_nonregular_page:" + relative
                _record_graph_failure(state, failure)
                continue
            slug = relative[:-3].replace(os.sep, "/")
            try:
                record, _frontmatter, _body = _read_graph_corpus_page(slug)
            except Exception as exc:
                failure = "graph_page_refused:" + slug + ":" \
                    + str(exc)[:160]
                _record_graph_failure(state, failure)
                continue
            state["pages_seen"] += 1
            _admit_graph_candidate(state, record)
    state["queue"] = list(queue)
    if not queue:
        state["phase"] = "ready"
    return _save_graph_projection_state(state)


def _graph_projection_pages(batch_size=500):
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) \
            or batch_size <= 0 or batch_size > MAX_GRAPH_SCAN_ENTRIES:
        raise ValueError("graph scan batch bound is invalid")
    state = _advance_graph_projection(
        _load_graph_projection_state(), batch_size)
    complete = state["phase"] == "ready" and not state["failed_ops"]
    failure = None
    if state["phase"] != "ready":
        failure = "graph_projection_pending"
    elif state["failed_ops"]:
        failure = state["failed_ops"][0]
    return [dict(record) for record in state["candidates"]], complete, failure


def _graph_projection_debt():
    state = _load_graph_projection_state()
    if state["phase"] != "ready":
        return "bounded graph projection scan is pending"
    if state["failed_ops"]:
        return "graph projection has explicit refusal debt"
    return ""


# gbrain's NER gazetteer deliberately covers its built-in entity types.  SIA
# also has machine-domain entity types (organ/unit/package/project/skill), and
# those are usually referenced explicitly with wikilinks.  The cockpit graph
# is derived from those corpus links rather than from gbrain traversal, so it
# needs to apply the active SIA pack's declared inference regexes itself.
_GAZETTEER_ENTITY_TYPES = frozenset(
    ("person", "company", "organization", "entity"))
_WIKILINK_RE = re.compile(r"\[\[([a-z0-9/._-]+)(?:\|[^\]]*)?\]\]")
_DOMAIN_CONTEXT_MAX_CHARS = 64_000
_DOMAIN_REGEX_MAX_CHARS = 512
_DOMAIN_REGEX_MAX_BOUND = 256
_DOMAIN_REGEX_MAX_OPTIONALS = 16
_DOMAIN_BOUNDED_DOT_RE = re.compile(r"\.\{([0-9]+),([0-9]+)\}")
# JACKAL status=exact: parsed=1024*64, exact=65536; parsed=16*256,
# exact=4096. Exact rational arithmetic outside the Lean certificate chain
# (NOT formal-bounded).
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


def _yaml_scalar(value):
    """Decode the small YAML scalar subset used by SIA's pack manifest."""
    value = value.strip()
    if value.startswith('"'):
        try:
            decoded = json.loads(value)
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise ValueError("quoted scalar is malformed") from exc
    elif value.startswith("'"):
        if not value.endswith("'"):
            raise ValueError("unterminated quoted schema-pack scalar")
        decoded = value[1:-1].replace("''", "'")
    else:
        decoded = value.split(" #", 1)[0].strip()
    if not isinstance(decoded, str) or not decoded:
        raise ValueError("empty schema-pack scalar")
    return decoded


def _sia_schema_pack_path(pack_path=None):
    if pack_path:
        return pack_path
    candidates = [
        os.environ.get("SIA_SCHEMA_PACK", ""),
        os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "schema-pack", "pack.yaml")),
        os.path.join(SHARE, ".gbrain/schema-packs/sia-pack/pack.yaml"),
    ]
    for path in candidates:
        # Select without following the final component. The authoritative
        # opener below decides whether the candidate is an admissible file;
        # a present but unsafe override must refuse instead of falling through.
        if path and os.path.lexists(path):
            return path
    raise FileNotFoundError("SIA schema pack not found")


def _read_owned_stable_lines(path, *, max_bytes, max_lines,
                             max_line_bytes, label):
    """Read one owned regular text file without following or streaming it."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_mode & 0o022 \
                or before.st_size > max_bytes:
            raise ValueError(
                f"{label} is not an owned bounded regular file")
        raw = stream.read(max_bytes + 1)
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
            raise ValueError(f"{label} changed while read")
        current = (rebound.st_dev, rebound.st_ino, rebound.st_size,
                   rebound.st_mtime_ns, rebound.st_ctime_ns)
    except OSError as exc:
        raise ValueError(f"{label} changed while read") from exc
    if observed != finished or current != observed or len(raw) > max_bytes:
        raise ValueError(f"{label} changed or exceeded its byte limit")
    # maxsplit bounds the temporary object count even for an all-newline file.
    raw_lines = raw.split(b"\n", max_lines)
    if raw_lines and raw_lines[-1] == b"":
        raw_lines.pop()
    if len(raw_lines) > max_lines:
        raise ValueError(f"{label} exceeds its line limit")
    lines = []
    for raw_line in raw_lines:
        if len(raw_line) > max_line_bytes:
            raise ValueError(f"{label} exceeds its line-width limit")
        try:
            lines.append(raw_line.decode("utf-8", errors="strict"))
        except UnicodeError as exc:
            raise ValueError(f"{label} contains invalid UTF-8") from exc
    return tuple(lines)


def _validate_domain_regex(pattern, rule_name):
    """Admit a deliberately finite regex subset with no unbounded repeat.

    The active SIA pack needs literals, alternation, one-level groups,
    optionals, and a small bounded ``.{m,n}`` window.  Rejecting every other
    Python-regex construct keeps matching linear in the bounded context and
    avoids treating a heuristic catastrophic-backtracking detector as a
    proof of safety.
    """
    if len(pattern) > _DOMAIN_REGEX_MAX_CHARS:
        raise ValueError(f"unsafe domain regex for {rule_name}: too long")
    if "(?" in pattern or any(char in pattern for char in "*+[]^$\\"):
        raise ValueError(
            f"unsafe domain regex for {rule_name}: unsupported or unbounded construct")
    if pattern.count("?") > _DOMAIN_REGEX_MAX_OPTIONALS or "??" in pattern:
        raise ValueError(
            f"unsafe domain regex for {rule_name}: excessive optionals")
    depth = 0
    for char in pattern:
        if char == "(":
            depth += 1
            if depth > 1:
                raise ValueError(
                    f"unsafe domain regex for {rule_name}: nested groups")
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError(
                    f"unsafe domain regex for {rule_name}: unbalanced group")
    if depth:
        raise ValueError(
            f"unsafe domain regex for {rule_name}: unbalanced group")

    def check_bound(match):
        lower, upper = int(match.group(1)), int(match.group(2))
        if lower > upper or upper > _DOMAIN_REGEX_MAX_BOUND:
            raise ValueError(
                f"unsafe domain regex for {rule_name}: invalid bound")
        return "."

    without_bounds = _DOMAIN_BOUNDED_DOT_RE.sub(check_bound, pattern)
    if "{" in without_bounds or "}" in without_bounds:
        raise ValueError(
            f"unsafe domain regex for {rule_name}: unsupported bound")


def load_domain_edge_spec(pack_path=None):
    """Load SIA entity types and every declared link inference regex.

    This is intentionally a narrow manifest reader, not a second YAML
    implementation: it accepts the validated pack's sequence-of-maps shape
    and decodes only `name`, `primitive`, and `inference.regex`.  Patterns are
    restricted to SIA's finite, no-unbounded-repeat subset; rejected or
    malformed rules fail the typed layer closed. export_graph then retains the
    underlying `mentions` edges and marks the snapshot partial.
    """
    path = _sia_schema_pack_path(pack_path)
    section = current_name = None
    entity_types = set(_GAZETTEER_ENTITY_TYPES)
    rules, seen_rules = [], set()
    lines = _read_owned_stable_lines(
        path, max_bytes=MAX_SCHEMA_PACK_BYTES,
        max_lines=MAX_SCHEMA_PACK_LINES,
        max_line_bytes=MAX_SCHEMA_PACK_LINE_BYTES,
        label="SIA schema pack")
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            section = stripped[:-1] if stripped.endswith(":") else None
            current_name = None
            continue
        if section not in ("page_types", "link_types"):
            continue
        if indent == 2 and stripped.startswith("- name:"):
            current_name = _yaml_scalar(stripped.split(":", 1)[1])
            continue
        if not current_name:
            continue
        if section == "page_types" and indent == 4 and \
                stripped.startswith("primitive:"):
            primitive = _yaml_scalar(stripped.split(":", 1)[1])
            if primitive == "entity":
                if current_name not in entity_types \
                        and len(entity_types) >= MAX_DOMAIN_ENTITY_TYPES:
                    raise ValueError(
                        "SIA schema pack exceeds its entity-type limit")
                entity_types.add(current_name)
            continue
        if section == "link_types" and indent == 6 and \
                stripped.startswith("regex:"):
            if current_name in seen_rules:
                raise ValueError(
                    f"duplicate inference regex for {current_name}")
            if len(rules) >= MAX_DOMAIN_EDGE_RULES:
                raise ValueError(
                    "SIA schema pack exceeds its inference-rule limit")
            pattern = _yaml_scalar(stripped.split(":", 1)[1])
            _validate_domain_regex(pattern, current_name)
            try:
                compiled = re.compile(pattern)
            except re.error as e:
                raise ValueError(
                    f"invalid inference regex for {current_name}: {e}") from e
            seen_rules.add(current_name)
            rules.append((current_name, compiled))
    if not rules:
        raise ValueError("SIA schema pack declares no inference regexes")
    return tuple(rules), frozenset(entity_types)


def _relation_context(body, link_match, inherit_link_only=False):
    """Return the Markdown record governing one explicit wikilink.

    Generated event records are one line, so a leading verb still governs the
    last member of a long package list.  Thought pages put their evidence links
    on a link-only line; for those, inherit the nearest preceding prose line.
    Headings never supply a relation.
    """
    line_start = body.rfind("\n", 0, link_match.start()) + 1
    line_end = body.find("\n", link_match.end())
    if line_end < 0:
        line_end = len(body)
    line = body[line_start:line_end]
    if line.lstrip().startswith("#"):
        return ""
    masked = _WIKILINK_RE.sub(" ", line)
    if any(ch.isalnum() for ch in masked):
        return line
    if not inherit_link_only:
        return line

    cursor = line_start
    while cursor > 0:
        previous_end = cursor - 1
        previous_start = body.rfind("\n", 0, previous_end) + 1
        previous = body[previous_start:previous_end]
        cursor = previous_start
        if not previous.strip():
            continue
        if previous.lstrip().startswith("#"):
            return line
        return previous + "\n" + line
    return line


def _infer_domain_link_type(context, rules):
    # Link targets and display aliases are entity identity, not evidence of a
    # relation.  Masking them prevents names such as `diagnose-crash` from
    # manufacturing a `crashed` edge to every neighbor in the same record.
    scan = _WIKILINK_RE.sub(" ", context)
    if len(scan) > _DOMAIN_CONTEXT_MAX_CHARS:
        return "mentions"
    for name, pattern in rules:
        if pattern.search(scan):
            return name
    return "mentions"


def _suppress_shadowed_mentions(edges):
    """Drop generic edges when the same directed pair has typed evidence."""
    typed_pairs = {
        (edge.get("from_slug"), edge.get("to_slug"))
        for edge in edges
        if edge.get("link_type", "mentions") != "mentions"
    }
    return [
        edge for edge in edges
        if edge.get("link_type", "mentions") != "mentions"
        or (edge.get("from_slug"), edge.get("to_slug")) not in typed_pairs
    ]


def _iter_corpus_link_edges(canonical_slugs, rules, source_digests,
                            target_slugs=None):
    """Yield stable link occurrences from a fixed selected-page generation."""
    for slug in canonical_slugs:
        record, fmtext, body = _read_graph_corpus_page(slug)
        expected_digest = source_digests.get(slug)
        if expected_digest is None:
            source_digests[slug] = record["sha256"]
        elif not isinstance(expected_digest, str) \
                or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None \
                or record["sha256"] != expected_digest:
            raise RuntimeError(
                f"graph source changed after selection: {slug}")
        page_type = record["type"]
        if page_type == "take":
            # The prediction and its operator-approved structural links
            # precede the canonical grade heading. Everything after it may
            # include legacy model prose and never participates in the graph.
            body = body.split("\n## Grade · ", 1)[0]
        tagm = re.search(r"^tags:\s*\[(.*)\]\s*$", fmtext, re.M)
        tags = ({t.strip() for t in tagm.group(1).split(",")}
                if tagm else set())
        origin_values = re.findall(r"^origin:\s*(.*?)\s*$", fmtext, re.M)
        try:
            page_origin = (_yaml_scalar(origin_values[0])
                           if len(origin_values) == 1 else "")
        except (ValueError, json.JSONDecodeError):
            page_origin = ""
        trusted_thought = (page_type == "thought"
                           and page_origin == "derived"
                           and bool(tags & _DOMAIN_THOUGHT_KINDS))
        inherit_link_only = trusted_thought
        page_rules = (rules if page_type in _DOMAIN_EVIDENCE_PAGE_TYPES
                      or trusted_thought else ())
        for lm in _WIKILINK_RE.finditer(body):
            target = lm.group(1)
            if target_slugs is not None and target not in target_slugs:
                continue
            lo = max(0, lm.start() - 45)
            why = re.sub(r"\s+", " ",
                         body[lo:lm.end() + 45]).strip()[:90]
            link_type = _infer_domain_link_type(
                _relation_context(body, lm, inherit_link_only), page_rules)
            yield {"from_slug": slug, "to_slug": target,
                   "link_type": link_type, "context": why}


def corpus_edges(rules=None, entity_types=None, slugs=None,
                 source_digests=None, include_omissions=False,
                 target_slugs=None):
    """Extract bounded edges from the already-selected cockpit window.

    With no explicit ``slugs`` this advances the durable graph baseline once
    and proceeds only if that bounded generation is complete.  It never walks
    or materializes the whole corpus merely to discard most pages afterward.
    Each selected page is opened no-follow, byte-bounded, and optionally bound
    to the digest observed by the selection pass.  Edge retention is a
    deterministic cockpit display window.  With an explicit ``target_slugs``
    window, duplicates, out-of-window targets, and generic mentions shadowed by
    typed relations are resolved before the cap; ``include_omissions`` then
    returns ``(edges, omitted_count)`` for exact unique display edges.
    """
    if rules is None or entity_types is None:
        rules, entity_types = load_domain_edge_spec()
    if slugs is None:
        pages, complete, failure = _graph_projection_pages(
            MAX_GRAPH_SCAN_ENTRIES)
        if not complete:
            raise GraphProjectionPending(
                failure or "graph projection baseline is incomplete")
        slugs = [page["slug"] for page in pages]
        source_digests = {page["slug"]: page["sha256"] for page in pages}
    if not isinstance(slugs, (list, tuple, set)) \
            or len(slugs) > MAX_GRAPH_NODES:
        raise ValueError("graph edge source window exceeds its bound")
    if not isinstance(include_omissions, bool):
        raise ValueError("graph edge omission mode is invalid")
    try:
        rules = tuple(rules)
    except TypeError as exc:
        raise ValueError("graph edge rules are invalid") from exc
    if len(rules) > MAX_DOMAIN_EDGE_RULES:
        raise ValueError("graph edge rules exceed their bound")
    canonical_slugs = []
    for slug in slugs:
        slug = _canonical_corpus_slug(slug)
        if slug in canonical_slugs:
            continue
        canonical_slugs.append(slug)
    canonical_slugs.sort()
    source_digests = source_digests or {}
    if not isinstance(source_digests, dict):
        raise ValueError("graph source digest map is invalid")
    observed_digests = dict(source_digests)
    if target_slugs is None:
        typed_edges, mention_edges = [], []
        omitted_edges = 0
        for edge in _iter_corpus_link_edges(
                canonical_slugs, rules, observed_digests):
            if len(typed_edges) + len(mention_edges) >= MAX_GRAPH_EDGES:
                omitted_edges += 1
                continue
            (typed_edges if edge["link_type"] != "mentions"
             else mention_edges).append(edge)
        retained = _suppress_shadowed_mentions(typed_edges + mention_edges)
        if include_omissions:
            return retained, omitted_edges
        return retained

    if not isinstance(target_slugs, (list, tuple, set)) \
            or len(target_slugs) > MAX_GRAPH_NODES:
        raise ValueError("graph edge target window exceeds its bound")
    allowed_targets = {_canonical_corpus_slug(slug) for slug in target_slugs}
    if len(allowed_targets) != len(target_slugs) \
            or not set(canonical_slugs) <= allowed_targets:
        raise ValueError("graph edge target window is invalid")
    relation_names = ["mentions"]
    for name, _pattern in rules:
        if not isinstance(name, str) or name in relation_names:
            raise ValueError("graph edge relation identities are invalid")
        relation_names.append(name)

    # First establish typed pairs. The set has at most one entry per directed
    # pair in the already capped node window.
    typed_pairs = set()
    for edge in _iter_corpus_link_edges(
            canonical_slugs, rules, observed_digests, allowed_targets):
        if edge["link_type"] != "mentions":
            typed_pairs.add((edge["from_slug"], edge["to_slug"]))

    node_names = sorted(allowed_targets)
    node_index = {slug: index for index, slug in enumerate(node_names)}
    relation_index = {
        relation: index for index, relation in enumerate(relation_names)}
    slots = len(node_names) * len(node_names) * len(relation_names)
    seen = bytearray((slots + 7) // 8)
    retained, omitted_edges = [], 0
    for edge in _iter_corpus_link_edges(
            canonical_slugs, rules, observed_digests, allowed_targets):
        source, target = edge["from_slug"], edge["to_slug"]
        relation = edge["link_type"]
        if relation == "mentions" and (source, target) in typed_pairs:
            continue
        slot = ((node_index[source] * len(node_names) + node_index[target])
                * len(relation_names) + relation_index[relation])
        byte_index, bit_index = divmod(slot, 8)
        mask = 1 << bit_index
        if seen[byte_index] & mask:
            continue
        seen[byte_index] |= mask
        if len(retained) < MAX_GRAPH_EDGES:
            retained.append(edge)
        else:
            omitted_edges += 1
    if include_omissions:
        return retained, omitted_edges
    return retained


def _graph_display_nodes(pages):
    """Select the deterministic capped cockpit node window."""
    cutoff = iso(utcnow() - datetime.timedelta(days=14))
    keep = {}
    for page in pages:
        slug = page.get("slug", "")
        page_type = page.get("type", "note")
        recent = (page.get("updated_at") or "") >= cutoff
        if page_type in ("organ",) or slug == "sia/cortex" or recent:
            keep[slug] = {
                "id": slug, "t": page_type,
                "title": page.get("title", slug),
                "ts": page.get("updated_at", ""),
                "origin": (page["origin"]
                           if isinstance(page.get("origin"), str)
                           else corpus_origin(slug, page_type)),
                "deg": 0, "din": 0, "dout": 0,
            }
    aged_out = len(pages) - len(keep)
    truncated = 0
    if len(keep) > MAX_GRAPH_NODES:
        organs = {slug: node for slug, node in keep.items()
                  if node["t"] == "organ"}
        rest = sorted(
            (node for node in keep.values() if node["t"] != "organ"),
            key=lambda node: (node["ts"], node["id"]), reverse=True)[
                :max(0, MAX_GRAPH_NODES - len(organs))]
        truncated = len(keep) - len(organs) - len(rest)
        keep = {**organs, **{node["id"]: node for node in rest}}
    return keep, aged_out, truncated


def export_graph(require_complete=True):
    """Graph snapshot v2 — carries its own truth boundary (the snapshot
    block says what is complete, what was truncated, and which reads
    failed), per-node in/out degrees, and per-edge type + extraction
    context so the panel can answer 'why does this connection exist'.
    Edges come from the corpus itself (see corpus_edges)."""
    failed_ops = []
    pages, pages_complete, page_failure = gbrain_all_pages()
    if not pages_complete:
        _append_graph_failure(failed_ops, page_failure or "list_pages")
    keep, aged_out, truncated = _graph_display_nodes(pages)
    try:
        rules, entity_types = load_domain_edge_spec()
    except Exception:
        _append_graph_failure(failed_ops, "domain_link_rules")
        rules, entity_types = (), _GAZETTEER_ENTITY_TYPES
    try:
        # Defend the exported invariant even when another edge provider is
        # substituted for corpus_edges.
        selected_slugs = sorted(keep)
        source_digests = {
            page["slug"]: page["sha256"] for page in pages
            if isinstance(page, dict)
            and isinstance(page.get("slug"), str)
            and isinstance(page.get("sha256"), str)}
        edge_projection = corpus_edges(
            rules, entity_types, selected_slugs, source_digests, True,
            selected_slugs)
        # Preserve the substitution seam used by embedders that supplied a
        # pre-cap edge provider before omission accounting was added.
        if isinstance(edge_projection, tuple):
            if len(edge_projection) != 2:
                raise ValueError("graph edge projection result is invalid")
            paths, omitted_edges = edge_projection
        else:
            paths, omitted_edges = edge_projection, 0
        if isinstance(omitted_edges, bool) \
                or not isinstance(omitted_edges, int) \
                or omitted_edges < 0:
            raise ValueError("graph edge omission count is invalid")
        paths = _suppress_shadowed_mentions(paths)
    except Exception:
        _append_graph_failure(failed_ops, "corpus_edges")
        paths = []
        omitted_edges = 0
    edges, eseen = [], set()
    for e in paths:
        s, d = e.get("from_slug"), e.get("to_slug")
        relation = e.get("link_type", "mentions")
        if s in keep and d in keep and (s, d, relation) not in eseen:
            eseen.add((s, d, relation))
            why = re.sub(r"\s+", " ", str(e.get("context") or "")).strip()[:90]
            edges.append({"s": s, "d": d,
                          "t": relation, "why": why})
            keep[s]["deg"] += 1; keep[s]["dout"] += 1
            keep[d]["deg"] += 1; keep[d]["din"] += 1
    counts = {}
    for v in keep.values():
        counts[v["t"]] = counts.get(v["t"], 0) + 1
    pages_total = len(pages)
    try:
        projection = _load_graph_projection_state()
        projected_slugs = {record["slug"]
                           for record in projection["candidates"]}
        if projected_slugs == set(keep) or projected_slugs == {
                page.get("slug") for page in pages
                if isinstance(page, dict)}:
            pages_total = projection["pages_seen"]
            aged_out = max(
                aged_out,
                projection["pages_seen"] - projection["eligible_seen"])
            truncated = max(
                truncated,
                projection["eligible_seen"]
                - len(projection["candidates"]))
            for failure in projection["failed_ops"]:
                _append_graph_failure(failed_ops, failure)
    except Exception as exc:
        _append_graph_failure(
            failed_ops, "graph_projection_state:" + str(exc)[:120])
    graph = {"v": 2, "ts": iso(),
             "nodes": sorted(keep.values(), key=lambda n: n["id"]),
             "edges": edges,
             "pages_total": pages_total,
             "pages_total_complete": pages_complete,
             "snapshot": {"complete": not failed_ops,
                          "truncated": truncated,
                          "omitted_nodes": truncated,
                          "omitted_edges": omitted_edges,
                          "omissions_imply_absence": False,
                          "aged_out": aged_out,
                          "counts_by_kind": counts,
                          "failed_ops": failed_ops,
                          "window_days": 14}}
    atomic_write(GRAPH_PATH, json.dumps(graph))
    if require_complete and not graph["snapshot"]["complete"]:
        reason = ", ".join(graph["snapshot"]["failed_ops"][:3]) \
            or "graph snapshot is partial"
        raise GraphProjectionPending(reason)
    return len(keep), len(edges), pages_total


def _export_graph_publication():
    """Require a complete graph and drain its bounded durable cursor.

    Corpus mutation conservatively restarts the projection. Returning after
    only one directory page would make an active corpus larger than that page
    alternate forever between recovery and new publication debt. Keep the
    corpus lease, advance independently bounded pages, and retain a finite
    aggregate ceiling for churn or an unexpectedly large tree.
    """
    attempts = 0
    while True:
        try:
            return export_graph()
        except GraphProjectionPending:
            state = _load_graph_projection_state()
            if state["phase"] == "ready":
                raise
            attempts += 1
            if attempts >= MAX_EVENT_LOOKUP_PAGES:
                raise GraphProjectionPending(
                    "graph publication exceeded its generation "
                    "ceiling") from None


def export_status(st):
    atomic_write(STATUS_PATH, json.dumps(st))


def export_thoughts(store):
    atomic_write(THOUGHTS_PATH, json.dumps(store))


# ---------------------------------------------------------------- pulse

MEMO_PATH = os.path.join(STATE, "memo.json")
MAX_MEMO_BYTES = 16_777_216
MAX_SOURCE_REPLAY_EVENTS = 65_536
MAX_SOURCE_REPLAY_SOURCES = 2001
# JACKAL status=exact, parsed=4*1024*1024, exact=4194304. Exact rational
# arithmetic outside the Lean certificate chain (NOT formal-bounded).
MAX_SOURCE_REPLAY_RECORD_BYTES = 4_194_304
# A legacy trend may contain more history than the current cockpit window,
# but every pulse still admits only a finite source. JACKAL status=exact:
# parsed=4*1024*1024, exact=4194304; parsed=16*256, exact=4096;
# parsed=1024*64, exact=65536. Exact rational arithmetic outside the Lean
# certificate chain (NOT formal-bounded).
MAX_BENCH_TREND_BYTES = 4_194_304
MAX_BENCH_TREND_INPUT_LINES = 4_096
MAX_BENCH_TREND_LINE_BYTES = 65_536
MAX_BENCH_TREND_ROWS = 30


def load_memo():
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    try:
        fd = os.open(MEMO_PATH, flags)
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise RuntimeError(f"brainstem memo cannot be opened safely: {exc}") \
            from exc
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_size > MAX_MEMO_BYTES:
            raise RuntimeError("brainstem memo is not a bounded regular file")
        raw = stream.read(MAX_MEMO_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_MEMO_BYTES:
        raise RuntimeError("brainstem memo changed while read")
    try:
        value = json.loads(raw)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise RuntimeError("brainstem memo is unreadable or malformed") \
            from exc
    if not isinstance(value, dict):
        raise RuntimeError("brainstem memo must be an object")
    return value


def _memo_text(value):
    encoded = json.dumps(value)
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
            or receipt.get("v") != 1 \
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
    """Publish evidence offsets only after corresponding mind state saves."""
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
    try:
        # The migrator holds this same lease from its first marker write
        # through PGLite/graph reconciliation.  Reading both the marker and
        # take store under one lease prevents a false-ready TOCTOU snapshot.
        with corpus_owner():
            memo = load_memo()
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
                return False, consolidation_debt
            source_pending = _pending_source_replay_marker(memo)
            if source_pending is not None:
                return False, "evidence source replay is pending"
            thought_debt = _thought_recovery_debt()
            if thought_debt:
                return False, thought_debt
            if sync_needed:
                return False, "a corpus publication is still pending"
            graph_debt = _graph_projection_debt()
            if graph_debt:
                return False, graph_debt
            if _ready_receipt(memo) is None:
                return False, "no successful memory publication is recorded"
            mind_state = siamind.load_mind()
            if mind_state.get("event_applied") \
                    or mind_state.get("event_batch_applied") is not None:
                return False, "evidence cursor replay guard is pending"
            if _pending_dream_unit(mind_state) is not None:
                return False, "a DREAM mind transition is pending recovery"
            if siatakes.natural_history_recovery_required():
                return False, "a take/intent projection transaction is pending recovery"
            if siatakes.grade_recovery_required():
                return False, "a signed grade transaction is pending recovery"
            if siatakes.take_migration_required():
                return False, "legacy model-grade provenance migration is pending"
            if siatakes.intent_history_required():
                return False, "legacy intent history projection is pending"
    except Exception as exc:
        return False, f"memory readiness check refused: {exc}"
    return True, ""


def _read_existing_agent_note(slug):
    """Read one deterministic note page through a bounded stable handle."""
    slug = _canonical_corpus_slug(slug)
    path = corpus_path(slug)
    fd = _open_source_nofollow(path, os.O_RDONLY)
    with os.fdopen(fd, "rb") as stream:
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


def materialize_agent_notes(store):
    """Materialize valid agent-note requests without acknowledging them.

    The caller acknowledges returned paths only after corpus commit and gbrain
    sync succeed. Existing deterministic pages make retry idempotent if a
    daemon dies after writing but before acknowledgment.
    """
    requests, queue_errors = siaqueue.pending(STATE)
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


def acknowledge_agent_notes(paths, commit_status, synced):
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
            acknowledged += 1
        except Exception as exc:
            errors.append({"file": os.path.basename(path),
                           "error": str(exc)})
    return acknowledged, errors

def coincidence_findings(mind, findings, now=None):
    """Cross-organ coincidence: two or more DISTINCT organs spiking
    out-of-band in the same detection window is itself an observation
    worth a thought. Deterministic, and scrupulously causal-free: the
    thought states the coincidence and the sighting count, never a
    cause. Pair history accumulates in mind['coincide'] — the ground a
    future (measured) hypothesis lane would build on."""
    spikes = {o: t for o, k, t in findings if k == "spike"}
    spiked = sorted(spikes)
    if len(spiked) < 2:
        return []
    now = now or time.time()
    co = mind.setdefault("coincide", {})

    def _counts(organ):
        # pull "produced X events … (previous max Y)" out of the spike
        # text so the coincidence thought states both counts verbatim
        m = re.search(r"produced (\d+) events.*previous max (\d+)",
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
                f"out-of-band in the same window — {nth} sighting of "
                f"this pair. I state the coincidence, not a cause.",
                [f"organs/{spiked[i]}", f"organs/{spiked[j]}"]))
    return out[:2]                      # cap per pulse; pairs still counted


def _event_transition_receipt(value, batch_identity):
    """Validate the bounded thought/finding projection bound to a mind batch."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
            "id", "novelty_thoughts", "findings", "coincidences"} \
            or value.get("id") != batch_identity:
        raise RuntimeError("event cognitive transition receipt is invalid")
    collections_to_bound = (
        value.get("novelty_thoughts"), value.get("findings"),
        value.get("coincidences"))
    if any(not isinstance(items, list)
           or len(items) > MAX_SOURCE_REPLAY_EVENTS
           for items in collections_to_bound):
        raise RuntimeError("event cognitive transition receipt is invalid")
    for item in value["novelty_thoughts"]:
        if not isinstance(item, list) or len(item) != 4 \
                or not all(isinstance(field, str)
                           for field in (item[0], item[1], item[3])) \
                or len(item[1]) > MAX_THOUGHT_INBOX_TEXT \
                or not isinstance(item[2], list) \
                or any(_canonical_corpus_slug(link) != link
                       for link in item[2]) \
                or re.fullmatch(r"[0-9a-f]{32}", item[3]) is None:
            raise RuntimeError("event cognitive transition receipt is invalid")
    for item in value["findings"]:
        if not isinstance(item, list) or len(item) != 3 \
                or not all(isinstance(field, str) for field in item) \
                or any(len(field) > MAX_THOUGHT_INBOX_TEXT for field in item):
            raise RuntimeError("event cognitive transition receipt is invalid")
    for item in value["coincidences"]:
        if not isinstance(item, list) or len(item) != 2 \
                or not isinstance(item[0], str) \
                or len(item[0]) > MAX_THOUGHT_INBOX_TEXT \
                or not isinstance(item[1], list) \
                or any(_canonical_corpus_slug(link) != link
                       for link in item[1]):
            raise RuntimeError("event cognitive transition receipt is invalid")
    return value


def _event_cognitive_transition(
        mind, admitted_events, now_ts, day, source_batch_identity):
    """Apply one exact source batch to a private mind candidate.

    The caller runs this before source staging and later persists this same
    admitted candidate. Corpus thoughts are returned as inert specifications;
    this function itself has no corpus or queue side effects.
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
            "event cognitive transition receipt has no batch replay guard")
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
    """Select and deduplicate the exact observations that may change mind."""
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
        | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
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
            record = json.loads(line)
            date = record.get("date")
            metric = record.get("slug_match_at_5_blend")
            if metric is None:
                metric = record.get("hit5_blend")
            if (not isinstance(date, str)
                    or re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) is None
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
    """Run one whole heartbeat under the corpus transaction lease."""
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
    if not isinstance(effects["day"], str) \
            or re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}", effects["day"]) is None \
            or isinstance(effects["events_pulse"], bool) \
            or not isinstance(effects["events_pulse"], int) \
            or effects["events_pulse"] < 0 \
            or not isinstance(effects["organs"], dict):
        raise RuntimeError("pulse publication effects are invalid")
    for organ, state in effects["organs"].items():
        if not isinstance(organ, str) or sanitize_slugpart(organ) != organ \
                or not isinstance(state, dict) or set(state) != {
                    "today", "last_ts"} \
                or isinstance(state.get("today"), bool) \
                or not isinstance(state.get("today"), int) \
                or state["today"] < 0 \
                or not isinstance(state.get("last_ts"), str):
            raise RuntimeError("pulse publication effects are invalid")
        if state["last_ts"]:
            try:
                _canonical_utc_timestamp(state["last_ts"])
            except ValueError:
                raise RuntimeError(
                    "pulse publication effects are invalid") from None
    return effects


def _pending_pulse_marker(memo):
    """Validate and return a crash-recovery identity for pulse publication."""
    marker = memo.get("pulse_publication")
    if marker is None:
        return None
    required = {"v", "seq", "id", "started_at"}
    optional = {"ledger", "effects"}
    if not isinstance(marker, dict) or not required.issubset(marker) \
            or set(marker) - required - optional \
            or marker.get("v") != 1 \
            or not isinstance(marker.get("seq"), int) \
            or isinstance(marker.get("seq"), bool) \
            or marker["seq"] < 0 \
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
    return marker


def _mark_pulse_publication(memo, seq):
    """Persist one pulse transaction identity before its first corpus byte."""
    marker = _pending_pulse_marker(memo)
    if marker is not None:
        return marker
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
        raise RuntimeError("pulse sequence is invalid")
    marker = {"v": 1, "seq": seq, "id": uuid.uuid4().hex,
              "started_at": iso()}
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


def _canonical_source_cognitive_ids(value):
    if not isinstance(value, list) \
            or len(value) > MAX_SOURCE_REPLAY_EVENTS \
            or any(not isinstance(event_id, str)
                   or re.fullmatch(r"[0-9a-f]{64}", event_id) is None
                   for event_id in value) \
            or len(value) != len(set(value)):
        raise ValueError("source cognitive admission is invalid")
    return sorted(value)


def _pending_source_replay_marker(memo):
    """Validate exact evidence debt that must settle before consolidation."""
    marker = memo.get("source_replay_pending")
    if marker is None:
        return None
    if not isinstance(marker, dict) or set(marker) != {
            "v", "id", "started_at", "started_seq", "sources", "events",
            "effects", "cognitive_ids"} \
            or marker.get("v") != 1 \
            or not isinstance(marker.get("id"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", marker["id"]) is None \
            or isinstance(marker.get("started_seq"), bool) \
            or not isinstance(marker.get("started_seq"), int) \
            or marker["started_seq"] < 0 \
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
            raise ValueError("cognitive admission is not a source event")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("source replay marker is invalid") from exc
    return marker


def _source_replay_events(marker):
    return [_event_from_replay_record(record) for record in marker["events"]]


def _source_replay_clock(marker):
    """Return the immutable cognitive timestamp/day bound by a source batch."""
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
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
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
        raise ValueError("source cognitive admission is invalid")
    if marker is None:
        marker = {"v": 1, "id": uuid.uuid4().hex, "started_at": iso(),
                  "started_seq": seq, "sources": sources,
                  "events": list(records.values()), "effects": effects,
                  "cognitive_ids": cognitive_ids}
    else:
        if marker["effects"] != effects:
            raise ValueError("source replay effects conflict")
        if marker["cognitive_ids"] != cognitive_ids:
            raise ValueError("source cognitive admission conflicts")
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
    pulse = _pending_pulse_marker(memo)
    if pulse is None:
        pulse = {"v": 1, "seq": seq, "id": uuid.uuid4().hex,
                 "started_at": iso(), "effects": effects}
    elif pulse["seq"] != seq:
        raise RuntimeError("pulse publication sequence conflicts")
    elif pulse.get("effects") not in (None, effects):
        raise RuntimeError("pulse publication effects conflict")
    else:
        pulse = dict(pulse, effects=effects)
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
    optional = {"ledger", "cycle"}
    if not isinstance(marker, dict) \
            or not required.issubset(marker) \
            or set(marker) - required - optional \
            or marker.get("v") != 1 \
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


def _mark_dream_publication(memo):
    marker = _pending_dream_marker(memo)
    if marker is not None:
        return marker
    marker = {"v": 1, "id": uuid.uuid4().hex, "started_at": iso()}
    updated = dict(memo, dream_publication=marker, sync_needed=True)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return marker


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
    """Persist one exact cycle result before status, ledger, or thought."""
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
    """Idempotently finish a marker-bound cycle row and result thought."""
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
    """Sign and clear an interrupted DREAM after projections are current."""
    marker = _pending_dream_marker(memo)
    if marker is None:
        return False
    if "cycle" in marker:
        raise RuntimeError("dream cycle recovery must complete before publish")
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


def _pending_consolidation_marker(memo):
    marker = memo.get("consolidation_pending", False)
    if marker is False or marker is None:
        return None
    if marker is True:  # pre-structured crash marker; upgraded on recovery
        return True
    if not isinstance(marker, dict) or set(marker) not in ({
            "v", "id", "started_at"}, {
            "v", "id", "started_at", "ledger"}, {
            "v", "id", "started_at", "ledger", "applied_at"}) \
            or marker.get("v") != 1 \
            or not isinstance(marker.get("id"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", marker["id"]) is None \
            or not isinstance(marker.get("started_at"), str):
        raise RuntimeError("consolidation recovery marker is invalid")
    try:
        if _canonical_utc_timestamp(marker["started_at"]) \
                != marker["started_at"]:
            raise ValueError
    except ValueError:
        raise RuntimeError("consolidation recovery marker is invalid") \
            from None
    if "ledger" in marker:
        ledger = marker["ledger"]
        if not isinstance(ledger, dict) or set(ledger) != {
                "order", "action", "arg1", "arg2", "content",
                "record_id"}:
            raise RuntimeError("consolidation ledger binding is invalid")
        try:
            basis = _pending_basis(
                ledger["order"], ledger["action"], ledger["arg1"],
                ledger["arg2"], ledger["content"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError("consolidation ledger binding is invalid") \
                from exc
        expected = {**basis, "record_id": _pending_identity(basis)}
        if ledger != expected or basis["action"] not in {
                "DREAM:consolidate", "RECOVER:consolidate"}:
            raise RuntimeError("consolidation ledger binding is invalid")
    if "applied_at" in marker:
        if "ledger" not in marker \
                or not isinstance(marker["applied_at"], str):
            raise RuntimeError("consolidation applied marker is invalid")
        try:
            if _canonical_utc_timestamp(marker["applied_at"]) \
                    != marker["applied_at"]:
                raise ValueError
        except ValueError:
            raise RuntimeError(
                "consolidation applied marker is invalid") from None
    return marker


def _mark_consolidation_pending(memo):
    marker = _pending_consolidation_marker(memo)
    if marker is not None:
        return marker
    marker = {"v": 1, "id": uuid.uuid4().hex, "started_at": iso()}
    updated = dict(memo, consolidation_pending=marker)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return marker


def _ensure_structured_consolidation_marker(memo):
    marker = _pending_consolidation_marker(memo)
    if marker is not True:
        return marker
    marker = {"v": 1, "id": uuid.uuid4().hex, "started_at": iso()}
    updated = dict(memo, consolidation_pending=marker)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return marker


def _bind_consolidation_ledger(memo, action, arg1, arg2, content=""):
    marker = _ensure_structured_consolidation_marker(memo)
    if not isinstance(marker, dict):
        raise RuntimeError("consolidation has no recovery identity")
    if "ledger" in marker:
        return marker["ledger"]
    basis = _pending_basis(time.time_ns(), action, arg1, arg2, content)
    ledger = {**basis, "record_id": _pending_identity(basis)}
    probe = {"schema": LEDGER_PENDING_SCHEMA,
             "record_id": ledger["record_id"], "queued_at": iso(), **basis}
    if len((json.dumps(
            probe, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False) + "\n").encode("utf-8")) \
            > MAX_LEDGER_PENDING_RECORD_BYTES:
        raise ValueError("consolidation ledger binding exceeds record bound")
    rebound = dict(marker, ledger=ledger)
    updated = dict(memo, consolidation_pending=rebound)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return ledger


def _settle_consolidation_ledger(memo):
    marker = _pending_consolidation_marker(memo)
    if not isinstance(marker, dict) or "ledger" not in marker:
        raise RuntimeError("consolidation ledger binding is absent")
    ledger = marker["ledger"]
    path = queue_ledger_transition(
        ledger["order"], ledger["action"], ledger["arg1"],
        ledger["arg2"], ledger["content"])
    _settle_ledger_transition(path)
    return ledger


def _mark_consolidation_applied(memo):
    marker = _pending_consolidation_marker(memo)
    if not isinstance(marker, dict) or "ledger" not in marker:
        raise RuntimeError("consolidation ledger must bind before apply")
    if "applied_at" in marker:
        return marker
    rebound = dict(marker, applied_at=iso())
    updated = dict(memo, consolidation_pending=rebound)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return rebound


def _clear_consolidation_marker(memo):
    updated = dict(memo)
    updated.pop("consolidation_pending", None)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)


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
        raise RuntimeError(f"pending brain sync failed: {sync_note}")
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


def _recover_pending_thought_projection(memo, store):
    """Rejoin every page-first thought and its rehearsal before new work."""
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
            # pulses commit one generation and visibly retry next heartbeat.
            if os.environ.get("SIA_BACKFILL") != "1":
                raise
            continue


def _settle_thought_page_signals(store, mind=None):
    """Commit bounded thought claims to both states before acknowledgment."""
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
    # A page-prefix crash still has exact source work to replay. Its planned
    # counters are authoritative only after that batch reaches every page,
    # mind, and cursor boundary; applying them here would make the isolated
    # replay count the missing suffix twice.
    if effects is not None and not source_pending:
        current = read_json(STATUS_PATH, {})
        if not isinstance(current, dict):
            current = {}
        if current.get("publication_id") != marker["id"]:
            recovered_errors = current.get("errors", {})
            if not isinstance(recovered_errors, dict):
                recovered_errors = {}
            recovered_errors = dict(
                recovered_errors,
                publication_recovery="recovered interrupted pulse status")
            organs = copy.deepcopy(effects["organs"])
            recovered = dict(
                current, v=1, ts=iso(), state="degraded",
                pulse_seq=marker["seq"], day=effects["day"],
                publication_id=marker["id"],
                events_pulse=effects["events_pulse"],
                events_today=sum(
                    state["today"] for state in organs.values()),
                organs=organs, errors=recovered_errors)
            export_status(recovered)
    updated = dict(memo)
    updated.pop("pulse_publication", None)
    if "dream_publication" not in updated and not source_pending:
        updated.pop("sync_needed", None)
        updated = _with_ready_receipt(updated, "pulse", marker["id"])
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return True


def _recover_pending_consolidation(memo):
    """Replay an interrupted lineage-bound consolidation before reads."""
    marker = _ensure_structured_consolidation_marker(memo)
    if marker is None:
        return None
    if "ledger" not in marker:
        _bind_consolidation_ledger(
            memo, "RECOVER:consolidate", f"id={marker['id']}",
            "completed")
        marker = _pending_consolidation_marker(memo)
    result = None
    if "applied_at" not in marker:
        result = consolidate_corpus()
        # The named DREAM transaction owns the whole cutoff-pinned generation,
        # not merely one directory page or claim batch.  Keep its exact ledger
        # binding pending while later pulses resume bounded consolidation
        # units, including the conservative scan after admitted source unlink.
        if _consolidation_scan_debt():
            return result
        _mark_consolidation_applied(memo)
    _settle_consolidation_ledger(memo)
    _clear_consolidation_marker(memo)
    return result


def _pulse_transaction(seq, opts=None):
    """Install the write-ahead publication barrier for one heartbeat."""
    ensure_dirs()
    memo = load_memo()
    if _ready_receipt(memo) is None \
            and memo.get("sync_needed", False) is False:
        _mark_sync_needed(memo)
    store = load_thoughts()
    # Prior transactions recover under generic publication debt. Installing
    # the new sequence marker before this phase would misattribute their
    # corpus repairs to the new pulse and allow two keeper rows for one seq.
    with corpus_mutation_barrier(lambda: _mark_sync_needed(memo)):
        recovery = _recover_before_pulse(memo, store)
    with corpus_mutation_barrier(
            lambda: _mark_pulse_publication(memo, seq)):
        return _pulse_transaction_guarded(
            seq, opts, memo, store, recovery)


def _recover_before_pulse(memo, store):
    """Finish older journals before the next named pulse may begin."""
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


def _pulse_transaction_guarded(seq, opts, memo, store=None, recovery=None):
    """One heartbeat. Returns the status dict it exported."""
    opts = opts or {}
    now_ts = float(opts.get("now", time.time()))
    cursors = load_cursors()
    store = load_thoughts() if store is None else store
    sync_needed = memo.get("sync_needed", False)
    if not isinstance(sync_needed, bool):
        raise RuntimeError("brainstem memo sync-needed state is invalid")
    stnow = read_json(STATUS_PATH, {})
    organs_st = stnow.get("organs", {})
    day = today()
    if stnow.get("day") != day:
        # keep the organ roster stable across midnight; zero the counters
        organs_st = {k: {**v, "today": 0} for k, v in organs_st.items()}

    # Each sense runs on an isolated cursor copy, merged back only on
    # success — a raising sense never persists cursor advances for events
    # it dropped. Cursors are made durable only AFTER the corpus writes.
    PENDING_CURSOR_RENAMES.clear()
    source_marker = _pending_source_replay_marker(memo)
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
    # an older valid batch forever; normal sensing resumes next heartbeat.
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
            graph_before_source = read_json(GRAPH_PATH, {})
            siamind.sync_graph_state(
                prepared_event_mind, graph_before_source, now=now_ts)
            if not prepared_event_mind["seen"]:
                for graph_node in graph_before_source.get("nodes", []):
                    prepared_event_mind["seen"][graph_node["id"]] = now_ts
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

            # One atomic memo image binds the admitted cognitive transition,
            # exact source bytes, and projected status before corpus mutation.
            _pulse_marker, source_marker = _stage_pulse_source_publication(
                memo, seq, event_sources, events, day,
                planned_events_pulse, planned_organs,
                source_effects=source_effects,
                prepared_source=prepared_source,
                cognitive_ids=cognitive_ids)
            # Persist the exact cognitive candidate and its bounded thought /
            # finding receipt before any source page can alter GRAPH_PATH.
            # A crash before this save sees the old graph and recomputes; a
            # crash after it reuses the receipt, so publication timing cannot
            # change first-sighting novelty or derived thoughts.
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
                    "event cognitive admission changed after dry-run")
    except Exception as e:
        write_ok = False
        # Cognitive state is all-or-nothing for the exact source batch. A
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

    # Event pages must be visible through PGLite and the graph before this
    # same pulse asks those surfaces for salience, anomalies, or associative
    # state. Keep the durable marker set: the final publication/signature
    # phase clears it only after all later thought pages are reconciled too.
    _settle_pending_publication(
        memo, "publish pulse events before memory queries", clear=False)

    # thoughts may add corpus pages too — generate BEFORE commit+sync
    every = int(opts.get("integrity_every", 10))
    chains = memo.get("chains", {})
    salience = anomalies = None
    if events or seq % every == 0 or not chains:
        chains = verify_chains()
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
        materialize_agent_notes(store)
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
        memo, "publish pulse thoughts before associative graph reads",
        clear=False)
    # ---- neurocognitive core (siamind): recall touches, Hebbian binding,
    # novelty gate, surprisal baselines, global workspace. Deterministic;
    # mind.json is owned by this daemon alone.
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
            g0 = read_json(GRAPH_PATH, {})
            siamind.sync_graph_state(mind, g0, now=now_ts)
            if not mind["seen"]:
                # first run: everything already in the graph counts as seen —
                # novelty is for what arrives from now on
                for n0 in g0.get("nodes", []):
                    mind["seen"][n0["id"]] = now_ts
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

    # prospective memory: surface open intents as deadlines approach
    # (once per stage: "soon" inside 48 h, then "overdue" once per day)
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

    # outcome learning: remind (once a day) when predictions come due
    takes_sum = {}
    try:
        takes_sum = siatakes.summary()
        if takes_sum.get("due") and memo.get("takes_reminder_day") != day:
            memo["takes_reminder_day"] = day
            reminder_text = (
                f"{takes_sum['due']} of my predictions are due for "
                f"grading — tonight's dream judges up to 3, or run "
                f"`sia grade` now.")
            new_thoughts.append(add_thought(
                store, "take", reminder_text, ["sia/cortex"],
                queue_id=thought_queue_identity(
                    "pulse.take-reminder", "take", reminder_text,
                    ["sia/cortex"], day=day,
                    extra=takes_sum.get("due"))))
    except Exception as e:
        errors["siatakes"] = str(e)[:160]

    # A thought page is the redo journal for its derived rehearsal signal.
    # Settle every page into the daemon-owned mind before evidence cursors or
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
            # Persist every in-memory thought gate before making evidence
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
                # Cursor publication and exact replay have both completed.
                # Clear the batch first; only then may its cognitive replay
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
        events or new_thoughts or agent_activity or organ_activity or dirty)
    sync_needed = memo.get("sync_needed", False)
    # Keep the post-publication acknowledgment predicate total even when a
    # valid but empty inbox claim reaches an otherwise idle pulse.
    graph_publication_failed = False
    if publication_activity:
        # Bind every publication to a durable pulse identity. If the daemon
        # dies after any page/commit but before its signed result, recovery
        # publishes the projections and signs that exact interrupted pulse
        # before either marker may clear.
        _mark_pulse_publication(memo, seq)
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
            # These removals stay in memory until the final status/thought
            # snapshots succeed. The last memo write is the readiness point.
            completed_pulse = _pending_pulse_marker(memo)
            memo.pop("pulse_publication", None)
            memo.pop("sync_needed", None)
            memo.update(_with_ready_receipt(
                memo, "pulse", completed_pulse["id"]))
            sync_needed = False
        if agent_activity and published and ledger_transition == "signed" \
                and thought_reinforcement_ready:
            agent_acknowledged, ack_errors = acknowledge_agent_notes(
                agent_paths, commit, synced)
            if ack_errors:
                errors["agent_ack"] = ack_errors

    hist = memo.get("pulse_history", [])
    hist.append([iso(), len(events)])
    memo["pulse_history"] = hist[-120:]
    if REDACTIONS:
        red = memo.setdefault("redactions", {})
        for organ, n in REDACTIONS.items():
            red[organ] = red.get(organ, 0) + n
        REDACTIONS.clear()
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

    try:
        intents_open = siatakes.open_intents()
    except Exception:
        intents_open = []
    try:
        bench_trend, bench_trend_boundary = _bench_trend_snapshot(
            include_metadata=True)
    except Exception as exc:
        bench_trend = []
        bench_trend_boundary = {"legacy_truncated": False}
        errors["bench_trend"] = str(exc)[:160]
    projection_debt = {
        "graph": _graph_projection_debt(),
        "consolidation": _consolidation_scan_debt(),
    }

    lseq, lhead = ledger_head()
    chain_status = chain_verdict(chains)
    failing = [k for k, v in chains.items() if v == "fail"]
    state = ("failed" if failing else
             "degraded" if (errors or not synced
                            or chain_status != "pass") else
             "thinking" if (events or new_thoughts or agent_activity)
             else "ok")
    last_thought = (store["thoughts"] or [{}])[-1]
    last_thought_origin = last_thought.get("origin")
    if last_thought_origin not in THOUGHT_ORIGINS:
        last_thought_origin = "legacy-unlabeled"
    prev_graph = read_json(GRAPH_PATH, {})
    status_marker = completed_pulse or _pending_pulse_marker(memo)
    st = {"v": 1, "ts": iso(), "state": state, "pulse_seq": seq, "day": day,
          "publication_id": (status_marker or {}).get("id", ""),
          "events_pulse": len(events),
          "events_today": sum(o.get("today", 0) for o in organs_st.values()),
          "organs": organs_st, "errors": errors,
          "pages": pages_total if pages_total is not None
                   else prev_graph.get("pages_total", 0),
          "graph_nodes": nodes if nodes is not None
                         else len(prev_graph.get("nodes", [])),
          "graph_edges": edges if edges is not None
                         else len(prev_graph.get("edges", [])),
          "integrity": {"chains": chains,
                        "verdict": chain_status,
                        "checked_at": iso()},
          "ledger": {"seq": lseq, "head": lhead[:12]},
          "ledger_transition": {
              "state": ledger_transition,
              "recovered": len(ledger_recovered),
              "pending_errors": len(ledger_recovery_errors)},
          "thought": {"ts": last_thought.get("ts", ""),
                      "kind": last_thought.get("kind", ""),
                      "text": last_thought.get("text", ""),
                      "origin": last_thought_origin},
          "dream": memo.get("dream", {}),
          "history": memo.get("pulse_history", []),
          "workspace": ws,
          "mind": {"nodes": len(mind.get("nodes", {})),
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
                      for it in intents_open[:5]
                      if it.get("id") and it.get("text")],
          "bench_trend": bench_trend,
          "bench_trend_boundary": bench_trend_boundary,
          "projection_debt": projection_debt,
          "agent_queue": {"materialized": len(agent_paths),
                          "refused": len(agent_queue_errors),
                          "acknowledged": agent_acknowledged},
          "redactions": memo.get("redactions", {}),
          "sync_note": sync_note}
    export_status(st)
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


def _epoch_slug_for_day(organ, date):
    year, week, _weekday = datetime.date.fromisoformat(date).isocalendar()
    return f"epochs/{organ}/{year}-w{week:02d}"


def _epoch_json_field(frontmatter, key, label, default):
    values = re.findall(rf"^{re.escape(key)}: (.*)$", frontmatter, re.M)
    if not values:
        return copy.deepcopy(default)
    if len(values) != 1:
        raise RuntimeError(f"{label} has duplicate {key}")
    try:
        return json.loads(values[0])
    except (TypeError, UnicodeError, ValueError, RecursionError) as exc:
        raise RuntimeError(f"{label} {key} is malformed") from exc


def _canonical_epoch_source_manifest(records, epoch_slug, prior_sources):
    if not isinstance(records, list):
        raise RuntimeError(f"epoch source manifest is invalid: {epoch_slug}")
    if len(records) > MAX_EPOCH_SOURCE_RECORDS:
        raise ConsolidationCapacityError(
            f"epoch source manifest is at capacity: {epoch_slug}")
    canonical = []
    day_parts = collections.defaultdict(list)
    seen_rel, seen_sha = set(), set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"rel", "sha256"} \
                or not isinstance(record.get("rel"), str) \
                or not isinstance(record.get("sha256"), str) \
                or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None:
            raise RuntimeError(
                f"epoch source manifest is invalid: {epoch_slug}")
        organ, date, part = _event_source_parts(record["rel"])
        if _epoch_slug_for_day(organ, date) != epoch_slug \
                or record["rel"] in seen_rel \
                or record["sha256"] in seen_sha \
                or record["sha256"] not in prior_sources:
            raise RuntimeError(
                f"epoch source manifest is invalid: {epoch_slug}")
        seen_rel.add(record["rel"])
        seen_sha.add(record["sha256"])
        day_parts[(organ, date)].append(part)
        canonical.append({"rel": record["rel"],
                          "sha256": record["sha256"]})
    for parts in day_parts.values():
        parts.sort()
        if parts != list(range(1, parts[-1] + 1)):
            raise RuntimeError(
                f"epoch source manifest has incomplete day lineage: "
                f"{epoch_slug}")
    canonical.sort(key=lambda record: record["rel"])
    if records != canonical:
        raise RuntimeError(f"epoch source manifest is invalid: {epoch_slug}")
    encoded = json.dumps(canonical, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) \
            > MAX_EPOCH_SOURCE_MANIFEST_BYTES:
        raise ConsolidationCapacityError(
            f"epoch source manifest exceeds its bound: {epoch_slug}")
    return canonical


def _read_epoch_state(slug):
    """Read and validate one bounded epoch plus optional exact shard lineage."""
    if not page_exists(slug):
        return {"slug": slug, "text": "", "sources": [], "dates": [],
                "ndays": 0, "source_manifest": []}
    text = _read_event_page(slug)
    match = FM_RE.match(text)
    if match is None:
        raise RuntimeError(f"existing epoch lacks frontmatter: {slug}")
    frontmatter = match.group(1)
    types = re.findall(r"^type:\s*(.*?)\s*$", frontmatter, re.M)
    if types != ["epoch"]:
        raise RuntimeError(f"existing epoch identity is invalid: {slug}")
    prior_sources = _epoch_json_field(
        frontmatter, "sia_sources", f"epoch lineage {slug}", [])
    if not isinstance(prior_sources, list) \
            or len(prior_sources) != len(set(prior_sources)) \
            or any(not isinstance(value, str)
                   or re.fullmatch(r"[0-9a-f]{64}", value) is None
                   for value in prior_sources):
        raise RuntimeError(f"epoch lineage is invalid: {slug}")
    prior_dates = _epoch_json_field(
        frontmatter, "sia_dates", f"epoch date lineage {slug}", [])
    if not isinstance(prior_dates, list) \
            or prior_dates != sorted(set(prior_dates)) \
            or any(not isinstance(value, str)
                   or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None
                   for value in prior_dates):
        raise RuntimeError(f"epoch date lineage is invalid: {slug}")
    manifest = _epoch_json_field(
        frontmatter, "sia_source_manifest",
        f"epoch source manifest {slug}", [])
    manifest = _canonical_epoch_source_manifest(
        manifest, slug, set(prior_sources))
    if any(_event_source_parts(record["rel"])[1] not in prior_dates
           for record in manifest):
        raise RuntimeError(f"epoch source manifest lacks date lineage: {slug}")
    day_matches = re.findall(r"Consolidated from (\d+) day-memories", text)
    if len(day_matches) != 1:
        raise RuntimeError(f"existing epoch lacks exact day count: {slug}")
    return {"slug": slug, "text": text, "sources": prior_sources,
            "dates": prior_dates, "ndays": int(day_matches[0]),
            "source_manifest": manifest}


def _merge_epoch_source_manifest(existing, items, epoch_slug, source_ids):
    by_rel = {record["rel"]: record for record in existing}
    by_sha = {record["sha256"]: record for record in existing}
    for _date, _path, _text, _tags, source_id, relative, _part in items:
        record = {"rel": relative, "sha256": source_id}
        prior_rel = by_rel.get(relative)
        prior_sha = by_sha.get(source_id)
        if (prior_rel is not None and prior_rel != record) \
                or (prior_sha is not None and prior_sha != record):
            raise RuntimeError(
                f"epoch source manifest conflicts with live shard: {relative}")
        if prior_rel is None and len(by_rel) >= MAX_EPOCH_SOURCE_RECORDS:
            raise ConsolidationCapacityError(
                f"epoch source manifest is at capacity: {epoch_slug}")
        by_rel[relative] = record
        by_sha[source_id] = record
    merged = sorted(by_rel.values(), key=lambda record: record["rel"])
    return _canonical_epoch_source_manifest(
        merged, epoch_slug, set(source_ids))


def _event_index_entries_for_sources(items, epoch_slug):
    entries = {}
    for _date, _path, text, _tags, source_id, relative, _part in items:
        source_organ, _source_date, _source_part = _event_source_parts(relative)
        match = FM_RE.match(text)
        if match is None:
            raise RuntimeError(
                f"consolidation source lacks frontmatter: {relative}")
        log_part = text[match.end():].split("## Timeline", 1)[0]
        if "## Log" in log_part:
            log_part = log_part.split("## Log", 1)[1]
        for line in (value for value in log_part.splitlines()
                     if value.startswith("- ")):
            marker = EVENT_MARKER_RE.fullmatch(line)
            if marker is None:
                if "sia-event:" in line:
                    raise RuntimeError(
                        f"consolidation source has malformed event identity: "
                        f"{relative}")
                continue
            event_id = marker.group("id")
            if event_id in entries:
                raise RuntimeError(
                    "event identity is duplicated across consolidation sources")
            if len(entries) >= MAX_EVENT_INDEX_RECORDS:
                raise ConsolidationCapacityError(
                    "consolidated event index batch is at capacity")
            entries[event_id] = {
                "schema": EVENT_INDEX_SCHEMA,
                "organ": source_organ,
                "event_id": event_id,
                "semantic_id": marker.group("semantic"),
                "payload_sha256": _event_payload_digest(
                    marker.group("payload")),
                "source_rel": relative,
                "source_sha256": source_id,
                "epoch_slug": epoch_slug,
            }
    result = [entries[event_id] for event_id in sorted(entries)]
    if len(result) > MAX_EVENT_INDEX_RECORDS:
        raise RuntimeError("consolidated event index batch exceeds its bound")
    for entry in result:
        _event_index_encoded(entry)
    return result


def _render_epoch_source_manifest(state, records, dates):
    """Prepare a legacy/recovery epoch update without mutating the corpus."""
    if not isinstance(dates, list) or dates != sorted(set(dates)) \
            or any(not isinstance(value, str)
                   or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None
                   for value in dates):
        raise RuntimeError(
            f"epoch date lineage is invalid: {state['slug']}")
    if records == state["source_manifest"] and dates == state["dates"]:
        return None
    text = state["text"]
    match = FM_RE.match(text)
    if match is None:
        raise RuntimeError(
            f"existing epoch lacks frontmatter: {state['slug']}")
    lines = match.group(1).splitlines()
    fields = {
        "sia_source_manifest": json.dumps(
            records, separators=(",", ":"), ensure_ascii=False),
        "sia_dates": json.dumps(
            dates, separators=(",", ":"), ensure_ascii=False),
    }
    for key, value in fields.items():
        field = f"{key}: {value}"
        positions = [index for index, line in enumerate(lines)
                     if line.startswith(f"{key}: ")]
        if len(positions) > 1:
            raise RuntimeError(
                f"epoch recovery metadata is invalid: {state['slug']}")
        if positions:
            lines[positions[0]] = field
            continue
        source_positions = [index for index, line in enumerate(lines)
                            if line.startswith("sia_sources: ")]
        position = source_positions[0] + 1 if len(source_positions) == 1 \
            else len(lines)
        lines.insert(position, field)
    body = text[match.end():]
    encoded = ("---\n" + "\n".join(lines) + "\n---\n" + body).encode(
        "utf-8")
    if len(encoded) > MAX_EPOCH_PAGE_BYTES:
        raise ConsolidationCapacityError(
            f"epoch page exceeds its lineage bound: {state['slug']}")
    return lines, body


def _write_epoch_source_manifest(state, rendered):
    if rendered is not None:
        frontmatter, body = rendered
        write_page(state["slug"], frontmatter, body)


def _render_bounded_epoch(slug, frontmatter, body):
    """Prepare a complete epoch page and classify capacity before publish."""
    encoded = ("---\n" + "\n".join(frontmatter) + "\n---\n" + body).encode(
        "utf-8")
    if len(encoded) > MAX_EPOCH_PAGE_BYTES:
        raise ConsolidationCapacityError(
            f"epoch page exceeds its lineage bound: {slug}")
    return frontmatter, body


def _write_bounded_epoch(slug, rendered):
    frontmatter, body = rendered
    write_page(slug, frontmatter, body)


def _consolidation_scan_path():
    """Return production state, or a corpus-scoped sibling for test roots."""
    production_corpus = os.path.abspath(os.path.join(SHARE, "corpus"))
    if os.path.abspath(CORPUS) == production_corpus:
        return os.path.join(STATE, "consolidation-scan.json")
    token = hashlib.sha256(os.path.abspath(CORPUS).encode("utf-8")).hexdigest()
    return os.path.join(
        os.path.dirname(os.path.abspath(CORPUS)),
        ".sia-consolidation-" + token,
        "scan.json")


def _fresh_consolidation_scan(cutoff):
    if not isinstance(cutoff, str) \
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", cutoff) is None:
        raise ValueError("consolidation cutoff is invalid")
    return {
        "schema": CONSOLIDATION_SCAN_SCHEMA,
        "generation": uuid.uuid4().hex,
        "phase": "scan",
        "cutoff": cutoff,
        "queue": [{"relative": "", "levels":
                   MAX_CONSOLIDATION_TREE_LEVELS, "page": {}}],
        "pending_days": [],
        "claims": [],
    }


def _canonical_consolidation_day(value):
    if not isinstance(value, dict) or set(value) != {"organ", "date"} \
            or not isinstance(value.get("organ"), str) \
            or re.fullmatch(
                r"[a-z0-9][a-z0-9._-]{0,199}", value["organ"]) is None \
            or not isinstance(value.get("date"), str):
        raise RuntimeError("consolidation candidate day is invalid")
    try:
        if datetime.date.fromisoformat(value["date"]).isoformat() \
                != value["date"]:
            raise ValueError
    except ValueError:
        raise RuntimeError("consolidation candidate day is invalid") \
            from None
    return dict(value)


def _canonical_consolidation_scan(value):
    if not isinstance(value, dict) \
            or value.get("schema") != CONSOLIDATION_SCAN_SCHEMA \
            or value.get("phase") not in {"scan", "complete"} \
            or not isinstance(value.get("generation"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", value["generation"]) is None \
            or not isinstance(value.get("cutoff"), str) \
            or re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value["cutoff"]) is None \
            or not isinstance(value.get("queue"), list) \
            or len(value["queue"]) > MAX_CONSOLIDATION_DIRECTORY_QUEUE \
            or not isinstance(value.get("pending_days"), list) \
            or len(value["pending_days"]) > MAX_SOURCE_SCAN_ENTRIES \
            or not isinstance(value.get("claims"), list) \
            or len(value["claims"]) > MAX_CONSOLIDATION_DAYS_PER_RUN:
        raise RuntimeError("consolidation scan state is invalid")
    queue = []
    for frame in value["queue"]:
        if not isinstance(frame, dict) or set(frame) != {
                "relative", "levels", "page"}:
            raise RuntimeError("consolidation scan cursor is invalid")
        relative = frame["relative"]
        if not isinstance(relative, str) or os.path.isabs(relative) \
                or relative in {".", ".."} \
                or any(part in {"", ".", ".."}
                       for part in relative.split("/") if relative) \
                or isinstance(frame["levels"], bool) \
                or not isinstance(frame["levels"], int) \
                or frame["levels"] < 0 \
                or frame["levels"] > MAX_CONSOLIDATION_TREE_LEVELS:
            raise RuntimeError("consolidation scan cursor is invalid")
        queue.append({"relative": relative, "levels": frame["levels"],
                      "page": _validated_source_page_state(frame["page"])})
    pending = [_canonical_consolidation_day(day)
               for day in value["pending_days"]]
    if len({(day["organ"], day["date"]) for day in pending}) != len(pending):
        raise RuntimeError("consolidation candidate day is duplicated")
    claims = []
    for claim in value["claims"]:
        if not isinstance(claim, dict) or set(claim) != {
                "organ", "date", "cutoff", "directory", "sources"}:
            raise RuntimeError("consolidation day claim is invalid")
        day = _canonical_consolidation_day(
            {"organ": claim.get("organ"), "date": claim.get("date")})
        directory = _validated_source_page_state(claim.get("directory"))
        sources = claim.get("sources")
        if not isinstance(sources, list) \
                or len(sources) > MAX_EVENT_SHARDS or not sources:
            raise RuntimeError("consolidation day claim is invalid")
        canonical_sources = []
        for record in sources:
            if not isinstance(record, dict) or set(record) != {
                    "rel", "sha256"} \
                    or not isinstance(record.get("rel"), str) \
                    or not isinstance(record.get("sha256"), str) \
                    or re.fullmatch(
                        r"[0-9a-f]{64}", record["sha256"]) is None:
                raise RuntimeError("consolidation day claim is invalid")
            organ, date, _part = _event_source_parts(record["rel"])
            if organ != day["organ"] or date != day["date"]:
                raise RuntimeError("consolidation day claim is invalid")
            canonical_sources.append(dict(record))
        canonical_sources.sort(key=lambda record: record["rel"])
        if sources != canonical_sources \
                or len({record["rel"] for record in sources}) != len(sources):
            raise RuntimeError("consolidation day claim is invalid")
        if claim["cutoff"] != value["cutoff"]:
            raise RuntimeError("consolidation claim cutoff conflicts")
        claims.append({**day, "cutoff": claim["cutoff"],
                       "directory": directory,
                       "sources": canonical_sources})
    if value["phase"] == "complete" and queue:
        raise RuntimeError("completed consolidation scan retains a cursor")
    return dict(value, queue=queue, pending_days=pending, claims=claims)


def _load_consolidation_scan(cutoff):
    """Load one cutoff-pinned generation, rolling only after convergence."""
    path = _consolidation_scan_path()
    value = read_state_json(path, {}, "consolidation scan")
    if not value:
        return _fresh_consolidation_scan(cutoff)
    value = _canonical_consolidation_scan(value)
    if value["cutoff"] != cutoff \
            and value["phase"] == "complete" \
            and not value["queue"] \
            and not value["pending_days"] \
            and not value["claims"]:
        # A later UTC day widens eligibility only after the prior generation
        # has no cursor or admitted work left. Restarting an incomplete scan
        # here would repeatedly discard its suffix on a large corpus.
        return _fresh_consolidation_scan(cutoff)
    return value


def _save_consolidation_scan(value):
    value = _canonical_consolidation_scan(value)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_STATE_JSON_BYTES:
        raise RuntimeError("consolidation scan state exceeds its byte bound")
    path = _consolidation_scan_path()
    ensure_durable_directory(os.path.dirname(path))
    atomic_write(path, encoded)
    return value


def _advance_consolidation_scan(value):
    """Inspect one global directory-page budget without deletion inference."""
    value = _canonical_consolidation_scan(value)
    if value["claims"] or value["pending_days"]:
        return value
    if value["phase"] == "complete":
        return value
    root = os.path.join(CORPUS, "events")
    queue = collections.deque(value["queue"])
    remaining = MAX_SOURCE_SCAN_ENTRIES
    discovered = []
    while queue and remaining:
        frame = queue.popleft()
        directory = os.path.join(root, frame["relative"])
        try:
            entries, complete, inspected, next_page = \
                _bounded_source_entries(
                    directory, frame["page"], remaining,
                    cleanup_legacy_atomic=True)
        except FileNotFoundError:
            if not frame["relative"]:
                queue.clear()
                break
            continue
        if next_page.get("reset"):
            return _save_consolidation_scan(
                _fresh_consolidation_scan(value["cutoff"]))
        remaining -= inspected
        if not complete:
            frame["page"] = next_page
            queue.appendleft(frame)
        for entry in entries:
            relative = os.path.join(frame["relative"], entry["name"])
            if frame["levels"] and stat.S_ISDIR(entry["mode"]):
                if len(queue) >= MAX_CONSOLIDATION_DIRECTORY_QUEUE:
                    raise RuntimeError(
                        "consolidation directory queue exceeds its bound")
                queue.append({"relative": relative,
                              "levels": frame["levels"] - 1,
                              "page": {}})
                continue
            if frame["levels"] or not entry["name"].endswith(".md"):
                continue
            rel = os.path.join("events", relative).replace(os.sep, "/")
            try:
                organ, date, _part = _event_source_parts(rel)
            except ValueError:
                continue
            if date < value["cutoff"]:
                discovered.append({"organ": organ, "date": date})
    deduped = {(day["organ"], day["date"]): day for day in discovered}
    value["pending_days"] = [deduped[key] for key in sorted(deduped)]
    value["queue"] = list(queue)
    if not queue:
        value["phase"] = "complete"
    return _save_consolidation_scan(value)


def _bounded_event_directory_entries(organ):
    """Read one complete organ directory only within the existing page cap."""
    root = os.path.join(CORPUS, "events", organ)
    page = {}
    remaining = MAX_EVENT_LOOKUP_PAGES
    gathered = []
    while remaining:
        limit = min(remaining, MAX_SOURCE_SCAN_ENTRIES)
        try:
            entries, complete, inspected, next_page = \
                _bounded_source_entries(
                    root, page, limit, cleanup_legacy_atomic=True)
        except FileNotFoundError:
            return [], {}
        if next_page.get("reset"):
            raise RuntimeError(
                "event directory changed during bounded consolidation scan")
        gathered.extend(entries)
        remaining -= inspected
        if complete:
            return gathered, next_page
        if inspected <= 0:
            raise RuntimeError("event directory scan made no progress")
        page = next_page
    raise RuntimeError("event directory exceeds its consolidation page bound")


def _prepare_consolidation_claims(value):
    if value["claims"]:
        return value
    selected = value["pending_days"][:MAX_CONSOLIDATION_DAYS_PER_RUN]
    if not selected:
        return value
    by_organ = collections.defaultdict(list)
    for day in selected:
        by_organ[day["organ"]].append(day["date"])
    claims = []
    for organ in sorted(by_organ):
        entries, directory = _bounded_event_directory_entries(organ)
        wanted = set(by_organ[organ])
        sources = collections.defaultdict(list)
        for entry in entries:
            if not entry["name"].endswith(".md"):
                continue
            if not stat.S_ISREG(entry["mode"]):
                raise RuntimeError(
                    "consolidation event source is not a regular file")
            rel = f"events/{organ}/{entry['name']}"
            try:
                source_organ, date, _part = _event_source_parts(rel)
            except ValueError:
                continue
            if source_organ != organ or date not in wanted:
                continue
            slug = rel[:-3]
            text = _read_event_page(slug)
            raw = text.encode("utf-8")
            sources[date].append({
                "rel": rel,
                "sha256": hashlib.sha256(
                    rel.encode("utf-8") + b"\0" + raw).hexdigest(),
            })
        for date in sorted(wanted):
            records = sorted(sources.get(date, []),
                             key=lambda record: record["rel"])
            if not records:
                # A candidate may have disappeared before its immutable claim.
                # It makes no absence claim and will be reconsidered later.
                continue
            claims.append({"organ": organ, "date": date,
                           "cutoff": value["cutoff"],
                           "directory": directory,
                           "sources": records})
    claimed_keys = {(claim["organ"], claim["date"]) for claim in claims}
    selected_keys = {(day["organ"], day["date"]) for day in selected}
    value["pending_days"] = [
        day for day in value["pending_days"]
        if (day["organ"], day["date"]) not in selected_keys
        or (day["organ"], day["date"]) in claimed_keys]
    value["claims"] = claims
    return _save_consolidation_scan(value)


def _claimed_consolidation_paths(value):
    """Revalidate exact claim bytes; missing sources require epoch lineage."""
    if not value["claims"]:
        return []
    by_organ = collections.defaultdict(list)
    for claim in value["claims"]:
        by_organ[claim["organ"]].append(claim)
    paths = []
    for organ, claims in by_organ.items():
        entries, _generation = _bounded_event_directory_entries(organ)
        live = {}
        selected_dates = {claim["date"] for claim in claims}
        for entry in entries:
            if not entry["name"].endswith(".md"):
                continue
            rel = f"events/{organ}/{entry['name']}"
            try:
                _source_organ, date, _part = _event_source_parts(rel)
            except ValueError:
                continue
            if date in selected_dates:
                live[rel] = os.path.join(CORPUS, rel)
        for claim in claims:
            records = {record["rel"]: record for record in claim["sources"]}
            extra = {rel for rel in live
                     if _event_source_parts(rel)[1] == claim["date"]} \
                - set(records)
            if extra:
                raise RuntimeError(
                    "live event shards conflict with consolidation claim")
            epoch = None
            for rel, record in records.items():
                path = live.get(rel)
                if path is not None:
                    text = _read_event_page(rel[:-3])
                    digest = hashlib.sha256(
                        rel.encode("utf-8") + b"\0"
                        + text.encode("utf-8")).hexdigest()
                    if digest != record["sha256"]:
                        raise RuntimeError(
                            "live event shard conflicts with epoch source "
                            "lineage and consolidation "
                            f"claim: {rel}")
                    paths.append(path)
                    continue
                if epoch is None:
                    epoch = _read_epoch_state(
                        _epoch_slug_for_day(organ, claim["date"]))
                if record not in epoch["source_manifest"]:
                    raise RuntimeError(
                        "missing event shard lacks exact epoch source lineage")
    return sorted(paths)


def _acknowledge_consolidation_claims(value):
    claimed_days = {(claim["organ"], claim["date"])
                    for claim in value["claims"]}
    mutated = False
    for claim in value["claims"]:
        for record in claim["sources"]:
            if not page_exists(record["rel"][:-3]):
                mutated = True
                break
    value["pending_days"] = [
        day for day in value["pending_days"]
        if (day["organ"], day["date"]) not in claimed_days]
    value["claims"] = []
    if mutated:
        replacement = _fresh_consolidation_scan(value["cutoff"])
        return _save_consolidation_scan(replacement)
    return _save_consolidation_scan(value)


def _consolidation_scan_debt():
    path = _consolidation_scan_path()
    try:
        value = read_state_json(path, {}, "consolidation scan")
    except RuntimeError as exc:
        return f"consolidation scan refused: {exc}"
    if not value:
        return ""
    value = _canonical_consolidation_scan(value)
    if value["claims"]:
        return "a bounded consolidation day claim is pending"
    if value["pending_days"] or value["phase"] != "complete":
        return "bounded corpus consolidation scan is pending"
    return ""


def consolidate_corpus():
    """Systems consolidation (hippocampus→neocortex): day pages older than
    the episodic window compact into weekly epoch pages. McGaugh preserve
    rule: declared safety-class days stay verbatim. Originals remain in
    corpus git history."""
    # never consolidate over an unhealthy repo: the unlink below is only
    # honest if the verbatim file is provably in git history first
    if corpus_commit("pre-consolidation") == "error":
        raise RuntimeError("pre-consolidation corpus git commit failed")
    mind_state = siamind.load_mind()
    # A completed `sia memory --pin` is protection immediately, even though
    # the single-writer brainstem materializes it on the next pulse.  The
    # producer and DREAM share the corpus lease; the queue snapshot itself is
    # additionally bounded and flocked inside siamind.
    scheduled_pages = siamind.pending_user_pin_slugs() | {
        slug for slug, record in mind_state.get("nodes", {}).items()
        if isinstance(record, dict)
        and siamind.is_important(record)
    }
    cutoff = (utcnow() - datetime.timedelta(
        days=siamind.EPISODIC_DAYS)).strftime("%Y-%m-%d")
    scan_state = _load_consolidation_scan(cutoff)
    scan_state = _advance_consolidation_scan(scan_state)
    scan_state = _prepare_consolidation_claims(scan_state)
    if not scan_state["claims"]:
        return 0, 0, 0
    claimed_paths = _claimed_consolidation_paths(scan_state)
    groups, kept_days = {}, set()
    epoch_states = {}

    def epoch_state_for_day(organ, date):
        slug = _epoch_slug_for_day(organ, date)
        if slug not in epoch_states:
            epoch_states[slug] = _read_epoch_state(slug)
        return epoch_states[slug]

    day_paths = collections.defaultdict(list)
    for path in claimed_paths:
        rel = os.path.relpath(path, CORPUS)
        try:
            organ, date, part = _event_source_parts(rel)
        except ValueError:
            continue
        if date >= cutoff:
            continue
        page_slug = rel[:-3]
        day_paths[(organ, date)].append((path, rel, page_slug, part))

    for (organ, date), paths in day_paths.items():
        paths.sort(key=lambda item: item[3])
        observed_parts = [item[3] for item in paths]
        observed_parts.sort()
        if len(observed_parts) != len(set(observed_parts)):
            raise RuntimeError("event day shard identity is duplicated")

        try:
            epoch_state = epoch_state_for_day(organ, date)
        except ConsolidationCapacityError:
            kept_days.add((organ, date))
            continue
        day_manifest = []
        for record in epoch_state["source_manifest"]:
            source_organ, source_date, _source_part = _event_source_parts(
                record["rel"])
            if source_organ == organ and source_date == date:
                day_manifest.append(record)
        recovery_lineage = bool(day_manifest)
        manifest_by_rel = {record["rel"]: record
                           for record in day_manifest}
        if recovery_lineage:
            if date not in epoch_state["dates"] \
                    or any(rel not in manifest_by_rel
                           for _path, rel, _page_slug, _part in paths):
                raise RuntimeError(
                    "live event shards conflict with epoch source lineage")
        elif observed_parts != list(range(1, observed_parts[-1] + 1)):
            raise RuntimeError("event day shards are not contiguous")

        durable = True
        for _path, rel, _page_slug, _part in paths:
            try:
                tracked = _run_bounded_text_process(
                    ["git", "ls-files", "--error-unmatch", "--", rel],
                    env=None, timeout=30, cwd=CORPUS,
                    label="git tracked-source check").returncode == 0
                clean_status = _run_bounded_text_process(
                    ["git", "status", "--porcelain", "--", rel],
                    env=None, timeout=30, cwd=CORPUS,
                    label="git source status")
                clean = clean_status.returncode == 0 \
                    and clean_status.stdout.strip() == ""
            except Exception:
                tracked = clean = False
            durable = durable and tracked and clean
        if not durable:
            continue               # retain the entire day; try next dream

        day_items = []
        protected = any(page_slug in scheduled_pages
                        for _path, _rel, page_slug, _part in paths)
        for path, rel, _page_slug, part in paths:
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
                | getattr(os, "O_NOFOLLOW", 0)
            try:
                fd = os.open(path, flags)
            except OSError as exc:
                raise RuntimeError(
                    f"consolidation source cannot be opened safely: {rel}") \
                    from exc
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) \
                        or before.st_size > MAX_EVENT_PAGE_BYTES:
                    raise RuntimeError(
                        f"consolidation source is not a bounded regular file: "
                        f"{rel}")
                raw = stream.read(MAX_EVENT_PAGE_BYTES + 1)
                after = os.fstat(stream.fileno())
            before_token = (before.st_dev, before.st_ino, before.st_size,
                            before.st_mtime_ns, before.st_ctime_ns)
            after_token = (after.st_dev, after.st_ino, after.st_size,
                           after.st_mtime_ns, after.st_ctime_ns)
            if before_token != after_token \
                    or len(raw) > MAX_EVENT_PAGE_BYTES:
                raise RuntimeError(
                    f"consolidation source changed while read: {rel}")
            try:
                text = raw.decode("utf-8", errors="strict")
            except UnicodeError as exc:
                raise RuntimeError(
                    f"consolidation source is not valid UTF-8: {rel}") \
                    from exc
            source_id = hashlib.sha256(
                rel.encode("utf-8") + b"\0" + raw).hexdigest()
            lineage_record = manifest_by_rel.get(rel)
            if recovery_lineage and (lineage_record is None
                                     or lineage_record["sha256"]
                                     != source_id):
                raise RuntimeError(
                    f"live event shard conflicts with epoch source lineage: "
                    f"{rel}")
            tm = re.search(r"^tags: \[(.*)\]$", text, re.M)
            tags = {tag.strip()
                    for tag in (tm.group(1).split(",") if tm else [])}
            protected = protected or bool(tags & siamind.SAFETY_TAGS)
            day_items.append(
                (date, path, text, tags, source_id, rel, part))
        if protected and not recovery_lineage:
            # McGaugh preservation is a day-level invariant. Keeping only a
            # protected shard would orphan its siblings' numbering.
            kept_days.add((organ, date))
            continue
        y, w, _ = datetime.date.fromisoformat(date).isocalendar()
        groups.setdefault((organ, y, w), []).extend(day_items)
    consolidated_days = set()
    written_epochs = 0
    for (organ, y, w), items in groups.items():
        items.sort(key=lambda item: (item[0], item[6], item[5]))
        slug = f"epochs/{organ}/{y}-w{w:02d}"
        state = epoch_states.get(slug)
        if state is None:
            state = _read_epoch_state(slug)
            epoch_states[slug] = state
        et = state["text"]
        prior_sources = state["sources"]
        prior_dates = state["dates"]
        prior_ndays = state["ndays"]
        prior_source_set = set(prior_sources)
        pending_items = [item for item in items
                         if item[4] not in prior_source_set]
        source_ids = prior_sources + [item[4] for item in pending_items]
        try:
            merged_manifest = _merge_epoch_source_manifest(
                state["source_manifest"], items, slug, source_ids)
            event_entries = _event_index_entries_for_sources(items, slug)
            _preflight_event_index_entries(event_entries)
        except ConsolidationCapacityError:
            # Capacity is retention policy, not a failed transaction. Nothing
            # in this weekly group has been mutated yet, so DREAM can settle
            # its publication marker and reconsider the verbatim days later.
            kept_days |= {(organ, item[0]) for item in items}
            continue

        for item in pending_items:
            if item[0] in prior_dates \
                    and not any(record["rel"] == item[5]
                                for record in state["source_manifest"]):
                raise RuntimeError(
                    "event source conflicts with legacy epoch date lineage")

        def unlink_admitted(item):
            """Delete only the exact source bytes admitted to this epoch."""
            _date, path, _text, _tags, expected_id, rel, _part = item
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
                | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) \
                        or before.st_size > MAX_EVENT_PAGE_BYTES:
                    raise RuntimeError(
                        f"consolidation cleanup target is not bounded: {rel}")
                current = stream.read(MAX_EVENT_PAGE_BYTES + 1)
                after = os.fstat(stream.fileno())
            observed = (before.st_dev, before.st_ino, before.st_size,
                        before.st_mtime_ns, before.st_ctime_ns)
            finished = (after.st_dev, after.st_ino, after.st_size,
                        after.st_mtime_ns, after.st_ctime_ns)
            target = os.lstat(path)
            if observed != finished or len(current) > MAX_EVENT_PAGE_BYTES \
                    or (target.st_dev, target.st_ino) != (after.st_dev,
                                                          after.st_ino):
                raise RuntimeError(
                    f"consolidation source changed before cleanup: {rel}")
            current_id = hashlib.sha256(
                rel.encode("utf-8") + b"\0" + current).hexdigest()
            if current_id != expected_id:
                raise RuntimeError(
                    f"consolidation source changed before cleanup: {rel}")
            _before_corpus_mutation()
            os.unlink(path)
            dfd = os.open(os.path.dirname(path),
                          os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)

        # A crash can leave sources whose lineage is already in the durable
        # epoch page. Cleanup is replayable and must not merge their counts a
        # second time.
        if not pending_items:
            recovery_dates = sorted(
                set(prior_dates) | {item[0] for item in items})
            try:
                recovery_epoch = _render_epoch_source_manifest(
                    state, merged_manifest, recovery_dates)
            except ConsolidationCapacityError:
                kept_days |= {(organ, item[0]) for item in items}
                continue
            _write_epoch_source_manifest(state, recovery_epoch)
            _publish_event_index_entries(event_entries)
            for item in items:
                unlink_admitted(item)
            continue

        name = ORGANS.get(organ, (organ, ""))[0]
        counts, all_tags, bullets, links = {}, {organ}, [], set()
        for date, path, text, tags, _source_id, _rel, _part in pending_items:
            cm = re.search(r"^sia_counts: (.*)$", text, re.M)
            if not cm:
                raise RuntimeError(
                    f"consolidation source lacks sia_counts: "
                    f"{os.path.relpath(path, CORPUS)}")
            source_counts = _parse_sia_counts(
                cm.group(1), os.path.relpath(path, CORPUS))
            for k, v in source_counts.items():
                counts[k] = counts.get(k, 0) + v
            all_tags |= tags
            log_part = text.split("## Timeline")[0].split("## Log")[-1]
            blts = [l for l in log_part.splitlines() if l.startswith("- ")]
            for b in blts[:2] + blts[-1:]:
                bullets.append(f"- {date} ·" + b[1:])
            for wl in re.findall(r"\[\[([a-z0-9/._-]+)", text):
                links.add(wl)
        # merge with an existing epoch page — a later consolidation run for
        # the same week must extend it, never atomically erase it
        from_date = pending_items[0][0]
        to_date = pending_items[-1][0]
        pending_dates = {item[0] for item in pending_items}
        all_dates = sorted(set(prior_dates) | pending_dates)
        ndays = prior_ndays + len(pending_dates - set(prior_dates))
        if et:
            pm = re.search(r"^sia_counts: (.*)$", et, re.M)
            if not pm:
                raise RuntimeError(f"existing epoch lacks sia_counts: {slug}")
            epoch_counts = _parse_sia_counts(pm.group(1), slug)
            for k, v in epoch_counts.items():
                counts[k] = counts.get(k, 0) + v
            ptm = re.search(r"^tags: \[(.*)\]$", et, re.M)
            if ptm:
                all_tags |= {t.strip() for t in ptm.group(1).split(",")
                             if t.strip()}
            pdm = re.search(r"^date: (.*)$", et, re.M)
            if pdm and pdm.group(1).strip() < from_date:
                from_date = pdm.group(1).strip()
            etm = re.search(
                r"Consolidated from \d+ day-memories "
                r"\(\d{4}-\d{2}-\d{2} … (\d{4}-\d{2}-\d{2})\)", et)
            if etm and etm.group(1) > to_date:
                to_date = etm.group(1)
            if "## Exemplars" in et:
                ex = et.split("## Exemplars", 1)[1].split("\n## ")[0]
                prev_b = [l for l in ex.splitlines() if l.startswith("- ")]
                bullets = prev_b + bullets
            for wl in re.findall(r"\[\[([a-z0-9/._-]+)", et):
                links.add(wl)
        bullets = bullets[:24]
        total = sum(counts.values())
        agg = ", ".join(f"{v}× {k}" for k, v in
                        sorted(counts.items(), key=lambda kv: -kv[1])[:8])
        linkline = " ".join(f"[[{l}]]" for l in sorted(links)
                            if not l.startswith("events/"))[:800]
        epoch_frontmatter = [
            "type: epoch", fm_title(f"{name} — {y} week {w}"),
            f"tags: [{', '.join(sorted(all_tags))}]",
            f"date: {from_date}",
            f"sia_sources: {json.dumps(source_ids, separators=(',', ':'))}",
            "sia_source_manifest: " + json.dumps(
                merged_manifest, separators=(",", ":"),
                ensure_ascii=False),
            f"sia_dates: {json.dumps(all_dates, separators=(',', ':'))}",
            f"sia_counts: {json.dumps(counts, sort_keys=True)}",
        ]
        if organ == "jackal":
            epoch_frontmatter.insert(1, "origin: derived")
        epoch_body = (
            f"# {name} — {y} week {w}\n\n"
            f"Consolidated from {ndays} day-memories "
            f"({from_date} … {to_date}); originals verbatim in "
            f"corpus git history. Organ: [[organs/{organ}]] of "
            f"[[sia/cortex]].\n\n"
            f"## Exemplars\n" + "\n".join(bullets) + "\n\n"
            f"{linkline}\n\n"
            f"## Timeline\n- **{to_date}** — {total} events that "
            f"week: {agg}\n")
        try:
            rendered_epoch = _render_bounded_epoch(
                slug, epoch_frontmatter, epoch_body)
        except ConsolidationCapacityError:
            kept_days |= {(organ, item[0]) for item in items}
            continue
        _write_bounded_epoch(slug, rendered_epoch)
        _publish_event_index_entries(event_entries)
        consolidated_days |= {(organ, item[0]) for item in pending_items}
        written_epochs += 1
        for item in items:
            unlink_admitted(item)
    result = (len(consolidated_days), written_epochs, len(kept_days))
    _acknowledge_consolidation_claims(scan_state)
    return result


def _pending_dream_unit(mind):
    receipt = mind.get("dream_unit")
    if receipt is None:
        return None
    required = {"v", "id", "unit", "ledger", "thought", "trend"}
    if not isinstance(receipt, dict) or set(receipt) != required \
            or receipt.get("v") != 1 \
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
            prior = json.loads(line)
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
    # window before it can strand a durable dream-unit receipt at the file
    # bound. JACKAL status=exact: parsed=30-1, exact=29 (NOT formal-bounded).
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


def rehearse_memories(now=None, stage=None):
    """Embed due pages and atomically stage their mind/ledger transition."""
    now = time.time() if now is None else float(now)
    mind = siamind.load_mind(now=now)
    siamind.sync_graph_state(mind, read_json(GRAPH_PATH, {}), now=now)
    planned = siamind.plan_rehearsal(mind, now=now)
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
        result = gbrain(["embed", slug], timeout=300)
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
            failed += 1
        attempted.append(item)
    decay = siamind.decay_sweep(mind, now=now)
    report = {"reviewed": reviewed, "embedded": embedded, "failed": failed,
              "missing": missing, "planned": attempted, "decay": decay}
    if stage is not None:
        stage(mind, report)
    siamind.save_mind(mind)
    return report


def dream(memo_update=True, now=None):
    """Run the whole nightly workflow under the corpus transaction lease."""
    with corpus_owner():
        return _dream_transaction(memo_update=memo_update, now=now)


def _dream_transaction(memo_update=True, now=None):
    """Install the write-ahead publication barrier for one dream cycle."""
    ensure_dirs()
    memo = load_memo()
    if _ready_receipt(memo) is None \
            and memo.get("sync_needed", False) is False:
        _mark_sync_needed(memo)
    with corpus_mutation_barrier(lambda: _mark_sync_needed(memo)):
        return _dream_transaction_guarded(memo_update, now, memo)


def _dream_transaction_guarded(memo_update, now, memo):
    """Nightly consolidation: run gbrain's deterministic dream cycle."""
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
    if _pending_dream_marker(memo) is not None:
        _settle_pending_publication(
            memo, "publish interrupted dream before dream recovery",
            clear=False)
        _recover_pending_dream_publication(memo)
    _settle_pending_publication(
        memo, "publish pending corpus migration before dream")
    # The nightly job is independent units with separate ledgers/failure:
    # failure — a bad grade must never block an epoch merge, and a
    # A failed heuristic drift tripwire must never block the gbrain cycle.
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
            durable_ledger_append(
                "DREAM:consolidate", "error", str(e)[:80])
            log(f"consolidation failed: {e!r}")
            raise RuntimeError(
                f"dream consolidation requires recovery: {e}") from e
    if ncomp:
        add_thought(store0, "dream",
            f"I consolidated {ncomp} day-memories into {nepoch} epoch "
            f"memories; {nkept} protected day-memories stay verbatim. "
            f"The originals live on in my git history.", ["sia/cortex"])
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
            if reviewed:
                qualities = {}
                for item in reviewed:
                    quality = item["quality"]
                    qualities[quality] = qualities.get(quality, 0) + 1
                quality_text = ", ".join(
                    f"q{quality}:{count}"
                    for quality, count in sorted(qualities.items()))
                thought_text = (
                    f"I rehearsed {len(reviewed)} important memories on "
                    f"their SM-2 schedule ({quality_text}); "
                    f"{rehearsal['embedded']} pages re-embedded. Decay "
                    f"only changes retrieval salience; it never deletes "
                    f"evidence.")
                thought = (
                    "dream", thought_text,
                    [item["slug"] for item in reviewed[:5]], False)
            _stage_dream_unit(
                mind, "rehearse", "DREAM:rehearse",
                f"reviewed={len(reviewed)}",
                f"embedded={rehearsal['embedded']} "
                f"failed={rehearsal['failed']} "
                f"missing={rehearsal['missing']}",
                json.dumps(reviewed, sort_keys=True), thought=thought)

        rehearsal = rehearse_memories(now=now, stage=stage_rehearsal)
        _settle_pending_dream_unit(store0, expected_unit="rehearse")
    except LedgerTransitionError:
        raise
    except Exception as e:
        durable_ledger_append("DREAM:rehearse", "error", str(e)[:80])
        log(f"rehearsal failed: {e!r}")
    export_thoughts(store0)
    _settle_thought_page_signals(store0)
    _settle_pending_publication(
        memo, "publish dream rehearsal thoughts before musing")
    try:
        mind = siamind.load_mind()
        pruned = siamind.hebb_hygiene(mind, now=now)
        g = read_json(GRAPH_PATH, None)
        _, lhead = ledger_head()
        dream_day = datetime.datetime.fromtimestamp(
            now, datetime.timezone.utc).strftime("%Y-%m-%d")
        m = siamind.muse(mind, g, dream_day, lhead, now=now)
        thought = ("association", m[0], m[1], False) if m else None
        _stage_dream_unit(
            mind, "muse", "DREAM:muse", "1" if m else "0",
            f"edges-pruned={pruned}", "", thought=thought)
        siamind.save_mind(mind)
        _settle_pending_dream_unit(store0, expected_unit="muse")
    except LedgerTransitionError:
        raise
    except Exception as e:
        durable_ledger_append("DREAM:muse", "error", str(e)[:80])
        log(f"musing failed: {e!r}")
    # outcome learning: grade due predictions (≤3/night; configured judge,
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
                memo, "publish prior dream thoughts before grading")
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
                f"Graded my prediction “{clip(gt['claim'], 80)}”: "
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
    except LedgerTransitionError:
        raise
    except Exception as e:
        durable_ledger_append("DREAM:grade", "error", str(e)[:80])
        log(f"take grading failed: {e!r}")
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
    except LedgerTransitionError:
        raise
    except Exception as e:
        durable_ledger_append("DREAM:bench", "error", str(e)[:80])
        log(f"heuristic drift tripwire failed: {e!r}")
    export_thoughts(store0)
    _settle_thought_page_signals(store0)
    _settle_pending_publication(
        memo, "publish dream benchmark before gbrain cycle")
    # gbrain's dream command mutates its derived PGLite state. Publish a
    # recovery identity before launching it, so a kill during any phase keeps
    # readiness closed until corpus sync + graph export are reconciled.
    _mark_dream_publication(memo)
    r = gbrain(["dream", "--json"], timeout=900)
    rep = None
    if r.returncode == 0:
        for opener in ("{",):
            i = r.stdout.find(opener)
            if i >= 0:
                try:
                    parsed = json.loads(r.stdout[i:])
                    if isinstance(parsed, dict):
                        rep = parsed
                except Exception:
                    pass
    store = load_thoughts()
    cycle_finished = (rep is not None and
                      rep.get("status") in {"ok", "clean", "partial"})
    if cycle_finished:
        tot = rep.get("totals", {})
        bits = clip(", ".join(
            f"{v} {k.replace('_', ' ')}" for k, v in tot.items()
            if isinstance(v, (int, float)) and v), 400)
        text = (f"I dreamed: consolidation cycle finished with status "
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
        status = clip(str(rep.get("status") or "invalid-status"), 80)
        reason = clip(str(rep.get("reason") or "cycle did not finish"), 400)
        dream_state = {
            "last": previous.get("last", ""), "attempt": iso(),
            "status": status, "summary": reason[-160:]}
        _bind_pending_dream_cycle(
            memo, dream_state, status, reason[:100], "",
            f"My dream cycle did not finish: {status} ({reason}).",
            urgent=True)
        _complete_pending_dream_cycle(memo, store)
    else:
        previous = memo.get("dream", {})
        failure_detail = clip(
            r.stderr or r.stdout or "no diagnostic output", 400)
        dream_state = {
            "last": previous.get("last", ""), "attempt": iso(),
            "status": "failed", "summary": failure_detail[-160:]}
        _bind_pending_dream_cycle(
            memo, dream_state, "failed", failure_detail[-100:], "",
            "My dream cycle failed to run.", urgent=True)
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
        _bind_pending_dream_ledger(
            memo, "error", str(exc)[:120], "projection exception")
        _settle_pending_dream_ledger(memo)
        raise RuntimeError(f"dream publication failed: {exc}") from exc
    _bind_pending_dream_ledger(
        memo, "ok" if synced else "sync-fail",
        f"commit={commit} graph={nodes}/{edges}/{pages_total}",
        sync_note[:400])
    _settle_pending_dream_ledger(memo)
    if not synced:
        raise RuntimeError(f"dream brain sync failed: {sync_note}")
    cleared_memo = dict(memo)
    completed_dream = _pending_dream_marker(memo)
    cleared_memo.pop("dream_publication", None)
    cleared_memo.pop("sync_needed", None)
    cleared_memo = _with_ready_receipt(
        cleared_memo, "dream", completed_dream["id"])
    _write_memo(cleared_memo)
    memo.clear()
    memo.update(cleared_memo)
    # DREAM's own deterministic state is durable, but an earlier pulse may
    # have left an external producer retryable. Selective finalization keeps
    # every queue-bound row whose exact producer still exists.
    _finalize_native_thought_mind_replay()
    if not cycle_finished:
        status = rep.get("status") if rep is not None else "failed"
        raise RuntimeError(f"gbrain dream cycle {status}")
    return rep

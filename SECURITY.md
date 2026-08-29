# Security & privacy

**Model**: SIA ingests *records, not content* — subsystem ledgers, logs,
reflogs, notification summaries, session metadata (never message bodies,
clipboards, or key material). Secret-shaped spans (key blocks, JWTs,
tokens, `.ssh` paths, password fields) are redacted at the sense
boundary, before anything reaches the corpus or git; every omission is
counted in SOURCE HEALTH. All storage and embeddings are local. The only
network calls are the installer's downloads and the optional judge on
your own CLI subscription (invoked read-only, sandboxed, ephemeral).

The daemon runs unsandboxed as your user (like any Omarchy plugin — read
the code before installing). The QML surfaces render snapshots only and
use `Text.PlainText` throughout. PGLite is single-writer: only the
daemon touches the database; agents use append-only queues.

**Reporting**: open a GitHub issue for non-sensitive matters; for
sensitive reports, use GitHub's private vulnerability reporting on this
repository.

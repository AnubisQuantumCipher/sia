# Disposable cgroup resource controls

This experiment starts uniquely named transient user services. It is not
installed and is not an authorization service. Before either workload starts,
the probe reads its actual unified-cgroup memory, swap, process and OOM-group
limits. A mismatch refuses without allocating the pressure workload.

```
timeout --kill-after=5s 150s python3 -B spark/resources/check_cgroup_boundary.py NEW_EVIDENCE_DIR
```

The process control creates a bounded number of children that wait on a pipe.
It requires a positive child, EAGAIN refusal and a kernel pids-limit event,
then releases and reaps those children. The memory control retains and touches
bounded blocks until the limited service is killed. ExecStopPost reads the
same cgroup's local memory counters; acceptance requires increases in max,
oom and oom_kill, plus the manager's OOM result and main-process SIGKILL.
Each service has a runtime deadline. Cleanup attempts stop and reset separately,
records errors and verifies the unit is gone or inactive without a cgroup.
Unexpected cleanup debt prevents a successful report.

The initial v1 experiment failed before workloads because MemoryOOMGroup was
not a supported transient property. OOMPolicy=kill is the documented service
setting; the probe independently checks memory.oom.group. A successful service
may already be garbage-collected when queried: not-found manager defaults are
not effective-limit evidence. The running probe's kernel reads are retained.

These are TESTED resource mechanisms on the recorded host, not a SPARK resource
proof, aggregate disk bound, production indexer sizing or protection against
hostile processes with the same user authority. Memory pressure currently comes
from one workload process; combined descendant-memory pressure is still UNRUN.
The trusted probe emits bounded records, but this is not a generic untrusted
output supervisor. Toolchain/runtime trust and kernel accounting remain
assumptions. Acceptance requires a committed-source reproduction, retained
commands/logs/hashes, independent review and terminal cleanup readback.

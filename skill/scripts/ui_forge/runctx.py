"""Per-run context for the gate: a hard deadline plus stderr progress.

The gate used to be able to burn unbounded wall-clock time in silence: a
180 s CLI subprocess for the fingerprint, then up to a dozen sequential
30 s fetches for the item and its registryDependencies, with no output
until the final JSON. To a calling agent that is indistinguishable from a
hang, and agents respond by killing the process and rabbit-holing.

A RunContext gives every stage one shared clock:

- each network/subprocess call receives only the time left, never its
  full private timeout stacked on top of the others;
- progress lines go to **stderr** (stdout stays pure JSON);
- expiry raises :class:`DeadlineExceeded` before the item is fetched, or
  produces a clearly-marked partial report after it — never silence.
"""
import os
import sys
import time


class DeadlineExceeded(Exception):
    """The run's wall-clock deadline expired during ``stage``."""

    def __init__(self, stage, elapsed, limit):
        super().__init__(
            "deadline of %ss exceeded during %s (elapsed %.1fs)" % (limit, stage, elapsed))
        self.stage = stage
        self.elapsed = round(elapsed, 1)
        self.limit = limit

    def as_dict(self):
        return {
            "code": "deadline_exceeded",
            "message": str(self),
            "stage": self.stage,
            "elapsed_seconds": self.elapsed,
            "deadline_seconds": self.limit,
            "hint": "rerun with a larger --deadline, or check the stage named above; "
                    "progress lines on stderr show where the time went",
        }


def progress_default():
    """Progress is on unless UIFORGE_PROGRESS opts out (0/no/off)."""
    return os.environ.get("UIFORGE_PROGRESS", "1").strip().lower() not in ("0", "no", "off")


class RunContext:
    def __init__(self, deadline=None, progress=True):
        self.started = time.monotonic()
        self.deadline = deadline or None
        self.progress_enabled = bool(progress)

    def elapsed(self):
        return time.monotonic() - self.started

    def remaining(self):
        if not self.deadline:
            return None
        return self.deadline - self.elapsed()

    def check(self, stage):
        """Raise DeadlineExceeded if the deadline has passed."""
        if self.deadline and self.remaining() <= 0:
            raise DeadlineExceeded(stage, self.elapsed(), self.deadline)

    def budget(self, stage, cap):
        """Timeout for one call in ``stage``: its cap, or the time left."""
        self.check(stage)
        remaining = self.remaining()
        if remaining is None:
            return cap
        return max(0.2, round(min(cap, remaining), 3))

    def deadline_bound(self, cap):
        """True when the deadline, not the stage cap, sizes the next timeout.

        Evaluate BEFORE the call: a timeout error from a deadline-bound call
        means the deadline fired inside the call, not merely a slow peer
        hitting its own cap.
        """
        remaining = self.remaining()
        return remaining is not None and remaining <= cap

    def blown(self, slack=0.5):
        """True when the deadline is exhausted (small clock slack allowed)."""
        remaining = self.remaining()
        return remaining is not None and remaining <= slack

    def log(self, stage, message):
        if self.progress_enabled:
            sys.stderr.write("[uiforge %5.1fs] %s: %s\n" % (self.elapsed(), stage, message))
            sys.stderr.flush()

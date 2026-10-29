"""Spring motion engine.

Principles (Apple's "Designing Fluid Interfaces", translated to Tk):
- Springs, not timed tweens: a new target never restarts an animation, it
  re-targets from the CURRENT value and velocity, so everything is interruptible.
- Critically damped (no bounce) by default; response is how fast it settles.
- Respect the Windows "show animations" setting (reduced motion): snap instead.
"""
import math
import time


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def mix(c1, c2, t):
    """Blend two #RRGGBB colours (t=0 -> c1, t=1 -> c2). Used to fake opacity on a known background."""
    t = clamp(t, 0.0, 1.0)
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def reduced_motion():
    """True if Windows 'Show animations' is turned off."""
    try:
        import ctypes
        from ctypes import wintypes
        flag = wintypes.BOOL(1)
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(flag), 0)  # SPI_GETCLIENTAREAANIMATION
        return not flag.value
    except Exception:
        return False


class Spring:
    def __init__(self, motion, owner=None, value=0.0, response=0.38, damping=1.0, eps=0.0008):
        self.motion, self.owner = motion, owner
        self.value = self.target = float(value)
        self.v = 0.0
        self.response, self.damping, self.eps = response, damping, eps

    def jump(self, value):
        self.value = self.target = float(value)
        self.v = 0.0
        self.motion.touch(self.owner)

    def to(self, target, velocity=None):
        self.target = float(target)
        if velocity is not None:
            self.v = velocity
        if not self.motion.enabled:
            self.value, self.v = self.target, 0.0
            self.motion.touch(self.owner)
            return
        if abs(self.target - self.value) <= self.eps and abs(self.v) <= self.eps * 5:
            self.value = self.target
            return
        self.motion.activate(self)

    def step(self, dt):
        w = 2 * math.pi / max(self.response, 0.05)
        k, c = w * w, 2 * self.damping * w
        n = max(1, int(dt / 0.004))
        h = dt / n
        for _ in range(n):
            a = k * (self.target - self.value) - c * self.v
            self.v += a * h
            self.value += self.v * h
        if abs(self.target - self.value) < self.eps and abs(self.v) < self.eps * 5:
            self.value, self.v = self.target, 0.0
            return False
        return True


class Motion:
    def __init__(self, root, enabled=True, clock=time.perf_counter):
        self.root, self.enabled, self.clock = root, enabled, clock
        self.active, self.dirty = set(), set()
        self.running = False
        self._flush_pending = False
        self.last = 0.0

    def activate(self, spring):
        self.active.add(spring)
        if not self.running:
            self.running = True
            self.last = self.clock()
            self.root.after(8, self._tick)

    def touch(self, owner):
        """Mark a widget for redraw (batched: one redraw per widget per frame)."""
        if owner is None:
            return
        self.dirty.add(owner)
        if not self.running and not self._flush_pending:
            self._flush_pending = True
            self.root.after_idle(self._flush)

    def _flush(self):
        self._flush_pending = False
        dirty, self.dirty = self.dirty, set()
        for o in dirty:
            try:
                o.redraw()
            except Exception:
                pass

    def _tick(self):
        now = self.clock()
        dt = clamp(now - self.last, 0.001, 0.05)
        self.last = now
        for sp in list(self.active):
            if sp.owner is not None:
                self.dirty.add(sp.owner)
            if not sp.step(dt):
                self.active.discard(sp)
        self._flush()
        if self.active:
            self.root.after(10, self._tick)
        else:
            self.running = False

    def later(self, ms, fn):
        if ms <= 0 or not self.enabled:
            fn()
        else:
            self.root.after(int(ms), fn)

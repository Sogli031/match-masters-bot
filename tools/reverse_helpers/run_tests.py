"""Minimal pytest stand-in: python run_tests.py tests/test_x.py ..."""
import importlib.util, inspect, itertools, math, os, sys, tempfile, traceback, types
from pathlib import Path

ROOT = Path(r"C:\Users\PC\Desktop\memory gui")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.chdir(ROOT)

pytest = types.ModuleType("pytest")


class _Mark:
    def parametrize(self, names, values, **_kw):
        if isinstance(names, str):
            names = [n.strip() for n in names.split(",")]
        def deco(fn):
            fn.__dict__.setdefault("_params", []).append((list(names), list(values)))
            return fn
        return deco

    def __getattr__(self, _name):
        return lambda *a, **k: (a[0] if a and callable(a[0]) and not k else (lambda fn: fn))


pytest.mark = _Mark()


class _Approx:
    def __init__(self, expected, rel=None, abs=None):
        self.e, self.rel, self.abs = expected, rel, abs
    def _close(self, a, b):
        tol = max(self.abs or 1e-12, (self.rel if self.rel is not None else 1e-6) * abs(b))
        return abs(a - b) <= tol
    def __eq__(self, other):
        if isinstance(self.e, (list, tuple)):
            return len(other) == len(self.e) and all(self._close(a, b) for a, b in zip(other, self.e))
        if isinstance(self.e, dict):
            return other.keys() == self.e.keys() and all(self._close(other[k], v) for k, v in self.e.items())
        return self._close(other, self.e)
    def __repr__(self):
        return f"approx({self.e})"


pytest.approx = lambda e, rel=None, abs=None: _Approx(e, rel, abs)


class _Raises:
    def __init__(self, exc, match=None):
        self.exc, self.match = exc, match
    def __enter__(self):
        return self
    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"did not raise {self.exc}")
        if not issubclass(et, self.exc):
            return False
        if self.match:
            import re
            assert re.search(self.match, str(ev)), str(ev)
        self.value = ev
        return True


pytest.raises = lambda exc, match=None: _Raises(exc, match)
pytest.fixture = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda fn: fn))
pytest.skip = lambda msg="": (_ for _ in ()).throw(RuntimeError("skip: " + msg))
sys.modules["pytest"] = pytest


class MonkeyPatch:
    def __init__(self):
        self._undo = []
    def setattr(self, target, name, value=None, raising=True):
        if isinstance(target, str) and value is None:
            mod, attr = target.rsplit(".", 1)
            target, name, value = importlib.import_module(mod), attr, name
        old = getattr(target, name, None)
        self._undo.append(lambda: setattr(target, name, old))
        setattr(target, name, value)
    def setitem(self, d, k, v):
        had, old = k in d, d.get(k)
        self._undo.append(lambda: d.__setitem__(k, old) if had else d.pop(k, None))
        d[k] = v
    def setenv(self, k, v):
        old = os.environ.get(k)
        self._undo.append(lambda: os.environ.__setitem__(k, old) if old is not None else os.environ.pop(k, None))
        os.environ[k] = v
    def delenv(self, k, raising=True):
        old = os.environ.get(k)
        self._undo.append(lambda: os.environ.__setitem__(k, old) if old is not None else None)
        os.environ.pop(k, None)
    def undo(self):
        for fn in reversed(self._undo):
            fn()


def run_file(path):
    spec = importlib.util.spec_from_file_location(Path(path).stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    passed = failed = 0
    for name, fn in list(vars(mod).items()):
        if not (name.startswith("test") and callable(fn)):
            continue
        combos = [{}]
        for names, values in reversed(getattr(fn, "_params", [])):
            new = []
            for c in combos:
                for v in values:
                    vv = v if len(names) > 1 else (v,)
                    new.append({**c, **dict(zip(names, vv))})
            combos = new
        for combo in combos:
            mp = MonkeyPatch()
            kwargs = dict(combo)
            params = inspect.signature(fn).parameters
            if "monkeypatch" in params:
                kwargs["monkeypatch"] = mp
            if "tmp_path" in params:
                kwargs["tmp_path"] = Path(tempfile.mkdtemp())
            try:
                fn(**kwargs)
                passed += 1
            except Exception:
                failed += 1
                print(f"FAIL {Path(path).name}::{name} {combo or ''}")
                traceback.print_exc(limit=6)
            finally:
                mp.undo()
    return passed, failed


if __name__ == "__main__":
    tp = tf = 0
    for p in sys.argv[1:]:
        a, b = run_file(p)
        tp += a; tf += b
    print(f"passed {tp}, failed {tf}")

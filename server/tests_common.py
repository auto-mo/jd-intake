"""Shared setup for the server test suites: the invented example profile, a temporary data folder, and a
network guard. Import this BEFORE app.py.

Every suite runs against examples/profile (Alex Rivera, an invented person) and a fresh temporary data
directory, so nothing touches your own profile, jobs or folders. The guard refuses any socket to a host that
is not this machine and replaces the calls that would reach Claude, DNS or a mailbox, so a test that
slipped would fail loudly instead of spending anything.
"""
import importlib.util
import os
import socket
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
EXAMPLE_PROFILE = os.path.join(REPO, "examples", "profile")
LCA_DATA = os.path.join(REPO, "plugins", "sponsorship", "data")

NET_ATTEMPTS = []        # every refused outbound connection, so a suite can fail on it
CLAUDE_CALLS = []        # every prompt that reached the guard instead of a stub


def setup_env(prefix):
    """Point the server at the example profile and a fresh temp data dir. Returns the temp dir."""
    tmp = tempfile.mkdtemp(prefix=prefix)
    os.environ["JDI_PROFILE_DIR"] = EXAMPLE_PROFILE
    os.environ["JDI_DATA_DIR"] = os.path.join(tmp, "data")
    os.environ["JDI_DROP_DIR"] = os.path.join(tmp, "Drop")
    os.environ.pop("JDI_EXTENSION_ID", None)
    os.makedirs(os.path.join(tmp, "data", "applications"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "Drop"), exist_ok=True)
    block_network()
    return tmp


def _local(host):
    h = (host or "").strip("[]").lower()
    return h in ("127.0.0.1", "localhost", "::1", "") or h.startswith("127.")


def block_network():
    """Refuse every connection that leaves this machine. Loopback stays open (a suite may run a local server)."""
    if getattr(socket, "_jdi_blocked", False):
        return
    real_connect, real_connect_ex, real_gai = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo

    def addr_host(addr):
        return addr[0] if isinstance(addr, tuple) else str(addr)

    def connect(self, addr):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _local(addr_host(addr)):
            NET_ATTEMPTS.append(str(addr))
            raise OSError(f"network blocked in tests: {addr}")
        return real_connect(self, addr)

    def connect_ex(self, addr):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _local(addr_host(addr)):
            NET_ATTEMPTS.append(str(addr))
            return 111
        return real_connect_ex(self, addr)

    def getaddrinfo(host, *a, **kw):
        if not _local(host if isinstance(host, str) else (host or b"").decode()):
            NET_ATTEMPTS.append(f"dns:{host}")
            raise socket.gaierror(f"DNS blocked in tests: {host}")
        return real_gai(host, *a, **kw)

    socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = connect, connect_ex, getaddrinfo
    socket._jdi_blocked = True


def load_app(module_name, tmp):
    """Import server/app.py under its own module name, with the guards in place and secrets read from a temp .env."""
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(HERE, "app.py"))
    app = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = app
    spec.loader.exec_module(app)
    app.ENV_FILE = os.path.join(tmp, ".env")          # never the repository's real .env
    guard(app)
    return app


def guard(app):
    """Replace every call that would leave the machine with a refusal a test can see."""
    def no_claude(prompt, *a, **kw):
        CLAUDE_CALLS.append((prompt or "")[:120])
        return {"error": "Claude is not available in tests", "timing": {"wall_ms": 0, "turns": 0}}
    app.unguarded = {"_run_claude_once": app._run_claude_once, "mail_domain_ok": app.mail_domain_ok}   # for a test that
    # exercises one of these itself, with its own stubs underneath
    app._run_claude_once = no_claude
    app.claude_status = lambda: "missing"
    app.mail_domain_ok = lambda domain: None          # no `dig`
    app.company_url_from_posting = lambda job: ""     # no LinkedIn reads
    app.company_site_from_linkedin = lambda url: ""
    app.company_page_info = lambda url: {}

    def no_mail(*a, **kw):
        raise RuntimeError("mailer is not available in tests")
    app.mailer.send = no_mail
    app.mailer.fetch = no_mail
    app.mailer.find_bounces = no_mail


def feature(app, **on):
    """Turn profile features on or off for this process: feature(app, email=True). Returns a restore function."""
    real = app.userprofile.feature

    def patched(key):
        return on[key] if key in on else real(key)
    app.userprofile.feature = patched

    def restore():
        app.userprofile.feature = real
    return restore


def lca_data_present():
    return os.path.isdir(LCA_DATA) and any(not n.startswith(".") for n in os.listdir(LCA_DATA))


def skip(results, name, reason):
    """Record a test that did not run, with the reason (shown, never counted as a pass or a failure)."""
    results.append((name, None, reason))


def report(results):
    """Print PASS/FAIL/SKIP lines and exit non-zero on any failure, or on any network attempt."""
    results.append(("no network was used", not NET_ATTEMPTS, "; ".join(NET_ATTEMPTS[:5])))
    ran = [r for r in results if r[1] is not None]
    fails = [r for r in ran if not r[1]]
    for name, ok, detail in results:
        if ok is None:
            print(f"SKIP  {name}   [{detail}]")
        else:
            print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""))
    skipped = len(results) - len(ran)
    print(f"\n{len(ran) - len(fails)}/{len(ran)} passed" + (f", {skipped} skipped" if skipped else ""))
    sys.exit(1 if fails else 0)

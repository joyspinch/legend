#!/usr/bin/env python3
"""Local development secret bootstrap for the legend server.

The published repository ships NO usable credential on purpose.
``config/app.json`` leaves ``[auth].secret`` and ``[auth].bootstrapPassword``
empty, which is the fail-closed state the engine is designed for:

* ``AuthToken.Ready()`` is false while the session key is shorter than 32
  characters, so no admin session cookie can be issued at all -- a clone
  cannot be logged into with a signing key that is also published here;
* ``Schema.SeedAdmin`` refuses to create a guide account while the
  bootstrap password is missing, so a fresh database is not seeded with a
  password that is also published here.

The engine reads both values from the environment when they are set --
``ZAN_AUTH_SECRET`` and ``ZAN_BOOTSTRAP_ADMIN_PASSWORD`` override the file
(the MVC package's ``Cfg.ApplyEnv`` runs after the file is applied). This
helper generates them once with a CSPRNG, keeps them in a git-ignored local
file under ``data/``, and hands them to the server process, so local
development needs no manual copy-paste and the repository keeps no key.

One password, one source of truth: the effective bootstrap password is
``LEGEND_ADMIN_PASSWORD`` -> ``ZAN_BOOTSTRAP_ADMIN_PASSWORD`` -> the local
file, in that order. The same value is used to seed the admin account and to
log into it, so seeding and login can never drift apart.

Usage:
  python tools/dev_env.py                       # create (or reuse) + summary
  python tools/dev_env.py init [--force]        # create the local secret file
  python tools/dev_env.py show                  # print the effective values
  python tools/dev_env.py env                   # print KEY=VALUE lines
  python tools/dev_env.py launch [--exe PATH]   # start the server with them

Stdlib only.
"""
import argparse
import json
import os
import secrets
import string
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # server
SECRETS_FILE = os.path.join(ROOT, "data", ".dev-secrets.json")

# Session key: the engine refuses anything shorter than 32 characters.
SECRET_LEN = 48
# Seed password: the package's Schema.SeedAdmin refuses anything shorter
# than 12 characters.
PASSWORD_LEN = 20

ALPHABET = string.ascii_letters + string.digits


def _generate():
    secret = secrets.token_urlsafe(SECRET_LEN)[:SECRET_LEN]
    password = "".join(secrets.choice(ALPHABET) for _ in range(PASSWORD_LEN))
    return {"authSecret": secret, "bootstrapPassword": password}


def load(create=True, force=False):
    """Return the local secret mapping, creating it on first use."""
    if os.path.exists(SECRETS_FILE) and not force:
        with open(SECRETS_FILE, encoding="utf-8") as f:
            return json.load(f)
    if not create:
        raise SystemExit("no local secrets yet -- run: python tools/dev_env.py init")
    os.makedirs(os.path.dirname(SECRETS_FILE), exist_ok=True)
    data = _generate()
    with open(SECRETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return data


def _effective(data, base=None):
    """The values actually in force: environment first, local file second."""
    env = os.environ if base is None else base
    password = (env.get("LEGEND_ADMIN_PASSWORD")
                or env.get("ZAN_BOOTSTRAP_ADMIN_PASSWORD")
                or data.get("bootstrapPassword", ""))
    secret = env.get("ZAN_AUTH_SECRET") or data.get("authSecret", "")
    return secret, password


def env_for(data, base=None):
    """Environment overlay the engine reads on top of config/app.json."""
    env = dict(os.environ if base is None else base)
    secret, password = _effective(data, env)
    env["ZAN_AUTH_SECRET"] = secret
    env["ZAN_BOOTSTRAP_ADMIN_PASSWORD"] = password
    # the e2e / security probes log into the admin backend
    env["LEGEND_ADMIN_PASSWORD"] = password
    return env


def admin_password():
    """The admin seed password in use: environment first, local file second.

    The environment wins so a deployment can override the local file; the
    local file is the fallback so a developer who started the server with
    ``dev_env.py launch`` can run the probes in a second shell.
    """
    for name in ("LEGEND_ADMIN_PASSWORD", "ZAN_BOOTSTRAP_ADMIN_PASSWORD"):
        v = os.environ.get(name, "")
        if v:
            return v
    if os.path.exists(SECRETS_FILE):
        with open(SECRETS_FILE, encoding="utf-8") as f:
            v = json.load(f).get("bootstrapPassword", "")
        if v:
            return v
    raise SystemExit(
            "admin password unknown -- start the server with "
            "'python tools/dev_env.py launch', or set LEGEND_ADMIN_PASSWORD")
    return password


def ensure_env():
    """Publish the effective secrets into os.environ.

    The parent process and every child it spawns then agree on the same
    session key and the same admin password -- which is what keeps
    "seeded password" and "login password" from drifting apart.
    """
    data = load(create=True)
    env = env_for(data)
    for k in ("ZAN_AUTH_SECRET", "ZAN_BOOTSTRAP_ADMIN_PASSWORD", "LEGEND_ADMIN_PASSWORD"):
        os.environ[k] = env[k]
    return os.environ


def cmd_init(args):
    existed = os.path.exists(SECRETS_FILE)
    load(create=True, force=args.force)
    print(("reusing " if existed else "wrote ") + SECRETS_FILE)
    return 0


def cmd_show(args):
    data = load(create=not args.no_create)
    secret, password = _effective(data)
    print("local secrets file : " + SECRETS_FILE)
    print("session key length : " + str(len(secret))
          + " chars (engine needs >= 32)")
    print("admin seed password: " + password
          + "  (engine needs >= 12)")
    return 0


def cmd_env(args):
    data = load(create=not args.no_create)
    for k, v in env_for(data).items():
        if k in ("ZAN_AUTH_SECRET", "ZAN_BOOTSTRAP_ADMIN_PASSWORD", "LEGEND_ADMIN_PASSWORD"):
            print(k + "=" + v)
    return 0


def _default_exe():
    for rel in (os.path.join("..", "build", "legend-server.exe"),
                os.path.join("build", "legend-server.exe"),
                "legend-server.exe"):
        p = os.path.normpath(os.path.join(ROOT, rel))
        if os.path.exists(p):
            return p
    return None


def cmd_launch(args):
    data = load(create=True)
    exe = args.exe or _default_exe()
    if not exe or not os.path.exists(exe):
        raise SystemExit("server executable not found -- build it first "
                         "(see server/README.md) or pass --exe PATH")
    env = env_for(data)
    print("[dev_env] launching " + os.path.abspath(exe))
    print("[dev_env] admin backend password: " + env["LEGEND_ADMIN_PASSWORD"])
    print("[dev_env] session key injected as ZAN_AUTH_SECRET")
    proc = subprocess.Popen([os.path.abspath(exe)], cwd=ROOT, env=env)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("init", help="create the local secret file")
    p.add_argument("--force", action="store_true", help="regenerate")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("show", help="print the effective values")
    p.add_argument("--no-create", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("env", help="print KEY=VALUE lines")
    p.add_argument("--no-create", action="store_true")
    p.set_defaults(func=cmd_env)

    p = sub.add_parser("launch", help="start the server with the local secrets")
    p.add_argument("--exe", default=None)
    p.set_defaults(func=cmd_launch)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        data = load(create=True)
        _, password = _effective(data)
        print("local secrets file : " + SECRETS_FILE)
        print("admin seed password: " + password)
        print("start the server with: python tools/dev_env.py launch")
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

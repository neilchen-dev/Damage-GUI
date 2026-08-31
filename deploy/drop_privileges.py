#!/usr/local/bin/python
"""Exec a command as the image's unprivileged service account."""
from __future__ import annotations

import grp
import os
import pwd
import sys


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: damagelab-drop-privileges COMMAND [ARG ...]")
    account = pwd.getpwnam("damagelab")
    group = grp.getgrgid(account.pw_gid)
    if os.geteuid() == 0:
        os.setgroups([])
        os.setgid(group.gr_gid)
        os.setuid(account.pw_uid)
    os.execvpe(sys.argv[1], sys.argv[1:], os.environ)


if __name__ == "__main__":
    main()

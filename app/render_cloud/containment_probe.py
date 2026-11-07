"""Test worker network containment without provisioning, storage, or user media."""
import argparse
import errno
import json
import os
import socket
import subprocess
import sys

from .isolation import enable_loopback, isolated_command
from .supervisor import child_environment
from . import socketless


def probe_child(parent_namespace):
    if os.readlink('/proc/self/ns/net') == parent_namespace:
        return False
    if {name for _, name in socket.if_nameindex()} != {'lo'}:
        return False
    enable_loopback()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        server.settimeout(2)
        with socket.create_connection(server.getsockname(), timeout=2) as client:
            client.sendall(b'ok')
            peer, _ = server.accept()
            with peer:
                peer.settimeout(2)
                if peer.recv(2, socket.MSG_WAITALL) != b'ok':
                    return False
    # UDP connect performs a route lookup without sending application data.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(('192.0.2.1', 9))
        except OSError as error:
            return error.errno in {errno.ENETUNREACH, errno.EHOSTUNREACH}
    return False


def inspect():
    if sys.platform != 'linux' or os.geteuid() == 0:
        return False
    namespace = os.readlink('/proc/self/ns/net')
    result = subprocess.run(
        isolated_command([sys.executable, '-m', 'app.render_cloud.containment_probe', '--child', namespace]),
        env={**child_environment(), 'LC_ALL': 'C'}, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=10, check=False,
    )
    return result.returncode == 0


def probe_socketless_child():
    for family, kind in [(socket.AF_INET, socket.SOCK_STREAM), (socket.AF_INET, socket.SOCK_DGRAM),
                         (socket.AF_INET6, socket.SOCK_STREAM), (socket.AF_UNIX, socket.SOCK_STREAM)]:
        try:
            with socket.socket(family, kind):
                return False
        except OSError as error:
            if error.errno != errno.EPERM:
                return False
    left, right = socket.socketpair()
    with left, right:
        left.sendall(b'ok')
        if right.recv(2) != b'ok':
            return False
    # Use a fresh executable to prove the filter is inherited through exec.
    nested = subprocess.run([sys.executable, '-c',
        'import errno,socket,sys\ntry: socket.socket()\n'
        'except OSError as e: sys.exit(0 if e.errno == errno.EPERM else 2)\nsys.exit(2)'],
        capture_output=True, timeout=5, check=False)
    return nested.returncode == 0


def inspect_socketless():
    result = subprocess.run(
        [sys.executable, '-m', 'app.render_cloud.socketless', '--', sys.executable,
         '-m', 'app.render_cloud.containment_probe', '--socketless-child'],
        env=child_environment(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=10, check=False,
    )
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', help=argparse.SUPPRESS)
    parser.add_argument('--socketless-child', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--require-socketless', action='store_true')
    args = parser.parse_args()
    try:
        if args.child:
            return 0 if probe_child(args.child) else 2
        if args.socketless_child:
            return 0 if probe_socketless_child() else 2
        passed = inspect()
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        passed = False
    try:
        socketless_passed = inspect_socketless()
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        socketless_passed = False
    print(json.dumps({'network_containment_passed': passed, 'socketless_containment_passed': socketless_passed,
                      'sandbox_certified': False}))
    return 0 if (socketless_passed if args.require_socketless else passed) else 2


if __name__ == '__main__':
    raise SystemExit(main())

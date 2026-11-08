"""Test worker network containment without provisioning, storage, or user media."""
import argparse
import ctypes
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


def diagnose_host():
    """Report only capability results. Do not print host identifiers or stderr."""
    if sys.platform != 'linux' or os.geteuid() == 0:
        return {}
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    results = {}
    for name, options in (
        ('user_namespace', ['--user', '--map-root-user']),
        ('network_namespace', ['--user', '--map-root-user', '--net']),
    ):
        check = subprocess.run(['unshare', *options, '--', 'true'], env={
            **child_environment(), 'LC_ALL': 'C',
        }, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=4)
        results[name] = 'ok' if check.returncode == 0 else (
            'permission_denied' if b'Operation not permitted' in check.stderr or b'Permission denied' in check.stderr
            else 'failed'
        )
    if os.uname().machine != 'x86_64':
        return results

    class IOVec(ctypes.Structure):
        _fields_ = [('base', ctypes.c_void_p), ('length', ctypes.c_size_t)]

    abi = libc.syscall(444, 0, 0, 1)  # landlock_create_ruleset VERSION
    results['landlock_abi'] = max(0, abi)
    # The probe child inherits known memory and a harmless pipe descriptor.
    # Read it from its actual parent, the relationship a broker would need.
    source = ctypes.create_string_buffer(b'x', 1)
    destination = ctypes.create_string_buffer(1)
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(write_fd)
        try:
            os.read(read_fd, 1)
        finally:
            os._exit(0)
    os.close(read_fd)
    try:
        ours = IOVec(ctypes.addressof(destination), 1)
        theirs = IOVec(ctypes.addressof(source), 1)
        copied = libc.syscall(310, pid, ctypes.byref(ours), 1, ctypes.byref(theirs), 1, 0)
        results['process_vm_readv'] = copied == 1 and destination.raw == b'x'
        results['pidfd_getfd'] = False
        if hasattr(os, 'pidfd_open'):
            try:
                process_fd = os.pidfd_open(pid)
            except OSError:
                process_fd = None
            if process_fd is not None:
                try:
                    duplicate = libc.syscall(438, process_fd, read_fd, 0)
                    if duplicate >= 0:
                        os.close(duplicate)
                        results['pidfd_getfd'] = True
                finally:
                    os.close(process_fd)
    finally:
        os.close(write_fd)
        os.waitpid(pid, 0)
    # Install a listener only in a disposable child. The selected syscall is
    # never used by the probe so no userspace broker is needed here.
    pid = os.fork()
    if pid == 0:
        try:
            class Filter(ctypes.Structure):
                _fields_ = [('code', ctypes.c_ushort), ('yes', ctypes.c_ubyte),
                            ('no', ctypes.c_ubyte), ('value', ctypes.c_uint32)]

            class Program(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ushort), ('filters', ctypes.POINTER(Filter))]

            code = (Filter * 4)(Filter(0x20, 0, 0, 0), Filter(0x15, 0, 1, 121),
                                Filter(0x06, 0, 0, 0x7fc00000), Filter(0x06, 0, 0, 0x7fff0000))
            program = Program(len(code), code)
            if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
                os._exit(2)
            listener = libc.syscall(317, 1, 8, ctypes.byref(program))  # SET_MODE_FILTER, NEW_LISTENER
            if listener >= 0:
                os.close(listener)
            os._exit(0 if listener >= 0 else 2)
        finally:
            os._exit(2)
    _, status = os.waitpid(pid, 0)
    results['seccomp_listener'] = status == 0
    return results


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
    try:
        host = diagnose_host()
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        host = {}
    print(json.dumps({'network_containment_passed': passed, 'socketless_containment_passed': socketless_passed,
                      'sandbox_certified': False, 'host_capabilities': host}))
    return 0 if (socketless_passed if args.require_socketless else passed) else 2


if __name__ == '__main__':
    raise SystemExit(main())

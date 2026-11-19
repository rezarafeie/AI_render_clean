"""Inherited Linux egress restriction for engines that only use local files."""
import ctypes as C
import errno
import os
import platform
import socket
import sys


# Talking styles may launch the Tscaps Chromium overlay, even though their
# final encode is FFmpeg. Preserve that behavior on the namespace path.
ENGINES = frozenset({'mlt', 'ffmpeg_job'})         # ffmpeg_job: only ffmpeg runs, on the job's own files, with no sockets


class Comparison(C.Structure):
    _fields_ = [('arg', C.c_uint), ('op', C.c_int),
                ('value', C.c_uint64), ('mask', C.c_uint64)]


def _prctl(option, value):
    libc = C.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [C.c_int] + [C.c_ulong] * 4
    if libc.prctl(option, value, 0, 0, 0) != 0:
        raise OSError(C.get_errno(), 'Cannot enforce worker process policy')


def protect_supervisor():
    # The render subprocess has the same UID. Block /proc memory, fd and
    # environment access to the parent that holds scoped storage credentials.
    _prctl(4, 0)  # PR_SET_DUMPABLE


def install():
    if sys.platform != 'linux' or platform.machine() != 'x86_64' or os.geteuid() == 0:
        raise RuntimeError('Socketless rendering requires non-root Linux x86-64')
    _prctl(38, 1)  # PR_SET_NO_NEW_PRIVS
    lib = C.CDLL('libseccomp.so.2')
    lib.seccomp_init.argtypes = [C.c_uint32]
    lib.seccomp_init.restype = C.c_void_p
    lib.seccomp_release.argtypes = [C.c_void_p]
    lib.seccomp_syscall_resolve_name.argtypes = [C.c_char_p]
    lib.seccomp_rule_add_array.argtypes = [C.c_void_p, C.c_uint32, C.c_int, C.c_uint, C.POINTER(Comparison)]
    lib.seccomp_load.argtypes = [C.c_void_p]
    context = lib.seccomp_init(0x7fff0000)  # SCMP_ACT_ALLOW
    if not context:
        raise RuntimeError('Cannot allocate seccomp filter')
    deny = 0x00050000 | errno.EPERM  # SCMP_ACT_ERRNO
    try:
        # Only private AF_UNIX socket pairs remain available for local IPC.
        # Block alternate socket creation and access to other process handles.
        for name in (
            'socket', 'connect', 'bind', 'listen', 'accept', 'accept4',
            'io_uring_setup', 'io_uring_enter', 'io_uring_register',
            'pidfd_getfd', 'ptrace', 'process_vm_readv', 'process_vm_writev',
            'bpf', 'setns', 'unshare',
        ):
            syscall = lib.seccomp_syscall_resolve_name(name.encode())
            if syscall < 0 or lib.seccomp_rule_add_array(context, deny, syscall, 0, None) < 0:
                raise RuntimeError('Cannot enforce seccomp syscall restriction')
        socketpair = lib.seccomp_syscall_resolve_name(b'socketpair')
        other_family = Comparison(0, 1, socket.AF_UNIX, 0)  # SCMP_CMP_NE
        if socketpair < 0 or lib.seccomp_rule_add_array(context, deny, socketpair, 1, C.byref(other_family)) < 0:
            raise RuntimeError('Cannot enforce socketpair restriction')
        if lib.seccomp_load(context) < 0:
            raise RuntimeError('Cannot activate seccomp filter')
    finally:
        lib.seccomp_release(context)


def main():
    if sys.argv[1:2] != ['--'] or len(sys.argv) < 3:
        raise SystemExit('Missing confined command')
    install()
    os.execv(sys.argv[2], sys.argv[2:])


if __name__ == '__main__':
    main()

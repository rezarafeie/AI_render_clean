"""Mediate native browser sockets without permitting Pod network access.

The broker copies and validates addresses before issuing its own syscalls. It
never continues an original connect, bind or listen request from the renderer.
"""
import array
import ctypes as C
import errno
import fcntl
import ipaddress
import os
from pathlib import Path
import re
import select
import signal
import socket
import struct
import sys

from app.render_cloud.socketless import Comparison, _prctl, protect_supervisor


def install():
    _prctl(38, 1)
    lib = C.CDLL('libseccomp.so.2', use_errno=True)
    lib.seccomp_init.argtypes = [C.c_uint]
    lib.seccomp_init.restype = C.c_void_p
    lib.seccomp_rule_add_array.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_uint, C.POINTER(Comparison)]
    lib.seccomp_syscall_resolve_name.argtypes = [C.c_char_p]
    lib.seccomp_load.argtypes = [C.c_void_p]
    lib.seccomp_notify_fd.argtypes = [C.c_void_p]
    ctx = lib.seccomp_init(0x7fff0000)
    if not ctx:
        raise RuntimeError('Cannot allocate browser socket filter')
    deny = 0x00050000 | errno.EPERM
    def rule(name, action=deny, comparison=None):
        syscall = lib.seccomp_syscall_resolve_name(name.encode())
        argument = C.byref(comparison) if comparison is not None else None
        if syscall < 0 or lib.seccomp_rule_add_array(ctx, action, syscall, int(argument is not None), argument) != 0:
            raise RuntimeError('Cannot configure browser socket filter')
    for name in ('connect', 'bind', 'listen'):
        rule(name, 0x7fc00000)
    # Notify on socket creation too. The broker injects only TCP stream sockets.
    rule('socket', 0x7fc00000)
    rule('socketpair', comparison=Comparison(0, 1, socket.AF_UNIX, 0))
    rule('prctl', comparison=Comparison(0, 4, 22, 0))
    for name in ('seccomp', 'io_uring_setup', 'io_uring_register', 'io_uring_enter',
                 'pidfd_getfd', 'ptrace', 'process_vm_readv', 'process_vm_writev',
                 'bpf', 'setns', 'unshare'):
        rule(name)
    if lib.seccomp_load(ctx) != 0:
        raise RuntimeError('Cannot install browser socket filter')
    fd = lib.seccomp_notify_fd(ctx)
    if fd < 0:
        raise RuntimeError('Cannot acquire browser socket listener')
    return fd


def ioctl(direction, nr, size):
    return (direction << 30) | (size << 16) | (ord('!') << 8) | nr


class IOVec(C.Structure):
    _fields_ = [('base', C.c_void_p), ('length', C.c_size_t)]


def sockaddr(pid, ptr, length, *, binding=False):
    if length not in (16, 28):
        raise OSError(errno.EAFNOSUPPORT, 'Address length')
    data = C.create_string_buffer(length)
    local, remote = IOVec(C.addressof(data), length), IOVec(ptr, length)
    if C.CDLL(None, use_errno=True).syscall(310, pid, C.byref(local), 1,
                                          C.byref(remote), 1, 0) != length:
        # Some container seccomp profiles restrict process_vm_readv even for
        # direct children. procfs applies its own ptrace access check.
        with open(f'/proc/{pid}/mem', 'rb', buffering=0) as memory:
            copied = os.pread(memory.fileno(), length, ptr)
        if len(copied) != length:
            raise OSError(errno.EFAULT, 'Address unavailable')
        data.raw = copied
    family = struct.unpack_from('H', data.raw)[0]
    port = struct.unpack_from('!H', data.raw, 2)[0]
    if family == socket.AF_INET and length == 16:
        address = ipaddress.IPv4Address(data.raw[4:8])
        if binding and address.is_unspecified:
            address = ipaddress.IPv4Address('127.0.0.1')
        if address.is_loopback:
            return family, (str(address), port)
    if family == socket.AF_INET6 and length == 28:
        address = ipaddress.IPv6Address(data.raw[8:24])
        if binding and address.is_unspecified:
            address = ipaddress.IPv6Address('::1')
        if address.is_loopback or (address.ipv4_mapped and address.ipv4_mapped.is_loopback):
            return family, (str(address), port, 0, 0)
    raise OSError(errno.EPERM, 'External address')


def notify(listener, notification, bound, listening):
    ident, pid, _, syscall, _, _, *args = struct.unpack('=QIIiIQ6Q', notification)
    result = 0
    error = 0
    new = None
    try:
        fcntl.ioctl(listener, ioctl(1, 2, 8), struct.pack('=Q', ident))
        if syscall == 41:
            family, kind, protocol = args[:3]
            if (family not in (socket.AF_INET, socket.AF_INET6) or protocol not in (0, 6)
                    or kind & ~(socket.SOCK_NONBLOCK | socket.SOCK_CLOEXEC) != socket.SOCK_STREAM):
                raise OSError(errno.EPERM, 'Non-TCP socket')
            new = socket.socket(family, kind, protocol)
            result = fcntl.ioctl(listener, ioctl(1, 3, 24), bytearray(struct.pack(
                '=QIIII', ident, 0, new.fileno(), 0,
                os.O_CLOEXEC if kind & socket.SOCK_CLOEXEC else 0)), True)
        else:
            target, ptr, size = args[:3]
            fd_link = os.readlink(f'/proc/{pid}/fd/{target}')
            if not re.fullmatch(r'socket:\[\d+\]', fd_link):
                raise OSError(errno.ENOTSOCK, 'Not a socket')
            flags = int(next(x.split()[1] for x in Path(f'/proc/{pid}/fdinfo/{target}').read_text().splitlines()
                             if x.startswith('flags:')), 8)
            if syscall == 50:
                saved = bound.get(fd_link)
                if saved is None:
                    raise OSError(errno.EPERM, 'Unverified bind')
                if len(listening) >= 1024 and saved.getsockname()[:2] not in listening:
                    raise OSError(errno.EMFILE, 'Listener limit')
                saved.listen(min(ptr, 128))
                listening[saved.getsockname()[:2]] = fd_link[8:-1]
                new = saved.dup()
            else:
                family, address = sockaddr(pid, ptr, size, binding=syscall == 49)
                new = socket.socket(family, socket.SOCK_STREAM)
                if syscall == 49:
                    if len(bound) >= 32:
                        raise OSError(errno.EMFILE, 'Bound socket limit')
                    new.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    new.bind(address)
                else:
                    host, port = address[:2]
                    mapped = ipaddress.IPv6Address(host).ipv4_mapped if family == socket.AF_INET6 else None
                    destination = (str(mapped) if mapped else host, port)
                    inode = listening.get(destination)
                    if inode is None or not any(
                        row[3] == '0A' and row[9] == inode
                        for table in ('tcp', 'tcp6')
                        for line in Path(f'/proc/net/{table}').read_text().splitlines()[1:]
                        if len(row := line.split()) > 9
                    ):
                        raise OSError(errno.EPERM, 'Unverified loopback listener')
                    new.settimeout(.25)
                    new.connect(address)
                new.setblocking(not bool(flags & os.O_NONBLOCK))
            fcntl.ioctl(listener, ioctl(1, 3, 24), struct.pack(
                '=QIIII', ident, 1, new.fileno(), target, flags & os.O_CLOEXEC))
            if syscall == 49:
                bound[os.readlink(f'/proc/self/fd/{new.fileno()}')] = new.dup()
            elif syscall == 50:
                bound.pop(fd_link).close()
    except (OSError, StopIteration, OverflowError, ValueError) as exc:
        error = -(getattr(exc, 'errno', None) or errno.EIO)
    finally:
        if new is not None:
            new.close()
    try:
        fcntl.ioctl(listener, ioctl(3, 1, 24), struct.pack('=QqiI', ident, result, error, 0))
    except OSError as exc:
        if exc.errno not in (errno.ENOENT, errno.EINTR):
            raise


def main(command):
    if not available() or os.geteuid() == 0 or not command:
        raise RuntimeError('Native browser mediation requires a non-root Linux worker')
    protect_supervisor()
    control, peer = socket.socketpair()
    pid = os.fork()
    if pid == 0:
        try:
            control.close()
            listener = install()
            peer.sendmsg([b'1'], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [listener]))])
            os.close(listener)
            peer.close()
            os.execvp(command[0], command)
        finally:
            os._exit(2)
    peer.close()
    listener = None
    reaped = False
    bound = {}
    listening = {}
    try:
        with control:
            control.settimeout(10)
            _, messages, _, _ = control.recvmsg(1, socket.CMSG_SPACE(4))
        if len(messages) != 1 or messages[0][:2] != (socket.SOL_SOCKET, socket.SCM_RIGHTS):
            raise RuntimeError('Browser socket filter did not start')
        listener = array.array('i', messages[0][2])[0]
        os.set_inheritable(listener, False)
        poller = select.poll()
        poller.register(listener, select.POLLIN)
        while True:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                reaped = True
                return os.waitstatus_to_exitcode(status)
            if any(flags & select.POLLIN for _, flags in poller.poll(100)):
                buf = bytearray(80)
                try:
                    fcntl.ioctl(listener, ioctl(3, 0, len(buf)), buf, True)
                except OSError as exc:
                    if exc.errno in (errno.ENOENT, errno.EINTR):
                        continue
                    raise
                notify(listener, buf, bound, listening)
    finally:
        if listener is not None:
            os.close(listener)
        for connection in bound.values():
            connection.close()
        if not reaped:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.waitpid(pid, 0)


BROWSER = Path('/opt/editorgpt-headless/chrome-headless-shell')


def available():
    return sys.platform == 'linux' and os.uname().machine == 'x86_64' and BROWSER.is_file()


if __name__ == '__main__':
    if not available():
        raise SystemExit(2)
    os.environ.update(REMOTION_BROWSER_EXECUTABLE=str(BROWSER), TSCAPS_CHROME=str(BROWSER),
                      HYPERFRAMES_BROWSER_PATH=str(BROWSER),
                      NODE_OPTIONS='--require=' + str(Path(__file__).with_name('loopback-interfaces.cjs')))
    raise SystemExit(main(sys.argv[1:]))

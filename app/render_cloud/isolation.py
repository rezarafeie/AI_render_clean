"""Shared worker and containment probe namespace setup."""
import sys


def isolated_command(command):
    if sys.platform != 'linux':
        raise RuntimeError('Cloud renderer requires Linux network isolation')
    return ['unshare', '--user', '--map-root-user', '--net', '--', *command]


def enable_loopback():
    import fcntl
    import socket
    import struct
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        flags = fcntl.ioctl(sock, 0x8913, struct.pack('16sh', b'lo', 0))
        current = struct.unpack('16sh', flags[:18])[1]
        fcntl.ioctl(sock, 0x8914, struct.pack('16sh', b'lo', current | 1))

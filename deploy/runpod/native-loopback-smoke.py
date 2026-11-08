import errno
import socket
import subprocess
import sys

for host, family in (('127.0.0.1', socket.AF_INET), ('::1', socket.AF_INET6)):
    with socket.socket(family) as server:
        server.bind((host, 0))
        server.listen(2)
        server.settimeout(1)
        with socket.socket(family) as client:
            client.connect(server.getsockname())
            client.sendall(b'ok')
            with server.accept()[0] as peer:
                assert peer.recv(2) == b'ok'
        with socket.socket(family) as unbound:
            try:
                unbound.listen(2)
            except PermissionError:
                pass
            else:
                raise AssertionError('unbound listener was permitted')
        print('Loopback roundtrip', host, flush=True)
for host in ('192.0.2.1', '169.254.169.254'):
    with socket.socket() as client:
        try:
            client.connect((host, 443))
        except OSError as exc:
            assert exc.errno == errno.EPERM, exc
        else:
            raise AssertionError('external connect was permitted')
assert subprocess.run([sys.executable, '-c',
    'import socket; socket.socket(socket.AF_INET, socket.SOCK_DGRAM)'],
    capture_output=True).returncode != 0
print('External TCP and nested UDP denied', flush=True)

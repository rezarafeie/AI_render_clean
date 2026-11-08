"""Run the same browser renderer inside a Linux guest with no network device."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path('/opt/editorgpt-offline')
WORK_ROOT = Path('/work')
SUCCESS = b'EDITORGPT_OFFLINE_RENDER_OK'


def available():
    return all((ROOT / path).is_file() for path in ('vmlinuz', 'initrd.gz', 'root.squashfs'))


def qemu_command(workspace: Path):
    workspace = workspace.resolve()
    if (not available() or WORK_ROOT not in workspace.parents or not workspace.is_dir()
            or any(c in str(workspace) for c in ',\n\r')):
        raise RuntimeError('Offline render guest or workspace unavailable')
    return [
        '/usr/bin/qemu-system-x86_64',
        '-machine', 'q35,accel=tcg', '-cpu', 'max', '-m', '3072', '-smp', '2',
        '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-nic', 'none', '-no-reboot',
        '-kernel', str(ROOT/'vmlinuz'), '-initrd', str(ROOT/'initrd.gz'),
        '-append', 'console=ttyS0 quiet panic=-1',
        '-drive', f'file={ROOT/"root.squashfs"},if=virtio,format=raw,readonly=on',
        '-virtfs', f'local,path={workspace},mount_tag=job,security_model=none,multidevs=remap',
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace', type=Path)
    args = parser.parse_args()
    seen = False
    with subprocess.Popen(qemu_command(args.workspace), stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
        while line := process.stdout.readline(2048):
            line = line.strip()
            if line == SUCCESS:
                seen = True
            elif line.startswith(b'{"state":'):
                sys.stdout.buffer.write(line + b'\n')
                sys.stdout.buffer.flush()
        return 0 if process.wait() == 0 and seen else 2


if __name__ == '__main__':
    raise SystemExit(main())

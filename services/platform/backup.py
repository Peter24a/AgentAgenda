#!/usr/bin/env python3
"""Consistent encrypted backups of every provisioned space and the control registry."""
import datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile

def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, **kwargs).stdout

def main():
    if not os.path.ismount("/srv/agentagenda"):
        raise SystemExit("Encrypted storage is not mounted")
    root = Path("/srv/agentagenda")
    backup_root = Path("/home/cite/AgentAgenda-platform/backups")
    backup_root.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with tempfile.TemporaryDirectory(dir=root/"recovery", prefix="backup-") as working:
        work = Path(working)
        for resource_path in sorted((root/"runtime").glob("*/resources.json")):
            import fcntl
            descriptor = os.open(resource_path.parent / "lifecycle.lock", os.O_RDWR | os.O_CREAT, 0o600)
            lock = os.fdopen(descriptor, "r+")
            fcntl.flock(lock, fcntl.LOCK_EX)
            resource = json.loads(resource_path.read_text())
            space_id = resource_path.parent.name
            dest = work/"spaces"/space_id
            dest.mkdir(parents=True, mode=0o700)
            names = [resource[k] for k in ("backend","worker","db")]
            running = {name:json.loads(run("docker","inspect",name))[0]["State"]["Running"] for name in names}
            try:
                for name in names[:2]:
                    if running[name]:run("docker","stop",name)
                if not running[names[2]]:run("docker","start",names[2])
                import time
                for attempt in range(60):
                    if subprocess.run(["docker","exec",names[2],"pg_isready","-U","agentagenda"],capture_output=True).returncode == 0:break
                    time.sleep(1)
                dump = run("docker","exec",names[2],"pg_dump","-U","agentagenda","-d","agentagenda","-Fc")
                (dest/"database.dump").write_bytes(dump)
                shutil.copytree(root/"spaces"/space_id/"vault",dest/"vault")
                shutil.copytree(resource_path.parent,dest/"runtime")
            finally:
                for name in names:
                    if running[name]:run("docker","start",name)
                    elif name==names[2]:run("docker","stop",name)
                lock.close()
        with sqlite3.connect(root/"control"/"platform.sqlite3") as original, sqlite3.connect(work/"platform.sqlite3") as copy:
            original.backup(copy)
        allocations = root/"runtime"/"ports.json"
        if allocations.exists():
            shutil.copyfile(allocations, work/"ports.json")
        archive = work/"backup.tar"
        with tarfile.open(archive,"w") as tar:
            tar.add(work/"spaces",arcname="spaces")
            tar.add(work/"platform.sqlite3",arcname="platform.sqlite3")
            if (work/"ports.json").exists():
                tar.add(work/"ports.json",arcname="ports.json")
        recipient = run("age-keygen","-y","/etc/agentagenda/backup.agekey").decode().strip()
        final = backup_root/("agentagenda-"+stamp+".tar.age")
        run("age","-r",recipient,"-o",str(final),str(archive))
        final.chmod(0o600)
        # Decryption+archive integrity check without writing plaintext outside the encrypted mount.
        decrypted = run("age","-d","-i","/etc/agentagenda/backup.agekey",str(final))
        import io
        with tarfile.open(fileobj=io.BytesIO(decrypted)) as tar:
            if not tar.getmember("platform.sqlite3"):raise RuntimeError("Missing registry backup")
        cutoff = datetime.datetime.now().timestamp()-30*86400
        for old in backup_root.glob("agentagenda-*.tar.age"):
            if old.stat().st_mtime < cutoff:old.unlink()
        print("Encrypted backup verified:",final.name)

if __name__ == "__main__":
    main()

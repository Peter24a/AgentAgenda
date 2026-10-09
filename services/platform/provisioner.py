#!/usr/bin/env python3
"""Local fixed-action worker. Run on the self-hosted server, never accept shell input."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid

from app.config import Settings
from app.registry import Registry

def command(*args, timeout=180):
    return subprocess.run(args, check=True, capture_output=True, timeout=timeout).stdout

def write_private_json(path, value):
    temporary = path.with_name(path.name + ".new")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(value, output)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def allocate_port(runtime_root, space_id):
    import fcntl
    import socket
    descriptor = os.open(runtime_root / "ports.lock", os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        allocations_file = runtime_root / "ports.json"
        allocations = json.loads(allocations_file.read_text()) if allocations_file.exists() else {}
        if space_id in allocations:
            return allocations[space_id]
        used = set(allocations.values())
        for port in range(8400, 9400):
            if port in used:
                continue
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError:
                    continue
            allocations[space_id] = port
            write_private_json(allocations_file, allocations)
            return port
        raise SystemExit("No private backend port is available")


def provision():
    if len(sys.argv) != 3 or sys.argv[1] not in {"create","suspend","resume","close","reopen"}:
        raise SystemExit("Invalid action")
    action, space_id = sys.argv[1], str(uuid.UUID(sys.argv[2]))
    cfg = Settings()
    registry = Registry(cfg.registry_path, cfg.encryption_key())
    space = registry.get_space(space_id, include_secret=True)
    storage_root = Path(os.environ.get("PLATFORM_SPACES_ROOT", "/srv/agentagenda/spaces"))
    runtime_root = Path(os.environ.get("PLATFORM_RUNTIME_ROOT", "/srv/agentagenda/runtime"))
    # Fail closed if the encrypted filesystem is unavailable.
    if not os.path.ismount("/srv/agentagenda"):
        raise SystemExit("Encrypted storage is not mounted")
    root = runtime_root / space_id
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    resources_file = root / "resources.json"
    if resources_file.exists():
        resources = json.loads(resources_file.read_text())
    elif action == "create":
        prefix = "aa-" + uuid.UUID(space_id).hex[:16]
        data = storage_root / space_id
        for child in [data, data/"postgres", data/"vault"]:
            child.mkdir(mode=0o700, parents=True, exist_ok=True)
        password, enrollment = secrets.token_urlsafe(36), secrets.token_urlsafe(48)
        shared = json.loads(Path("/etc/agentagenda/backend-shared.json").read_text())
        environment = {**shared, "DATABASE_URL":f"postgresql+asyncpg://agentagenda:{password}@db:5432/agentagenda",
            "SECRET_KEY":secrets.token_urlsafe(48), "PLATFORM_ENROLLMENT_KEY":enrollment,
            "ALLOW_ANONYMOUS_FALLBACK":"false", "SEED_DEMO_DATA":"false", "STORAGE_PATH":"/storage",
            "STORAGE_QUOTA_BYTES":str(space["quota_bytes"] or 5*1024**3), "HOST":"0.0.0.0", "PORT":"8001"}
        host_port = allocate_port(runtime_root, space_id)
        image = os.environ.get("PLATFORM_BACKEND_IMAGE", "agentagenda-backend:multitenancy-v2")
        compose = {"services": {
            "db":{"image":"postgres:16-alpine","container_name":prefix+"-db","restart":"unless-stopped",
                "environment":{"POSTGRES_USER":"agentagenda","POSTGRES_PASSWORD":password,"POSTGRES_DB":"agentagenda"},
                "volumes":[str(data/"postgres")+":/var/lib/postgresql/data"],
                "healthcheck":{"test":["CMD-SHELL","pg_isready -U agentagenda -d agentagenda"],"interval":"3s","timeout":"3s","retries":20}},
            "backend":{"image":image,"container_name":prefix+"-backend","restart":"unless-stopped",
                "depends_on":{"db":{"condition":"service_healthy"}},"environment":environment,
                "volumes":[str(data/"vault")+":/storage"],"ports":[f"127.0.0.1:{host_port}:8001"],"networks":["default","llm-apps"]},
            "worker":{"image":image,"container_name":prefix+"-worker","restart":"unless-stopped","init":True,
                "depends_on":{"db":{"condition":"service_healthy"}},"environment":environment,
                "command":["python","-m","app.worker.runner"],"volumes":[str(data/"vault")+":/storage"],"networks":["default","llm-apps"]}},
            "networks":{"default":{},"llm-apps":{"external":True}}}
        for service in compose["services"].values():
            service["logging"] = {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}}
        compose_file = root / "compose.json"
        write_private_json(compose_file, compose)
        resources = {"compose":str(compose_file), "project":prefix,"db":prefix+"-db","backend":prefix+"-backend","worker":prefix+"-worker", "enrollment_key":enrollment, "host_port":host_port}
        write_private_json(resources_file, resources)
    else:
        raise SystemExit("Space resources not provisioned")
    base = ["docker","compose","-p",resources["project"],"-f",resources["compose"]]
    if action in {"suspend","close"}:
        command(*base,"stop",timeout=120)
        return
    command(*base,"up","-d","--no-build",timeout=240)
    port = json.loads(command("docker","inspect",resources["backend"]))[0]["NetworkSettings"]["Ports"]["8001/tcp"][0]["HostPort"]
    import urllib.request
    target = "http://127.0.0.1:"+port
    for attempt in range(90):
        try:
            with urllib.request.urlopen(target+"/health",timeout=2) as response:
                if response.status==200:break
        except Exception:time.sleep(1)
    else:raise SystemExit("Backend did not become healthy")
    registry.configure_space(space_id,target,space["user_id"] or "default_user",resources["enrollment_key"],bool(space["legacy"]))

def main():
    if len(sys.argv) != 3 or sys.argv[1] not in {"create","suspend","resume","close","reopen"}:
        raise SystemExit("Invalid action")
    space_id = str(uuid.UUID(sys.argv[2]))
    if not os.path.ismount("/srv/agentagenda"):
        raise SystemExit("Encrypted storage is not mounted")
    import fcntl
    runtime = Path(os.environ.get("PLATFORM_RUNTIME_ROOT", "/srv/agentagenda/runtime")) / space_id
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(runtime / "lifecycle.lock", os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        provision()

if __name__ == "__main__":
    main()

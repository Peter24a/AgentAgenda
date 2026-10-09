#!/usr/bin/env python3
"""Start ready spaces after encrypted storage is mounted; keep admin reachable on failures."""
import subprocess
from app.config import Settings
from app.registry import Registry

cfg = Settings()
registry = Registry(cfg.registry_path,cfg.encryption_key())
for space in registry.list_spaces():
    if space["state"] == "ready":
        result = subprocess.run([cfg.provisioner,"resume",space["id"]],capture_output=True)
        if result.returncode:
            print("Could not start space",space["id"],flush=True)

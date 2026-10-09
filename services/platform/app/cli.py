"""Operator-only registry/bootstrap commands. Never expose these through the gateway."""
import argparse
import getpass
import json
import os
import time
from pathlib import Path

from cryptography.fernet import Fernet

from .config import Settings
from .registry import Registry
from .security import password_hash


def write_private(path: str, value: bytes):
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(value + b"\n")


def main():
    parser = argparse.ArgumentParser(description="AgentAgenda platform operator CLI")
    commands = parser.add_subparsers(dest="command", required=True)
    init_key = commands.add_parser("init-key")
    init_key.add_argument("--output", required=True)
    hashed = commands.add_parser("hash-password")
    hashed.add_argument("--output", required=True)
    hashed.add_argument("--password-file", help="Read plaintext from a private file rather than a terminal; delete that file after setup")
    imported = commands.add_parser("import-space")
    imported.add_argument("--name", required=True)
    imported.add_argument("--owner-name", required=True)
    imported.add_argument("--space-id")
    imported.add_argument("--backend-url", required=True)
    imported.add_argument("--user-id", required=True)
    imported.add_argument("--enrollment-key-file", required=True)
    imported.add_argument("--legacy", action="store_true")
    commands.add_parser("list-spaces")
    invite = commands.add_parser("create-invite")
    invite.add_argument("space_id")
    invite.add_argument("--purpose", choices=["enroll", "reconnect"], default="reconnect")
    invite.add_argument("--replace-device-id")
    invite.add_argument("--ttl-seconds", type=int)
    review = commands.add_parser("create-review-code")
    review.add_argument("space_id")
    review.add_argument("--output", required=True, help="Export the reusable review credential into a new private JSON file")
    revoke_review = commands.add_parser("revoke-review-code")
    revoke_review.add_argument("credential_id")
    args = parser.parse_args()
    if args.command == "init-key":
        write_private(args.output, Fernet.generate_key())
        return
    if args.command == "hash-password":
        password = Path(args.password_file).read_text().rstrip("\r\n") if args.password_file else getpass.getpass("New admin password: ")
        if not args.password_file and password != getpass.getpass("Repeat password: "):
            raise SystemExit("Passwords do not match")
        write_private(args.output, password_hash(password).encode())
        return
    cfg = Settings()
    registry = Registry(cfg.registry_path, cfg.encryption_key())
    if args.command == "import-space":
        # Re-running with an explicit known ID preserves the space and existing invitations.
        if args.space_id:
            try:
                space = registry.get_space(args.space_id)
            except Exception as exc:
                if getattr(exc, "status", None) != 404:
                    raise
                space = registry.create_space(args.name, args.owner_name, space_id=args.space_id)
        else:
            space = registry.create_space(args.name, args.owner_name)
        registry.configure_space(space["id"], args.backend_url, args.user_id, Path(args.enrollment_key_file).read_text().strip(), args.legacy)
        registry.set_space_state(space["id"], "ready")
        print(json.dumps(registry.get_space(space["id"]), ensure_ascii=False))
    elif args.command == "list-spaces":
        print(json.dumps({"spaces": registry.list_spaces()}, ensure_ascii=False))
    elif args.command == "create-invite":
        ttl = args.ttl_seconds or cfg.invitation_seconds
        if not 60 <= ttl <= 604800:
            raise SystemExit("TTL must be between one minute and seven days")
        if args.replace_device_id and args.purpose != "reconnect":
            raise SystemExit("Device replacement requires reconnect purpose")
        result = registry.create_invitation(args.space_id, args.purpose, ttl, args.replace_device_id)
        print(json.dumps(result))
    elif args.command == "create-review-code":
        if Path(args.output).exists():
            raise SystemExit("Output already exists; choose a new private file")
        result = registry.create_review_credential(args.space_id, cfg.review_space_id)
        try:
            write_private(args.output, json.dumps(result).encode())
        except Exception:
            registry.revoke_review_credential(result["credential_id"])
            raise
        print(json.dumps({"credential_id": result["credential_id"], "space_id": result["space_id"], "code_file": str(Path(args.output).resolve())}))
    elif args.command == "revoke-review-code":
        print(json.dumps(registry.revoke_review_credential(args.credential_id)))


if __name__ == "__main__":
    main()

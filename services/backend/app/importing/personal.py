"""Plan/import personal archives without executing or following their contents."""
import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

import yaml
from sqlalchemy import select, text

from app.config import settings
from app.db.session import get_db_context
from app.models.canonical import Document, DocumentRevision, DocumentOrigin, ImportBatch, Job

SUPPORTED = {'.md', '.txt', '.pdf', '.docx', '.png', '.jpg', '.jpeg'}
SECRET_EXTENSIONS = {'.key', '.pem', '.p12', '.pfx', '.cer', '.crt', '.req', '.ren', '.kdbx'}
SECRET_DIRS = {'seguridaddigital', '98_boveda_privada_no_compartir', '.git', '.ssh', 'efirma', 'efirma_anterior'}
OPERATIONAL_DIRS = {'08_sesiones_llm', '99_archivo', '90_paquetes_llm'}
PRIVATE_DIRS = {'identidad', 'fiscal', '04_finanzas_privado'}
MAX_BYTES = 50 * 1024 * 1024
MAX_HEADER_BYTES = 65536
PRIVATE_KEY = re.compile(rb'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----')


def _relative_path(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('Source path must be a relative POSIX path')
    parts = value.split('/')
    if any(part in {'', '.', '..'} for part in parts) or PurePosixPath(value).is_absolute() or ':' in parts[0]:
        raise ValueError('Source path must not contain traversal or absolute components')
    return parts


def _root_path(value):
    path = Path(os.path.abspath(Path(value).expanduser()))
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('Source root must not follow a symlink')
    if {part.lower() for part in path.parts} & SECRET_DIRS:
        raise ValueError('Source root is a blocked directory')
    if not path.is_dir():
        raise ValueError('Source must be an existing directory')
    return path.resolve(strict=True)


def canonical_roots(paths):
    roots = sorted({_root_path(path) for path in paths}, key=lambda path: (len(path.parts), str(path)))
    return [path for path in roots if not any(parent in path.parents for parent in roots)]


@contextmanager
def _open_source(root, relative):
    """Open each component beneath root without following replaced symlinks."""
    parts = _relative_path(relative)
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child_fd
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('Source must be a regular file')
            with os.fdopen(fd, 'rb') as source:
                fd = None
                yield source
        finally:
            if fd is not None:
                os.close(fd)
    finally:
        os.close(directory_fd)


def _fingerprint(source):
    info = os.fstat(source.fileno())
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _path_policy(path, relative):
    parts = {part.lower() for part in (*path.parts, *_relative_path(relative))}
    name = path.name.lower()
    if parts & SECRET_DIRS or path.suffix.lower() in SECRET_EXTENSIONS:
        return 'excluded', 'secret_or_blocked_path', {}, 'NEVER_UPLOAD'
    if any(word in name for word in ('password', 'contrase', 'recovery', 'recuperacion', 'never_upload', 'credential', 'credencial', 'api_key', 'apikey')):
        return 'excluded', 'credential_filename', {}, 'NEVER_UPLOAD'
    if path.suffix.lower() not in SUPPORTED:
        return 'excluded', 'unsupported_format', {}, 'UNCLASSIFIED'
    if parts & OPERATIONAL_DIRS or name in {'agents.md', 'leeme.txt', 'changelog.md'} or name.startswith('readme') or 'plantilla' in name:
        return 'excluded', 'instructions_template_or_derived', {}, 'UNCLASSIFIED'
    if '00_inicio' in parts and name not in {'perfil_breve.md', 'glosario.md'}:
        return 'excluded', 'operational_document', {}, 'UNCLASSIFIED'
    return None


def _metadata(source):
    source.seek(0)
    first = source.readline(MAX_HEADER_BYTES + 1).decode('utf-8-sig', errors='replace').strip()
    if first != '---':
        return {}
    lines, total = [], 0
    while total <= MAX_HEADER_BYTES:
        line = source.readline(MAX_HEADER_BYTES + 1)
        total += len(line)
        if not line or total > MAX_HEADER_BYTES:
            raise ValueError('Unterminated or oversized metadata')
        if line.strip() in {b'---', b'...'}:
            raw = b''.join(lines).decode('utf-8', errors='strict')
            if any(isinstance(token, yaml.tokens.AliasToken) for token in yaml.scan(raw)):
                raise ValueError('Metadata aliases are not supported')
            result = yaml.safe_load(raw) or {}
            if not isinstance(result, dict):
                raise ValueError('Metadata must be a mapping')
            return json.loads(json.dumps(result, default=str))
        lines.append(line)
    raise ValueError('Oversized metadata')


def file_policy(path: Path, relative: str, include_opt_in: bool, source=None):
    blocked = _path_policy(path, relative)
    if blocked:
        return blocked
    if source is None:
        if path.is_symlink():
            return 'excluded', 'symlink', {}, 'NEVER_UPLOAD'
        with _open_source(_root_path(path.parent), path.name) as opened:
            return file_policy(path, relative, include_opt_in, opened)
    size = os.fstat(source.fileno()).st_size
    if not 0 < size <= MAX_BYTES:
        return 'excluded', 'empty_or_oversize', {}, 'UNCLASSIFIED'
    metadata, privacy = {}, 'OPT_IN'
    if path.suffix.lower() in {'.md', '.txt'}:
        try:
            metadata = _metadata(source)
        except (yaml.YAMLError, ValueError, UnicodeError, RecursionError):
            return 'excluded', 'invalid_metadata', {}, 'UNCLASSIFIED'
        privacy = str(metadata.get('sensibilidad', 'OPT_IN')).upper()
        if privacy == 'NEVER_UPLOAD':
            return 'excluded', 'never_upload_metadata', {}, privacy
        if privacy not in {'SAFE', 'OPT_IN'}:
            return 'excluded', 'unknown_privacy_class', {}, privacy
        if str(metadata.get('estado', '')).lower() in {'plantilla', 'redireccion', 'derivado_no_editar', 'archivado'}:
            return 'excluded', 'instructions_template_or_derived', {}, privacy
        source.seek(0)
        tail = b''
        while chunk := source.read(1024 * 1024):
            if PRIVATE_KEY.search(tail + chunk):
                return 'excluded', 'private_key_content', {}, 'NEVER_UPLOAD'
            tail = chunk[-256:]
    if {part.lower() for part in path.parts} & PRIVATE_DIRS:
        privacy = 'OPT_IN'
    if privacy == 'OPT_IN' and not include_opt_in:
        return 'review', 'opt_in_required', metadata, privacy
    return 'include', 'eligible', metadata, privacy


def _sha256_source(source):
    source.seek(0)
    digest = hashlib.sha256()
    while chunk := source.read(1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path):
    with _open_source(_root_path(path.parent), path.name) as source:
        return _sha256_source(source)


def _manifest_hash(manifest):
    payload = {key: manifest[key] for key in ('schema_version', 'collection', 'include_opt_in')}
    payload['selected'] = [entry for entry in manifest['entries'] if entry['action'] in {'include', 'duplicate'}]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def scan_archive(paths, collection='personal-archive', include_opt_in=False):
    if not isinstance(collection, str) or not 0 < len(collection) <= 128:
        raise ValueError('Collection must contain 1 to 128 characters')
    roots = canonical_roots(paths)
    if len(roots) != 1:
        raise ValueError('Use one common parent directory for each collection.')
    root, entries = roots[0], []
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs.sort()
        for name in list(dirs):
            path = Path(folder) / name
            if name.lower() in SECRET_DIRS or path.is_symlink():
                entries.append({'path': path.relative_to(root).as_posix() + '/', 'action': 'excluded', 'reason': 'blocked_directory'})
                dirs.remove(name)
        for name in sorted(files):
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            entry = {'path': relative}
            blocked = _path_policy(path, relative)
            if blocked:
                action, reason, metadata, privacy = blocked
                entry.update(action=action, reason=reason, privacy=privacy)
            else:
                try:
                    with _open_source(root, relative) as source:
                        before = _fingerprint(source)
                        action, reason, metadata, privacy = file_policy(path, relative, include_opt_in, source)
                        entry.update(action=action, reason=reason, privacy=privacy)
                        if action == 'include':
                            entry.update(sha256=_sha256_source(source), size=before[2], metadata=metadata)
                            if _fingerprint(source) != before:
                                raise ValueError('Source changed during scan')
                except (OSError, ValueError):
                    entry = {'path': relative, 'action': 'excluded', 'reason': 'unreadable_changed_or_unsafe_source', 'privacy': 'UNCLASSIFIED'}
            entries.append(entry)
    entries.sort(key=lambda entry: entry['path'])
    seen = {}
    for entry in entries:
        if entry['action'] != 'include':
            continue
        digest = entry['sha256']
        if digest in seen:
            primary = seen[digest]
            primary['aliases'].append(entry['path'])
            if entry['privacy'] == 'OPT_IN':
                primary['privacy'] = 'OPT_IN'
            entry.update(action='duplicate', duplicate_of=primary['path'])
        else:
            entry['aliases'] = [entry['path']]
            seen[digest] = entry
    result = {'schema_version': 1, 'source_root': str(root), 'collection': collection,
              'include_opt_in': include_opt_in, 'entries': entries,
              'summary': {action: sum(entry['action'] == action for entry in entries) for action in ('include', 'review', 'excluded', 'duplicate')}}
    result['manifest_sha256'] = _manifest_hash(result)
    return result


def stable_id(prefix, value):
    return prefix + hashlib.sha256(value.encode()).hexdigest()[:48]


def _validate_manifest(manifest):
    if manifest.get('schema_version') != 1 or type(manifest.get('include_opt_in')) is not bool:
        raise ValueError('Unsupported manifest schema or invalid privacy selection')
    collection = manifest.get('collection')
    if not isinstance(collection, str) or not 0 < len(collection) <= 128:
        raise ValueError('Invalid collection')
    entries = manifest.get('entries')
    if not isinstance(entries, list):
        raise ValueError('Invalid manifest entries')
    eligible = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get('action') not in {'include', 'duplicate', 'excluded', 'review'}:
            raise ValueError('Invalid manifest entry')
        if entry['action'] not in {'include', 'duplicate'}:
            continue
        _relative_path(entry.get('path'))
        if entry['path'] in eligible:
            raise ValueError('Duplicate source path in manifest')
        eligible[entry['path']] = entry
        if (entry.get('privacy') not in {'SAFE', 'OPT_IN'} or
                (entry['privacy'] == 'OPT_IN' and not manifest['include_opt_in']) or
                type(entry.get('size')) is not int or not 0 < entry['size'] <= MAX_BYTES or
                not re.fullmatch('[0-9a-f]{64}', str(entry.get('sha256', ''))) or
                not isinstance(entry.get('metadata'), dict)):
            raise ValueError('Invalid source metadata in manifest')
    for entry in eligible.values():
        if entry['action'] == 'duplicate':
            primary = eligible.get(entry.get('duplicate_of'))
            if not primary or primary['action'] != 'include' or primary['sha256'] != entry['sha256']:
                raise ValueError('Invalid duplicate source in manifest')
        else:
            aliases = sorted(path for path, other in eligible.items() if path == entry['path'] or other.get('duplicate_of') == entry['path'])
            if entry.get('aliases') != aliases:
                raise ValueError('Invalid source aliases in manifest')
    if _manifest_hash(manifest) != manifest.get('manifest_sha256'):
        raise ValueError('Manifest changed; generate a new plan.')


def _store_original(source, vault, digest):
    vault.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = vault / digest
    if target.exists() or target.is_symlink():
        if sha256_file(target) != digest:
            raise ValueError('Existing vault original changed; manual recovery required')
        return target
    fd, temporary = tempfile.mkstemp(dir=vault)
    try:
        source.seek(0)
        checksum = hashlib.sha256()
        with os.fdopen(fd, 'wb') as dest:
            while chunk := source.read(1024 * 1024):
                checksum.update(chunk)
                dest.write(chunk)
            dest.flush()
            os.fsync(dest.fileno())
        if checksum.hexdigest() != digest:
            raise ValueError('Source changed during copy')
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target


async def _find_document(session, user_id, collection, entry, selected_paths):
    doc_id = stable_id('doc-', user_id + '\0' + collection + '\0' + entry['path'])
    doc = await session.get(Document, doc_id)
    if doc is not None:
        return doc_id, doc
    origins = (await session.execute(select(DocumentOrigin, Document).join(Document).where(
        Document.user_id == user_id, DocumentOrigin.source_collection == collection))).all()
    for origin, candidate in origins:
        aliases = {origin.source_path, *(origin.metadata_json or {}).get('_import_aliases', [])}
        if aliases.intersection(entry['aliases']):
            if candidate.is_deleted:
                return candidate.id, candidate
            if origin.source_path in selected_paths and origin.source_path != entry['path']:
                continue
            return candidate.id, candidate
    return doc_id, None


def _set_origin(origin, entry, metadata, batch_id):
    relative = entry['path']
    origin.source_path = relative
    origin.privacy_class = entry['privacy']
    parts = {part.lower() for part in PurePosixPath(relative).parts}
    origin.source_kind = 'historical' if '07_bitacora' in parts else ('canonical' if '01_canonico' in parts else 'reference')
    origin.source_date = str(metadata.get('actualizado') or metadata.get('fecha') or metadata.get('periodo') or '') or None
    origin.metadata_json = {**metadata, '_import_aliases': entry['aliases']}
    origin.batch_id = batch_id


async def apply_manifest(manifest, user_id, source_root=None):
    _validate_manifest(manifest)
    if not isinstance(user_id, str) or not 0 < len(user_id) <= 64:
        raise ValueError('Invalid user id')
    root = _root_path(source_root or manifest['source_root'])
    collection, expected = manifest['collection'], manifest['manifest_sha256']
    selected = [entry for entry in manifest['entries'] if entry['action'] == 'include']
    selected_paths = {entry['path'] for entry in selected}
    all_entries = {entry['path']: entry for entry in manifest['entries']}
    batch_id = stable_id('imp-', user_id + '\0' + collection + '\0' + expected)
    report = {'imported': 0, 'unchanged': 0, 'deleted_not_restored': 0,
              'historical_not_restored': 0, 'failed': [], 'batch_id': batch_id}
    async with get_db_context() as session:
        lock_conn = None
        try:
            if session.bind.dialect.name == 'postgresql':
                lock_conn = await session.bind.connect()
                lock_key = int.from_bytes(hashlib.sha256((user_id + '\0' + collection).encode()).digest()[:8], 'big', signed=True)
                await lock_conn.execute(text('SELECT pg_advisory_lock(:key)'), {'key': lock_key})
            batch = await session.get(ImportBatch, batch_id)
            if batch is None:
                batch = ImportBatch(id=batch_id, user_id=user_id, source_collection=collection, manifest_sha256=expected)
                session.add(batch)
            batch.status, batch.completed_at = 'running', None
            await session.commit()
            for entry in selected:
                relative = entry['path']
                try:
                    privacy_classes = set()
                    for alias in entry['aliases']:
                        alias_entry = all_entries[alias]
                        path = root / alias
                        if _path_policy(path, alias):
                            raise ValueError('Source policy changed; rescan required')
                        with _open_source(root, alias) as source:
                            before = _fingerprint(source)
                            action, _, metadata, privacy = file_policy(path, alias, manifest['include_opt_in'], source)
                            if action != 'include' or metadata != alias_entry['metadata']:
                                raise ValueError('Source policy changed; rescan required')
                            privacy_classes.add(privacy)
                            if before[2] != entry['size'] or _sha256_source(source) != entry['sha256'] or _fingerprint(source) != before:
                                raise ValueError('Source bytes changed; rescan required')
                    effective_privacy = 'OPT_IN' if 'OPT_IN' in privacy_classes else 'SAFE'
                    if effective_privacy != entry['privacy']:
                        raise ValueError('Source privacy changed; rescan required')
                    doc_id, doc = await _find_document(session, user_id, collection, entry, selected_paths)
                    if doc is not None and doc.is_deleted:
                        report['deleted_not_restored'] += 1
                        continue
                    latest = (await session.execute(select(DocumentRevision).where(DocumentRevision.document_id == doc_id).order_by(DocumentRevision.version.desc()).limit(1))).scalar_one_or_none()
                    origin = await session.get(DocumentOrigin, doc_id)
                    if latest and latest.sha256_hash == entry['sha256']:
                        if sha256_file(Path(latest.storage_path)) != entry['sha256']:
                            raise ValueError('Existing vault original changed; manual recovery required')
                        if origin is not None:
                            _set_origin(origin, entry, entry['metadata'], batch_id)
                            await session.commit()
                        report['unchanged'] += 1
                        continue
                    # A completed/staged older plan can still have valid bytes.
                    # Replaying it must not implicitly restore a historical
                    # revision or replace the latest provenance and metadata.
                    historical_id = await session.scalar(select(DocumentRevision.id).where(
                        DocumentRevision.document_id == doc_id,
                        DocumentRevision.sha256_hash == entry['sha256'],
                    ).limit(1))
                    if historical_id is not None:
                        report['historical_not_restored'] += 1
                        continue
                    vault = Path(settings.storage_path).resolve() / 'documents' / stable_id('', user_id)
                    with _open_source(root, relative) as source:
                        before = _fingerprint(source)
                        if before[2] != entry['size'] or _sha256_source(source) != entry['sha256']:
                            raise ValueError('Source changed before copy; rescan required')
                        target = _store_original(source, vault, entry['sha256'])
                        if _fingerprint(source) != before:
                            raise ValueError('Source changed during copy; rescan required')
                    now = datetime.now(timezone.utc).replace(tzinfo=None)
                    if doc is None:
                        title = str(entry['metadata'].get('titulo') or Path(relative).stem)[:256]
                        doc = Document(id=doc_id, user_id=user_id, title=title, alias=relative[:256],
                                       doc_type='personal_import', is_deleted=False, created_at=now, updated_at=now)
                        session.add(doc)
                        await session.flush()
                    version = latest.version + 1 if latest else 1
                    rev_id = stable_id('rev-', doc_id + '\0' + str(version) + '\0' + entry['sha256'])
                    session.add(DocumentRevision(id=rev_id, document_id=doc_id, version=version,
                        storage_path=str(target), original_filename=Path(relative).name[:256],
                        mime_type=mimetypes.guess_type(relative)[0] or 'application/octet-stream',
                        file_size_bytes=entry['size'], sha256_hash=entry['sha256'], extraction_status='pending', created_at=now))
                    if origin is None:
                        origin = DocumentOrigin(document_id=doc_id, source_collection=collection)
                        session.add(origin)
                    _set_origin(origin, entry, entry['metadata'], batch_id)
                    doc.updated_at = now
                    session.add(Job(id=stable_id('job-', rev_id), job_type='document_extraction',
                                    payload_json={'document_id': doc_id, 'revision_id': rev_id, 'user_id': user_id},
                                    status='pending', scheduled_at=now, created_at=now))
                    await session.commit()
                    report['imported'] += 1
                except Exception as exc:
                    await session.rollback()
                    report['failed'].append({'path': relative, 'error': type(exc).__name__ + ': ' + str(exc)[:200]})
            batch = await session.get(ImportBatch, batch_id)
            batch.status = 'partial' if report['failed'] else 'completed'
            batch.report_json = report
            batch.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.commit()
        finally:
            if lock_conn is not None:
                try:
                    await lock_conn.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': lock_key})
                finally:
                    await lock_conn.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    scan = sub.add_parser('plan')
    scan.add_argument('roots', nargs='+')
    scan.add_argument('--collection', default='personal-archive')
    scan.add_argument('--include-opt-in', action='store_true')
    scan.add_argument('--output', required=True)
    apply = sub.add_parser('apply')
    apply.add_argument('manifest')
    apply.add_argument('--user-id', required=True)
    apply.add_argument('--source-root')
    args = parser.parse_args()
    if args.command == 'plan':
        result = scan_archive(args.roots, args.collection, args.include_opt_in)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps(result['summary']))
    else:
        manifest = json.loads(Path(args.manifest).read_text())
        result = asyncio.run(apply_manifest(manifest, args.user_id, args.source_root))
        print(json.dumps(result, ensure_ascii=False))
        if result['failed']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()

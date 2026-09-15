"""Synthetic archive fixtures; never read personal files or credentials."""
import copy
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.importing import personal
from app.models.canonical import Document, DocumentOrigin, DocumentRevision, ImportBatch, Job


def write_context(root, relative='PersonalLLM/01_CANONICO/PERFIL.md', *, privacy='SAFE', body='Perfil de ejemplo.', extra=''):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'---\ntitulo: Perfil sintético\nsensibilidad: {privacy}\nactualizado: 2026-08-31\nrevisar_el: 2026-09-07\nfuentes: [TEST-001]\n{extra}---\n{body}\n')
    return path


async def count(session, model):
    return await session.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_apply_replay_revision_and_deleted_document(test_engine, db_session, tmp_path, monkeypatch):
    root = tmp_path / 'archive'
    source = write_context(root)
    original = source.read_bytes()
    monkeypatch.setattr(personal.settings, 'storage_path', str(tmp_path / 'vault'))
    plan = personal.scan_archive([root, root / 'PersonalLLM'])
    first = await personal.apply_manifest(plan, 'owner')
    assert first['imported'] == 1 and not first['failed']
    doc = (await db_session.execute(select(Document))).scalar_one()
    origin = await db_session.get(DocumentOrigin, doc.id)
    revision = (await db_session.execute(select(DocumentRevision))).scalar_one()
    assert doc.title == 'Perfil sintético'
    assert doc.alias == 'PersonalLLM/01_CANONICO/PERFIL.md'
    assert origin.source_date == '2026-08-31'
    assert origin.privacy_class == 'SAFE' and origin.source_kind == 'canonical'
    assert origin.metadata_json['revisar_el'] == '2026-09-07'
    assert origin.metadata_json['fuentes'] == ['TEST-001']
    assert Path(revision.storage_path).read_bytes() == original
    assert Path(revision.storage_path).stat().st_mode & 0o777 == 0o600
    assert source.read_bytes() == original
    replay = await personal.apply_manifest(plan, 'owner')
    assert replay['unchanged'] == 1 and replay['batch_id'] == first['batch_id']
    assert await count(db_session, DocumentRevision) == 1
    assert await count(db_session, Job) == 1
    write_context(root, body='Perfil actualizado con información sintética.')
    updated = await personal.apply_manifest(personal.scan_archive([root]), 'owner')
    assert updated['imported'] == 1 and not updated['failed']
    assert await count(db_session, Document) == 1
    assert await count(db_session, DocumentRevision) == 2
    assert await count(db_session, Job) == 2
    versions = (await db_session.execute(select(DocumentRevision.version).order_by(DocumentRevision.version))).scalars().all()
    assert versions == [1, 2]
    doc.is_deleted = True
    await db_session.commit()
    write_context(root, body='Otra revisión sintética posterior a borrado.')
    deleted = await personal.apply_manifest(personal.scan_archive([root]), 'owner')
    assert deleted['deleted_not_restored'] == 1 and not deleted['failed']
    assert await count(db_session, DocumentRevision) == 2
    batch = await db_session.get(ImportBatch, deleted['batch_id'])
    assert batch.status == 'completed' and batch.completed_at is not None


@pytest.mark.asyncio
async def test_mutated_source_has_partial_batch_and_replay_recovers(test_engine, db_session, tmp_path, monkeypatch):
    source = write_context(tmp_path / 'archive')
    original = source.read_bytes()
    monkeypatch.setattr(personal.settings, 'storage_path', str(tmp_path / 'vault'))
    plan = personal.scan_archive([source.parents[2]])
    source.write_bytes(original + b'Changed after review')
    failed = await personal.apply_manifest(plan, 'owner')
    assert failed['imported'] == 0 and len(failed['failed']) == 1
    assert await count(db_session, Document) == 0
    batch = await db_session.get(ImportBatch, failed['batch_id'])
    assert batch.status == 'partial'
    source.write_bytes(original)
    recovered = await personal.apply_manifest(plan, 'owner')
    assert recovered['imported'] == 1 and not recovered['failed']
    await db_session.refresh(batch)
    assert batch.status == 'completed'
    assert batch.report_json['imported'] == 1


def test_exclusions_precede_open_and_private_originals_require_opt_in(tmp_path, monkeypatch):
    root = tmp_path / 'archive'
    write_context(root)
    for relative in ('seguridadDigital/recoveryCodes.txt', 'private.key', 'identidad/passport.pdf',
                     'fiscal/statement.pdf', 'PersonalLLM/AGENTS.md', 'notes/LEEME.txt',
                     'PersonalLLM/98_BOVEDA_PRIVADA_NO_COMPARTIR/anything.md'):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'SYNTHETIC PLACEHOLDER ONLY')
    write_context(root, 'PersonalLLM/PRIVATE.md', privacy='OPT_IN')
    write_context(root, 'PersonalLLM/NEVER.md', privacy='NEVER_UPLOAD')
    original_open = personal._open_source
    opened = []
    def guarded_open(root_path, relative):
        opened.append(relative)
        assert 'seguridadDigital' not in relative
        assert '98_BOVEDA' not in relative
        assert not relative.endswith('.key')
        return original_open(root_path, relative)
    monkeypatch.setattr(personal, '_open_source', guarded_open)
    safe = personal.scan_archive([root])
    by_path = {entry['path']: entry for entry in safe['entries']}
    assert by_path['identidad/passport.pdf']['action'] == 'review'
    assert by_path['fiscal/statement.pdf']['action'] == 'review'
    assert by_path['PersonalLLM/NEVER.md']['action'] == 'excluded'
    assert by_path['notes/LEEME.txt']['action'] == 'excluded'
    assert 'PersonalLLM/AGENTS.md' not in opened
    private = personal.scan_archive([root], include_opt_in=True)
    assert all(entry['privacy'] == 'OPT_IN' for entry in private['entries']
               if entry['path'] in {'identidad/passport.pdf', 'fiscal/statement.pdf'})


@pytest.mark.asyncio
async def test_deduplicates_bytes_preserves_aliases_and_changed_alias_cannot_sneak_in(test_engine, db_session, tmp_path, monkeypatch):
    root = tmp_path / 'archive'
    first = write_context(root, 'a.md')
    second = root / 'b.md'
    second.write_bytes(first.read_bytes())
    monkeypatch.setattr(personal.settings, 'storage_path', str(tmp_path / 'vault'))
    plan = personal.scan_archive([root])
    assert plan['summary']['include'] == 1 and plan['summary']['duplicate'] == 1
    assert plan['entries'][0]['aliases'] == ['a.md', 'b.md']
    result = await personal.apply_manifest(plan, 'owner')
    assert result['imported'] == 1
    origin = (await db_session.execute(select(DocumentOrigin))).scalar_one()
    assert origin.metadata_json['_import_aliases'] == ['a.md', 'b.md']
    second.write_text('Changed duplicate')
    result = await personal.apply_manifest(plan, 'owner')
    assert len(result['failed']) == 1
    assert await count(db_session, DocumentRevision) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('directory', [False, True])
async def test_apply_rejects_file_or_directory_symlink_replacement(test_engine, db_session, tmp_path, monkeypatch, directory):
    root = tmp_path / 'archive'
    source = write_context(root)
    monkeypatch.setattr(personal.settings, 'storage_path', str(tmp_path / 'vault'))
    plan = personal.scan_archive([root])
    if directory:
        parent = source.parent
        moved = parent.with_name('moved')
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
    else:
        target = tmp_path / 'external.md'
        target.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(target)
    result = await personal.apply_manifest(plan, 'owner')
    assert result['imported'] == 0 and len(result['failed']) == 1
    assert await count(db_session, Document) == 0


def test_scan_rejects_symlink_root_and_skips_file_symlink(tmp_path):
    root = tmp_path / 'archive'
    source = write_context(root)
    link = tmp_path / 'link'
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        personal.scan_archive([link])
    (root / 'link.md').symlink_to(source)
    plan = personal.scan_archive([root])
    assert next(entry for entry in plan['entries'] if entry['path'] == 'link.md')['action'] == 'excluded'


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['../escape.md', '/tmp/escape.md', 'C:/escape.md', 'folder/../escape.md', 'folder\\escape.md'])
async def test_apply_rejects_manifest_traversal_before_io(tmp_path, path):
    root = tmp_path / 'archive'
    write_context(root, 'valid.md')
    plan = personal.scan_archive([root])
    plan['entries'][0]['path'] = path
    plan['entries'][0]['aliases'] = [path]
    plan['manifest_sha256'] = personal._manifest_hash(plan)
    with pytest.raises(ValueError, match='path'):
        await personal.apply_manifest(plan, 'owner')


@pytest.mark.asyncio
async def test_manifest_privacy_flag_tampering_is_detected(tmp_path):
    root = tmp_path / 'archive'
    write_context(root)
    plan = personal.scan_archive([root])
    changed = copy.deepcopy(plan)
    changed['include_opt_in'] = True
    with pytest.raises(ValueError, match='Manifest changed'):
        await personal.apply_manifest(changed, 'owner')


@pytest.mark.asyncio
async def test_deleted_duplicate_aliases_remain_deleted_after_sources_split(test_engine, db_session, tmp_path, monkeypatch):
    root = tmp_path / 'archive'
    first = write_context(root, 'a.md')
    (root / 'b.md').write_bytes(first.read_bytes())
    monkeypatch.setattr(personal.settings, 'storage_path', str(tmp_path / 'vault'))
    await personal.apply_manifest(personal.scan_archive([root]), 'owner')
    doc = (await db_session.execute(select(Document))).scalar_one()
    doc.is_deleted = True
    await db_session.commit()
    write_context(root, 'b.md', body='Changed synthetic alias after deletion.')
    replay = await personal.apply_manifest(personal.scan_archive([root]), 'owner')
    assert replay['deleted_not_restored'] == 2 and not replay['failed']
    assert await count(db_session, Document) == 1


@pytest.mark.asyncio
async def test_new_sorted_duplicate_keeps_existing_document_identity(test_engine, db_session, tmp_path, monkeypatch):
    root = tmp_path / 'archive'
    source = write_context(root, 'b.md')
    monkeypatch.setattr(personal.settings, 'storage_path', str(tmp_path / 'vault'))
    await personal.apply_manifest(personal.scan_archive([root]), 'owner')
    doc_id = (await db_session.execute(select(Document.id))).scalar_one()
    (root / 'a.md').write_bytes(source.read_bytes())
    replay = await personal.apply_manifest(personal.scan_archive([root]), 'owner')
    assert replay['unchanged'] == 1 and not replay['failed']
    assert await count(db_session, Document) == 1
    assert (await db_session.execute(select(Document.id))).scalar_one() == doc_id


def test_never_upload_header_stops_before_body_read(tmp_path, monkeypatch):
    source = write_context(tmp_path / 'archive', privacy='NEVER_UPLOAD', body='Synthetic unapproved content.')
    def forbidden_hash(stream):
        raise AssertionError('NEVER_UPLOAD must not be hashed')
    monkeypatch.setattr(personal, '_sha256_source', forbidden_hash)
    plan = personal.scan_archive([source.parents[2]], include_opt_in=True)
    assert plan['summary']['include'] == 0
    assert plan['entries'][0]['reason'] == 'never_upload_metadata'


@pytest.mark.asyncio
async def test_replay_older_staging_preserves_latest_revision_and_provenance(test_engine, db_session, tmp_path, monkeypatch):
    # Both batches remain valid immutable snapshots, as on a storage host.
    stage_a, stage_b = tmp_path / 'stage_a', tmp_path / 'stage_b'
    write_context(stage_a, body='Revision A synthetic fact.')
    source_b = write_context(stage_b, body='Revision B supersedes A.', privacy='OPT_IN')
    source_b.write_text(source_b.read_text().replace('2026-08-31', '2026-09-15'))
    monkeypatch.setattr(personal.settings, 'storage_path', str(tmp_path / 'vault'))
    plan_a = personal.scan_archive([stage_a], include_opt_in=True)
    plan_b = personal.scan_archive([stage_b], include_opt_in=True)
    imported_a = await personal.apply_manifest(plan_a, 'owner')
    imported_b = await personal.apply_manifest(plan_b, 'owner')
    assert imported_a['imported'] == imported_b['imported'] == 1
    doc = (await db_session.execute(select(Document))).scalar_one()
    origin = await db_session.get(DocumentOrigin, doc.id)
    latest = (await db_session.execute(select(DocumentRevision).order_by(DocumentRevision.version.desc()).limit(1))).scalar_one()
    expected_origin = (origin.source_date, origin.privacy_class, origin.batch_id, copy.deepcopy(origin.metadata_json))
    expected_updated = doc.updated_at
    assert latest.version == 2 and latest.sha256_hash == plan_b['entries'][0]['sha256']

    replay = await personal.apply_manifest(plan_a, 'owner')
    assert replay['batch_id'] == imported_a['batch_id']
    assert replay['historical_not_restored'] == 1
    assert replay['imported'] == replay['unchanged'] == 0
    assert not replay['failed']
    assert await count(db_session, DocumentRevision) == 2
    assert await count(db_session, Job) == 2
    await db_session.refresh(origin)
    await db_session.refresh(doc)
    assert (origin.source_date, origin.privacy_class, origin.batch_id, origin.metadata_json) == expected_origin
    assert doc.updated_at == expected_updated
    assert Path(latest.storage_path).read_bytes() == source_b.read_bytes()
    batch_a = await db_session.get(ImportBatch, replay['batch_id'])
    assert batch_a.status == 'completed'
    assert batch_a.report_json['historical_not_restored'] == 1

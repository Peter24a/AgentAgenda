import hashlib
import os
import pytest
import pytest_asyncio
from app.config import settings


@pytest_asyncio.fixture
async def auth_headers(client):
    ch = await client.post("/v1/auth/challenge")
    code = ch.json()["pairing_code"]
    pair = await client.post(
        "/v1/auth/pair",
        json={
            "pairing_code": code,
            "device_name": "Pixel Doc Test",
            "platform": "android",
        },
    )
    token = pair.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_document_upload_success_and_download(client, auth_headers):
    # 1. Contenido de prueba
    content = b"%PDF-1.4 Mock PDF Content For Vault Testing With Cryptographic SHA-256 Verification"
    expected_size = len(content)
    expected_sha256 = hashlib.sha256(content).hexdigest()

    # 2. Iniciar sesión de carga
    init_res = await client.post(
        "/v1/documents/uploads",
        json={
            "filename": "constancia_sat.pdf",
            "mime_type": "application/pdf",
            "expected_size_bytes": expected_size,
            "expected_sha256": expected_sha256,
            "title": "Constancia de Situación Fiscal",
            "alias": "SAT 2026",
            "doc_type": "constancia",
            "issuer": "SAT",
            "holder": "Pedro Perez",
        },
        headers=auth_headers,
    )
    assert init_res.status_code in (200, 201)
    init_data = init_res.json()
    upload_id = init_data["upload_id"]
    assert init_data["status"] == "pending"

    # 3. Subir contenido en dos chunks
    chunk1 = content[:30]
    chunk2 = content[30:]

    up1 = await client.put(
        f"/v1/documents/uploads/{upload_id}/content",
        content=chunk1,
        headers={**auth_headers, "Content-Type": "application/octet-stream"},
    )
    assert up1.status_code == 200
    assert up1.json()["uploaded_bytes"] == 30

    up2 = await client.put(
        f"/v1/documents/uploads/{upload_id}/content",
        content=chunk2,
        headers={**auth_headers, "Content-Type": "application/octet-stream"},
    )
    assert up2.status_code == 200
    assert up2.json()["uploaded_bytes"] == expected_size

    # 4. Consultar estado intermedio
    status_res = await client.get(f"/v1/documents/uploads/{upload_id}", headers=auth_headers)
    assert status_res.status_code == 200
    assert status_res.json()["uploaded_bytes"] == expected_size

    # 5. Finalizar subida y verificar publicación
    complete_res = await client.post(
        f"/v1/documents/uploads/{upload_id}/complete",
        headers=auth_headers,
    )
    assert complete_res.status_code == 200
    doc_data = complete_res.json()
    doc_id = doc_data["id"]
    assert doc_data["title"] == "Constancia de Situación Fiscal"
    assert doc_data["issuer"] == "SAT"
    assert len(doc_data["revisions"]) == 1
    rev = doc_data["revisions"][0]
    assert rev["version"] == 1
    assert rev["sha256_hash"] == expected_sha256
    assert rev["file_size_bytes"] == expected_size

    # 6. Descargar versión 1 del archivo
    dl_res = await client.get(
        f"/v1/documents/{doc_id}/versions/1/download",
        headers=auth_headers,
    )
    assert dl_res.status_code == 200
    assert dl_res.content == content
    assert dl_res.headers["content-type"] == "application/pdf"

    # 7. Descargar última versión directa
    dl_latest = await client.get(
        f"/v1/documents/{doc_id}/download",
        headers=auth_headers,
    )
    assert dl_latest.status_code == 200
    assert dl_latest.content == content


@pytest.mark.asyncio
async def test_document_upload_sha256_mismatch(client, auth_headers):
    content = b"Some valid bytes for testing failure"
    fake_sha256 = "0" * 64

    init_res = await client.post(
        "/v1/documents/uploads",
        json={
            "filename": "fake.pdf",
            "mime_type": "application/pdf",
            "expected_size_bytes": len(content),
            "expected_sha256": fake_sha256,
            "title": "Documento con Hash Invalido",
        },
        headers=auth_headers,
    )
    assert init_res.status_code in (200, 201)
    upload_id = init_res.json()["upload_id"]

    await client.put(
        f"/v1/documents/uploads/{upload_id}/content",
        content=content,
        headers={**auth_headers, "Content-Type": "application/octet-stream"},
    )

    complete_res = await client.post(
        f"/v1/documents/uploads/{upload_id}/complete",
        headers=auth_headers,
    )
    assert complete_res.status_code == 400
    assert "Discrepancia de integridad criptográfica" in complete_res.json()["detail"]


@pytest.mark.asyncio
async def test_document_upload_size_mismatch(client, auth_headers):
    init_res = await client.post(
        "/v1/documents/uploads",
        json={
            "filename": "incomplete.pdf",
            "mime_type": "application/pdf",
            "expected_size_bytes": 1000,
            "title": "Documento Incompleto",
        },
        headers=auth_headers,
    )
    assert init_res.status_code in (200, 201)
    upload_id = init_res.json()["upload_id"]

    # Subir menos bytes de los esperados
    await client.put(
        f"/v1/documents/uploads/{upload_id}/content",
        content=b"Solo 15 bytes!!",
        headers={**auth_headers, "Content-Type": "application/octet-stream"},
    )

    complete_res = await client.post(
        f"/v1/documents/uploads/{upload_id}/complete",
        headers=auth_headers,
    )
    assert complete_res.status_code == 400
    assert "Discrepancia de tamaño de archivo" in complete_res.json()["detail"]


@pytest.mark.asyncio
async def test_document_versioning_search_and_soft_delete(client, auth_headers):
    # 1. Crear documento inicial versión 1
    v1_bytes = b"Version 1 content"
    init_v1 = await client.post(
        "/v1/documents/uploads",
        json={
            "filename": "pasaporte.pdf",
            "mime_type": "application/pdf",
            "expected_size_bytes": len(v1_bytes),
            "title": "Pasaporte Mexicano",
            "alias": "PASSPORT-MEX",
            "doc_type": "identificacion",
            "issuer": "SRE",
        },
        headers=auth_headers,
    )
    u1_id = init_v1.json()["upload_id"]
    await client.put(f"/v1/documents/uploads/{u1_id}/content", content=v1_bytes, headers=auth_headers)
    res_v1 = await client.post(f"/v1/documents/uploads/{u1_id}/complete", headers=auth_headers)
    doc_id = res_v1.json()["id"]

    # 2. Subir versión 2 vinculada al mismo document_id
    v2_bytes = b"Version 2 renewed passport content"
    init_v2 = await client.post(
        "/v1/documents/uploads",
        json={
            "filename": "pasaporte_renovado.pdf",
            "mime_type": "application/pdf",
            "expected_size_bytes": len(v2_bytes),
            "document_id": doc_id,
        },
        headers=auth_headers,
    )
    u2_id = init_v2.json()["upload_id"]
    await client.put(f"/v1/documents/uploads/{u2_id}/content", content=v2_bytes, headers=auth_headers)
    res_v2 = await client.post(f"/v1/documents/uploads/{u2_id}/complete", headers=auth_headers)
    assert res_v2.status_code == 200
    doc_updated = res_v2.json()
    assert doc_updated["id"] == doc_id
    assert len(doc_updated["revisions"]) == 2
    versions = [r["version"] for r in doc_updated["revisions"]]
    assert 1 in versions and 2 in versions

    # 3. Búsqueda por texto (query) y por doc_type
    search_q = await client.get("/v1/documents?q=Mexicano", headers=auth_headers)
    assert search_q.status_code == 200
    assert search_q.json()["total"] >= 1

    search_type = await client.get("/v1/documents?doc_type=identificacion", headers=auth_headers)
    assert search_type.status_code == 200
    assert any(d["id"] == doc_id for d in search_type.json()["documents"])

    # 4. Actualizar metadatos
    patch_res = await client.patch(
        f"/v1/documents/{doc_id}",
        json={"alias": "PASSPORT-MEX-2026-RENEWED"},
        headers=auth_headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["alias"] == "PASSPORT-MEX-2026-RENEWED"

    # 5. Soft delete
    del_res = await client.delete(f"/v1/documents/{doc_id}", headers=auth_headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Verificar que ya no aparece en listado activo
    list_after = await client.get("/v1/documents", headers=auth_headers)
    assert not any(d["id"] == doc_id for d in list_after.json()["documents"])

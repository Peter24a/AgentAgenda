import hashlib
import os
import tempfile
import pytest
from httpx import AsyncClient

from app.config import settings


@pytest.fixture(autouse=True)
def setup_temp_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_path", str(tmp_path / "storage"))
    os.makedirs(str(tmp_path / "storage" / "documents"), exist_ok=True)
    os.makedirs(str(tmp_path / "storage" / "temp"), exist_ok=True)


@pytest.mark.asyncio
async def test_upload_session_lifecycle(client: AsyncClient):
    sample_content = b"PDF Mock Content for RFC and Tax Info"
    content_hash = hashlib.sha256(sample_content).hexdigest()
    content_size = len(sample_content)

    # 1. Iniciar sesión de carga
    init_res = await client.post(
        "/v1/documents/uploads",
        json={
            "filename": "constancia_fiscal_2026.pdf",
            "mime_type": "application/pdf",
            "expected_size_bytes": content_size,
            "expected_sha256": content_hash,
            "title": "Constancia de Situación Fiscal",
            "alias": "RFC",
            "doc_type": "fiscal",
            "issuer": "SAT",
            "holder": "Pedro Perez",
        },
    )
    assert init_res.status_code == 200
    init_data = init_res.json()
    upload_id = init_data["upload_id"]
    assert init_data["status"] == "pending"
    assert init_data["expected_size_bytes"] == content_size

    # 2. Consultar estado de subida
    status_res = await client.get(f"/v1/documents/uploads/{upload_id}")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "pending"

    # 3. Subir en chunks binarios
    chunk1 = sample_content[:10]
    chunk2 = sample_content[10:]
    put_res1 = await client.put(
        f"/v1/documents/uploads/{upload_id}/content",
        content=chunk1,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert put_res1.status_code == 200
    assert put_res1.json()["uploaded_bytes"] == len(chunk1)

    put_res2 = await client.put(
        f"/v1/documents/uploads/{upload_id}/content",
        content=chunk2,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert put_res2.status_code == 200
    assert put_res2.json()["uploaded_bytes"] == content_size

    # 4. Finalizar carga y publicar documento
    complete_res = await client.post(f"/v1/documents/uploads/{upload_id}/complete")
    assert complete_res.status_code == 200
    doc_data = complete_res.json()
    assert doc_data["title"] == "Constancia de Situación Fiscal"
    assert doc_data["alias"] == "RFC"
    assert doc_data["doc_type"] == "fiscal"
    assert doc_data["issuer"] == "SAT"
    assert len(doc_data["revisions"]) == 1

    rev = doc_data["revisions"][0]
    assert rev["version"] == 1
    assert rev["sha256_hash"] == content_hash
    assert rev["file_size_bytes"] == content_size
    assert rev["original_filename"] == "constancia_fiscal_2026.pdf"


@pytest.mark.asyncio
async def test_upload_sha256_mismatch_aborts(client: AsyncClient):
    sample_content = b"Authentic Document Content"
    fake_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"

    init_res = await client.post(
        "/v1/documents/uploads",
        json={
            "filename": "fake_doc.pdf",
            "mime_type": "application/pdf",
            "expected_size_bytes": len(sample_content),
            "expected_sha256": fake_sha256,
            "title": "Documento con Hash Falso",
        },
    )
    assert init_res.status_code == 200
    upload_id = init_res.json()["upload_id"]

    # Subir contenido
    await client.put(
        f"/v1/documents/uploads/{upload_id}/content",
        content=sample_content,
        headers={"Content-Type": "application/octet-stream"},
    )

    # Completar debe fallar por discrepancia de integridad
    complete_res = await client.post(f"/v1/documents/uploads/{upload_id}/complete")
    assert complete_res.status_code == 400
    assert "Discrepancia de integridad" in complete_res.json()["detail"]


@pytest.mark.asyncio
async def test_upload_size_mismatch_aborts(client: AsyncClient):
    sample_content = b"Short"

    init_res = await client.post(
        "/v1/documents/uploads",
        json={
            "filename": "mismatch.pdf",
            "mime_type": "application/pdf",
            "expected_size_bytes": 100,  # Esperado 100 pero solo enviamos 5 bytes
            "title": "Size Mismatch Doc",
        },
    )
    assert init_res.status_code == 200
    upload_id = init_res.json()["upload_id"]

    await client.put(
        f"/v1/documents/uploads/{upload_id}/content",
        content=sample_content,
    )

    complete_res = await client.post(f"/v1/documents/uploads/{upload_id}/complete")
    assert complete_res.status_code == 400
    assert "Discrepancia de tamaño" in complete_res.json()["detail"]


@pytest.mark.asyncio
async def test_document_versioning_and_download(client: AsyncClient):
    content_v1 = b"Version 1 Content: INE 2024"
    hash_v1 = hashlib.sha256(content_v1).hexdigest()

    # 1. Subir Versión 1
    init_v1 = await client.post(
        "/v1/documents/uploads",
        json={
            "filename": "ine_2024.pdf",
            "mime_type": "application/pdf",
            "expected_size_bytes": len(content_v1),
            "expected_sha256": hash_v1,
            "title": "Identificación Oficial INE",
            "doc_type": "identificacion",
        },
    )
    up_id1 = init_v1.json()["upload_id"]
    await client.put(f"/v1/documents/uploads/{up_id1}/content", content=content_v1)
    complete_v1 = await client.post(f"/v1/documents/uploads/{up_id1}/complete")
    assert complete_v1.status_code == 200
    doc_id = complete_v1.json()["id"]

    # 2. Subir Versión 2 vinculada al mismo doc_id
    content_v2 = b"Version 2 Content: INE Renovada 2026 Vigente"
    hash_v2 = hashlib.sha256(content_v2).hexdigest()

    init_v2 = await client.post(
        "/v1/documents/uploads",
        json={
            "document_id": doc_id,
            "filename": "ine_2026.pdf",
            "mime_type": "application/pdf",
            "expected_size_bytes": len(content_v2),
            "expected_sha256": hash_v2,
        },
    )
    up_id2 = init_v2.json()["upload_id"]
    await client.put(f"/v1/documents/uploads/{up_id2}/content", content=content_v2)
    complete_v2 = await client.post(f"/v1/documents/uploads/{up_id2}/complete")
    assert complete_v2.status_code == 200
    doc_v2 = complete_v2.json()

    # Verificar que tiene 2 revisiones
    assert len(doc_v2["revisions"]) == 2
    assert doc_v2["revisions"][0]["version"] == 1
    assert doc_v2["revisions"][1]["version"] == 2

    # 3. Descarga de la última versión (debe ser la v2)
    dl_latest = await client.get(f"/v1/documents/{doc_id}/download")
    assert dl_latest.status_code == 200
    assert dl_latest.content == content_v2

    # 4. Descarga explícita de la versión 1
    dl_v1 = await client.get(f"/v1/documents/{doc_id}/versions/1/download")
    assert dl_v1.status_code == 200
    assert dl_v1.content == content_v1

    # 5. Descarga de una versión inexistente
    dl_v99 = await client.get(f"/v1/documents/{doc_id}/versions/99/download")
    assert dl_v99.status_code == 404


@pytest.mark.asyncio
async def test_document_catalog_search_and_deletion(client: AsyncClient):
    # Crear Documento A (SAT)
    c_sat = b"SAT Taxes Content"
    up_sat = (
        await client.post(
            "/v1/documents/uploads",
            json={
                "filename": "sat_opinion.pdf",
                "mime_type": "application/pdf",
                "expected_size_bytes": len(c_sat),
                "title": "Opinion de Cumplimiento",
                "alias": "SAT Positiva",
                "doc_type": "fiscal",
                "issuer": "SAT",
            },
        )
    ).json()["upload_id"]
    await client.put(f"/v1/documents/uploads/{up_sat}/content", content=c_sat)
    doc_sat = (await client.post(f"/v1/documents/uploads/{up_sat}/complete")).json()

    # Crear Documento B (Pasaporte)
    c_pas = b"Passport Content"
    up_pas = (
        await client.post(
            "/v1/documents/uploads",
            json={
                "filename": "pasaporte_mexicano.pdf",
                "mime_type": "application/pdf",
                "expected_size_bytes": len(c_pas),
                "title": "Pasaporte Ordinario",
                "alias": "Pasaporte Viaje",
                "doc_type": "viaje",
                "issuer": "SRE",
            },
        )
    ).json()["upload_id"]
    await client.put(f"/v1/documents/uploads/{up_pas}/content", content=c_pas)
    doc_pas = (await client.post(f"/v1/documents/uploads/{up_pas}/complete")).json()

    # Búsqueda por texto (SAT)
    search_sat = await client.get("/v1/documents?q=cumplimiento")
    assert search_sat.status_code == 200
    assert search_sat.json()["total"] == 1
    assert search_sat.json()["documents"][0]["id"] == doc_sat["id"]

    # Búsqueda por emisor SRE
    search_sre = await client.get("/v1/documents?q=sre")
    assert search_sre.status_code == 200
    assert search_sre.json()["total"] == 1
    assert search_sre.json()["documents"][0]["id"] == doc_pas["id"]

    # Filtro por doc_type
    filter_type = await client.get("/v1/documents?doc_type=viaje")
    assert filter_type.status_code == 200
    assert filter_type.json()["total"] == 1
    assert filter_type.json()["documents"][0]["id"] == doc_pas["id"]

    # Eliminación de Documento
    del_res = await client.delete(f"/v1/documents/{doc_pas['id']}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Ya no debe aparecer en listado
    list_after = await client.get("/v1/documents")
    assert list_after.json()["total"] == 1
    assert list_after.json()["documents"][0]["id"] == doc_sat["id"]

    # Consultar detalle del eliminado devuelve 404
    get_deleted = await client.get(f"/v1/documents/{doc_pas['id']}")
    assert get_deleted.status_code == 404

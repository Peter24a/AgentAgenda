import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_scope
from app.models.auth import AuthContext
from app.models.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdateRequest,
    UploadInitRequest,
    UploadSessionResponse,
)
from app.services.document_catalog import document_catalog
from app.services.document_storage import document_storage

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.get("/search", summary="Buscar fragmentos documentales con procedencia")
async def search_document_content(
    q: str = Query(..., min_length=2, max_length=500),
    limit: int = Query(5, ge=1, le=10),
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("documents:read")),
):
    from app.services.document_retrieval import search_documents
    return {"results": await search_documents(session, auth.user_id, q, limit=limit)}


@router.post(
    "/uploads",
    response_model=UploadSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Iniciar sesión de carga de documento",
    description="Crea una sesión de carga en la bóveda con metadatos y cálculo esperado de hash.",
)
async def start_upload(
    req: UploadInitRequest,
    auth: AuthContext = Depends(require_scope("documents:write")),
):
    try:
        session_info = document_storage.start_upload_session(
            user_id=auth.user_id,
            req=req,
        )
        return session_info
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put(
    "/uploads/{upload_id}/content",
    summary="Cargar contenido binario a una sesión de subida",
    description="Transfiere bytes en streaming hacia el archivo temporal de la sesión.",
)
async def upload_content(
    upload_id: str,
    request: Request,
    auth: AuthContext = Depends(require_scope("documents:write")),
):
    try:
        total_uploaded = 0
        async for chunk in request.stream():
            if chunk:
                total_uploaded = await document_storage.append_chunk(
                    upload_id=upload_id,
                    user_id=auth.user_id,
                    chunk=chunk,
                )
        return {"upload_id": upload_id, "uploaded_bytes": total_uploaded}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/uploads/{upload_id}",
    response_model=UploadSessionResponse,
    summary="Consultar estado y progreso de la sesión de carga",
)
async def get_upload_status(
    upload_id: str,
    auth: AuthContext = Depends(require_scope("documents:read")),
):
    session_info = document_storage.get_upload_session(
        upload_id=upload_id,
        user_id=auth.user_id,
    )
    if not session_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sesión de carga '{upload_id}' no encontrada",
        )
    return session_info


@router.post(
    "/uploads/{upload_id}/complete",
    response_model=DocumentResponse,
    summary="Finalizar sesión de carga y publicar revisión en la bóveda",
    description="Verifica tamaño y hash SHA-256 criptográfico. Mueve el archivo a la bóveda privada y registra la revisión.",
)
async def complete_upload(
    upload_id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("documents:write")),
):
    try:
        doc, rev = await document_storage.complete_upload(
            session_db=session,
            upload_id=upload_id,
            user_id=auth.user_id,
        )
        doc_details = await document_catalog.get_document(session, auth.user_id, doc.id)
        if not doc_details:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al recuperar la ficha del documento recién publicado",
            )
        return doc_details
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="Listado y búsqueda en el catálogo documental",
)
async def list_documents(
    q: Optional[str] = Query(None, description="Búsqueda por texto en título, alias, emisor o titular"),
    doc_type: Optional[str] = Query(None, description="Filtro por categoría documental"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("documents:read")),
):
    return await document_catalog.list_documents(
        session=session,
        user_id=auth.user_id,
        query=q,
        doc_type=doc_type,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{id}",
    response_model=DocumentResponse,
    summary="Ficha documental y revisiones históricas",
)
async def get_document(
    id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("documents:read")),
):
    doc = await document_catalog.get_document(session, auth.user_id, id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento '{id}' no encontrado",
        )
    return doc


@router.patch(
    "/{id}",
    response_model=DocumentResponse,
    summary="Actualizar metadatos de un documento",
)
async def update_document(
    id: str,
    req: DocumentUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("documents:write")),
):
    doc = await document_catalog.get_document_by_id(session, auth.user_id, id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento '{id}' no encontrado",
        )

    if req.title is not None:
        doc.title = req.title
    if req.alias is not None:
        doc.alias = req.alias
    if req.doc_type is not None:
        doc.doc_type = req.doc_type
    if req.issuer is not None:
        doc.issuer = req.issuer
    if req.holder is not None:
        doc.holder = req.holder
    if req.issue_date is not None:
        doc.issue_date = req.issue_date
    if req.expiry_date is not None:
        doc.expiry_date = req.expiry_date

    await session.commit()
    doc_details = await document_catalog.get_document(session, auth.user_id, id)
    return doc_details


@router.delete(
    "/{id}",
    summary="Eliminar lógicamente un documento del catálogo",
)
async def delete_document(
    id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("documents:write")),
):
    success = await document_catalog.delete_document(session, auth.user_id, id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento '{id}' no encontrado",
        )
    return {"status": "deleted", "id": id}


@router.get(
    "/{id}/versions/{version}/download",
    summary="Descarga autenticada de una versión específica",
)
async def download_document_version(
    id: str,
    version: int,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("documents:read")),
):
    rev = await document_catalog.get_revision_for_download(
        session=session,
        user_id=auth.user_id,
        document_id=id,
        version=version,
    )
    if not rev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento '{id}' o versión '{version}' no encontrados",
        )
    if not os.path.exists(rev.storage_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El archivo binario no se encuentra en el almacenamiento del servidor",
        )

    return FileResponse(
        path=rev.storage_path,
        media_type=rev.mime_type or "application/octet-stream",
        filename=rev.original_filename,
    )


@router.get(
    "/{id}/download",
    summary="Descarga autenticada de la última versión del documento",
)
async def download_document_latest(
    id: str,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("documents:read")),
):
    rev = await document_catalog.get_revision_for_download(
        session=session,
        user_id=auth.user_id,
        document_id=id,
        version=None,
    )
    if not rev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento '{id}' no encontrado o no contiene revisiones",
        )
    if not os.path.exists(rev.storage_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El archivo binario no se encuentra en el almacenamiento del servidor",
        )

    return FileResponse(
        path=rev.storage_path,
        media_type=rev.mime_type or "application/octet-stream",
        filename=rev.original_filename,
    )

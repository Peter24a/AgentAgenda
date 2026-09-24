"""Owner-requested file delivery without sending originals or metadata to the LLM."""
import re
from urllib.parse import quote

from sqlalchemy import exists, select

from app.models.canonical import Document, DocumentOrigin, DocumentRevision
from app.services.document_retrieval import normalize


def file_query(message: str):
    normalized = normalize(message.strip())
    if normalized.startswith('/archivo '):
        return normalized[9:].strip()
    if not re.match(r'^(?:por favor[,]?\s+)?(?:dame|pasame|enviame|mandame|muestrame|busca|descarga|quiero descargar|necesito descargar)\b', normalized):
        return None
    if not re.search(r'\b(?:archivo|archivos|documento|documentos|foto|fotos|imagen|imagenes|pdf|cv|curriculum)\b', normalized):
        return None
    return normalized


async def file_delivery_response(session, user_id: str, message: str):
    query = file_query(message)
    if query is None:
        return None
    words = re.findall(r'[\w]+', query)
    ignored = set('por favor dame pasame enviame mandame muestrame busca descarga quiero necesito descargar el la los las un una unos unas mi mis de del en con que tengo guardado guardados archivo archivos documento documentos foto fotos imagen imagenes'.split())
    keywords = [w for w in words if w not in ignored]
    blocked = exists(select(DocumentOrigin.document_id).where(
        DocumentOrigin.document_id == Document.id,
        DocumentOrigin.privacy_class == 'NEVER_UPLOAD',
    ).correlate(Document))
    stmt = select(Document.id, Document.title, Document.alias).where(
        Document.user_id == user_id, Document.is_deleted.is_(False), ~blocked,
    ).order_by(Document.updated_at.desc(), Document.id)
    # Catalogue metadata only. No OCR text, storage paths or model inference.
    rows = (await session.execute(stmt)).all()
    matches = []
    for doc_id, title, alias in rows:
        haystack = normalize(f'{title} {alias or ""}')
        if keywords and not all(word in haystack for word in keywords):
            continue
        rev = (await session.execute(select(
            DocumentRevision.version, DocumentRevision.original_filename, DocumentRevision.mime_type,
        ).where(DocumentRevision.document_id == doc_id).order_by(DocumentRevision.version.desc()).limit(1))).first()
        if not rev:
            continue
        if re.search(r'\b(?:foto|fotos|imagen|imagenes)\b', query) and not rev.mime_type.startswith('image/'):
            continue
        label = re.sub(r'[\[\]()`<>\\]', '', ' '.join(title.split()))[:160]
        url = f'/v1/documents/{quote(doc_id, safe="")}/versions/{rev.version}/download'
        matches.append(f'- [{label}]({url})')
        if len(matches) == 8:
            break
    if not matches:
        return 'No encontré archivos con ese nombre. Prueba con «/archivo nombre» o abre la biblioteca para buscarlos.'
    return 'Puedes abrir o guardar estos archivos' + (' (hasta 8 resultados; precisa el nombre para acotar)' if len(matches) == 8 else '') + ':\n\n' + '\n'.join(matches)

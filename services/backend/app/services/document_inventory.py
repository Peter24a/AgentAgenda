"""Complete title counts and conservative, consent-scoped duplicate inspection.

Metadata is rendered locally, never sent to the model. Content is selected only
for the latest revisions visible to the current recipient. Similarity is not
proof of a duplicate award, and no stored document is modified.
"""
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import re
from urllib.parse import quote

from sqlalchemy import exists, select
from sqlalchemy.orm import aliased

from app.models.canonical import Document, DocumentOrigin, DocumentRevision
from app.services.context_visibility import document_context_filters
from app.services.document_retrieval import normalize


@dataclass(frozen=True)
class InventoryQuery:
    keywords: tuple[str, ...]
    compare: bool = False


def _word(word):
    # Deliberately limited inflection; do not conflate arbitrary substrings.
    if word.endswith('ciones'):
        return word[:-2]
    if len(word) > 4 and word.endswith('s') and word[-2] in 'aeiou':
        return word[:-1]
    return word


def inventory_query(message):
    text = normalize(message.strip())
    if text.startswith('/archivo ') or text.startswith(('/autorizar', '/revocar')):
        return None
    docs = bool(re.search(r'\b(?:documentos?|archivos?|titulos?)\b', text))
    awards = bool(re.search(r'\b(?:reconocimientos?|diplomas?|certificados?|constancias?)\b', text))
    count = bool(re.search(r'\b(?:cuantos?|cuantas?|cantidad|numero|total|cuenta|contar)\b', text))
    search = bool(re.match(r'(?:por favor[,]?\s+)?(?:(?:puedes|podrias)\s+)?(?:busca|buscar|lista|listar|enumera|muestra|muestrame|cuales)\b', text))
    compare = bool(re.search(r'\b(?:duplicados?|repetidos?|duplicadas?|repetidas?|distintos?|unicos?|compara|comparar)\b', text))
    if not ((docs or awards) and (count or search or compare)):
        return None
    # Scheduling/mutation requests must keep their normal route.
    if re.match(r'(?:por favor[,]?\s+)?(?:agenda|programa|elimina|borra|revoca|autoriza)\b', text):
        return None
    quoted = re.search(r'["“«]([^"”»]+)["”»]', text)
    filler = set('por favor busca buscar lista listar enumera muestra muestrame cuales cual cuantos cuantas cuanto cuanta cantidad numero total cuenta contar de del el la los las un una unos unas mi mis tus sus tengo tienes hay he has obtenido obtenidos recibido recibidos conseguido conseguidos ganado ganados son es estan se que cuyo cuyos cuya cuyas titulo titulos nombre nombres documento documentos archivo archivos subido subidos subida subidas guardado guardados disponible disponibles biblioteca catalogo en con y o al para tambien puedes podrias dime saber quiero necesito cuantos cuantas obtuve revisa revisar compara comparar repetido repetidos repetida repetidas duplicado duplicados duplicada duplicadas distinto distintos unica unicas unico unicos sin realmente exactamente dicen dice diga digan contiene contienen incluya incluyan llamados llamadas llamado llamada todos todas'.split())
    subject = quoted.group(1) if quoted else text
    words = re.findall(r'[^\W_]+', subject)
    keywords = tuple(dict.fromkeys(_word(w) for w in words if quoted or w not in filler))
    return InventoryQuery(keywords, compare or (count and awards and not docs))


def _label(text):
    return re.sub(r'[\[\]()`<>\\]', '', ' '.join(str(text or '').split()))[:160]


def _link(row):
    label = _label(row['title'])
    if row['version'] is None:
        return label + ' (sin versión descargable)'
    return f'[{label}](/v1/documents/{quote(row["id"], safe="")}/versions/{row["version"]}/download)'


def _normalized_text(text):
    return ' '.join(re.findall(r'[^\W_]+', normalize(text or '')))


async def inventory_response(session, user_id, recipient_id, message):
    query = inventory_query(message)
    if query is None:
        return None
    revision = aliased(DocumentRevision)
    latest = (select(revision.id).where(revision.document_id == Document.id)
              .order_by(revision.version.desc(), revision.created_at.desc(), revision.id.desc())
              .limit(1).correlate(Document).scalar_subquery())
    blocked = exists(select(DocumentOrigin.document_id).where(
        DocumentOrigin.document_id == Document.id, DocumentOrigin.privacy_class == 'NEVER_UPLOAD',
    ).correlate(Document))
    # Columns only: the ORM relationship would otherwise fetch unauthorized text.
    rows = (await session.execute(select(
        Document.id, Document.title, DocumentRevision.id.label('revision_id'), DocumentRevision.version,
    ).select_from(Document).outerjoin(DocumentRevision, DocumentRevision.id == latest).where(
        Document.user_id == user_id, Document.is_deleted.is_(False), ~blocked,
    ).order_by(Document.title, Document.id))).mappings().all()
    matches = [dict(row) for row in rows if set(query.keywords) <= {
        _word(word) for word in re.findall(r'[^\W_]+', normalize(row['title']))
    }]
    total = len(matches)
    subject = ' '.join(query.keywords)
    heading = f'Encontré **{total} documentos**' + (f' cuyos títulos coinciden con «{_label(subject)}».' if subject else ' en tu catálogo disponible.')
    lines = [heading, 'Es un conteo de documentos, no de reconocimientos obtenidos. Cada documento cuenta una vez, aunque tenga varias versiones.' if query.compare else 'Cada documento cuenta una vez, aunque tenga varias versiones.']
    lines.extend('- ' + _link(row) for row in matches[:20])
    if total > 20:
        lines.append(f'Muestro 20 de {total}; el conteo incluye todas las coincidencias. Precisa el título para acotar la lista.')
    if not total or not query.compare:
        return '\n\n'.join(lines)
    by_revision = {row['revision_id']: row for row in matches if row['revision_id']}
    # Do not inspect text, hashes or identity fields of non-authorized revisions.
    allowed = []
    ids = list(by_revision)
    for offset in range(0, len(ids), 400):
        allowed.extend((await session.execute(select(
            DocumentRevision.id, DocumentRevision.extracted_text, DocumentRevision.extraction_status,
            DocumentRevision.sha256_hash,
        ).join(Document).where(
            *document_context_filters(user_id, recipient_id),
            DocumentRevision.id.in_(ids[offset:offset + 400]),
        ))).mappings().all())
    lines.append(f'Comparación de contenido: **{len(allowed)} de {total} documentos autorizados** para este dispositivo.')
    groups = defaultdict(list)
    texts = {}
    unreadable = 0
    for row in allowed:
        text = _normalized_text(row['extracted_text']) if row['extraction_status'] in ('ready', 'needs_review') else ''
        if len(text) < 80:
            unreadable += 1
        else:
            texts[row['id']] = text
        # Exact binary copies are conclusive even if OCR is absent. Otherwise
        # only sufficiently complete identical text is treated as a content copy.
        if re.fullmatch(r'[a-fA-F0-9]{64}', row['sha256_hash'] or ''):
            groups['hash:' + row['sha256_hash'].lower()].append(row['id'])
    parent = {row['id']: row['id'] for row in allowed}
    def root(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key
    def union(keys):
        for key in keys[1:]:
            parent[root(key)] = root(keys[0])
    for keys in groups.values():
        union(keys)
    text_groups = defaultdict(list)
    for key, text in texts.items():
        text_groups[hashlib.sha256(text.encode()).hexdigest()].append(key)
    for keys in text_groups.values():
        union(keys)
    clusters = defaultdict(list)
    for key in parent:
        clusters[root(key)].append(key)
    duplicates = [keys for keys in clusters.values() if len(keys) > 1]
    copies = sum(len(keys) - 1 for keys in duplicates)
    lines.append(f'Copias de archivo o de texto extraído equivalente: **{len(duplicates)} grupos; {copies} copias adicionales**.')
    for keys in duplicates[:10]:
        lines.append('Mismo archivo o texto extraído: ' + '; '.join(_link(by_revision[key]) for key in keys[:10]))
    if len(duplicates) > 10 or any(len(keys) > 10 for keys in duplicates):
        lines.append('La lista de grupos está abreviada; los conteos incluyen todas las copias detectadas.')
    # Similar text is only a suggestion. A changed name, date, folio or award can
    # be a different achievement, even with an almost identical template.
    comparable = [(key, text) for key, text in texts.items() if len(text) <= 20000][:100]
    shingles = {key: set(zip(words, words[1:], words[2:])) for key, text in comparable if (words := text.split())}
    possible = []
    for i, (left, _) in enumerate(comparable):
        for right, _ in comparable[i + 1:]:
            if root(left) == root(right):
                continue
            a, b = shingles[left], shingles[right]
            if a and b and len(a & b) / len(a | b) >= .60:
                possible.append((left, right))
    if possible:
        lines.append(f'**{len(possible)} pares parecidos, sin confirmar como duplicados**. Pueden cambiar el destinatario, la fecha, el folio o el motivo:')
        lines.extend('- ' + _link(by_revision[a]) + ' / ' + _link(by_revision[b]) for a, b in possible[:10])
        if len(possible) > 10:
            lines.append('Se muestran los primeros 10 pares similares.')
    if len(comparable) < len(texts):
        lines.append('La búsqueda de similitudes se limita a 100 documentos con hasta 20 000 caracteres; las copias exactas sí se compararon en todos los autorizados.')
    if unreadable:
        lines.append(f'{unreadable} documentos autorizados no tienen suficiente texto legible para comparar su contenido; sólo se pudo comprobar si sus archivos son idénticos.')
    missing = [row for row in matches if row['revision_id'] not in parent]
    if missing:
        lines.append(f'Falta autorización o una versión disponible para {len(missing)} documentos. No leí su contenido. Para autorizar uno, escribe «/autorizar ID»:')
        lines.extend(f'- {_label(row["title"])}: `/autorizar {row["id"]}`' for row in missing[:5] if row['revision_id'])
        lines.append('Después vuelve a pedir el conteo o la comparación.')
    lines.append('No eliminé ni fusioné archivos. Este resultado no acredita cuántos reconocimientos distintos has obtenido: un archivo puede contener varios, corresponder a otra persona o ser otra copia con diferencias de escaneo.')
    return '\n\n'.join(lines)

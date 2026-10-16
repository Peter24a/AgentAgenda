# Conteo por título y comparación documental

Cambio de servidor solicitado el 15 de octubre de 2026 (America/Mexico_City).
No modifica Android, su APK ni los contratos obligatorios del chat.

## Comportamiento

- Las preguntas de conteo y búsqueda consultan todos los títulos disponibles del
  propietario. Se normalizan acentos, mayúsculas y plurales comunes; los términos
  se buscan como palabras completas. No se confunden alias o nombres de archivo
  con títulos. Cada documento cuenta una vez y enlaza su revisión más reciente.
- Se muestran hasta 20 resultados, indicando el total completo. Los eliminados,
  documentos de otro propietario y los marcados NEVER_UPLOAD quedan excluidos.
- Un conteo explícito de documentos por título sólo consulta metadatos. Preguntar
  cuántos reconocimientos se han obtenido o pedir comparar duplicados añade la
  inspección de las revisiones autorizadas para el dispositivo actual.
- La comparación usa hashes de archivo y texto extraído normalizado idéntico.
  Los textos parecidos se presentan como posibles duplicados, sin fusionarlos:
  cambiar destinatario, fecha o folio puede indicar otro reconocimiento.
- No se leen textos ni hashes de revisiones sin permiso. Se informa cuántos
  documentos están autorizados y cómo autorizar los restantes individualmente.
  Revocaciones y versiones nuevas conservan las barreras de permiso existentes.
- No se afirma que documentos, grupos de texto y reconocimientos obtenidos sean
  equivalentes. Un archivo puede contener varios reconocimientos o pertenecer
  a otra persona. No se borran ni fusionan documentos.
- Las copias exactas se comprueban en todos los autorizados; la búsqueda de
  similitudes se limita a 100 textos de hasta 20 000 caracteres y lo indica si
  hay exclusiones. Textos de menos de 80 caracteres no prueban copias de contenido.
- Las respuestas son deterministas, locales y compatibles con el SSE instalado;
  los originales y metadatos de esta operación no se envían al modelo.

## Verificación local

391 pruebas aprobadas, 2 omitidas por configuración opcional de PostgreSQL.
Las 21 pruebas nuevas cubren conteos completos, filtrado por propietario,
NEVER_UPLOAD/eliminados, últimas versiones, metadatos sin lectura de texto,
archivos idénticos, texto normalizado equivalente, plantillas parecidas de
personas distintas, hashes inválidos, permisos por dispositivo/revisión,
revocación, documentos sin versión y respuesta SSE de Android sin llamar al modelo.

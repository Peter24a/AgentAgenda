# Archivo personal: importación y consulta

El backend conserva originales y recupera fragmentos relevantes para el chat.
La información pertenece al usuario de la importación; no modifica los pesos del
modelo ni convierte documentos antiguos en acciones nuevas.

## Preparar un lote

Desde `services/backend`, con el entorno Python y dependencias del proyecto:

```sh
python -m app.importing.personal plan /ruta/al/archivo /ruta/al/archivo/PersonalLLM \
  --collection personal-archive --output /ruta/privada/manifest.json
```

Añadir `--include-opt-in` sólo cuando el propietario haya elegido incluir esa
información. Las raíces solapadas se deduplican. El manifiesto privado enumera
archivos seleccionados, revisión pendiente, exclusiones y hashes. No subirlo a Git.

Se excluyen antes de leerlos las claves, certificados, archivos de recuperación,
`seguridadDigital`, `.ssh` y `98_BOVEDA_PRIVADA_NO_COMPARTIR`. También se separan
código, paquetes derivados, plantillas e instrucciones operativas. No se ejecuta
contenido ni se siguen enlaces web o rutas externas encontrados en documentos.
Los originales sin etiqueta requieren OPT_IN.

## Importar al servidor

Copiar los archivos `action=include` y `action=duplicate`, conservando rutas relativas, a un
directorio privado en el servidor y montar ese directorio de sólo lectura en el
contenedor que ejecuta la importación. Usar el mismo `--collection` para próximas
versiones del archivo.

```sh
python -m app.importing.personal apply /import/manifest.json \
  --source-root /import/source --user-id default_user
```

La base guarda un recibo del lote y el origen por documento. Mismos bytes y ruta
no crean una revisión adicional; un archivo modificado crea una nueva versión.
Un documento eliminado no reaparece al repetir una importación. Se verifican los
hashes antes y después de copiar; no se anuncia completado un archivo alterado.
Repetir bytes de una revisión histórica tampoco restaura esa versión sobre otra
más reciente: el informe los cuenta como `historical_not_restored`.
La importación conserva las fechas y metadatos declarados, sin inferir vigencia.
La importación añade documentos y versiones: quitar un archivo del siguiente lote
o cambiarlo a excluido no revoca una copia ya importada. Para retirarla de las
consultas hay que eliminar el documento mediante la API autenticada.

## Extracción automática

`document-worker` comparte únicamente base y volumen privado con el backend. Usa
pypdf, python-docx y OCR local Poppler/Tesseract español/inglés. Las imágenes y
páginas escaneadas no requieren subir el documento a un proveedor externo.

Estados:

- `pending`: pendiente de procesar.
- `ready`: texto extraído; el reconocimiento OCR aún puede contener errores.
- `needs_review`: extracción parcial o contenido que requiere revisión visual.
- `unsupported`: formato no extraíble por los adaptadores disponibles.
- `failed`: fallo de procesamiento, sujeto a reintentos limitados.

Se preservan páginas PDF y tablas Word. No se recorta el original ni se presenta
texto binario como una extracción correcta. Límites explícitos: 50 MB, 500 páginas
y 2 millones de caracteres por documento. El diagnóstico queda en el job.

```sh
docker compose up -d --build agent-backend document-worker
docker compose logs --tail 50 document-worker
```

`/v1/status` informa la actividad del worker mediante un latido reciente. No es una
prueba de que todos los documentos estén listos: revisar los estados de extracción.

## Recuperación y límites

`GET /v1/documents/search?q=...` devuelve fragmentos con documento, versión,
página/sección y origen. Requiere `documents:read`. El chat utiliza las mismas
fuentes sólo cuando sus credenciales incluyen ese alcance. Requiere la última
revisión no borrada, sin volver silenciosamente a una versión vieja pendiente.
El material OPT_IN incluido con autorización queda disponible para esas consultas
del propietario; no se solicita consentimiento de nuevo en cada pregunta.

El modelo recibe un subconjunto del archivo según la pregunta y un presupuesto
de contexto. Se le exige citar fuentes, reconocer falta de evidencia y distinguir
información histórica, planes y hechos. Notas llamadas HOY o SEMANA_ACTUAL no
cambian su fecha original al importarlas.

La búsqueda es textual con normalización de acentos, no semántica por embeddings;
puede necesitar palabras más concretas en preguntas muy indirectas. Los documentos
no se convierten automáticamente en memorias confirmadas ni recordatorios. OCR,
interpretación y citas deben comprobarse contra el original para datos importantes.

El catálogo y descargas autenticadas ya están disponibles por API. Esta entrega
carga el lote desde el servidor; no incorpora todavía un selector de archivos ni
una biblioteca documental completa en la interfaz móvil.

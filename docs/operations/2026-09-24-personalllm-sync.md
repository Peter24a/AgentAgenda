# Sincronización selectiva de PersonalLLM — 24 de septiembre de 2026

Actualizado: 24 de septiembre de 2026, Ciudad de México (25 de septiembre UTC).
Fuente y certeza: petición explícita de Pedro de revisar AgentAgenda en `cite-server` contra el contexto local y retomar Stanford/KHS; comprobación directa de metadatos, SHA-256, originales almacenados y filtros del servidor. No se infiere cumplimiento de tareas desde las reservas de agenda.

## Resultado del primer lote

Antes de las modificaciones de esta sesión, coincidían por SHA-256 los 30 documentos cotejados: 29 SAFE admisibles y HOY, autorizado para esta comparación. La última importación pertinente era del 21 de septiembre por la noche. Esta comprobación no equivale a auditar todos los documentos privados del catálogo.

Después de actualizar el contexto operativo local, se importaron exclusivamente cinco Markdown. El manifiesto contiene cinco inclusiones, cero duplicados, exclusiones o pendientes de revisión; la aplicación creó cinco revisiones y no reportó fallos. Se conservaron los documentos y sus revisiones anteriores.

| Fuente relativa a PersonalLLM | Revisión nueva | Extracción | SHA-256, prefijo |
|---|---:|---|---|
| `HOY.md` | 5 | ready | `6a8daf241e41` |
| `SEMANA_ACTUAL.md` | 4 | ready | `3e84ceed3977` |
| `06_PLANES/POSGRADO/KHS_STANFORD_2027.md` | 3 | ready | `798b7811983c` |
| `01_CANONICO/HECHOS_DUDAS_Y_PENDIENTES.md` | 4 | ready | `1e87678a6fb5` |
| `02_ESTADO_ACTUAL/ESTADO_ACTUAL.md` | 4 | ready | `c64c691886cd` |

Para cada archivo se verificó igualdad entre el hash local, la revisión en base y los bytes del original almacenado. El recuento de revisiones aumentó exactamente en uno; la revisión anterior y su hash permanecen intactos. La extracción terminó en `ready` para los cinco.

Se crearon dos permisos, uno para la nueva revisión OPT_IN de HOY y otro para la de HECHOS, únicamente para el mismo dispositivo que ya tenía autorización. Las tres revisiones SAFE no necesitan permisos individuales. El filtro real `document_context_filters` permite recuperar las cinco revisiones para ese destinatario.

## Corrección de contexto automático

El catálogo conservaba un registro antiguo de `PersonalLLM/INBOX.md`, importado el 15 de septiembre, activo e indexado como SAFE. El importador posterior excluía el archivo, pero excluirlo de un lote no retiraba el registro anterior.

Sin leer su contenido, se respaldaron y verificaron los metadatos del único documento afectado. Se cambió exclusivamente `document_origins.privacy_class` de SAFE a OPT_IN, sin otorgar permisos. Documento, revisión, original e historia permanecen intactos. No había permisos ni memorias documentales derivadas. El filtro real devuelve cero registros elegibles tanto para contexto por defecto como para el dispositivo previamente autorizado.

Respaldo privado en `cite-server`: `/home/peter/.local/share/AgentAgenda/operations/2026-09-24-personalllm-sync/inbox-metadata-before-20260925T000416Z.json`; SHA-256 `f551146e5c3f5ccfaa6f5b7bf844d0dd690efcb0c0ecc7d1e4d0f2a13ef352ea`. La corrección es reversible usando esos metadatos; no debe restaurarse SAFE mientras siga vigente la regla de no usar INBOX automáticamente.

## Procedimiento y continuidad

Se preparó una carpeta temporal con únicamente los cinco archivos autorizados, manteniendo el prefijo `PersonalLLM/` y sus subrutas. Se ejecutó el importador existente con colección `personal-archive` y propietario existente. No se recorrió la carpeta original completa ni se transfirieron PDF, otras fuentes privadas o paquetes.

```sh
python -m app.importing.personal plan STAGING \
  --collection personal-archive --include-opt-in --output manifest.json
python -m app.importing.personal apply manifest.json \
  --user-id default_user --source-root STAGING
```

Lote: `imp-7ba90b692d81dbc51e4fd4fc2c671b442cbcfaeb200c4db0`.

Los manifiestos, metadatos anteriores/posteriores, informes de importación y permisos, hashes completos y verificación se conservaron en directorios privados:

- Local: `/home/peterpad/.local/share/AgentAgenda/operations/2026-09-24-personalllm-sync/run-20260925T000702Z/`.
- `cite-server`: `/home/peter/.local/share/AgentAgenda/operations/2026-09-24-personalllm-sync/run-20260925T000702Z/`.

El código desplegado del importador, recuperación documental y filtros coincide por SHA-256 con el repositorio local. La recuperación consulta la última revisión en cada chat; tras extracción y permisos no necesita reinicio. **Cambios futuros en PersonalLLM requieren otra importación:** no hay sincronización continua del directorio.

Backend y base quedaron saludables, con worker activo. No hubo reinicios ni cambios de citas o rutina. La rutina semanal ya estaba activa y materializada hasta el 21 de octubre al consultar sus metadatos; ello no acredita que sus actividades se hayan realizado.

## Segundo lote — comprobación del kárdex actualizado

Actualización: 24 de septiembre de 2026, Ciudad de México (25 de septiembre UTC). Fuente: seguimiento de la petición vigente de Pedro, revisión local solicitada del kárdex fechado 3 de septiembre de 2026 y cambios resultantes en el contexto operativo. La revisión académica y sus conclusiones se mantienen en PersonalLLM; esta operación sincroniza únicamente los Markdown autorizados.

Se importaron exclusivamente tres nuevas revisiones. Los hashes locales, de base de datos y de los originales almacenados coinciden; las tres extracciones están `ready`. Se preservaron las revisiones anteriores y cada documento añadió exactamente una revisión. Se añadieron únicamente dos permisos, para HOY y HECHOS, al mismo destinatario ya autorizado. El filtro de contexto permite las tres revisiones para ese dispositivo. No se copiaron PDF ni otras fuentes, no se amplió la auditoría del catálogo y no se hicieron consultas a modelos ni cambios de agenda.

| Fuente relativa a PersonalLLM | Revisión vigente | Extracción | SHA-256, prefijo |
|---|---:|---|---|
| `HOY.md` | 6 | ready | `3aa6ec34a71a` |
| `01_CANONICO/HECHOS_DUDAS_Y_PENDIENTES.md` | 5 | ready | `6462d75878dd` |
| `06_PLANES/POSGRADO/KHS_STANFORD_2027.md` | 4 | ready | `181f96b1e141` |

Lote: `imp-c201325ed3c5d612403bd9eb70392541a2d50f7fa4560b7e`. Manifiesto: tres inclusiones; cero duplicados, exclusiones, pendientes o fallos. Los artefactos privados del segundo lote, incluidos hashes completos y verificación, se conservan en:

- Local: `/home/peterpad/.local/share/AgentAgenda/operations/2026-09-24-personalllm-sync/run-20260925T002652Z/`.
- `cite-server`: `/home/peter/.local/share/AgentAgenda/operations/2026-09-24-personalllm-sync/run-20260925T002652Z/`.

Antes de ampliar este informe se conservó y verificó su [versión anterior](../../99_ARCHIVO/2026-09-24-personalllm-sync-before-kardex-note/2026-09-24-personalllm-sync.md), SHA-256 `2bcb37b59b71af6a9fa1b3eeef92ce66c0fbc7bcb19316f1bd7fa1296782bfba`. Los resultados del primer lote quedan arriba como historial de esta operación; la tabla de este apartado indica las revisiones correspondientes al segundo lote.

## Tercer lote — optativas y consulta prevista en Movilidad

Actualización: 24 de septiembre de 2026, Ciudad de México (25 de septiembre UTC). Fuente: aclaraciones directas de Pedro sobre dos optativas, ausencia de kárdex traducido y su intención de consultar en Movilidad de Campus Central el 25 de septiembre. Los nombres se registraron como declaración de Pedro pendiente de cotejo institucional, conservando la diferencia menor entre el título truncado previamente observado y su aclaración. La visita sigue siendo intención, sin cita agendada. La orientación del plan distingue emisión institucional/profesional de una mera firma sobre un borrador y conserva la comprobación pendiente de la vía KHS en el portal.

Se actualizaron e importaron exclusivamente HOY, HECHOS y el plan KHS. Las copias locales previas se conservaron juntas y verificadas en `PersonalLLM/99_ARCHIVO/2026-09-24_optativas_y_consulta_movilidad/`. Resultado: tres revisiones nuevas `ready`, igualdad SHA-256 local/base/original almacenado, revisiones anteriores intactas y dos permisos nuevos únicamente para HOY/HECHOS y el mismo destinatario autorizado. El filtro de contexto permite las tres revisiones para ese dispositivo.

| Fuente relativa a PersonalLLM | Revisión vigente tras el tercer lote | SHA-256, prefijo |
|---|---:|---|
| `HOY.md` | 7 | `84006b22a385` |
| `01_CANONICO/HECHOS_DUDAS_Y_PENDIENTES.md` | 6 | `39c3e8251afd` |
| `06_PLANES/POSGRADO/KHS_STANFORD_2027.md` | 5 | `605701b539d7` |

Lote: `imp-aecc1e704cf27f93553e2f03b29e754a4df7f84d4fcbfb2e`. Manifiesto: tres inclusiones, cero duplicados, exclusiones, pendientes o fallos. Artefactos privados completos del lote:

- Local: `/home/peterpad/.local/share/AgentAgenda/operations/2026-09-24-personalllm-sync/run-20260925T004902Z/`.
- `cite-server`: `/home/peter/.local/share/AgentAgenda/operations/2026-09-24-personalllm-sync/run-20260925T004902Z/`.

No se abrieron ni transfirieron PDF u otras fuentes; no se modificaron horario, ESTADO o SEMANA, ni se realizaron contactos, consultas a modelos o cambios de agenda. Se preservó y verificó la [versión anterior de este informe](../../99_ARCHIVO/2026-09-24-personalllm-sync-before-optativas/2026-09-24-personalllm-sync.md), SHA-256 `7ac1810eb0afc585ed05ac90b66fe53b473ca4fb7618abd075f45902f5977068`.

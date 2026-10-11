# Preparación de AgentAgenda para Google Play

Archivos actualizados el 10 de octubre de 2026 para `com.agentagenda.agent_agenda`, versión `2.0.3+10`.

## Ficha en español (Latinoamérica)

| Campo | Archivo | Longitud validada |
|---|---|---:|
| Nombre | `listing/es-419/title.txt` | 11 / 30 |
| Descripción breve | `listing/es-419/short-description.txt` | 76 / 80 |
| Descripción completa | `listing/es-419/full-description.txt` | 2523 / 4000 |
| Notas de versión | `listing/es-419/release-notes.txt` | 333 / 500 |

Correo: **pibarrafacio@gmail.com**. Soporte/web: **https://agenda-api.pedroibarra.dev/soporte**. Privacidad: **https://privacy.ici-labs.com/agentagenda/**. Eliminación: **https://privacy.ici-labs.com/agentagenda/eliminacion/**.

App, categoría sugerida **Productividad**, instalación gratuita y sin anuncios. Público previsto: **13 años o más**; esto no asigna por sí solo una clasificación IARC. El espacio debe haber sido creado previamente por el administrador y se conecta mediante código. No se promete capacidad ilimitada, servicio gratuito perpetuo ni cifrado de extremo a extremo.

## Gráficos listos para subir

- `assets/app-icon-512.png`: 512 × 512, PNG RGBA, 16 577 bytes, fondo completo ciruela, sin bordes redondeados ni sombra externa.
- `assets/feature-graphic-1024x500.png`: 1024 × 500, PNG RGB sin alfa, 48 465 bytes. Ilustración conceptual de agenda y archivos, no una captura de pantalla.
- Fuentes editables: `assets/app-icon.svg`, `assets/feature-graphic.svg`; paleta de la app: ciruela `#6B4F73`, lila `#C5AED0`, fondo `#F7F5F2`.
- `assets/verification.json`: dimensiones, canales, formatos y tamaños comprobados al exportar.

El isotipo conserva los cuatro trazos y transformaciones de los SVG oficiales de Identidad SARA v0.4.0. `distribution/branding/source/` mantiene las fuentes originales y `sources.json` sus hashes. La app, Android, la web y Play comparten esa geometría, sin reinterpretar el símbolo. Android incluye icono adaptable y monocromo dentro de la zona segura; Play usa fondo completo para que la tienda aplique su máscara. La portada mantiene la ilustración de calendario/archivo y las fuentes Inter/Manrope del repositorio.

Para reproducir los PNG se necesita Node con `sharp` disponible:

```sh
node distribution/branding/render-branding.cjs
node distribution/google-play/render-assets.cjs
```

En el runtime de Codex, definir `NODE_PATH` con su directorio de dependencias para resolver `sharp`. `fontconfig.conf` utiliza las fuentes incluidas en `apps/mobile/assets/fonts`; no se descargan fuentes en la exportación.

Las dimensiones/formatos se verificaron con la [guía oficial de gráficos](https://support.google.com/googleplay/android-developer/answer/9866151?hl=en) y las [especificaciones oficiales del icono](https://developer.android.com/distribute/google-play/resources/icon-design-specifications?hl=en).

## Capturas y acceso de revisión

`screenshots/` contiene capturas **reales** del emulador temporal oficial Android 16 de 16 KB, realizadas con la versión 2.0.2+9, el espacio de revisión y contenido sintético. Se conservan como material de esa versión: no muestran ni verifican la UI actualizada de +10. Su resolución virtual se ajustó antes de capturar para respetar la relación máxima 2:1: 1080 × 2160. La UI se renderizó a esa resolución; no se recortó ni se generó. Los PNG se exportaron a RGB de 24 bits sin alfa, comprobando que sus píxeles no cambiaron. No son capturas del Pixel físico. La evidencia del Pixel corresponde a +8; +9 se probó en el emulador temporal, sin reinstalar un APK directo en el teléfono del usuario. No incluir nombres, agenda, documentos, chats privados, contraseñas ni códigos activos de clientes. No se han fabricado capturas de UI.

Antes de adjuntar las capturas, verificar en el dispositivo agenda, tareas, archivos, chat/reportes y ajustes. Usar el AAB final firmado, no confundir el APK para instalación directa con el paquete requerido por Play. El acceso de revisión debe usar un espacio dedicado y un método de activación disponible durante la revisión, con instrucciones claras; no incluir aquí sus secretos.

## Formularios

`DATA_SAFETY_DRAFT.md` documenta las respuestas guardadas en Console y su evidencia en el código e infraestructura. El CSV real exportado se verificó contra la matriz de 17 tipos: 5 obligatorios, 12 opcionales y 4 compartidos; no se encontraron diferencias. Los nombres, IDs y contenido que se transmiten al servidor cuentan aunque no se usen para publicidad. Revisar especialmente Cloudflare, IP/ubicación derivada, logs, búsqueda y el almacenamiento de originales genéricos de audio/vídeo.

No declarar una auditoría independiente, IARC, ausencia absoluta de compartición ni aprobación de Google que todavía no se haya obtenido. La consola puede guardar la ficha y los formularios como borradores mientras se completan las verificaciones.

## Paquetes y verificación

El paquete firmado actual para Play es `release/AgentAgenda-2.0.3+10.aab`, excluido de Git por su tamaño. No se generó un APK release de +10 para instalación directa. `verification/release-version-10-validation.json` registra el hash del AAB, manifest, firma, validación de bundletool y comprobaciones estáticas de alineación ELF y configuración del bundle para 16 KB. Todas esas comprobaciones pasaron; no se generaron splits ni se instaló o ejecutó este paquete como parte de esa validación.

Las pruebas Flutter de esta actualización terminaron con 59 aprobadas y 1 omitida, e incluyen la UI refinada. La evidencia de ejecución de 16 KB en `verification/runtime-16kb.json` y la verificación anterior en `verification/release-validation.json` corresponden a +9. Las bibliotecas nativas ajenas a la app permanecen idénticas a +9, pero esa comparación no valida la ejecución de +10. No se ha realizado una prueba de runtime de este AAB, en x86_64 ni en ARM de 16 KB.

La política de privacidad, contacto, metadatos y acceso de revisión deben quedar publicados y disponibles durante la revisión. Las versiones +6, +7, +8 y +9 anteriores se conservan como historial; la entrega actual es +10.

## Optimización DEX

`verification/dex-optimization-version-10.json` registra la comprobación del AAB actual; `verification/dex-optimization-version-8.json` conserva la auditoría del aviso original y `verify-dex-optimization.py` permite comprobar cada AAB. R8 está habilitado en modo completo, con reducción de código y recursos. En +10, el DEX sin comprimir ocupa 2.11 MB: 62.26 % de optimización, 63.33 % de ofuscación y 63.19 % de reducción. El paquete mantiene la configuración anterior. No se retiraron reglas de Flutter, plugins, JNI ni el recurso de notificaciones para elevar una puntuación. Estos porcentajes no son mediciones de velocidad ni sustituyen una prueba de rendimiento.

## Estado de Console

La versión **2.0.3 (10)** está publicada en prueba interna y Console confirma «Disponible para verificadores internos». La misma versión se promovió a **Beta AgentAgenda** y se envió un cambio a revisión para lanzamiento completo. Console confirma «Cambios en la etapa de revisión», con verificaciones preliminares todavía en curso; la beta +10 aún no se considera aprobada. La beta +9 ya estaba publicada antes de este envío. `verification/console-progress.json` registra el estado actual; `verification/history/version-9-console-progress.json` conserva el registro anterior. Los comprobantes son `verification/console-internal-version-10.jpg` y `verification/console-beta-version-10.jpg`.

IARC, seguridad de datos, acceso de revisión autorizado, privacidad, audiencia 13+, categoría y soporte se conservaron. La lista compartida AgentAgenda — Beta muestra cinco cuentas; figurar en ella no equivale a inscribirse como tester. No se cambiaron participantes ni se enviaron correos. Producción sigue deshabilitada en Console.

La cuenta muestra requisito de prueba cerrada: al menos 12 testers inscritos durante 14 días consecutivos antes de solicitar producción. No se enviaron invitaciones ni se inventaron participantes.

El usuario eligió conservar la nueva firma de distribución de Google. El AAB conserva nuestra firma como clave de subida, pero el certificado de distribución es distinto del APK directo publicado. Pasar de ese APK a Play requiere una reinstalación y un nuevo código para reconectar el mismo espacio; el servidor conserva el contenido. Las claves privadas no se exportaron a Google. Enlace de la prueba interna: https://play.google.com/apps/internaltest/4700803363705001483 (sólo cuentas autorizadas en la lista).

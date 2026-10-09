# Preparación de AgentAgenda para Google Play

Archivos preparados el 8 de octubre de 2026 para `com.agentagenda.agent_agenda`, versión `2.0.1+8`.

## Ficha en español (Latinoamérica)

| Campo | Archivo | Longitud validada |
|---|---|---:|
| Nombre | `listing/es-419/title.txt` | 11 / 30 |
| Descripción breve | `listing/es-419/short-description.txt` | 76 / 80 |
| Descripción completa | `listing/es-419/full-description.txt` | 2523 / 4000 |
| Notas de versión | `listing/es-419/release-notes.txt` | 468 / 500 |

Correo: **pibarrafacio@gmail.com**. Soporte/web: **https://agenda-api.pedroibarra.dev/soporte**. Privacidad: **https://privacy.ici-labs.com/agentagenda/**. Eliminación: **https://privacy.ici-labs.com/agentagenda/eliminacion/**.

App, categoría sugerida **Productividad**, instalación gratuita y sin anuncios. Público previsto: **13 años o más**; esto no asigna por sí solo una clasificación IARC. El espacio debe haber sido creado previamente por el administrador y se conecta mediante código. No se promete capacidad ilimitada, servicio gratuito perpetuo ni cifrado de extremo a extremo.

## Gráficos listos para subir

- `assets/app-icon-512.png`: 512 × 512, PNG RGBA, 15 174 bytes, fondo completo ciruela, sin bordes redondeados ni sombra externa.
- `assets/feature-graphic-1024x500.png`: 1024 × 500, PNG RGB sin alfa, 49 284 bytes. Ilustración conceptual de agenda y archivos, no una captura de pantalla.
- Fuentes editables: `assets/app-icon.svg`, `assets/feature-graphic.svg`; paleta de la app: ciruela `#6B4F73`, lila `#C5AED0`, fondo `#F7F5F2`.
- `assets/verification.json`: dimensiones, canales, formatos y tamaños comprobados al exportar.

El lazo del icono fue reconstruido como vector a partir del motivo visual existente en la app. La ilustración de portada usa formas vectoriales de calendario/archivo y las fuentes Inter/Manrope ya incluidas en el repositorio.

Para reproducir los PNG se necesita Node con `sharp` disponible:

```sh
node distribution/google-play/render-assets.cjs
```

En el runtime de Codex, definir `NODE_PATH` con su directorio de dependencias para resolver `sharp`. `fontconfig.conf` utiliza las fuentes incluidas en `apps/mobile/assets/fonts`; no se descargan fuentes en la exportación.

Las dimensiones/formatos se verificaron con la [guía oficial de gráficos](https://support.google.com/googleplay/android-developer/answer/9866151?hl=en) y las [especificaciones oficiales del icono](https://developer.android.com/distribute/google-play/resources/icon-design-specifications?hl=en).

## Capturas y acceso de revisión

`screenshots/` contiene capturas **reales** del emulador temporal oficial Android 16 de 16 KB, realizadas con la versión 2.0.1+8, el espacio de revisión y contenido sintético. Su resolución virtual se ajustó antes de capturar para respetar la relación máxima 2:1: 1080 × 2160. La UI se renderizó a esa resolución; no se recortó ni se generó. Los PNG se exportaron a RGB de 24 bits sin alfa, comprobando que sus píxeles no cambiaron. No son capturas del Pixel físico. No incluir nombres, agenda, documentos, chats privados, contraseñas ni códigos activos de clientes. No se han fabricado capturas de UI.

Antes de adjuntar las capturas, verificar en el dispositivo agenda, tareas, archivos, chat/reportes y ajustes. Usar el AAB final firmado, no confundir el APK para instalación directa con el paquete requerido por Play. El acceso de revisión debe usar un espacio dedicado y un método de activación disponible durante la revisión, con instrucciones claras; no incluir aquí sus secretos.

## Formularios

`DATA_SAFETY_DRAFT.md` documenta las respuestas guardadas en Console y su evidencia en el código e infraestructura. El CSV real exportado se verificó contra la matriz de 17 tipos: 5 obligatorios, 12 opcionales y 4 compartidos; no se encontraron diferencias. Los nombres, IDs y contenido que se transmiten al servidor cuentan aunque no se usen para publicidad. Revisar especialmente Cloudflare, IP/ubicación derivada, logs, búsqueda y el almacenamiento de originales genéricos de audio/vídeo.

No declarar una auditoría independiente, IARC, ausencia absoluta de compartición ni aprobación de Google que todavía no se haya obtenido. La consola puede guardar la ficha y los formularios como borradores mientras se completan las verificaciones.

## Paquetes y verificación

Los artefactos firmados finales se copian a `release/AgentAgenda-2.0.1+8.aab` y `.apk`, excluidos de Git por su tamaño. El AAB se usa en Play y el APK en instalación directa. `verification/release-validation.json` registra hashes, manifest, firma, validación de bundletool, segmentos ELF y alineación de los splits. `verification/runtime-16kb.json` registra la imagen oficial, tamaño de página real, compatibilidad desactivada y resultados de la prueba del APK release. La ejecución de 16 KB está probada en x86_64; no sustituye una prueba real ARM de 16 KB ni la aceptación de Play Console.

La política de privacidad, contacto, metadatos y acceso de revisión deben quedar publicados y disponibles durante la revisión. Las versiones +6 y +7 anteriores se conservan sólo como historial; la entrega actual es +8.

## Estado de Console

La app AgentAgenda existe en la cuenta del usuario. La ficha predeterminada en español (Latinoamérica), con texto, icono, gráfico y cuatro capturas reales, está guardada y lista para enviar a revisión. Las ilustraciones de icono/gráfico se declararon como creadas o editadas con ayuda de IA; las capturas son tomas reales de la app. Se guardaron privacidad, acceso de revisión autorizado por el usuario (sólo espacio sintético, sin opt-in adicional de partners), anuncios, audiencia 13–15/16–17/18+, categoría Productividad, correo y soporte, gobierno, finanzas y salud. IARC requiere aceptación específica de sus términos. El AAB +8 ya fue procesado y publicado en el canal de prueba interna activo, con una lista que contiene sólo la cuenta del usuario. La ficha y la app siguen sin revisión; los testers ven temporalmente el identificador del paquete. Seguridad de datos quedó guardada y su exportación real se verificó; sólo IARC queda pendiente de la configuración, pues requiere autorización para aceptar sus términos. Todavía no hay solicitud ni publicación de producción.

La cuenta muestra requisito de prueba cerrada: al menos 12 testers inscritos durante 14 días consecutivos antes de solicitar producción. No se enviaron invitaciones ni se inventaron participantes.

El usuario eligió conservar la nueva firma de distribución de Google. El AAB conserva nuestra firma como clave de subida, pero el certificado de distribución es distinto del APK directo publicado. Pasar de ese APK a Play requiere una reinstalación y un nuevo código para reconectar el mismo espacio; el servidor conserva el contenido. Las claves privadas no se exportaron a Google. Enlace de la prueba interna: https://play.google.com/apps/internaltest/4700803363705001483 (sólo cuentas autorizadas en la lista).

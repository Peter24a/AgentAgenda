# AgentAgenda web

Interfaz en español, sin compilación ni dependencias externas. `public/` se sirve desde la plataforma FastAPI mediante `PLATFORM_WEB_ROOT`. `/` y `/admin` abren directamente el panel administrativo, sin portada pública; `/activar` conecta a los clientes y `/app` abre su espacio privado. Los recursos están en `/assets/`.

El panel administrativo usa `/control/v1` y una sesión independiente. El dashboard privado usa `/platform/v1/session` y las rutas `/s/<space_id>/v1`. Las sesiones viven en cookies HttpOnly; JavaScript conserva únicamente los metadatos y tokens CSRF durante la sesión. No hay almacenamiento de secretos en localStorage ni visor administrativo de contenido.

Incluye altas y progreso de preparación, códigos temporales, suspensión y reapertura; agenda con edición y tareas; conversación durable con SSE y confirmación de propuestas; catálogo, carga por bloques y búsqueda documental; autorización y revocación de dispositivos.

Los enlaces de archivos recibidos del asistente se validan y resuelven dentro del espacio actual. Las respuestas y nombres se muestran con nodos de texto; no se evalúa HTML del servidor. Al terminar el streaming, se recupera el turno durable para completar cualquier token producido antes de la suscripción.

Comprobaciones locales:

```sh
node --check apps/web/public/assets/app.js
node --test apps/web/tests/utils.test.mjs
```

Para la revisión visual, usar la plataforma local con `PLATFORM_WEB_ROOT` apuntando a la ruta absoluta de `apps/web/public`. Una vista estática permite revisar el inicio y los formularios, pero las operaciones requieren los endpoints reales. No iniciar sesión ni activar espacios reales en pruebas automatizadas de interfaz; usar un espacio sintético.

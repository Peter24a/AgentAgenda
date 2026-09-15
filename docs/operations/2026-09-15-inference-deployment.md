# Revisión de inferencia y despliegue — 15 de septiembre de 2026

## Diagnóstico y cambios aplicados

AgentAgenda apuntaba a `http://172.30.81.1:8080/v1`, evitando el gateway de
AIlauncher. El gateway no tenía una identidad registrada para esta aplicación.

Ahora el flujo desplegado en `cite-server` es:

```text
Pixel → backend FastAPI → llm-gateway:8000/v1 → llama.cpp en el host → GPU
```

- Backend conectado a `llm-apps`, sin pertenecer a `llm-backend`.
- Clave propia `agentagenda` registrada en AIlauncher, conservando las demás claves.
- `LLM_API_KEY` se guarda en `deploy/.env` del servidor (modo 600), no en Git ni en Android.
- Comprobación LLM mediante `/ready` autenticado: valida el modelo cargado, no sólo el catálogo del gateway.
- Los fallos HTTP, de conexión, timeout, SSE inválido, respuesta vacía o stream sin `[DONE]` generan turnos fallidos; no se guardan como mensajes del asistente exitosos.
- Conexión limitada a 5 s; espera de lectura de 90 s para permitir la cola de admisión de hasta 60 s.
- Publicación Docker del backend limitada a `127.0.0.1:8001`.
- Fallback anónimo desactivado en Compose; secreto de backend independiente y aleatorio.
- Creación de desafíos de emparejamiento autenticada y vinculada al usuario autenticado.
- Android ya no envía una clave maestra compilada. Usa token de dispositivo y renueva la sesión al iniciar si tiene refresh token.
- `BACKEND_URL` se puede configurar con `--dart-define` al compilar Flutter.

## Inferencia observada

llama.cpp ya estaba configurado con Qwen3.8-27B Q4_K_M, proyector visual,
RTX 3090 + RTX 4070 SUPER, reparto 2:1, Flash Attention, 4 slots,
32.768 tokens totales y límite de 8.192 por slot. No se cambiaron los parámetros
compartidos de GPU ni se reinició el motor.

El gateway mantiene 4 peticiones simultáneas totales, 2 por aplicación,
cola de 32 y salida máxima de 2.048 tokens. AgentAgenda solicita 1.024 por defecto.

Prueba sintética desde el contenedor del backend, pasando por el adaptador real:
`Responde únicamente: Conexión correcta.` → `Conexión correcta.`

- Primer texto: 1,225 s.
- Total: 1,426 s.
- Log del gateway: `app_id=agentagenda`, HTTP 200; espera de cola 0,018 ms.

Es una muestra corta, no un benchmark de carga ni una mejora de velocidad demostrada.

## Cloudflare y móvil

Publicado túnel dedicado `cite-server-agentagenda` y servicio de usuario systemd
`agentagenda-tunnel.service`. Token en
`/home/cite/.config/agentagenda/tunnel-token`, modo 600.

Ruta publicada y verificada: `https://agenda-api.pedroibarra.dev` → `http://127.0.0.1:8001`.
Cloudflare confirmó la creación DNS y el túnel está Healthy. HTTPS `/health` devuelve
200; `/v1/chat/messages` sin credenciales devuelve 401.
Tunnel ID: `0160361e-4736-467e-80db-cb7ba0ae9969`.

APK debug instalado en el Pixel 10 Pro XL conectado. Preferencias privadas
aprovisionadas con URL y credenciales de dispositivo; ningún token está compilado.

## Verificación

- Backend final: 129 pruebas pasan, 1 omitida (PostgreSQL live no configurado localmente).
- Flutter: 5 pruebas pasan; `flutter analyze` sin incidencias; APK debug compilado.
- Prueba de integración en el Pixel físico: renovación de sesión, HTTPS y chat SSE
  completado sin errores. Gateway registra `agentagenda`, HTTP 200, primer contenido
  1.009 ms y total 1.199 ms (tiempos del gateway, no del recorrido completo).
- Cliente móvil muestra errores SSE y desconexiones; timeout de inactividad 120 s.
- Se enviaron mensajes de validación que quedan en el historial de chat.
- Backend desplegado: PostgreSQL conectado, almacenamiento disponible y LLM online.
- Sin token, con clave de desarrollo y con `X-Forwarded-For: 127.0.0.1`: HTTP 401.
- Token del Pixel: `/v1/auth/me` devuelve HTTP 200.

Quedan advertencias previas de APIs obsoletas de Pydantic y datetime. Esta revisión
no valida exhaustivamente memoria, sincronización, todas las políticas de
permisos ni concurrencia de chat. La renovación móvil ocurre al iniciar; no hay
reintento automático de todas las operaciones tras caducar una sesión en uso.

## Archivo personal cargado

Se analizaron las dos raíces solicitadas como un único árbol, evitando contar de
nuevo la carpeta PersonalLLM anidada. Con autorización del propietario se cargaron
77 originales: 27 SAFE y 50 OPT_IN (incluidos originales sin etiqueta explícita).
Claves, contraseñas, certificados, bóveda NEVER_UPLOAD y material operativo quedan
fuera de la consulta. Un README operativo detectado al afinar la selección se
retiró mediante borrado lógico.

- Integridad: 77 de 77 SHA-256 coinciden entre originales y almacén del servidor.
- Extracción local: 76 `ready`, 1 `needs_review`, sin trabajos pendientes.
- El Word marcado contiene dos membretes institucionales revisados visualmente.
  El cuerpo está extraído; la edición romana del congreso en el membrete no está
  indexada. Se conserva el diagnóstico de extracción parcial.
- Repetición del lote definitivo en PostgreSQL: 0 importados, 77 sin cambios,
  0 fallos. Repetir un lote histórico no restaura versiones anteriores.
- Consulta autenticada `/v1/documents/search`: HTTP 200 con fuentes recuperadas.
- Integración en Pixel: pregunta sobre el archivo personal, stream completado y
  referencias documentales presentes. El modelo sigue pasando por AIlauncher.
- Después de la prueba, se instaló la app normal, se aprovisionó la sesión privada
  y se verificaron renovación HTTP 200, agenda HTTP 200 y `/v1/auth/me` HTTP 200.
  El APK normal se comprobó sin las credenciales de prueba ni del dispositivo.

La migración `7ac921e1d012` está aplicada. El esquema anterior se verificó antes de
marcar la revisión base, porque la instalación antigua usaba `create_all` sin
historial Alembic. Copia previa: `~/AgentAgenda-backups/20260915-personal/`, con
dump PostgreSQL y código. Manifiesto y staging privados:
`~/AgentAgenda-imports/20260915/`, fuera de Git.

Consultar [PERSONAL_IMPORT.md](../PERSONAL_IMPORT.md) para formatos, privacidad,
repetición de lotes y límites. El chat recupera fragmentos por búsqueda textual con
citas y fechas; no incorpora todavía biblioteca/selector documental móvil ni
convierte automáticamente documentos en memorias o recordatorios.

## Operación

En `cite-server`, desde `~/AgentAgenda/deploy`:

```sh
docker compose up -d --build agent-backend document-worker
curl --fail http://127.0.0.1:8001/v1/status
systemctl --user status agentagenda-tunnel.service
```

Se preservaron los datos PostgreSQL y el volumen documental. Configuración previa
de Compose y adaptador LLM en `~/AgentAgenda-backups/20260915-llm/`.
La copia protegida del registro anterior de claves está en
`/etc/ailauncher/app-keys.before-agentagenda.json`.
No restaurar el Compose anterior al publicar: reactivaría acceso anónimo y conexión
directa al motor. Para revertir código, mantener las restricciones de red y auth.

El exportador BuildKit del host falló por una instantánea padre ausente. Se pudo
construir la imagen con `DOCKER_BUILDKIT=0 docker build -t agentagenda-backend:local
services/backend` desde la raíz del repositorio y luego ejecutar Compose sin
`--build`. No se reinició Docker ni se tocaron los contenedores de otras apps.

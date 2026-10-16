# Administración: SARA ID, códigos y dispositivos

Desplegado el 15 de octubre de 2026 (America/Mexico_City) en `cite-server`.
Fuente de código: commit `5641704`. Release: `admin-sara-auth-20261015`.

## Resultado

`https://agenda-api.pedroibarra.dev/admin` ofrece «Continuar con SARA ID».
El cliente `agentagenda-admin-web` está registrado en Identity con audiencia
`agentagenda-admin`, callback exacto
`https://agenda-api.pedroibarra.dev/control/v1/auth/sara/callback` y reutilización
de sesión central habilitada. Se preservaron los otros 15 clientes registrados.
Una única cuenta central, elegida expresamente por Pedro, tiene autorización
local por UUID. La configuración y ese vínculo permanecen fuera de Git.

El panel conserva el historial de los últimos 100 códigos de un uso y muestra
estado disponible, activación en curso, usado, vencido o reemplazado. Incluye
fechas y referencia pública; no devuelve el código, su hash ni credenciales.
Los registros que versiones anteriores eliminaron no se pueden reconstruir.

Cada espacio muestra dispositivos con acceso vigente y el subconjunto con
actividad en los últimos 15 minutos. Son conteos agregados por propietario;
no prueban conexión simultánea exacta. Un servicio detenido muestra «Sin medición».
El detalle se actualiza cada 15 segundos mientras no haya una ventana abierta.

## Verificaciones

- Plataforma: 60 pruebas aprobadas, incluidas 26 de autenticación SARA.
- Backend de inscripción/métricas: 10 pruebas aprobadas.
- Utilidades web: 5 pruebas aprobadas; sintaxis JavaScript y diff sin errores.
- Se verificaron estado, PKCE, rechazo de navegador ajeno y replay, UUID no
  autorizado, audiencia fija, cifrado, renovación concurrente, revocación,
  interrupción de Identity, cierre local y persistencia tras reiniciar.
- En producción se comprobaron los hashes de las siete fuentes de ejecución,
  la nueva fuente dentro de cada imagen, salud de los tres espacios y métricas
  internas agregadas. Los contenedores PostgreSQL conservaron sus identidades.
- Sondas públicas/locales: salud 200, configuración `provider=sara`, listado sin
  sesión 401 y login por contraseña local 404.
- El navegador real mostró el nuevo acceso y llegó al portal central con cliente,
  callback y challenge válidos. Ese navegador no tenía sesión SARA; no se introdujo
  una contraseña ni se creó una sesión administrativa real para completar el
  acceso. La primera entrada autenticada de Pedro queda por comprobar.

## Despliegue y recuperación

La plataforma sigue siendo el servicio nativo `agentagenda-platform.service`.
Backend y worker de los tres espacios usan
`agentagenda-backend:admin-sara-auth-20261015`, imagen
`sha256:c4deeda1d83ca107bb895ea546ebbe1652bf02f4bc64ea6e2f6c4fe71f9d7119`.
No se migraron ni restauraron las bases de contenido.

Antes del corte se ejecutó correctamente el respaldo cifrado completo y se guardó
una copia SQLite consistente, configuración, fuentes e imagen anterior. La copia
privada y el procedimiento de reversión están en
`/srv/agentagenda/recovery/deploy-admin-sara-auth-20261015/`; no se publican sus
contenidos ni secretos. La configuración previa de Identity se respaldó antes de
registrar el cliente y solo se recreó su API para aplicar la configuración.

La reversión de código conserva el registro vivo y las bases de los espacios.
Antes de arrancar una versión que desconoce SARA o códigos reemplazados, retira
las sesiones administrativas y los códigos revocados sin operación para evitar
que vuelvan a autorizar acceso. No reemplaza el registro con la copia anterior ni
reintroduce datos históricos sobre escrituras nuevas.

# Política pública de AgentAgenda

`agentagenda/index.html` y `agentagenda/style.css` forman una política estática independiente, legible sin JavaScript. La dirección canónica es `https://privacy.ici-labs.com/agentagenda/`.

Se publica en `/home/peter/privacyset-site/agentagenda/` del servidor `cite-server`. El contenedor existente `privacyset-web` monta el directorio del portal en modo de sólo lectura; actualizar sus archivos no requiere reiniciar nginx. Las políticas de otras aplicaciones permanecen en sus directorios originales.

El portal raíz está generado previamente con Astro y no tiene un proyecto fuente Git en ese servidor. Se añadió una tarjeta AgentAgenda a su catálogo reutilizando las clases y los atributos del diseño existente, conservando las otras tres tarjetas y el filtro. Si se vuelve a generar el portal desde su proyecto original, hay que incorporar AgentAgenda también en ese catálogo para conservar el enlace.

Antes de modificar el índice raíz, guardar una copia en un directorio privado y comparar el hash del archivo con la versión inspeccionada. Publicar mediante reemplazo atómico dentro del mismo sistema de archivos. La copia anterior a esta integración está en `/home/peter/.local/share/agentagenda/privacy-portal-backups/index-before-agentagenda-20261008T214625.html`.

La página dedicada de eliminación es `https://privacy.ici-labs.com/agentagenda/eliminacion/`; su fuente está en `agentagenda/eliminacion/index.html` y reutiliza `../style.css`. Es legible sin JavaScript ni sesión. Publicar su URL con barra final evita el redireccionamiento de directorio del nginx interno.

La página de ayuda y su formulario revisable de solicitud siguen en `https://agenda-api.pedroibarra.dev/soporte#eliminacion`; su fuente es `../public/support.html`. La app Android +8 conserva este enlace. La declaración de Google Play usa la página estática dedicada, que responde a GET y HEAD. No es necesario recompilar la app para mantener ambas vías. `/privacidad` del servicio principal redirige a la política canónica.

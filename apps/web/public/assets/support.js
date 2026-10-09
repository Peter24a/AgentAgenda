const form = document.querySelector('#deletion-form');
const review = document.querySelector('#request-review');
const preview = document.querySelector('#request-message');
const send = document.querySelector('#request-send');
const status = document.querySelector('#request-status');

form.addEventListener('submit', event => {
  event.preventDefault();
  const values = new FormData(form);
  const name = String(values.get('name') || '').trim();
  if (!name) { form.querySelector('[name=name]').focus(); return; }
  const space = String(values.get('space') || '').trim();
  const partial = values.get('scope') === 'selected';
  const detail = String(values.get('detail') || '').trim();
  const message = [
    'Hola, quiero solicitar la eliminación de datos de AgentAgenda.',
    '',
    `Titular: ${name}`,
    `Espacio: ${space || 'No recuerdo el nombre o identificador'}`,
    `Solicitud: ${partial ? 'Eliminar sólo la información indicada abajo.' : 'Eliminar mi cuenta, todo el espacio y sus datos asociados.'}`,
    detail && `Detalle: ${detail}`,
    '',
    'Entiendo que se verificará mi identidad antes de atender la solicitud.',
    'Por favor, confirmen el resultado y cualquier retención de datos necesaria.',
  ].filter(line => line !== false && line !== null).join('\n');
  preview.textContent = message;
  send.href = `mailto:pibarrafacio@gmail.com?subject=${encodeURIComponent('AgentAgenda - Eliminar cuenta y datos')}&body=${encodeURIComponent(message)}`;
  review.hidden = false;
  status.textContent = 'El mensaje todavía no se ha enviado. Al abrir el correo, revisa el destinatario y envíalo.';
  review.scrollIntoView({block: 'nearest'});
});

document.querySelector('#request-copy').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(preview.textContent);
    status.textContent = 'Mensaje copiado. Pégalo en un correo a pibarrafacio@gmail.com y envíalo cuando lo hayas revisado.';
  } catch {
    status.textContent = 'No se pudo copiar automáticamente. Selecciona el mensaje y cópialo o abre tu aplicación de correo.';
  }
});

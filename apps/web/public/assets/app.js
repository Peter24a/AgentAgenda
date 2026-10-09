import {TIMEZONE, canonicalDate, localDay, spaceBase, documentLink, splitSse, formatBytes, errorMessage} from './utils.js';

const root = document.querySelector('#root');
const notifications = document.querySelector('#notifications');
const state = {admin: null, session: null, spaces: [], operations: [], screen: 'spaces', privateTab: 'agenda', timezone: TIMEZONE, startDate: localDay(), endDate: localDay(), epoch: 0, timer: null, stream: null};
const icons = {
  arrow: ['M5 12h14', 'm13 6 6 6-6 6'], back: ['M19 12H5', 'm11 6-6 6 6 6'], download: ['M12 3v12', 'm7 10 5 5 5-5', 'M5 16v5h14v-5'],
  calendar: ['M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z', 'M7 3v4M17 3v4M3 11h18'],
  chat: ['M21 11a8 8 0 0 1-8 8H7l-4 3V7a4 4 0 0 1 4-4h6a8 8 0 0 1 8 8Z', 'M7 8h9M7 12h6'],
  file: ['M14 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V10Z', 'M14 3v7h7M7 14h10M7 17h7'],
  lock: ['M6 10h12a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2Z', 'M8 10V6a4 4 0 0 1 8 0v4M12 14v3'],
  plus: ['M12 5v14M5 12h14'], close: ['m6 6 12 12M6 18 18 6'], check: ['m5 12 4 4L19 6'],
  edit: ['m16 3 5 5-12 12-6 1 1-6Z', 'm14 5 5 5'], trash: ['M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7'],
  spaces: ['M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z'], settings: ['M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z', 'm9 3-1 3-3 1-2 3 2 2-1 3 2 3h3l2 3h3l1-3 3-1 2-3-2-2 1-3-2-3h-3l-2-3Z'],
  logout: ['M9 3H4v18h5M9 12h12', 'm16 7 5 5-5 5'], refresh: ['M20 7V3l-4 1M4 17v4l4-1', 'M20 7a8 8 0 0 0-14-3M4 17a8 8 0 0 0 14 3'],
  activity: ['M3 12h4l3-8 4 16 3-8h4'], phone: ['M8 2h8a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z', 'M10 18h4'],
  search: ['M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14Z', 'm15 15 6 6'], send: ['m3 3 18 9-18 9 4-9-4-9Z', 'M7 12h14'], copy: ['M9 9h12v12H9zM15 6V3H3v12h3'], shield: ['M12 3 3 7v5c0 5 9 9 9 9s9-4 9-9V7Z', 'm8 12 3 3 5-6'], clock: ['M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Z', 'M12 6v6l4 2'],
};

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (name === 'class') node.className = value;
    else if (name === 'text') node.textContent = value;
    else if (name.startsWith('on')) node.addEventListener(name.slice(2).toLowerCase(), value);
    else if (name === 'value') node.value = value;
    else if (name === 'checked') node.checked = value;
    else node.setAttribute(name, value === true ? '' : String(value));
  }
  for (const child of children.flat(Infinity)) if (child !== null && child !== undefined && typeof child !== 'boolean') node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  return node;
}
function icon(name) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  node.setAttribute('viewBox', '0 0 24 24'); node.setAttribute('class', 'icon'); node.setAttribute('aria-hidden', 'true');
  for (const path of icons[name] || icons.file) { const p = document.createElementNS('http://www.w3.org/2000/svg', 'path'); p.setAttribute('d', path); node.append(p); }
  return node;
}
function button(text, action, style = '', iconName = null) { return el('button', {type: 'button', class: `button ${style}`, onclick: action}, iconName && icon(iconName), text); }
function iconButton(name, title, action, danger = false) { return el('button', {type: 'button', class: `icon-button${danger ? ' danger' : ''}`, title, 'aria-label': title, onclick: action}, icon(name)); }
function link(text, href, style = '', iconName = null) { return el('a', {href, class: style}, iconName && icon(iconName), text); }
function brand() { return el('a', {href: '/', class: 'brand'}, el('img', {src: '/assets/brand.svg', alt: '', width: 37, height: 37}), 'AgentAgenda'); }
function field(label, name, options = {}) {
  const input = el(options.tag || 'input', {id: `field-${name}`, name, type: options.type || 'text', ...options});
  input.removeAttribute('tag'); input.removeAttribute('hint');
  return el('div', {class: `field${options.full ? ' span-full' : ''}`}, el('label', {for: input.id}, label), input, options.hint && el('small', {}, options.hint));
}
function statusBadge(value) {
  const labels = {ready: 'Activo', active: 'Activo', suspended: 'Suspendido', closed: 'Cerrado', closing: 'Cerrando', provisioning: 'Preparando', pending: 'Pendiente', queued: 'En espera', running: 'En curso', completed: 'Completado', succeeded: 'Completado', failed: 'Falló', healthy: 'Disponible', degraded: 'Degradado', online: 'En línea', offline: 'Sin conexión', accepted: 'Aceptada', rejected: 'Rechazada'};
  const css = ['closed', 'failed', 'offline'].includes(value) ? 'danger' : ['suspended', 'provisioning', 'pending', 'queued', 'degraded', 'running', 'closing'].includes(value) ? 'warning' : ['ready', 'active', 'healthy', 'online', 'completed', 'succeeded', 'accepted'].includes(value) ? '' : 'neutral';
  return el('span', {class: `badge ${css}`}, labels[value] || value || 'Sin estado');
}
function dateObject(value) { return canonicalDate(value); }
function dateTime(value) { return value ? dateObject(value).toLocaleString('es-MX', {timeZone: state.timezone, dateStyle: 'medium', timeStyle: 'short'}) : 'Sin registro'; }
function dayLabel(day) { return new Date(`${day}T12:00:00`).toLocaleDateString('es-MX', {weekday: 'long', day: 'numeric', month: 'long'}); }
function time(value) { return dateObject(value).toLocaleTimeString('es-MX', {timeZone: state.timezone, hour: '2-digit', minute: '2-digit', hour12: false}); }
function loading(text = 'Cargando…') { return el('div', {class: 'loading', role: 'status'}, el('span', {class: 'spinner', 'aria-hidden': true}), text); }
function empty(title, description, iconName = 'calendar', action = null) { return el('div', {class: 'empty'}, icon(iconName), el('h3', {}, title), el('p', {}, description), action); }
function notice(message, kind = '') { return el('div', {class: `notice ${kind}`, role: kind === 'error' ? 'alert' : 'status'}, message); }
function toast(message, isError = false) { const node = el('div', {class: `toast${isError ? ' error' : ''}`, role: isError ? 'alert' : 'status'}, message); notifications.append(node); setTimeout(() => node.remove(), 7000); }
function formError(form, error) { const node = form.querySelector('.form-error'); node.replaceChildren(notice(error.message, 'error')); }
async function busy(node, work) { node.disabled = true; node.setAttribute('aria-busy', 'true'); try { return await work(); } catch (error) { toast(error.message, true); } finally { node.disabled = false; node.removeAttribute('aria-busy'); } }
function apiPath(path) { return `${spaceBase(state.session.space_id)}${path}`; }
async function api(path, {method = 'GET', body, scope = 'owner', signal, raw = false, headers: extra = {}} = {}) {
  const headers = new Headers(extra);
  if (body !== undefined && !(body instanceof Blob)) headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD'].includes(method)) {
    const csrf = scope === 'admin' ? state.admin?.csrf_token : state.session?.csrf_token;
    if (csrf) headers.set('X-CSRF-Token', csrf);
  }
  let response;
  try { response = await fetch(path, {method, headers, body: body === undefined ? undefined : body instanceof Blob ? body : JSON.stringify(body), credentials: 'same-origin', signal, cache: 'no-store'}); }
  catch (error) { if (error.name === 'AbortError') throw error; throw new Error('No hay conexión con el servidor. Revisa tu conexión e inténtalo de nuevo.'); }
  if (!response.ok) { let payload; try { payload = await response.json(); } catch {} const error = new Error(errorMessage(payload, response.status)); error.status = response.status; throw error; }
  if (raw) return response;
  if (response.status === 204) return null;
  return response.json();
}
function control(path, options = {}) { return api(`/control/v1${path}`, {...options, scope: 'admin'}); }
function content(path, options = {}) { return api(apiPath(`/v1${path}`), options); }
function stopBackground() { if (state.timer) clearTimeout(state.timer); state.timer = null; if (state.stream) state.stream.abort(); state.stream = null; }
function startScreen() { state.epoch += 1; stopBackground(); document.querySelectorAll('dialog').forEach(node => node.remove()); return state.epoch; }
function displayError(container, error, retry) { container.replaceChildren(notice(error.message, 'error'), retry && button('Intentar de nuevo', retry, 'secondary small', 'refresh')); }
function publicHeader(active = '') { return el('header', {class: 'public-header'}, brand(), el('nav', {class: 'public-nav', 'aria-label': 'Navegación principal'}, link('Mi espacio', '/app', 'nav-link'), link(active === 'activation' ? 'Descargar app' : 'Activar espacio', active === 'activation' ? '/download/agentagenda.apk' : '/activar', 'button secondary small'))); }
function publicFooter() { return el('footer', {class: 'public-footer'}, el('span', {}, 'Una agenda. Un espacio propio.'), el('span', {}, link('Administración', '/admin', 'nav-link'), ' · AgentAgenda')); }
function pageHeader(eyebrow, title, description = '', action = null) { return el('div', {class: 'page-header'}, el('div', {}, el('p', {class: 'eyebrow'}, eyebrow), el('h1', {}, title), description && el('p', {}, description)), action); }
function panel(title, children, action = null) { return el('section', {class: 'panel'}, el('div', {class: 'panel-title'}, el('h2', {}, title), action), children); }
function metadata(entries) { return el('dl', {class: 'metadata'}, entries.map(([title, value]) => el('div', {}, el('dt', {}, title), el('dd', {}, value)))); }

function showHome() {
  startScreen(); document.title = 'AgentAgenda · Tu espacio personal';
  const today = new Date();
  const week = ['L', 'M', 'M', 'J', 'V', 'S', 'D'];
  const currentWeekday = new Intl.DateTimeFormat('en-US', {timeZone: TIMEZONE, weekday: 'short'}).format(today);
  const todayIndex = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].indexOf(currentWeekday);
  const monday = new Date(`${localDay(today)}T12:00:00Z`); monday.setUTCDate(monday.getUTCDate() - todayIndex);
  const weekDates = week.map((_, index) => { const date = new Date(monday); date.setUTCDate(date.getUTCDate() + index); return date.getUTCDate(); });
  const visual = el('div', {class: 'illustration', 'aria-label': 'Agenda, conversación y documentos reunidos en un espacio personal'},
    el('div', {class: 'workspace-paper'}, el('p', {class: 'eyebrow'}, icon('lock'), 'TU ESPACIO'), el('h2', {class: 'serif'}, 'Todo, en su lugar.'),
      el('div', {class: 'workspace-date'}, today.toLocaleDateString('es-MX', {timeZone: TIMEZONE, month: 'long', year: 'numeric'})),
      el('div', {class: 'week-strip', 'aria-hidden': true}, week.map((label, index) => el('span', {class: index === todayIndex ? 'today' : ''}, label, el('b', {}, weekDates[index])))),
      [['calendar', 'Tu agenda', 'Planes, actividades y pendientes.'], ['chat', 'Tu asistente', 'Una conversación para organizarte.'], ['file', 'Tus documentos', 'Archivos disponibles cuando los necesitas.']].map(([name, title, text]) => el('div', {class: 'paper-line'}, el('div', {class: 'paper-icon'}, icon(name)), el('div', {}, el('h3', {}, title), el('p', {}, text)), el('span', {class: 'paper-arrow'}, icon('arrow'))))),
    el('p', {class: 'landing-caption'}, 'Un mismo lugar para lo que importa.'));
  root.replaceChildren(publicHeader(), el('main', {id: 'main', class: 'landing'},
    el('section', {class: 'hero'}, el('div', {}, el('p', {class: 'eyebrow'}, 'TU DÍA, CON MÁS CLARIDAD'), el('h1', {class: 'serif'}, 'Haz espacio para ', el('em', {}, 'tu vida.')), el('p', {}, 'Reúne tu agenda, conversaciones y documentos en un espacio personal. Conecta tu app y continúa donde lo dejaste.'), el('div', {class: 'hero-actions'}, link('Activar mi espacio', '/activar', 'button', 'arrow'), link('Descargar para Android', '/download/agentagenda.apk', 'button secondary', 'download')), el('div', {class: 'hero-note'}, icon('lock'), 'Acceso mediante un código personal de activación.')), visual),
    el('section', {class: 'how', 'aria-labelledby': 'how-title'}, el('div', {}, el('p', {class: 'eyebrow'}, 'EMPEZAR ES SIMPLE'), el('h2', {id: 'how-title', class: 'serif'}, 'Tu espacio te espera.')),
      el('div', {class: 'steps'}, [['01', 'Recibe tu código', 'El administrador prepara tu espacio y te entrega un código temporal.'], ['02', 'Conecta tu app', 'Instala AgentAgenda e introduce el código. También puedes empezar desde el navegador.'], ['03', 'Continúa tu día', 'Accede a tu agenda, conversa con tu asistente y guarda tus documentos.']].map(([n, title, text]) => el('div', {}, el('span', {class: 'step-number'}, n), el('h3', {}, title), el('p', {}, text)))))), publicFooter());
}

function authLayout({eyebrow, title, copy, card, activation = false}) { root.replaceChildren(publicHeader(activation ? 'activation' : ''), el('main', {id: 'main', class: 'auth-layout'}, el('div', {class: 'auth-copy'}, el('p', {class: 'eyebrow'}, eyebrow), el('h1', {class: 'serif'}, title), el('p', {}, copy)), card), publicFooter()); }
function showActivation() {
  startScreen(); document.title = 'Conectar mi espacio · AgentAgenda';
  const params = new URLSearchParams(location.hash.slice(1)); const initialCode = params.get('code') || '';
  if (location.hash) history.replaceState(null, '', location.pathname);
  let requestId = crypto.randomUUID(); let attempt = '';
  const form = el('form', {class: 'stack'}, el('div', {class: 'form-error'}), field('Código de activación', 'code', {value: initialCode, required: true, maxlength: 120, class: 'code-input', autocomplete: 'off', spellcheck: 'false', placeholder: 'Introduce tu código', hint: 'Usa el código temporal que te entregó el administrador.'}), field('Nombre de este dispositivo', 'device_name', {required: true, maxlength: 128, value: 'Mi navegador', autocomplete: 'off'}), el('button', {type: 'submit', class: 'button'}, 'Conectar mi espacio', icon('arrow')));
  form.addEventListener('submit', async event => {
    event.preventDefault(); const submit = form.querySelector('[type=submit]'); submit.disabled = true; form.querySelector('.form-error').replaceChildren();
    const values = new FormData(form); const body = {code: values.get('code').trim(), device_name: values.get('device_name').trim(), platform: 'web'};
    const key = JSON.stringify(body); if (key !== attempt) { attempt = key; requestId = crypto.randomUUID(); }
    try { await api('/platform/v1/activate', {method: 'POST', body: {...body, request_id: requestId}}); state.session = await api('/platform/v1/session'); history.replaceState(null, '', '/app'); showPrivate(); }
    catch (error) { formError(form, error); } finally { submit.disabled = false; }
  });
  authLayout({eyebrow: 'BIENVENIDO A TU ESPACIO', title: 'Lo tuyo, siempre contigo.', copy: 'Activa este navegador para abrir tu agenda. Si reinstalaste la app, tu código de reconexión te devuelve al mismo espacio y a su contenido guardado.', activation: true, card: el('section', {class: 'panel auth-card'}, el('h2', {}, 'Conectar mi espacio'), el('p', {}, 'Un código. Tu agenda de siempre.'), form, el('p', {class: 'auth-footnote'}, 'El código es temporal y de un solo uso. Si venció o ya se utilizó, pide uno nuevo al administrador.'))});
}

function showAdminLogin(errorText = '') {
  startScreen(); document.title = 'Acceso administrativo · AgentAgenda';
  const form = el('form', {class: 'stack'}, el('div', {class: 'form-error'}, errorText && notice(errorText, 'error')), field('Usuario', 'username', {required: true, autocomplete: 'username', maxlength: 128}), field('Contraseña', 'password', {type: 'password', required: true, autocomplete: 'current-password', maxlength: 1024}), el('button', {type: 'submit', class: 'button'}, 'Entrar a administración', icon('arrow')));
  form.addEventListener('submit', async event => {
    event.preventDefault(); const submit = form.querySelector('[type=submit]'); submit.disabled = true; form.querySelector('.form-error').replaceChildren(); const data = new FormData(form);
    try { state.admin = await control('/auth/login', {method: 'POST', body: {username: data.get('username'), password: data.get('password')}}); form.reset(); showAdmin(); }
    catch (error) { formError(form, error); } finally { submit.disabled = false; }
  });
  authLayout({eyebrow: 'ADMINISTRACIÓN', title: 'Un espacio para cada persona.', copy: 'Prepara espacios, entrega accesos y administra el servicio desde un mismo lugar. El panel muestra información operativa; cada cliente tiene su sesión privada.', card: el('section', {class: 'panel auth-card'}, el('h2', {}, 'Acceso administrativo'), el('p', {}, 'Usa tus credenciales de administrador.'), form, el('p', {class: 'auth-footnote'}, 'Para abrir tu agenda personal, ', link('conecta tu espacio', '/activar'), '.'))});
}

function shell(mode, active, contentNode) {
  const admin = mode === 'admin'; const items = admin ? [['spaces', 'spaces', 'Espacios'], ['operations', 'activity', 'Operaciones']] : [['agenda', 'calendar', 'Agenda'], ['chat', 'chat', 'Conversación'], ['documents', 'file', 'Documentos'], ['settings', 'settings', 'Ajustes']];
  const displayName = admin ? state.admin.username : state.session.space_name;
  const nav = el('nav', {class: 'side-nav', 'aria-label': admin ? 'Administración' : 'Mi espacio'}, items.map(([name, glyph, label]) => el('button', {type: 'button', class: name === active ? 'active' : '', 'aria-current': name === active ? 'page' : null, onclick: () => admin ? showAdmin(name) : showPrivate(name)}, icon(glyph), label)));
  const logout = button('Salir', async event => {
    await busy(event.currentTarget, async () => { await api(admin ? '/control/v1/auth/logout' : '/platform/v1/logout', {method: 'POST', scope: admin ? 'admin' : 'owner'}); if (admin) { state.admin = null; showAdminLogin(); } else { state.session = null; history.replaceState(null, '', '/activar'); showActivation(); } });
  }, 'ghost small logout', 'logout');
  const side = el('aside', {class: 'sidebar'}, brand(), el('p', {class: 'eyebrow sidebar-label'}, admin ? 'CONTROL DEL SERVICIO' : 'MI ESPACIO'), nav, el('div', {class: 'sidebar-bottom'}, el('div', {class: 'identity'}, el('div', {class: 'avatar'}, displayName.slice(0, 2).toUpperCase()), el('div', {class: 'identity-text'}, el('strong', {}, displayName), el('small', {}, admin ? 'Administrador' : 'Espacio personal'))), logout));
  root.replaceChildren(el('div', {class: 'app-layout'}, side, el('main', {id: 'main', class: 'app-content'}, el('div', {class: 'topbar'}, el('span', {}, admin ? 'Administración / AgentAgenda' : `Mi espacio / ${displayName}`), el('span', {class: 'connection'}, 'Sesión autenticada')), contentNode)));
}

async function showAdmin(screen = 'spaces', spaceId = null) {
  const epoch = startScreen(); state.screen = screen; document.title = 'Administración · AgentAgenda';
  const area = el('div', {}, loading()); shell('admin', screen === 'detail' ? 'spaces' : screen, area);
  try {
    if (screen === 'spaces') { const result = await control('/spaces'); if (epoch !== state.epoch) return; state.spaces = result.spaces || []; renderSpaces(area); }
    else if (screen === 'operations') { const result = await control('/operations'); if (epoch !== state.epoch) return; state.operations = result.operations || []; renderOperations(area); }
    else { const [space, result] = await Promise.all([control(`/spaces/${encodeURIComponent(spaceId)}`), control('/operations')]); if (epoch !== state.epoch) return; renderSpaceDetail(area, space, (result.operations || []).filter(operation => operation.space_id === space.id)); }
    const running = screen === 'spaces' ? state.spaces.some(space => ['provisioning', 'closing'].includes(space.state)) : screen === 'operations' ? state.operations.some(operation => ['queued', 'running', 'pending'].includes(operation.state)) : Boolean(area.querySelector('[data-poll]'));
    if (running) {
      const refresh = () => { if (epoch !== state.epoch) return; if (document.querySelector('dialog')) { state.timer = setTimeout(refresh, 4000); return; } showAdmin(screen, spaceId); };
      state.timer = setTimeout(refresh, 4000);
    }
  } catch (error) { if (epoch !== state.epoch) return; if (error.status === 401) { state.admin = null; showAdminLogin(); } else displayError(area, error, () => showAdmin(screen, spaceId)); }
}
function renderSpaces(area) {
  const count = value => state.spaces.filter(space => space.state === value).length;
  const summary = el('div', {class: 'summary-grid'}, [['ESPACIOS', state.spaces.length, 'En el servicio'], ['ACTIVOS', count('ready'), 'Listos para conectar'], ['SUSPENDIDOS', count('suspended'), 'Con datos conservados']].map(([label, value, caption]) => el('div', {class: 'summary-stat'}, el('span', {class: 'eyebrow'}, label), el('strong', {}, value), el('small', {}, caption))));
  const rows = state.spaces.map(space => el('tr', {}, el('td', {}, el('div', {class: 'table-name'}, el('div', {class: 'avatar'}, space.name.slice(0, 2).toUpperCase()), el('div', {}, el('button', {type: 'button', onclick: () => showAdmin('detail', space.id)}, space.name), el('small', {}, space.owner_name || 'Sin propietario')))), el('td', {}, statusBadge(space.state)), el('td', {}, formatBytes(space.quota_bytes)), el('td', {class: 'muted'}, dateTime(space.created_at)), el('td', {}, iconButton('arrow', `Administrar ${space.name}`, () => showAdmin('detail', space.id)))));
  const list = rows.length ? el('div', {class: 'table-wrap'}, el('table', {}, el('thead', {}, el('tr', {}, ['Espacio / propietario', 'Estado', 'Límite de archivos', 'Creado', ''].map(title => el('th', {scope: 'col'}, title)))), el('tbody', {}, rows))) : empty('El siguiente espacio empieza aquí', 'Crea un espacio vacío y genera un código para su propietario.', 'spaces', button('Crear espacio', showCreateSpace, '', 'plus'));
  area.replaceChildren(pageHeader('CONTROL DEL SERVICIO', 'Espacios personales', 'Un mismo producto. Un espacio independiente para cada cliente.', button('Crear espacio', showCreateSpace, '', 'plus')), summary, panel('Tus espacios', list, button('Actualizar', () => showAdmin(), 'ghost small', 'refresh')));
}
function operationNode(operation) {
  const labels = {create: 'Crear espacio', provision: 'Preparar espacio', suspend: 'Suspender espacio', resume: 'Reactivar espacio', close: 'Cerrar espacio', reopen: 'Reabrir espacio'};
  return el('div', {class: 'operation'}, icon('activity'), el('div', {class: 'operation-title'}, el('strong', {}, labels[operation.action] || operation.action), el('small', {}, dateTime(operation.created_at)), operation.space_id && el('small', {}, ' · ', state.spaces.find(space => space.id === operation.space_id)?.name || operation.space_id), operation.error && el('p', {class: 'operation-error'}, operation.error)), statusBadge(operation.state));
}
function renderOperations(area) { area.replaceChildren(pageHeader('ACTIVIDAD DEL SERVICIO', 'Operaciones', 'Preparación y cambios de estado de los espacios.', button('Actualizar', () => showAdmin('operations'), 'secondary', 'refresh')), panel('Actividad reciente', state.operations.length ? el('div', {}, state.operations.map(operationNode)) : empty('Sin operaciones todavía', 'Aquí aparecerá el progreso de las altas y los cambios de estado.', 'activity'))); }
function renderSpaceDetail(area, space, operations) {
  const running = operations.some(operation => ['pending', 'queued', 'running'].includes(operation.state));
  const lifecycle = el('div', {class: 'detail-actions'});
  if (space.state === 'ready') lifecycle.append(button('Suspender', () => confirmLifecycle(space, 'suspend'), 'secondary', 'lock'), button('Cerrar espacio', () => confirmLifecycle(space, 'close'), 'ghost'));
  else if (space.state === 'suspended') lifecycle.append(button('Reactivar', () => confirmLifecycle(space, 'resume'), '', 'refresh'), button('Cerrar espacio', () => confirmLifecycle(space, 'close'), 'ghost'));
  else if (space.state === 'closed') lifecycle.append(button('Reabrir espacio', () => confirmLifecycle(space, 'reopen'), 'secondary', 'refresh'));
  else if (space.state === 'failed') lifecycle.append(button('Reintentar preparación', () => confirmLifecycle(space, 'retry'), 'secondary', 'refresh'));
  const access = el('div', {}, el('p', {class: 'muted'}, 'Entrega un código temporal para activar un dispositivo nuevo o recuperar acceso al mismo espacio.'), el('div', {class: 'detail-actions'}, button('Activar dispositivo', () => createActivation(space, 'enroll'), '', 'plus'), button('Código de reconexión', () => createActivation(space, 'reconnect'), 'secondary', 'refresh')), notice('Verifica la identidad del propietario antes de entregar un código de reconexión.'), el('p', {class: 'retention'}, 'Los códigos no aparecen en listados y se muestran sólo al generarlos.'));
  access.querySelectorAll('button').forEach(node => { node.disabled = space.state !== 'ready'; });
  const statePanel = el('div', {}, metadata([['Propietario', space.owner_name], ['Estado', statusBadge(space.state)], ['Salud del servicio', statusBadge(space.health === 'ready' ? 'healthy' : space.health === 'unavailable' ? 'offline' : space.health || 'Sin medición')], ['Archivos almacenados', formatBytes(space.usage_bytes)], ['Límite efectivo de archivos', space.effective_quota_bytes !== undefined && space.effective_quota_bytes !== null ? formatBytes(space.effective_quota_bytes) : formatBytes(space.quota_bytes)], ['Creado', dateTime(space.created_at)], ['Última actualización', dateTime(space.updated_at)], ['Identificador', space.id]]), lifecycle, el('p', {class: 'retention'}, 'Suspender bloquea el servicio y conserva los datos. Cerrar también bloquea el acceso y conserva sus recursos para una posible reapertura.'));
  area.replaceChildren(button('Todos los espacios', () => showAdmin(), 'ghost small back-button', 'back'), pageHeader('ESPACIO PERSONAL', space.name, 'Administración del acceso y los recursos del servicio.'), el('div', {class: 'detail-grid'}, panel('Estado del espacio', statePanel), panel('Acceso del propietario', access)), el('div', {class: 'stack'}, el('div', {}, ''), panel('Operaciones', operations.length ? el('div', {'data-poll': running ? '' : null}, operations.map(operationNode)) : empty('Sin operaciones registradas', 'Los cambios en este espacio aparecerán aquí.', 'activity'))));
}

function dialog(title, body) {
  const node = el('dialog', {class: 'dialog', 'aria-label': title}, el('div', {class: 'dialog-head'}, el('h2', {}, title), iconButton('close', 'Cerrar ventana', () => node.close())), el('div', {class: 'dialog-body'}, body));
  node.addEventListener('close', () => node.remove()); document.body.append(node); node.showModal(); return node;
}
function showCreateSpace() {
  const form = el('form', {class: 'stack'}, el('p', {class: 'muted'}, 'Prepara un espacio vacío con su propia agenda y archivos.'), el('div', {class: 'form-error'}), field('Nombre del espacio', 'name', {required: true, maxlength: 120, placeholder: 'Agenda de…'}), field('Nombre del propietario', 'owner_name', {required: true, maxlength: 128, autocomplete: 'name'}), field('Límite de archivos (GB)', 'quota', {type: 'number', min: 0.1, max: 1024, step: 0.1, value: 5, required: true, hint: 'Cuota de almacenamiento documental del espacio.'}), el('div', {class: 'dialog-footer'}, el('button', {type: 'submit', class: 'button'}, icon('plus'), 'Crear espacio')));
  const modal = dialog('Crear espacio', form);
  form.addEventListener('submit', async event => { event.preventDefault(); const submit = form.querySelector('[type=submit]'); submit.disabled = true; const values = new FormData(form);
    try { const result = await control('/spaces', {method: 'POST', body: {name: values.get('name').trim(), owner_name: values.get('owner_name').trim(), quota_bytes: Math.round(Number(values.get('quota')) * 1024 ** 3)}}); modal.close(); toast('La preparación del espacio comenzó.'); const id = result.id || result.space?.id || result.space_id; if (id) showAdmin('detail', id); else showAdmin(); }
    catch (error) { formError(form, error); } finally { submit.disabled = false; }
  });
}
function confirmLifecycle(space, action) {
  const definitions = {suspend: ['Suspender espacio', 'El acceso y los trabajos de este espacio se bloquearán. Sus datos se conservarán y podrás reactivarlo después.', 'Suspender'], resume: ['Reactivar espacio', 'El propietario podrá volver a usar el mismo espacio y sus datos.', 'Reactivar'], close: ['Cerrar espacio', 'El propietario perderá acceso. La agenda y los archivos se conservarán. Esta operación no elimina volúmenes ni respaldos.', 'Cerrar espacio'], reopen: ['Reabrir espacio', 'Se solicitará la reapertura del espacio conservado. No se creará una agenda nueva.', 'Reabrir'], retry: ['Reintentar preparación', 'Se retomará la preparación del mismo espacio y de sus recursos ya creados.', 'Reintentar']};
  const [title, message, label] = definitions[action];
  const body = el('div', {class: 'stack'}, el('p', {}, `«${space.name}»`), el('p', {class: 'muted'}, message), el('div', {class: 'dialog-footer'})); const modal = dialog(title, body);
  body.lastChild.append(button('Cancelar', () => modal.close(), 'secondary'), button(label, event => busy(event.currentTarget, async () => { await control(`/spaces/${encodeURIComponent(space.id)}/${action}`, {method: 'POST', body: {}}); modal.close(); toast('El cambio de estado se solicitó correctamente.'); showAdmin('detail', space.id); }), ['close', 'suspend'].includes(action) ? 'danger' : ''));
}
async function createActivation(space, purpose) {
  const body = el('div', {}, loading('Generando código…')); const modal = dialog(purpose === 'reconnect' ? 'Reconectar al mismo espacio' : 'Activar un dispositivo', body);
  try { const result = await control(`/spaces/${encodeURIComponent(space.id)}/activation`, {method: 'POST', body: {purpose}}); if (!modal.open) return; renderCode(body, result, space.name, purpose); }
  catch (error) { if (modal.open) displayError(body, error); }
}
function renderCode(body, result, spaceName, purpose = 'enroll') {
  const url = `${location.origin}/activar#code=${encodeURIComponent(result.code)}`;
  body.replaceChildren(el('p', {class: 'muted'}, purpose === 'reconnect' ? `Este código conecta un dispositivo al espacio existente «${spaceName}». Sus contenidos se conservan.` : `Entrega este código al propietario de «${spaceName}».`), el('div', {class: 'activation-code'}, result.code), el('p', {class: 'code-expiry'}, `Vence: ${dateTime(result.expires_at)}`), el('div', {class: 'flex wrap'}, button('Copiar código', () => copyText(result.code), 'secondary', 'copy'), button('Copiar enlace web', () => copyText(url), 'secondary', 'copy')), el('p', {class: 'notice code-warning'}, 'Es de un solo uso. Compártelo únicamente con el propietario y evita publicarlo. El enlace activa este navegador; en Android introduce el código en la app.'));
}
async function copyText(value) { try { await navigator.clipboard.writeText(value); toast('Copiado al portapapeles.'); } catch { toast('No se pudo copiar. Selecciona el código y cópialo manualmente.', true); } }

async function showPrivate(tab = state.privateTab) {
  const epoch = startScreen(); state.privateTab = tab; document.title = `${{agenda: 'Mi agenda', chat: 'Conversación', documents: 'Documentos', settings: 'Ajustes'}[tab]} · AgentAgenda`;
  if (!state.session) { history.replaceState(null, '', '/activar'); showActivation(); return; }
  const area = el('div', {}, loading()); shell('owner', tab, area);
  try {
    if (tab === 'agenda') await renderAgenda(area, epoch);
    if (tab === 'chat') await renderChat(area, epoch);
    if (tab === 'documents') await renderDocuments(area, epoch);
    if (tab === 'settings') await renderSettings(area, epoch);
  } catch (error) {
    if (epoch !== state.epoch || error.name === 'AbortError') return;
    if (error.status === 401) { state.session = null; showActivation(); }
    else displayError(area, error, () => showPrivate(tab));
  }
}

const categoryLabels = {general: 'General', work: 'Trabajo', study: 'Estudio', exercise: 'Ejercicio', food: 'Comida', leisure: 'Tiempo libre', sleep: 'Descanso'};
async function renderAgenda(area, epoch) {
  const params = new URLSearchParams({start_date: state.startDate, end_date: state.endDate, timezone: state.timezone});
  const [events, tasks] = await Promise.all([content(`/agenda/events?${params}`), content('/agenda/tasks?status=pending')]);
  if (epoch !== state.epoch) return;
  const range = el('form', {class: 'date-controls'}, field('Desde', 'start_date', {type: 'date', value: state.startDate, required: true}), field('Hasta', 'end_date', {type: 'date', value: state.endDate, required: true}), el('button', {type: 'submit', class: 'button secondary small'}, 'Ver agenda'), button('Hoy', () => { state.startDate = state.endDate = localDay(new Date(), state.timezone); showPrivate('agenda'); }, 'ghost small'));
  range.addEventListener('submit', event => { event.preventDefault(); const values = new FormData(range); if (values.get('start_date') > values.get('end_date')) { toast('La fecha de inicio debe ser anterior a la fecha final.', true); return; } state.startDate = values.get('start_date'); state.endDate = values.get('end_date'); showPrivate('agenda'); });
  const completed = events.filter(event => event.is_completed).length;
  const summary = el('div', {class: 'summary-grid'}, [['ACTIVIDADES', events.length, 'En el periodo'], ['COMPLETADAS', completed, 'De tu agenda'], ['PENDIENTES', tasks.length, 'Tareas por hacer']].map(([label, number, caption]) => el('div', {class: 'summary-stat'}, el('span', {class: 'eyebrow'}, label), el('strong', {}, number), el('small', {}, caption))));
  const grouped = new Map();
  for (const event of events) { const day = localDay(dateObject(event.start_time), state.timezone); if (!grouped.has(day)) grouped.set(day, []); grouped.get(day).push(event); }
  const eventList = events.length ? el('div', {}, [...grouped.entries()].map(([day, items]) => el('section', {class: 'event-day'}, el('h3', {class: 'event-day-label'}, dayLabel(day)), items.map(eventCard)))) : empty('Un poco de espacio en tu día', 'Agrega una actividad o conversa con tu asistente para organizar este periodo.', 'calendar', button('Agregar actividad', () => showEventForm(), 'secondary small', 'plus'));
  const taskList = tasks.length ? el('div', {}, tasks.map(task => el('div', {class: 'task'}, el('button', {class: 'task-check', type: 'button', title: `Completar ${task.title}`, 'aria-label': `Completar ${task.title}`, onclick: event => busy(event.currentTarget, async () => { await content(`/agenda/tasks/${encodeURIComponent(task.id)}/toggle`, {method: 'POST', body: {}}); toast('Tarea completada.'); showPrivate('agenda'); })}, icon('check')), el('div', {}, el('strong', {}, task.title), task.due_date && el('small', {}, `Fecha: ${dateTime(task.due_date)}`))))) : empty('Sin tareas pendientes', 'Tus pendientes aparecerán aquí cuando los acuerdes con tu asistente.', 'check');
  area.replaceChildren(pageHeader('TU ESPACIO PERSONAL', 'Mi agenda', state.startDate === state.endDate ? dayLabel(state.startDate) : `${dayLabel(state.startDate)} — ${dayLabel(state.endDate)}`, button('Agregar actividad', () => showEventForm(), '', 'plus')), summary, range, el('div', {class: 'agenda-grid'}, panel('Tu plan', eventList), el('div', {class: 'stack'}, panel('Pendientes', taskList), el('div', {class: 'notice'}, 'Puedes pedirle al asistente que ajuste tu horario. Revisa y acepta sus propuestas antes de aplicarlas.', button('Abrir conversación', () => showPrivate('chat'), 'ghost small', 'arrow')))));
}
function eventCard(event) {
  return el('article', {class: 'event'}, el('div', {class: 'event-time'}, time(event.start_time), event.end_time && el('small', {}, time(event.end_time))), el('div', {class: `event-body ${event.category in categoryLabels ? event.category : 'general'}${event.is_completed ? ' completed' : ''}`}, el('h3', {}, event.title), event.description && el('p', {}, event.description), el('div', {class: 'event-footer'}, el('span', {class: 'category'}, categoryLabels[event.category] || 'General'), el('div', {class: 'flex'}, iconButton('check', event.is_completed ? 'Marcar pendiente' : 'Marcar completada', action => busy(action.currentTarget, async () => { await content(`/agenda/events/${encodeURIComponent(event.id)}/toggle`, {method: 'POST', body: {}}); showPrivate('agenda'); })), iconButton('edit', `Editar ${event.title}`, () => showEventForm(event)), iconButton('trash', `Eliminar ${event.title}`, () => confirmDeleteEvent(event), true)))));
}
function datetimeValue(value) {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone: state.timezone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'}).formatToParts(dateObject(value));
  const part = name => parts.find(value => value.type === name).value;
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}`;
}
function showEventForm(event = null) {
  const categoryField = field('Categoría', 'category', {tag: 'select'}); const category = categoryField.querySelector('select');
  Object.entries(categoryLabels).forEach(([value, label]) => category.append(el('option', {value}, label))); category.value = event?.category || 'general';
  const form = el('form', {}, el('div', {class: 'form-error'}), el('div', {class: 'form-grid'}, field('Título', 'title', {value: event?.title || '', required: true, maxlength: 500, full: true}), field('Inicio', 'start_time', {type: 'datetime-local', value: event ? datetimeValue(event.start_time) : `${state.startDate}T09:00`, required: true}), field('Fin (opcional)', 'end_time', {type: 'datetime-local', value: event?.end_time ? datetimeValue(event.end_time) : ''}), categoryField, el('div', {class: 'field'}, el('label', {for: 'event_completed'}, 'Estado'), el('select', {name: 'completed', id: 'event_completed'}, el('option', {value: 'false'}, 'Pendiente'), el('option', {value: 'true'}, 'Completada'))), field('Descripción (opcional)', 'description', {tag: 'textarea', value: event?.description || '', maxlength: 10000, full: true})), el('p', {class: 'auth-footnote'}, `Horas en ${state.timezone}.`), el('div', {class: 'dialog-footer'}, el('button', {type: 'submit', class: 'button'}, event ? 'Guardar cambios' : 'Agregar actividad')));
  form.querySelector('[name=completed]').value = String(Boolean(event?.is_completed));
  const modal = dialog(event ? 'Editar actividad' : 'Agregar actividad', form);
  form.addEventListener('submit', async action => { action.preventDefault(); const submit = form.querySelector('[type=submit]'); submit.disabled = true; const values = new FormData(form);
    try {
      if (values.get('end_time') && values.get('end_time') <= values.get('start_time')) throw new Error('El fin debe ser posterior al inicio.');
      await content(`/agenda/events?timezone=${encodeURIComponent(state.timezone)}`, {method: 'POST', body: {id: event?.id || null, title: values.get('title').trim(), description: values.get('description').trim() || null, start_time: values.get('start_time'), end_time: values.get('end_time') || null, category: values.get('category'), is_completed: values.get('completed') === 'true'}}); modal.close(); toast(event ? 'Actividad actualizada.' : 'Actividad agregada.'); showPrivate('agenda');
    } catch (error) { formError(form, error); } finally { submit.disabled = false; }
  });
}
function confirmDeleteEvent(event) {
  const body = el('div', {class: 'stack'}, el('p', {}, `¿Eliminar «${event.title}» de tu agenda?`), el('div', {class: 'dialog-footer'})); const modal = dialog('Eliminar actividad', body);
  body.lastChild.append(button('Cancelar', () => modal.close(), 'secondary'), button('Eliminar actividad', action => busy(action.currentTarget, async () => { await content(`/agenda/events/${encodeURIComponent(event.id)}`, {method: 'DELETE'}); modal.close(); toast('Actividad eliminada.'); showPrivate('agenda'); }), 'danger', 'trash'));
}

function messageContent(text) {
  const node = el('div', {class: 'message-content'}); const pattern = /\[([^\]\n]{1,180})\]\((\/v1\/documents\/[^)\s]+)\)/g; let last = 0; let match;
  while ((match = pattern.exec(text))) {
    const href = documentLink(match[2], state.session.space_id);
    if (!href) continue;
    node.append(document.createTextNode(text.slice(last, match.index)), el('a', {href, download: ''}, match[1])); last = pattern.lastIndex;
  }
  node.append(document.createTextNode(text.slice(last))); return node;
}
function chatMessage(role, text, timestamp = null) {
  const content = messageContent(text); const node = el('article', {class: `chat-message${role === 'user' ? ' user' : ''}`, 'aria-label': role === 'user' ? 'Tu mensaje' : 'Mensaje de AgentAgenda'}, el('div', {class: 'chat-avatar'}, role === 'user' ? 'Tú' : 'A'), el('div', {}, content, timestamp && el('p', {class: 'message-meta'}, dateTime(timestamp)))); return {node, content};
}
async function renderChat(area, epoch) {
  const [messages, proposal] = await Promise.all([content('/chat/messages?limit=50'), content('/proposals/pending')]);
  if (epoch !== state.epoch) return;
  const list = el('div', {class: 'chat-messages', 'aria-label': 'Historial de conversación'}); let earliest = messages[0]?.id; let canLoad = messages.length === 50;
  const older = button('Ver mensajes anteriores', async action => busy(action.currentTarget, async () => { const batch = await content(`/chat/messages?limit=50&cursor=${encodeURIComponent(earliest)}`); if (epoch !== state.epoch) return; const oldHeight = list.scrollHeight; const nodes = batch.map(message => chatMessage(message.role, message.content, message.created_at).node); older.after(...nodes); earliest = batch[0]?.id || earliest; older.hidden = batch.length < 50; list.scrollTop += list.scrollHeight - oldHeight; }), 'ghost small', 'clock'); older.hidden = !canLoad; list.append(older);
  if (messages.length) messages.forEach(message => list.append(chatMessage(message.role, message.content, message.created_at).node));
  else list.append(empty('Conversa para organizar tu día', 'Cuéntame qué tienes pendiente o pide una propuesta para tu horario. Los cambios de agenda necesitan tu confirmación.', 'chat'));
  if (proposal) list.append(proposalCard(proposal));
  const status = el('div', {class: 'chat-status', role: 'status'});
  const input = el('textarea', {name: 'message', 'aria-label': 'Mensaje para AgentAgenda', placeholder: '¿Qué necesitas organizar hoy?', rows: 1, required: true, maxlength: 16000});
  const submit = el('button', {class: 'button', type: 'submit', 'aria-label': 'Enviar mensaje'}, icon('send'), el('span', {class: 'send-label'}, 'Enviar'));
  const form = el('form', {}, input, submit);
  const conversation = el('section', {class: 'panel chat-panel'}, list, el('div', {class: 'chat-composer'}, form, status, el('small', {}, 'La IA puede equivocarse. Revisa las propuestas antes de confirmarlas.')));
  area.replaceChildren(pageHeader('TU ASISTENTE', 'Una conversación, un plan.', 'Agenda, contexto y documentos de tu espacio.'), conversation);
  list.scrollTop = list.scrollHeight;
  let sending = false;
  form.addEventListener('submit', async action => {
    action.preventDefault(); if (sending || !input.value.trim()) return; const message = input.value.trim(); sending = true; submit.disabled = true; status.replaceChildren(el('span', {class: 'spinner'}), 'Guardando tu mensaje…');
    let turn = null; let assistant = null;
    try {
      turn = await content('/chat/turns', {method: 'POST', body: {message, client_message_id: crypto.randomUUID(), date: state.startDate, timezone: state.timezone}});
      if (epoch !== state.epoch) return;
      list.querySelector('.empty')?.remove(); list.append(chatMessage('user', message, new Date().toISOString()).node); input.value = ''; assistant = chatMessage('assistant', ''); list.append(assistant.node); list.scrollTop = list.scrollHeight;
      await receiveTurn(turn.turn_id, assistant, list, status, epoch);
    } catch (error) {
      if (epoch !== state.epoch || error.name === 'AbortError') return;
      status.replaceChildren(notice(error.message, 'error'));
      if (turn && assistant) status.append(button('Recuperar respuesta', action => busy(action.currentTarget, async () => { await receiveTurn(turn.turn_id, assistant, list, status, epoch); }), 'secondary small', 'refresh'));
    } finally { if (epoch === state.epoch) { sending = false; submit.disabled = false; input.focus(); } }
  });
  input.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); form.requestSubmit(); } });
}
async function receiveTurn(turnId, assistant, list, status, epoch) {
  const abort = new AbortController(); state.stream = abort; let accumulated = ''; let done = false; let streaming = false;
  const update = text => { assistant.content.replaceChildren(...messageContent(text).childNodes); list.scrollTop = list.scrollHeight; };
  try {
    const saved = await content(`/chat/turns/${encodeURIComponent(turnId)}`);
    if (epoch !== state.epoch) return;
    if (saved.status === 'completed') { update(saved.assistant_message || ''); if (saved.proposal && !list.querySelector(`[data-proposal="${CSS.escape(saved.proposal.id)}"]`)) list.append(proposalCard(saved.proposal)); status.replaceChildren('Respuesta guardada en tu espacio.'); return; }
    if (saved.status === 'failed' || saved.status === 'cancelled') throw new Error(saved.error_message || 'No se pudo generar la respuesta.');
    status.replaceChildren(el('span', {class: 'spinner'}), saved.status === 'queued' ? 'Tu asistente está por responder…' : 'Tu asistente está respondiendo…');
    const response = await content(`/chat/turns/${encodeURIComponent(turnId)}/stream`, {raw: true, signal: abort.signal});
    if (!response.body) throw new Error('Este navegador no permite recibir la respuesta en tiempo real.');
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
    while (true) {
      const chunk = await reader.read(); buffer += decoder.decode(chunk.value || new Uint8Array(), {stream: !chunk.done}); const parsed = splitSse(buffer); buffer = parsed.remainder;
      if (epoch !== state.epoch) { await reader.cancel(); return; }
      for (const event of parsed.events) {
        if (event.type === 'token') { accumulated += event.content || ''; streaming = true; update(accumulated); }
        if (event.type === 'proposal' && event.proposal && !list.querySelector(`[data-proposal="${CSS.escape(event.proposal.id)}"]`)) list.append(proposalCard(event.proposal));
        if (event.type === 'error') throw new Error(event.message || 'No se pudo generar la respuesta.');
        if (event.type === 'done') { done = true; status.replaceChildren('Respuesta guardada en tu espacio.'); }
        if (event.type === 'status' && !streaming) status.replaceChildren(el('span', {class: 'spinner'}), event.status === 'queued' ? 'Tu asistente está por responder…' : 'Tu asistente está respondiendo…');
      }
      if (chunk.done) break;
    }
    // Read the durable result even after a complete stream: tokens can have been
    // generated before this browser subscribed, especially on reconnection.
    const result = await content(`/chat/turns/${encodeURIComponent(turnId)}`);
    if (epoch !== state.epoch) return;
    if (result.status !== 'completed') throw new Error(result.error_message || 'Se interrumpió la conexión. El turno sigue guardado; puedes recuperar su respuesta.');
    update(result.assistant_message || accumulated); if (result.proposal && !list.querySelector(`[data-proposal="${CSS.escape(result.proposal.id)}"]`)) list.append(proposalCard(result.proposal)); status.replaceChildren('Respuesta guardada en tu espacio.');
  } finally { abort.abort(); if (state.stream === abort) state.stream = null; }
}
function proposalCard(proposal) {
  const actions = el('div', {class: 'flex wrap'}); const card = el('section', {class: 'proposal', 'data-proposal': proposal.id}, el('p', {class: 'eyebrow'}, 'PROPUESTA PARA TU AGENDA'), el('h3', {}, proposal.summary), el('p', {}, proposal.reason), el('ul', {}, (proposal.resulting_items || []).map(item => el('li', {}, item.action === 'delete' ? 'Eliminar: ' : '', item.title, ' · ', dateTime(item.start_time)))), actions);
  if (proposal.status !== 'pending') actions.append(statusBadge(proposal.status));
  else for (const [action, label, style] of [['confirm', 'Aceptar propuesta', 'small'], ['reject', 'Rechazar', 'secondary small']]) actions.append(button(label, event => busy(event.currentTarget, async () => { actions.querySelectorAll('button').forEach(node => { node.disabled = true; }); try { const result = await content(`/proposals/${encodeURIComponent(proposal.id)}/${action}`, {method: 'POST', body: {}}); actions.replaceChildren(statusBadge(result.status)); toast(result.message || (action === 'confirm' ? 'Propuesta aplicada a tu agenda.' : 'Propuesta rechazada.')); } finally { actions.querySelectorAll('button').forEach(node => { node.disabled = false; }); } }), style, action === 'confirm' ? 'check' : null));
  return card;
}

async function renderDocuments(area, epoch, query = '', offset = 0) {
  const params = new URLSearchParams({include_text: 'false', limit: '30', offset: String(offset)}); if (query) params.set('q', query);
  const result = await content(`/documents?${params}`); if (epoch !== state.epoch) return;
  const listArea = el('div'); const searchInput = el('input', {name: 'query', type: 'search', value: query, placeholder: 'Buscar por título, alias o emisor', 'aria-label': 'Buscar documentos', maxlength: 500});
  const search = el('form', {class: 'search-bar'}, searchInput, el('button', {type: 'submit', class: 'button secondary'}, icon('search'), 'Buscar'), button('Buscar en el contenido', action => busy(action.currentTarget, async () => { const q = searchInput.value.trim(); if (q.length < 2) throw new Error('Escribe al menos dos caracteres para buscar.'); const response = await content(`/documents/search?q=${encodeURIComponent(q)}&limit=10`); if (epoch !== state.epoch) return; renderDocumentSearch(listArea, response.results || [], q); }), 'ghost small'));
  search.addEventListener('submit', async action => { action.preventDefault(); listArea.replaceChildren(loading()); try { await renderDocuments(area, epoch, searchInput.value.trim(), 0); } catch (error) { displayError(listArea, error); } });
  listArea.append(result.documents?.length ? el('div', {class: 'document-grid'}, result.documents.map(documentCard)) : empty(query ? 'No se encontraron documentos' : 'Tus documentos, a mano', query ? 'Prueba otro título o busca dentro del contenido.' : 'Sube un archivo para tenerlo disponible en tu espacio.', 'file', query ? null : button('Subir documento', showUpload, 'secondary small', 'plus')));
  const pagination = el('div', {class: 'flex between wrap'}, el('p', {class: 'auth-footnote'}, `${result.total} documento${result.total === 1 ? '' : 's'}${query ? ` · «${query}»` : ''}`), el('div', {class: 'flex'}));
  if (offset > 0) pagination.lastChild.append(button('Anterior', action => busy(action.currentTarget, () => renderDocuments(area, epoch, query, Math.max(0, offset - 30))), 'secondary small', 'back'));
  if (offset + 30 < result.total) pagination.lastChild.append(button('Siguiente', action => busy(action.currentTarget, () => renderDocuments(area, epoch, query, offset + 30)), 'secondary small', 'arrow'));
  area.replaceChildren(pageHeader('BIBLIOTECA PERSONAL', 'Mis documentos', 'Originales, versiones y búsqueda dentro de tu espacio.', button('Subir documento', showUpload, '', 'plus')), search, listArea, pagination);
}
function documentCard(document) {
  const revision = [...(document.revisions || [])].sort((a, b) => b.version - a.version)[0];
  const type = {generic: 'General', identificacion: 'Identificación', constancia: 'Constancia', factura: 'Factura', medico: 'Médico', tramite: 'Trámite'}[document.doc_type] || document.doc_type;
  return el('article', {class: 'document-card'}, el('div', {class: 'document-icon'}, icon('file')), el('h3', {}, document.title), el('p', {}, document.alias || document.issuer || type), el('p', {}, revision ? `${formatBytes(revision.file_size_bytes)} · Versión ${revision.version}` : 'Sin archivo disponible'), el('p', {}, dateTime(document.updated_at)), el('div', {class: 'flex'}, revision ? link('Descargar', apiPath(`/v1/documents/${encodeURIComponent(document.id)}/download`), 'button secondary small', 'download') : el('span', {class: 'muted'}, 'Sin revisiones'), iconButton('trash', `Eliminar ${document.title}`, () => confirmDeleteDocument(document), true)));
}
function renderDocumentSearch(area, results, query) {
  area.replaceChildren(el('p', {class: 'auth-footnote'}, `Fragmentos encontrados para «${query}». Se consulta el texto de los documentos habilitados para el asistente.`), results.length ? panel('Resultados en el contenido', results.map(result => {
    const id = result.documento_id || result.document_id; const href = id ? apiPath(`/v1/documents/${encodeURIComponent(id)}/versions/${Number(result.version || 1)}/download`) : null;
    return el('article', {class: 'search-result'}, el('h3', {}, result.titulo || result.title || result.filename || 'Documento'), el('p', {}, result.fragmento || result.texto || result.text || result.excerpt || result.snippet || ''), el('small', {class: 'muted'}, `Versión ${result.version || 1}${result.pagina || result.page ? ` · Página ${result.pagina || result.page}` : ''}`), href && el('div', {class: 'auth-footnote'}, link('Abrir original', href, 'button secondary small', 'download')));
  })) : empty('Sin fragmentos coincidentes', 'Prueba términos más concretos. Esta búsqueda incluye documentos con texto extraído y acceso habilitado para el asistente. Puedes buscar cualquier original por su título en el catálogo.', 'search'));
}
function showUpload() {
  const progress = el('progress', {max: 100, value: 0, hidden: true, 'aria-label': 'Progreso de carga'}); const status = el('div', {class: 'chat-status', role: 'status'});
  const form = el('form', {class: 'stack'}, el('div', {class: 'form-error'}), el('div', {class: 'upload-area'}, el('label', {for: 'upload-file'}, 'Seleccionar archivo'), el('p', {class: 'muted'}, 'El original se guardará en tu espacio.'), el('input', {id: 'upload-file', type: 'file', name: 'file', required: true})), field('Título (opcional)', 'title', {maxlength: 300, placeholder: 'Se usará el nombre del archivo'}), field('Tipo de documento', 'doc_type', {tag: 'select'}), progress, status, el('div', {class: 'dialog-footer'}, el('button', {type: 'submit', class: 'button'}, icon('plus'), 'Subir documento')));
  const select = form.querySelector('[name=doc_type]'); [['generic', 'General'], ['identificacion', 'Identificación'], ['constancia', 'Constancia'], ['factura', 'Factura'], ['medico', 'Médico'], ['tramite', 'Trámite']].forEach(([value, text]) => select.append(el('option', {value}, text)));
  const modal = dialog('Subir documento', form);
  form.addEventListener('submit', async action => { action.preventDefault(); const submit = form.querySelector('[type=submit]'); submit.disabled = true; const values = new FormData(form); const file = values.get('file'); progress.hidden = false; progress.value = 0; form.querySelector('.form-error').replaceChildren();
    try {
      if (!file.size) throw new Error('Selecciona un archivo que no esté vacío.');
      status.replaceChildren('Preparando carga…');
      const upload = await content('/documents/uploads', {method: 'POST', body: {filename: file.name, mime_type: file.type || 'application/octet-stream', expected_size_bytes: file.size, title: values.get('title').trim() || file.name, doc_type: values.get('doc_type')}});
      for (let offset = 0; offset < file.size; offset += 1024 * 1024) { const chunk = file.slice(offset, offset + 1024 * 1024); await content(`/documents/uploads/${encodeURIComponent(upload.upload_id)}/content`, {method: 'PUT', body: chunk, headers: {'Content-Type': 'application/octet-stream'}}); progress.value = Math.min(99, (offset + chunk.size) / file.size * 100); status.replaceChildren(`Cargando… ${Math.round(progress.value)} %`); }
      status.replaceChildren('Verificando y guardando el original…'); await content(`/documents/uploads/${encodeURIComponent(upload.upload_id)}/complete`, {method: 'POST', body: {}}); progress.value = 100; modal.close(); toast('Documento guardado en tu espacio.'); showPrivate('documents');
    } catch (error) { formError(form, error); status.replaceChildren('La carga no se completó. Puedes intentar nuevamente.'); } finally { submit.disabled = false; }
  });
}
function confirmDeleteDocument(document) {
  const body = el('div', {class: 'stack'}, el('p', {}, `¿Retirar «${document.title}» de tu biblioteca?`), el('p', {class: 'muted'}, 'Dejará de aparecer en tus documentos y en las búsquedas.'), el('div', {class: 'dialog-footer'})); const modal = dialog('Retirar documento', body);
  body.lastChild.append(button('Cancelar', () => modal.close(), 'secondary'), button('Retirar documento', action => busy(action.currentTarget, async () => { await content(`/documents/${encodeURIComponent(document.id)}`, {method: 'DELETE'}); modal.close(); toast('Documento retirado.'); showPrivate('documents'); }), 'danger', 'trash'));
}

async function renderSettings(area, epoch) {
  const [identity, result] = await Promise.all([content('/auth/me'), api('/platform/v1/devices')]); if (epoch !== state.epoch) return;
  const devices = result.devices || [];
  const timezone = el('select', {id: 'timezone', name: 'timezone'}, [['America/Mexico_City', 'Ciudad de México'], ['America/Monterrey', 'Monterrey'], ['America/Tijuana', 'Tijuana'], ['America/Cancun', 'Cancún'], ['America/Hermosillo', 'Hermosillo'], ['America/New_York', 'Nueva York'], ['Europe/Madrid', 'Madrid']].map(([value, title]) => el('option', {value}, title))); timezone.value = state.timezone;
  timezone.addEventListener('change', () => { state.timezone = timezone.value; state.startDate = state.endDate = localDay(new Date(), state.timezone); toast('Zona horaria actualizada para esta sesión.'); });
  const deviceNodes = devices.length ? el('div', {}, devices.map(device => {
    const current = device.id === state.session.device_id; const active = device.is_active !== false;
    return el('div', {class: 'device'}, icon(device.platform === 'android' || device.platform === 'ios' ? 'phone' : 'spaces'), el('div', {class: 'device-info'}, el('strong', {}, device.device_name, current ? ' · Este navegador' : ''), el('small', {}, `${device.platform || 'Dispositivo'} · ${active ? 'Activo' : 'Revocado'}`), el('small', {}, `Último acceso: ${dateTime(device.last_seen_at)}`)), active && button(current ? 'Cerrar sesión' : 'Revocar', () => confirmRevokeDevice(device, current), 'secondary small'));
  })) : empty('Sin dispositivos disponibles', 'Actualiza para volver a consultar tus sesiones.', 'phone');
  const addDevice = button('Autorizar otro dispositivo', async action => busy(action.currentTarget, async () => { const code = await api('/platform/v1/activation', {method: 'POST', body: {}}); const body = el('div'); dialog('Conectar otro dispositivo', body); renderCode(body, code, state.session.space_name); }), 'secondary small', 'plus');
  area.replaceChildren(pageHeader('TU ESPACIO PERSONAL', 'Ajustes y acceso', 'Identidad, visualización y sesiones de tus dispositivos.'), el('div', {class: 'settings-grid'}, panel('Mi espacio', el('div', {}, metadata([['Espacio', state.session.space_name], ['Dispositivo actual', identity.device_name || state.session.device_name], ['Sesión válida hasta', dateTime(state.session.expires_at)]]), el('label', {for: 'timezone'}, 'Zona horaria para esta sesión'), timezone, el('p', {class: 'auth-footnote'}, 'Este ajuste cambia las fechas y horas que muestra el navegador.'))), panel('Mis dispositivos', deviceNodes, addDevice)));
}
function confirmRevokeDevice(device, current) {
  const body = el('div', {class: 'stack'}, el('p', {}, `¿Revocar el acceso de «${device.device_name}»?`), el('p', {class: 'muted'}, current ? 'Este navegador cerrará su sesión. Para volver a entrar necesitarás un nuevo código.' : 'Este dispositivo necesitará un nuevo código para conectarse. Tu agenda y tus archivos se conservarán.'), el('div', {class: 'dialog-footer'})); const modal = dialog('Revocar dispositivo', body);
  body.lastChild.append(button('Cancelar', () => modal.close(), 'secondary'), button('Revocar acceso', action => busy(action.currentTarget, async () => { await api(`/platform/v1/devices/${encodeURIComponent(device.id)}/revoke`, {method: 'POST', body: {}}); modal.close(); toast('Acceso del dispositivo revocado.'); if (current) { state.session = null; history.replaceState(null, '', '/activar'); showActivation(); } else showPrivate('settings'); }), 'danger', 'lock'));
}

async function bootstrap() {
  if (location.pathname === '/') { showHome(); return; }
  if (location.pathname === '/activar') { showActivation(); return; }
  if (location.pathname === '/admin') {
    root.replaceChildren(publicHeader(), el('main', {id: 'main'}, loading('Comprobando sesión administrativa…')));
    try { state.admin = await control('/auth/me'); showAdmin(); } catch (error) { showAdminLogin(error.status === 401 ? '' : error.message); } return;
  }
  if (location.pathname === '/app') {
    root.replaceChildren(publicHeader(), el('main', {id: 'main'}, loading('Conectando tu espacio…')));
    try { state.session = await api('/platform/v1/session'); showPrivate(); } catch (error) { history.replaceState(null, '', '/activar'); showActivation(); if (error.status !== 401) toast(error.message, true); } return;
  }
  showHome();
}

window.addEventListener('pagehide', stopBackground);
bootstrap();

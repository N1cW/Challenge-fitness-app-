const state = { token: sessionStorage.getItem('challenge_token') || '', user: null, challenges: [], sport: '', currentId: null, socket: null, authMode: 'login' };
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const dateText = (value) => new Intl.DateTimeFormat('ru-RU', {day:'numeric',month:'short',year:'numeric'}).format(new Date(value));

async function api(path, options = {}) {
  const headers = {'Content-Type':'application/json', ...(options.headers || {})};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let response;
  try { response = await fetch(path, {...options, headers}); }
  catch { throw new Error('Нет связи с сервером. Проверьте подключение и попробуйте ещё раз.'); }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === 'string' ? detail : 'Не удалось выполнить запрос. Проверьте данные.');
  }
  return data;
}

function notice(message, error = false) {
  const box = $('#notice'); box.textContent = message; box.classList.toggle('error', error); box.hidden = false;
  setTimeout(() => { box.hidden = true; }, 6000);
}

function account() {
  const area = $('#account-area');
  if (!state.user) { area.innerHTML = '<button class="button button-outline" id="login-open">Войти</button>'; return; }
  area.innerHTML = `<span class="account-name">${esc(state.user.display_name)}</span><button class="button button-outline" id="logout">Выйти</button>`;
}

async function loadMe() {
  if (!state.token) return;
  try { state.user = await api('/api/me'); }
  catch { state.token = ''; sessionStorage.removeItem('challenge_token'); state.user = null; }
  account();
}

function card(challenge) {
  const open = challenge.status === 'open' && new Date(challenge.ends_at) > new Date();
  return `<article class="challenge-card"><div class="card-top"><span class="sport-chip">${esc(challenge.sport)}</span><span class="status-chip ${open?'':'closed'}">${open?'● АКТИВЕН':'● ЗАВЕРШЁН'}</span></div><h3>${esc(challenge.title)}</h3><p>${esc(challenge.description)}</p><div class="card-meta"><span>Цель <strong>${esc(challenge.target_value)} ${esc(challenge.unit)}</strong></span><span>До ${esc(dateText(challenge.ends_at))}</span></div><div class="card-bottom"><span>Участников: ${esc(challenge.participant_count)}</span><button data-detail="${challenge.id}">Подробнее ↗</button></div></article>`;
}

async function loadChallenges() {
  const grid = $('#challenge-grid'); grid.innerHTML = '<div class="loading-card">Загружаем челленджи…</div>';
  try {
    state.challenges = await api('/api/challenges');
    const visible = state.challenges.filter((item) => !state.sport || item.sport === state.sport);
    grid.innerHTML = visible.length ? visible.map(card).join('') : '<div class="empty-card">Пока нет челленджей в этой категории. Выберите другой вид спорта.</div>';
    $('#stat-challenges').textContent = state.challenges.length;
    $('#stat-members').textContent = state.challenges.reduce((total, item) => total + item.participant_count, 0);
  } catch (error) { grid.innerHTML = `<div class="empty-card">${esc(error.message)} <button class="text-button" id="retry-list">Повторить</button></div>`; }
}

function authDialog(mode = 'login') {
  state.authMode = mode;
  $('#auth-title').textContent = mode === 'login' ? 'Вход в аккаунт' : 'Регистрация';
  $('#auth-submit').textContent = mode === 'login' ? 'Войти' : 'Создать аккаунт';
  $('#auth-toggle').textContent = mode === 'login' ? 'Нет аккаунта? Зарегистрироваться' : 'Уже есть аккаунт? Войти';
  $('#register-fields').hidden = mode === 'login';
  $('#auth-error').textContent = '';
  if (!$('#auth-dialog').open) $('#auth-dialog').showModal();
}

function openEditor(challenge = null) {
  if (!state.user) { authDialog(); return; }
  if (!['organizer','admin'].includes(state.user.role)) { notice('Создавать челленджи могут организаторы и администраторы.', true); return; }
  const form = $('#create-form'); form.reset(); form.dataset.editId = challenge ? String(challenge.id) : '';
  form.querySelector('h2').textContent = challenge ? 'Изменить челлендж' : 'Создать челлендж';
  form.querySelector('button[type="submit"]').textContent = challenge ? 'Сохранить изменения' : 'Опубликовать челлендж';
  $('#create-error').textContent = '';
  if (challenge) {
    for (const name of ['title','description','sport','unit','target_value']) form.elements[name].value = challenge[name];
    form.elements.starts_at.value = new Date(challenge.starts_at).toISOString().slice(0,16);
    form.elements.ends_at.value = new Date(challenge.ends_at).toISOString().slice(0,16);
  }
  $('#create-dialog').showModal();
}

function detailHtml(challenge, board, progress) {
  const me = state.user && board.find((row) => row.user_id === state.user.id);
  const owner = state.user && (state.user.role === 'admin' || state.user.id === challenge.created_by);
  const open = challenge.status === 'open' && new Date(challenge.ends_at) > new Date();
  const total = me ? me.total : 0;
  return `<div class="detail-header"><span class="sport-chip">${esc(challenge.sport)}</span><span class="live-indicator" id="live-indicator">● Подключение…</span></div><h2>${esc(challenge.title)}</h2><p class="detail-description">${esc(challenge.description)}</p><div class="detail-stats"><div><span>ЦЕЛЬ</span><strong>${esc(challenge.target_value)} ${esc(challenge.unit)}</strong></div><div><span>УЧАСТНИКИ</span><strong>${esc(challenge.participant_count)}</strong></div><div><span>ДО ОКОНЧАНИЯ</span><strong>${esc(dateText(challenge.ends_at))}</strong></div></div><div class="detail-actions">${!state.user ? '<button class="button button-primary" id="detail-login">Войти для участия</button>' : me ? `<button class="button button-outline" id="leave-challenge">Покинуть</button><span class="my-progress">Мой результат: <b>${total} ${esc(challenge.unit)}</b></span>` : open ? '<button class="button button-primary" id="join-challenge">Присоединиться</button>' : '<span class="my-progress">Челлендж завершён</span>'}${owner ? '<button class="button button-outline" id="edit-challenge">Изменить</button><button class="button button-outline" id="delete-challenge">Удалить</button>' : ''}</div>${me && open ? `<form class="progress-form" id="progress-form"><label>Результат<input name="value" type="number" min="1" max="1000000" required></label><label>Заметка<input name="note" maxlength="240" placeholder="Например, утренняя тренировка"></label><button class="button button-dark" type="submit">Добавить</button></form><p class="form-error" id="progress-error" role="alert"></p>` : ''}<div class="leaderboard"><h3>Таблица участников</h3>${board.length ? board.map((row,index) => `<div class="leaderboard-row"><span>${index+1}. ${esc(row.display_name)} ${row.completed?'✓':''}</span><strong>${esc(row.total)} ${esc(challenge.unit)}</strong></div>`).join('') : '<p class="my-progress">Пока нет участников. Станьте первым!</p>'}</div>${progress?.length ? `<p class="my-progress">Моих записей: ${progress.length}</p>` : ''}`;
}

function closeSocket() { if (state.socket) { state.socket.close(); state.socket = null; } }
function connectSocket(id) {
  closeSocket(); if (!state.token) return;
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(`${protocol}//${location.host}/ws/challenges/${id}`); state.socket = socket;
  socket.addEventListener('open', () => socket.send(JSON.stringify({token: state.token})));
  socket.addEventListener('message', async (event) => {
    let payload; try { payload = JSON.parse(event.data); } catch { return; }
    if (payload.event === 'ready') { if ($('#live-indicator')) $('#live-indicator').textContent = '● Обновления в реальном времени'; return; }
    if (state.currentId === id) { await loadChallenges(); await showDetail(id, false); }
  });
  socket.addEventListener('close', () => { if ($('#live-indicator')) $('#live-indicator').textContent = '○ Нет соединения'; });
}

async function showDetail(id, open = true) {
  state.currentId = id;
  if (open) { $('#detail-content').innerHTML = '<div class="loading-card">Загружаем данные…</div>'; $('#detail-dialog').showModal(); }
  try {
    const [challenge, board, progress] = await Promise.all([api(`/api/challenges/${id}`), api(`/api/challenges/${id}/leaderboard`), state.user ? api(`/api/challenges/${id}/progress`) : Promise.resolve([])]);
    $('#detail-content').innerHTML = detailHtml(challenge, board, progress);
    if (open) connectSocket(id);
  } catch (error) { $('#detail-content').innerHTML = `<p class="form-error">${esc(error.message)}</p>`; }
}

document.addEventListener('click', async (event) => {
  const target = event.target.closest('button'); if (!target) return;
  if (target.dataset.close) { $(`#${target.dataset.close}`).close(); return; }
  if (target.id === 'login-open' || target.id === 'detail-login') { if (target.id === 'detail-login') $('#detail-dialog').close(); authDialog(); return; }
  if (target.id === 'logout') { closeSocket(); state.token=''; state.user=null; sessionStorage.removeItem('challenge_token'); account(); notice('Вы вышли из аккаунта.'); return; }
  if (target.id === 'auth-toggle') { authDialog(state.authMode === 'login' ? 'register' : 'login'); return; }
  if (target.id === 'hero-create' || target.id === 'create-open') { openEditor(); return; }
  if (target.dataset.sport !== undefined) { state.sport = target.dataset.sport; document.querySelectorAll('.filter').forEach((b) => b.classList.toggle('active', b === target)); loadChallenges(); return; }
  if (target.dataset.detail) { showDetail(Number(target.dataset.detail)); return; }
  if (target.id === 'retry-list') { loadChallenges(); return; }
  const id = state.currentId; if (!id) return;
  try {
    if (target.id === 'join-challenge') { await api(`/api/challenges/${id}/join`, {method:'POST'}); notice('Вы присоединились к челленджу.'); await loadChallenges(); await showDetail(id, false); }
    if (target.id === 'leave-challenge') { await api(`/api/challenges/${id}/join`, {method:'DELETE'}); notice('Вы покинули челлендж.'); await loadChallenges(); await showDetail(id, false); }
    if (target.id === 'edit-challenge') { const challenge = await api(`/api/challenges/${id}`); $('#detail-dialog').close(); openEditor(challenge); }
    if (target.id === 'delete-challenge' && confirm('Удалить челлендж и все результаты участников?')) { await api(`/api/challenges/${id}`, {method:'DELETE'}); $('#detail-dialog').close(); closeSocket(); notice('Челлендж удалён.'); loadChallenges(); }
  } catch (error) { notice(error.message, true); }
});

$('#auth-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const form = event.currentTarget; const button = $('#auth-submit'); button.disabled = true; $('#auth-error').textContent = '';
  const fields = Object.fromEntries(new FormData(form));
  try {
    const payload = state.authMode === 'login' ? {email:fields.email,password:fields.password} : fields;
    const result = await api(state.authMode === 'login' ? '/api/auth/login' : '/api/auth/register', {method:'POST',body:JSON.stringify(payload)});
    state.token = result.access_token; state.user = result.user; sessionStorage.setItem('challenge_token', state.token);
    account(); $('#auth-dialog').close(); form.reset(); notice(`Добро пожаловать, ${state.user.display_name}!`);
    if ($('#detail-dialog').open && state.currentId) showDetail(state.currentId);
  } catch (error) { $('#auth-error').textContent = error.message; }
  finally { button.disabled = false; }
});

$('#create-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const form = event.currentTarget; const button = form.querySelector('button[type="submit"]'); button.disabled = true; $('#create-error').textContent = '';
  const fields = Object.fromEntries(new FormData(form));
  const payload = {...fields, target_value:Number(fields.target_value), starts_at:new Date(fields.starts_at).toISOString(), ends_at:new Date(fields.ends_at).toISOString()};
  try {
    const id = form.dataset.editId;
    await api(id ? `/api/challenges/${id}` : '/api/challenges', {method:id?'PATCH':'POST',body:JSON.stringify(payload)});
    $('#create-dialog').close(); form.reset(); notice(id ? 'Челлендж обновлён.' : 'Челлендж создан.'); loadChallenges();
  } catch (error) { $('#create-error').textContent = error.message; }
  finally { button.disabled = false; }
});

$('#detail-content').addEventListener('submit', async (event) => {
  if (event.target.id !== 'progress-form') return; event.preventDefault();
  const form = event.target; const button = form.querySelector('button[type="submit"]'); button.disabled = true;
  const fields = Object.fromEntries(new FormData(form));
  try { await api(`/api/challenges/${state.currentId}/progress`, {method:'POST',body:JSON.stringify({value:Number(fields.value),note:fields.note})}); await loadChallenges(); await showDetail(state.currentId, false); }
  catch (error) { $('#progress-error').textContent = error.message; }
  finally { button.disabled = false; }
});

$('#detail-dialog').addEventListener('close', () => { closeSocket(); state.currentId = null; });
loadMe().then(loadChallenges);

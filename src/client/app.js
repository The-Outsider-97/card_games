/* A small accessible DOM-only client; the Python match engine owns all rules. */
const base = '/api';
const state = { page: 'home', catalog: [], saved: [], stats: {}, prefs: {}, match: null, viewer: null,
  selected: new Set(), lastCard: false, ready: false, setup: { humans: 1, ai: 2, difficulty: 'medium' },
  account: { username: 'Guest', status: 'guest', available: 'false' }, authMode: 'login' };
const root = document.getElementById('app');

function node(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'text') el.textContent = String(value);
    else if (key === 'onClick') el.addEventListener('click', value);
    else if (key === 'onChange') el.addEventListener('change', value);
    else if (key === 'disabled') el.disabled = !!value;
    else if (key === 'value') el.value = value;
    else if (key === 'checked') el.checked = !!value;
    else el.setAttribute(key, String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}
function button(text, onClick, extra = {}) { return node('button', { type: 'button', onClick, ...extra }, text); }
function section(...children) { return node('section', { class: 'panel' }, ...children); }
function title(text, level = 2) { return node(`h${level}`, {}, text); }
function clear(element) { element.replaceChildren(); }
async function api(path, options = {}) {
  const response = await fetch(base + path, { ...options,
    headers: { 'X-SLAI-card_games': '1', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
  let body;
  try { body = await response.json(); } catch { throw new Error(`Server returned HTTP ${response.status}`); }
  if (!response.ok || !body.ok) throw new Error(body.error?.message || `HTTP ${response.status}`);
  return body.data;
}
async function task(action) { try { await action(); render(); } catch (e) { toast(e.message || 'Unexpected error'); } }
function toast(message) {
  const item = node('div', { class: 'toast', role: 'alert' }, message);
  document.body.append(item);
  setTimeout(() => item.remove(), 4500);
}
function nav(page) { state.page = page; state.ready = false; state.selected.clear(); render(); }
function shell(content) {
  const app = node('div', { class: 'shell' });
  const sidebar = node('aside', { class: 'sidebar' },
    node('div', { class: 'brand' }, node('div', { class: 'brand-icon' }, 'CG'), node('div', {}, title('Card Games', 2), node('small', {}, 'POWERED BY SLAI'))),
    node('div', { class: 'nav-list' }, ...[
      ['home', '⌂', 'Home'], ['games', '▦', 'Games'], ['saved', '◷', 'Continue game'],
      ['stats', '◫', 'Statistics'], ['settings', '⚙', 'Settings'], ['account', '♙', 'Account'], ['help', '?', 'How to play'],
    ].map(([id, glyph, label]) => button(`${glyph}   ${label}`, () => nav(id), { class: `nav-button ${state.page === id ? 'active' : ''}` }))),
    button(state.account.username, () => nav('account'), { class: 'account-button' }),
    node('div', { class: 'sidebar-bottom' }, node('div', { class: 'avatar' }, state.account.username.slice(0, 1).toUpperCase()),
      node('div', {}, node('b', {}, state.account.username), node('small', {}, state.account.status === 'guest' ? 'Local guest' : 'Signed in'))));
  const main = node('main', { class: 'main' },
    node('header', { class: 'topbar' }, node('div', { class: 'breadcrumb' }, 'SLAI / ', state.page === 'table' ? 'Playing' : state.page),
      node('div', { class: 'user-status' }, node('span', { class: 'status-dot' }), 'Local & private')),
    node('div', { class: 'content' }, content));
  app.append(sidebar, main);
  return app;
}
function gameTile(item) {
  const playable = item.status === 'playable';
  return node('article', { class: 'game-tile' },
    node('div', { class: 'cover-wrap' }, node('img', { src: item.image, alt: `${item.title} card back`, loading: 'lazy' })),
    node('div', { class: 'tile-body' }, node('div', { class: 'tile-top' },
      node('span', { class: `chip ${playable ? 'green' : 'muted'}` }, playable ? 'PLAYABLE' :
        item.status === 'assets-missing' ? 'ASSETS MISSING' : 'RULES PENDING'),
      node('span', { class: 'minor' }, item.players)), title(item.title, 3),
      node('p', {}, item.description), button(playable ? 'Play now' : 'Unavailable', () => { if (playable) nav('setup'); },
        { class: 'primary full', disabled: !playable })));
}
function home() {
  return node('div', {},
    node('div', { class: 'hero' }, node('div', {}, node('span', { class: 'eyebrow' }, 'YOUR TABLE IS READY'),
      title('Every card tells a story.', 1), node('p', {}, 'Original tabletop games. Strategic decisions. Intelligent opponents.'),
      button('Explore games', () => nav('games'), { class: 'primary' })),
      node('div', { class: 'hero-visual' }, '♠  ♥  ♦  ♣')),
    node('div', { class: 'section-head' }, title('Featured games'), button('View all', () => nav('games'), { class: 'subtle' })),
    node('div', { class: 'tiles' }, ...state.catalog.map(gameTile)),
    node('div', { class: 'section-head' }, title('Jump back in')),
    state.saved.length ? node('div', { class: 'saved-grid' }, ...state.saved.slice(0, 3).map(savedTile)) :
      section(node('p', { class: 'muted' }, 'Your saved matches will appear here after you start playing.')));
}
function savedTile(item) {
  return section(node('div', { class: 'row split' }, node('div', {}, title(item.players.join(' · '), 3),
    node('p', { class: 'minor' }, item.completed ? `Finished · winner ${item.winner}` : `In progress · move ${item.revision}`)),
    button(item.completed ? 'Review' : 'Continue', () => task(async () => {
      state.match = await api(`/matches/${item.id}?viewer=`);
      state.viewer = null; state.page = 'table'; state.ready = false;
    }), { class: 'primary' })));
}
function games() { return node('div', {}, node('span', { class: 'eyebrow' }, 'THE COLLECTION'),
  title('Choose your game', 1), node('p', { class: 'muted' }, 'Different games can share cards, but each has its own rules.'),
  node('div', { class: 'tiles' }, ...state.catalog.map(gameTile))); }
function setup() {
  const humans = state.setup.humans, ai = state.setup.ai;
  function numberInput(label, key, max) {
    return node('label', { class: 'form-field' }, node('span', {}, label), node('input', {
      type: 'number', min: key === 'humans' ? '1' : '0', max: String(max), value: String(state.setup[key]),
      onChange: event => { state.setup[key] = Math.max(key === 'humans' ? 1 : 0, Math.min(max, Number(event.target.value) || 0)); render(); },
    }));
  }
  return node('div', { class: 'narrow' }, node('span', { class: 'eyebrow' }, 'NEW MATCH'), title('Set the table', 1),
    node('p', { class: 'muted' }, 'Four-Color · 2–8 players · 7 cards each · no stacking'),
    section(title('Players', 3), node('div', { class: 'form-grid' }, numberInput('Local human players', 'humans', 8), numberInput('AI opponents', 'ai', 7)),
      node('p', { class: 'minor' }, `Total ${humans + ai} players. First seat is always human.`),
      node('label', { class: 'form-field' }, node('span', {}, 'SLAI opponent difficulty'),
        node('select', { onChange: event => { state.setup.difficulty = event.target.value; } },
          ...['easy', 'medium', 'hard', 'expert'].map(d => node('option', { value: d,
            ...(d === state.setup.difficulty ? { selected: '' } : {}) }, d)))),
      node('div', { class: 'row' }, button('Back', () => nav('games')),
        button('Start match', () => task(async () => {
          if (humans + ai < 2 || humans + ai > 8) throw new Error('Choose between 2 and 8 players.');
          const participants = [
            ...Array.from({ length: humans }, (_, i) => ({ id: `human${i + 1}`, name: `Player ${i + 1}`, kind: 'human' })),
            ...Array.from({ length: ai }, (_, i) => ({ id: `ai${i + 1}`, name: `SLAI ${i + 1}`, kind: 'ai' })),
          ];
          state.match = await api('/matches', { method: 'POST', body: JSON.stringify({ game: 'four-color', participants, difficulty: state.setup.difficulty }) });
          state.viewer = null; state.ready = false; state.page = 'table';
          state.saved = await api('/matches'); state.stats = await api('/stats');
        }), { class: 'primary' }))));
}
function image(card, className = '') { return node('img', { src: `/assets/colors/${card}.jpg`, class: className, alt: card.replace('-', ' '), loading: 'lazy' }); }
async function choose(message, options) {
  return new Promise(resolve => {
    const shade = node('div', { class: 'modal-shade' });
    const grid = node('div', { class: 'choice-grid' }, ...options.map(([value, name]) => button(name, () => {
      shade.remove(); resolve(value);
    }, { class: 'choice' })));
    shade.append(section(title(message, 3), grid)); document.body.append(shade);
  });
}
async function refreshMatch(viewer = state.viewer) {
  state.match = await api(`/matches/${state.match.id}?viewer=${encodeURIComponent(viewer || '')}`);
  state.viewer = viewer;
}
async function perform(actor, command, args = {}) {
  const match = state.match;
  await api(`/matches/${match.id}/actions`, { method: 'POST', body: JSON.stringify({ actor, command, args, revision: match.revision }) });
  state.selected.clear(); state.lastCard = false; state.ready = false;
  await refreshMatch(null);
}
async function playCard(card) {
  const match = state.match, player = match.players[match.current];
  const family = card.slice(0, card.lastIndexOf('-'));
  const neutral = card.endsWith('-neutral');
  const args = { card, last_card: state.lastCard };
  if (neutral) args.color = await choose('Choose the next color', ['blue', 'green', 'red', 'yellow'].map(c => [c, c.toUpperCase()]));
  if (family === 'Wild') args.number = await choose('Declare a number', Array.from({ length: 14 }, (_, i) => [i, String(i)]));
  if (family === 'verdict') args.target = await choose('Select an opponent', match.players.filter(p => p.id !== player.id).map(p => [p.id, p.name]));
  if (family === 'steal') args.steal = await choose('Take an earlier discard', match.stealable.map(c => [c, c]));
  await perform(player.id, 'play', args);
}
function table() {
  const m = state.match;
  if (!m) return section('No match selected.');
  const pendingId = m.outstanding?.find(x => m.players.find(p => p.id === x.player)?.kind === 'human')?.player;
  const current = m.players[m.current];
  const nextId = pendingId || (current.kind === 'human' ? current.id : null);
  if (!m.winner && (!state.ready || state.viewer !== nextId)) {
    return node('div', { class: 'narrow reveal' }, node('span', { class: 'eyebrow' }, 'PRIVATE TURN'),
      title(nextId ? `Pass the device to ${m.players.find(p => p.id === nextId)?.name}` : 'Computer is playing', 1),
      node('p', { class: 'muted' }, 'Other hands remain hidden until the next player confirms.'),
      button('Reveal my cards', () => task(async () => { await refreshMatch(nextId); state.ready = true; }),
        { class: 'primary', disabled: !nextId }), button('Return home', () => nav('home')));
  }
  const me = m.players.find(p => p.id === state.viewer);
  const choice = m.choices?.[0];
  return node('div', { class: 'game-screen' },
    node('div', { class: 'row split' }, node('div', {}, node('span', { class: 'eyebrow' }, 'FOUR-COLOR'),
      title(m.winner ? `${m.players.find(p => p.id === m.winner)?.name} wins!` : `${current.name}'s turn`, 2)),
      node('div', { class: 'row' }, button('Rules', () => nav('help')), button('Leave table', () => nav('home')))),
    node('div', { class: 'opponents' }, ...m.players.filter(p => p.id !== state.viewer).map(p =>
      node('div', { class: `opponent ${p.id === current.id ? 'current' : ''}` },
        node('span', { class: 'avatar mini' }, p.kind === 'ai' ? 'AI' : 'P'), node('b', {}, p.name),
        node('span', { class: 'minor' }, `${p.count} cards${p.verdict ? ` · ${p.verdict} missed` : ''}`)))),
    node('div', { class: 'playing-field' }, node('div', { class: 'piles' },
      node('div', { class: 'pile' }, image('cover'), node('span', {}, `Draw · ${m.draw_count}`)),
      node('div', { class: 'pile' }, image(m.discard[m.discard.length - 1]), node('span', {}, 'Discard'))),
      node('div', { class: 'state-badges' }, node('span', { class: `color-dot ${m.active_color}` }),
        `Active ${m.active_color} · ${m.direction === 1 ? 'Clockwise ↻' : 'Counterclockwise ↺'}`,
        m.wild_rank == null ? '' : ` · Rank ${m.wild_rank}`,
        m.stop_player != null ? ' · STOP active' : '')),
    me ? node('div', { class: 'hand-area' }, node('div', { class: 'row split' }, title(`${me.name}'s hand`, 3),
      node('div', { class: 'row' },
        button(state.lastCard ? 'LAST CARD! ✓' : 'Call LAST CARD!', () => { state.lastCard = !state.lastCard; render(); },
          { class: state.lastCard ? 'primary' : 'secondary', disabled: !!choice || !!m.winner }),
        button('Draw', () => task(() => perform(me.id, 'draw')), { class: 'primary', disabled: !!choice || !!m.winner || m.current !== m.players.indexOf(me) || !!m.turn_drawn }),
        button('End turn', () => task(() => perform(me.id, 'pass')), { disabled: !m.turn_drawn || !!choice }))),
      node('div', { class: 'hand' }, ...me.hand.map(c => {
        const selectable = choice ? true : m.legal.includes(c);
        return button('', () => choice ? (state.selected.has(c) ? state.selected.delete(c) : state.selected.add(c), render()) :
          task(() => playCard(c)), { class: `hand-card ${selectable ? 'legal' : ''} ${state.selected.has(c) ? 'selected' : ''}`,
            disabled: !selectable, 'aria-label': `${c} ${selectable ? 'selectable' : 'unplayable'}`,
            title: c, 'data-card': c });
      }).map((btn, i) => { btn.append(image(me.hand[i])); return btn; })),
      choice ? section(node('p', {}, `Select ${choice.count} ${choice.count === 1 ? 'card' : 'cards'} for ${choice.kind}.`),
        button('Confirm selection', () => task(() => perform(me.id, 'select', { cards: [...state.selected] })),
          { class: 'primary', disabled: state.selected.size !== choice.count })) : null,
      m.challenge_open && m.last_uncalled != null && m.players[m.last_uncalled].id !== me.id ?
        button('Challenge a missed LAST CARD!', () => task(() => perform(me.id, 'challenge')), { class: 'warning' }) : null)
      : section('Game completed. Return to Home or review another game.'),
    node('div', { class: 'events' }, title('Table history', 3),
      ...m.events.slice(-5).reverse().map(e => node('div', { class: 'event' }, e.type.replace('_', ' '),
        e.player ? ` · ${e.player}` : '', e.card ? ` · ${e.card}` : ''))));
}
function settings() {
  const p = state.prefs;
  function selection(name, options, field) {
    return node('label', { class: 'form-field' }, node('span', {}, name), node('select', {
      onChange: event => task(async () => { state.prefs = await api('/settings', { method: 'PUT', body: JSON.stringify({ [field]: event.target.value }) });
        document.documentElement.dataset.theme = state.prefs.theme; }),
    }, ...options.map(opt => node('option', { value: opt, selected: opt === p[field] ? '' : null }, opt))));
  }
  return node('div', { class: 'narrow' }, title('Settings', 1), section(title('Appearance & gameplay', 3),
    selection('Theme', ['dark', 'light', 'contrast'], 'theme'), selection('Default AI difficulty', ['easy', 'medium', 'hard', 'expert'], 'difficulty'),
    node('p', { class: 'minor' }, 'Preferences are saved locally with SLAI’s database toolkit.')));
}
function stats() {
  const info = state.stats;
  return node('div', {}, title('Your games', 1), node('div', { class: 'metrics' },
    section(title(String(info.total || 0), 1), 'Total matches'), section(title(String(info.completed || 0), 1), 'Completed'),
    section(title(String(info.human_wins || 0), 1), 'Human wins')),
    node('p', { class: 'minor' }, `AI wins: ${info.ai_wins || 0} · Average duration: ${info.avg_duration_seconds == null ? 'Not available' : `${Math.round(info.avg_duration_seconds / 60)} minutes`}`),
    node('div', { class: 'saved-grid' }, ...state.saved.map(savedTile)));
}
function help() {
  return node('div', { class: 'narrow' }, title('How to play Four-Color', 1),
    section(title('Objective', 3), node('p', {}, 'Be first to discard every card. Everyone starts with seven cards.'),
      title('Match', 3), node('p', {}, 'Play a matching color, rank, letter or action. Neutral cards let you choose the next color.'),
      title('Your turn', 3), node('p', {}, 'Play one legal card or draw one. Only the drawn card can be played immediately.'),
      title('Special actions', 3), node('p', {}, 'Draw penalties, Skip, Reverse, Stop, Verdict, Equality, Swap, Steal, Cycle and Wild follow the prototype rules.'),
      title('Finish', 3), node('p', {}, 'Call LAST CARD when one card remains. Playing your final card wins before its action occurs.'),
      node('p', { class: 'minor' }, 'Prototype v1.0: Cycle and some rule parameters remain provisional.')));
}
function accountPage() {
  const signed = state.account.status === 'signed-in';
  if (signed) return node('div', { class: 'narrow' }, title('Your profile', 1),
    section(title(`Welcome, ${state.account.username}`, 3), node('p', { class: 'muted' }, 'Your saved matches and preferences are kept in your account.'),
      button('Log out', () => task(async () => {
        await api('/account/logout', { method: 'POST' }); await refreshAccount(); nav('home');
      }), { class: 'primary' })));
  if (state.account.available !== 'true') return node('div', { class: 'narrow' }, title('Accounts unavailable', 1),
    section(node('p', {}, 'SLAI authentication is not currently available. Guest games remain fully playable locally.')));
  const username = node('input', { type: 'text', placeholder: 'Username', autocomplete: 'username', maxlength: 32 });
  const password = node('input', { type: 'password', placeholder: 'Password', autocomplete: state.authMode === 'login' ? 'current-password' : 'new-password' });
  const isLogin = state.authMode === 'login';
  return node('div', { class: 'narrow' }, title(isLogin ? 'Log in' : 'Create an account', 1),
    section(node('label', { class: 'form-field' }, node('span', {}, 'Username'), username),
      node('label', { class: 'form-field' }, node('span', {}, 'Password'), password),
      node('p', { class: 'minor' }, isLogin ? 'Your account is managed by SLAI authentication.' :
        'Use a strong password that meets the SLAI credential policy.'),
      node('div', { class: 'row' },
        button(isLogin ? 'Log in' : 'Sign up', () => task(async () => {
          await api(`/account/${isLogin ? 'login' : 'signup'}`, { method: 'POST',
            body: JSON.stringify({ username: username.value, password: password.value }) });
          if (isLogin) { await refreshAccount(); nav('home'); }
          else { state.authMode = 'login'; toast('Account created. You can now log in.'); }
        }), { class: 'primary' }),
        button(isLogin ? 'Create account' : 'I already have an account', () => { state.authMode = isLogin ? 'signup' : 'login'; render(); }))));
}
async function refreshAccount() {
  state.account = await api('/account');
  state.saved = await api('/matches');
  state.stats = await api('/stats');
  state.prefs = await api('/settings');
  state.setup.difficulty = state.prefs.difficulty;
  document.documentElement.dataset.theme = state.prefs.theme;
  state.match = null;
}
function render() {
  const content = state.page === 'home' ? home() : state.page === 'games' ? games() :
    state.page === 'setup' ? setup() : state.page === 'table' ? table() : state.page === 'settings' ? settings() :
    state.page === 'saved' ? node('div', {}, title('Saved matches', 1), ...state.saved.map(savedTile)) :
    state.page === 'stats' ? stats() : state.page === 'account' ? accountPage() : help();
  clear(root); root.append(shell(content));
}
async function initialize() {
  try {
    [state.catalog, state.saved, state.prefs, state.account, state.stats] = await Promise.all([
      api('/catalog'), api('/matches'), api('/settings'), api('/account'), api('/stats')]);
    document.documentElement.dataset.theme = state.prefs.theme;
    state.setup.difficulty = state.prefs.difficulty;
    render();
  } catch (e) { root.replaceChildren(section(title('Unable to start Card Games'), node('p', {}, e.message))); }
}
initialize();

/* A small accessible DOM-only client; the Python match engine owns all rules. */
const base = '/api';
const state = { page: 'home', catalog: [], saved: [], stats: {}, prefs: {}, match: null, viewer: null,
  selected: new Set(), lastCard: false, ready: false, plan: [],
  setup: { game: 'four-color', humans: 1, ai: 2, difficulty: 'medium', shortGame: false, partnership: false },
  account: { username: 'Guest', status: 'guest', available: 'false' }, profile: { display_name: 'Guest', avatar: 'initials' },
  authMode: 'login', remote: null, invite: null, matchSource: 'local',
  handoffBusy: false, revealAnimation: false, justSelectedCard: null };
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
async function remoteApi(path, options = {}) {
  if (!state.remote) throw new Error('Connect to an online room first.');
  const headers = { ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    ...(state.remote.token ? { Authorization: `Bearer ${state.remote.token}` } : {}), ...options.headers };
  const response = await fetch(state.remote.server + path, { ...options, headers });
  const body = await response.json();
  if (!response.ok || !body.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body.data;
}
async function task(action) { try { await action(); render(); } catch (e) { toast(e.message || 'Unexpected error'); } }
function toast(message) {
  const item = node('div', { class: 'toast', role: 'alert' }, message);
  document.body.append(item);
  setTimeout(() => item.remove(), 4500);
}
function nav(page) {
  if (page === 'online' && state.remote?.room) {
    task(async () => { state.match = await remoteApi(`/rooms/${state.remote.room}`);
      state.viewer = state.remote.seat; state.matchSource = 'remote'; state.page = 'online'; });
    return;
  }
  const readingRules = page === 'help' && state.page === 'table';
  state.page = page; if (!readingRules) state.ready = false;
  state.revealAnimation = false; state.selected.clear(); render();
}
function returnFromRules() { state.page = 'table'; render(); }
async function playAgain() {
  if (!state.match || state.matchSource !== 'local') throw new Error('Replay is available for completed local matches.');
  const next = await api(`/matches/${state.match.id}/rematch`, { method: 'POST' });
  state.match = next; state.viewer = null; state.ready = false;
  state.plan = []; state.selected.clear(); state.lastCard = false;
  state.matchSource = 'local'; state.page = 'table';
  const solo = soloHumanId(next);
  if (solo) { state.viewer = solo; state.ready = true; state.revealAnimation = motionEnabled(); }
  [state.saved, state.stats] = await Promise.all([api('/matches'), api('/stats')]);
}
function replayButton() {
  return state.matchSource === 'local' ? button('Play again', () => task(playAgain), { class: 'primary' }) :
    button('Create another online room', () => nav('online'), { class: 'primary' });
}
function shell(content) {
  const app = node('div', { class: 'shell' });
  const sidebar = node('aside', { class: 'sidebar' },
    node('div', { class: 'brand' }, node('div', { class: 'brand-icon' }, 'CG'), node('div', {}, title('Card Games', 2), node('small', {}, 'POWERED BY SLAI'))),
    node('div', { class: 'nav-list' }, ...[
      ['home', '⌂', 'Home'], ['games', '▦', 'Games'], ['online', '◇', 'Online rooms'], ['saved', '◷', 'Continue game'],
      ['stats', '◫', 'Statistics'], ['settings', '⚙', 'Settings'], ['account', '♙', 'Account'], ['help', '?', 'How to play'],
    ].map(([id, glyph, label]) => button(`${glyph}   ${label}`, () => nav(id), { class: `nav-button ${state.page === id ? 'active' : ''}` }))),
    button(state.account.username, () => nav('account'), { class: 'account-button' }),
    node('div', { class: 'sidebar-bottom' }, node('div', { class: 'avatar' }, state.account.username.slice(0, 1).toUpperCase()),
      node('div', {}, node('b', {}, state.account.username), node('small', {}, state.account.status === 'guest' ? 'Local guest' : 'Signed in'))));
  const main = node('main', { class: 'main' },
    node('header', { class: 'topbar' }, node('div', { class: 'breadcrumb' }, 'SLAI / ', state.page === 'table' ? 'Playing' : state.page),
      node('div', { class: 'user-status' }, node('span', { class: 'status-dot' }), state.matchSource === 'remote' ? 'Online room' : 'Local & private')),
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
      node('p', {}, item.description), button(playable ? 'Play now' : 'Unavailable', () => {
        if (playable) { state.setup.game = item.id; state.setup.ai = item.id === 'four-color' ? 2 : 1; nav('setup'); }
      },
        { class: 'primary full', disabled: !playable })));
}
function soloHumanId(match) {
  const humans = match?.players?.filter(player => player.kind === 'human') || [];
  return humans.length === 1 ? humans[0].id : null;
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
    node('p', { class: 'minor' }, item.completed ?
      `Finished · ${item.winners?.length ? `winner ${item.winners.join(', ')}` : item.winner ? `winner ${item.winner}` : 'draw'}` :
      `In progress · move ${item.revision}`)),
    button(item.completed ? 'Review' : 'Continue', () => task(async () => {
      state.match = await api(`/matches/${item.id}?viewer=`);
      state.viewer = null; state.plan = []; state.page = 'table'; state.ready = false; state.matchSource = 'local';
      const onlyHuman = soloHumanId(state.match);
      if (onlyHuman) { await refreshMatch(onlyHuman); state.ready = true; }
    }), { class: 'primary' })));
}
function games() { return node('div', {}, node('span', { class: 'eyebrow' }, 'THE COLLECTION'),
  title('Choose your game', 1), node('p', { class: 'muted' }, 'Different games can share cards, but each has its own rules.'),
  node('div', { class: 'tiles' }, ...state.catalog.map(gameTile))); }
function setup() {
  const humans = state.setup.humans, ai = state.setup.ai;
  const fourfold = state.setup.game === 'fourfold';
  const skipBo = state.setup.game === 'skip-bo';
  const limit = state.setup.game === 'four-color' ? 8 : 6;
  function numberInput(label, key, max) {
    return node('label', { class: 'form-field' }, node('span', {}, label), node('input', {
      type: 'number', min: key === 'humans' ? '1' : '0', max: String(max), value: String(state.setup[key]),
      onChange: event => { state.setup[key] = Math.max(key === 'humans' ? 1 : 0, Math.min(max, Number(event.target.value) || 0)); render(); },
    }));
  }
  return node('div', { class: 'narrow' }, node('span', { class: 'eyebrow' }, 'NEW MATCH'), title('Set the table', 1),
    node('p', { class: 'muted' }, state.catalog.find(item => item.id === state.setup.game)?.description ||
      (fourfold ? 'Fourfold Mandate · 2–6 players' : 'Four-Color · 2–8 players')),
    section(title('Players', 3), node('div', { class: 'form-grid' }, numberInput('Local human players', 'humans', limit), numberInput('AI opponents', 'ai', limit - 1)),
      node('p', { class: 'minor' }, `Total ${humans + ai} players. First seat is always human.`),
      node('label', { class: 'form-field' }, node('span', {}, 'SLAI opponent difficulty'),
        node('select', { onChange: event => { state.setup.difficulty = event.target.value; } },
          ...['easy', 'medium', 'hard', 'expert'].map(d => node('option', { value: d,
            ...(d === state.setup.difficulty ? { selected: '' } : {}) }, d)))),
      skipBo ? node('div', { class: 'form-grid' },
        node('label', { class: 'row motion-setting' }, node('input', { type: 'checkbox', checked: state.setup.shortGame,
          onChange: event => { state.setup.shortGame = event.target.checked; render(); } }),
        node('span', {}, 'Short game · 10 stock cards per player')),
        node('label', { class: 'row motion-setting' }, node('input', { type: 'checkbox', checked: state.setup.partnership,
          onChange: event => { state.setup.partnership = event.target.checked; render(); } }),
        node('span', {}, 'Partnerships · 4 or 6 players, alternating seats')),
        state.setup.partnership ? node('p', { class: 'minor' }, 'Team members share access to each other’s visible stock and discard tops. Each team must clear both stockpiles.') : null) : null,
      node('div', { class: 'row' }, button('Back', () => nav('games')),
        button('Start match', () => task(async () => {
          if (humans + ai < 2 || humans + ai > limit) throw new Error(`Choose between 2 and ${limit} players.`);
          if (skipBo && state.setup.partnership && ![4, 6].includes(humans + ai))
            throw new Error('Partnership Skip-Bo requires four or six players.');
          const participants = [
            ...Array.from({ length: humans }, (_, i) => ({ id: `human${i + 1}`, name: `Player ${i + 1}`, kind: 'human' })),
            ...Array.from({ length: ai }, (_, i) => ({ id: `ai${i + 1}`, name: `SLAI ${i + 1}`, kind: 'ai' })),
          ];
          state.match = await api('/matches', { method: 'POST', body: JSON.stringify({
            game: state.setup.game, participants, difficulty: state.setup.difficulty,
            ...(skipBo ? { options: { short_game: state.setup.shortGame, partnership: state.setup.partnership } } : {}),
          }) });
          state.viewer = null; state.ready = false; state.plan = []; state.page = 'table'; state.matchSource = 'local';
          const onlyHuman = soloHumanId(state.match);
          if (onlyHuman) { state.viewer = onlyHuman; state.ready = true; state.revealAnimation = motionEnabled(); }
          state.saved = await api('/matches'); state.stats = await api('/stats');
        }), { class: 'primary' }))));
}
function cardArtPath(card, collection = 'colors') {
  // The SLAI static-file allowlist excludes '+': use the narrowly scoped art
  // route only for those physical faces, preserving their original filenames.
  return collection === 'colors' && card.startsWith('+') ? `/api/card-art/plus${encodeURIComponent(card.slice(1))}` :
    `/assets/${collection}/${encodeURIComponent(card)}.jpg`;
}
function image(card, className = '', eager = false, collection = 'colors') {
  const element = node('img', { src: cardArtPath(card, collection), class: className,
    alt: card.replace('-', ' '), loading: eager ? 'eager' : 'lazy' });
  element.addEventListener('error', () => element.replaceWith(node('span', {
    class: 'art-fallback', role: 'img', 'aria-label': `${card} artwork unavailable`,
  }, card)));
  return element;
}
function discardStack(cards) {
  const recent = cards.slice(-4);
  return node('div', { class: 'discard-stack', role: 'group',
    'aria-label': `Recent discards: ${recent.join(', ')}` }, ...recent.map((card, index) => {
    const face = image(card, 'discard-card', true);
    face.style.left = `${index * 21}px`;
    face.style.zIndex = String(index + 1);
    return face;
  }));
}
function fourfoldArt(card) {
  const aliases = { 'queen-hearts': 'queen-heart', 'queen-spades': 'queen-spade', 'king-spades': 'king-spade' };
  if (card === 'king-hearts') return node('span', { class: 'art-fallback', role: 'img', 'aria-label': 'King of Hearts artwork missing' }, 'K ♥');
  const el = node('img', { src: `/assets/fourfold/${aliases[card] || card}.jpg`, alt: card.replace('-', ' '), loading: 'lazy' });
  el.addEventListener('error', () => el.replaceWith(node('span', { class: 'art-fallback' }, card)));
  return el;
}
function motionEnabled() {
  return state.prefs.motion !== false &&
    !(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false);
}
function applyAppearance() {
  document.documentElement.dataset.theme = state.prefs.theme;
  document.documentElement.dataset.motion = state.prefs.motion === false ? 'reduce' : 'normal';
}
function handoffPanel(game, next, label) {
  const collection = game === 'fourfold' ? 'fourfold' : ['21', 'blackjack', 'knuckles'].includes(game) ? 'symbols' : 'colors';
  const visual = node('div', { class: 'handoff-card', 'aria-hidden': 'true' },
    node('div', { class: 'handoff-card-inner' },
      node('div', { class: 'handoff-card-side handoff-card-back' },
        node('img', { src: `/assets/${collection}/cover.jpg`, alt: '' })),
      node('div', { class: 'handoff-card-side handoff-card-front' }, '♠  ♥  ♦  ♣')));
  const confirm = button(next ? `I'm ${next.name} — Reveal ${label}` : 'Waiting for player',
    () => task(async () => {
      if (!next || state.handoffBusy) return;
      state.handoffBusy = true;
      confirm.disabled = true;
      const animate = motionEnabled();
      try {
        if (animate) {
          visual.classList.add('is-flipping');
          await new Promise(resolve => setTimeout(resolve, 390));
        }
        await refreshMatch(next.id);
        state.ready = true;
        state.plan = [];
        state.revealAnimation = animate;
      } catch (error) {
        visual.classList.remove('is-flipping');
        confirm.disabled = false;
        throw error;
      } finally {
        state.handoffBusy = false;
      }
    }), { class: 'primary handoff-confirm', disabled: !next });
  return node('section', { class: 'panel handoff-panel', role: 'group', 'aria-label': 'Private turn handoff' },
    visual,
    node('div', { class: 'handoff-copy' }, node('span', { class: 'eyebrow' }, 'PRIVATE HANDOFF'),
      title(next ? `${next.name}, you're up` : 'Waiting for the next player', 3),
      node('p', { class: 'muted' }, 'The table stays visible. Your private cards and orders remain concealed until you confirm.'),
      node('div', { class: 'row handoff-actions' }, confirm,
        button('Return home', () => nav('home'), { class: 'subtle' }))));
}
async function animatePlayedCard(card, target, collection = 'colors') {
  const source = [...document.querySelectorAll('[data-card]')].find(el => el.getAttribute('data-card') === card);
  if (!source || !target || !motionEnabled()) return;
  await cardFlight({ source, target, card: card.split('~')[0], collection, reveal: false });
}
async function cardFlight({ source, target, card, collection = 'colors', reveal = true, label = '' }) {
  // A presentation-only animation: server state has already been validated.
  // The entire card moves; only the inner faces rotate, ending face-up.
  if (!source || !target || !card || !motionEnabled() || state.page !== 'table') return;
  const start = source.getBoundingClientRect(), end = target.getBoundingClientRect();
  const width = 90, height = 128;
  const fromX = start.left + (start.width - width) / 2, fromY = start.top + (start.height - height) / 2;
  const dx = end.left + (end.width - width) / 2 - fromX;
  const dy = end.top + (end.height - height) / 2 - fromY;
  const flight = node('div', { class: `ai-flight-card ${reveal ? '' : 'face-up-flight'}` },
    node('div', { class: 'ai-flight-inner' },
      node('div', { class: 'ai-flight-back' }, image('cover', '', true, collection)),
      node('div', { class: 'ai-flight-front' }, image(card, '', true, collection))));
  flight.style.left = `${fromX}px`; flight.style.top = `${fromY}px`;
  const overlay = node('div', { class: 'ai-flight-overlay', 'aria-live': 'polite' },
    label ? node('div', { class: 'ai-flight-label' }, label) : null, flight);
  document.body.append(overlay);
  try {
    const movement = flight.animate([
      { transform: 'translate(0, 0) scale(.78)', opacity: .9 },
      { transform: `translate(${dx * .58}px, ${dy * .58}px) scale(1.05)`, opacity: 1, offset: .58 },
      { transform: `translate(${dx}px, ${dy}px) scale(1)`, opacity: 1 },
    ], { duration: 540, easing: 'cubic-bezier(.22,.8,.25,1)', fill: 'forwards' });
    const motions = [movement.finished];
    if (reveal) {
      const flip = flight.querySelector('.ai-flight-inner').animate([
        { transform: 'rotateY(0deg)' },
        { transform: 'rotateY(180deg)', offset: .78 },
        { transform: 'rotateY(180deg)' },
      ], { duration: 540, easing: 'ease-out', fill: 'forwards' });
      motions.push(flip.finished);
    }
    await Promise.race([Promise.all(motions).catch(() => {}),
      new Promise(resolve => setTimeout(resolve, 680))]);
    target.classList.add('card-arrived');
  } catch (error) {
    console.warn('Card animation unavailable:', error);
  } finally { overlay.remove(); }
}
async function choose(message, options, { cards = false, cancel = false } = {}) {
  return new Promise(resolve => {
    const shade = node('div', { class: `modal-shade ${cards ? 'modal-card-choice' : ''}` });
    const grid = node('div', { class: `choice-grid ${cards ? 'card-choice-grid' : ''}` }, ...options.map(([value, name]) => {
      const choice = button(cards ? '' : name, () => { shade.remove(); resolve(value); },
        { class: `choice ${cards ? 'card-choice' : ''}`, 'aria-label': String(name) });
      if (cards) choice.append(image(value), node('span', {}, name));
      return choice;
    }));
    shade.append(section(title(message, 3), grid,
      cancel ? button('Cancel', () => { shade.remove(); resolve(null); }, { class: 'subtle choice-cancel' }) : null));
    document.body.append(shade);
  });
}
function recentAiPlays(before, after) {
  if (before?.game !== 'four-color' || after?.game !== 'four-color') return [];
  return newEventsSince(before, after).filter(event => event.type === 'play' &&
    after.players.some(player => player.id === event.player && player.kind === 'ai')).slice(-4);
}
function newEventsSince(before, after) {
  if (!before || !after || after.revision <= before.revision) return [];
  const oldEvents = before.events || [], newEvents = after.events || [];
  let overlap = Math.min(oldEvents.length, newEvents.length);
  while (overlap > 0 && JSON.stringify(oldEvents.slice(-overlap)) !== JSON.stringify(newEvents.slice(0, overlap))) overlap--;
  return newEvents.slice(overlap);
}
async function animateAiPlays(events, players, initialDiscards = []) {
  if (!events.length || !motionEnabled() || state.page !== 'table') return;
  let discard = document.querySelector('[data-pile="discard"] .discard-stack');
  const field = document.querySelector('.playing-field');
  if (!discard || !field) return;
  const shown = initialDiscards.slice(-4);
  for (const event of events) {
    if (state.page !== 'table') break;
    const player = players.find(p => p.id === event.player);
    const seat = [...document.querySelectorAll('.opponent')].find(el => el.getAttribute('data-player-id') === event.player);
    await cardFlight({ source: seat || field, target: discard.lastElementChild || discard,
      card: event.card, label: `${player?.name || 'SLAI'} plays ${event.card}` });
    shown.push(event.card);
    const replacement = discardStack(shown);
    discard.replaceWith(replacement);
    discard = replacement;
  }
}
async function animateVariantMoves(before, after, actor, command, args) {
  if (!motionEnabled() || state.page !== 'table' || !['skip-bo', 'knuckles'].includes(after.game)) return;
  const publicMoves = newEventsSince(before, after).filter(event =>
    (event.type === 'play' || event.type === 'discard') && event.card);
  const selected = publicMoves.filter(e => e.player === actor).slice(0, 1);
  const aiPlays = publicMoves.filter(e => after.players.some(p => p.id === e.player && p.kind === 'ai')).slice(-4);
  for (const event of [...selected, ...aiPlays]) {
    if (state.page !== 'table') break;
    const target = event.type === 'play' ?
      [...document.querySelectorAll('[data-variant-build]')].find(el => el.getAttribute('data-variant-build') === String(event.pile)) :
      after.game === 'knuckles' ? document.querySelector('[data-variant-main-discard]') :
      [...document.querySelectorAll('[data-variant-discard]')].find(el =>
        el.getAttribute('data-variant-discard') === `${event.player}:${event.pile}`);
    const own = event.player === actor;
    const source = own ? [...document.querySelectorAll('[data-card]')].find(el =>
      el.getAttribute('data-card') === args.card) :
      [...document.querySelectorAll('[data-player-id]')].find(el => el.getAttribute('data-player-id') === event.player);
    const participant = after.players.find(p => p.id === event.player);
    await cardFlight({ source: source || document.querySelector('.variant-players'), target,
      card: event.card, collection: after.game === 'skip-bo' ? 'colors' : 'symbols',
      reveal: !own, label: `${participant?.name || 'Player'} ${event.type === 'play' ? 'builds' : 'discards'} ${event.card}` });
  }
}
async function refreshMatch(viewer = state.viewer) {
  if (state.matchSource === 'remote' && state.remote) {
    state.match = await remoteApi(`/rooms/${state.remote.room}`);
    state.viewer = state.remote.seat;
    return;
  }
  state.match = await api(`/matches/${state.match.id}?viewer=${encodeURIComponent(viewer || '')}`);
  state.viewer = viewer;
}
async function perform(actor, command, args = {}) {
  const match = state.match;
  if (state.matchSource === 'remote' && state.remote) {
    if (actor !== state.remote.seat) throw new Error('You may act only for your own online seat.');
    const reply = await remoteApi(`/rooms/${state.remote.room}/actions`, { method: 'POST',
      body: JSON.stringify({ command, args, revision: match.revision, action_id: crypto.randomUUID() }) });
    state.match = reply.state; state.viewer = state.remote.seat; state.plan = []; state.selected.clear();
    state.lastCard = false; state.ready = true;
    return;
  }
  const result = await api(`/matches/${match.id}/actions`, {
    method: 'POST', body: JSON.stringify({ actor, command, args, revision: match.revision }) });
  const aiPlays = recentAiPlays(match, result);
  if (match.game === 'four-color' && command === 'play') {
    const pile = document.querySelector('[data-pile="discard"] .discard-stack');
    await animatePlayedCard(args.card, pile?.lastElementChild || pile);
    if (pile && result.discard.includes(args.card))
      pile.replaceWith(discardStack([...match.discard, args.card]));
  }
  await animateAiPlays(aiPlays, result.players,
    result.game === 'four-color' ? result.discard.slice(0, result.discard.length - aiPlays.length) : []);
  await animateVariantMoves(match, result, actor, command, args);
  state.selected.clear(); state.lastCard = false; state.ready = false; state.plan = [];
  const solo = soloHumanId(result);
  const nextDecision = result.game === 'fourfold' ? result.players.find(p => p.kind === 'human' && !p.ready)?.id :
    result.outstanding?.find(c => result.players.some(p => p.id === c.player && p.kind === 'human'))?.player ||
    result.players[result.current]?.id;
  if (solo || nextDecision === actor || result.winner || result.phase === 'complete') {
    state.match = result;
    state.viewer = solo || actor;
    state.ready = true;
    state.revealAnimation = motionEnabled() && result.game === 'fourfold' && result.round !== match.round;
  } else {
    await refreshMatch(null);
  }
}
async function playCard(card) {
  const match = state.match, player = match.players[match.current];
  const family = card.slice(0, card.lastIndexOf('-'));
  const neutral = card.endsWith('-neutral');
  const args = { card, last_card: state.lastCard };
  if (neutral) args.color = await choose('Choose the next color', ['blue', 'green', 'red', 'yellow'].map(c => [c, c.toUpperCase()]));
  if (family === 'Wild') args.number = await choose('Declare a number', Array.from({ length: 14 }, (_, i) => [i, String(i)]));
  if (family === 'verdict') args.target = await choose('Select an opponent', match.players.filter(p => p.id !== player.id).map(p => [p.id, p.name]));
  if (family === 'steal') {
    args.steal = await choose('Take an earlier discard', match.stealable.map(c => [c, c]), { cards: true, cancel: true });
    if (args.steal == null) return;
  }
  await perform(player.id, 'play', args);
}
function table() {
  const m = state.match;
  if (!m) return section('No match selected.');
  if (m.game === 'fourfold') return fourfoldTable();
  if (m.game !== 'four-color') return variantTable();
  const pendingId = m.outstanding?.find(x => m.players.find(p => p.id === x.player)?.kind === 'human')?.player;
  const current = m.players[m.current];
  if (state.matchSource === 'remote' && !m.winner && state.remote.seat !== (pendingId || current.id)) {
    return section(title('Waiting for the next turn', 2),
      node('p', {}, `${current.name} is playing. Your hand is private.`),
      button('Check for opponent moves', () => task(() => refreshMatch()), { class: 'primary' }),
      button('Return to online rooms', () => nav('online')));
  }
  const nextId = pendingId || (current.kind === 'human' ? current.id : null);
  const handoff = state.matchSource === 'local' && !m.winner && (!state.ready || state.viewer !== nextId);
  const next = m.players.find(p => p.id === nextId);
  const me = handoff ? null : m.players.find(p => p.id === state.viewer);
  const choice = m.choices?.[0];
  const acting = next || current;
  return node('div', { class: 'game-screen' },
    node('div', { class: 'row split' }, node('div', {}, node('span', { class: 'eyebrow' }, 'FOUR-COLOR'),
      title(m.winner ? `${m.players.find(p => p.id === m.winner)?.name} wins!` : `${current.name}'s turn`, 2)),
      node('div', { class: 'row' }, button('Rules', () => nav('help')), button('Leave table', () => nav('home')))),
    node('div', { class: 'turn-banner', role: 'status', 'aria-live': 'polite' },
      node('div', {}, node('span', { class: 'turn-kicker' }, m.winner ? 'MATCH FINISHED' :
        handoff ? 'NEXT PLAYER' : choice ? 'DECISION REQUIRED' : 'NEXT TO ACT'),
      node('strong', {}, m.winner ? `${m.players.find(p => p.id === m.winner)?.name || 'Player'} won` : acting.name)),
      node('span', { class: 'turn-hint' }, m.winner ? 'Well played!' : handoff ?
        'Reveal your hand to continue' : choice ? 'Choose the required cards' :
        acting.kind === 'ai' ? 'SLAI is deciding' : acting.id === state.viewer ? 'Your move' : 'Waiting for their move')),
    node('div', { class: 'opponents' }, ...m.players.map(p =>
      node('div', { class: `opponent ${p.id === acting.id && !m.winner ? 'current' : ''} ${p.id === state.viewer ? 'self' : ''}`,
        'data-player-id': p.id, ...(p.id === acting.id && !m.winner ? { 'aria-current': 'step' } : {}) },
        node('span', { class: 'avatar mini' }, p.kind === 'ai' ? 'AI' : 'P'), node('b', {}, p.name),
        node('span', { class: 'minor' }, `${p.count} cards${p.verdict ? ` · ${p.verdict} missed` : ''}`),
        p.id === acting.id && !m.winner ? node('span', { class: 'turn-chip' }, 'NEXT') : null))),
    node('div', { class: 'playing-field' }, node('div', { class: 'piles' },
      node('div', { class: 'pile', 'data-pile': 'draw' }, image('cover'), node('span', {}, `Draw · ${m.draw_count}`)),
      node('div', { class: 'pile', 'data-pile': 'discard' }, discardStack(m.discard), node('span', {}, 'Discard'))),
      node('div', { class: 'state-badges' }, node('span', { class: `color-dot ${m.active_color}` }),
        `Active ${m.active_color} · ${m.direction === 1 ? 'Clockwise ↻' : 'Counterclockwise ↺'}`,
        m.wild_rank == null ? '' : ` · Rank ${m.wild_rank}`,
        m.stop_player != null ? ' · STOP active' : '')),
    handoff ? handoffPanel('four-color', next, 'hand') : null,
    m.winner ? section(node('p', {}, 'Game completed. Ready for another round?'),
      node('div', { class: 'row' }, replayButton(), button('Return home', () => nav('home')))) :
    me ? node('div', { class: `hand-area ${state.revealAnimation ? 'reveal-animate' : ''}` }, node('div', { class: 'row split' }, title(`${me.name}'s hand`, 3),
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
      : null,
    node('div', { class: 'events' }, title('Table history', 3),
      ...m.events.slice(-5).reverse().map(e => node('div', { class: 'event' }, e.type.replace('_', ' '),
        e.player ? ` · ${e.player}` : '', e.card ? ` · ${e.card}` : ''))));
}
function variantTable() {
  const m = state.match, completed = m.phase === 'complete';
  const current = m.players[m.current];
  const handoff = state.matchSource === 'local' && !completed && (!state.ready || state.viewer !== current.id);
  const me = handoff ? null : m.players.find(p => p.id === state.viewer);
  const collection = m.game === 'skip-bo' ? 'colors' : 'symbols';
  const art = (token, extra = '') => token ? image(token.split('~')[0], extra, false, collection) :
    node('div', { class: 'variant-empty' }, 'Empty');
  const cardRow = (cards, className = 'variant-hand') => node('div', { class: className }, ...cards.map(c => art(c)));
  const winnerNames = (m.winners || []).map(id => m.players.find(p => p.id === id)?.name || id);
  const status = completed ? (winnerNames.length ? `Winner: ${winnerNames.join(' & ')}` : 'Round ended in a draw') : current.name;
  function actionLabel(action) {
    const a = action.args;
    if (m.game === 'skip-bo') return action.command === 'build' ?
      `Build ${a.pile + 1} from ${a.source}` : action.command === 'discard' ?
        `Discard to pile ${a.pile + 1} · end turn` : 'Pass';
    if (m.game === 'knuckles') return action.command === 'take' ?
      `Take from ${a.source === 'stock' ? 'draw pile' : 'discard pile'}` :
      action.command === 'discard' ? 'Discard this card · end turn' : 'Knock · last round';
    return action.command === 'hit' ? 'Hit · draw one card' : 'Stand · keep this total';
  }
  const actions = (me ? m.legal_actions || [] : []).map(a => {
    const token = a.args.card || (a.command === 'take' && a.args.source === 'discard' ? m.discard.at(-1) : null);
    const tile = button('', () => task(() => perform(me.id, a.command, a.args)), {
      class: 'variant-action', ...(a.args.card ? { 'data-card': a.args.card } : {}) });
    if (token) tile.append(art(token));
    tile.append(node('span', {}, actionLabel(a)));
    return tile;
  });
  const heading = m.game === 'skip-bo' ? 'SKIP-BO' : m.game === 'knuckles' ? 'KNUCKLES' :
    m.game === '21' ? '21 · COMPETITIVE' : 'BLACKJACK';
  const content = [];
  if (m.game === 'skip-bo') {
    content.push(node('p', { class: 'minor' },
      `${m.short_game ? 'Short · 10-card stock' : 'Standard stock'} · ${m.partnership ? 'Partnership teams' : 'Individual play'} · ` +
      `Dealer: ${m.players[m.dealer ?? 0].name} · Draw pile: ${m.draw_count}`));
    content.push(section(title('Shared building piles · 1 → 12', 3), node('div', { class: 'variant-piles' },
      ...m.building.map((pile, i) => node('div', { class: 'variant-pile', 'data-variant-build': String(i) },
        node('span', { class: 'minor' }, `Build ${i + 1} · Next ${pile.length + 1}`),
        art(pile.at(-1)?.card), node('small', {}, pile.length ? `Current: ${pile.at(-1).rank}` : 'Start at 1'))))));
    content.push(section(title('Stock and personal discard piles', 3), node('div', { class: 'variant-players' },
      ...m.players.map(p => node('div', { class: 'variant-player', 'data-player-id': p.id },
        node('b', {}, `${p.name} · Stock ${p.stock_count}${p.team != null ? ` · Team ${p.team + 1}` : ''}`),
        node('div', { class: 'variant-piles' }, node('div', { class: 'variant-pile' },
          node('small', {}, 'Stock top'), art(p.stock_top)),
        ...p.discards.map((token, i) => node('div', { class: 'variant-pile', 'data-variant-discard': `${p.id}:${i}` },
          node('small', {}, `Discard ${i + 1}`), art(token)))))))));
    if (me) content.push(section(title(`${me.name}'s hand`, 3), cardRow(me.hand)));
  } else if (m.game === 'knuckles') {
    content.push(section(title('Draw and discard', 3),
      node('div', { class: 'variant-piles' }, node('div', { class: 'variant-pile' },
        node('small', {}, `Draw · ${m.draw_count}`), art('cover')),
      node('div', { class: 'variant-pile', 'data-variant-main-discard': 'true' }, node('small', {}, 'Discard'), art(m.discard.at(-1))))));
    if (m.knocker) content.push(section(node('b', {}, `${m.players.find(p => p.id === m.knocker)?.name || m.knocker} knocked!`),
      node('p', { class: 'minor' }, `${m.remaining} final player turns remaining.`)));
    if (me) content.push(section(title(`${me.name}'s hand · ${me.total} points (lower is better)`, 3), cardRow(me.hand)));
    if (completed) content.push(section(title('Final scores', 3),
      ...m.players.map(p => node('p', {}, `${p.name}: ${p.total} points`))));
  } else {
    if (m.game === 'blackjack') content.push(section(title('Dealer', 3),
      node('div', { class: 'variant-piles' },
        ...((completed ? m.dealer.hand : [m.dealer.upcard, 'cover']).filter(Boolean).map(token => art(token)))),
      node('p', { class: 'minor' }, completed ? `Dealer total: ${m.dealer.total}` : 'One dealer card stays concealed until settlement')));
    content.push(section(title('Players', 3), node('div', { class: 'variant-players' },
      ...m.players.map(p => node('div', { class: 'variant-player' },
        node('b', {}, `${p.name} · ${p.done ? 'Standing / done' : 'Playing'}`),
        node('p', { class: 'minor' }, p.total == null ? `${p.count} private cards` :
          `${p.total} points${p.total > 21 ? ' · BUST' : ''}`),
        !handoff && (p.id === state.viewer || completed) && p.hand.length ? cardRow(p.hand) : null)))));
  }
  return node('div', { class: 'game-screen variant-screen' },
    node('div', { class: 'row split' }, node('div', {}, node('span', { class: 'eyebrow' }, heading),
      title(completed ? 'Game complete' : `${current.name}'s turn`, 2)),
      node('div', { class: 'row' }, button('Rules', () => nav('help')),
        button('Back to launcher', () => nav('home')))),
    node('div', { class: 'turn-banner', role: 'status', 'aria-live': 'polite' },
      node('div', {}, node('span', { class: 'turn-kicker' }, completed ? 'RESULT' : handoff ? 'NEXT PLAYER' : 'NEXT TO ACT'),
        node('strong', {}, status)),
      node('span', { class: 'turn-hint' }, completed ? 'Match finished' : handoff ?
        'Reveal your cards when ready' : current.id === state.viewer ? 'Your move' : 'Waiting for this player')),
    ...content,
    handoff ? handoffPanel(m.game, current, m.game === 'skip-bo' ? 'hand and stock' : 'hand') : null,
    !handoff && !completed ? section(title('Available moves', 3),
      node('p', { class: 'minor' }, m.game === 'skip-bo' ?
        'Select a legal card and destination below. Playing from your stock clears the pile needed to win.' :
        'Only moves approved by the game rules are shown.'), node('div', { class: 'variant-actions' }, ...actions)) : null,
    completed ? section(title(status, 3),
      m.game === 'skip-bo' ? node('div', { class: 'score-summary' },
        node('p', {}, `Round points: ${m.points_awarded ?? 0}${m.series_complete ? ' · 500-point series complete!' : ''}`),
        ...Object.entries(m.series_scores || {}).map(([participant, points]) =>
          node('span', { class: 'chip' }, `${participant}: ${points} points`))) : null,
      node('div', { class: 'row' }, replayButton(), button('Return to launcher', () => nav('home')))) : null,
    node('div', { class: 'events' }, title('Table history', 3),
      ...m.events.slice(-8).reverse().map(e => node('div', { class: 'event' }, e.type.replaceAll('_', ' '),
        e.player ? ` · ${e.player}` : '', e.card ? ` · ${e.card}` : ''))));
}
function fourfoldTable() {
  const m = state.match;
  const next = state.matchSource === 'remote' ? m.players.find(p => p.id === state.remote.seat && !p.ready) :
    m.players.find(p => p.kind === 'human' && !p.ready);
  if (state.matchSource === 'remote' && m.phase === 'plan' && !next) {
    return section(title(`Round ${m.round}: orders locked`, 2), node('p', {}, 'Waiting for the remaining players to submit their sealed orders.'),
      button('Check for revealed round', () => task(() => refreshMatch()), { class: 'primary' }),
      button('Return to online rooms', () => nav('online')));
  }
  const handoff = state.matchSource === 'local' && m.phase === 'plan' &&
    (!state.ready || state.viewer !== next?.id);
  const me = handoff ? null : m.players.find(p => p.id === state.viewer);
  const cp = state.plan.reduce((total, o) => total + (o.card.startsWith('ace-') ? m.targets[o.card.split('-')[1]] :
    { jack: 4, queen: 5, king: 8 }[o.card.split('-')[0]] || Number(o.card.split('-')[0])), 0);
  const treasury = state.plan.reduce((n, o) => n + o.treasury, 0);
  const estates = ['hearts', 'diamonds', 'clubs', 'spades'];
  const suitIcon = { hearts: '♥', diamonds: '♦', clubs: '♣', spades: '♠' };
  async function addCard(card) {
    const suit = card.split('-')[1];
    const old = state.plan.find(o => o.card === card);
    if (old) { state.plan = state.plan.filter(o => o !== old); state.justSelectedCard = null; render(); return; }
    state.plan = state.plan.filter(o => !o.card.endsWith('-' + suit));
    const order = { card, kind: 'claim', treasury: 0 };
    if (card.startsWith('jack-')) {
      order.target = await choose('Jack: target an opponent', m.players.filter(p => p.id !== me.id).map(p => [p.id, p.name]));
    }
    state.plan.push(order); state.justSelectedCard = card; render();
  }
  return node('div', { class: 'fourfold-screen' },
    node('div', { class: 'row split' }, node('div', {}, node('span', { class: 'eyebrow' }, 'FOURFOLD MANDATE'),
      title(m.phase === 'complete' ? (m.winners.length > 1 ? 'Shared victory' : 'Match complete') : `Round ${m.round} of 12`, 1)),
      button(state.matchSource === 'remote' ? 'Online rooms' : 'Back to launcher', () => nav(state.matchSource === 'remote' ? 'online' : 'home'))),
    m.phase === 'plan' ? node('div', { class: 'turn-banner', role: 'status', 'aria-live': 'polite' },
      node('div', {}, node('span', { class: 'turn-kicker' }, 'AWAITING SEALED ORDERS'),
        node('strong', {}, next ? next.name : 'All orders submitted')),
      node('span', { class: 'turn-hint' }, handoff ? 'Next player: reveal your planning area' :
        next ? `${m.players.filter(p => p.ready).length} of ${m.players.length} players ready` : 'Resolving round')) : null,
    node('div', { class: 'estates' }, ...estates.map(suit => section(
      node('span', { class: `suit-icon suit-${suit}` }, suitIcon[suit]), title(suit.toUpperCase(), 3),
      node('span', { class: 'muted' }, `Target: ${m.targets[suit]}`)))),
    node('div', { class: 'fourfold-score' }, ...m.players.map(p => section(
      node('div', { class: 'row split' }, title(p.name, 3), node('span', { class: 'chip green' }, p.ready ? 'READY' : 'PLANNING')),
      node('p', {}, `${p.mp} MP · ${p.treasury} Treasury`),
      node('p', { class: 'minor' }, estates.map(s => `${suitIcon[s]} ${p.seals[s]}`).join('   ')),
      node('p', { class: 'minor' }, `${p.available_count} cards remaining${p.foundation ? ` · Foundation ${p.foundation.card}` : ''}`)))),
    handoff ? handoffPanel('fourfold', next, 'planning area') : null,
    m.phase === 'complete' ? section(title(`Winners: ${m.players.filter(p => m.winners.includes(p.id)).map(p => p.name).join(' and ')}`, 2),
      node('div', { class: 'row' }, replayButton(), button('Return home', () => nav('home')))) :
      me && !me.ready ? node('div', { class: state.revealAnimation ? 'reveal-animate' : '' }, section(node('div', { class: 'row split' }, title(`${me.name}: secret orders`, 2),
        node('b', {}, `${cp} / 16 CP · ${treasury} / ${me.treasury} Treasury`)),
        node('p', { class: 'muted' }, 'Choose up to three different estates. Click a card to add or remove it. Secret choices lock when submitted.'),
        ...state.plan.map(o => node('div', { class: 'order-row' }, node('b', {}, o.card),
          node('span', { class: 'minor' }, o.kind === 'foundation' ? 'Foundation' : o.target ? `Jack → ${o.target}` : 'Contest'),
          button(`Boost: ${o.treasury}`, () => {
            if (o.kind === 'claim') { o.treasury = (o.treasury + 1) % 3; render(); }
          }, { disabled: o.kind === 'foundation' }),
          button(o.kind === 'foundation' ? 'Use as claim' : 'Build foundation', () => {
            o.kind = o.kind === 'foundation' ? 'claim' : 'foundation'; o.treasury = 0; render();
          }, { disabled: !(Number.parseInt(o.card, 10) >= 1 && Number.parseInt(o.card, 10) <= 10) ||
            (m.round - 1) % 4 > 1 || !!me.foundation }),
          button('Remove', () => { state.plan = state.plan.filter(x => x !== o); render(); }))),
        button('Lock and submit orders', () => task(() => perform(me.id, 'submit', { orders: state.plan })),
          { class: 'primary', disabled: cp > 16 || treasury > me.treasury || state.plan.length > 3 })),
      section(title('Unspent cards', 2), node('div', { class: 'fourfold-hand' }, ...me.available.map(card => {
        const selected = state.plan.some(o => o.card === card);
        const btn = button('', () => task(() => addCard(card)), { class: `fourfold-card ${selected ? 'selected' : ''} ${card === state.justSelectedCard ? 'just-selected' : ''}`,
          'aria-label': `Select ${card}`, 'aria-pressed': String(selected) });
        btn.append(fourfoldArt(card)); return btn;
      })))) : handoff ? null : section(node('p', {}, 'Your orders are locked. Pass the device to the next participant.')),
    node('div', { class: 'events' }, title('Completed rounds', 3),
      ...m.events.filter(e => e.type === 'round_resolved').slice(-4).reverse().map(e => section(
        node('b', {}, `Round ${e.round}`), node('p', { class: 'minor' }, e.awards.map(a =>
          `${a.estate}: ${a.winner || `tie (${a.tie.join(', ')})`}`).join(' · '))))));
}
function settings() {
  const p = state.prefs;
  function selection(name, options, field) {
    return node('label', { class: 'form-field' }, node('span', {}, name), node('select', {
      onChange: event => task(async () => { state.prefs = await api('/settings', { method: 'PUT', body: JSON.stringify({ [field]: event.target.value }) });
        applyAppearance(); }),
    }, ...options.map(opt => node('option', { value: opt, selected: opt === p[field] ? '' : null }, opt))));
  }
  return node('div', { class: 'narrow' }, title('Settings', 1), section(title('Appearance & gameplay', 3),
    selection('Theme', ['dark', 'light', 'contrast'], 'theme'), selection('Default AI difficulty', ['easy', 'medium', 'hard', 'expert'], 'difficulty'),
    node('label', { class: 'row motion-setting' }, node('input', { type: 'checkbox', checked: p.motion !== false,
      onChange: event => task(async () => {
        state.prefs = await api('/settings', { method: 'PUT', body: JSON.stringify({ motion: event.target.checked }) });
        applyAppearance();
      }) }), node('span', {}, 'Animate card flips and transitions')),
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
  const game = state.match?.game || state.setup.game;
  if (game === 'skip-bo') return node('div', { class: 'narrow' }, title('How to play Skip-Bo', 1),
    section(title('Objective', 3), node('p', {}, 'Be first to empty your personal stockpile.'),
      title('Cards', 3), node('p', {}, 'The 162-card deck uses repeated digital instances of the existing colored 1–12 and Wild faces. Card colors have no effect; Wild can represent any required number.'),
      title('Dealer and turns', 3), node('p', {}, 'Highest-number-card draw selects the dealer (Wilds do not count); the player to their left starts. On the next round, the dealer moves one seat left. Draw up to five cards at the beginning of each turn.'),
      title('Your turn', 3), node('p', {}, 'Build up to four common piles in ascending order from 1 through 12, using your hand, the top of your stockpile, or the top of your own four discard piles. Only a 1 or Wild can start a pile. Use as many playable cards as you wish.'),
      title('End turn', 3), node('p', {}, 'Discard one hand card to one of your four personal discard piles. Clearing your hand refills it; completing a pile at 12 makes its cards available for recycling.'),
      title('Scoring and variants', 3), node('p', {}, '2–4 players begin with 30 stock cards each; 5–6 with 20. Optional short games use 10. The winner earns 25 points plus five per card left in opponents’ stocks; the first to 500 wins the series.'),
      node('p', {}, 'In partnership play (four or six players), a player may also build using their teammate’s visible stock top or discard-pile tops. Both partners must empty their stockpiles to win.'),
      node('p', { class: 'minor' }, 'Automatic hand sizes and validated turn order prevent accidental overdraw/out-of-turn mistakes. The artwork is original; Skip-Bo is a Mattel trademark.')),
    button('Back to table', returnFromRules));
  if (game === '21' || game === 'blackjack') return node('div', { class: 'narrow' }, title(`How to play ${game === '21' ? 'Competitive 21' : 'Blackjack'}`, 1),
    section(title('Card values', 3), node('p', {}, 'Aces count as 1 or 11. Number cards count at face value; J, Q and K count as 10. Go over 21 and you bust.'),
      title('Your turn', 3), node('p', {}, 'Choose Hit to draw a card or Stand to keep your total. A 52-card suit deck is used without action cards or wagers.'),
      title('How it differs', 3), node('p', {}, game === '21' ?
        'Competitive 21 is an explicitly defined house variant: players compare totals directly. The highest total at or below 21 wins; ties share the win. There is no dealer.' :
        'In Blackjack, all players compare against a fixed dealer. The dealer hits below 17 and stands on every 17. Two-card natural Blackjack beats an ordinary 21; ties with the dealer are pushes.'),
      node('p', { class: 'minor' }, 'This is one no-wager round; betting, splitting and doubling are not included.')),
    button('Back to table', returnFromRules));
  if (game === 'knuckles') return node('div', { class: 'narrow' }, title('How to play Knuckles', 1),
    section(title('Goal', 3), node('p', {}, 'Have the lowest sum across five cards at the end of the round.'),
      title('Card values', 3), node('p', {}, 'A=1, J=0, Q=10, K=10, and 2–10 at face value.'),
      title('Turns', 3), node('p', {}, 'Take a card from the draw pile or top discard, then choose one card to discard. You always end with five cards.'),
      title('Knock', 3), node('p', {}, 'Instead of drawing, knock to give every other player one final turn. The lowest total wins; tied lows share the win.'),
      node('p', { class: 'minor' }, 'Five-card low-score ruleset; no physical forfeit or punishment mechanics.')),
    button('Back to table', returnFromRules));
  return node('div', { class: 'narrow' }, title('How to play Four-Color', 1),
    section(title('Objective', 3), node('p', {}, 'Be first to discard every card. Everyone starts with seven cards.'),
      title('Match', 3), node('p', {}, 'Play a matching color, rank, letter or action. Neutral cards let you choose the next color.'),
      title('Your turn', 3), node('p', {}, 'Play one legal card or draw one. Only the drawn card can be played immediately.'),
      title('Special actions', 3), node('p', {}, 'Draw penalties, Skip, Reverse, Stop, Verdict, Equality, Swap, Steal, Cycle and Wild follow the prototype rules.'),
      title('Finish', 3), node('p', {}, 'Call LAST CARD when one card remains. Playing your final card wins before its action occurs.'),
      node('p', { class: 'minor' }, 'Prototype v1.0: Cycle and some rule parameters remain provisional.')),
    button('Back to table', returnFromRules));
}
function onlinePage() {
  const serverInput = node('input', { type: 'url', placeholder: 'https://cards.example.com:8775',
    value: state.remote?.server || 'http://127.0.0.1:8775' });
  const roomInput = node('input', { placeholder: 'Room ID', maxlength: 36 });
  const inviteInput = node('input', { placeholder: 'Invitation code' });
  const gameSelect = node('select', {}, ...[['four-color', 'Four-Color'], ['fourfold', 'Fourfold Mandate']].map(([id, name]) =>
    node('option', { value: id }, name)));
  const seatCount = node('select', {}, ...[2, 3, 4, 5, 6, 7, 8].map(n => node('option', { value: n }, String(n))));
  const seat = node('select', {}, ...(state.match?.players || []).filter(p => p.id !== state.remote?.seat).map(p =>
    node('option', { value: p.id }, p.name)));
  function validatedServer() {
    const url = new URL(serverInput.value.trim());
    if (url.username || url.password || url.pathname !== '/' || url.search || url.hash ||
      (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)))) {
      throw new Error('Use a secure HTTPS room service (HTTP is allowed only for localhost testing).');
    }
    return url.origin;
  }
  async function connect(room, token, mySeat) {
    state.remote = { ...state.remote, room, token, seat: mySeat };
    sessionStorage.setItem('cg-remote-room', JSON.stringify(state.remote));
    state.match = await remoteApi(`/rooms/${room}`);
    state.viewer = mySeat; state.ready = true; state.plan = []; state.matchSource = 'remote';
    state.page = 'table';
  }
  return node('div', { class: 'narrow' }, title('Online rooms', 1),
    node('p', { class: 'muted' }, 'Play with friends on a separately hosted Card Games room server. Room seats are protected by private tokens. No cloud account is required.'),
    section(title('Server', 3), node('label', { class: 'form-field' }, node('span', {}, 'Trusted room-service address'), serverInput),
      node('p', { class: 'minor' }, 'The remote service must explicitly allow this launcher origin. For internet access, deploy it behind TLS.')),
    state.remote?.room ? section(title('Current room', 3),
      node('p', {}, `Room ${state.remote.room} · Seat ${state.remote.seat}`),
      button('Open table', () => task(async () => { await refreshMatch(); state.ready = true; state.page = 'table'; }), { class: 'primary' }),
      button('Leave this device', () => { sessionStorage.removeItem('cg-remote-room'); state.remote = null; state.match = null;
        state.matchSource = 'local'; render(); }),
      state.remote?.seat === state.match?.players?.[0]?.id ?
        node('div', {}, node('label', { class: 'form-field' }, node('span', {}, 'Invite a seat'), seat),
          button('Generate one-use invite', () => task(async () => {
            state.invite = await remoteApi(`/rooms/${state.remote.room}/invites`, {
              method: 'POST', body: JSON.stringify({ seat: seat.value }) });
          }), { class: 'primary' }),
          state.invite ? node('p', { class: 'invite-details' }, `Room: ${state.invite.room}\nSeat: ${state.invite.seat}\nInvite: ${state.invite.invite}`) : null) : null) :
      section(title('Create a new room', 3),
        node('label', { class: 'form-field' }, node('span', {}, 'Game'), gameSelect),
        node('label', { class: 'form-field' }, node('span', {}, 'Number of people'), seatCount),
        button('Create online room', () => task(async () => {
          state.remote = { server: validatedServer() };
          const count = Number(seatCount.value);
          if (gameSelect.value === 'fourfold' && count > 6) throw new Error('Fourfold supports at most six players.');
          const participants = Array.from({ length: count }, (_, i) => ({ id: `player${i + 1}`, name: `Player ${i + 1}`, kind: 'human' }));
          const result = await remoteApi('/rooms', { method: 'POST', body: JSON.stringify({ game: gameSelect.value, participants }) });
          await connect(result.room, result.token, result.seat);
        }), { class: 'primary' })),
    section(title('Join with an invitation', 3),
      node('label', { class: 'form-field' }, node('span', {}, 'Room ID'), roomInput),
      node('label', { class: 'form-field' }, node('span', {}, 'Private one-use invitation'), inviteInput),
      button('Join room', () => task(async () => {
        state.remote = { server: validatedServer() };
        const result = await remoteApi(`/rooms/${encodeURIComponent(roomInput.value.trim())}/join`, {
          method: 'POST', body: JSON.stringify({ invite: inviteInput.value.trim() }) });
        await connect(result.room, result.token, result.seat);
      }), { class: 'primary' })));
}
function accountPage() {
  const signed = state.account.status === 'signed-in';
  if (signed) {
    const display = node('input', { type: 'text', maxlength: 40, value: state.profile.display_name });
    const avatar = node('select', {}, ...['initials', 'circle', 'suit'].map(x =>
      node('option', { value: x, selected: x === state.profile.avatar ? '' : null }, x)));
    return node('div', { class: 'narrow' }, title('Your profile', 1),
      section(title(`Welcome, ${state.account.username}`, 3),
        node('p', { class: 'muted' }, 'Your username is fixed; your public display name and avatar style are editable.'),
        node('label', { class: 'form-field' }, node('span', {}, 'Display name'), display),
        node('label', { class: 'form-field' }, node('span', {}, 'Avatar style'), avatar),
        button('Save profile', () => task(async () => {
          state.profile = await api('/profile', { method: 'PUT', body: JSON.stringify({ display_name: display.value, avatar: avatar.value }) });
          toast('Profile saved.');
        }), { class: 'primary' }),
        button('Refresh session', () => task(async () => {
          await api('/account/refresh', { method: 'POST' }); await refreshAccount(); toast('Session renewed.');
        })),
      button('Log out', () => task(async () => {
        await api('/account/logout', { method: 'POST' }); await refreshAccount(); nav('home');
      }), { class: 'warning' })));
  }
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
  state.profile = await api('/profile');
  state.saved = await api('/matches');
  state.stats = await api('/stats');
  state.prefs = await api('/settings');
  state.setup.difficulty = state.prefs.difficulty;
  applyAppearance();
  state.match = null;
}
function render() {
  const content = state.page === 'home' ? home() : state.page === 'games' ? games() :
    state.page === 'setup' ? setup() : state.page === 'table' ? table() : state.page === 'online' ? onlinePage() : state.page === 'settings' ? settings() :
    state.page === 'saved' ? node('div', {}, title('Saved matches', 1), ...state.saved.map(savedTile)) :
    state.page === 'stats' ? stats() : state.page === 'account' ? accountPage() : help();
  clear(root); root.append(shell(content));
  state.revealAnimation = false;
  state.justSelectedCard = null;
}
async function initialize() {
  try {
    try {
      const savedRoom = sessionStorage.getItem('cg-remote-room');
      if (savedRoom) {
        const remote = JSON.parse(savedRoom);
        if (remote.server && remote.room && remote.seat && remote.token) state.remote = remote;
      }
    } catch { sessionStorage.removeItem('cg-remote-room'); }
    state.account = await api('/account');
    if (state.account.status === 'guest' && state.account.available === 'true') {
      try { await api('/account/refresh', { method: 'POST' }); } catch { /* No refresh cookie on guest devices. */ }
      state.account = await api('/account');
    }
    [state.catalog, state.saved, state.prefs, state.stats, state.profile] = await Promise.all([
      api('/catalog'), api('/matches'), api('/settings'), api('/stats'), api('/profile')]);
    applyAppearance();
    state.setup.difficulty = state.prefs.difficulty;
    render();
  } catch (e) { root.replaceChildren(section(title('Unable to start Card Games'), node('p', {}, e.message))); }
}
initialize();
// Online state uses bounded polling; the server remains the sole authority.
let onlinePolling = false;
setInterval(async () => {
  if (state.matchSource !== 'remote' || !state.remote?.room || state.page !== 'table' || onlinePolling) return;
  if (state.match?.game === 'fourfold' && state.match.phase === 'plan' &&
    state.match.players.some(p => p.id === state.remote.seat && !p.ready)) return;
  if (state.match?.game === 'four-color' && !state.match.winner &&
    (state.match.players[state.match.current]?.id === state.remote.seat ||
      state.match.choices?.some(c => c.player === state.remote.seat))) return;
  onlinePolling = true;
  try { await refreshMatch(); render(); } catch { /* Retain the local view for manual reconnect. */ }
  finally { onlinePolling = false; }
}, 3000);

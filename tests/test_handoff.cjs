/* Headless DOM-state regression without requiring Chromium or third-party JS packages. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class FakeNode {
  constructor(tag = '') {
    this.tag = tag; this.children = []; this.attributes = {}; this.handlers = {}; this.className = ''; this.textContent = '';
    this.style = {};
    this.classList = {
      add: cls => { this.className = [...new Set([...this.className.split(' ').filter(Boolean), cls])].join(' '); },
      remove: cls => { this.className = this.className.split(' ').filter(name => name !== cls).join(' '); },
    };
  }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  addEventListener(event, callback) { this.handlers[event] = callback; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  getAttribute(key) { return this.attributes[key]; }
  get lastElementChild() { return [...this.children].reverse().find(child => child instanceof FakeNode) || null; }
  querySelector(selector) { return selector.startsWith('.') ? find(this, selector.slice(1)) : null; }
  replaceWith(element) { this.replacedWith = element; }
  getBoundingClientRect() { return { left: 100, top: 100, width: 120, height: 145 }; }
  animate(keyframes, options) {
    FakeNode.animations = [...(FakeNode.animations || []), { keyframes, options }];
    return { finished: Promise.resolve() };
  }
  remove() {}
}
function flatten(node) {
  return [node.textContent || '', node.className || '', ...Object.values(node.attributes || {}),
    ...(node.children || []).flatMap(item => item instanceof FakeNode ? [flatten(item)] : [String(item)])].join(' ');
}
function find(node, className) {
  if ((node.className || '').split(' ').includes(className)) return node;
  for (const item of node.children || []) {
    if (item instanceof FakeNode) {
      const match = find(item, className);
      if (match) return match;
    }
  }
  return null;
}

const root = new FakeNode('root');
const document = {
  createElement: tag => new FakeNode(tag),
  createTextNode: text => { const n = new FakeNode('#text'); n.textContent = String(text); return n; },
  getElementById: () => root, documentElement: { dataset: {} }, body: new FakeNode('body'),
};
let systemReducedMotion = true;
const context = vm.createContext({ Node: FakeNode, document,
  window: { matchMedia: () => ({ matches: systemReducedMotion }) },
  setTimeout, console, URL, sessionStorage: { getItem: () => null } });
const filename = path.join(__dirname, '..', 'src', 'client', 'app.js');
const app = fs.readFileSync(filename, 'utf8').split('\ninitialize();')[0];
vm.runInContext(`${app}\n globalThis.ui = {state, table, fourfoldTable, render, perform, soloHumanId, cardArtPath, choose, recentAiPlays, animateAiPlays};`, context, { filename });
const { state, table, fourfoldTable, render, perform, soloHumanId, cardArtPath, choose, recentAiPlays, animateAiPlays } = context.ui;

assert.equal(cardArtPath('+5-yellow'), '/api/card-art/plus5-yellow');
assert.equal(cardArtPath('+2-neutral'), '/api/card-art/plus2-neutral');
assert.equal(cardArtPath('08-red'), '/assets/colors/08-red.jpg');
assert.equal(cardArtPath('A-hearts', 'symbols'), '/assets/symbols/A-hearts.jpg');

const score = () => ({ hearts: 0, diamonds: 0, clubs: 0, spades: 0 });
const players = [
  { id: 'h1', name: 'Player 1', kind: 'human', mp: 0, treasury: 2, seals: score(), ready: false,
    spent: [], available_count: 56 },
  { id: 'h2', name: 'Player 2', kind: 'human', mp: 0, treasury: 2, seals: score(), ready: false,
    spent: [], available_count: 56 },
];
const publicFourfold = { id: 'fourfold-test', game: 'fourfold', phase: 'plan', round: 4, revision: 0,
  players, targets: { hearts: 7, diamonds: 9, clubs: 1, spades: 3 }, events: [], winners: [], winner: null };
state.match = publicFourfold;
state.viewer = null;
state.ready = false;
state.page = 'table';
state.matchSource = 'local';
state.prefs = { motion: false, theme: 'dark' };

const handoff = fourfoldTable();
const visible = flatten(handoff);
assert.match(visible, /Target: 7/);
assert.match(visible, /Player 1, you're up/);
assert.match(visible, /PRIVATE HANDOFF/);
assert.ok(find(handoff, 'handoff-card'));
assert.doesNotMatch(visible, /PRIVATE_SECRET_CARD/);

const revealed = { ...publicFourfold, players: [
  { ...players[0], available: ['04-hearts'], orders: null },
  { ...players[1], orders: [{ card: 'PRIVATE_SECRET_CARD' }] },
] };
context.fetch = async () => ({ ok: true, status: 200,
  json: async () => ({ ok: true, data: revealed }) });

(async () => {
  const confirm = find(handoff, 'handoff-confirm');
  assert.ok(confirm, 'Handoff reveal button must be present');
  await confirm.handlers.click();
  assert.equal(state.ready, true);
  assert.equal(state.viewer, 'h1');
  const after = flatten(root);
  assert.match(after, /Select 04-hearts/);
  assert.doesNotMatch(after, /PRIVATE SECRET CARD|PRIVATE_SECRET_CARD/);
  assert.doesNotMatch(after, /PRIVATE HANDOFF/);

  state.match = { id: 'color-test', game: 'four-color', current: 0, direction: 1,
    winner: null, outstanding: [], choices: [], events: [], revision: 0, discard: ['05-blue'],
    active_color: 'blue', draw_count: 104, wild_rank: null, stop_player: null,
    players: [
      { id: 'h1', name: 'Player 1', kind: 'human', hand: ['PRIVATE_SECRET_CARD'], count: 1, verdict: 0 },
      { id: 'h2', name: 'Player 2', kind: 'human', hand: [], count: 7, verdict: 0 },
    ], legal: [] };
  state.ready = false;
  state.viewer = null;
  const colorView = flatten(table());
  assert.match(colorView, /Discard/);
  assert.match(colorView, /Player 1, you're up/);
  assert.match(colorView, /NEXT PLAYER/);
  assert.doesNotMatch(colorView, /PRIVATE_SECRET_CARD/);
  state.match.discard = ['01-blue', '02-green', '03-yellow', '04-red', '05-red'];
  const stack = find(table(), 'discard-stack');
  assert.equal(stack.children.length, 4, 'Keep only the four most recent discards visibly stacked');
  assert.equal(stack.children.at(-1).getAttribute('src'), '/assets/colors/05-red.jpg');

  const selectedCard = choose('Take an earlier discard', [['+5-yellow', '+5-yellow'], ['06-green', '06-green']],
    { cards: true, cancel: true });
  const picker = find(document.body, 'modal-card-choice');
  assert.ok(picker, 'Steal should show a visual card picker');
  const firstCard = find(picker, 'card-choice');
  assert.equal(find(firstCard, 'art-fallback'), null);
  assert.match(flatten(firstCard), /api\/card-art\/plus5-yellow/);
  firstCard.handlers.click();
  assert.equal(await selectedCard, '+5-yellow');

  const solo = { ...publicFourfold, id: 'solo-test', round: 4, players: [
    { ...players[0], available: ['04-hearts'] },
    { ...players[1], id: 'ai', name: 'SLAI', kind: 'ai', ready: true },
  ] };
  assert.equal(soloHumanId(solo), 'h1');
  state.match = { ...solo, round: 3, revision: 0 };
  state.ready = true;
  state.viewer = 'h1';
  context.fetch = async () => ({ ok: true, status: 200, json: async () => ({ ok: true, data: solo }) });
  await perform('h1', 'submit', { orders: [] });
  assert.equal(state.ready, true, 'AI round must resume automatically for the only human');
  assert.equal(state.viewer, 'h1');
  assert.equal(state.match.round, 4);
  assert.equal(find(fourfoldTable(), 'handoff-panel'), null,
    'Solo-human matches should not ask the player to pass the device to themselves');

  // The visual flip must precede the private-hand fetch; reduced motion disables it.
  state.match = publicFourfold;
  state.viewer = null;
  state.ready = false;
  state.prefs.motion = true;
  systemReducedMotion = false;
  let fetchedDuringFlip = false;
  context.fetch = async () => {
    fetchedDuringFlip = true;
    return { ok: true, status: 200, json: async () => ({ ok: true, data: revealed }) };
  };
  const animatedHandoff = fourfoldTable();
  const flippingCard = find(animatedHandoff, 'handoff-card');
  const flipPromise = find(animatedHandoff, 'handoff-confirm').handlers.click();
  assert.match(flippingCard.className, /is-flipping/, 'Reveal should animate a card flip');
  assert.equal(fetchedDuringFlip, false, 'Do not expose the private hand before the flip finishes');
  await flipPromise;
  assert.equal(fetchedDuringFlip, true);
  assert.equal(state.viewer, 'h1');

  // The server is authoritative; replay only new public AI play events.
  const oldTurn = { game: 'four-color', revision: 8, events: [{ type: 'play', player: 'h1', card: '01-blue' }] };
  const nextTurn = { ...oldTurn, revision: 10, events: [
    ...oldTurn.events, { type: 'play', player: 'h1', card: '03-red' },
    { type: 'play', player: 'ai', card: '+5-green' }, { type: 'turn', player: 'h1' },
  ], players: [{ id: 'h1', name: 'Human', kind: 'human' }, { id: 'ai', name: 'SLAI 1', kind: 'ai' }] };
  const aiPlays = recentAiPlays(oldTurn, nextTurn);
  assert.equal(aiPlays.length, 1);
  assert.equal(aiPlays[0].card, '+5-green');
  assert.equal(recentAiPlays(nextTurn, nextTurn).length, 0, 'No duplicate animation on stale revisions');
  const discard = new FakeNode('div');
  discard.append(new FakeNode('img'));
  const field = new FakeNode('div');
  document.querySelector = selector => selector.includes('discard') ? discard : field;
  document.querySelectorAll = () => [];
  await animateAiPlays(aiPlays, nextTurn.players, ['01-blue']);
  assert.equal(discard.replacedWith.children.at(-1).getAttribute('src'), '/api/card-art/plus5-green',
    'An AI play should land face-up on the visible discard stack');
  assert.equal(FakeNode.animations.length, 2, 'Use independent movement and face-reveal animations');
  assert.equal(FakeNode.animations[0].options.duration, 560);
  assert.doesNotMatch(FakeNode.animations[0].keyframes.at(-1).transform, /rotateY/,
    'Movement must not rotate the entire card back to its cover');
  assert.match(FakeNode.animations[1].keyframes.at(-1).transform, /rotateY\(180deg\)/);

  // A new game may reuse an asset family without showing every face or
  // exposing a different participant's private hand during handoff.
  state.prefs.motion = false;
  state.match = { id: 'skip-test', game: 'skip-bo', phase: 'play', current: 0,
    players: [{ id: 'h1', name: 'Human', kind: 'human', stock_count: 30, stock_top: '01-blue~0',
      hand_count: 5, hand: ['PRIVATE_SECRET_CARD'], discards: [null, null, null, null] },
    { id: 'h2', name: 'Other', kind: 'human', stock_count: 30, stock_top: '03-red~0',
      hand_count: 5, hand: [], discards: [null, null, null, null] }],
    building: [[], [], [], []], legal_actions: [{ command: 'build',
      args: { source: 'stock', card: '01-blue~0', pile: 0 } }], events: [], winners: [], winner: null };
  state.viewer = null; state.ready = false;
  const skipHandoff = flatten(table());
  assert.match(skipHandoff, /NEXT PLAYER/);
  assert.doesNotMatch(skipHandoff, /PRIVATE_SECRET_CARD/);
  state.viewer = 'h1'; state.ready = true;
  const skipTable = table();
  assert.match(flatten(skipTable), /01-blue.jpg/);
  assert.ok(find(skipTable, 'variant-action'), 'Skip-Bo should have real legal moves');
  state.match = { ...state.match, game: 'blackjack', current: 0,
    players: [{ id: 'h1', name: 'Human', kind: 'human', count: 2, done: false,
      hand: ['A-hearts', 'K-diamonds'], total: 21 },
    { id: 'h2', name: 'Other', kind: 'human', count: 2, done: false,
      hand: ['PRIVATE_SECRET_CARD'], total: 11 }],
    dealer: { upcard: '06-spades', hand: [], count: 2, total: null },
    legal_actions: [{ command: 'stand', args: {} }] };
  assert.match(flatten(table()), /A-hearts.jpg/);
  assert.doesNotMatch(flatten(table()), /PRIVATE_SECRET_CARD/, 'Opponent hand never renders in ongoing Blackjack');
  console.log('Card Games DOM checks passed: handoffs, card art, Steal picker, next player, and AI plays.');
})().catch(error => { console.error(error); process.exitCode = 1; });

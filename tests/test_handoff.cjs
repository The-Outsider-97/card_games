/* Headless DOM-state regression without requiring Chromium or third-party JS packages. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class FakeNode {
  constructor(tag = '') {
    this.tag = tag; this.children = []; this.attributes = {}; this.handlers = {}; this.className = ''; this.textContent = '';
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
vm.runInContext(`${app}\n globalThis.ui = {state, table, fourfoldTable, render, perform, soloHumanId};`, context, { filename });
const { state, table, fourfoldTable, render, perform, soloHumanId } = context.ui;

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
  assert.doesNotMatch(colorView, /PRIVATE_SECRET_CARD/);

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
  console.log('Handoff DOM checks passed: public board persists and hands stay concealed until reveal.');
})().catch(error => { console.error(error); process.exitCode = 1; });

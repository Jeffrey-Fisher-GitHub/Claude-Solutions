/*
 * PA Turnpike visualizer (p5.js global mode).
 *
 * The Java server owns the simulation. This sketch polls GET /api/state about
 * four times a second, then animates at 60 fps between polls: a traveling
 * car's position is computed from its trip start time and duration, so motion
 * stays smooth no matter how often the poll returns.
 */

const H = 560;              // canvas height
const MARGIN = 70;          // left/right padding for the road
const POLL_MS = 250;
const QUEUE_SHOWN = 9;      // cars drawn per queue before "+n more"

let state = null;           // last JSON snapshot from the server
let clockOffset = 0;        // Date.now() - serverTimeMs
let serverDown = false;
let plazaByName = {};
let hitTargets = [];        // cars under the mouse this frame, for tooltips

// Simplified outline of Pennsylvania in 0..1 coordinates (west to east, north to south).
const PA_OUTLINE = [
  [0.00, 0.14], [0.055, 0.14], [0.11, 0.00], [0.86, 0.00], [0.90, 0.10],
  [0.955, 0.17], [0.935, 0.30], [1.00, 0.43], [0.975, 0.55], [0.925, 0.65],
  [0.955, 0.77], [0.89, 0.90], [0.86, 1.00], [0.00, 1.00]
];

const COLORS = {};

function setup() {
  const holder = document.getElementById('canvas-holder');
  const c = createCanvas(holder.clientWidth || 1200, H);
  c.parent(holder);
  textFont('Helvetica');
  COLORS.land = color(222, 232, 210);
  COLORS.landEdge = color(160, 178, 140);
  COLORS.road = color(70, 76, 82);
  COLORS.roadEdge = color(40, 44, 48);
  COLORS.ez = color(106, 63, 181);
  COLORS.tbp = color(224, 123, 24);
  COLORS.booth = color(242, 194, 48);
  COLORS.ink = color(31, 42, 51);
  COLORS.muted = color(93, 107, 117);

  document.getElementById('run').onclick = () =>
    post('/api/run?cars=' + carCount() + '&rush=' + (document.getElementById('traffic').value === 'rush'));
  document.getElementById('stop').onclick = () => post('/api/stop');
  document.getElementById('reset').onclick = () => post('/api/reset');

  poll();
  setInterval(poll, POLL_MS);
}

function windowResized() {
  const holder = document.getElementById('canvas-holder');
  resizeCanvas(holder.clientWidth || 1200, H);
}

function carCount() {
  const n = parseInt(document.getElementById('cars').value, 10);
  return isNaN(n) ? 100 : n;
}

// ---------------------------------------------------------------- networking

async function poll() {
  try {
    const res = await fetch('/api/state', { cache: 'no-store' });
    accept(await res.json());
  } catch (e) {
    serverDown = true;
  }
}

async function post(url) {
  try {
    const res = await fetch(url, { method: 'POST' });
    accept(await res.json());
  } catch (e) {
    serverDown = true;
  }
}

function accept(s) {
  serverDown = false;
  state = s;
  clockOffset = Date.now() - s.serverTimeMs;
  plazaByName = {};
  for (const p of s.plazas) plazaByName[p.name] = p;
  updatePanels();
}

function serverNow() {
  return Date.now() - clockOffset;
}

// ---------------------------------------------------------------- geometry

function mpToX(mp) {
  return MARGIN + (mp / state.mainlineMiles) * (width - 2 * MARGIN);
}

// The road arcs gently north through the middle of the state, like a highway on a map.
function roadY(mp) {
  return 318 - 46 * Math.sin(Math.PI * mp / state.mainlineMiles);
}

function laneOffset(eastbound) {
  return eastbound ? -8 : 8;
}

// ---------------------------------------------------------------- drawing

function draw() {
  background(244, 241, 234);
  hitTargets = [];
  if (!state) {
    drawMessage(serverDown ? 'Cannot reach the Java server. Run TurnpikeVisualizerServer in Eclipse.' : 'Loading turnpike data...');
    return;
  }
  drawState();
  drawRoad();
  drawSegmentDistances();
  for (const p of state.plazas) drawPlaza(p);
  drawTraveling();
  drawHud();
  drawTooltip();
  if (serverDown) drawMessage('Lost connection to the Java server.');
}

function drawState() {
  const x0 = MARGIN - 40, x1 = width - MARGIN + 40, y0 = 40, y1 = H - 20;
  stroke(COLORS.landEdge);
  strokeWeight(2);
  fill(COLORS.land);
  beginShape();
  for (const [u, v] of PA_OUTLINE) vertex(lerp(x0, x1, u), lerp(y0, y1, v));
  endShape(CLOSE);

  noStroke();
  fill(120, 140, 105);
  textAlign(CENTER, CENTER);
  textSize(13);
  textStyle(BOLD);
  const regions = [['WESTERN PA', 45], ['CENTRAL PA', 200], ['EASTERN PA', 320]];
  for (const [name, mp] of regions) text(name, mpToX(mp), 72);
  textStyle(NORMAL);
}

function drawRoad() {
  const steps = 120;
  noFill();
  // shoulder, asphalt, then lane markings
  for (const [w, c] of [[30, COLORS.roadEdge], [26, COLORS.road]]) {
    stroke(c);
    strokeWeight(w);
    beginShape();
    for (let i = 0; i <= steps; i++) {
      const mp = (i / steps) * state.mainlineMiles;
      vertex(mpToX(mp), roadY(mp));
    }
    endShape();
  }
  stroke(250, 210, 60);
  strokeWeight(1.5);
  drawingContext.setLineDash([8, 8]);
  beginShape();
  for (let i = 0; i <= steps; i++) {
    const mp = (i / steps) * state.mainlineMiles;
    vertex(mpToX(mp), roadY(mp));
  }
  endShape();
  drawingContext.setLineDash([]);

  // Ohio and New Jersey ends
  noStroke();
  fill(COLORS.muted);
  textSize(11);
  textAlign(RIGHT, CENTER);
  text('OHIO', mpToX(0) - 22, roadY(0));
  textAlign(LEFT, CENTER);
  text('NJ', mpToX(state.mainlineMiles) + 22, roadY(state.mainlineMiles));
}

function drawSegmentDistances() {
  const ps = state.plazas;
  textSize(9);
  textAlign(CENTER, CENTER);
  for (let i = 0; i + 1 < ps.length; i++) {
    const mid = (ps[i].milepost + ps[i + 1].milepost) / 2;
    const miles = Math.round(ps[i + 1].milepost - ps[i].milepost);
    const x = mpToX(mid), y = roadY(mid) + 24;
    noStroke();
    fill(255, 255, 255, 220);
    rect(x - 16, y - 7, 32, 14, 7);
    fill(COLORS.muted);
    text(miles + ' mi', x, y);
  }
}

function drawPlaza(p) {
  const x = mpToX(p.milepost), y = roadY(p.milepost);
  const busy = !!p.inBooth;

  // booth canopy across the road
  stroke(COLORS.roadEdge);
  strokeWeight(1);
  fill(busy ? COLORS.booth : color(235, 235, 228));
  rect(x - 7, y - 22, 14, 44, 3);
  fill(COLORS.roadEdge);
  noStroke();
  rect(x - 9, y - 25, 18, 5, 2);

  if (busy) {
    drawCar(x, y, true, p.inBooth.ezpass ? COLORS.ez : COLORS.tbp, 0.8, true);
    addHit(x, y, p.inBooth, 'in booth at ' + p.name);
  }

  // label
  push();
  translate(x + 2, y - 30);
  rotate(-PI / 4);
  noStroke();
  fill(COLORS.ink);
  textAlign(LEFT, BOTTOM);
  textSize(12);
  textStyle(BOLD);
  text(p.name, 0, 0);
  textStyle(NORMAL);
  fill(COLORS.muted);
  textSize(10);
  text('MP ' + p.milepost, 0, 12);
  pop();

  // FIFO queue: front of the line is closest to the booth
  const q = p.queue;
  for (let i = 0; i < Math.min(q.length, QUEUE_SHOWN); i++) {
    const cy = y + 34 + i * 15;
    drawCar(x, cy, true, q[i].ezpass ? COLORS.ez : COLORS.tbp, 0.8, false);
    addHit(x, cy, q[i], 'waiting at ' + p.name + ' (#' + (i + 1) + ' in line)');
  }
  if (q.length > QUEUE_SHOWN) {
    noStroke();
    fill(COLORS.ink);
    textAlign(CENTER, TOP);
    textSize(10);
    text('+' + (q.length - QUEUE_SHOWN) + ' more', x, y + 34 + QUEUE_SHOWN * 15 - 4);
  }

  // counters under the queue column
  const by = y + 34 + QUEUE_SHOWN * 15 + 12;
  noStroke();
  textAlign(CENTER, TOP);
  textSize(10);
  fill(COLORS.muted);
  text('paid ' + p.processed, x, by);
  text('out ' + p.exited, x, by + 12);
}

function drawTraveling() {
  const now = serverNow();
  for (const c of state.traveling) {
    const a = plazaByName[c.entry], b = plazaByName[c.exit];
    if (!a || !b) continue;
    const t = constrain((now - c.tripStartMs) / c.tripDurationMs, 0, 1);
    const mp = lerp(a.milepost, b.milepost, t);
    const east = b.milepost > a.milepost;
    const x = mpToX(mp), y = roadY(mp) + laneOffset(east);
    drawCar(x, y, east, c.ezpass ? COLORS.ez : COLORS.tbp, 1, false);
    addHit(x, y, c, 'driving to ' + c.exit + ' (' + Math.round(t * 100) + '%)');
  }
}

// A small top-down car. `east` decides which end is the front (windshield).
function drawCar(x, y, east, col, s, highlight) {
  push();
  translate(x, y);
  scale(s);
  if (!east) scale(-1, 1);
  rectMode(CENTER);
  stroke(highlight ? color(255) : color(0, 0, 0, 120));
  strokeWeight(highlight ? 2 : 1);
  fill(col);
  rect(0, 0, 22, 11, 4);
  noStroke();
  fill(255, 255, 255, 190);
  rect(5, 0, 5, 8, 1.5);     // windshield
  fill(255, 255, 255, 120);
  rect(-6, 0, 3, 8, 1);      // rear window
  pop();
}

function drawHud() {
  const t = state.totals;
  noStroke();
  fill(255, 255, 255, 225);
  rect(12, 10, 300, 52, 8);
  fill(COLORS.ink);
  textAlign(LEFT, TOP);
  textSize(13);
  textStyle(BOLD);
  const secs = (state.elapsedMs / 1000).toFixed(1);
  text(state.state === 'IDLE' ? 'Static view: ' + state.plazas.length + ' toll plazas' : state.state + ' · ' + secs + ' s' + (state.rushHour ? ' · rush hour' : ''), 22, 18);
  textStyle(NORMAL);
  textSize(11);
  fill(COLORS.muted);
  if (state.state === 'IDLE') {
    text('Press ▶ Run to send cars between the tollbooths.', 22, 38);
  } else {
    text('queued ' + t.queued + ' · driving ' + t.traveling + ' · exited ' + t.exited + ' / ' + state.carsRequested, 22, 38);
  }
}

function addHit(x, y, car, where) {
  if (abs(mouseX - x) < 13 && abs(mouseY - y) < 8) hitTargets.push({ car, where });
}

function drawTooltip() {
  if (!hitTargets.length) return;
  const { car, where } = hitTargets[hitTargets.length - 1];
  const lines = [
    car.plate + (car.ezpass ? '  (E-ZPass)' : '  (Toll-by-Plate)'),
    car.entry + ' → ' + car.exit,
    where,
    car.toll > 0 ? 'Toll paid: $' + car.toll.toFixed(2) : 'Toll not paid yet'
  ];
  textSize(12);
  const w = Math.max(...lines.map(l => textWidth(l))) + 20;
  const h = lines.length * 16 + 12;
  let x = mouseX + 14, y = mouseY + 14;
  if (x + w > width) x = mouseX - w - 14;
  if (y + h > height) y = mouseY - h - 14;
  noStroke();
  fill(18, 50, 79, 240);
  rect(x, y, w, h, 6);
  fill(255);
  textAlign(LEFT, TOP);
  lines.forEach((l, i) => text(l, x + 10, y + 7 + i * 16));
}

function drawMessage(msg) {
  noStroke();
  fill(178, 59, 59);
  rect(width / 2 - 260, 12, 520, 30, 6);
  fill(255);
  textAlign(CENTER, CENTER);
  textSize(13);
  text(msg, width / 2, 27);
}

// ---------------------------------------------------------------- HTML panels

function updatePanels() {
  const s = state;
  const st = document.getElementById('state');
  st.textContent = s.state;
  st.className = 'pill ' + s.state;
  const active = s.state === 'RUNNING' || s.state === 'DRAINING';
  document.getElementById('run').disabled = active;
  document.getElementById('stop').disabled = !active;
  document.getElementById('cars').disabled = active;
  document.getElementById('traffic').disabled = active;

  const t = s.totals;
  const cards = [
    ['Toll plazas', s.plazas.length],
    ['Mainline miles', s.mainlineMiles],
    ['Waiting in queues', t.queued],
    ['Paid at booth', t.processed],
    ['On the road', t.traveling],
    ['Exited', t.exited],
    ['Toll revenue', '$' + t.revenue.toFixed(2)],
    ['Stack size', t.stackSize]
  ];
  document.getElementById('cards').innerHTML = cards
    .map(([l, v]) => `<div class="card"><div class="label">${l}</div><div class="value">${v}</div></div>`)
    .join('');

  document.getElementById('plaza-rows').innerHTML = s.plazas
    .map(p => `<tr><td>${esc(p.name)}</td><td>${p.milepost}</td><td>${p.queueSize}</td>` +
              `<td>${p.processed}</td><td>${p.exited}</td><td>$${p.tolls.toFixed(2)}</td></tr>`)
    .join('');

  const stack = document.getElementById('stack');
  stack.innerHTML = s.history.length
    ? s.history.map(r => `<li>${esc(r)}</li>`).join('')
    : '<li class="empty">Empty: no transactions yet. Press Run.</li>';
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

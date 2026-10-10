// LinkedIn mode in the side panel: the list, grouping, the same-tab open with the note copied,
// marking sent with your edit, skip, approving a person, and the search over names.
//   node test/linkedin.test.js
'use strict';
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const extDir = path.join(__dirname, '..');
let passed = 0, failed = 0;
function assert(cond, msg) {
  if (cond) { passed++; console.log('  PASS  ' + msg); } else { failed++; console.log('  FAIL  ' + msg); }
}

const job = (id, company, title) => ({ id, company, title, url: 'https://www.linkedin.com/jobs/view/1/' });
function note(id, name, slug, j, draft) {
  return { id, channel: 'linkedin', status: 'review', draft, job: j,
    person: { name, title: 'Head of Talent', linkedin_url: 'https://www.linkedin.com/in/' + slug } };
}
const basis = job('j-basis', 'Northbridge Logistics', 'Operations Analyst');
const second = job('j-second', 'Pied Piper Labs', 'Product Builder');
let queue = {
  people: [{ id: 'p-1', name: 'Pat Proposed', title: 'Director', linkedin_url: 'https://www.linkedin.com/in/pat', job: basis, why: 'Runs the team.' }],
  linkedin: [note('m-1', 'Riley P.', 'riley-p-example', basis, 'Hi Riley, I applied to the Operations Analyst role.'),
             note('m-2', 'Morgan Ellis', 'morgan-ellis-example', basis, 'Hi Morgan, I applied too.'),
             note('m-3', 'Jordan Lee', 'jordan-lee', second, 'Hi Jordan, I applied to the builder role.')]
};
const posted = [], opened = [], copied = [];

const dom = new JSDOM(fs.readFileSync(path.join(extDir, 'sidepanel.html'), 'utf8'),
  { url: 'http://localhost/sidepanel.html', runScripts: 'outside-only' });
const w = dom.window;
w.fetch = function (url, opts) {
  const u = String(url);
  if (opts && opts.method === 'POST') {
    posted.push({ url: u, body: JSON.parse(opts.body || '{}') });
    const m = /\/api\/messages\/([^/]+)\/(linkedin_sent|skip)$/.exec(u);
    if (m) queue = Object.assign({}, queue, { linkedin: queue.linkedin.filter(x => x.id !== decodeURIComponent(m[1])) });
    if (/\/decide$/.test(u)) queue = Object.assign({}, queue, { people: [] });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  }
  const body = /\/api\/queue$/.test(u) ? queue : /\/notifications$/.test(u) ? { total: 4, linkedin: 3, people: 1 } :
    /\/api\/profile\/status$/.test(u) ? { onboarded: true, features: { sponsorship: false, outreach: true, email: true, alerts: false } } :
    /\/jobs$/.test(u) ? [] : /\/settings$/.test(u) ? { auto: false, threshold: 70 } : { ok: true };
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
};
w.navigator.clipboard = { writeText: t => { copied.push(t); return Promise.resolve(); } };
let activeUrl = 'https://www.linkedin.com/in/morgan-ellis-example/';
w.chrome = {
  tabs: {
    query: (q, cb) => cb([{ id: 7, url: activeUrl, active: true }]),
    update: (id, o) => { opened.push({ id, url: o.url }); },
    create: o => opened.push({ id: null, url: o.url }),
    onActivated: { addListener() {} }, onUpdated: { addListener() {} }
  },
  storage: { session: { get: () => Promise.resolve({}), set: () => Promise.resolve() } },
  runtime: { sendMessage: () => Promise.resolve(), onMessage: { addListener() {} } }
};
w.eval(fs.readFileSync(path.join(extDir, 'sidepanel.js'), 'utf8'));
const doc = w.document;
const tick = () => new Promise(r => setTimeout(r, 0));
const flush = async () => { for (let i = 0; i < 6; i++) await tick(); };

(async function () {
  await flush();
  assert(!doc.getElementById('li-btn').hidden, 'the LinkedIn button shows when the server reports outreach on');
  doc.getElementById('li-btn').click();
  await w.loadLinkedin(); await flush();
  const view = doc.getElementById('li-view');
  assert(!view.hidden && doc.getElementById('jobs-list').hidden, 'the LinkedIn button swaps the job list for the LinkedIn view');
  assert(doc.getElementById('li-btn').getAttribute('aria-pressed') === 'true', 'the button shows it is on');
  const heads = Array.from(view.querySelectorAll('.group-head')).map(e => e.textContent);
  assert(/On this profile/.test(heads[0]) && /People to approve/.test(heads[1]) && /Northbridge Logistics, Operations Analyst1/.test(heads[2]) && /Pied Piper Labs/.test(heads[3]),
    'the open profile first, then people to approve, then notes grouped by job: ' + heads.join(' | '));
  assert(view.querySelector('.li-row').getAttribute('data-mid') === 'm-2', 'the open profile\'s note is the first row');
  assert(view.querySelectorAll('.li-row').length === 4, 'one row per person and per note');
  const here = view.querySelector('.li-row.here');
  assert(here && here.getAttribute('data-mid') === 'm-2' && /Open in this tab/.test(here.textContent),
    'the profile open in the tab is marked on its row');

  view.querySelector('.li-name[data-mid="m-1"]').click(); await flush();
  assert(copied[copied.length - 1] === 'Hi Riley, I applied to the Operations Analyst role.', 'clicking a name copies that note');
  assert(opened.length === 1 && opened[0].id === 7 && opened[0].url === 'https://www.linkedin.com/in/riley-p-example',
    'and opens the profile in the same tab: ' + JSON.stringify(opened));
  assert(/Copied/.test(view.querySelector('.li-row[data-mid="m-1"] .li-copy').textContent), 'the row says the note is copied');

  const area = view.querySelector('.li-row[data-mid="m-1"] textarea');
  area.focus(); area.value = 'Hi Riley, edited by me.'; area.dispatchEvent(new w.Event('input'));
  assert(/23 characters/.test(view.querySelector('.li-row[data-mid="m-1"] .li-chars').textContent), 'the character count follows your edit');
  await w.loadLinkedin(); await flush();
  assert(doc.activeElement === area, 'a poll does not redraw over a note you are typing');
  view.querySelector('.li-row[data-mid="m-1"] .li-copy').click(); await flush();
  assert(copied[copied.length - 1] === 'Hi Riley, edited by me.', 'Copy uses your edited note');
  view.querySelector('.li-row[data-mid="m-1"] .li-sent').click(); await flush(); await flush();
  const sent = posted.find(p => /m-1\/linkedin_sent$/.test(p.url));
  assert(sent && sent.body.text === 'Hi Riley, edited by me.', 'Sent records the note you actually sent');
  assert(!view.querySelector('.li-row[data-mid="m-1"]'), 'a sent note leaves the list');
  assert(doc.activeElement && doc.activeElement.getAttribute('data-mid') === 'm-3', 'focus moves to the next name below (the open profile is pinned above), got ' + (doc.activeElement && doc.activeElement.outerHTML.slice(0, 80)));

  view.querySelector('.li-row[data-mid="m-3"] .li-skip').click(); await flush(); await flush();
  assert(posted.some(p => /m-3\/skip$/.test(p.url)) && !view.querySelector('.li-row[data-mid="m-3"]'), 'Skip removes a note');

  view.querySelector('.li-row.person button.primary').click(); await flush(); await flush();
  const dec = posted.find(p => /people\/p-1\/decide$/.test(p.url));
  assert(dec && dec.body.decision === 'approve' && !view.querySelector('.li-row.person'), 'a person can be approved from here');

  const s = doc.getElementById('search-input');
  s.value = 'zzz'; s.dispatchEvent(new w.Event('input'));
  assert(/No one matches/.test(view.textContent), 'search filters names in this mode');
  s.value = ''; s.dispatchEvent(new w.Event('input'));
  doc.getElementById('li-btn').click();
  assert(view.hidden && !doc.getElementById('jobs-list').hidden, 'pressing it again returns to the jobs');

  // Outreach off (or a server with no status route): the LinkedIn button stays hidden.
  const off = new JSDOM(fs.readFileSync(path.join(extDir, 'sidepanel.html'), 'utf8'), { url: 'http://localhost/sidepanel.html', runScripts: 'outside-only' }).window;
  off.fetch = u => /\/api\/profile\/status$/.test(String(u)) ? Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) })
    : Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(/\/jobs$/.test(String(u)) ? [] : {}) });
  off.chrome = w.chrome;
  off.eval(fs.readFileSync(path.join(extDir, 'sidepanel.js'), 'utf8'));
  await flush();
  assert(off.document.getElementById('li-btn').hidden, 'the LinkedIn button is hidden when outreach is off or the status route is missing');

  console.log('\n' + passed + ' passed, ' + failed + ' failed');
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });

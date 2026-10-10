// The careers page an Apply click on LinkedIn opens is recorded against the job, never a LinkedIn
// address, and a link seen before the job was captured is handed over at capture.
//   node test/careers.test.js
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

let passed = 0, failed = 0;
function assert(c, m) { if (c) { passed++; console.log('  PASS  ' + m); } else { failed++; console.log('  FAIL  ' + m); } }

function ev() { const fns = []; return { addListener: f => fns.push(f), fire: (...a) => fns.forEach(f => f(...a)) }; }
function store() { let s = {}; return { get: k => Promise.resolve({ [k]: s[k] }), set: o => { Object.assign(s, o); return Promise.resolve(); }, _s: () => s }; }
const tabs = { 1: { id: 1, url: 'https://www.linkedin.com/jobs/search-results/?currentJobId=1000000001&eBP=x', status: 'complete' } };
const posted = [];
const chrome = {
  runtime: { onInstalled: ev(), onStartup: ev(), onMessage: ev(), sendMessage: () => Promise.resolve(), lastError: null },
  contextMenus: { create() {}, onClicked: ev() }, sidePanel: { setPanelBehavior: () => Promise.resolve(), open: () => Promise.resolve() },
  action: { setBadgeText() {}, setBadgeBackgroundColor() {} }, alarms: { create() {}, onAlarm: ev() },
  commands: { onCommand: ev() }, scripting: { executeScript: () => Promise.resolve([]) },
  storage: { session: store(), local: store(), onChanged: ev() },
  tabs: { onCreated: ev(), onUpdated: ev(), onRemoved: ev(), query: (q, cb) => cb && cb([]),
          get: id => Promise.resolve(tabs[id]), create() {}, remove() {}, sendMessage() {} }
};
const ctx = { chrome, console, setTimeout, clearTimeout, Promise, JSON,
  fetch: (url, opts) => { posted.push({ url, body: opts && opts.body ? JSON.parse(opts.body) : null });
    return Promise.resolve({ ok: !/linkedin:999/.test(opts && opts.body || ''), json: () => Promise.resolve({}) }); } };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'background.js'), 'utf8'), ctx);
const flush = async () => { for (let i = 0; i < 12; i++) await new Promise(r => setImmediate(r)); };

(async function () {
  // Apply click: a new tab from the LinkedIn job tab, through LinkedIn's redirect, to the careers site.
  tabs[2] = { id: 2, openerTabId: 1, url: '', status: 'loading' };
  chrome.tabs.onCreated.fire(tabs[2]); await flush();
  tabs[2].url = 'https://www.linkedin.com/jobs/view/externalApply/1000000001?url=x';
  chrome.tabs.onUpdated.fire(2, { status: 'complete' }, tabs[2]); await flush();
  assert(!posted.some(p => /careers_url/.test(p.url)), 'nothing is recorded while the tab is still on LinkedIn');
  tabs[2].url = 'https://careers.example.com/jobs/AI-Enablement-Lead/12345';
  chrome.tabs.onUpdated.fire(2, { status: 'complete' }, tabs[2]); await flush();
  const sent = posted.filter(p => /\/api\/careers_url$/.test(p.url));
  assert(sent.length === 1 && sent[0].body.job_key === 'linkedin:1000000001'
    && sent[0].body.url === tabs[2].url, 'the careers page is sent for the job the opener showed: ' + JSON.stringify(sent));
  assert(chrome.storage.local._s().careers['1000000001'] === tabs[2].url, 'and kept locally');
  chrome.tabs.onUpdated.fire(2, { status: 'complete' }, Object.assign({}, tabs[2], { url: 'https://careers.example.com/apply/step2' })); await flush();
  assert(posted.filter(p => /\/api\/careers_url$/.test(p.url)).length === 1, 'later pages in that tab are not recorded again');

  // A tab opened from somewhere other than a LinkedIn job records nothing.
  tabs[3] = { id: 3, openerTabId: 9, url: 'https://example.com', status: 'complete' }; tabs[9] = { id: 9, url: 'https://news.ycombinator.com' };
  chrome.tabs.onCreated.fire(tabs[3]); await flush();
  chrome.tabs.onUpdated.fire(3, { status: 'complete' }, tabs[3]); await flush();
  assert(posted.filter(p => /\/api\/careers_url$/.test(p.url)).length === 1, 'tabs not opened from a LinkedIn job are ignored');

  // The job is captured after the Apply click: the stored link is handed over.
  chrome.storage.local.set({ careers: { '1000000001': 'https://careers.example.com/x', '5551': 'https://careers.example.com/jobs/1' } });
  ctx.onJobCreated({ id: 'j', job_key: 'linkedin:5551', careers_url: null }, 1); await flush();
  const last = posted[posted.length - 1];
  assert(/\/api\/careers_url$/.test(last.url) && last.body.job_key === 'linkedin:5551' && last.body.url === 'https://careers.example.com/jobs/1',
    'a capture after the Apply click sends the stored careers link');
  const n = posted.length;
  ctx.onJobCreated({ id: 'k', job_key: 'linkedin:5551', careers_url: 'https://careers.example.com/jobs/1' }, 1); await flush();
  assert(posted.length === n, 'a job that already has its careers link is left alone');

  assert(ctx.careersPageUrl('https://www.linkedin.com/jobs/view/1/') === '' && ctx.careersPageUrl('https://jobs.lever.co/example/1') !== '',
    'a LinkedIn address is never a careers page');
  // The server address: the default, then a saved override picked up by the worker.
  posted.length = 0;
  chrome.storage.local.set({ serverUrl: 'http://127.0.0.1:9911' }); await flush();
  ctx.onJobCreated({ id: 'm', job_key: 'linkedin:6001', careers_url: null }, 1);
  assert(ctx.DEFAULT_SERVER === 'http://127.0.0.1:8790', 'the default server address is the one default');
  assert(ctx.normalizeServer('http://127.0.0.1:9911/') === 'http://127.0.0.1:9911' && ctx.normalizeServer('not a url') === '',
    'a server address is trimmed of a trailing slash, and nonsense is rejected');
  await ctx.loadServer();
  assert(ctx.SERVER === 'http://127.0.0.1:9911', 'the worker uses the address saved in storage.local');
  chrome.storage.local.set({ serverUrl: '' }); await ctx.loadServer();
  assert(ctx.SERVER === 'http://127.0.0.1:8790', 'an empty or invalid saved address falls back to the default');

  console.log('\n' + passed + ' passed, ' + failed + ' failed');
  process.exit(failed ? 1 : 0);
})();

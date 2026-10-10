// JD Intake side panel logic.
// One default server address. A different one is typed into the Settings sheet and kept in
// chrome.storage.local (key serverUrl). A custom host or port also needs manifest.json
// host_permissions edited to match, or Chrome blocks the calls.
var DEFAULT_SERVER = 'http://127.0.0.1:8790';
var SERVER = DEFAULT_SERVER;

// Optional features the server reports on /api/profile/status. Until it answers, or when it
// has no such route, everything optional is off. onboarded stays null until the server says.
var features = { sponsorship: false, outreach: false, email: false, alerts: false };
var onboarded = null;

var jobs = [];
var settings = { auto: false, threshold: 70, auto_apply: false };
var expandedId = null;         // accordion: exactly one card expanded at a time
var currentFilter = 'active';  // 'active' (needs you or running) | 'applied' | 'skipped' | 'all'
var inFlight = {};    // jobId -> { action: true }
var actionError = {}; // jobId -> message
var jobsTimer = null;
var lastJobsJson = '';
// jobId -> { ask: '', note: '', questions: { qid: { choice, text, remember } } }
var drafts = {};

var jobsListEl = document.getElementById('jobs-list');
var healthDot = document.getElementById('health-dot');
var healthText = document.getElementById('health-text');
var warningLine = document.getElementById('warning-line');
var bannerEl = document.getElementById('banner');
var autoToggle = document.getElementById('auto-toggle');
var thresholdInput = document.getElementById('threshold-input');
var captureBtn = document.getElementById('capture-btn');
var filterButtons = Array.prototype.slice.call(document.querySelectorAll('#filter-row .filter-btn'));
var filterRow = document.getElementById('filter-row');
var settingsRow = document.getElementById('settings-row');
var settingsBtn = document.getElementById('settings-btn');
var autoBadge = document.getElementById('auto-badge');

// Filters only earn their space once there are enough jobs to lose one.
var FILTER_MIN_JOBS = 7;

// ---------- Search ----------
// Typing narrows the list at once on what the panel already holds (title, company, location,
// the first 300 characters). A quarter-second later the server searches the full JD.md of
// every job and the list settles on that answer, so a keyword deep in an old description finds
// the job. If the server call fails the local match stands.
var searchInput = document.getElementById('search-input');
var searchQuery = '';
var searchIds = null;        // null: no server answer yet; otherwise the ids the server matched
var searchTimer = null;
var searchSeq = 0;
function localMatch(job, q) {
  var hay = [job.title, job.company, job.location, job.text_head].join(' ').toLowerCase();
  return hay.indexOf(q) !== -1;
}
function searchMatches(job) {
  if (!searchQuery) return true;
  if (searchIds) return searchIds.indexOf(job.id) !== -1;
  return localMatch(job, searchQuery);
}
function runServerSearch() {
  var q = searchQuery;
  var seq = ++searchSeq;
  if (!q) { searchIds = null; return; }
  apiGet('/search?q=' + encodeURIComponent(q)).then(function (res) {
    if (seq !== searchSeq || searchQuery !== q) return;   // a newer query is in flight
    searchIds = res.ids || [];
    render();
  }).catch(function () {});
}
searchInput.addEventListener('input', function () {
  searchQuery = searchInput.value.trim().toLowerCase();
  searchIds = null;
  clearTimeout(searchTimer);
  if (liMode) { renderLinkedin(true); return; }     // LinkedIn mode filters its own names
  if (searchQuery) searchTimer = setTimeout(runServerSearch, 250);
  render();
});
searchInput.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') { searchInput.value = ''; searchInput.dispatchEvent(new Event('input')); }
});

settingsBtn.addEventListener('click', function () {
  var open = settingsRow.hidden;
  settingsRow.hidden = !open;
  settingsBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
});

// ---------- Bell: outreach waiting on you ----------
// Counts from /notifications on the same cycle as the health dot; a click opens the dashboard,
// on the Outreach tab when something is waiting.
var bellBtn = document.getElementById('bell-btn');
var bellCount = document.getElementById('bell-count');
function openDashboard(tab) {
  try { chrome.tabs.create({ url: SERVER + '/#' + (tab || 'jobs') }); } catch (e) { /* no tabs API in tests */ }
}
function pollBell() {
  if (!bellBtn) return;
  apiGet('/notifications').then(function (n) {
    var t = n.total || 0, parts = [];
    if (n.people) parts.push(n.people + (n.people === 1 ? ' person' : ' people') + ' to approve');
    if (n.approve) parts.push(n.approve + (n.approve === 1 ? ' email' : ' emails') + ' to approve');
    if (n.linkedin) parts.push(n.linkedin + ' LinkedIn ' + (n.linkedin === 1 ? 'note' : 'notes') + ' to send');
    if (n.failed) parts.push(n.failed + ' failed ' + (n.failed === 1 ? 'send' : 'sends'));
    if (n.inbox) parts.push(n.inbox + (n.inbox === 1 ? ' email' : ' emails') + ' to confirm');
    bellCount.hidden = !t;
    bellCount.textContent = t > 99 ? '99+' : String(t);
    bellBtn.classList.toggle('has-count', !!t);
    bellBtn.title = parts.length ? parts.join(', ') : 'Open the dashboard';
    bellBtn.setAttribute('aria-label', (parts.length ? parts.join(', ') + '. ' : '') + 'Open the dashboard');
    // Outreach work first; when only mail waits, the bell opens the Inbox tab.
    var outreachWork = (n.people || 0) + (n.approve || 0) + (n.linkedin || 0) + (n.failed || 0);
    bellBtn.setAttribute('data-tab', outreachWork ? 'outreach' : n.inbox ? 'inbox' : 'jobs');
    if (liCount) {
      var li = (n.linkedin || 0) + (n.people || 0);
      liCount.hidden = !li;
      liCount.textContent = li > 99 ? '99+' : String(li);
      liBtn.classList.toggle('has-count', !!li);
    }
  }).catch(function () {});
}
if (bellBtn) bellBtn.addEventListener('click', function () { openDashboard(bellBtn.getAttribute('data-tab')); });

// Auto changes what happens without being asked, so its state stays visible even when the
// settings sheet is shut. Everything else in there is set once and forgotten.
function renderAutoBadge() {
  var on = !!(settings && settings.auto);
  autoBadge.hidden = false;
  autoBadge.classList.toggle('on', on);
  autoBadge.setAttribute('aria-pressed', on ? 'true' : 'false');
  autoBadge.title = on
    ? 'Auto active: every clean capture is evaluated at once; a job scoring ' + (settings.threshold || 70) + '+ asks its questions if it has any, otherwise builds. Click to turn off.'
    : 'Auto off: capture, evaluate and build each wait for a click. Click to turn on.';
  autoBadge.setAttribute('aria-label', on ? 'Auto active' : 'Auto off');
  autoBadge.innerHTML = '';
  autoBadge.appendChild(icon('bolt'));
}
autoBadge.addEventListener('click', function () {
  var next = !(settings && settings.auto);
  settings = settings || {};
  settings.auto = next;
  autoToggle.checked = next;           // keep the settings sheet in step
  renderAutoBadge();
  apiPost('/settings', { auto: next }).then(function (st) { settings = st; renderAutoBadge(); }).catch(function () {});
});

function h(tag, attrs, children) {
  var e = document.createElement(tag);
  attrs = attrs || {};
  for (var k in attrs) {
    if (k === 'class') e.className = attrs[k];
    else if (k === 'text') e.textContent = attrs[k];
    else if (k.indexOf('on') === 0 && typeof attrs[k] === 'function') e.addEventListener(k.slice(2), attrs[k]);
    else if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]);
  }
  (children || []).forEach(function (c) {
    if (c !== null && c !== undefined) e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  });
  return e;
}

// ---------- Icons (inline SVG, 16px, stroke 1.75, currentColor) ----------
var ICONS = {
  bolt: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>',
  play: '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round"><polygon points="7 4 20 12 7 20 7 4"></polygon></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 12 9 17 20 6"></polyline></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.75" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="6" x2="18" y2="18"></line><line x1="18" y1="6" x2="6" y2="18"></line></svg>',
  send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11 L20 4 L13 21 L11 13 Z"></path></svg>',
  folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6z"></path></svg>',
  copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="1"></rect><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"></path></svg>',
  person: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="3.75"></circle><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"></path></svg>',
  eye: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"></path><circle cx="12" cy="12" r="3"></circle></svg>',
  link: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6"></path><path d="M20 4 10 14"></path><path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6"></path></svg>',
  // Claude's spark: eight rays from the centre, round-capped, the way the Claude mark reads at 16 px.
  claude: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="12" y1="3" x2="12" y2="21"></line><line x1="3" y1="12" x2="21" y2="12"></line><line x1="5.6" y1="5.6" x2="18.4" y2="18.4"></line><line x1="18.4" y1="5.6" x2="5.6" y2="18.4"></line></svg>',
  skip: '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 4 15 12 5 20 5 4"></polygon><line x1="19" y1="5" x2="19" y2="19"></line></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>',
  question: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.2 9a3 3 0 1 1 4 2.8c-.8.3-1.2 1-1.2 1.8v.9"></path><line x1="12" y1="17.5" x2="12" y2="17.6"></line></svg>',
  upload: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4"></path><path d="M7.5 8.5 12 4l4.5 4.5"></path><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"></path></svg>',
  clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"></circle><path d="M12 7.5V12l3 1.8"></path></svg>',
  alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4.5 21 19.5H3z"></path><line x1="12" y1="10" x2="12" y2="14"></line><line x1="12" y1="17" x2="12" y2="17.1"></line></svg>',
  bookmark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M6 4h12a1 1 0 0 1 1 1v15l-7-4.5L5 20V5a1 1 0 0 1 1-1z"></path></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"></path><path d="M9.5 7V4.5h5V7"></path><path d="M6.5 7l.8 12.5a1 1 0 0 0 1 .9h7.4a1 1 0 0 0 1-.9L17.5 7"></path><line x1="10.2" y1="11" x2="10.4" y2="17"></line><line x1="13.8" y1="11" x2="13.6" y2="17"></line></svg>',
  pen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20l1-4.5L16.5 4a1.6 1.6 0 0 1 2.3 0l1.2 1.2a1.6 1.6 0 0 1 0 2.3L8.5 19 4 20z"></path><line x1="14" y1="6.5" x2="17.5" y2="10"></line></svg>',
  at: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3.5"></circle><path d="M15.5 12v1.5a2.5 2.5 0 0 0 5 0V12a8.5 8.5 0 1 0-3.4 6.8"></path></svg>',
  chevron: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>',
  'chevron-up': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 15 12 9 18 15"></polyline></svg>',
  refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 0 0-14.5-4.5L4 8"></path><path d="M4 3v5h5"></path><path d="M4 13a8 8 0 0 0 14.5 4.5L20 16"></path><path d="M20 21v-5h-5"></path></svg>'
};
function icon(name, extraClass) {
  var span = document.createElement('span');
  span.className = 'icon' + (extraClass ? ' ' + extraClass : '');
  span.setAttribute('aria-hidden', 'true');
  span.innerHTML = ICONS[name] || '';
  return span;
}

// A button that disables itself while `action` is in flight for `job.id` and posts on click.
function actionButton(iconName, label, cls, job, action, path, bodyFn) {
  var btn = h('button', { type: 'button', class: cls || '', 'aria-label': label }, [icon(iconName), h('span', {}, [label])]);
  btn.disabled = isInFlight(job.id, action);
  btn.addEventListener('click', function () { runAction(job, action, path, bodyFn ? bodyFn() : {}); });
  return btn;
}

function copyButton(getText) {
  var label = h('span', {}, ['Copy']);
  var btn = h('button', { type: 'button', class: 'copy-btn', 'aria-label': 'Copy' }, [icon('copy'), label]);
  btn.addEventListener('click', function () {
    navigator.clipboard.writeText(getText()).catch(function () {});
    label.textContent = 'Copied';
    btn.setAttribute('aria-label', 'Copied');
    setTimeout(function () { label.textContent = 'Copy'; btn.setAttribute('aria-label', 'Copy'); }, 1200);
  });
  return btn;
}

// ---------- Documents on the built card ----------
// Each built document is its own thumbnail (page 1, about 120 px wide) with a caption, an eye
// on hover, click to open the PDF, and a drag handle that carries the real file so it can be
// dropped straight onto an application's upload zone. A missing cover letter is a dashed box
// that writes one. The image comes from the server; if it cannot load, the tile hides itself.
var fileCache = {};   // 'jobId:doc' -> File, fetched when the tile renders so dragstart is synchronous
function prefetchFile(job, doc, name) {
  var key = job.id + ':' + doc;
  if (fileCache[key] || typeof fetch !== 'function') return;
  fetch(SERVER + '/jobs/' + job.id + '/file?doc=' + doc).then(function (r) {
    if (!r.ok) throw new Error('no file');
    return r.blob();
  }).then(function (blob) {
    fileCache[key] = new File([blob], name, { type: 'application/pdf' });
  }).catch(function () {});
}
function docTile(job, doc) {
  var d = doc === 'cover' ? job.cover : job.build;
  var label = doc === 'cover' ? 'Cover letter' : 'Resume';
  var name = d && d.pdf ? String(d.pdf).split('/').pop() : label + '.pdf';
  var stamp = encodeURIComponent((doc === 'cover' ? job.cover_built_at : job.built_at) || '');
  var img = h('img', { class: 'thumb-img', alt: 'Page 1 of the ' + label.toLowerCase(),
    src: SERVER + '/jobs/' + job.id + '/thumb?doc=' + doc + '&v=' + stamp });
  var btn = h('button', { type: 'button', class: 'thumb', 'aria-label': 'Open the ' + label.toLowerCase(),
    title: 'Open the ' + label.toLowerCase() + ' · drag it onto an upload field', draggable: 'true' },
    [img, h('span', { class: 'thumb-eye' }, [icon('eye')])]);
  var tile = h('div', { class: 'doc-tile', 'data-doc': doc }, [btn, h('div', { class: 'doc-caption' }, [label])]);
  img.addEventListener('error', function () { tile.hidden = true; });
  btn.addEventListener('click', function () {
    apiPost('/jobs/' + job.id + '/open', { what: doc }).catch(function () {});
  });
  btn.addEventListener('dragstart', function (e) {
    var f = fileCache[job.id + ':' + doc];
    var dt = e.dataTransfer;
    if (!dt) return;
    if (f && dt.items && dt.items.add) dt.items.add(f);
    // Finder and the desktop understand this form; web drop zones read dt.files from the item above.
    dt.setData('DownloadURL', 'application/pdf:' + name + ':' + SERVER + '/jobs/' + job.id + '/file?doc=' + doc);
    dt.effectAllowed = 'copy';
  });
  prefetchFile(job, doc, name);
  return tile;
}
function coverBox(job) {
  // No cover letter yet: a dashed box that writes one. While it writes, the box carries a timer.
  if (job.cover_busy) {
    return h('div', { class: 'doc-tile' }, [
      h('div', { class: 'thumb thumb-empty busy' }, [workingTimer('Writing', job.cover_started_at, 'cover')]),
      h('div', { class: 'doc-caption' }, ['Cover letter'])
    ]);
  }
  var btn = h('button', { type: 'button', class: 'thumb thumb-empty', 'aria-label': 'Generate cover letter',
    title: 'Write a cover letter for this job' }, [icon('plus'), h('span', { class: 'thumb-empty-label' }, ['Generate cover letter'])]);
  btn.disabled = isInFlight(job.id, 'cover');
  btn.addEventListener('click', function () { runAction(job, 'cover', '/jobs/' + job.id + '/cover', {}); });
  var tile = h('div', { class: 'doc-tile' }, [btn, h('div', { class: 'doc-caption' }, ['Cover letter'])]);
  if (job.cover_error) tile.appendChild(h('div', { class: 'error-text doc-error' }, [job.cover_error]));
  return tile;
}
function documentsRow(job) {
  var tiles = [docTile(job, 'resume'), (job.cover && job.cover.pdf) ? docTile(job, 'cover') : coverBox(job)];
  if (job.revising && job.revising.doc) {
    // The document being revised shows a timer over its page until the new one lands.
    var idx = job.revising.doc === 'cover' ? 1 : 0;
    var t = tiles[idx] && tiles[idx].querySelector('.thumb');
    if (t) {
      t.classList.add('revising');
      t.appendChild(h('span', { class: 'thumb-working' }, [workingTimer('Revising', job.revising.started_at, 'revise')]));
    }
  }
  return h('div', { class: 'thumb-row' }, tiles);
}

// Feedback on a document, or the employer's own asks for the letter. One box, one button; the
// server resumes the session that wrote the document and the engine fits it again.
function feedbackForm(job) {
  var d = getDraft(job.id);
  var hasCover = !!(job.cover && job.cover.pdf);
  var asks = job.cover_requirements || [];
  if (d.fbDoc === undefined) d.fbDoc = (!hasCover && asks.length) ? 'cover' : 'resume';
  if (d.fb === undefined) d.fb = (!hasCover && asks.length) ? asks.join('\n') : '';
  var busy = !!(job.revising || job.cover_busy);
  var box = h('div', { class: 'feedback' });
  var choice = h('div', { class: 'fb-choice', role: 'radiogroup', 'aria-label': 'Which document' });
  var ta = h('textarea', { class: 'fb-text', rows: '3', placeholder: 'What should change?' });
  ta.value = d.fb;
  ta.addEventListener('input', function () { d.fb = ta.value; });
  var send = h('button', { type: 'button', class: 'btn-secondary fb-send' }, [icon('refresh'), h('span', {}, [''])]);
  function labelFor() {
    if (d.fbDoc === 'cover' && !hasCover) return 'Write the cover letter with this';
    return d.fbDoc === 'cover' ? 'Revise the cover letter' : 'Revise the resume';
  }
  function refresh() {
    send.querySelector('span:not(.icon)').textContent = labelFor();
    send.disabled = busy || !ta.value.trim() || isInFlight(job.id, 'revise') || isInFlight(job.id, 'cover');
    Array.prototype.forEach.call(choice.children, function (c) {
      var on = c.getAttribute('data-doc') === d.fbDoc;
      c.classList.toggle('active', on);
      c.setAttribute('aria-checked', on ? 'true' : 'false');
    });
  }
  [['resume', 'Resume'], ['cover', 'Cover letter']].forEach(function (pair) {
    var c = h('button', { type: 'button', class: 'fb-chip', role: 'radio', 'data-doc': pair[0] }, [pair[1]]);
    c.addEventListener('click', function () { d.fbDoc = pair[0]; refresh(); });
    choice.appendChild(c);
  });
  ta.addEventListener('input', refresh);
  send.addEventListener('click', function () {
    var text = ta.value.trim();
    if (!text) return;
    if (d.fbDoc === 'cover' && !hasCover) {
      runAction(job, 'cover', '/jobs/' + job.id + '/cover', { instructions: text });
    } else {
      runAction(job, 'revise', '/jobs/' + job.id + '/revise', { doc: d.fbDoc, feedback: text });
    }
    d.fb = '';
  });
  if (asks.length) {
    box.appendChild(h('div', { class: 'fb-asks' }, [h('div', { class: 'fb-asks-title' }, ['The posting asks for this in the letter']),
      h('ul', { class: 'list-compact' }, asks.map(function (a) { return h('li', { text: a }); }))]));
  }
  box.appendChild(choice);
  box.appendChild(ta);
  box.appendChild(h('div', { class: 'fb-row' }, [send]));
  if (job.revise_error) box.appendChild(h('div', { class: 'error-text' }, [job.revise_error]));
  refresh();
  var open = !!(asks.length && !hasCover);
  var details = detailsBlock('feedback-details', open, 'Feedback, or the employer\u2019s own asks', box);
  return details;
}

// "Sep 14, 3:02 pm" from an ISO stamp; empty when there is none.
function formatWhen(iso) {
  if (!iso) return '';
  var d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ', ' +
    d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }).toLowerCase();
}

// Re-run the evaluation on a job that already has one: the posting may have changed, or a
// month may have passed. The previous verdict stays on the record server-side.
// Evaluate again replaces an evaluation you may have acted on, and the button is easy to hit by
// accident . The first click arms it for a few seconds and says so on the button;
// only a second click runs it. Kept in a map so a re-render while armed does not lose it.
var evalArmed = {};          // job id -> time the arming lapses
var EVAL_ARM_MS = 4000;
function evaluateAgainButton(job, full) {
  var label = 'Evaluate again';
  var armed = (evalArmed[job.id] || 0) > Date.now();
  var btn = full
    ? h('button', { type: 'button', class: 'btn-secondary' + (armed ? ' armed' : ''), 'aria-label': armed ? 'Click again to evaluate again' : label },
        [icon('refresh'), h('span', {}, [armed ? 'Click again to confirm' : label])])
    : h('button', { type: 'button', class: 'btn-icon btn-icon-sm' + (armed ? ' armed' : ''),
                    'aria-label': armed ? 'Click again to evaluate again' : label, title: armed ? 'Click again to evaluate again' : label },
        armed ? [h('span', { class: 'armed-text' }, ['Again?'])] : [icon('refresh'), h('span', { class: 'sr-only' }, [label])]);
  btn.disabled = isInFlight(job.id, 'evaluate') || job.status === 'evaluating' || job.status === 'building';
  btn.addEventListener('click', function (e) {
    e.stopPropagation();
    if ((evalArmed[job.id] || 0) > Date.now()) {
      delete evalArmed[job.id];
      runAction(job, 'evaluate', '/jobs/' + job.id + '/evaluate', {});
      return;
    }
    evalArmed[job.id] = Date.now() + EVAL_ARM_MS;
    render();
    setTimeout(function () { if ((evalArmed[job.id] || 0) <= Date.now()) { delete evalArmed[job.id]; render(); } }, EVAL_ARM_MS + 50);
  });
  btn.addEventListener('keydown', function (e) { e.stopPropagation(); });
  return btn;
}

function openFolderButton(job) {
  var btn = h('button', { type: 'button', class: 'btn-icon', 'aria-label': 'Open folder', title: 'Open folder' },
    [icon('folder'), h('span', { class: 'sr-only' }, ['Open folder'])]);
  btn.addEventListener('click', function () { apiPost('/jobs/' + job.id + '/open').catch(function () {}); });
  return btn;
}

function showBanner(text) { bannerEl.textContent = text; bannerEl.hidden = false; }
function clearBanner() { bannerEl.hidden = true; }

function formatNum(n) { return (n || 0).toLocaleString('en-US'); }

// ---------- API ----------
function apiGet(path) {
  return fetch(SERVER + path).then(function (r) {
    if (!r.ok) throw new Error('Server responded ' + r.status);
    return r.json();
  });
}
function apiPost(path, body) {
  return fetch(SERVER + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {})
  }).then(function (r) {
    return r.json().catch(function () { return {}; }).then(function (data) {
      if (!r.ok) throw new Error(data.error || data.message || ('Server error ' + r.status));
      return data;
    });
  });
}

// ---------- Health ----------
function pollHealth() {
  apiGet('/health').then(function (health) {
    clearBanner();
    pollBell();
    healthDot.className = 'dot ok';
    healthText.textContent = 'Server ok';   // only visible inside the settings sheet
    var missing = health.claude === 'missing' || health.claude === 'not_logged_in';
    warningLine.hidden = !missing;
    if (missing) warningLine.textContent = health.claude === 'missing'
      ? 'claude: missing. Install the Claude Code CLI, then run: claude login'
      : 'claude: not logged in. In Terminal run: claude login';
  }).catch(function () {
    healthDot.className = 'dot down';
    healthText.textContent = 'Server unreachable';
    showBanner('Start the server: python3 server/app.py');
  });
}

// ---------- Profile status: onboarding and optional features ----------
var setupEl = null;
function applyFeatures() {
  var li = document.getElementById('li-btn');
  if (li) { li.hidden = !features.outreach; if (!features.outreach && liMode) setLiMode(false); }
  var empty = onboarded === false;
  if (empty && !setupEl) {
    setupEl = document.createElement('div');
    setupEl.id = 'setup-empty';
    setupEl.className = 'empty-state';
    setupEl.textContent = 'Set up your profile first: open this folder in Claude Code and run /onboard.';
    jobsListEl.parentNode.insertBefore(setupEl, jobsListEl);
  }
  if (setupEl) setupEl.hidden = !empty;
  jobsListEl.hidden = empty || liMode;
  render();
}
function loadProfileStatus() {
  return apiGet('/api/profile/status').then(function (st) {
    var f = (st && st.features) || {};
    features = { sponsorship: !!f.sponsorship, outreach: !!f.outreach, email: !!f.email, alerts: !!f.alerts };
    onboarded = (st && typeof st.onboarded === 'boolean') ? st.onboarded : null;
  }).catch(function () {
    features = { sponsorship: false, outreach: false, email: false, alerts: false };
    onboarded = null;
  }).then(applyFeatures);
}

// ---------- Server address ----------
var serverInput = document.getElementById('server-input');
var serverSaveBtn = document.getElementById('server-save');
function normalizeServer(v) {
  v = String(v || '').trim().replace(/\/+$/, '');
  return /^https?:\/\/[^\s\/]+$/i.test(v) ? v : '';
}
function showServerField() { if (serverInput) serverInput.value = SERVER; }
function setServer(v) {
  var url = normalizeServer(v) || DEFAULT_SERVER;
  SERVER = url;
  showServerField();
  try {
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      if (url === DEFAULT_SERVER) chrome.storage.local.remove('serverUrl'); else chrome.storage.local.set({ serverUrl: url });
    }
  } catch (e) { /* storage unavailable */ }
  refreshAll();
}
function refreshAll() { loadProfileStatus(); loadSettings(); loadJobs(); pollHealth(); pollStats(); }
if (serverSaveBtn) serverSaveBtn.addEventListener('click', function () {
  var typed = serverInput.value;
  if (String(typed).trim() && !normalizeServer(typed)) { showBanner('The server address looks like http://127.0.0.1:8790'); return; }
  setServer(typed);
});
function loadServerSetting() {
  try {
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      return chrome.storage.local.get('serverUrl').then(function (d) {
        var url = normalizeServer(d && d.serverUrl);
        if (url) SERVER = url;
        showServerField();
      }).catch(function () {});
    }
  } catch (e) { /* storage unavailable */ }
  return Promise.resolve();
}

// ---------- Settings ----------
var buildModelSelect = document.getElementById('build-model');
function loadSettings() {
  apiGet('/settings').then(function (s) {
    settings = s;
    autoToggle.checked = !!s.auto;
    thresholdInput.value = (s.threshold === undefined || s.threshold === null) ? 70 : s.threshold;
    if (buildModelSelect && s.build_model) buildModelSelect.value = s.build_model;
    renderAutoBadge();
  }).catch(function () {});
}
function saveSettings() {
  var body = { auto: autoToggle.checked, threshold: Number(thresholdInput.value) || 0 };
  if (buildModelSelect) body.build_model = buildModelSelect.value;
  apiPost('/settings', body).then(function (s) { settings = s; renderAutoBadge(); }).catch(function () {});
}
autoToggle.addEventListener('change', saveSettings);
thresholdInput.addEventListener('change', saveSettings);
if (buildModelSelect) buildModelSelect.addEventListener('change', saveSettings);

// ---------- Jobs polling ----------
function scheduleJobsPoll() {
  clearTimeout(jobsTimer);
  var active = jobs.some(function (j) { return j.status === 'evaluating' || j.status === 'building' || j.status === 'queued' || j.ask_busy; });
  jobsTimer = setTimeout(loadJobs, active ? 2000 : 10000);
}
// A capture always shows its card where you already are. You live on Active, so the filter never
// changes: the captured job is pinned to the top of the list under "Just captured" even when its
// own state (applied, skipped) belongs to a group Active hides. A posting already in the list
// says so on the card and offers the only two things you would want: leave it, or evaluate again.
var revealedId = null;      // pinned into the current view until you act or capture another
var revealedSeen = false;   // it was already in the list when you pressed the eye
var pendingReveal = null;
function revealJob(id, msg) {
  pendingReveal = id;
  expandedId = id;
  revealedId = id;
  revealedSeen = !!(msg && msg.seen);
  clearBanner();
  loadJobs();
}
function clearReveal() {
  revealedId = null;
  revealedSeen = false;
  render();
}
function applyPendingReveal() {
  if (!pendingReveal) return;
  var job = jobs.filter(function (j) { return j.id === pendingReveal; })[0];
  if (!job) return;                                   // not in the list yet; the next poll will catch it
  if (searchQuery) { searchInput.value = ''; searchQuery = ''; searchIds = null; }
  pendingReveal = null;
  setTimeout(function () {
    var el = document.getElementById('body-' + job.id);
    if (el && el.parentNode && el.parentNode.scrollIntoView) el.parentNode.scrollIntoView({ block: 'nearest' });
  }, 60);
}

// The line at the top of a freshly captured card: what the panel already knows about it, and
// the two ways out. Only on a posting that was already in the list.
function seenBeforeRow(job) {
  var ev = job.evaluation;
  var bits = [];
  if (job.evaluated_at) bits.push('evaluated ' + formatWhen(job.evaluated_at));
  if (ev) bits.push(ev.fit_score + ' ' + String(ev.recommendation || '').toUpperCase());
  if (job.status === 'applied') bits.push('you applied');
  else if (job.status === 'skipped') bits.push('you skipped it');
  else if (job.build && job.build.pdf) bits.push('resume built');
  var box = h('div', { class: 'seen-row' }, [
    h('div', { class: 'seen-text' }, ['You captured this before' + (bits.length ? ' · ' + bits.join(' · ') : '')])
  ]);
  var leave = h('button', { type: 'button', class: 'btn-secondary' }, [icon('check'), h('span', {}, ['Leave it'])]);
  leave.addEventListener('click', clearReveal);
  box.appendChild(h('div', { class: 'action-pair' }, [leave, evaluateAgainButton(job, true)]));
  return box;
}

function loadJobs() {
  apiGet('/jobs').then(function (list) {
    var json = JSON.stringify(list);
    var changed = json !== lastJobsJson;
    lastJobsJson = json;
    jobs = list;
    if (expandedId === null && jobs.length) expandedId = jobs[0].id;
    var wasPending = pendingReveal;
    applyPendingReveal();
    if (changed || wasPending) render();   // never rebuild the DOM under the user's fingers for no reason
    scheduleJobsPoll();
  }).catch(function () { scheduleJobsPoll(); });
}

// ---------- Markdown-lite rendering (paragraphs, bullet lists, fenced code) ----------
function withCopy(node, plainText) {
  var box = h('div', { class: 'copy-box' }, [node]);
  box.appendChild(copyButton(function () { return plainText; }));
  return box;
}

function renderMarkdownLite(text) {
  var wrap = h('div', { class: 'md' });
  var lines = String(text || '').split(/\r?\n/);
  var i = 0;
  while (i < lines.length) {
    var line = lines[i];
    if (/^```/.test(line)) {
      var codeLines = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) { codeLines.push(lines[i]); i++; }
      i++;
      var codeText = codeLines.join('\n');
      var pre = h('pre', { class: 'code-block' }, [h('code', { text: codeText })]);
      wrap.appendChild(withCopy(pre, codeText));
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      var items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*]\s+/, '')); i++; }
      var ul = h('ul', { class: 'md-list' }, items.map(function (it) { return h('li', { text: it }); }));
      wrap.appendChild(withCopy(ul, items.join('\n')));
      continue;
    }
    if (line.trim() === '') { i++; continue; }
    var q = /^\s*\*\*(.+)\*\*\s*$/.exec(line);
    if (q) { wrap.appendChild(h('p', { class: 'md-q', text: q[1] })); i++; continue; }   // a restated question line
    var paraLines = [];
    while (i < lines.length && lines[i].trim() !== '' && !/^```/.test(lines[i]) && !/^\s*[-*]\s+/.test(lines[i])
           && !/^\s*\*\*(.+)\*\*\s*$/.test(lines[i])) {
      paraLines.push(lines[i]);
      i++;
    }
    wrap.appendChild(h('p', {}, inlineMd(paraLines.join(' '))));
  }
  return wrap;
}
// **bold** inside a paragraph becomes <strong>; everything else is text.
function inlineMd(text) {
  var out = [];
  var parts = String(text).split(/\*\*(.+?)\*\*/);
  for (var k = 0; k < parts.length; k++) {
    if (!parts[k]) continue;
    out.push(k % 2 === 1 ? h('strong', { text: parts[k] }) : document.createTextNode(parts[k]));
  }
  return out;
}

// ---------- Status groups (for the filter row) ----------
// Two filters over the list, and three groups inside it. Active is everything still in play,
// whether it is waiting on you or on the machine; the headings inside say which.
var NEEDS = ['questions', 'error', 'needs_login', 'built', 'built_external', 'scored', 'awaiting', 'captured'];
var WORKING = ['evaluating', 'building', 'queued'];
var DONE = ['applied', 'skipped'];
var GROUP_LABEL = { captured: 'Just captured', needs: 'Needs you', working: 'Working', applied: 'Applied', skipped: 'Skipped' };
var GROUP_ORDER = ['captured', 'needs', 'working', 'applied', 'skipped'];

// Within "Needs you", the order is what to do next, not when it was captured: answer a
// question, fix an error, upload a finished build, approve, evaluate.
// Submitted, and waiting on your answer to "reach out to people here?" : the
// card stays in Active under Needs you until you answer.
// The server refuses outreach once you are in their process or the application has ended (job_closed), so
// neither surface offers the Find people prompt for those stages .
var CLOSED_STAGES = ['rejected', 'withdrawn'];
function outreachHold(job) {
  if (job.status !== 'applied') return null;
  var label = (STAGE_LABEL[job.stage] || '').toLowerCase();
  if (job.stage === 'paused') return 'On hold: search paused';
  if (OPEN_STAGES.indexOf(job.stage) !== -1) return 'On hold: ' + label;
  if (CLOSED_STAGES.indexOf(job.stage) !== -1) return 'Closed: ' + label;
  return null;
}
// The inbox watch's newest email about this job, from the server's per-job summary (job.inbox).
var INBOX_KIND = { rejection: 'rejection', paused: 'search paused', out_of_office: 'away reply', interview: 'interview', assessment: 'assessment',
  reply: 'reply', received: 'acknowledgement', other: 'other' };
function lastEmail(job) {
  var ib = job.inbox;
  if (!ib || !ib.count) return '';
  var d = new Date(ib.last_at), day = isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  return ' · last email: ' + (INBOX_KIND[ib.last_kind] || 'email') + (day ? ', ' + day : '');
}
function isPending(job) { return features.outreach && job.status === 'applied' && !!job.outreach_pending && !outreachHold(job); }
function needsRank(job) {
  if (isPending(job)) return NEEDS.indexOf('built') + 0.5;   // right after uploading a finished build
  var i = NEEDS.indexOf(job.status);
  return i === -1 ? NEEDS.length : i;
}
function jobGroup(job) {
  // A built job whose cover letter or revision is still running is working, not waiting on you.
  if (job.revising || job.cover_busy) return 'working';
  if (WORKING.indexOf(job.status) !== -1) return 'working';
  if (isPending(job)) return 'needs';
  if (DONE.indexOf(job.status) !== -1) return job.status;   // 'applied' or 'skipped'

  if (NEEDS.indexOf(job.status) !== -1) return 'needs';
  return null;
}
// After Applied : where the job stands. The open ones make up In process.
var STAGE_LABEL = { heard_back: 'Heard back', assessment: 'Assessment', interviewing: 'Interviewing',
  offer: 'Offer', paused: 'On hold', rejected: 'Rejected', withdrawn: 'Withdrawn' };
// 'paused' : the company put the search on hold. Open, so it holds outreach like the rest.
var OPEN_STAGES = ['heard_back', 'assessment', 'interviewing', 'offer', 'paused'];
function inProcess(job) { return job.status === 'applied' && OPEN_STAGES.indexOf(job.stage) !== -1; }
function inFilter(job, f) {
  if (f === 'all') return true;
  if (f === 'process') return inProcess(job);
  if (f === 'active') return WORKING.indexOf(job.status) !== -1 || NEEDS.indexOf(job.status) !== -1 || isPending(job);
  return job.status === f;   // 'applied' or 'skipped'
}
function computeCounts(list) {
  var counts = { all: list.length, active: 0, process: 0, applied: 0, skipped: 0 };
  list.forEach(function (j) { ['active', 'process', 'applied', 'skipped'].forEach(function (f) { if (inFilter(j, f)) counts[f]++; }); });
  return counts;
}
function renderFilterRow() {
  var counts = computeCounts(jobs);
  filterRow.hidden = liMode || jobs.length < FILTER_MIN_JOBS;
  if (filterRow.hidden && currentFilter !== 'all') currentFilter = 'all';   // few jobs: no filtering at all
  renderAutoBadge();
  filterButtons.forEach(function (btn) {
    var f = btn.getAttribute('data-filter');
    var countEl = btn.querySelector('.filter-count');
    if (countEl) countEl.textContent = String(counts[f] || 0);
    var name = (btn.querySelector('.filter-label') || btn).textContent.trim();
    btn.setAttribute('aria-label', name + ', ' + (counts[f] || 0));
    btn.title = name + ' · ' + (counts[f] || 0);
    var active = f === currentFilter;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
  });
}
filterButtons.forEach(function (btn) {
  btn.addEventListener('click', function () {
    currentFilter = btn.getAttribute('data-filter');
    render();
  });
});

// ---------- Drafts ----------
function getDraft(jobId) {
  if (!drafts[jobId]) drafts[jobId] = {};
  var d = drafts[jobId];
  if (d.ask === undefined) d.ask = '';
  if (d.note === undefined) d.note = '';
  if (!d.questions) d.questions = {};
  return d;
}
function getQuestionDraft(jobId, qid) {
  var d = getDraft(jobId);
  if (!d.questions[qid]) d.questions[qid] = { choice: '', text: '', remember: false };
  return d.questions[qid];
}

// ---------- Score / recommendation colour ----------
function scoreTone(score) {
  if (score >= 70) return 'ok';
  if (score >= 50) return 'warn';
  return 'muted';
}

// ---------- Verdict chips (exact table at the end of API.md) ----------
// Blocker kinds that are structural (the JD rules you out) read red; the rest amber.
var HARD_BLOCKER_KINDS = { contract: 1, visa: 1, clearance: 1, citizenship: 1 };

// Visa wording only means something when sponsorship matters to you. With that feature off,
// visa pre-screen hits and visa blockers are left out everywhere.
function kindShown(kind) { return features.sponsorship || kind !== 'visa'; }
function prescreenOf(job) {
  return (job.prescreen || []).filter(function (p) { return p && kindShown(p.kind); });
}

function buildChips(job) {
  var ev = job.evaluation;
  var chips = [];

  // Pre-screen first: read straight from the JD text at capture, with evidence, before any
  // model runs. Then the evaluator's blockers for kinds the pre-screen did not already cover.
  var kindsShown = {};
  prescreenOf(job).forEach(function (p) {
    if (!p || !p.label) return;
    chips.push({ text: p.label, tone: p.hard ? 'danger' : 'warn', title: p.evidence || '' });
    kindsShown[p.kind] = true;
  });
  ((ev && ev.blockers) || []).forEach(function (b) {
    if (!b || !b.label || kindsShown[b.kind] || !kindShown(b.kind)) return;
    if (chips.length >= 4) return;
    chips.push({ text: b.label, tone: HARD_BLOCKER_KINDS[b.kind] ? 'danger' : 'warn' });
    kindsShown[b.kind] = true;
  });
  if (job.seen_before) {
    var sb = job.seen_before;
    chips.push({ text: 'Seen before · ' + String(sb.captured_at || '').slice(0, 10) +
      (sb.fit_score != null ? ' · scored ' + sb.fit_score : ''), tone: 'warn',
      title: 'Same company and role captured earlier as ' + sb.id });
  }
  if (ev && ev.approach && ev.approach.name && ev.approach.name !== 'unset') {
    // How the resume will be approached, decided once at evaluation; hover for the reason.
    chips.push({ text: 'Approach · ' + ev.approach.name, tone: 'neutral',
      title: (ev.approach.why || '') + ((ev.approach.adjustments || []).length ? '\n\n' + ev.approach.adjustments.map(function (a) { return '\u2022 ' + a; }).join('\n') : '')
        + (ev.approach.by ? '\n\nChosen by ' + ev.approach.by : '') });
  }
  if (job.jd_changed) {
    chips.push({ text: 'Posting changed since evaluated', tone: 'warn',
      title: formatNum(job.jd_changed.old_chars) + ' characters when evaluated, ' + formatNum(job.jd_changed.new_chars) +
        ' now (' + formatWhen(job.jd_changed.at) + ')' });
  }
  if (job.captured_again && job.captured_again.count) {
    chips.push({ text: 'Captured ' + (job.captured_again.count + 1) + ' times', tone: 'neutral' });
  }

  if (features.sponsorship && ev && ev.sponsorship_flag === 'explicit_no') {
    chips.push({ text: 'No sponsorship in the JD', tone: 'danger' });
  }

  if (!features.sponsorship) {
    // Sponsorship is off: no filing chips at all.
  } else if (job.lca) {
    var filings = job.lca.filings || 0;
    var trend = String(job.lca.trend || '').toUpperCase();
    if (filings > 0) {
      var unit = filings === 1 ? ' filing' : ' filings';
      if (/SHRINKING|DROPPED/.test(trend)) {
        chips.push({ text: 'Sponsors, but shrinking', tone: 'warn' });
      } else if (filings < 5) {
        // A handful of filings is thin evidence. Green here would overstate it, and the chip
        // is a decision signal, so it says how thin it is instead.
        chips.push({ text: 'Sponsored only ' + formatNum(filings) + ' time' + (filings === 1 ? '' : 's'), tone: 'warn' });
      } else {
        chips.push({ text: 'Sponsors · ' + formatNum(filings) + unit, tone: 'ok' });
      }
    }
  } else {
    chips.push({ text: 'No LCA record', tone: 'warn' });
  }

  if (ev && ev.level_fit === 'stretch') chips.push({ text: 'Level stretch', tone: 'warn' });
  else if (ev && ev.level_fit === 'under') chips.push({ text: 'Below level', tone: 'warn' });

  if (job.duplicate_of) chips.push({ text: 'Seen before', tone: 'warn' });

  if (job.capture_quality && job.capture_quality !== 'ok') {
    chips.push(job.capture_quality === 'list'
      ? { text: 'Captured the list, not the job', tone: 'danger' }
      : { text: 'Short capture · ' + formatNum(job.text_chars) + ' chars', tone: 'warn' });
  }

  // The resume version is not a chip: it does not change what you do next, so it lives under Why.

  if (!chips.length) return null;
  return h('div', { class: 'chips-row' }, chips.map(function (c) {
    var attrs = { class: 'chip tone-' + c.tone };
    if (c.title) attrs.title = c.title;
    return h('span', attrs, [c.text]);
  }));
}

function setInFlight(jobId, action, value) {
  inFlight[jobId] = inFlight[jobId] || {};
  inFlight[jobId][action] = value;
}
function isInFlight(jobId, action) { return !!(inFlight[jobId] && inFlight[jobId][action]); }

function runAction(job, action, path, body) {
  setInFlight(job.id, action, true);
  delete actionError[job.id];
  render();
  apiPost(path, body).then(function () {
    setInFlight(job.id, action, false);
    loadJobs();
  }).catch(function (err) {
    setInFlight(job.id, action, false);
    actionError[job.id] = err.message || String(err);
    render();
  });
}

// A labelled compact list, only rendered when items is non-empty.
function labelledList(label, items) {
  if (!items || !items.length) return null;
  return h('div', {}, [
    h('div', { class: 'muted' }, [label]),
    h('ul', { class: 'list-compact' }, items.map(function (s) { return h('li', { text: s }); }))
  ]);
}

// A <details> section with a compact summary line; open when isOpen is true.
// Once the user toggles a section, that choice is remembered per job across re-renders.
var openState = {};       // 'jobId:cls' -> true/false
var currentJobId = null;  // set by buildCard while its sections are built
function detailsBlock(cls, isOpen, summaryText, contentNode) {
  var key = currentJobId + ':' + cls;
  var attrs = { class: cls };
  var open = (key in openState) ? openState[key] : isOpen;
  if (open) attrs.open = '';
  var d = h('details', attrs, [h('summary', {}, [summaryText]), h('div', { class: 'section-body' }, [contentNode])]);
  d.addEventListener('toggle', function () { openState[key] = d.open; });
  return d;
}

// ---------- "Why NN and what changed" disclosure ----------
function buildWhyDetails(job) {
  var ev = job.evaluation;
  var summary = ev ? ('Why ' + ev.fit_score) : 'Capture details';
  var quick = [];
  var more = [];

  if (ev) {
    // The quick read: one sentence, then the reasons as signed bullets. This is what you asked
    // to see without clicking: why the number is the number.
    if (ev.honest_take) quick.push(h('p', { class: 'why-take' }, [ev.honest_take]));
    function reasonCard(title, items, cls) {
      if (!items || !items.length) return null;
      var ul = h('ul', { class: 'why-list' });
      items.forEach(function (t) { ul.appendChild(h('li', { class: cls }, [t])); });
      return h('div', { class: 'why-card' }, [h('div', { class: 'why-card-title' }, [title]), ul]);
    }
    var sc = reasonCard('Strengths', ev.strengths, 'why-plus');
    var gc = reasonCard('Gaps', ev.gaps, 'why-minus');
    if (sc) quick.push(sc);
    if (gc) quick.push(gc);
    if (ev.keyword_gaps && ev.keyword_gaps.length) {
      quick.push(h('div', { class: 'why-keywords' }, ['Missing from the resume: ' + ev.keyword_gaps.join(' · ')]));
    }
  }

  // Everything else is real but secondary; it sits behind one more click.
  if (ev) more.push(h('div', { class: 'muted' }, ['Built from resume ' + ev.resume_version]));
  if (features.sponsorship && ev && ev.sponsorship) more.push(h('div', {}, [ev.sponsorship]));
  if (features.sponsorship && job.lca) {
    more.push(h('div', { class: 'muted' }, [
      job.lca.matched_name + ': ' + job.lca.filings + ' filings, ' + job.lca.certified + ' certified, ' + String(job.lca.trend || '').toLowerCase()
    ]));
  } else if (features.sponsorship && ev) {
    more.push(h('div', { class: 'muted' }, ['No LCA record']));
  }
  if (job.duplicate_of) {
    more.push(h('div', { class: 'error-text' }, ['Duplicate of job ' + job.duplicate_of.id + ' (' + job.duplicate_of.status + ')']));
  }
  if (job.build) {
    var b = job.build;
    [labelledList('Claims to verify', b.claims_to_verify), labelledList('What changed', b.changes), labelledList('Tools left off', b.tools_omitted)]
      .forEach(function (n) { if (n) more.push(n); });
    if (b.duration_ms) more.push(h('div', { class: 'muted' }, ['Build took ' + formatDuration(b.duration_ms / 1000)]));
  }
  if (ev && ev.timing && ev.timing.wall_ms) {
    more.push(h('div', { class: 'muted' }, ['Evaluation took ' + formatDuration(ev.timing.wall_ms / 1000) +
      ' over ' + ev.timing.turns + ' turns']));
  }
  more.push(h('div', { class: 'meta-line' }, [formatNum(job.text_chars) + ' characters captured']));
  more.push(h('details', { class: 'preview' }, [
    h('summary', {}, ['First 300 characters']),
    h('pre', { text: job.text_head || (job.text || '').slice(0, 300) })
  ]));
  var folderLine = h('div', { class: 'folder-line' }, [h('span', { class: 'mono', text: (job.folder || '').split('/').pop() })]);
  folderLine.appendChild(copyButton(function () { return job.folder || ''; }));
  more.push(folderLine);
  if (ev && ev.brief) {
    more.push(h('details', { class: 'preview' }, [h('summary', {}, ['Full brief']), h('pre', { class: 'brief', text: ev.brief })]));
  }

  // Expanding the card is the "I'm interested" signal, so the reasoning sits in the open and
  // only the secondary detail stays behind a click.
  var body = h('div', { class: 'why-inline' }, quick);
  body.appendChild(h('details', { class: 'preview why-more' }, [h('summary', {}, ['More detail']), h('div', {}, more)]));
  return body;
}

// ---------- Ask disclosure ----------
// Plain text of an assistant message for the clipboard: the bold markers go, nothing else.
function plainAnswer(text) {
  return String(text || '').replace(/\*\*(.+?)\*\*/g, '$1').replace(/\r?\n{3,}/g, '\n\n').trim();
}

// An answer message split at its bold question lines: one block per form question, each with
// its own copy. A message with no question lines is one block. Deterministic, on the text.
function answerBlocks(text) {
  var blocks = [];
  var cur = { question: '', lines: [] };
  String(text || '').split(/\r?\n/).forEach(function (line) {
    var q = /^\s*\*\*(.+)\*\*\s*$/.exec(line);
    if (q) {
      if (cur.question || cur.lines.join('').trim()) blocks.push(cur);
      cur = { question: q[1], lines: [] };
    } else {
      cur.lines.push(line);
    }
  });
  if (cur.question || cur.lines.join('').trim()) blocks.push(cur);
  return blocks.map(function (b) { return { question: b.question, body: b.lines.join('\n').trim() }; });
}
function copyIcon(getText) {
  var cp = h('button', { type: 'button', class: 'btn-icon btn-icon-sm msg-copy', 'aria-label': 'Copy', title: 'Copy this answer' },
    [icon('copy'), h('span', { class: 'sr-only' }, ['Copy'])]);
  cp.addEventListener('click', function () {
    navigator.clipboard.writeText(getText()).catch(function () {});
    cp.classList.add('copied');
    setTimeout(function () { cp.classList.remove('copied'); }, 1200);
  });
  return cp;
}

function buildAskSection(job) {
  var d = getDraft(job.id);
  var thread = h('div', { class: 'ask-thread' }, (job.messages || []).map(function (m) {
    if (m.role !== 'assistant') return h('div', { class: 'msg user' }, [h('div', { class: 'user-text', text: m.text })]);
    var blocks = answerBlocks(m.text);
    return h('div', { class: 'msg assistant' }, blocks.map(function (b) {
      // The copy takes the answer alone, the way it goes into the form field.
      return h('div', { class: 'answer' }, [
        b.question ? h('p', { class: 'md-q', text: b.question }) : null,
        renderMarkdownLite(b.body),
        b.body ? copyIcon(function () { return plainAnswer(b.body); }) : null
      ]);
    }));
  }));

  if (job.ask_busy) thread.appendChild(h('div', { class: 'msg assistant' }, [workingTimer('Writing', job.ask_since, 'ask')]));

  // One box, one voice: form questions come back as your paste-ready answers, a question about
  // the job gets a short reply to you. Enter sends; Shift+Enter makes a new line.
  var input = h('textarea', { class: 'ask-input', 'data-job': job.id, rows: '2', placeholder: 'Paste the form\u2019s questions, or ask about this job' });
  input.value = d.ask;
  input.addEventListener('input', function () { d.ask = input.value; });
  var sendBtn = h('button', { type: 'button', class: 'btn-icon ask-send', 'aria-label': 'Send', title: 'Send (Enter)' },
    [icon('send'), h('span', { class: 'sr-only' }, ['Send'])]);
  sendBtn.disabled = isInFlight(job.id, 'ask');
  function send() {
    var text = input.value.trim();
    if (!text) return;
    input.value = '';
    d.ask = '';
    runAction(job, 'ask', '/jobs/' + job.id + '/ask', { text: text });
  }
  sendBtn.addEventListener('click', send);
  input.addEventListener('keydown', function (e) { if ((e.key === 'Enter' || e.keyCode === 13) && !e.shiftKey) { e.preventDefault(); send(); } });

  return h('div', {}, [thread, h('div', { class: 'row ask-input-row' }, [input, sendBtn])]);
}
function buildAskDetails(job) {
  var d = detailsBlock('section-details', false, 'Ask about this job', buildAskSection(job));
  d.classList.add('ask-details');
  return d;
}
// The chat icon in the header: open the Ask section and put the cursor in it.
function chatButton(job) {
  var label = 'Ask about this job';
  var btn = h('button', { type: 'button', class: 'btn-icon btn-icon-sm', 'aria-label': label, title: label },
    [icon('claude'), h('span', { class: 'sr-only' }, [label])]);
  btn.addEventListener('keydown', function (e) { e.stopPropagation(); });
  btn.addEventListener('click', function (e) {
    e.stopPropagation();
    var card = btn.closest('.card');
    var d = card && card.querySelector('.ask-details');
    if (!d) return;
    d.open = true;
    openState[job.id + ':section-details'] = true;
    if (d.scrollIntoView) d.scrollIntoView({ behavior: 'smooth', block: 'end' });
    // The box is a textarea: put the cursor in it so you can type at once .
    // Looked up when the timer fires, not now: a redraw in between replaces the box.
    setTimeout(function () {
      var input = Array.prototype.find.call(document.querySelectorAll('.ask-input'), function (x) { return x.getAttribute('data-job') === job.id; });
      if (input) input.focus({ preventScroll: true });
    }, 250);
  });
  return btn;
}

// ---------- Questions as radios (v2, legacy strings fall back to a textarea) ----------
function questionId(q, idx) { return (typeof q === 'string') ? ('legacy_' + idx) : q.id; }

function allRequiredAnswered(job) {
  var qs = job.questions || [];
  return qs.every(function (q, idx) {
    if (typeof q === 'string' || q.type === 'text') return true;
    var qd = getQuestionDraft(job.id, questionId(q, idx));
    return !!qd.choice;
  });
}
function refreshSubmitButton(job) {
  var btn = document.getElementById('submit-answers-' + job.id);
  if (btn) btn.disabled = isInFlight(job.id, 'answer') || !allRequiredAnswered(job);
}

function buildOneQuestion(job, q, idx) {
  var qid = questionId(q, idx);
  var qd = getQuestionDraft(job.id, qid);
  var isLegacy = typeof q === 'string';
  var isTextType = isLegacy || q.type === 'text';
  var questionText = isLegacy ? q : q.question;

  var wrap = h('div', { class: 'question-item' });
  wrap.appendChild(h('div', { class: 'question-text' }, [questionText]));
  if (!isLegacy && q.why) wrap.appendChild(h('div', { class: 'muted question-why' }, [q.why]));

  if (isTextType) {
    var ta = h('textarea', { placeholder: 'Your answer...' });
    ta.value = qd.text || '';
    ta.addEventListener('input', function () { qd.text = ta.value; });
    wrap.appendChild(ta);
  } else {
    var optsWrap = h('div', { class: 'question-options' });
    (q.options || []).forEach(function (opt, oi) {
      var inputId = 'q-' + job.id + '-' + qid + '-' + oi;
      var radio = h('input', { type: 'radio', name: 'q-' + job.id + '-' + qid, id: inputId, value: opt });
      radio.checked = qd.choice === opt;
      radio.addEventListener('change', function () { qd.choice = opt; refreshSubmitButton(job); });
      optsWrap.appendChild(h('label', { class: 'question-option', for: inputId }, [radio, h('span', {}, [opt])]));
    });
    wrap.appendChild(optsWrap);
  }

  var rememberId = 'remember-' + job.id + '-' + qid;
  var rememberCheck = h('input', { type: 'checkbox', id: rememberId });
  rememberCheck.checked = !!qd.remember;
  rememberCheck.addEventListener('change', function () { qd.remember = rememberCheck.checked; });
  wrap.appendChild(h('label', { class: 'remember-check', for: rememberId }, [rememberCheck, 'Remember this']));

  return wrap;
}

function buildQuestionsBlock(job) {
  var qs = job.questions || [];
  if (!qs.length) return null;
  var draft = getDraft(job.id);

  var container = h('div', { class: 'questions-block', id: 'questions-' + job.id });
  if (job.status === 'built') {
    container.appendChild(h('div', { class: 'muted questions-note' },
      ['Built without these. Answer them and the resume is revised with the claims in.']));
  }
  qs.forEach(function (q, idx) { container.appendChild(buildOneQuestion(job, q, idx)); });

  var noteArea = h('textarea', { placeholder: 'Anything to add...' });
  noteArea.value = draft.note;
  noteArea.addEventListener('input', function () { draft.note = noteArea.value; });
  container.appendChild(h('div', { class: 'question-note-wrap' }, [h('div', { class: 'muted' }, ['Anything to add']), noteArea]));

  var submitBtn = h('button', { type: 'button', class: 'primary primary-action-btn', id: 'submit-answers-' + job.id },
    [h('span', {}, [job.status === 'built' ? 'Answer and revise' : 'Submit answers'])]);
  submitBtn.disabled = isInFlight(job.id, 'answer') || !allRequiredAnswered(job);
  submitBtn.addEventListener('click', function () {
    var answers = qs.map(function (q, idx) {
      var qid = questionId(q, idx);
      var qd = getQuestionDraft(job.id, qid);
      var isTextType = typeof q === 'string' || q.type === 'text';
      return { id: qid, choice: isTextType ? (qd.text || '') : (qd.choice || ''), note: null, remember: !!qd.remember };
    });
    runAction(job, 'answer', '/jobs/' + job.id + '/answer', { answers: answers, note: draft.note || '' });
  });
  container.appendChild(h('div', { class: 'actions' }, [submitBtn]));
  return container;
}

// ---------- Stages (four dots: Captured / Evaluated / Built / Applied) ----------
function computeStages(job) {
  var s = job.status;
  var done = [false, false, false, false];
  var active = -1;
  var skipped = s === 'skipped';
  var isError = s === 'error' || s === 'needs_login';
  if (skipped) {
    // bar greyed entirely, no fill
  } else if (isError) {
    done[0] = true;
    if (job.evaluation) done[1] = true;
    if (job.build) done[2] = true;
  } else {
    switch (s) {
      case 'captured': done[0] = true; break;
      case 'evaluating': done[0] = true; active = 1; break;
      case 'scored': case 'questions': case 'awaiting': done[0] = true; done[1] = true; break;
      case 'queued': case 'building': done[0] = true; done[1] = true; active = 2; break;
      case 'built': case 'built_external': done[0] = true; done[1] = true; done[2] = true; break;
      case 'applied': done[0] = true; done[1] = true; done[2] = true; done[3] = true; break;
      default: done[0] = true;
    }
  }
  return { done: done, active: active, skipped: skipped, isError: isError };
}

function buildStageDots(job) {
  var st = computeStages(job);
  var track = h('div', { class: 'stage-dots' });
  for (var i = 0; i < 4; i++) {
    if (i > 0) {
      var connCls = 'stage-connector' + (!st.skipped && st.done[i - 1] ? ' done' : '');
      track.appendChild(h('div', { class: connCls }));
    }
    var cls = 'stage-dot';
    if (st.skipped) cls += ' skipped';
    else if (st.done[i]) cls += ' done';
    else if (i === st.active) cls += ' active';
    track.appendChild(h('div', { class: cls }));
  }
  return track;
}

// The one status sentence that says what is true right now.
function statusSentence(job) {
  var s = job.status;
  if (s === 'skipped') return 'Skipped';
  if (s === 'error') return job.error || 'Something went wrong.';
  if (s === 'needs_login') return 'Claude session needs login. In Terminal run: claude login';
  if (s === 'captured') {
    if (job.capture_quality === 'empty') return 'Capture failed. Capture the page again.';
    if (job.capture_quality === 'list') return 'Captured the job list, not the job. Open the job and capture again.';
    var hard = prescreenOf(job).filter(function (p) { return p.hard; });
    if (hard.length) return 'Blocked before evaluation: ' + hard.map(function (p) { return p.label; }).join(', ');
    return 'Ready to evaluate';
  }
  if (s === 'evaluating') return 'Evaluating…';
  if (s === 'scored' || s === 'awaiting') return 'Ready to approve and build';
  if (s === 'questions') {
    var n = (job.questions || []).length;
    return 'Needs your answer to ' + n + (n === 1 ? ' question' : ' questions');
  }
  if (s === 'queued') return 'Waiting for the current build to finish';
  if (s === 'building') {
    var bp = job.build_progress;
    if (bp) {
      return (bp.phase_label || 'Building') + ', ' + formatDuration(bp.elapsed_s) +
             (bp.renders > 0 ? ' · render ' + bp.renders : '');
    }
    return 'Building, 5 to 15 min';
  }
  if (s === 'built') {
    var docs = 1 + (job.cover && job.cover.pdf ? 1 : 0);
    return 'Ready to upload · ' + docs + (docs === 1 ? ' document' : ' documents');
  }
  if (s === 'built_external') return 'Built elsewhere, ready to upload';
  if (s === 'applied') {
    if (isPending(job)) return 'Applied · reach out to people?';
    var last = lastEmail(job);
    if (job.stage && STAGE_LABEL[job.stage]) return STAGE_LABEL[job.stage] + (job.stage_at ? ' · ' + formatWhen(job.stage_at) : '') + last;
    return 'Applied' + last;
  }
  return '';
}

// Every status gets one icon and one colour, so the state reads from across the room and the
// sentence beside it only confirms what the icon already said.
var STATUS_ICONS = {
  captured: ['play', 'accent'], scored: ['check', 'accent'], awaiting: ['check', 'accent'],
  questions: ['question', 'warn'], built: ['upload', 'ok'], built_external: ['folder', 'ok'],
  evaluating: ['clock', 'muted'], building: ['clock', 'muted'], queued: ['clock', 'muted'],
  applied: ['check', 'ok'], skipped: ['skip', 'muted'],
  error: ['alert', 'danger'], needs_login: ['alert', 'danger']
};
function statusIcon(job) {
  var pair = STATUS_ICONS[job.status];
  if (!pair) return null;
  // A capture that cannot be used, or one a pre-screen blocked, is a warning whatever its status.
  var tone = pair[1], name = pair[0];
  if (job.status === 'captured') {
    if (job.capture_quality !== 'ok') { name = 'alert'; tone = 'danger'; }
    else if (prescreenOf(job).some(function (p) { return p.hard; })) { name = 'alert'; tone = 'warn'; }
  }
  if (job.status === 'built' && job.revising) { name = 'clock'; tone = 'muted'; }
  if (job.status === 'applied' && job.stage) {
    name = job.stage === 'rejected' || job.stage === 'withdrawn' ? 'x' : job.stage === 'offer' ? 'check' : 'clock';
    tone = job.stage === 'offer' ? 'ok' : job.stage === 'rejected' ? 'danger' : job.stage === 'withdrawn' ? 'muted' : 'accent';
  }
  var el = icon(name, 'status-icon tone-' + tone);
  el.setAttribute('title', statusSentence(job));
  return el;
}

// ---------- Card header (sticky: title+score, company/location+rec, stage dots+status) ----------
function buildCardHeader(job, isExpanded) {
  var ev = job.evaluation;
  var tone = ev ? scoreTone(ev.fit_score) : null;

  // The company leads: titles repeat across the list ("AI Consultant" five times), the
  // company is what tells the cards apart.
  var titleRow = h('div', { class: 'card-title-row' }, [
    h('div', { class: 'card-title', text: job.company || 'Unknown company' }),
    ev ? h('div', { class: 'card-score tone-' + tone }, [String(ev.fit_score)]) : null
  ]);
  var subRow = h('div', { class: 'card-sub-row' }, [
    h('div', { class: 'card-sub' }, [(job.title || job.id) + ' · ' + (job.location || 'location unknown')]),
    ev ? h('div', { class: 'card-rec tone-' + tone }, [String(ev.recommendation || '').toUpperCase()]) : null
  ]);
  // The folder is for the rare look inside; builds go to the Desktop anyway. It lives small,
  // under the score, and must not toggle the card when clicked.
  var folder = null;
  if (isExpanded) {
    folder = openFolderButton(job);
    folder.className = 'btn-icon btn-icon-sm';
    folder.addEventListener('click', function (e) { e.stopPropagation(); });
    folder.addEventListener('keydown', function (e) { e.stopPropagation(); });
  }
  var st = computeStages(job);
  // The dots are a position indicator. Once a job has stopped moving the status sentence
  // already says where it is, so the dots are decoration and come off.
  var moving = job.status === 'evaluating' || job.status === 'building' || job.status === 'queued';
  // On an expanded card the buttons say what can happen next, so the "Ready to..." line is
  // dropped there; it stays on the collapsed card, where it is the only signal.
  var sentence = statusSentence(job);
  var redundant = isExpanded && /^Ready to /.test(sentence);
  // An evaluated card says when, so a month-old verdict reads as month-old; the refresh
  // beside the folder re-runs it. Neither toggles the card.
  var when = ev && isExpanded ? formatWhen(job.evaluated_at || job.evaluating_since) : '';
  var again = ev && isExpanded && !moving ? evaluateAgainButton(job, false) : null;
  var chat = isExpanded ? chatButton(job) : null;
  var si = statusIcon(job);
  var stageRow = h('div', { class: 'card-stage-row' }, [
    si,
    moving ? buildStageDots(job) : null,
    h('div', { class: 'stage-status-text' + (st.isError ? ' error-text' : '') + (si ? ' tone-' + si.className.split('tone-')[1] : ''), title: sentence },
      [redundant ? (when ? 'Evaluated ' + when : '') : sentence]),
    chat,
    again,
    folder
  ]);

  var header = h('div', {
    class: 'card-header', tabindex: '0', role: 'button',
    'aria-expanded': isExpanded ? 'true' : 'false',
    'aria-controls': 'body-' + job.id
  }, [titleRow, subRow, stageRow]);
  function toggle() { expandedId = isExpanded ? null : job.id; render(); }
  header.addEventListener('click', toggle);
  header.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ' || e.keyCode === 13 || e.keyCode === 32) { e.preventDefault(); toggle(); }
  });
  return header;
}

// ---------- Primary action (exactly one, label depends on status) ----------
// Typical durations from your own history, for "usually ~1:20". Refreshed every 30s.
var stats = { evaluate: null, ask: null, build: null };
function pollStats() { apiGet('/stats').then(function (st) { stats = st || stats; }).catch(function () {}); }
setInterval(pollStats, 30000);   // first call happens once the server address is known

function clockFmt(sec) {
  sec = Math.max(0, Math.round(sec || 0));
  return Math.floor(sec / 60) + ':' + String(sec % 60).padStart(2, '0');
}

// An elapsed clock that ticks client-side from a server timestamp, so it is smooth even
// though the job list only refreshes every couple of seconds. It only ever exists while
// something is running, so it disappears on its own when the work does.
function workingTimer(label, sinceIso, typicalKey) {
  var el = h('div', { class: 'working-timer' });
  var lab = h('span', {}, [label]);
  var elapsed = h('span', { class: 'elapsed' });
  el.appendChild(lab); el.appendChild(elapsed);
  var typical = typicalKey ? stats[typicalKey] : null;
  if (typical) el.appendChild(h('span', { class: 'usually' }, ['usually ~' + clockFmt(typical / 1000)]));
  var since = sinceIso ? Date.parse(sinceIso) : Date.now();
  if (isNaN(since)) since = Date.now();
  function tick() { elapsed.textContent = clockFmt((Date.now() - since) / 1000); }
  tick();
  el.setAttribute('data-since', String(since));
  return el;
}
setInterval(function () {
  var nodes = document.querySelectorAll('.working-timer[data-since]');
  for (var i = 0; i < nodes.length; i++) {
    var since = Number(nodes[i].getAttribute('data-since'));
    var e = nodes[i].querySelector('.elapsed');
    if (e) e.textContent = clockFmt((Date.now() - since) / 1000);
  }
}, 1000);

function formatDuration(sec) {
  sec = Math.max(0, Math.round(sec || 0));
  if (sec < 60) return sec + 's';
  var m = Math.floor(sec / 60);
  return m + 'm ' + (sec % 60) + 's';
}

// Real progress, not a decorative bar: the server watches the application folder and reports
// the furthest milestone the build has actually reached and how many times it has rendered.
function buildProgressBlock(job) {
  var p = job.build_progress;
  if (!p) return h('div', { class: 'stage-status-text' }, [statusSentence(job)]);

  var total = Math.max(1, (p.phases_total || 5) - 1);
  var pct = Math.max(6, Math.min(100, Math.round((p.phase / total) * 100)));
  var fill = h('div', { class: 'build-progress-fill' });
  fill.style.width = pct + '%';

  var right = p.renders > 0 ? 'render ' + p.renders : '';

  var block = h('div', { class: 'build-progress' }, [
    h('div', { class: 'build-progress-track' }, [fill]),
    h('div', { class: 'build-progress-meta' }, [
      h('span', { class: 'build-progress-phase' }, [p.phase_label || 'Building']),
      h('span', {}, [right])
    ])
  ]);

  // The model can think for a couple of minutes between file writes, so only say something
  // when the folder has been genuinely quiet for a while.
  if ((p.idle_s || 0) > 240) {
    block.appendChild(h('div', { class: 'build-progress-stall' }, [
      'No file change for ' + formatDuration(p.idle_s) + '. Still running; long thinking passes look like this.'
    ]));
  }
  return block;
}

function buildActionRow(job) {
  var s = job.status;
  var ev = job.evaluation;
  var area = h('div', { class: 'action-area' });

  if (actionError[job.id]) area.appendChild(h('div', { class: 'error-text', text: actionError[job.id] }));

  if (job.jd_changed && ev && s !== 'evaluating' && s !== 'building' && s !== 'queued') {
    area.appendChild(h('div', { class: 'action-pair changed-row' }, [evaluateAgainButton(job, true)]));
  }

  if (s === 'captured') {
    if (job.capture_quality === 'empty') {
      area.appendChild(h('div', { class: 'error-text' }, ['Nothing captured. Wait for the job to finish loading, then click Capture this page again.']));
      return area;
    }
    if (job.capture_quality !== 'ok') {
      area.appendChild(h('div', { class: 'error-text' }, [statusSentence(job)]));
      area.appendChild(h('div', { class: 'action-pair' }, [
        actionButton('skip', 'Skip', 'btn-secondary', job, 'skip', '/jobs/' + job.id + '/skip')
      ]));
      return area;
    }
    // A hard pre-screen hit (no sponsorship, contract, clearance) means an evaluation would
    // only confirm what the JD already says. Skip takes the blue; Evaluate stays available.
    var hardHits = prescreenOf(job).filter(function (p) { return p.hard; });
    if (hardHits.length) {
      area.appendChild(h('div', { class: 'muted primary-note' }, ['Not worth evaluating: ' + hardHits.map(function (p) { return p.label; }).join(', ')]));
    }
    area.appendChild(h('div', { class: 'action-pair' }, [
      actionButton('skip', 'Skip', hardHits.length ? 'primary' : 'btn-secondary', job, 'skip', '/jobs/' + job.id + '/skip'),
      actionButton('play', 'Evaluate', hardHits.length ? 'btn-secondary btn-low' : 'primary', job, 'evaluate', '/jobs/' + job.id + '/evaluate')
    ]));
    area.appendChild(externalRow(job));
    return area;
  }

  if (s === 'evaluating') {
    area.appendChild(workingTimer('Evaluating', job.evaluating_since, 'evaluate'));
    return area;
  }

  if (s === 'scored' || s === 'awaiting') {
    var coverCheck = h('input', { type: 'checkbox', id: 'cover-' + job.id });
    coverCheck.checked = !!getDraft(job.id).coverLetter;
    coverCheck.addEventListener('change', function () { getDraft(job.id).coverLetter = coverCheck.checked; });
    area.appendChild(h('label', { class: 'toggle-row', for: 'cover-' + job.id },
      [coverCheck, h('span', {}, ['Also write a cover letter'])]));
    // The build button's brightness follows the score, in three tiers, so the card itself
    // says how good an idea building is. Under 50 (or a SKIP call) it goes quiet and Skip
    // takes the blue; 50 to 69 is outlined in the accent; 70 and up is the full button.
    var score = ev ? Number(ev.fit_score) : 0;
    var tier = (ev && ev.recommendation === 'SKIP') || score < 50 ? 'low' : (score < 70 ? 'mid' : 'high');
    var buildCls = tier === 'high' ? 'primary' : (tier === 'mid' ? 'btn-secondary btn-mid' : 'btn-secondary btn-low');
    area.appendChild(h('div', { class: 'action-pair tier-' + tier }, [
      actionButton('skip', 'Skip', tier === 'low' ? 'primary' : 'btn-secondary', job, 'skip', '/jobs/' + job.id + '/skip'),
      actionButton('check', 'Approve and build', buildCls, job, 'approve',
        '/jobs/' + job.id + '/approve', function () { return { cover_letter: coverCheck.checked }; })
    ]));
    area.appendChild(externalRow(job));
    return area;
  }

  if (s === 'questions') {
    // The questions block itself carries Submit; only Skip is offered beside it.
    area.appendChild(h('div', { class: 'action-pair' }, [
      actionButton('skip', 'Skip', 'btn-secondary', job, 'skip', '/jobs/' + job.id + '/skip')
    ]));
    area.appendChild(externalRow(job));
    return area;
  }

  if (s === 'building' || s === 'queued') {
    area.appendChild(buildProgressBlock(job));
    if (s === 'building') area.appendChild(workingTimer('Build', job.build_started_at, 'build'));
    return area;
  }

  if (s === 'built') {
    var docs = 1 + (job.cover && job.cover.pdf ? 1 : 0);
    var notes = [];
    if (job.build && job.build.pages && job.build.pages !== 1) {
      notes.push(h('div', { class: 'error-text' }, [job.build.pages + ' pages, not 1']));
    }
    if (job.desktop_files && job.desktop_files.length) {
      notes.push(h('div', { class: 'muted small-note' }, [(docs === 1 ? 'A copy is on your Desktop' : 'Copies are on your Desktop') +
        ' until you mark it submitted or skip it']));
    }
    area.appendChild(documentsRow(job));
    notes.forEach(function (n) { area.appendChild(n); });
    var skipSmall = actionButton('skip', 'Skip', 'btn-icon skip-small', job, 'skip', '/jobs/' + job.id + '/skip');
    skipSmall.querySelector('span:not(.icon)').className = 'sr-only';
    skipSmall.title = 'Skip this job';
    area.appendChild(h('div', { class: 'action-pair submit-row' }, [
      skipSmall,
      actionButton('send', 'Mark submitted', 'primary', job, 'submitted', '/jobs/' + job.id + '/submitted')
    ]));
    area.appendChild(feedbackForm(job));
    return area;
  }

  if (s === 'built_external') {
    area.appendChild(h('div', { class: 'external-path small-note', title: job.external_folder || '' },
      [icon('folder'), ' ', job.external_folder || '']));
    var skipExt = actionButton('skip', 'Skip', 'btn-icon skip-small', job, 'skip', '/jobs/' + job.id + '/skip');
    skipExt.querySelector('span:not(.icon)').className = 'sr-only';
    skipExt.title = 'Skip this job';
    area.appendChild(h('div', { class: 'action-pair submit-row' }, [
      skipExt, actionButton('send', 'Mark submitted', 'primary', job, 'submitted', '/jobs/' + job.id + '/submitted')
    ]));
    return area;
  }

  if (s === 'error' || s === 'needs_login') {
    area.appendChild(h('div', { class: 'error-text' }, [statusSentence(job)]));
    area.appendChild(h('div', { class: 'action-pair' }, [
      actionButton('skip', 'Skip', 'btn-secondary', job, 'skip', '/jobs/' + job.id + '/skip'),
      ev ? actionButton('check', 'Try the build again', 'primary', job, 'approve', '/jobs/' + job.id + '/approve')
         : actionButton('play', 'Evaluate again', 'primary', job, 'evaluate', '/jobs/' + job.id + '/evaluate')
    ]));
    return area;
  }
  if (s === 'applied') {
    // Just submitted, the reach-out question comes first; after that, where the job stands leads.
    var ob = outreachBlock(job), sp = stagePicker(job);
    if (isPending(job)) { if (ob) area.appendChild(ob); area.appendChild(sp); }
    else { area.appendChild(sp); if (ob) area.appendChild(ob); }
    var sc = savedContactsBlock(job);
    if (sc) area.appendChild(sc);
  }
  if ((s === 'applied' || s === 'skipped') && (job.url || job.handoff)) {
    // A finished card's one use is going back to the posting itself. A job in an interview process also has a
    // handoff note the server keeps current (read only; the dashboard has the Copy button).
    var pair = [];
    if (job.url) pair.push(h('a', { class: 'btn-secondary', href: job.url, target: '_blank', rel: 'noopener', 'aria-label': 'Open the posting' },
      [icon('link'), h('span', {}, ['Open the posting'])]));
    if (s === 'applied' && job.handoff) pair.push(h('a', { class: 'btn-secondary', href: SERVER + '/api/jobs/' + encodeURIComponent(job.id) + '/handoff',
      target: '_blank', rel: 'noopener', 'aria-label': 'Open the interview handoff note', title: 'Interview prep note, kept current from your inbox' },
      [icon('eye'), h('span', {}, ['Handoff'])]));
    area.appendChild(h('div', { class: 'action-pair' }, pair));
  }
  return area;
}

// ---------- Built outside jd-intake ----------
// For a job you build by hand (claude.ai, a referral you want to tune): the job keeps its JD,
// sponsorship check and dedupe; only the build happened elsewhere, in a folder you name.
var externalOpen = {};   // jobId -> true while the folder field is showing
function externalRow(job) {
  if (!externalOpen[job.id]) {
    return h('div', { class: 'external-row' }, [h('button', { type: 'button', class: 'link-btn small-note',
      onclick: function () { externalOpen[job.id] = true; render(); } }, ['Built it elsewhere'])]);
  }
  var input = h('input', { type: 'text', class: 'external-input', placeholder: '~/Documents/Resumes/Amazon',
    'aria-label': 'Folder with the resume you built', spellcheck: 'false' });
  input.value = getDraft(job.id).externalFolder || '';
  input.addEventListener('input', function () { getDraft(job.id).externalFolder = input.value; });
  var cancel = h('button', { type: 'button', class: 'btn-secondary',
    onclick: function () { externalOpen[job.id] = false; render(); } }, ['Cancel']);
  var save = actionButton('folder', 'Save folder', 'primary', job, 'built_external',
    '/jobs/' + job.id + '/built_external', function () { return { folder: input.value.trim() }; });
  return h('div', { class: 'external-row open' }, [input, h('div', { class: 'action-pair' }, [cancel, save])]);
}

// ---------- Where an applied job stands ----------
// One select and one note line; Save appears once something changed. The latest note shows under it.
var stageDraft = {};   // job id -> { stage, note } while you edit
function stagePicker(job) {
  var d = stageDraft[job.id] || (stageDraft[job.id] = { stage: job.stage || 'applied', note: '' });
  var sel = h('select', { class: 'stage-select', 'aria-label': 'Where this application stands' },
    [['applied', 'Applied']].concat(Object.keys(STAGE_LABEL).map(function (k) { return [k, STAGE_LABEL[k]]; })).map(function (o) {
      var opt = h('option', { value: o[0] }, [o[1]]);
      if (o[0] === d.stage) opt.selected = true;
      return opt;
    }));
  var note = h('input', { type: 'text', class: 'stage-note', placeholder: 'Note', 'aria-label': 'Note' });
  note.value = d.note;
  var save = h('button', { type: 'button', class: 'primary stage-save' }, [icon('check'), h('span', {}, ['Save'])]);
  function dirty() { return d.stage !== (job.stage || 'applied') || !!d.note.trim(); }
  function sync() { save.hidden = !dirty(); }
  sel.addEventListener('change', function () { d.stage = sel.value; sync(); });
  note.addEventListener('input', function () { d.note = note.value; sync(); });
  note.addEventListener('keydown', function (e) { if (e.key === 'Enter' && dirty()) save.click(); });
  save.disabled = isInFlight(job.id, 'stage');
  save.addEventListener('click', function () {
    setInFlight(job.id, 'stage', true); delete actionError[job.id]; render();
    apiPost('/jobs/' + job.id + '/stage', { stage: d.stage, note: d.note.trim() })
      .then(function () { delete stageDraft[job.id]; setInFlight(job.id, 'stage', false); loadJobs(); })
      .catch(function (err) { setInFlight(job.id, 'stage', false); actionError[job.id] = err.message || String(err); render(); });
  });
  sync();
  return h('div', { class: 'stage-row' }, [
    h('div', { class: 'stage-controls' }, [sel, note, save]),
    job.stage_note ? h('div', { class: 'stage-last' }, [job.stage_note]) : null
  ]);
}

// ---------- Contacts you saved first, offered on the job at their company  ----------
// The server lists, on each open application, the people you saved without a job whose company is this one.
function savedContactsBlock(job) {
  if (!features.outreach) return null;
  var cs = job.contacts || [];
  if (!cs.length) return null;
  var kids = [h('div', { class: 'sc-head' }, ['Saved contacts at ' + (job.company || 'this company')])];
  cs.forEach(function (c) {
    var key = 'attach:' + c.id;
    var btn = h('button', { type: 'button', class: 'btn-secondary', 'data-sc': c.id, 'aria-label': 'Add ' + c.name + ' to this job' }, [
      icon('plus'), h('span', {}, [isInFlight(job.id, key) ? 'Adding' : 'Add to this job'])]);
    btn.disabled = isInFlight(job.id, key);
    btn.addEventListener('click', function () {
      setInFlight(job.id, key, true); delete actionError[job.id]; render();
      apiPost('/api/people/' + encodeURIComponent(c.id) + '/attach', { job_id: job.id })
        .then(function () { setInFlight(job.id, key, false); loadJobs(); })
        .catch(function (err) { setInFlight(job.id, key, false); actionError[job.id] = err.message || String(err); render(); });
    });
    kids.push(h('div', { class: 'sc-row' }, [
      h('div', { class: 'sc-who' }, [h('span', { class: 'sc-name' }, [c.name]), c.title ? h('span', { class: 'sc-title' }, [c.title]) : null]), btn]));
  });
  return h('div', { class: 'saved-contacts' }, kids);
}

// ---------- Outreach, after Mark submitted ----------
// One opt-in per job. Nothing is searched until you press Find people, because each search
// is a paid Apify call. Not now hides the prompt for this panel session; the dashboard still
// offers it on the job's row.
var outreachDismissed = {};
function outreachBlock(job) {
  if (!features.outreach) return null;
  var o = job.outreach || {};
  var state = o.state || 'none';
  var hold = outreachHold(job);
  if (hold && (state === 'none' || state === 'failed')) {
    // No start button: Find people and Try again would both be refused.
    return h('div', { class: 'outreach-row muted' }, [h('span', {}, [hold])]);
  }
  if (state === 'people_review') {
    var np = o.people || 0;
    return h('div', { class: 'outreach-row' }, [
      h('span', {}, [np + (np === 1 ? ' person found. Approve before anything is drafted.' : ' people found. Approve each one before anything is drafted.')]),
      h('button', { type: 'button', class: 'link-btn', onclick: function () { openDashboard('outreach'); } }, ['Review them on the dashboard'])
    ]);
  }
  if (state === 'searching' || state === 'ranking' || state === 'drafting') {
    var label = { searching: 'Searching for people', ranking: 'Choosing who to message', drafting: 'Drafting messages' }[state];
    return h('div', { class: 'outreach-row muted' }, [icon('clock'), h('span', {}, [label + ' at ' + (job.company || 'the company')])]);
  }
  if (state === 'ready') {
    var n = o.people || 0;
    return h('div', { class: 'outreach-row' }, [
      h('span', {}, [n ? n + (n === 1 ? ' person found, drafts waiting for you' : ' people found, drafts waiting for you') : (o.error || 'No one looked worth messaging')]),
      h('button', { type: 'button', class: 'link-btn', onclick: function () { openDashboard('outreach'); } }, ['Open the dashboard'])
    ]);
  }
  if (state === 'failed') {
    return h('div', { class: 'outreach-row' }, [h('div', { class: 'error-text' }, [o.error || 'Finding people failed.']),
      findPeopleForm(job, 'Try again')]);
  }
  if (outreachDismissed[job.id] || job.outreach_decision === 'pass') return null;
  return h('div', { class: 'outreach-prompt' }, [
    h('div', { class: 'outreach-q' }, ['Find people at ' + (job.company || 'this company') + ' to reach out to?']),
    findPeopleForm(job, 'Find people')
  ]);
}
function findPeopleForm(job, label) {
  var kids = [], urlInput = null;
  if (!job.company_url) {
    urlInput = h('input', { type: 'url', class: 'external-input', placeholder: 'linkedin.com/company/name',
      'aria-label': 'Company LinkedIn link', spellcheck: 'false' });
    urlInput.value = getDraft(job.id).companyUrl || '';
    urlInput.addEventListener('input', function () { getDraft(job.id).companyUrl = urlInput.value; });
    kids.push(urlInput);
  }
  var go = h('button', { type: 'button', class: 'primary' }, [icon('send'), h('span', {}, [label])]);
  go.disabled = isInFlight(job.id, 'outreach');
  go.addEventListener('click', function () {
    setInFlight(job.id, 'outreach', true);
    delete actionError[job.id];
    render();
    var first = urlInput ? apiPost('/jobs/' + job.id + '/company_url', { url: urlInput.value.trim() }) : Promise.resolve();
    first.then(function () { return apiPost('/api/jobs/' + job.id + '/outreach', { search_size: 15, keep: 5 }); })
      .then(function () { setInFlight(job.id, 'outreach', false); loadJobs(); })
      .catch(function (err) { setInFlight(job.id, 'outreach', false); actionError[job.id] = err.message || String(err); render(); });
  });
  var buttons = [go];
  if (label === 'Find people') {
    // Your no is saved, so the card leaves Active and the question does not come back.
    buttons.unshift(h('button', { type: 'button', class: 'btn-secondary',
      onclick: function () {
        outreachDismissed[job.id] = true; render();
        apiPost('/jobs/' + job.id + '/outreach_decision', { decision: 'pass' }).then(loadJobs).catch(function (err) {
          delete outreachDismissed[job.id]; actionError[job.id] = err.message || String(err); render();
        });
      } }, ["Don't reach out"]));
  }
  kids.push(h('div', { class: 'action-pair' }, buttons));
  return h('div', { class: 'outreach-form' }, kids);
}

// ---------- Card ----------
function buildCard(job) {
  currentJobId = job.id;
  var isExpanded = job.id === expandedId;
  var header = buildCardHeader(job, isExpanded);

  // Your reading order: decide (or see why you cannot), then the pills, then the reasoning.
  var bodyChildren = [];
  if (job.id === revealedId && revealedSeen) bodyChildren.push(seenBeforeRow(job));
  bodyChildren.push(buildActionRow(job));
  if (job.status === 'questions' || (job.status === 'built' && (job.questions || []).length && !job.revising)) {
    // Open questions stay on a built card: the build went ahead without those claims, and
    // answering now revises the resume in place.
    var qBlock = buildQuestionsBlock(job);
    if (qBlock) bodyChildren.push(qBlock);
  }
  var chips = buildChips(job);
  if (chips) bodyChildren.push(chips);
  bodyChildren.push(buildWhyDetails(job));
  bodyChildren.push(buildAskDetails(job));

  var body = h('div', { class: 'card-body', id: 'body-' + job.id }, bodyChildren);
  return h('div', { class: 'card' + (isExpanded ? '' : ' collapsed') }, [header, body, isExpanded ? submitDock(job, body) : null]);
}

// Working through the form's questions puts you far below the card's Mark submitted. A bar pinned to the bottom of the panel carries it, shown only while the card's own
// button is out of view, so the two are never on screen together.
var dockObserver = null;
function submitDock(job, body) {
  if (job.status !== 'built' && job.status !== 'built_external') return null;
  var main = Array.prototype.find.call(body.querySelectorAll('.action-area button'), function (b) { return /Mark submitted/.test(b.textContent); });
  if (!main) return null;
  var dock = h('div', { class: 'submit-dock', hidden: '' }, [
    h('span', { class: 'submit-dock-text' }, [job.company || '']),
    actionButton('send', 'Mark submitted', 'primary', job, 'submitted', '/jobs/' + job.id + '/submitted')
  ]);
  if (dockObserver) dockObserver.disconnect();
  if (typeof IntersectionObserver === 'function') {
    dockObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { dock.hidden = en.isIntersecting; });
    }, { root: jobsListEl, threshold: 0 });
    dockObserver.observe(main);
  }
  return dock;
}

// A redraw rebuilds the cards, which would throw the cursor out of the question box mid-sentence (a job
// updates every 2 s while one runs). If the box had the cursor, the new one gets it back, same place.
function render() {
  if (cardPress) { renderWaiting = true; return; }          // see "A redraw between pressing and releasing" below
  var a = document.activeElement, keep = null;
  if (a && a.classList && a.classList.contains('ask-input')) {
    keep = { id: a.getAttribute('data-job'), s: a.selectionStart, e: a.selectionEnd };
  }
  renderJobs();
  if (capturedPerson) jobsListEl.insertBefore(personCard(), jobsListEl.firstChild);
  if (!keep) return;
  var box = Array.prototype.find.call(jobsListEl.querySelectorAll('.ask-input'), function (x) { return x.getAttribute('data-job') === keep.id; });
  if (box) { box.focus({ preventScroll: true }); try { box.setSelectionRange(keep.s, keep.e); } catch (e) { /* ignore */ } }
}
function renderJobs() {
  renderFilterRow();
  jobsListEl.innerHTML = '';
  if (!jobs.length) {
    jobsListEl.appendChild(h('div', { class: 'empty-state' }, ['No jobs yet. Open a job posting and click Capture, or right-click a job link.']));
    return;
  }
  var visible = jobs.filter(function (j) {
    return j.id === revealedId ||                       // a just-captured job is always shown
      (inFilter(j, currentFilter) && searchMatches(j));
  });
  if (!visible.length) {
    jobsListEl.appendChild(h('div', { class: 'empty-state' }, [searchQuery
      ? 'Nothing mentions "' + searchInput.value.trim() + '".'
      : currentFilter === 'active' ? 'Nothing needs you right now.' : 'No jobs match this filter.']));
    return;
  }
  if (searchQuery) {
    jobsListEl.appendChild(h('div', { class: 'search-note' }, [
      visible.length + (visible.length === 1 ? ' job mentions "' : ' jobs mention "') + searchInput.value.trim() + '"'
      + (searchIds ? '' : ', searching descriptions')]));
  }
  // Group the list: what needs you first, in the order you would act, then what is running,
  // then what is finished. A heading only appears when the list holds more than one group.
  var buckets = { captured: [], needs: [], working: [], applied: [], skipped: [] };
  visible.forEach(function (job) {
    if (job.id === revealedId) { buckets.captured.push(job); return; }
    var g = jobGroup(job); if (g) buckets[g].push(job);
  });
  buckets.needs.sort(function (a, b) { return needsRank(a) - needsRank(b); });
  var present = GROUP_ORDER.filter(function (g) { return buckets[g].length; });
  present.forEach(function (g) {
    if (present.length > 1) {
      jobsListEl.appendChild(h('div', { class: 'group-head', 'data-group': g }, [
        h('span', {}, [GROUP_LABEL[g]]), h('span', { class: 'group-count' }, [String(buckets[g].length)])
      ]));
    }
    buckets[g].forEach(function (job) { jobsListEl.appendChild(buildCard(job)); });
  });
}

// ---------- Capture button + background messages ----------
captureBtn.addEventListener('click', function () {
  try {
    var p = chrome.runtime.sendMessage({ type: 'capture-active-tab' });
    if (p && p.catch) p.catch(function (e) { showBanner('Could not reach the extension: ' + (e && e.message ? e.message : e) + '. Close and reopen this panel.'); });
  } catch (e) {
    // After the extension is reloaded, an open panel keeps a dead context and every message throws.
    showBanner('The extension was reloaded. Close and reopen this panel.');
  }
});

if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.onMessage) {
  chrome.runtime.onMessage.addListener(function (msg) {
    if (!msg) return;
    if (msg.type === 'job-created') { revealJob(msg.id, msg); }
    else if (msg.type === 'person-created') { showPerson(msg.result); }
    else if (msg.type === 'person-refreshed') personRefreshed(msg);
    else if (msg.type === 'person-refresh-failed') personRefreshFailed(msg);
    else if (msg.type === 'server-down') showBanner('Start the server: python3 server/app.py');
    else if (msg.type === 'capture-error') showBanner(msg.message || 'Capture failed');
  });
}

// ---------- Person capture  ----------
// One eye. On a linkedin.com/in/ page it says so ("Capture this person") and saves the person as a contact: free,
// nothing drafted. The card then asks where they go: onto a job's people list, or contact only. "Draft a note" and
// "Find their email" are separate buttons you press; the second is a paid lookup, so it says what it costs.
var EYE_HTML = captureBtn && captureBtn.querySelector('.icon') ? captureBtn.querySelector('.icon').innerHTML : '';
var onProfile = false;         // the active tab is a LinkedIn profile
function updateCaptureButton() {
  if (!captureBtn) return;
  var label = onProfile ? 'Capture this person' : 'Look at this page';
  captureBtn.setAttribute('aria-label', label);
  captureBtn.title = label + ' (Cmd+Shift+J)';
  var ic = captureBtn.querySelector('.icon');
  if (ic) ic.innerHTML = onProfile ? ICONS.person : EYE_HTML;
}

var capturedPerson = null;     // {data, jobs, tracked, created, pick, chooser, contactOnly, working, note, err}
var personTimer = null, personJson = '', refreshTimer = null;
var FINDER_PRICE = 'about 3 cents when it finds one, nothing when it does not';

function personKeep() { try { chrome.storage.session.remove(['lastPerson', 'lastPersonAt']); } catch (e) { /* tests */ } }

function showPerson(result) {
  if (!result || !result.person) return;
  if (liMode) setLiMode(false);
  clearBanner();
  var jobsHere = result.jobs || [];
  var first = jobsHere.filter(function (j) { return j.match; })[0];     // the best job: their company page, then their company's name
  capturedPerson = { data: result, jobs: jobsHere, tracked: result.tracked || [], created: result.created !== false,
    pick: first ? first.id : '', chooser: undefined, contactOnly: false, working: null, note: '', err: '' };
  render();
  if (result.busy) startPersonPoll();
}

function applyPerson(out) {
  if (!capturedPerson || !out || !out.person) return;
  capturedPerson.data = out;
  capturedPerson.err = '';
  if (out.busy) startPersonPoll(); else stopPersonPoll();
  render();
}
function stopPersonPoll() { clearTimeout(personTimer); personTimer = null; }
function startPersonPoll() {
  stopPersonPoll();
  personTimer = setTimeout(function pollPerson() {
    if (!capturedPerson) return;
    apiGet('/api/people/' + encodeURIComponent(capturedPerson.data.person.id)).then(function (out) {
      var json = JSON.stringify(out);
      if (json !== personJson) { personJson = json; applyPerson(out); }
      if (out.busy) personTimer = setTimeout(pollPerson, 3000); else stopPersonPoll();
    }).catch(function () { personTimer = setTimeout(pollPerson, 6000); });
  }, 3000);
}

function personAct(path, body, busyLabel) {
  var cp = capturedPerson;
  if (!cp) return Promise.resolve();
  cp.err = ''; cp.note = ''; cp.working = busyLabel; render();
  return apiPost('/api/people/' + encodeURIComponent(cp.data.person.id) + path, body || {}).then(function (out) {
    if (capturedPerson) { capturedPerson.working = null; }
    if (out && out.person) applyPerson(out); else render();
    return out;
  }, function (e) {
    if (capturedPerson) { capturedPerson.working = null; capturedPerson.err = e.message || 'Could not reach the server.'; render(); }
  });
}

// "Refresh from profile": read the profile open in the active tab again. It has to be this person's own profile; the
// background script reads the page and the server runs the one model call, then answers with person-refreshed.
function personRefresh() {
  var cp = capturedPerson;
  if (!cp) return;
  var p = cp.data.person;
  cp.err = ''; cp.note = '';
  function fail(msg) { clearTimeout(refreshTimer); if (capturedPerson) { capturedPerson.working = null; capturedPerson.err = msg; render(); } }
  try {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      var here = liSlug(tabs && tabs[0] && tabs[0].url);
      if (!here || here !== liSlug(p.linkedin_url)) { fail('Open ' + (p.name || 'their') + "'s profile first"); return; }
      cp.working = 'Refreshing'; render();
      clearTimeout(refreshTimer);
      refreshTimer = setTimeout(function () { fail('The profile read took too long. Try again.'); }, 150000);
      try {
        var sent = chrome.runtime.sendMessage({ type: 'refresh-person', person_id: p.id, linkedin_url: p.linkedin_url, name: p.name });
        if (sent && sent.catch) sent.catch(function () { fail('Could not reach the extension. Close and reopen this panel.'); });
      } catch (e) { fail('The extension was reloaded. Close and reopen this panel.'); }
    });
  } catch (e) { fail('Open ' + (p.name || 'their') + "'s profile first"); }
}

function personRefreshed(msg) {
  var cp = capturedPerson;
  if (!cp || !msg || !msg.result || !msg.result.person || msg.result.person.id !== cp.data.person.id) return;
  clearTimeout(refreshTimer);
  var r = msg.result, jobsHere = r.jobs || cp.jobs;
  var best = jobsHere.filter(function (j) { return j.match; })[0];
  cp.data = r; cp.jobs = jobsHere; cp.working = null; cp.err = '';
  if (!cp.data.person.job_id) { cp.pick = best ? best.id : ''; cp.chooser = undefined; }
  var got = [r.person.title, r.person.company].filter(Boolean);
  cp.note = got.length ? 'Read again: ' + got.join(' at ') + '.' : 'Read again, but no title or company was found on the page.';
  if (r.read === 'page') cp.note += ' The model could not be reached, so the page was read with its own rules.';
  render();
}
function personRefreshFailed(msg) {
  var cp = capturedPerson;
  if (!cp || (msg.person_id && msg.person_id !== cp.data.person.id)) return;
  clearTimeout(refreshTimer);
  cp.working = null; cp.err = msg.message || 'Could not read the profile.';
  render();
}

function initialsOf(name) {
  var w = String(name || '').split(',')[0].replace(/\(.*?\)/g, '').trim().split(/\s+/).filter(Boolean);
  if (!w.length) return '?';
  return (w[0].charAt(0) + (w.length > 1 ? w[w.length - 1].charAt(0) : '')).toUpperCase();
}
function jobLabel(j) { return [j.company, j.title].filter(Boolean).join(', '); }

// A button on the person card. Every one carries data-pc: a single click listener on the panel's list (below) finds it
// and acts on the CURRENT card state, so a button can never run a handler bound to a card that has been redrawn.
function pcBtn(act, cls, iconName, label, extra) {
  var attrs = { type: 'button', class: cls, 'data-pc': act };
  for (var k in (extra || {})) attrs[k] = extra[k];
  return h('button', attrs, [iconName ? icon(iconName) : null, h('span', { class: 'pc-label' }, [label])]);
}

function pcJobRow(j, selected) {
  var tag = j.stage ? (STAGE_LABEL[j.stage] || '') : '';
  return h('button', { type: 'button', class: 'pc-job' + (selected ? ' sel' : ''), role: 'radio', 'aria-checked': selected ? 'true' : 'false',
    'data-pc': 'pick', 'data-job': j.id }, [
    h('span', { class: 'pc-radio', 'aria-hidden': 'true' }, []),
    h('span', { class: 'pc-job-text' }, [h('span', { class: 'pc-job-co' }, [j.company || 'Unnamed']), h('span', { class: 'pc-job-title' }, [j.title || ''])]),
    tag ? h('span', { class: 'pc-tag' + (j.hold ? ' warn' : '') }, [tag]) : null
  ]);
}

function personCard() {
  var cp = capturedPerson, d = cp.data, p = d.person, att = d.job, msgs = d.messages || [];
  var live = msgs.filter(function (m) { return m.status !== 'skipped'; });
  var draft = live[0];
  var busy = d.busy && d.busy.what;
  var kids = [];

  // Who: initials, name, title, company and place.
  var sub = p.title || p.headline;
  var where = [p.company, p.location].filter(Boolean).join(' · ');
  kids.push(h('div', { class: 'pc-head' }, [
    h('div', { class: 'pc-avatar', 'aria-hidden': 'true' }, [initialsOf(p.name)]),
    h('div', { class: 'pc-id' }, [
      h('div', { class: 'pc-name' }, [p.name || 'Unnamed']),
      sub ? h('div', { class: 'pc-title' }, [sub]) : null,
      where ? h('div', { class: 'pc-where' }, [where]) : null
    ]),
    h('button', { type: 'button', class: 'pc-x', 'data-pc': 'dismiss', 'aria-label': 'Dismiss', title: 'Dismiss' }, [icon('x')])
  ]));
  if (!sub && !p.company) kids.push(h('div', { class: 'pc-note warn' }, ["Their title and company were not read from the page."]));
  kids.push(pcBtn('refresh', 'pc-ghost', 'refresh', cp.working === 'Refreshing' ? 'Reading the profile' : 'Refresh from profile',
    cp.working ? { disabled: 'disabled' } : {}));
  if (cp.note) kids.push(h('div', { class: 'pc-note', role: 'status' }, [cp.note]));

  // Where this profile already is.
  var onList = cp.tracked.filter(function (t) { return t.job; })[0];
  if (!cp.created && onList) {
    kids.push(h('div', { class: 'pc-status warn' }, [
      'Already tracked: on the ' + onList.job.company + ', ' + onList.job.title + ' list (' + (onList.status === 'proposed' ? 'waiting for your approval' : onList.status) + '). ',
      pcBtn('open-tracked', 'link-btn', null, 'Open')]));
  } else if (!cp.created && !p.job_id) {
    kids.push(h('div', { class: 'pc-status' }, ['Already saved as a contact.']));
  }

  if (!p.job_id && !cp.contactOnly) {
    // Which job: the best match is the one primary button; the rest are one click away, in a list of rows.
    var matches = cp.jobs.filter(function (j) { return j.match; }), others = cp.jobs.filter(function (j) { return !j.match; });
    var picked = cp.jobs.filter(function (j) { return j.id === cp.pick; })[0];
    var adding = cp.working === 'Adding';
    kids.push(pcBtn('attach', 'primary pc-primary', 'plus', adding ? 'Adding' : (picked ? 'Add to ' + jobLabel(picked) : 'Add to a job'),
      !picked || cp.working ? { disabled: 'disabled' } : {}));
    if (picked && picked.reason && picked.match) kids.push(h('div', { class: 'pc-note' }, [picked.reason + '.']));
    if (picked && picked.hold) kids.push(h('div', { class: 'pc-note warn' }, ['You are in their process, so no note can be drafted for this job. Adding them is fine.']));
    if (!matches.length) {
      kids.push(h('div', { class: 'pc-note' }, ['No open application at ' + (p.company || 'their company') + '. ',
        pcBtn('add-job', 'link-btn', null, 'Add a job')]));
    }
    var open = cp.chooser === undefined ? !cp.pick : cp.chooser;
    if (cp.jobs.length) {
      kids.push(pcBtn('choose', 'pc-ghost', open ? 'chevron-up' : 'chevron', open ? 'Hide the job list' : 'Choose another job', { 'aria-expanded': open ? 'true' : 'false' }));
    }
    if (open && cp.jobs.length) {
      var list = [];
      if (matches.length) { list.push(h('div', { class: 'pc-group' }, ['At ' + (p.company || 'their company')])); matches.forEach(function (j) { list.push(pcJobRow(j, j.id === cp.pick)); }); }
      if (others.length) { list.push(h('div', { class: 'pc-group' }, [matches.length ? 'Other open applications' : 'Open applications'])); others.forEach(function (j) { list.push(pcJobRow(j, j.id === cp.pick)); }); }
      kids.push(h('div', { class: 'pc-jobs', role: 'radiogroup', 'aria-label': 'Add ' + (p.name || 'this person') + ' to which job' }, list));
    }
    kids.push(cp.created ? pcBtn('save', 'btn-secondary pc-second', 'bookmark', 'Save as contact')
                         : (!live.length && p.manual ? pcBtn('remove', 'btn-secondary pc-second', 'trash', cp.working === 'Removing' ? 'Removing' : 'Remove', cp.working ? { disabled: 'disabled' } : {}) : null));
  } else if (!p.job_id) {
    kids.push(h('div', { class: 'pc-status ok' }, [icon('check'), h('span', {}, ['Saved as a contact. Nothing was drafted or paid for.'])]));
    var pair = [pcBtn('add', 'btn-secondary', 'plus', 'Add to a job')];
    if (!live.length && p.manual) pair.push(pcBtn('remove', 'btn-secondary pc-danger', 'trash', cp.working === 'Removing' ? 'Removing' : 'Remove', cp.working ? { disabled: 'disabled' } : {}));
    kids.push(h('div', { class: 'action-pair pc-pair' }, pair));
  } else if (att) {
    kids.push(h('div', { class: 'pc-status ok' }, [icon('check'), h('span', {}, ['On the ' + att.company + ', ' + att.title + ' list.'])]));
    if (att.hold) kids.push(h('div', { class: 'pc-note warn' }, [att.hold.charAt(0).toUpperCase() + att.hold.slice(1) + '. A note can be drafted once that changes.']));
  }

  // Draft a note: your click, one note for one person.
  var hold = att && att.hold;
  var actions = [];
  if (busy === 'draft' || cp.working === 'Drafting') {
    actions.push(h('button', { type: 'button', class: 'primary', disabled: 'disabled' }, [icon('pen'), h('span', {}, ['Drafting'])]));
    actions.push(workingTimer('', d.busy && d.busy.since, null));
  } else if (draft && draft.status === 'sent') {
    actions.push(h('button', { type: 'button', class: 'btn-secondary', disabled: 'disabled' }, [icon('check'), h('span', {}, [draft.channel === 'linkedin' ? 'Note sent' : 'Email sent'])]));
  } else if (draft && draft.status !== 'drafting') {
    var isLi = draft.channel === 'linkedin';
    actions.push(pcBtn(isLi ? 'open-notes' : 'open-dashboard', 'primary', 'pen', isLi ? 'Note ready, open LinkedIn notes' : 'Email ready, open the dashboard'));
  } else {
    actions.push(pcBtn('draft', 'primary', 'pen', 'Draft a note', !att || hold || cp.working ? { disabled: 'disabled' } : {}));
    if (!att) actions.push(h('div', { class: 'pc-hint' }, ['Add this person to a job first; the note is written for that application.']));
  }
  kids.push(h('div', { class: 'pc-actions' }, actions));

  // Find their email: a paid lookup, so a button of its own with its price.
  var emailNodes = [];
  if (p.email) {
    emailNodes.push(h('div', { class: 'pc-email' }, [icon('at'), h('span', { class: 'mono' }, [p.email])]));
  } else if (busy === 'email' || cp.working === 'Looking') {
    emailNodes.push(h('button', { type: 'button', class: 'btn-secondary', disabled: 'disabled' }, [icon('at'), h('span', {}, ['Looking for an email'])]));
    emailNodes.push(workingTimer('', d.busy && d.busy.since, null));
  } else {
    var again = p.email_source === 'not_found';
    emailNodes.push(h('button', { type: 'button', class: 'btn-secondary pc-email-btn', 'data-pc': 'email', 'data-again': again ? '1' : '',
      disabled: cp.working ? 'disabled' : null, 'aria-label': (again ? 'Look again' : 'Find their email') + ', a paid lookup, ' + FINDER_PRICE }, [
      icon('at'), h('span', { class: 'pc-label' }, [again ? 'Look again' : 'Find their email']), h('span', { class: 'pc-price' }, ['about 3 cents'])]));
    emailNodes.push(h('div', { class: 'pc-hint' }, [(again ? 'No email was found last time. ' : '') + 'A paid lookup: ' + FINDER_PRICE + '.']));
  }
  kids.push(h('div', { class: 'pc-actions' }, emailNodes));

  var err = cp.err || d.error;
  if (err) kids.push(h('div', { class: 'error-text', role: 'alert' }, [err]));
  return h('section', { class: 'person-card', 'aria-label': 'Captured person: ' + (p.name || '') }, kids);
}

// One listener for every button on the card. It reads capturedPerson now, never a value captured when the card was
// drawn, so a redraw cannot leave a button wired to a card that is gone.
function personClick(act, el) {
  var cp = capturedPerson;
  if (!cp) return;
  var p = cp.data.person;
  if (act === 'dismiss') { stopPersonPoll(); capturedPerson = null; personKeep(); render(); }
  else if (act === 'refresh') personRefresh();
  else if (act === 'attach') { if (cp.pick) personAct('/attach', { job_id: cp.pick }, 'Adding'); }
  else if (act === 'choose') { cp.chooser = !(cp.chooser === undefined ? !cp.pick : cp.chooser); render(); }
  else if (act === 'pick') { cp.pick = el.getAttribute('data-job') || ''; cp.chooser = false; render(); }
  else if (act === 'save') { cp.contactOnly = true; render(); }
  else if (act === 'add') { cp.contactOnly = false; cp.chooser = undefined; render(); }
  else if (act === 'remove') {
    personAct('/forget', {}, 'Removing').then(function (o) { if (o && o.removed) { stopPersonPoll(); capturedPerson = null; personKeep(); render(); } });
  }
  else if (act === 'draft') personAct('/draft', {}, 'Drafting');
  else if (act === 'email') personAct('/find_email', el.getAttribute('data-again') ? { again: true } : {}, 'Looking');
  else if (act === 'open-notes') setLiMode(true);
  else if (act === 'open-dashboard' || act === 'open-tracked') openDashboard('outreach');
  else if (act === 'add-job') openDashboard('jobs?add=' + encodeURIComponent(p.company || '') + (p.company_url ? '&li=' + encodeURIComponent(p.company_url) : ''));
}
jobsListEl.addEventListener('click', function (e) {
  var t = e.target && e.target.closest ? e.target.closest('[data-pc]') : null;
  if (!t || !jobsListEl.contains(t) || t.disabled) return;
  personClick(t.getAttribute('data-pc'), t);
});

// A redraw between pressing and releasing the mouse eats the click: the release lands on a new node. Chrome only fires
// a click when both ends are on the same element. While a press that began on the card is down, a redraw waits.
var cardPress = false, renderWaiting = false, pressTimer = null;
jobsListEl.addEventListener('pointerdown', function (e) {
  cardPress = !!(e.target && e.target.closest && e.target.closest('.person-card'));
  clearTimeout(pressTimer);
});
function releaseCardPress() {
  if (!cardPress) return;
  clearTimeout(pressTimer);
  pressTimer = setTimeout(function () { cardPress = false; if (renderWaiting) { renderWaiting = false; render(); } }, 80);
}
document.addEventListener('pointerup', releaseCardPress);
document.addEventListener('pointercancel', releaseCardPress);

// ---------- LinkedIn mode ----------
// Every connection note waiting on you, grouped by job, and anyone still waiting for your yes.
// Clicking a name copies that person's note and opens their profile in this same tab, so the
// loop is: name, Connect, Add a note, paste, Send, then Sent here and on to the next name.
// Software never sends anything on LinkedIn; you do (account risk).
var liBtn = document.getElementById('li-btn');
var liCount = document.getElementById('li-count');
var liView = document.getElementById('li-view');
var liMode = false;
var liData = { linkedin: [], people: [] };
var liLoaded = false, liDown = false;
var liEdits = {};      // message id -> your edited note
var liBusy = {};       // message or person id -> request in flight
var liErr = {};
var liCopied = null;   // message id whose note is on the clipboard right now
var liCurrent = '';    // profile open in the active tab, as a lowercase /in/ slug
var liTimer = null, liLastJson = '', liStale = false, liFocusNext = null;

function liSlug(url) {
  var m = /linkedin\.com\/in\/([^/?#]+)/i.exec(url || '');
  if (!m) return '';
  try { return decodeURIComponent(m[1]).toLowerCase(); } catch (e) { return m[1].toLowerCase(); }
}
function liText(m) { return liEdits[m.id] !== undefined ? liEdits[m.id] : (m.draft || ''); }

function setLiMode(on) {
  liMode = !!on;
  liBtn.setAttribute('aria-pressed', liMode ? 'true' : 'false');
  jobsListEl.hidden = liMode || onboarded === false;
  liView.hidden = !liMode;
  searchInput.placeholder = liMode ? 'Search names' : 'Search';
  try { chrome.storage.session.set({ liMode: liMode }); } catch (e) { /* tests */ }
  if (liMode) { renderLinkedin(); loadLinkedin(); readActiveTab(); }
  else { clearTimeout(liTimer); render(); }
}
if (liBtn) liBtn.addEventListener('click', function () { setLiMode(!liMode); });

function loadLinkedin(force) {
  clearTimeout(liTimer);
  return apiGet('/api/queue').then(function (q) {
    liDown = false;
    var data = { linkedin: q.linkedin || [], people: q.people || [] };
    var json = JSON.stringify(data);
    if (json !== liLastJson || !liLoaded || force) { liLastJson = json; liData = data; liLoaded = true; renderLinkedin(force); }
  }).catch(function () { liDown = true; renderLinkedin(); }).then(function () {
    if (liMode) liTimer = setTimeout(loadLinkedin, 15000);
  });
}

// Which profile is open, so its row can say so. Only the active tab of this window counts.
function readActiveTab() {
  try {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      var slug = liSlug(tabs && tabs[0] && tabs[0].url);
      if (!!slug !== onProfile) { onProfile = !!slug; updateCaptureButton(); }
      if (slug !== liCurrent) {
        liCurrent = slug;
        if (liMode) {
          renderLinkedin();
          // A new profile: bring its pinned row into view rather than leaving you where the last one was.
          var top = liView && liView.querySelector('[data-group="here"]');
          if (top && top.scrollIntoView) top.scrollIntoView({ block: 'nearest' });
        }
      }
    });
  } catch (e) { /* no tabs API in tests */ }
}
try {
  chrome.tabs.onActivated.addListener(readActiveTab);
  chrome.tabs.onUpdated.addListener(function (id, info, tab) { if (info.url && tab.active) readActiveTab(); });
} catch (e) { /* tests */ }

function liOpen(url) {
  try {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      if (tabs && tabs[0]) chrome.tabs.update(tabs[0].id, { url: url });
      else chrome.tabs.create({ url: url });
    });
  } catch (e) { /* tests */ }
}
function liCopy(m) {
  try { navigator.clipboard.writeText(liText(m)).catch(function () {}); } catch (e) { /* tests */ }
  liCopied = m.id;
  setTimeout(function () { if (liCopied === m.id) { liCopied = null; renderLinkedin(); } }, 1600);
}

function liPost(id, path, body, after) {
  liBusy[id] = true; delete liErr[id]; renderLinkedin();
  return apiPost(path, body).then(function () {
    delete liBusy[id];
    if (after) after();
    pollBell();
    return loadLinkedin(true);     // your own click: redraw even if a note box still has focus
  }, function (e) { delete liBusy[id]; liErr[id] = e.message || 'Could not reach the server.'; renderLinkedin(); });
}

function liNoteRow(m, nextId) {
  var p = m.person || {};
  var here = !!liCurrent && liSlug(p.linkedin_url) === liCurrent;
  var busy = !!liBusy[m.id];
  var count = h('span', { class: 'li-chars' }, [liText(m).length + ' characters']);
  // Tall enough for the whole note at panel width (about 46 characters a line), so nothing hides.
  var area = h('textarea', { class: 'li-note', rows: String(Math.max(3, Math.ceil(liText(m).length / 46) + 1)), 'aria-label': 'Note to ' + (p.name || 'this person'),
    oninput: function (e) { liEdits[m.id] = e.target.value; count.textContent = e.target.value.length + ' characters'; },
    onblur: function () { if (liStale) setTimeout(renderLinkedin, 0); } });
  area.value = liText(m);
  var name = h('button', { type: 'button', class: 'li-name', 'data-mid': m.id,
    title: p.linkedin_url ? 'Copy the note and open the profile in this tab' : 'No profile link',
    onclick: function () { liCopy(m); if (p.linkedin_url) liOpen(p.linkedin_url); renderLinkedin(); } }, [p.name || 'Unnamed']);
  if (!p.linkedin_url) name.disabled = true;
  var copied = liCopied === m.id;
  return h('div', { class: 'li-row' + (here ? ' here' : ''), 'data-mid': m.id }, [
    h('div', { class: 'li-who' }, [name, here ? h('span', { class: 'li-here' }, ['Open in this tab']) : null]),
    p.title ? h('div', { class: 'li-title' }, [p.title]) : null,
    area,
    h('div', { class: 'li-actions' }, [
      h('button', { type: 'button', class: 'li-copy', onclick: function () { liCopy(m); renderLinkedin(); } },
        [icon(copied ? 'check' : 'copy'), h('span', {}, [copied ? 'Copied' : 'Copy'])]),
      count,
      h('button', { type: 'button', class: 'primary li-sent', disabled: busy ? 'disabled' : null,
        onclick: function () {
          var edited = liEdits[m.id] !== undefined && liEdits[m.id] !== (m.draft || '');
          liPost(m.id, '/api/messages/' + encodeURIComponent(m.id) + '/linkedin_sent', edited ? { text: liEdits[m.id] } : {},
            function () { delete liEdits[m.id]; liFocusNext = nextId; });
        } }, [icon('check'), h('span', {}, [busy ? 'Saving' : 'Sent'])]),
      h('button', { type: 'button', class: 'li-skip', disabled: busy ? 'disabled' : null,
        onclick: function () {
          liPost(m.id, '/api/messages/' + encodeURIComponent(m.id) + '/skip', {}, function () { delete liEdits[m.id]; liFocusNext = nextId; });
        } }, ['Skip'])
    ]),
    liErr[m.id] ? h('div', { class: 'li-err' }, [liErr[m.id]]) : null
  ]);
}

function liPersonRow(x) {
  var busy = !!liBusy[x.id];
  var j = x.job || {};
  var name = h('button', { type: 'button', class: 'li-name', title: 'Open the profile in this tab',
    onclick: function () { if (x.linkedin_url) liOpen(x.linkedin_url); } }, [x.name || 'Unnamed']);
  if (!x.linkedin_url) name.disabled = true;
  return h('div', { class: 'li-row person' + (liCurrent && liSlug(x.linkedin_url) === liCurrent ? ' here' : '') }, [
    h('div', { class: 'li-who' }, [name]),
    h('div', { class: 'li-title' }, [[x.title, j.company].filter(Boolean).join(', ')]),
    x.why ? h('div', { class: 'li-why' }, [x.why]) : null,
    h('div', { class: 'li-actions' }, [
      h('button', { type: 'button', class: 'primary', disabled: busy ? 'disabled' : null,
        onclick: function () { liPost(x.id, '/api/people/' + encodeURIComponent(x.id) + '/decide', { decision: 'approve' }); } },
        [icon('check'), h('span', {}, ['Approve'])]),
      h('button', { type: 'button', disabled: busy ? 'disabled' : null,
        onclick: function () { liPost(x.id, '/api/people/' + encodeURIComponent(x.id) + '/decide', { decision: 'reject' }); } }, ['Skip'])
    ]),
    liErr[x.id] ? h('div', { class: 'li-err' }, [liErr[x.id]]) : null
  ]);
}

function renderLinkedin(force) {
  if (!liView || !liMode) return;
  // A poll must not pull the caret out of a note you are typing; it redraws when you leave the box.
  // Your edits live in liEdits, so a forced redraw after your own click loses nothing.
  var a = document.activeElement;
  if (!force && a && a.tagName === 'TEXTAREA' && liView.contains(a)) { liStale = true; return; }
  liStale = false;
  liView.innerHTML = '';
  var q = (searchInput.value || '').trim().toLowerCase();
  function hit(name, job) { return !q || [name, (job || {}).company, (job || {}).title].join(' ').toLowerCase().indexOf(q) !== -1; }
  var people = liData.people.filter(function (x) { return hit(x.name, x.job); });
  var notes = liData.linkedin.filter(function (m) { return hit((m.person || {}).name, m.job); });
  if (!liLoaded) { liView.appendChild(h('div', { class: 'empty-state' }, [liDown ? 'Cannot reach the server.' : 'Loading'])); return; }
  if (!people.length && !notes.length) {
    liView.appendChild(h('div', { class: 'empty-state' }, [q ? 'No one matches "' + searchInput.value.trim() + '".' : 'No LinkedIn notes waiting.']));
    return;
  }
  // The person whose profile is open in this tab goes first, in a group of its own (on a profile, the
  // People tab should show that person without hunting for them). Search still applies.
  function isHere(url) { return !!liCurrent && liSlug(url) === liCurrent; }
  var hereP = people.filter(function (x) { return isHere(x.linkedin_url); });
  var hereN = notes.filter(function (m) { return isHere((m.person || {}).linkedin_url); });
  if (hereP.length || hereN.length) {
    liView.appendChild(h('div', { class: 'group-head', 'data-group': 'here' }, [h('span', {}, ['On this profile'])]));
    hereP.forEach(function (x) { liView.appendChild(liPersonRow(x)); });
    hereN.forEach(function (m) { liView.appendChild(liNoteRow(m, null)); });
    people = people.filter(function (x) { return hereP.indexOf(x) === -1; });
    notes = notes.filter(function (m) { return hereN.indexOf(m) === -1; });
  }
  if (people.length) {
    liView.appendChild(h('div', { class: 'group-head', 'data-group': 'needs' }, [h('span', {}, ['People to approve']), h('span', { class: 'group-count' }, [String(people.length)])]));
    people.forEach(function (x) { liView.appendChild(liPersonRow(x)); });
  }
  var groups = {}, order = [];
  notes.forEach(function (m) {
    var k = (m.job || {}).id || 'none';
    if (!groups[k]) { groups[k] = []; order.push(k); }
    groups[k].push(m);
  });
  var flat = [];
  order.forEach(function (k) { flat = flat.concat(groups[k]); });
  order.forEach(function (k) {
    var j = groups[k][0].job || {};
    liView.appendChild(h('div', { class: 'group-head li-job' }, [
      h('span', {}, [[j.company, j.title].filter(Boolean).join(', ') || 'Notes']), h('span', { class: 'group-count' }, [String(groups[k].length)])]));
    groups[k].forEach(function (m) {
      var i = flat.indexOf(m), next = flat[i + 1] || flat[i - 1];
      liView.appendChild(liNoteRow(m, next ? next.id : null));
    });
  });
  if (liFocusNext) {
    var btn = liView.querySelector('.li-name[data-mid="' + liFocusNext.replace(/"/g, '\\"') + '"]');
    liFocusNext = null;
    if (btn) { btn.focus(); if (btn.scrollIntoView) btn.scrollIntoView({ block: 'nearest' }); }
  }
}

// ---------- Init ----------
// Reflect any capture result that landed in storage before the panel was open.
if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.session) {
  chrome.storage.session.get(['lastEvent', 'lastJobId', 'lastPerson', 'lastPersonAt']).then(function (data) {
    // A person captured while the panel was shut: shown if it was in the last half hour.
    if (data.lastPerson && data.lastPersonAt && Date.now() - data.lastPersonAt < 30 * 60 * 1000) showPerson(data.lastPerson);
    if (data.lastEvent && data.lastEvent.type === 'server-down') showBanner('Start the server: python3 server/app.py');
    else if (data.lastEvent && data.lastEvent.type === 'capture-error') showBanner(data.lastEvent.message || 'Capture failed');
    if (data.lastJobId) expandedId = data.lastJobId;
  }).catch(function () {});
  chrome.storage.session.get(['liMode']).then(function (d) { if (d.liMode) setLiMode(true); }).catch(function () {});
}

readActiveTab();
showServerField();
loadServerSetting().then(function () {
  loadProfileStatus();
  loadSettings();
  loadJobs();
  pollHealth();
  pollStats();
});
setInterval(pollHealth, 10000);

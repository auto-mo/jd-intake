// JD Intake background service worker.
// Default server address. The side panel's Settings sheet can override it (chrome.storage.local,
// key serverUrl). A custom host or port also needs manifest.json host_permissions edited to match.
var DEFAULT_SERVER = 'http://127.0.0.1:8790';
var SERVER = DEFAULT_SERVER;
function normalizeServer(v) {
  v = String(v || '').trim().replace(/\/+$/, '');
  return /^https?:\/\/[^\s\/]+$/i.test(v) ? v : '';
}
function loadServer() {
  return chrome.storage.local.get('serverUrl').then(function (d) {
    SERVER = normalizeServer(d && d.serverUrl) || DEFAULT_SERVER;
  }).catch(function () {});
}
loadServer();
chrome.storage.onChanged.addListener(function (changes, area) {
  if (area === 'local' && changes.serverUrl) {
    SERVER = normalizeServer(changes.serverUrl.newValue) || DEFAULT_SERVER;
    refreshBadge();
  }
});
var TAB_LOAD_TIMEOUT_MS = 20000;

chrome.runtime.onInstalled.addListener(function () {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(function () {});
  chrome.contextMenus.create({ id: 'jd-intake-evaluate-link', title: 'Evaluate this job link', contexts: ['link'] });
  chrome.contextMenus.create({ id: 'jd-intake-capture-page', title: 'Capture this job page', contexts: ['page', 'action'] });
});

// The count of items waiting on you, on the toolbar icon, so it shows with the panel shut.
function refreshBadge() {
  fetch(SERVER + '/notifications').then(function (r) { return r.json(); }).then(function (n) {
    var t = (n && n.total) || 0;
    chrome.action.setBadgeText({ text: t ? (t > 99 ? '99+' : String(t)) : '' });
    chrome.action.setBadgeBackgroundColor({ color: '#1F6FE5' });
  }).catch(function () { chrome.action.setBadgeText({ text: '' }); });
}
chrome.alarms.create('outreach-badge', { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(function (a) { if (a.name === 'outreach-badge') refreshBadge(); });
chrome.runtime.onStartup.addListener(refreshBadge);
loadServer().then(refreshBadge);

function activeTab(cb) {
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    if (tabs && tabs[0]) cb(tabs[0]);
  });
}

chrome.commands.onCommand.addListener(function (command) {
  if (command === 'capture-job') activeTab(function (t) { captureActiveTab(t.id, t.windowId); });
});

chrome.contextMenus.onClicked.addListener(function (info, tab) {
  if (info.menuItemId === 'jd-intake-capture-page' && tab) captureActiveTab(tab.id, tab.windowId);
  else if (info.menuItemId === 'jd-intake-evaluate-link' && info.linkUrl && tab) captureLinkInBackgroundTab(info.linkUrl, tab.windowId);
});

chrome.runtime.onMessage.addListener(function (msg) {
  if (msg && msg.type === 'capture-active-tab') activeTab(function (t) { captureActiveTab(t.id, t.windowId); });
  else if (msg && msg.type === 'refresh-person') activeTab(function (t) { refreshPerson(msg.person_id, msg.linkedin_url, msg.name, t); });
  return false;
});

// Resolves once the tab finishes loading (or rejects after timeoutMs).
function waitForTabComplete(tabId, timeoutMs) {
  return new Promise(function (resolve, reject) {
    var settled = false;
    var timer = setTimeout(function () { finish(false); reject(new Error('Timed out waiting for page load')); }, timeoutMs);

    function finish(ok) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listener);
      if (ok) resolve();
    }
    function listener(updatedTabId, changeInfo) {
      if (updatedTabId === tabId && changeInfo.status === 'complete') finish(true);
    }

    chrome.tabs.get(tabId, function (tab) {
      if (chrome.runtime.lastError) return;
      if (tab && tab.status === 'complete') finish(true);
      else chrome.tabs.onUpdated.addListener(listener);
    });
  });
}

function sendExtractMessage(tabId) {
  return new Promise(function (resolve, reject) {
    chrome.tabs.sendMessage(tabId, { type: 'extract' }, function (response) {
      if (chrome.runtime.lastError || !response) reject(chrome.runtime.lastError || new Error('No response from content script'));
      else resolve(response);
    });
  });
}

// Content scripts are not pre-injected on every host, so try messaging first
// and fall back to an on-demand injection (guarded by window.__jdIntakeLoaded).
function extractOnce(tabId) {
  return sendExtractMessage(tabId).catch(function () {
    return chrome.scripting.executeScript({ target: { tabId: tabId }, files: ['content.js'] })
      .then(function () { return sendExtractMessage(tabId); });
  });
}

// LinkedIn and Workday fill the description after the page reports "complete", so an empty or
// short capture is retried a few times before giving up.
// The job the URL names: /jobs/view/<id> or the search view's currentJobId.
function urlJobId(url) {
  var m = String(url || '').match(/\/jobs\/view\/(?:[^\/?#]*?-)?(\d+)/) || String(url || '').match(/currentJobId=(\d+)/);
  return m ? m[1] : '';
}

function ensureContentScriptAndExtract(tabId, attempt) {
  attempt = attempt || 1;
  return extractOnce(tabId).then(function (job) {
    // A LinkedIn profile is a person, not a job: no description to wait for, only a name that may not have painted yet.
    if (job && job.kind === 'person') {
      if (job.name || attempt >= 4) return job;
      return new Promise(function (resolve) { setTimeout(resolve, 1500); })
        .then(function () { return ensureContentScriptAndExtract(tabId, attempt + 1); });
    }
    // The pane still shows the previously clicked job: wait for LinkedIn to repaint it.
    var stale = job && job.shown_job_id && urlJobId(job.url) && job.shown_job_id !== urlJobId(job.url);
    if (stale && attempt < 5) {
      return new Promise(function (resolve) { setTimeout(resolve, 1200); })
        .then(function () { return ensureContentScriptAndExtract(tabId, attempt + 1); });
    }
    if ((job && job.text && job.text.length >= 800) || attempt >= 4) return job;
    return new Promise(function (resolve) { setTimeout(resolve, 1500); })
      .then(function () { return ensureContentScriptAndExtract(tabId, attempt + 1); });
  });
}

function postJob(job) {
  return fetch(SERVER + '/jobs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(job)
  }).then(function (res) {
    if (!res.ok) {
      // Show the server's reason (a stale page, for one) rather than a bare status code.
      return res.json().catch(function () { return {}; }).then(function (d) {
        throw new Error((d && d.error) || ('Server responded ' + res.status));
      });
    }
    return res.json();
  });
}

// A captured profile is saved as a contact, free: nothing is drafted and nothing paid runs .
function postPerson(p) {
  if (!p.name) return Promise.reject(new Error('The profile has not finished loading. Scroll the page a little and press the eye again.'));
  return fetch(SERVER + '/api/people/manual', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: p.name, linkedin_url: p.linkedin_url || p.url, title: p.title, headline: p.headline, location: p.location,
      company: p.company, company_url: p.company_url, about: p.about, raw: p.raw || null })
  }).then(function (res) {
    if (!res.ok) {
      return res.json().catch(function () { return {}; }).then(function (d) { throw new Error((d && d.error) || ('Server responded ' + res.status)); });
    }
    return res.json();
  });
}

// "Refresh from profile" : read the profile open in the active tab again and send it for an already
// captured person. The tab must be that person's own profile; the server checks too.
function profileSlugOf(url) {
  var m = /linkedin\.com\/in\/([^\/?#]+)/i.exec(url || '');
  if (!m) return '';
  try { return decodeURIComponent(m[1]).toLowerCase(); } catch (e) { return m[1].toLowerCase(); }
}

function refreshPerson(personId, personUrl, name, tab) {
  var who = name || 'this person';
  if (!personId || !tab || !profileSlugOf(tab.url) || profileSlugOf(tab.url) !== profileSlugOf(personUrl)) {
    notifyPanel({ type: 'person-refresh-failed', person_id: personId, message: 'Open ' + who + "'s profile first" });
    return;
  }
  ensureContentScriptAndExtract(tab.id).then(function (found) {
    if (!found || found.kind !== 'person') throw new Error('Open ' + who + "'s profile first");
    return fetch(SERVER + '/api/people/' + encodeURIComponent(personId) + '/refresh', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: found.name, linkedin_url: found.linkedin_url || found.url, title: found.title, headline: found.headline,
        location: found.location, company: found.company, company_url: found.company_url, about: found.about, raw: found.raw || null })
    });
  }).then(function (res) {
    return res.json().catch(function () { return {}; }).then(function (d) {
      if (!res.ok) throw new Error((d && d.error) || ('Server responded ' + res.status));
      notifyPanel({ type: 'person-refreshed', person_id: personId, result: d });
    });
  }).catch(function (err) {
    var down = /Failed to fetch|NetworkError|ECONNREFUSED/i.test(String(err && (err.message || err)));
    notifyPanel({ type: 'person-refresh-failed', person_id: personId, message: down ? 'The server is not running.' : String((err && err.message) || err) });
  });
}

// One place that sends what a capture found to the right route: a profile to the people list, a page to the jobs list.
function postCaptured(found, windowId) {
  if (found && found.kind === 'person') {
    return postPerson(found).then(function (r) {
      chrome.storage.session.set({ lastPerson: r, lastPersonAt: Date.now() });
      notifyPanel({ type: 'person-created', result: r });
      openSidePanelForWindow(windowId);
    });
  }
  return postJob(found).then(function (created) { onJobCreated(created, windowId); });
}

function notifyPanel(msg) { chrome.runtime.sendMessage(msg).catch(function () {}); }

function openSidePanelForWindow(windowId) {
  if (windowId !== undefined && windowId !== null) chrome.sidePanel.open({ windowId: windowId }).catch(function () {});
}

function handleCaptureError(err) {
  var isServerDown = /Failed to fetch|NetworkError|ECONNREFUSED/i.test(String(err && (err.message || err)));
  var event = isServerDown ? { type: 'server-down' } : { type: 'capture-error', message: String((err && err.message) || err) };
  chrome.storage.session.set({ lastEvent: event });
  notifyPanel(event);
}

function onJobCreated(created, windowId) {
  chrome.storage.session.set({ lastJobId: created.id });
  sendStoredCareers(created);
  // `seen` tells the panel this posting was already in the list, so it can say so instead of
  // looking like the button did nothing.
  notifyPanel({ type: 'job-created', id: created.id, seen: !!created.duplicate_of, status: created.status });
  openSidePanelForWindow(windowId);
}

function captureActiveTab(tabId, windowId) {
  ensureContentScriptAndExtract(tabId)
    .then(function (found) { return postCaptured(found, windowId); })
    .catch(function (err) { handleCaptureError(err); openSidePanelForWindow(windowId); });
}

function captureLinkInBackgroundTab(linkUrl, windowId) {
  chrome.tabs.create({ url: linkUrl, active: false }, function (tab) {
    var tabId = tab.id;
    waitForTabComplete(tabId, TAB_LOAD_TIMEOUT_MS)
      .then(function () { return ensureContentScriptAndExtract(tabId); })
      .then(function (found) { chrome.tabs.remove(tabId); return postCaptured(found, windowId); })
      .catch(function (err) {
        chrome.tabs.remove(tabId, function () {});
        handleCaptureError(err);
        openSidePanelForWindow(windowId);
      });
  });
}

// ---------- Careers page from an Apply click ----------
// On LinkedIn, Apply for a job hosted elsewhere opens the company's careers page in a new tab. That
// page is the only link an outreach email may carry (never a LinkedIn link, which may be private), so
// the new tab's address, once it has finished loading and redirecting, is recorded against the
// LinkedIn job its opener tab was showing. Easy Apply opens no tab and records nothing; the email
// then names the role and its job ID. A service worker can sleep between events, so the tabs being
// watched live in session storage, and links for jobs not captured yet wait in local storage.
function careersPageUrl(url) {
  var m = /^https?:\/\/([^\/?#]+)/i.exec(String(url || ''));
  return m && !/(^|\.)linkedin\.com$/i.test(m[1]) ? String(url) : '';
}

function sendCareers(jobId, url) {
  return fetch(SERVER + '/api/careers_url', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_key: 'linkedin:' + jobId, url: url })
  }).then(function (r) { return r.ok; }).catch(function () { return false; });
}

function rememberCareers(jobId, url) {
  return chrome.storage.local.get('careers').then(function (d) {
    var all = (d && d.careers) || {};
    all[jobId] = url;
    return chrome.storage.local.set({ careers: all });
  }).then(function () { return sendCareers(jobId, url); }).catch(function () {});
}

// A capture made after the Apply click: hand over the careers link recorded for that job.
function sendStoredCareers(created) {
  var m = /^linkedin:(\d+)$/.exec((created && created.job_key) || '');
  if (!m || created.careers_url) return;
  chrome.storage.local.get('careers').then(function (d) {
    var url = d && d.careers && d.careers[m[1]];
    if (url) sendCareers(m[1], url);
  }).catch(function () {});
}

function watchedApply(tabId) {
  return chrome.storage.session.get('applyWatch').then(function (d) { return ((d && d.applyWatch) || {})[tabId] || ''; });
}
function setWatch(tabId, jobId) {
  return chrome.storage.session.get('applyWatch').then(function (d) {
    var w = (d && d.applyWatch) || {};
    if (jobId) w[tabId] = jobId; else delete w[tabId];
    return chrome.storage.session.set({ applyWatch: w });
  });
}
function recordIfLanded(tabId, url) {
  var careers = careersPageUrl(url);
  if (!careers) return Promise.resolve();          // still on LinkedIn's redirect
  return watchedApply(tabId).then(function (jobId) {
    if (!jobId) return;
    return setWatch(tabId, null).then(function () { return rememberCareers(jobId, careers); });
  });
}

chrome.tabs.onCreated.addListener(function (tab) {
  if (tab.openerTabId === undefined || tab.openerTabId === null) return;
  chrome.tabs.get(tab.openerTabId).then(function (opener) {
    var jobId = /linkedin\.com\/jobs/i.test((opener && opener.url) || '') ? urlJobId(opener.url) : '';
    if (!jobId) return;
    return setWatch(tab.id, jobId).then(function () { return chrome.tabs.get(tab.id); }).then(function (now) {
      // The page may have finished loading before the watch was in place.
      if (now && now.status === 'complete') return recordIfLanded(tab.id, now.url);
    });
  }).catch(function () {});
});
chrome.tabs.onUpdated.addListener(function (tabId, info, tab) {
  if (info.status === 'complete') recordIfLanded(tabId, (tab && tab.url) || '').catch(function () {});
});
chrome.tabs.onRemoved.addListener(function (tabId) { setWatch(tabId, null).catch(function () {}); });

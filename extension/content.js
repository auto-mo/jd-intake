// JD Intake content script.
// Exposes window.extractJob() and, when running as a real content script,
// answers chrome.runtime messages of type "extract". Never throws.
(function () {
  // A version, not a flag: a LinkedIn tab left open all day kept the old script after the
  // extension was updated, because the flag said it was already loaded .
  var SCRIPT_VERSION = '2026-10-09b';
  if (typeof window !== 'undefined' && window.__jdIntakeLoaded === SCRIPT_VERSION) return;
  if (typeof window !== 'undefined') window.__jdIntakeLoaded = SCRIPT_VERSION;

  var MAX_CHARS = 40000;

  function getText(el) {
    if (!el) return '';
    var t = el.innerText;
    if (t === undefined || t === null || t === '') {
      t = el.textContent || '';
    }
    return String(t).trim();
  }

  function qs(sel, root) {
    try {
      return (root || document).querySelector(sel);
    } catch (e) {
      return null;
    }
  }

  // A LinkedIn company link in any of its shapes (/company/acme/, /company/acme/life/,
  // ?trk=...) reduced to https://www.linkedin.com/company/acme. The outreach search scopes on
  // this URL, so a wrong one finds the wrong people; anything that does not parse is dropped.
  function companyUrl(href) {
    if (!href) return '';
    var m = String(href).match(/(?:^|linkedin\.com)\/company\/([^\/?#]+)/i);
    return m ? 'https://www.linkedin.com/company/' + m[1].toLowerCase() : '';
  }

  function attr(sel, name, root) {
    var el = qs(sel, root);
    return el ? el.getAttribute(name) : null;
  }

  // Runs each candidate fn in order, returns the first non-empty trimmed string.
  function pick(candidates) {
    for (var i = 0; i < candidates.length; i++) {
      try {
        var v = candidates[i]();
        if (v && String(v).trim()) return String(v).trim();
      } catch (e) {
        // try next candidate
      }
    }
    return '';
  }

  function stripTrailingToggle(t) {
    return t.replace(/\s*(See more|Show more|Show less)\s*$/i, '').trim();
  }

  function postprocess(text) {
    var t = text || '';
    t = t.replace(/\n{3,}/g, '\n\n');
    t = stripTrailingToggle(t);
    t = t.trim();
    if (t.length > MAX_CHARS) t = t.slice(0, MAX_CHARS);
    return t;
  }

  function firstPathSegment() {
    var parts = (window.location.pathname || '').split('/').filter(Boolean);
    return parts.length ? parts[0] : '';
  }

  function hostnameNoWww() {
    return (window.location.hostname || '').replace(/^www\./, '');
  }

  function largestTextDescendant(root) {
    if (!root) return null;
    var all;
    try {
      all = root.querySelectorAll('*');
    } catch (e) {
      return root;
    }
    var best = null;
    var bestLen = -1;
    for (var i = 0; i < all.length; i++) {
      var len = getText(all[i]).length;
      if (len > bestLen) {
        bestLen = len;
        best = all[i];
      }
    }
    return best || root;
  }

  function textMinusForms(el) {
    if (!el) return '';
    try {
      var clone = el.cloneNode(true);
      var forms = clone.querySelectorAll('form');
      for (var i = 0; i < forms.length; i++) {
        forms[i].parentNode.removeChild(forms[i]);
      }
      return getText(clone);
    } catch (e) {
      return getText(el);
    }
  }

  // ---------- LinkedIn ----------
  // Logged-in LinkedIn rotates class names and lazy-loads the right pane, so every field has
  // a chain of fallbacks ending in the tab title ("Title | Company | LinkedIn").
  function liTitleParts() {
    var parts = (document.title || '').split(' | ');
    return parts.length >= 3 ? { title: parts[0].trim(), company: parts[1].trim() } : { title: '', company: '' };
  }

  // The job the details pane is actually showing, from its title link. On the search-results view
  // LinkedIn changes the URL the moment a job is clicked and repaints the pane a moment later, so the
  // URL can name one job while the pane still shows another (two jobs in a row can show the wrong one).
  function liShownJobId() {
    var a = qs('.job-details-jobs-unified-top-card__job-title a[href*="/jobs/view/"]') ||
      qs('.jobs-unified-top-card__job-title a[href*="/jobs/view/"]') ||
      qs('.top-card-layout__title a[href*="/jobs/view/"]');
    var m = a && String(a.getAttribute('href') || '').match(/\/jobs\/view\/(?:[^\/?#]*?-)?(\d+)/);
    return m ? m[1] : '';
  }

  function liDetailRoot() {
    return qs('.scaffold-layout__detail') || qs('.jobs-search__job-details--container') ||
      qs('.job-view-layout') || qs('.jobs-details') || qs('main') || document.body;
  }

  function liLargestDescription(root) {
    // Largest element whose class mentions "description" inside the detail pane.
    var best = null, bestLen = 0;
    var nodes = root.querySelectorAll('[class*="description"], [id*="description"], [class*="job-details"]');
    for (var i = 0; i < nodes.length; i++) {
      var len = getText(nodes[i]).length;
      if (len > bestLen) { bestLen = len; best = nodes[i]; }
    }
    return best;
  }

  // The search-results view keeps the job list and the job detail side by side. Class names
  // rotate, but the detail pane always carries an "About the job" heading, so the tightest
  // element containing that heading with real length is the description. The list pane is
  // recognisable by its own chrome and is rejected outright.
  var LIST_MARKERS = ['How promoted jobs are ranked', 'Be an early applicant', 'Jobs based on your preferences', 'Set alert'];
  function looksLikeList(t) {
    if (!t) return false;
    var hits = 0;
    for (var i = 0; i < LIST_MARKERS.length; i++) if (t.indexOf(LIST_MARKERS[i]) !== -1) hits++;
    return hits >= 1 || /^\s*\d+\+?\s+results/.test(t);
  }
  function liAboutTheJob() {
    var nodes, best = null, bestLen = Infinity;
    try { nodes = document.querySelectorAll('div, section, article'); } catch (e) { return null; }
    for (var i = 0; i < nodes.length; i++) {
      var t = getText(nodes[i]);
      if (t.length < 800 || t.indexOf('About the job') === -1 || looksLikeList(t)) continue;
      if (t.length < bestLen) { bestLen = t.length; best = nodes[i]; }
    }
    return best;
  }

  function extractLinkedIn() {
    var root = liDetailRoot();
    var tp = liTitleParts();

    var title = pick([
      function () { return getText(qs('.job-details-jobs-unified-top-card__job-title h1')); },
      function () { return getText(qs('.job-details-jobs-unified-top-card__job-title')); },
      function () { return getText(qs('h1', root)); },
      function () { return getText(qs('.top-card-layout__title')); },
      function () { return getText(qs('h1')); },
      function () { return tp.title; }
    ]);

    var company = pick([
      function () {
        var container = qs('.job-details-jobs-unified-top-card__company-name');
        if (!container) return '';
        var a = qs('a', container);
        return getText(a) || getText(container);
      },
      function () { return getText(qs('.topcard__org-name-link')); },
      function () { return getText(qs('a[href*="/company/"]', root)); },
      function () { return tp.company; }
    ]);

    var location = pick([
      function () { return getText(qs('.job-details-jobs-unified-top-card__primary-description-container')); },
      function () { return getText(qs('.job-details-jobs-unified-top-card__tertiary-description-container')); },
      function () { return getText(qs('.topcard__flavor--bullet')); },
      function () {
        // Top card reads "Greater Chicago Area · 3 weeks ago · ..." in the logged-in view.
        var head = getText(root).slice(0, 600);
        var m = head.match(/([^\n·]{3,60}?)\s*·\s*\d+\s+(?:hours?|days?|weeks?|months?) ago/);
        return m ? m[1].trim() : '';
      }
    ]);

    var text = pick([
      function () { return getText(liAboutTheJob()); },
      function () { return getText(qs('#job-details')); },
      function () { return getText(qs('.jobs-description__content')); },
      function () { return getText(qs('.jobs-description')); },
      function () { return getText(qs('.jobs-box__html-content')); },
      function () { return getText(qs('article', root)); },
      function () { return getText(qs('.show-more-less-html__markup')); },
      function () { return getText(qs('.description__text')); },
      function () { return getText(liLargestDescription(root)); },
      function () { return root !== document.body ? getText(root) : ''; }
    ]);

    // Anything that reads as the results list is worse than nothing: an empty capture gets
    // re-captured, a list gets evaluated as if it were a job.
    if (looksLikeList(text)) text = '';
    // Strip the "About the job" heading LinkedIn puts above the body.
    text = text.replace(/^About the job\s*/i, '');

    var company_url = pick([
      function () { return companyUrl(attr('.job-details-jobs-unified-top-card__company-name a', 'href')); },
      function () { return companyUrl(attr('.topcard__org-name-link', 'href')); },
      function () { return companyUrl(attr('a[href*="/company/"]', 'href', root)); }
    ]);

    return { title: title, company: company, company_url: company_url, location: location, text: text, source: 'linkedin',
      shown_job_id: liShownJobId() };
  }

  // ---------- LinkedIn profile  ----------
  // The eye on linkedin.com/in/<slug> captures the person, not a job. Written against the profile page's structure
  // and its visible text, with fallbacks for every field, but it has not been run on a live profile (LinkedIn needs a
  // login): the fixture in test/person.test.js is hand-written. Class names rotate, so text lines carry the weight.
  function isProfilePath() {
    return /^\/in\/[^\/]+/i.test((window.location && window.location.pathname) || '');
  }

  function profileUrl() {
    var m = ((window.location && window.location.pathname) || '').match(/^\/in\/([^\/?#]+)/i);
    return m ? 'https://www.linkedin.com/in/' + m[1] : '';
  }

  // The visible lines of an element: trimmed, no blanks, and no line repeated straight after itself (LinkedIn writes
  // each title twice, once visually hidden).
  function textLines(el) {
    var out = [];
    String(getText(el)).split('\n').forEach(function (ln) {
      var t = ln.replace(/\s+/g, ' ').trim();
      if (!t) return;
      var half = t.length % 2 === 0 ? t.slice(0, t.length / 2) : '';
      if (half && half === t.slice(t.length / 2)) t = half;           // "DirectorDirector"
      var words = t.split(' ');
      if (words.length % 2 === 0 && words.length > 1 && words.slice(0, words.length / 2).join(' ') === words.slice(words.length / 2).join(' ')) {
        t = words.slice(0, words.length / 2).join(' ');                // "Director Director"
      }
      if (out.length && out[out.length - 1] === t) return;
      out.push(t);
    });
    return out;
  }

  // A profile section by its anchor id (<div id="experience"> sits inside the section), else by its heading.
  function profileSection(anchorId, heading) {
    var a = qs('#' + anchorId);
    var sec = a && a.closest ? a.closest('section') : null;
    if (sec) return sec;
    var secs = [];
    try { secs = document.querySelectorAll('section'); } catch (e) { /* none */ }
    for (var i = 0; i < secs.length; i++) {
      var first = textLines(secs[i])[0] || '';
      if (first.toLowerCase() === heading.toLowerCase()) return secs[i];
    }
    return null;
  }

  var NOT_A_PLACE = /connections?|followers?|contact info|^message$|^follow$|^connect$|^more$|^save in|open to|^pending$|mutual|\bhe\/him\b|\bshe\/her\b|\bthey\/them\b|^[\u00b7\s]*(1st|2nd|3rd)/i;
  var EMPLOYMENT_TYPE = /^(full-time|part-time|contract|internship|self-employed|freelance|apprenticeship|seasonal|permanent|temporary)\b/i;

  function topCardLines(h1) {
    var card = (h1 && h1.closest && (h1.closest('section') || h1.closest('main'))) || document.body;
    var lines = textLines(card);
    var nm = getText(h1).replace(/\s+/g, ' ').trim();
    var at = lines.indexOf(nm);
    if (at === -1) for (var i = 0; i < lines.length; i++) if (nm && lines[i].indexOf(nm) === 0) { at = i; break; }
    return at === -1 ? lines : lines.slice(at + 1);
  }

  // Raw material for the server's one model call . The heuristics below read a profile by
  // its markup, and LinkedIn's markup is hashed and moves; the page's VISIBLE TEXT does not. So the content script also
  // sends what is on the page, in order, and the server decides what it means: the page heading, the tab title, the top
  // card and the Experience section as text (about 8,000 characters in all) and every link to a company page.
  var RAW_CAP = 8000;
  var PROFILE_HEADINGS = /^(about|featured|activity|highlights|experience|education|licenses (&|and) certifications|volunteering|skills|projects|publications|honors (&|and) awards|recommendations|courses|languages|interests|services|analytics|resources|people also viewed|more profiles for you|people you may know|explore premium profiles)$/i;

  function personLines(h1, name) {
    var main = qs('main') || document.body;
    var lines = textLines(main);
    var at = lines.indexOf(name);
    if (at === -1) for (var i = 0; i < lines.length; i++) if (name && lines[i].indexOf(name) === 0) { at = i; break; }
    return at === -1 ? lines : lines.slice(at);
  }

  function linesUntilHeading(lines, from, cap) {
    var out = [], size = 0;
    for (var i = from; i < lines.length; i++) {
      if (i > from && PROFILE_HEADINGS.test(lines[i])) break;
      if (size + lines[i].length + 1 > cap) { if (cap - size > 20) out.push(lines[i].slice(0, cap - size)); break; }
      size += lines[i].length + 1;
      out.push(lines[i]);
    }
    return out;
  }

  function headingAt(lines, re, from) {
    for (var i = from || 0; i < lines.length; i++) if (re.test(lines[i])) return i;
    return -1;
  }

  function personAbout(lines) {
    var exp = headingAt(lines, /^experience$/i);
    var at = headingAt(lines, /^about$/i);
    if (at === -1 || (exp !== -1 && at > exp)) return '';
    var body = linesUntilHeading(lines, at + 1, 1400);
    return body.join(' ').replace(/\s*(\u2026|\.\.\.)?\s*(see more|show more)\s*$/i, '').trim().slice(0, 1000);
  }

  function companyLinkText(a) {
    var t = getText(a).split('\n')[0] || '';
    if (!t.trim()) t = a.getAttribute('aria-label') || '';
    if (!t.trim()) { var img = qs('img', a); t = img ? (img.getAttribute('alt') || '') : ''; }
    return t.replace(/\s+/g, ' ').trim().slice(0, 120);
  }

  function personRaw(h1, name) {
    var lines = personLines(h1, name);
    var top = linesUntilHeading(lines, 0, 2500).join('\n');
    // Experience: the section found by its anchor or heading when there is one, else the lines under the heading.
    var expEl = profileSection('experience', 'Experience');
    var expText = expEl ? textLines(expEl).join('\n') : '';
    if (expText.length < 30) {
      var at = headingAt(lines, /^experience$/i);
      expText = at === -1 ? '' : linesUntilHeading(lines, at, RAW_CAP).join('\n');
    }
    var title = '';
    try { title = String(document.title || ''); } catch (e) { /* none */ }
    var h1t = getText(h1).replace(/\s+/g, ' ').trim().slice(0, 200);
    title = title.slice(0, 300);
    var budget = Math.max(0, RAW_CAP - h1t.length - title.length - top.length);
    var links = [], seen = {}, scope = qs('main') || document;
    var anchors = [];
    try { anchors = scope.querySelectorAll('a[href*="/company/"]'); } catch (e) { /* none */ }
    if (!anchors.length && scope !== document) { try { anchors = document.querySelectorAll('a[href*="/company/"]'); } catch (e2) { /* none */ } }
    for (var i = 0; i < anchors.length && links.length < 60; i++) {
      var href = anchors[i].getAttribute('href') || '', text = companyLinkText(anchors[i]);
      var key = href + '|' + text;
      if (!companyUrl(href) || seen[key]) continue;
      seen[key] = true;
      links.push({ href: href, text: text });
    }
    return { h1: h1t, page_title: title, top_card: top, experience: expText.slice(0, budget), company_links: links, lines: lines };
  }

  function extractPerson() {
    var h1 = qs('main h1') || qs('h1');
    var titleParts = String(document.title || '').replace(/^\(\d+\)\s*/, '').split(' | ')[0].split(' - ');
    var name = pick([
      function () { return getText(h1).replace(/\s+/g, ' '); },
      function () { return titleParts[0]; }
    ]);
    var after = h1 ? topCardLines(h1).filter(function (l) { return !NOT_A_PLACE.test(l); }) : [];

    var headline = pick([
      function () { return getText(qs('.text-body-medium.break-words')); },
      function () { return getText(qs('[data-generated-suggestion-target]')); },
      function () { return after[0]; },
      function () { return titleParts.length > 2 ? titleParts.slice(1, -1).join(' - ') : ''; }
    ]);
    var location = pick([
      function () { return getText(qs('.text-body-small.inline.t-black--light.break-words')); },
      function () { return after.filter(function (l) { return l !== headline && l.length < 90 && /,|\bArea\b|\bRegion\b|\bUnited\b/.test(l); })[0]; }
    ]).replace(/\s*[\u00b7|]\s*Contact info.*$/i, '').trim();

    // The first Experience entry: a single role ("Director / Acme · Full-time / dates") or a company with its roles under it.
    var exp = profileSection('experience', 'Experience');
    var entry = exp ? (qs('li.artdeco-list__item', exp) || qs('[data-view-name="profile-component-entity"]', exp) || qs('li', exp)) : null;
    var lines = entry ? textLines(entry) : [];
    var grouped = !!entry && entry.querySelectorAll('li').length > 0;
    var role = '', company = '', current = false;
    if (lines.length) {
      current = /\bPresent\b/i.test(lines.join(' '));
      if (grouped || (lines[1] && EMPLOYMENT_TYPE.test(lines[1]))) {
        company = lines[0];
        var nested = entry.querySelector('li');
        role = nested ? (textLines(nested)[0] || '') : (lines[2] || '');
      } else {
        role = lines[0];
        company = (lines[1] || '').split('\u00b7')[0].trim();
      }
    }
    var company_url = entry ? companyUrl(attr('a[href*="/company/"]', 'href', entry)) : '';
    if (!current) { role = ''; company = ''; company_url = ''; }          // an old job is not where they work now
    if (!company) {
      var cc = String(attr('button[aria-label^="Current company"]', 'aria-label') || '').match(/Current company:\s*([^.]+)\./i);
      company = cc ? cc[1].trim() : '';
    }
    if (!company || !role) {
      var hm = String(headline).match(/^(.*?)\s+(?:at|@)\s+(.+?)(?:\s+[|\u00b7].*)?$/);
      if (hm) { role = role || hm[1].trim(); company = company || hm[2].trim(); }
    }

    var raw = personRaw(h1, name);
    var about = personAbout(raw.lines);
    if (!about) {                      // a page whose lines do not break at headings: the section found by anchor or heading
      var aboutEl = profileSection('about', 'About');
      var aboutLines = aboutEl ? textLines(aboutEl) : textLines(qs('.pv-about__summary-text'));
      if (aboutLines.length && /^about$/i.test(aboutLines[0])) aboutLines = aboutLines.slice(1);
      about = aboutLines.join(' ').replace(/\s*(\u2026|\.\.\.)?\s*(see more|show more)\s*$/i, '').trim().slice(0, 1000);
    }

    delete raw.lines;
    return { kind: 'person', name: name, headline: headline, title: role || headline, location: location, company: company,
      company_url: company_url, about: about, linkedin_url: profileUrl(), text: '', source: 'linkedin_profile', raw: raw };
  }

  // ---------- Greenhouse ----------
  function isGreenhouse() {
    return window.location.hostname.indexOf('greenhouse.io') !== -1 ||
      !!qs('#grnhse_app') || !!qs('div.job__description');
  }

  function extractGreenhouse() {
    var title = pick([
      function () { return getText(qs('h1.app-title')); },
      function () { return getText(qs('.job__title h1')); },
      function () { return getText(qs('h1')); }
    ]);

    var company = pick([
      function () { return getText(qs('.company-name')); },
      function () { return attr('meta[property="og:site_name"]', 'content'); },
      function () { return firstPathSegment(); }
    ]);

    var location = pick([
      function () { return getText(qs('.job__location')); },
      function () { return getText(qs('.location')); }
    ]);

    var text = pick([
      function () { return getText(qs('#content')); },
      function () { return getText(qs('.job__description')); }
    ]);

    return { title: title, company: company, location: location, text: text, source: 'greenhouse' };
  }

  // ---------- Lever ----------
  function extractLever() {
    var title = pick([
      function () { return getText(qs('.posting-headline h2')); },
      function () { return getText(qs('h2')); }
    ]);

    var company = pick([
      function () {
        // Lever titles read "Company - Job title"; the company is the first part.
        var og = attr('meta[property="og:title"]', 'content') || document.title || '';
        var parts = og.split(' - ');
        return parts.length > 1 ? parts[0] : '';
      },
      function () { return attr('.main-header-logo img', 'alt'); },
      function () { return firstPathSegment(); }
    ]);

    var location = getText(qs('.posting-categories .location'));

    var text = pick([
      function () { return textMinusForms(qs('.posting-page')); },
      function () { return textMinusForms(qs('.section-wrapper')); }
    ]);

    return { title: title, company: company, location: location, text: text, source: 'lever' };
  }

  // ---------- Ashby ----------
  function extractAshby() {
    var title = getText(qs('h1'));

    var company = pick([
      function () { return attr('meta[property="og:site_name"]', 'content'); },
      function () {
        // Ashby titles read "Job title @ Company".
        var dt = document.title || '';
        var at = dt.split(/\s+@\s+/);
        if (at.length > 1) return at[at.length - 1];
        var parts = dt.split(/\s+[|-]\s+/);
        return parts.length > 1 ? parts[parts.length - 1] : '';
      },
      function () { return firstPathSegment(); }
    ]);

    var descEl = qs('[class*="descriptionText"], [class*="_description"]');
    if (!descEl) {
      var main = qs('main');
      descEl = largestTextDescendant(main || document.body);
    }

    return { title: title, company: company, location: '', text: getText(descEl), source: 'ashby' };
  }

  // ---------- Workday ----------
  function extractWorkday() {
    var title = pick([
      function () { return getText(qs('[data-automation-id="jobPostingHeader"]')); },
      function () { return getText(qs('h2')); }
    ]);

    var host = window.location.hostname || '';
    var company = host.split('.')[0] || '';

    var location = getText(qs('[data-automation-id="locations"]'))
      .replace(/^locations?\s*/i, '').split('\n')[0].trim();
    var text = getText(qs('[data-automation-id="jobPostingDescription"]'));

    return { title: title, company: company, location: location, text: text, source: 'workday' };
  }

  // ---------- Generic ----------
  function extractGeneric() {
    var title = pick([
      function () { return attr('meta[property="og:title"]', 'content'); },
      function () { return getText(qs('h1')); },
      function () { return document.title; }
    ]);

    var company = pick([
      function () { return attr('meta[property="og:site_name"]', 'content'); },
      function () { return hostnameNoWww(); }
    ]);

    var candidateSelectors = ['main', 'article', '[role=main]', '#content', '.content', 'body'];
    var best = null;
    var bestLen = -1;
    for (var i = 0; i < candidateSelectors.length; i++) {
      var el = qs(candidateSelectors[i]);
      var len = getText(el).length;
      if (len > bestLen) {
        bestLen = len;
        best = el;
      }
    }

    return { title: title, company: company, location: '', text: getText(best), source: 'generic' };
  }

  function extractJob() {
    var result;
    try {
      var host = (window.location && window.location.hostname) || '';
      if (host.indexOf('linkedin.com') !== -1 && isProfilePath()) {
        result = extractPerson();
      } else if (host.indexOf('linkedin.com') !== -1) {
        result = extractLinkedIn();
      } else if (isGreenhouse()) {
        result = extractGreenhouse();
      } else if (host.indexOf('lever.co') !== -1) {
        result = extractLever();
      } else if (host.indexOf('ashbyhq.com') !== -1) {
        result = extractAshby();
      } else if (host.indexOf('myworkdayjobs.com') !== -1) {
        result = extractWorkday();
      } else {
        result = extractGeneric();
      }
    } catch (e) {
      result = { title: '', company: '', location: '', text: '', source: 'generic' };
    }

    var url = '';
    var pageTitle = '';
    try { url = window.location.href; } catch (e) {}
    try { pageTitle = document.title || ''; } catch (e) {}

    if (result && result.kind === 'person') {
      return { kind: 'person', url: url, page_title: pageTitle, name: result.name || '', headline: result.headline || '',
        title: result.title || '', location: result.location || '', company: result.company || '', company_url: result.company_url || '',
        about: result.about || '', linkedin_url: result.linkedin_url || '', text: '', source: 'linkedin_profile', raw: result.raw || null };
    }
    return {
      url: url,
      title: (result && result.title) || '',
      company: (result && result.company) || '',
      company_url: (result && result.company_url) || '',
      shown_job_id: (result && result.shown_job_id) || '',
      location: (result && result.location) || '',
      text: postprocess((result && result.text) || ''),
      source: (result && result.source) || 'generic',
      page_title: pageTitle
    };
  }

  if (typeof window !== 'undefined') {
    window.extractJob = extractJob;
  }

  if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
      if (msg && msg.type === 'extract') {
        sendResponse(extractJob());
        return true;
      }
      return false;
    });
  }
})();

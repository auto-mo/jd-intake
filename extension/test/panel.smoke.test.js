// Loads sidepanel.html + sidepanel.js into a jsdom document with a stubbed
// fetch and exercises render() against fixtures covering every status, the
// verdict chip table, the accordion, primary-button labels, radio questions,
// legacy string questions, draft persistence and filter counts. Run with:
//   node test/panel.smoke.test.js
'use strict';
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const extDir = path.join(__dirname, '..');
const htmlSource = fs.readFileSync(path.join(extDir, 'sidepanel.html'), 'utf8');
const jsSource = fs.readFileSync(path.join(extDir, 'sidepanel.js'), 'utf8');
const cssSource = fs.readFileSync(path.join(extDir, 'sidepanel.css'), 'utf8');

let passed = 0;
let failed = 0;
function assert(cond, msg) {
  if (cond) { passed++; console.log('  PASS  ' + msg); }
  else { failed++; console.log('  FAIL  ' + msg); }
}

// ---------- Fixtures ----------
function baseJob(overrides) {
  return Object.assign({
    id: 'job-' + overrides.status,
    url: 'https://www.linkedin.com/jobs/view/4396843644/',
    source: 'linkedin',
    job_key: 'linkedin:4396843644',
    title: 'Strategy Insights & Planning Consultant for a Very Long Title That Should Not Wrap',
    company: 'Northbridge Logistics',
    location: 'Denver, CO (Hybrid)',
    text_chars: 5268,
    text_head: 'We are looking for a strategy consultant to join our team.',
    capture_quality: 'ok',
    captured_at: '2026-09-12T21:30:00',
    folder: '/home/alex/job-hunt/data/applications/job-x',
    lca: { matched_name: 'NORTHBRIDGE LOGISTICS, INC.', filings: 607, certified: 560, dependent: 'YES', fy24: 289, fy25: 318, trend: 'GROWING', how: 'exact' },
    duplicate_of: null,
    evaluation: null,
    questions: [],
    messages: [],
    desktop_files: [],
    build: null,
    cover: null,
    answers: [],
    error: null
  }, overrides);
}

const evaluation = {
  fit_score: 82, recommendation: 'TAILOR', resume_version: 'analytics', sponsorship: 'Sponsors H-1B routinely.',
  strengths: ['Strategy background'], gaps: ['No healthcare experience'], keyword_gaps: ['Snowflake'],
  sponsorship_flag: 'explicit_yes', level_fit: 'at_level',
  cover_letter_combo: 'C + 1B', honest_take: 'Strong fit.', brief: 'Full brief text here.', session_id: 's1'
};
const lowEvaluation = Object.assign({}, evaluation, { fit_score: 45, recommendation: 'SKIP' });
const midEvaluation = Object.assign({}, evaluation, { fit_score: 60, recommendation: 'BASE' });

const v2Questions = [
  { id: 'smartsheet', question: 'Have you used Smartsheet?', why: 'The JD names it as a core tool', type: 'yes_no', options: ['Yes, hands on', 'No'], affects: 'the Tools line' },
  { id: 'people_mgmt', question: 'Formal people management?', why: 'The JD asks for coaching', type: 'choice', options: ['Direct reports', 'Informal mentoring only', 'Neither'], affects: 'a leadership bullet' },
  { id: 'anything_else', question: 'Anything else to note?', why: 'Optional context', type: 'text', options: [], affects: 'nothing specific' }
];
const legacyQuestions = ['Have you used Snowflake?', 'Do you have a portfolio link?'];

const build = {
  mode: 'tailored', docx: '/x/resume.docx', pdf: '/x/resume.pdf', jpg: '/x/resume.jpg', pages: 1, fill_ok: true,
  claims_to_verify: ['Led a team of 5'], changes: ['Reordered bullets'], tools_omitted: ['Tableau'], cost_usd: 0.12
};
const cover = { docx: '/x/cover.docx', pdf: '/x/cover.pdf', pages: 1, combo_used: 'C + 1B', firm_specific_claim: 'Northbridge grew LCA filings 10% YoY.' };

const jobsByStatus = {
  captured: baseJob({ status: 'captured' }),
  captured_empty: baseJob({ status: 'captured', capture_quality: 'empty', text_chars: 0 }),
  evaluating: baseJob({ status: 'evaluating' }),
  scored: baseJob({ status: 'scored', evaluation: evaluation }),
  awaiting: baseJob({ status: 'awaiting', evaluation: evaluation }),
  questions: baseJob({ status: 'questions', evaluation: evaluation, questions: v2Questions }),
  questions_legacy: baseJob({ status: 'questions', evaluation: evaluation, questions: legacyQuestions }),
  building: baseJob({ status: 'building', evaluation: evaluation }),
  built: baseJob({ status: 'built', evaluation: evaluation, build: build }),
  built_with_cover: baseJob({ status: 'built', evaluation: evaluation, build: build, cover: cover, desktop_files: ['/home/alex/Desktop/Alex_Rivera_Northbridge.pdf'] }),
  applied: baseJob({ status: 'applied', evaluation: evaluation, build: build }),
  applied_people_review: baseJob({ status: 'applied', evaluation: evaluation, build: build,
    company_url: 'https://www.linkedin.com/company/northbridge-logistics', outreach: { state: 'people_review', people: 4 } }),
  applied_outreach_ready: baseJob({ status: 'applied', evaluation: evaluation, build: build,
    company_url: 'https://www.linkedin.com/company/northbridge-logistics', outreach: { state: 'ready', people: 3 } }),
  built_external: baseJob({ status: 'built_external', evaluation: evaluation,
    external_folder: '/home/alex/Documents/Resumes/Referral build' }),
  skipped: baseJob({ status: 'skipped' }),
  error: baseJob({ status: 'error', evaluation: evaluation, error: 'Claude CLI exited with code 1' }),
  needs_login: baseJob({ status: 'needs_login' }),
  // chip fixtures
  chip_no_sponsor: baseJob({ status: 'scored', evaluation: Object.assign({}, evaluation, { sponsorship_flag: 'explicit_no' }), lca: null }),
  chip_shrinking: baseJob({ status: 'scored', evaluation: evaluation, lca: { matched_name: 'X', filings: 40, certified: 30, trend: 'SHRINKING' } }),
  chip_no_lca: baseJob({ status: 'scored', evaluation: evaluation, lca: null }),
  chip_stretch: baseJob({ status: 'scored', evaluation: Object.assign({}, evaluation, { level_fit: 'stretch' }) }),
  chip_under: baseJob({ status: 'scored', evaluation: Object.assign({}, evaluation, { level_fit: 'under' }) }),
  chip_duplicate: baseJob({ status: 'scored', evaluation: evaluation, duplicate_of: { id: 'other-job', status: 'built', captured_at: '2026-08-12T00:00:00' } }),
  chip_short: baseJob({ status: 'captured', capture_quality: 'short', text_chars: 640 }),
  chip_clean: baseJob({ status: 'scored', evaluation: evaluation }), // at_level, sponsors growing, no dup, ok capture -> only Sponsors + Resume chips
  score_low: baseJob({ status: 'scored', evaluation: lowEvaluation }),
  score_mid: baseJob({ status: 'scored', evaluation: midEvaluation })
};
// baseJob() defaults id to 'job-' + status, which collides whenever two fixtures share a
// status (several chip/score fixtures below all use status: 'scored'). Force each fixture's
// id to match its own fixture key so every job in this file has a distinct id.
Object.keys(jobsByStatus).forEach(function (key) { jobsByStatus[key].id = 'job-' + key; });

const statuses = Object.keys(jobsByStatus);
const jobList = statuses.map(function (s) { return jobsByStatus[s]; });

// ---------- Stub fetch ----------
function jsonResponse(body, ok) {
  return Promise.resolve({
    ok: ok !== false,
    status: ok === false ? 404 : 200,
    json: function () { return Promise.resolve(body); }
  });
}
// What the server reports about the profile: every optional feature on, so the whole panel renders.
const statusBody = { onboarded: true, features: { sponsorship: true, outreach: true, email: true, alerts: true } };
function makeFetchStub() {
  return function (url) {
    const u = String(url);
    if (/\/api\/profile\/status$/.test(u)) return jsonResponse(statusBody);
    if (u.indexOf('/health') !== -1) return jsonResponse({ ok: true, claude: 'ready', version: '1' });
    if (/\/settings$/.test(u)) return jsonResponse({ auto: false, threshold: 70, auto_apply: false });
    if (/\/jobs\/[^/]+\/[a-z]+$/.test(u)) return jsonResponse({});
    if (/\/jobs\/[^/]+$/.test(u)) {
      const id = u.split('/').pop();
      const job = jobList.filter(function (j) { return j.id === id; })[0];
      return jsonResponse(job || { error: 'not found' }, !!job);
    }
    if (/\/jobs$/.test(u)) return jsonResponse(jobList);
    return jsonResponse({});
  };
}

// ---------- Build the DOM ----------
const dom = new JSDOM(htmlSource, { url: 'http://localhost/sidepanel.html', runScripts: 'outside-only' });
const styleEl = dom.window.document.createElement('style');
styleEl.textContent = cssSource;
dom.window.document.head.appendChild(styleEl);
dom.window.fetch = makeFetchStub();
dom.window.navigator.clipboard = { writeText: function () { return Promise.resolve(); } };
dom.window.eval(jsSource);
dom.window.features = statusBody.features;
dom.window.onboarded = true;

// Force a synchronous, controlled render against our fixed job list rather
// than relying on the timing of the stubbed initial fetch.
dom.window.jobs = jobList;
dom.window.expandedId = null;
dom.window.currentFilter = 'all';
dom.window.render();

const doc = dom.window.document;
function cardFor(status) {
  const job = jobsByStatus[status];
  return doc.getElementById('body-' + job.id) && doc.getElementById('body-' + job.id).closest('.card');
}
function expand(status) {
  dom.window.expandedId = jobsByStatus[status].id;
  dom.window.render();
}

// =====================================================================
// 1. Collapsed card renders for each of the 9 core statuses
// =====================================================================
console.log('\n-- Collapsed card per status --');
['captured', 'evaluating', 'scored', 'questions', 'building', 'built', 'applied', 'skipped', 'error'].forEach(function (status) {
  dom.window.expandedId = null;
  dom.window.render();
  const card = cardFor(status);
  assert(!!card, status + ': renders a .card');
  assert(card.className.indexOf('collapsed') !== -1, status + ': card is collapsed when not expandedId');
  const header = card.querySelector('.card-header');
  assert(!!header, status + ': has a sticky header');
  assert(header.querySelector('.card-title').textContent === 'Northbridge Logistics', status + ': the company leads the header');
  assert(header.querySelector('.card-sub').textContent.indexOf(jobsByStatus[status].title) === 0, status + ': the title and location sit under it');
  const sentence = header.querySelector('.stage-status-text').textContent;
  assert(sentence.length > 0, status + ': status sentence is non-empty (' + sentence + ')');
  var moving = ['evaluating', 'building', 'queued'].indexOf(status) !== -1;
  assert(header.querySelectorAll('.stage-dot').length === (moving ? 4 : 0),
    status + (moving ? ': four-dot stage row while moving' : ': no decorative dots once stopped'));
});

// Specific status-sentence wording
assert(cardFor('questions').querySelector('.stage-status-text').textContent === 'Needs your answer to 3 questions', 'questions: sentence names the count');
assert(cardFor('building').querySelector('.stage-status-text').textContent.indexOf('Building') === 0, 'building: sentence starts with "Building"');
assert(cardFor('built').querySelector('.stage-status-text').textContent.indexOf('Ready to upload') === 0, 'built: sentence starts with "Ready to upload"');
assert(cardFor('evaluating').querySelector('.stage-status-text').textContent === 'Evaluating…', 'evaluating: sentence is "Evaluating…"');
assert(cardFor('skipped').querySelector('.stage-status-text').textContent === 'Skipped', 'skipped: sentence is "Skipped"');
assert(cardFor('applied').querySelector('.stage-status-text').textContent === 'Applied', 'applied: sentence is "Applied"');

// =====================================================================
// 2. Accordion: opening B collapses A
// =====================================================================
console.log('\n-- Accordion --');
expand('scored');
assert(cardFor('scored').className.indexOf('collapsed') === -1, 'accordion: expanding scored shows it expanded');
assert(cardFor('built').className.indexOf('collapsed') !== -1, 'accordion: built stays collapsed while scored is expanded');
expand('built');
assert(cardFor('built').className.indexOf('collapsed') === -1, 'accordion: expanding built shows it expanded');
assert(cardFor('scored').className.indexOf('collapsed') !== -1, 'accordion: opening built collapsed the previously-open scored card');

// =====================================================================
// 3. Verdict chips: each condition fires, and only when it should
// =====================================================================
console.log('\n-- Verdict chips --');
function chipTexts(status) {
  expand(status);
  return Array.from(cardFor(status).querySelectorAll('.chips-row .chip')).map(function (c) { return c.textContent; });
}
function chipTones(status) {
  expand(status);
  const map = {};
  cardFor(status).querySelectorAll('.chips-row .chip').forEach(function (c) {
    const tone = Array.from(c.classList).filter(function (cl) { return cl.indexOf('tone-') === 0; })[0];
    map[c.textContent] = tone;
  });
  return map;
}

const noSponsorChips = chipTexts('chip_no_sponsor');
assert(noSponsorChips.indexOf('No sponsorship in the JD') !== -1, 'chip: "No sponsorship in the JD" fires when sponsorship_flag is explicit_no');
assert(chipTones('chip_no_sponsor')['No sponsorship in the JD'] === 'tone-danger', 'chip: no-sponsorship chip is danger tone');

const cleanChips = chipTexts('chip_clean');
assert(cleanChips.some(function (t) { return t.indexOf('Sponsors ·') === 0; }), 'chip: "Sponsors · N filings" fires for a growing LCA trend');
assert(chipTones('chip_clean')['Sponsors · 607 filings'] === 'tone-ok', 'chip: sponsors-filings chip is ok tone');
assert(cleanChips.indexOf('No sponsorship in the JD') === -1, 'chip: clean job has no no-sponsorship chip');
assert(cleanChips.indexOf('No LCA record') === -1, 'chip: clean job (has lca) has no "No LCA record" chip');
assert(cleanChips.indexOf('Level stretch') === -1 && cleanChips.indexOf('Below level') === -1, 'chip: at_level job has no level chip');
assert(cleanChips.indexOf('Seen before') === -1, 'chip: non-duplicate job has no "Seen before" chip');
assert(cleanChips.some(function (t) { return t.indexOf('Short capture') === 0; }) === false, 'chip: ok capture quality has no short-capture chip');
// 'Resume NNN' stopped being a chip: it does not change the next action, so it moved into Why.
assert(!chipTexts('scored').some(function (t) { return /^Resume /.test(t); }),
  'chip: the resume version is no longer a chip');

const shrinkChips = chipTexts('chip_shrinking');
assert(shrinkChips.indexOf('Sponsors, but shrinking') !== -1, 'chip: "Sponsors, but shrinking" fires for a SHRINKING trend');
assert(shrinkChips.some(function (t) { return t.indexOf('Sponsors ·') === 0; }) === false, 'chip: shrinking case does not also show the plain Sponsors chip');
assert(chipTones('chip_shrinking')['Sponsors, but shrinking'] === 'tone-warn', 'chip: shrinking chip is warn tone');

const noLcaChips = chipTexts('chip_no_lca');
assert(noLcaChips.indexOf('No LCA record') !== -1, 'chip: "No LCA record" fires when lca is null');
assert(chipTones('chip_no_lca')['No LCA record'] === 'tone-warn', 'chip: no-LCA chip is warn tone');

const stretchChips = chipTexts('chip_stretch');
assert(stretchChips.indexOf('Level stretch') !== -1, 'chip: "Level stretch" fires when level_fit is stretch');
const underChips = chipTexts('chip_under');
assert(underChips.indexOf('Below level') !== -1, 'chip: "Below level" fires when level_fit is under');

const dupChips = chipTexts('chip_duplicate');
assert(dupChips.indexOf('Seen before') !== -1, 'chip: "Seen before" fires when duplicate_of is set');

const shortChips = chipTexts('chip_short');
assert(shortChips.some(function (t) { return t.indexOf('Short capture · 640 chars') === 0; }), 'chip: "Short capture · N chars" fires when capture_quality != ok');

// Older jobs lacking sponsorship_flag / level_fit must not guess a chip.
const oldEval = { fit_score: 70, recommendation: 'TAILOR', resume_version: 'operations' }; // no sponsorship_flag, no level_fit
const oldJob = baseJob({ status: 'scored', evaluation: oldEval, id: 'job-old' });
dom.window.jobs = jobList.concat([oldJob]);
dom.window.expandedId = oldJob.id;
dom.window.render();
const oldChips = Array.from(doc.getElementById('body-job-old').querySelectorAll('.chips-row .chip')).map(function (c) { return c.textContent; });
assert(oldChips.indexOf('No sponsorship in the JD') === -1, 'chip: missing sponsorship_flag is omitted, never guessed');
assert(oldChips.indexOf('Level stretch') === -1 && oldChips.indexOf('Below level') === -1, 'chip: missing level_fit is omitted, never guessed');
dom.window.jobs = jobList; // restore
dom.window.render();

// =====================================================================
// 4. Score colour thresholds
// =====================================================================
console.log('\n-- Score colour --');
expand('score_low');
const lowScoreEl = cardFor('score_low').querySelector('.card-header .card-score');
assert(lowScoreEl.className.indexOf('tone-muted') !== -1, 'score < 50 gets tone-muted');
expand('score_mid');
const midScoreEl = cardFor('score_mid').querySelector('.card-header .card-score');
assert(midScoreEl.className.indexOf('tone-warn') !== -1, 'score 50-69 gets tone-warn');
expand('scored');
const highScoreEl = cardFor('scored').querySelector('.card-header .card-score');
assert(highScoreEl.className.indexOf('tone-ok') !== -1, 'score >= 70 gets tone-ok');
const highRecEl = cardFor('scored').querySelector('.card-header .card-rec');
assert(highRecEl.className.indexOf('tone-ok') !== -1, 'recommendation word matches the score tone');
assert(cardFor('captured').querySelector('.card-header .card-score') === null, 'no score shown when evaluation is absent');

// =====================================================================
// 5. The decision row at the bottom of the card
// =====================================================================
console.log('\n-- Decision row per status --');
function actionArea(status) { expand(status); return cardFor(status).querySelector('.action-area'); }
function pairButtons(status) {
  const pair = actionArea(status) && actionArea(status).querySelector('.action-pair');
  return pair ? Array.from(pair.querySelectorAll('button')) : [];
}
function pairLabels(status) { return pairButtons(status).map(function (b) { return b.textContent.trim(); }); }
function filledLabel(status) {
  const b = pairButtons(status).find(function (x) { return /\bprimary\b/.test(x.className); });
  return b ? b.textContent.trim() : '';
}

assert(pairLabels('captured').join('|') === 'Skip|Evaluate', 'captured: Skip left, Evaluate right, got ' + pairLabels('captured').join('|'));
assert(filledLabel('captured') === 'Evaluate', 'captured: Evaluate is the filled button');
assert(pairButtons('captured_empty').length === 0, 'captured+empty: no buttons');
assert(/Nothing captured/.test(actionArea('captured_empty').textContent), 'captured+empty: shows re-capture guidance line instead');
assert(pairLabels('scored').join('|') === 'Skip|Approve and build', 'scored: Skip left, Approve right');
assert(filledLabel('scored') === 'Approve and build', 'scored TAILOR: Approve is the filled button');
assert(!!cardFor('scored').querySelector('#cover-' + jobsByStatus.scored.id), 'scored: cover-letter toggle sits above the pair');
assert(pairLabels('awaiting').join('|') === 'Skip|Approve and build', 'awaiting: same pair');
assert(pairLabels('questions').join('|') === 'Skip', 'questions: only Skip in the pair; Submit lives in the questions block');
assert(pairButtons('building').length === 0 && !!actionArea('building').querySelector('.build-progress, .working-timer, .stage-status-text'), 'building: no buttons, progress shown');
assert(pairButtons('evaluating').length === 0 && !!actionArea('evaluating').querySelector('.working-timer'), 'evaluating: no buttons, a live timer instead');
assert(pairLabels('built').join('|') === 'Skip|Mark submitted', 'built: a small Skip then Mark submitted, got ' + pairLabels('built').join('|'));
assert(/skip-small/.test(pairButtons('built')[0].className) && /btn-icon/.test(pairButtons('built')[0].className), 'built: the Skip is the small square icon button');
assert(!!pairButtons('built')[0].querySelector('.icon svg') && /sr-only/.test(pairButtons('built')[0].querySelector('span:not(.icon)').className), 'built: the small Skip shows the icon and hides its word');
assert(filledLabel('built') === 'Mark submitted', 'built: Mark submitted is the filled button');
assert(!/Open the/.test(actionArea('built_with_cover').textContent), 'built with cover letter: no Open the documents button anywhere');
assert(/Desktop/.test(actionArea('built_with_cover').textContent), 'built with desktop copies: a muted line says so');
assert(pairLabels('applied').join('|') === "Don't reach out|Find people",
  "applied: asks once whether to find people, Don't reach out then Find people, got " + pairLabels('applied').join('|'));
assert(/Find people at Northbridge Logistics to reach out to\?/.test(actionArea('applied').textContent), 'applied: the question names the company');
assert(!!actionArea('applied').querySelector('input[type=url]'), 'applied with no company link: asks for it in the same place');
assert(pairButtons('applied_people_review').length === 0 && /4 people found\. Approve each one/.test(actionArea('applied_people_review').textContent),
  'applied with people waiting: no buttons on the card, says they need approval first');
assert(pairButtons('applied_outreach_ready').length === 0 && /3 people found/.test(actionArea('applied_outreach_ready').textContent),
  'applied with people found: no buttons, says how many');
assert(pairLabels('built_external').join('|') === 'Skip|Mark submitted', 'built elsewhere: Skip then Mark submitted, got ' + pairLabels('built_external').join('|'));
assert(/Referral build/.test(actionArea('built_external').textContent), 'built elsewhere: shows the folder');
assert(/Built it elsewhere/.test(actionArea('scored').textContent), 'scored: offers Built it elsewhere');
assert(!/Built it elsewhere/.test(actionArea('built').textContent), 'built: does not offer Built it elsewhere');
assert(pairButtons('skipped').length === 0, 'skipped: no buttons');
Array.prototype.forEach.call(doc.querySelectorAll('.action-pair > button'), function (b) {
  assert(/\bprimary\b|\bbtn-secondary\b|\bbtn-icon\b/.test(b.className), 'every decision button is a real button: ' + b.textContent.trim());
});

// The filled button follows the recommendation: on a SKIP the blue one is Skip.
(function () {
  const j = jobsByStatus['scored'];
  const keep = j.evaluation.recommendation;
  j.evaluation.recommendation = 'SKIP'; dom.window.jobs = jobList; expand('scored');
  assert(filledLabel('scored') === 'Skip', 'scored SKIP: Skip becomes the filled button, got "' + filledLabel('scored') + '"');
  j.evaluation.recommendation = keep; dom.window.jobs = jobList; expand('scored');
  // and a low score alone does it, whatever the recommendation says (a 38 BASE example)
  const keepScore = j.evaluation.fit_score;
  j.evaluation.fit_score = 38; dom.window.jobs = jobList; expand('scored');
  assert(filledLabel('scored') === 'Skip', 'scored 38 with a BASE call: Skip is still the filled button, got "' + filledLabel('scored') + '"');
  // three tiers of build button
  function buildBtn() { return pairButtons('scored').find(function (b) { return /Approve/.test(b.textContent); }); }
  j.evaluation.fit_score = 60; dom.window.jobs = jobList; expand('scored');
  assert(/btn-mid/.test(buildBtn().className) && filledLabel('scored') === '', 'scored 60: build button is the outlined accent mid tier, nothing filled');
  j.evaluation.fit_score = 85; dom.window.jobs = jobList; expand('scored');
  assert(/\bprimary\b/.test(buildBtn().className), 'scored 85: build button is the full filled tier');
  j.evaluation.fit_score = 40; dom.window.jobs = jobList; expand('scored');
  assert(/btn-low/.test(buildBtn().className) && filledLabel('scored') === 'Skip', 'scored 40: build button goes quiet and Skip takes the blue');
  j.evaluation.fit_score = keepScore; dom.window.jobs = jobList; expand('scored');
})();

// =====================================================================
// 6. The folder icon lives small in the header, under the score
// =====================================================================
console.log('\n-- Folder icon --');
function folderIcon(status) { expand(status); return cardFor(status).querySelector('.card-header .btn-icon[aria-label="Open folder"]'); }
assert(!!folderIcon('scored') && folderIcon('scored').getAttribute('aria-label') === 'Open folder', 'scored: folder icon in the header with an accessible name');
assert(!!folderIcon('built'), 'built: folder icon still in the header');
assert(/btn-icon-sm/.test(folderIcon('built').className), 'the folder icon is the small variant');
(function () { dom.window.expandedId = null; dom.window.render(); })();
assert(!cardFor('built').querySelector('.card-header .btn-icon'), 'collapsed card: no folder icon');
assert(!doc.querySelector('.text-btn'), 'no hyperlink-styled actions remain anywhere');

// (the old secondary-actions row is gone: its contents live in the decision row and the header folder icon, tested above)

// =====================================================================
// 7. Radio questions (v2) render with the right number of inputs; submit disabled until answered
// =====================================================================
console.log('\n-- Radio questions (v2) --');
expand('questions');
const qJob = jobsByStatus.questions;
const qBlock = doc.getElementById('questions-' + qJob.id);
assert(!!qBlock, 'questions block renders with a scroll-target id');
const questionItems = qBlock.querySelectorAll('.question-item');
assert(questionItems.length === 3, 'renders one .question-item per question, got ' + questionItems.length);
const radios = qBlock.querySelectorAll('input[type="radio"]');
assert(radios.length === 5, 'renders 5 radio inputs total (2 options + 3 options across the two choice questions), got ' + radios.length);
const smartsheetNames = new Set(Array.from(qBlock.querySelectorAll('input[type="radio"]')).map(function (r) { return r.name; }));
assert(smartsheetNames.size === 2, 'radio name is unique per question id (2 distinct groups for 2 non-text questions), got ' + smartsheetNames.size);
assert(qBlock.querySelectorAll('textarea').length === 2, 'the type:"text" question renders a textarea, plus the "anything to add" textarea, got ' + qBlock.querySelectorAll('textarea').length);
const whyLines = Array.from(qBlock.querySelectorAll('.question-why')).map(function (n) { return n.textContent; });
assert(whyLines.indexOf('The JD names it as a core tool') !== -1, 'the "why" line renders in muted text under its question');

const submitBtn = doc.getElementById('submit-answers-' + qJob.id);
assert(!!submitBtn, 'submit button exists');
assert(submitBtn.disabled === true, 'submit disabled before any non-text question is answered');

// Answer the first radio question only.
const firstRadio = qBlock.querySelector('input[type="radio"]');
firstRadio.checked = true;
firstRadio.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
assert(doc.getElementById('submit-answers-' + qJob.id).disabled === true, 'submit stays disabled with only one of two choice questions answered');

// Answer the second choice question too (people_mgmt) - pick its first radio.
const peopleMgmtRadio = qBlock.querySelectorAll('input[name="q-' + qJob.id + '-people_mgmt"]')[0];
peopleMgmtRadio.checked = true;
peopleMgmtRadio.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
assert(doc.getElementById('submit-answers-' + qJob.id).disabled === false, 'submit enabled once every non-text question has a selection (text question exempt)');

// =====================================================================
// 8. Legacy string questions render as a textarea
// =====================================================================
console.log('\n-- Legacy string questions --');
expand('questions_legacy');
const legacyJob = jobsByStatus.questions_legacy;
const legacyBlock = doc.getElementById('questions-' + legacyJob.id);
const legacyItems = legacyBlock.querySelectorAll('.question-item');
assert(legacyItems.length === 2, 'renders one .question-item per legacy string question, got ' + legacyItems.length);
assert(legacyBlock.querySelectorAll('input[type="radio"]').length === 0, 'legacy string questions render no radios');
assert(legacyBlock.querySelectorAll('textarea').length === 3, 'each legacy question renders a textarea (2) plus the anything-to-add textarea (1), got ' + legacyBlock.querySelectorAll('textarea').length);
assert(legacyItems[0].querySelector('.question-text').textContent === legacyQuestions[0], 'legacy question text renders verbatim');
assert(doc.getElementById('submit-answers-' + legacyJob.id).disabled === false, 'submit is enabled for an all-legacy question set (no non-text question requires a selection)');

// =====================================================================
// 9. Drafts survive a forced re-render
// =====================================================================
console.log('\n-- Draft persistence --');
expand('captured');
const askInputBefore = cardFor('captured').querySelector('.ask-input-row .ask-input');
askInputBefore.value = 'Is this remote-friendly?';
askInputBefore.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
assert(dom.window.drafts[jobsByStatus.captured.id].ask === 'Is this remote-friendly?', 'typing into the ask input updates the drafts store');
dom.window.render();
const askInputAfter = doc.getElementById('body-' + jobsByStatus.captured.id).querySelector('.ask-input-row .ask-input');
assert(askInputAfter !== askInputBefore, 'render() rebuilt the DOM node (sanity check)');
assert(askInputAfter.value === 'Is this remote-friendly?', 'ask draft text survives a forced re-render');

expand('questions');
const noteAreaBefore = doc.getElementById('questions-' + qJob.id).querySelector('.question-note-wrap textarea');
noteAreaBefore.value = 'One more thing.';
noteAreaBefore.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
dom.window.render();
const noteAreaAfter = doc.getElementById('questions-' + qJob.id).querySelector('.question-note-wrap textarea');
assert(noteAreaAfter.value === 'One more thing.', 'the "anything to add" draft survives a forced re-render');
const radioAfterRerender = doc.getElementById('questions-' + qJob.id).querySelectorAll('input[name="q-' + qJob.id + '-smartsheet"]')[0];
assert(radioAfterRerender.checked === true, 'a selected radio choice survives a forced re-render');

// =====================================================================
// 10. Filter counts
// =====================================================================
console.log('\n-- Filter counts --');
dom.window.currentFilter = 'all';
dom.window.render();
function countText(filter) { return doc.getElementById('count-' + filter).textContent; }
assert(countText('all') === String(jobList.length), '"All" count equals the full job list length, got ' + countText('all'));

// Active is everything still in play, whether it waits on you or on the machine.
const ACTIVE_STATUSES = ['captured', 'scored', 'awaiting', 'questions', 'built', 'built_external', 'error', 'needs_login', 'evaluating', 'building', 'queued'];
const expectedActive = jobList.filter(function (j) { return ACTIVE_STATUSES.indexOf(j.status) !== -1; }).length;
const expectedApplied = jobList.filter(function (j) { return j.status === 'applied'; }).length;
const expectedSkipped = jobList.filter(function (j) { return j.status === 'skipped'; }).length;
assert(countText('active') === String(expectedActive), '"Active" count covers waiting and running jobs, got ' + countText('active') + ' expected ' + expectedActive);
assert(countText('applied') === String(expectedApplied) && countText('skipped') === String(expectedSkipped),
  '"Applied" and "Skipped" count their own jobs, got ' + countText('applied') + '/' + countText('skipped'));
assert(!doc.querySelector('.filter-btn[data-filter="done"]'), 'the unclear Done filter is gone');
assert(Array.prototype.map.call(doc.querySelectorAll('.filter-btn'), function (b) { return b.getAttribute('data-filter'); }).join('|') === 'active|process|applied|skipped|all',
  'filters read Active, In process, Applied, Skipped, All');
assert(!doc.querySelector('.filter-btn[data-filter="needs-me"]') && !doc.querySelector('.filter-btn[data-filter="working"]'), 'the old Needs me and Working filters are gone');

// The list is grouped: what needs you, then what is running, then what is done.
(function () {
  dom.window.currentFilter = 'all'; dom.window.render();
  const heads = Array.prototype.map.call(doc.querySelectorAll('.group-head'), function (el) { return el.getAttribute('data-group'); });
  assert(heads.join('|') === 'needs|working|applied|skipped', 'group headings appear in order needs, working, applied, skipped, got ' + heads.join('|'));
  const firstHead = doc.querySelector('.group-head');
  assert(/Needs you/.test(firstHead.textContent) && /\d/.test(firstHead.querySelector('.group-count').textContent), 'the first heading reads Needs you and carries a count');
  // inside Needs you, a question comes before a built job, which comes before a captured one
  const order = Array.prototype.map.call(doc.querySelectorAll('.group-head, .card'), function (el) {
    return el.classList.contains('group-head') ? 'HEAD:' + el.getAttribute('data-group') : (el.getAttribute('data-id') || 'card');
  });
  const needsCards = [];
  let inNeeds = false;
  Array.prototype.forEach.call(doc.querySelectorAll('.group-head, .card'), function (el) {
    if (el.classList.contains('group-head')) { inNeeds = el.getAttribute('data-group') === 'needs'; return; }
    if (inNeeds) needsCards.push(el);
  });
  assert(needsCards.length > 3, 'the Needs you group holds the waiting jobs, got ' + needsCards.length);
  const bodyIds = needsCards.map(function (el) { return el.querySelector('.card-body').id.replace('body-', ''); });
  assert(bodyIds.indexOf(jobsByStatus.questions.id) < bodyIds.indexOf(jobsByStatus.built.id)
    && bodyIds.indexOf(jobsByStatus.built.id) < bodyIds.indexOf(jobsByStatus.captured.id),
    'inside Needs you the order is answer, then upload, then evaluate, got ' + bodyIds.join(','));
  // a built job whose revision is running counts as working, not as needing you
  jobsByStatus.built.revising = { doc: 'resume', started_at: '2026-09-29T10:00:00' };
  dom.window.render();
  let seen = null, group = null;
  Array.prototype.forEach.call(doc.querySelectorAll('.group-head, .card'), function (el) {
    if (el.classList.contains('group-head')) { group = el.getAttribute('data-group'); return; }
    if (el.querySelector('.card-body').id === 'body-' + jobsByStatus.built.id) seen = group;
  });
  assert(seen === 'working', 'a built job being revised sits under Working, got ' + seen);
  delete jobsByStatus.built.revising;
  // one group on its own needs no heading
  dom.window.currentFilter = 'skipped'; dom.window.render();
  assert(!doc.querySelector('.group-head'), 'a single-group list shows no heading');
  dom.window.currentFilter = 'all'; dom.window.render();
})();

// Selecting a filter hides non-matching cards.
const filterBtn = doc.querySelector('.filter-btn[data-filter="applied"]');
filterBtn.dispatchEvent(new dom.window.Event('click', { bubbles: true }));
assert(dom.window.currentFilter === 'applied', 'clicking a filter button updates currentFilter');
assert(doc.getElementById('body-' + jobsByStatus.applied.id) !== null, '"Applied" filter shows an applied job');
assert(doc.getElementById('body-' + jobsByStatus.captured.id) === null, '"Applied" filter hides a captured job');
// Just submitted: the card stays in Active, under Needs you, until you answer the reach-out question.
jobsByStatus.applied.outreach_pending = true;
dom.window.currentFilter = 'active'; dom.window.render();
assert(doc.getElementById('body-' + jobsByStatus.applied.id) !== null, 'a just-submitted job stays in Active until you answer');
assert(/reach out to people\?/.test(doc.getElementById('body-' + jobsByStatus.applied.id).closest('.card').textContent), 'its status asks whether to reach out');
(function () {
  let group = null, seen = null;
  Array.prototype.forEach.call(doc.querySelectorAll('.group-head, .card'), function (el) {
    if (el.classList.contains('group-head')) { group = el.getAttribute('data-group'); return; }
    if (el.querySelector('.card-body').id === 'body-' + jobsByStatus.applied.id) seen = group;
  });
  assert(seen === 'needs', 'it sits under Needs you, got ' + seen);
})();
jobsByStatus.applied.outreach_pending = false; jobsByStatus.applied.outreach_decision = 'pass';
dom.window.render();
assert(doc.getElementById('body-' + jobsByStatus.applied.id) === null, 'once you answer no, it leaves Active');
dom.window.currentFilter = 'applied'; dom.window.render();
delete jobsByStatus.applied.outreach_decision; delete jobsByStatus.applied.outreach_pending;
assert(filterBtn.className.indexOf('active') !== -1, 'the selected filter button carries the active class');

// Active is the default the panel starts on.
assert(/'active'/.test(jsSource.split('var currentFilter =')[1].split('\n')[0]), 'the panel starts on the Active filter');
// Restore default filter for anything after this point.
dom.window.currentFilter = 'all';
dom.window.render();

// =====================================================================
// Bonus: preserved behaviours
// =====================================================================
console.log('\n-- Preserved behaviours --');
assert(/\.card-header\s*{[^}]*position:\s*sticky;[^}]*top:\s*0;[^}]*}/.test(cssSource), 'CSS pins .card-header with position: sticky; top: 0');
assert(/\.card-header\s*{[^}]*border-bottom:\s*1px solid var\(--border\);[^}]*}/.test(cssSource), 'CSS gives .card-header a bottom border');
assert(/\.card\s*{[^}]*flex:\s*0 0 auto;[^}]*}/.test(cssSource), 'CSS keeps flex: 0 0 auto on .card (load-bearing sticky fix)');
assert(/#jobs-list(?:, #li-view)?\s*{[^}]*min-height:\s*0;[^}]*}/.test(cssSource), 'CSS keeps min-height: 0 on #jobs-list (load-bearing sticky fix)');

dom.window.expandedId = jobsByStatus.captured_empty.id;
dom.window.render();
assert(/Nothing captured/.test(actionArea('captured_empty').textContent), '"Nothing captured" guidance shown for an empty capture');

// Health dot / warning line still present and wired.
assert(!!doc.getElementById('health-dot'), 'health dot element preserved (inside the settings sheet)');
assert(doc.getElementById('settings-row').hidden === true, 'settings start hidden behind the gear');
assert(/\[hidden\][\s\S]{0,60}display:\s*none\s*!important/.test(cssSource),
  'a [hidden] guard exists, since id selectors with display:flex would otherwise outrank it');
assert(!!doc.getElementById('settings-btn'), 'a settings gear exists');
(function () {
  const full = dom.window.jobs;
  dom.window.jobs = full.slice(0, 3); dom.window.render();
  assert(doc.getElementById('filter-row').hidden === true, 'filter row hides itself with only a few jobs');
  dom.window.jobs = full; dom.window.render();
  assert(doc.getElementById('filter-row').hidden === false, 'filter row appears once there are enough jobs to lose one');
})();
assert(!!doc.getElementById('warning-line'), 'claude-login warning line element preserved');
assert(!!doc.getElementById('capture-btn'), '"Capture this page" button preserved');
assert(!!doc.getElementById('auto-toggle') && !!doc.getElementById('threshold-input') && !!doc.getElementById('build-model'), 'settings row (auto/threshold/build model) preserved');
// The auto-apply control was removed rather than shown permanently disabled: it did nothing
// and it was the control overflowing the 400px panel.
assert(!doc.getElementById('autoapply-toggle'), 'no dead auto-apply control in the settings row');
assert(!!doc.getElementById('build-model') && !!doc.getElementById('threshold-input') && !!doc.getElementById('auto-toggle'),
  'Auto, Threshold and Build all survive in the settings row');
assert(/#settings-row[\s\S]{0,120}flex-wrap:\s*wrap/.test(cssSource), 'settings row wraps instead of overflowing');
assert(/#settings-row select[\s\S]{0,300}appearance:\s*none/.test(cssSource), 'the model select is themed, not the native slab');

// Markdown-lite + copy button on an assistant message.
const askJob = baseJob({ status: 'scored', evaluation: evaluation, id: 'job-ask', messages: [{ role: 'assistant', text: '- one\n- two' }] });
dom.window.jobs = jobList.concat([askJob]);
dom.window.expandedId = askJob.id;
dom.window.render();
const askCard = doc.getElementById('body-job-ask');
assert(!!askCard.querySelector('.md-list'), 'markdown-lite renders a bullet list from assistant messages');
assert(!!askCard.querySelector('.copy-btn'), 'a Copy button renders on the markdown list block');
dom.window.jobs = jobList;
dom.window.render();

// Empty job list -> empty state.
dom.window.jobs = [];
dom.window.render();
assert(/No jobs yet/.test(jobsListEl().textContent), 'empty job list shows the empty state message');
function jobsListEl() { return doc.getElementById('jobs-list'); }
dom.window.jobs = jobList;
dom.window.currentFilter = 'all';
dom.window.expandedId = null;
dom.window.render();

// =====================================================================
// Live build progress: real phase, render count, elapsed and the stall hint
// =====================================================================
console.log('\n-- Live build progress --');
function renderBuilding(progress) {
  const j = jobsByStatus['building'];
  j.build_progress = progress;
  dom.window.jobs = jobList;
  dom.window.expandedId = j.id;
  dom.window.render();
  return cardFor('building');
}

let card = renderBuilding({ phase: 2, phase_label: 'Measuring every bullet', phases_total: 5,
                            renders: 3, elapsed_s: 380, idle_s: 12 });
let bar = card.querySelector('.build-progress-fill');
assert(!!bar, 'building: a progress bar is rendered when the server reports progress');
assert(bar.style.width === '50%', 'building: phase 2 of 4 fills the bar to 50%, got ' + bar.style.width);
let meta = card.querySelector('.build-progress-meta').textContent;
assert(meta.indexOf('Measuring every bullet') !== -1, 'building: the real phase label is shown');
assert(meta.indexOf('render 3') !== -1, 'building: the render pass count is shown');
assert(!!card.querySelector('.working-timer .elapsed'), 'building: elapsed time is shown by the live timer beside the bar');
assert(!card.querySelector('.build-progress-stall'), 'building: no stall hint while files are changing');

card = renderBuilding({ phase: 0, phase_label: 'Reading the JD, your answers and the profile',
                        phases_total: 5, renders: 0, elapsed_s: 30, idle_s: 25 });
bar = card.querySelector('.build-progress-fill');
assert(bar.style.width === '6%', 'building: phase 0 still shows a visible sliver, got ' + bar.style.width);
assert(card.querySelector('.build-progress-meta').textContent.indexOf('render') === -1,
  'building: no render count before the first render');

card = renderBuilding({ phase: 3, phase_label: 'Checking the page fills', phases_total: 5,
                        renders: 4, elapsed_s: 700, idle_s: 300 });
assert(!!card.querySelector('.build-progress-stall'), 'building: a quiet folder past 4 min shows a reassurance line');

// the collapsed card is live too
jobsByStatus['building'].build_progress = { phase: 2, phase_label: 'Measuring every bullet',
  phases_total: 5, renders: 3, elapsed_s: 125, idle_s: 5 };
dom.window.expandedId = null;
dom.window.render();
let collapsedText = cardFor('building').querySelector('.card-header').textContent;
assert(collapsedText.indexOf('Measuring every bullet') !== -1, 'building: collapsed card shows the phase');
assert(collapsedText.indexOf('2m 5s') !== -1, 'building: collapsed card shows elapsed time');

jobsByStatus['building'].build_progress = null;
dom.window.expandedId = jobsByStatus['building'].id;
dom.window.render();
assert(!cardFor('building').querySelector('.build-progress-fill'),
  'building: falls back to the plain status line when the server reports no progress yet');

// =====================================================================
// Answer options are full-size hit targets, not bare radios
// =====================================================================
console.log('\n-- Answer hit targets --');
dom.window.expandedId = jobsByStatus['questions'].id;
dom.window.render();
const opts = cardFor('questions').querySelectorAll('.question-option');
assert(opts.length >= 2, 'questions: each option renders its own row, got ' + opts.length);
assert(Array.prototype.every.call(opts, function (o) { return o.tagName === 'LABEL' && o.querySelector('input'); }),
  'questions: every option row is a label wrapping its input, so the whole row is clickable');
assert(cssSource.indexOf('.question-option') !== -1 && /min-height:\s*40px/.test(cssSource),
  'questions: option rows are given a 40px minimum height in the stylesheet');
assert(/\.remember-check[\s\S]{0,200}min-height:\s*36px/.test(cssSource),
  'questions: the remember checkbox row is also a large target');

// =====================================================================
// Action set: two real buttons side by side, never more
// =====================================================================
console.log('\n-- Action set --');
assert(pairButtons('built').length === 2, 'built: the small Skip and Mark submitted, got ' + pairButtons('built').length);
assert(filledLabel('built') === 'Mark submitted', 'built: Mark submitted is the filled one');
assert(pairButtons('scored').length === 2, 'scored: exactly two buttons');
assert(pairButtons('applied').length === 2, 'applied: the outreach ask is the only thing left to press');
assert(pairButtons('applied_outreach_ready').length === 0, 'applied with people found: nothing left to press');

// Outreach is held once you are in their process or the application has ended: the server refuses Find people,
// so the card says so instead of offering it (UI audit 2026-10-09, step 1).
(function () {
  const w = dom.window;
  [['heard_back', 'On hold: heard back'], ['assessment', 'On hold: assessment'], ['interviewing', 'On hold: interviewing'],
   ['offer', 'On hold: offer'], ['rejected', 'Closed: rejected'], ['withdrawn', 'Closed: withdrawn']].forEach(function (c) {
    const j = Object.assign({}, jobsByStatus.applied, { stage: c[0], outreach: { state: 'none' } });
    const el = w.outreachBlock(j);
    assert(!!el && el.textContent.trim() === c[1] && !el.querySelector('button, input'), c[0] + ': "' + c[1] + '" and no Find people button');
  });
  const failedHeld = w.outreachBlock(Object.assign({}, jobsByStatus.applied, { stage: 'interviewing', outreach: { state: 'failed', error: 'x' } }));
  assert(!failedHeld.querySelector('button'), 'a failed search on a held job offers no Try again');
  const tracked = w.outreachBlock(Object.assign({}, jobsByStatus.applied_outreach_ready, { stage: 'interviewing' }));
  assert(/3 people found/.test(tracked.textContent), 'a job that already has outreach keeps showing it');
  const open = w.outreachBlock(Object.assign({}, jobsByStatus.applied, { stage: null, outreach: { state: 'none' } }));
  assert(!!open.querySelector('button'), 'an applied job with no stage still gets the Find people prompt');
  const pending = Object.assign({}, jobsByStatus.applied, { stage: 'interviewing', outreach_pending: true });
  assert(!/reach out to people\?/.test(w.statusSentence(pending)), 'a held job does not ask "reach out to people?"');
})();
assert(/\.action-pair > button[\s\S]{0,120}min-height:\s*44px/.test(cssSource), 'decision buttons are at least 44px tall');
assert(/\.btn-icon[\s\S]{0,160}width:\s*40px/.test(cssSource), 'the icon button is a 40px square');

expand('scored');
const toggle = cardFor('scored').querySelector('.toggle-row');
assert(!!toggle && toggle.tagName === 'LABEL' && !!toggle.querySelector('input[type=checkbox]'),
  'scored: the cover letter option is a full-width toggle row, not a cramped checkbox');
assert(toggle.textContent.indexOf('cover letter') !== -1, 'scored: the toggle says what it does');
assert(/\.toggle-row[\s\S]{0,200}min-height:\s*40px/.test(cssSource), 'the toggle row is a 40px target');

dom.window.jobs = jobList;
dom.window.currentFilter = 'all';
dom.window.expandedId = null;
dom.window.render();

// A thin filing history must not read as a green light
console.log('\n-- Sponsorship chip honesty --');
function chipsForLca(lca) {
  const j = jobsByStatus['scored'];
  const keep = j.lca;
  j.lca = lca;
  dom.window.jobs = jobList; dom.window.expandedId = j.id; dom.window.render();
  const out = [...cardFor('scored').querySelectorAll('.chip')].map(function (c) {
    return { text: c.textContent.trim(), tone: c.className };
  });
  j.lca = keep;
  return out;
}
let c = chipsForLca({ filings: 6919, certified: 6915, trend: 'GROWING' });
assert(c.some(function (x) { return /Sponsors · 6,919 filings/.test(x.text) && /ok/.test(x.tone); }),
  'a deep filing history reads green');
c = chipsForLca({ filings: 1, certified: 1, trend: 'NEW IN FY2025' });
assert(c.some(function (x) { return /Sponsored only 1 time\b/.test(x.text) && /warn/.test(x.tone); }),
  'a single filing reads amber and says so, rather than a confident green "1 filings"');
c = chipsForLca({ filings: 451, certified: 382, trend: 'SHRINKING' });
assert(c.some(function (x) { return /shrinking/.test(x.text) && /warn/.test(x.tone); }),
  'a shrinking history still reads amber');

dom.window.jobs = jobList;
dom.window.currentFilter = 'all';
dom.window.expandedId = null;
dom.window.render();

// =====================================================================
// Blocker pills: the reasons a score is low, first, in one glance
// =====================================================================
console.log('\n-- Blocker pills --');
(function () {
  const j = jobsByStatus['scored'];
  j.evaluation.blockers = [
    { label: 'Contract, not W-2', kind: 'contract' },
    { label: 'Needs 8+ years', kind: 'years' },
    { label: 'Pure engineering role', kind: 'domain' },
    { label: 'Fourth one, must be dropped', kind: 'skill' }
  ];
  dom.window.jobs = jobList; expand('scored');
  const chips = Array.from(cardFor('scored').querySelectorAll('.chip'));
  const texts = chips.map(function (c) { return c.textContent.trim(); });
  assert(texts[0] === 'Contract, not W-2', 'blockers come before every other chip, got ' + texts[0]);
  assert(/danger/.test(chips[0].className), 'a contract blocker reads red');
  assert(/warn/.test(chips[1].className), 'a years blocker reads amber');
  assert(chips.filter(function (c) { return /danger|warn/.test(c.className); }).length <= 4, 'blocker pills are capped at four');
  delete j.evaluation.blockers; dom.window.jobs = jobList; expand('scored');
  assert(!cardFor('scored').textContent.includes('Contract, not W-2'), 'a job with no blockers field shows none (older evaluations)');
})();

// The reasoning sits in the open once a card is expanded
expand('scored');
assert(!!cardFor('scored').querySelector('.why-inline .why-card'), 'expanded: reasoning cards render inline, not behind a disclosure');
assert(!!cardFor('scored').querySelector('.why-more'), 'expanded: only the secondary detail stays behind a click');

dom.window.jobs = jobList;
dom.window.currentFilter = 'all';
dom.window.expandedId = null;
dom.window.render();

// =====================================================================
// Pre-screen: deterministic flags at capture, before any evaluation
// =====================================================================
console.log('\n-- Pre-screen --');
(function () {
  const j = jobsByStatus['captured'];
  j.prescreen = [{ kind: 'contract', hard: true, label: 'Contract, not W-2', evidence: 'This is a 1099 contract position.' },
                 { kind: 'years', hard: false, label: 'Asks for 8+ years', evidence: '8+ years of experience' }];
  dom.window.jobs = jobList; expand('captured');
  const card = cardFor('captured');
  const chips = Array.from(card.querySelectorAll('.chip'));
  assert(chips[0] && chips[0].textContent.trim() === 'Contract, not W-2' && /danger/.test(chips[0].className), 'a hard pre-screen hit is the first pill, in red');
  assert(chips[0].getAttribute('title') === 'This is a 1099 contract position.', 'the pill carries the JD sentence as its tooltip');
  assert(/warn/.test(chips[1].className), 'a soft hit reads amber');
  assert(filledLabel('captured') === 'Skip', 'a hard hit makes Skip the filled button before any evaluation');
  assert(/Not worth evaluating/.test(card.querySelector('.action-area').textContent), 'and the card says evaluation is not worth it');
  assert(pairLabels('captured').indexOf('Evaluate') !== -1, 'Evaluate stays available for an override');
  j.prescreen = [];
  j.capture_quality = 'list'; dom.window.jobs = jobList; expand('captured');
  assert(pairLabels('captured').indexOf('Evaluate') === -1, 'a list capture offers no Evaluate at all');
  assert(/job list, not the job/.test(cardFor('captured').textContent), 'a list capture says what went wrong');
  j.capture_quality = 'ok'; dom.window.jobs = jobList; expand('captured');
})();

// Seen before
(function () {
  const j = jobsByStatus['scored'];
  j.seen_before = { id: 'old-one', captured_at: '2026-08-12T10:00:00', status: 'applied', fit_score: 71 };
  dom.window.jobs = jobList; expand('scored');
  assert(/Seen before · 2026-08-12 · scored 71/.test(cardFor('scored').textContent), 'a cross-posted role shows when it was seen and what it scored');
  j.seen_before = null; dom.window.jobs = jobList; expand('scored');
})();

// Auto-build switch
(function () {
  const sw = doc.getElementById('auto-badge');
  assert(sw && sw.tagName === 'BUTTON', 'auto-build is a button, not a badge');
  dom.window.settings = { auto: true, threshold: 70 }; dom.window.renderAutoBadge();
  assert(sw.classList.contains('on') && sw.getAttribute('aria-pressed') === 'true', 'on: green state and pressed');
  dom.window.settings = { auto: false, threshold: 70 }; dom.window.renderAutoBadge();
  assert(!sw.classList.contains('on') && !sw.hidden, 'off: grey but still visible, so it can be turned back on');
})();

// The bolt alone: no label, the words live in the tooltip and the accessible name
(function () {
  const sw = doc.getElementById('auto-badge');
  dom.window.settings = { auto: true, threshold: 70 }; dom.window.renderAutoBadge();
  assert(sw.textContent.trim() === '' && !!sw.querySelector('.icon svg'), 'auto-build shows only the bolt');
  assert(/Auto active/.test(sw.title) && /evaluated at once/.test(sw.title) && sw.getAttribute('aria-label') === 'Auto active', 'on: tooltip and name say active and explain the whole chain');
  dom.window.settings = { auto: false, threshold: 70 }; dom.window.renderAutoBadge();
  assert(/Auto off/.test(sw.title) && sw.getAttribute('aria-label') === 'Auto off', 'off: tooltip and name say off');
  const main = Array.prototype.map.call(doc.getElementById('top-main').children, function (el) { return el.id; });
  assert(main.join('|') === 'capture-btn|top-stack', 'the eye sits left of everything else, got ' + main.join('|'));
  const order = Array.prototype.map.call(doc.getElementById('health-row').children, function (el) { return el.id; });
  assert(order.join('|') === 'search-box|auto-badge|li-btn|bell-btn|settings-btn', 'top row beside the eye: search, bolt, LinkedIn, bell, gear, got ' + order.join('|'));
  const bell = doc.getElementById('bell-btn');
  assert(!!bell.querySelector('svg') && !/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/u.test(bell.textContent), 'the bell is an SVG, no emoji');
  assert(doc.getElementById('bell-count').hidden, 'the bell shows no count until the server says something is waiting');
  const stack = Array.prototype.map.call(doc.getElementById('top-stack').children, function (el) { return el.id; });
  assert(stack.join('|') === 'health-row|filter-row', 'the filter pills sit under the search box, sharing its left edge, got ' + stack.join('|'));
  const si = doc.getElementById('search-input');
  assert(si.placeholder === 'Search' && si.getAttribute('aria-label') === 'Search jobs and descriptions',
    'the search placeholder is one word, the accessible name still says what it searches');
  const cap = doc.getElementById('capture-btn');
  assert(cap.textContent.trim() === '' && !!cap.querySelector('.icon svg') && cap.getAttribute('aria-label') === 'Look at this page', 'the capture button is the eye alone with its name kept');
})();

// =====================================================================
// Search: local match at once, server ids when they arrive, Escape clears
// =====================================================================
console.log('\n-- Search --');
(function () {
  const input = doc.getElementById('search-input');
  dom.window.jobs = jobList; dom.window.currentFilter = 'all'; dom.window.expandedId = null;
  function type(q) { input.value = q; input.dispatchEvent(new dom.window.Event('input')); }
  const total = doc.querySelectorAll('.card').length;
  type('northbridge');
  assert(doc.querySelectorAll('.card').length === total, 'a word every fixture carries keeps every card');
  assert(/searching descriptions/.test(doc.querySelector('.search-note').textContent), 'while the server looks, the note says so');
  type('nothing-like-this-anywhere');
  assert(doc.querySelectorAll('.card').length === 0 && /Nothing mentions/.test(doc.querySelector('.empty-state').textContent), 'no local match: an empty state names the query');
  // the server answer wins once it arrives
  dom.window.searchQuery = 'nothing-like-this-anywhere';
  dom.window.searchIds = [jobsByStatus.built.id];
  dom.window.render();
  const shown = Array.prototype.map.call(doc.querySelectorAll('.card'), function (c) { return c.getAttribute('data-id') || c.id; });
  assert(doc.querySelectorAll('.card').length === 1, 'server ids narrow the list to the matched job, got ' + doc.querySelectorAll('.card').length);
  assert(!/searching descriptions/.test(doc.querySelector('.search-note').textContent), 'once the server answered the note stops saying searching');
  input.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape' }));
  assert(input.value === '' && doc.querySelectorAll('.card').length === total, 'Escape clears the search and every card returns');
  // the search composes with the status filter
  type('northbridge');
  dom.window.currentFilter = 'applied'; dom.window.render();
  assert(doc.querySelectorAll('.card').length < total, 'search and the status filter apply together');
  type('');
  dom.window.currentFilter = 'all'; dom.window.render();
})();

// =====================================================================
// Evaluate again: the refresh beside the folder, the date line, the changed-posting row
// =====================================================================
console.log('\n-- Evaluate again --');
(function () {
  expand('scored');
  var hdr = cardFor('scored').querySelector('.card-header');
  var again = hdr.querySelector('.btn-icon[aria-label="Evaluate again"]');
  assert(!!again, 'scored: an Evaluate again icon sits in the header');
  assert(hdr.querySelector('.stage-status-text').textContent.trim() === '', 'scored, no timestamp on record: the header line stays empty rather than guessing');
  expand('built');
  assert(!!cardFor('built').querySelector('.card-header .btn-icon[aria-label="Evaluate again"]'), 'built: Evaluate again is offered too');
  expand('captured');
  assert(!cardFor('captured').querySelector('.card-header .btn-icon[aria-label="Evaluate again"]'), 'captured: nothing to evaluate again');
  expand('evaluating');
  assert(!cardFor('evaluating').querySelector('.card-header .btn-icon[aria-label="Evaluate again"]'), 'evaluating: no second evaluate while one runs');
  var calls = [];
  var realFetch = dom.window.fetch;
  dom.window.fetch = function (url, opts) { calls.push(String(url)); return realFetch(url, opts); };
  expand('scored');
  cardFor('scored').querySelector('.card-header .btn-icon[aria-label="Evaluate again"]').click();
  assert(!calls.some(function (u) { return /\/jobs\/[^/]+\/evaluate$/.test(u); }), 'one click on Evaluate again does not run it');
  var armedBtn = cardFor('scored').querySelector('.card-header .btn-icon.armed');
  assert(!!armedBtn && /Again\?/.test(armedBtn.textContent) && /Click again/.test(armedBtn.getAttribute('aria-label')),
    'it arms instead and says to click again');
  armedBtn.click();
  dom.window.fetch = realFetch;
  assert(calls.some(function (u) { return /\/jobs\/[^/]+\/evaluate$/.test(u); }), 'the second click posts to /evaluate');
  assert(cardFor('scored') && cardFor('scored').className.indexOf('collapsed') === -1, 'the click did not collapse the card');
  // a posting that changed since the evaluation
  jobsByStatus.scored.jd_changed = { at: '2026-09-14T15:58:00', old_chars: 4214, new_chars: 5300 };
  jobsByStatus.scored.evaluated_at = '2026-09-14T15:02:44';
  dom.window.render(); expand('scored');
  var card = cardFor('scored');
  assert(/Posting changed since evaluated/.test(card.textContent), 'a changed posting shows its pill');
  var row = card.querySelector('.action-area .changed-row button');
  assert(!!row && /Evaluate again/.test(row.textContent), 'and a full Evaluate again button above the decision row');
  assert(/Sep 14/.test(card.querySelector('.card-header .stage-status-text').textContent), 'the evaluated date renders from evaluated_at');
  delete jobsByStatus.scored.jd_changed; delete jobsByStatus.scored.evaluated_at;
  dom.window.render();
})();

// =====================================================================
// Chat icon, feedback form, revising overlay, the employer's own asks
// =====================================================================
console.log('\n-- Feedback and chat --');
(function () {
  expand('built');
  var card = cardFor('built');
  var chat = card.querySelector('.card-header .btn-icon[aria-label="Ask about this job"]');
  assert(!!chat && chat.querySelector('.icon svg line'), 'a Claude spark icon sits in the header');
  assert(!!cardFor('built').querySelector('.skip-small .icon svg polygon'), 'Skip buttons carry the skip-forward icon, not the X');
  var ask = card.querySelector('.ask-details');
  assert(ask && !ask.open, 'the Ask section starts closed');
  chat.click();
  assert(ask.open, 'clicking the chat icon opens the Ask section');
  var fb = card.querySelector('.feedback-details');
  assert(!!fb && /Feedback/.test(fb.querySelector('summary').textContent), 'a feedback section sits under the documents');
  var chips = fb.querySelectorAll('.fb-chip');
  assert(chips.length === 2 && /active/.test(chips[0].className), 'Resume and Cover letter chips, resume chosen by default');
  var send = fb.querySelector('.fb-send');
  assert(send.disabled && /Revise the resume/.test(send.textContent), 'the button says Revise the resume and waits for text');
  assert(!!send.querySelector('.icon svg') && send.querySelector('span:not(.icon)').textContent === 'Revise the resume', 'the label lives in the label span, the icon keeps its svg');
  chips[1].click();
  assert(/Write the cover letter with this/.test(send.textContent), 'with no cover letter the cover chip turns the button into a write');
  var ta = fb.querySelector('.fb-text');
  ta.value = 'Answer their two questions'; ta.dispatchEvent(new dom.window.Event('input'));
  assert(!send.disabled, 'text enables the button');
  var posted = [];
  var rf = dom.window.fetch;
  dom.window.fetch = function (url, opts) { posted.push({ url: String(url), body: opts && opts.body }); return rf(url, opts); };
  send.click();
  dom.window.fetch = rf;
  assert(posted.some(function (p) { return /\/cover$/.test(p.url) && /"instructions":"Answer their two questions"/.test(p.body); }), 'it posts the text as cover letter instructions');
  expand('built_with_cover');
  var fb2 = cardFor('built_with_cover').querySelector('.feedback-details');
  var d2 = dom.window.getDraft(jobsByStatus.built_with_cover.id); d2.fbDoc = 'cover'; d2.fb = 'Shorter second paragraph';
  dom.window.render(); expand('built_with_cover');
  fb2 = cardFor('built_with_cover').querySelector('.feedback-details');
  assert(/Revise the cover letter/.test(fb2.querySelector('.fb-send').textContent), 'with a cover letter the button revises it');
  posted = [];
  dom.window.fetch = function (url, opts) { posted.push({ url: String(url), body: opts && opts.body }); return rf(url, opts); };
  fb2.querySelector('.fb-send').click();
  dom.window.fetch = rf;
  assert(posted.some(function (p) { return /\/revise$/.test(p.url) && /"doc":"cover"/.test(p.body) && /Shorter second/.test(p.body); }), 'it posts feedback to /revise for the cover letter');
  // revising overlay
  jobsByStatus.built.revising = { doc: 'resume', started_at: '2026-09-14T16:40:00' };
  dom.window.render(); expand('built');
  assert(!!cardFor('built').querySelector('.doc-tile[data-doc="resume"] .thumb.revising .working-timer'), 'the resume tile carries a timer while it is revised');
  delete jobsByStatus.built.revising;
  // the employer's own asks
  jobsByStatus.built.cover_requirements = ['In your cover letter, please tell us why this role.'];
  delete dom.window.drafts[jobsByStatus.built.id];
  dom.window.render(); expand('built');
  var fb3 = cardFor('built').querySelector('.feedback-details');
  assert(fb3.open && /The posting asks for this in the letter/.test(fb3.textContent), 'a posting with its own asks opens the section and lists them');
  assert(/tell us why this role/.test(fb3.querySelector('.fb-text').value) && /active/.test(fb3.querySelectorAll('.fb-chip')[1].className), 'the asks are prefilled and Cover letter is chosen');
  delete jobsByStatus.built.cover_requirements; delete dom.window.drafts[jobsByStatus.built.id];
  dom.window.render();
  // the desktop note is small
  expand('built_with_cover');
  assert(!!cardFor('built_with_cover').querySelector('.small-note'), 'the Desktop note is the small variant');
  // the stubbed posts never resolve inside this synchronous file, so clear the in-flight marks
  for (var k in dom.window.inFlight) delete dom.window.inFlight[k];
  dom.window.render();
})();

// =====================================================================
// The Ask box: one voice, icon-only send, one block and one copy per answer
// =====================================================================
console.log('\n-- Ask box --');
(function () {
  jobsByStatus.scored.messages = [
    { role: 'user', text: 'What are your salary expectations?' },
    { role: 'assistant', text: '**Salary expectations**\nOpen to discussion based on total compensation.' }
  ];
  dom.window.render(); expand('scored');
  var card = cardFor('scored');
  assert(!card.querySelector('.ask-mode'), 'no mode toggle: the box always answers as you');
  var send = card.querySelector('.ask-input-row .ask-send');
  assert(!!send && send.getAttribute('aria-label') === 'Send' && !!send.querySelector('.icon svg') && /sr-only/.test(send.querySelector('span:not(.icon)').className), 'send is an icon-only button with an accessible name');
  var cp = card.querySelector('.msg.assistant .msg-copy');
  assert(!!cp && cp.getAttribute('aria-label') === 'Copy' && !!cp.querySelector('.icon svg') && /btn-icon-sm/.test(cp.className), 'each answer has an icon-only copy button');
  assert(!card.querySelector('.msg .role'), 'no role labels above messages');
  var q = card.querySelector('.msg.assistant .md-q');
  assert(!!q && q.textContent === 'Salary expectations' && !/\*\*/.test(card.querySelector('.msg.assistant').textContent), 'a bold question line renders as a heading, no raw asterisks');
  var copied = null;
  dom.window.navigator.clipboard = { writeText: function (t) { copied = t; return Promise.resolve(); } };
  cp.click();
  assert(copied === 'Open to discussion based on total compensation.', 'copy gives the answer alone, without the heading or markers, got ' + JSON.stringify(copied));
  // several questions: one block and one copy per answer
  jobsByStatus.scored.messages = [
    { role: 'user', text: 'Why us?\nSalary?' },
    { role: 'assistant', text: '**Why Globex**\nBecause of the work.\n\nSecond paragraph.\n**Salary expectations**\nOpen to discussion.' }
  ];
  dom.window.render(); expand('scored'); card = cardFor('scored');
  var answers = card.querySelectorAll('.msg.assistant .answer');
  assert(answers.length === 2 && answers[0].querySelector('.md-q').textContent === 'Why Globex' && answers[1].querySelector('.md-q').textContent === 'Salary expectations', 'two questions render as two answer blocks with their headings');
  assert(card.querySelectorAll('.msg.assistant .msg-copy').length === 2, 'one copy button per answer');
  answers[0].querySelector('.msg-copy').click();
  assert(copied === 'Because of the work.\n\nSecond paragraph.', 'copying the first answer gives only that answer, got ' + JSON.stringify(copied));
  assert(answers[0].querySelectorAll('p:not(.md-q)').length === 2, 'paragraphs inside an answer stay separate');
  // a plain reply with no question line is one block with one copy
  jobsByStatus.scored.messages = [{ role: 'user', text: 'Remote?' }, { role: 'assistant', text: 'Hybrid, three days in Denver.' }];
  dom.window.render(); expand('scored'); card = cardFor('scored');
  assert(card.querySelectorAll('.msg.assistant .answer').length === 1 && !card.querySelector('.msg.assistant .md-q'), 'a plain reply is one block without a heading');
  var posted = [];
  var rf = dom.window.fetch;
  dom.window.fetch = function (url, opts) { posted.push({ url: String(url), body: opts && opts.body }); return rf(url, opts); };
  var ta = card.querySelector('.ask-input'); ta.value = 'Why us?'; ta.dispatchEvent(new dom.window.Event('input'));
  card.querySelector('.ask-input-row .ask-send').click();
  dom.window.fetch = rf;
  assert(posted.some(function (p) { return /\/ask$/.test(p.url) && /"text":"Why us\?"/.test(p.body); }), 'send posts the text to /ask');
  for (var k in dom.window.inFlight) delete dom.window.inFlight[k];
  jobsByStatus.scored.messages = []; delete dom.window.drafts[jobsByStatus.scored.id]; dom.window.render();
})();

// =====================================================================
// Open questions on a built card
// =====================================================================
console.log('\n-- Questions after the build --');
(function () {
  jobsByStatus.built.questions = v2Questions.slice(0, 1);
  dom.window.render(); expand('built');
  var card = cardFor('built');
  var blk = card.querySelector('.questions-block');
  assert(!!blk && /Built without these/.test(blk.textContent), 'a built card with open questions shows them with the note');
  assert(/Answer and revise/.test(blk.querySelector('#submit-answers-' + jobsByStatus.built.id).textContent), 'the button says Answer and revise');
  jobsByStatus.built.revising = { doc: 'resume', started_at: '2026-09-21T12:00:00' };
  dom.window.render(); expand('built');
  assert(!cardFor('built').querySelector('.questions-block'), 'while the revision runs the questions block is hidden');
  delete jobsByStatus.built.revising; jobsByStatus.built.questions = []; dom.window.render();
})();

// =====================================================================
// Status icon and colour on every card
// =====================================================================
console.log('\n-- Status at a glance --');
(function () {
  dom.window.expandedId = null; dom.window.currentFilter = 'all'; dom.window.render();
  const iconOf = function (status) {
    const el = cardFor(status).querySelector('.card-stage-row .status-icon');
    return el ? { tone: (el.className.match(/tone-(\w+)/) || [])[1], svg: el.innerHTML.length > 20, title: el.getAttribute('title') } : null;
  };
  const expect = { captured: 'accent', scored: 'accent', questions: 'warn', building: 'muted',
                   evaluating: 'muted', built: 'ok', applied: 'ok', skipped: 'muted', error: 'danger' };
  Object.keys(expect).forEach(function (st) {
    const got = iconOf(st);
    assert(got && got.tone === expect[st] && got.svg, st + ': status icon in the ' + expect[st] + ' tone, got ' + JSON.stringify(got));
    assert(got.title === dom.window.statusSentence(jobsByStatus[st]), st + ': the icon carries the status sentence as its tooltip');
  });
  assert(/tone-ok/.test(cardFor('built').querySelector('.stage-status-text').className), 'the status sentence takes the same colour as its icon');
  // a bad capture and a hard-blocked capture are warnings whatever the status says
  jobsByStatus.captured.capture_quality = 'list';
  dom.window.render();
  assert(iconOf('captured').tone === 'danger', 'an unusable capture shows a danger icon');
  jobsByStatus.captured.capture_quality = 'ok';
  jobsByStatus.captured.prescreen = [{ kind: 'visa', hard: true, label: 'No sponsorship in JD', evidence: 'x' }];
  dom.window.render();
  assert(iconOf('captured').tone === 'warn', 'a hard pre-screen block shows a warning icon');
  jobsByStatus.captured.prescreen = [];
  // a built job being revised reads as working, not as ready to upload
  jobsByStatus.built.revising = { doc: 'resume', started_at: '2026-09-29T10:00:00' };
  dom.window.render();
  assert(iconOf('built').tone === 'muted', 'a built job being revised shows the working icon');
  delete jobsByStatus.built.revising;
  dom.window.render();
})();

// =====================================================================
// A capture comes to the pane you are already on, and says what it knows
// =====================================================================
console.log('\n-- Reveal on capture --');
(function () {
  dom.window.jobs = jobList;
  dom.window.currentFilter = 'active';
  dom.window.searchQuery = 'zzz'; dom.window.searchIds = []; doc.getElementById('search-input').value = 'zzz';
  dom.window.render();
  const skipped = jobsByStatus.skipped;                       // its state belongs to Done, which Active hides
  skipped.evaluated_at = '2026-09-29T18:42:00';
  skipped.evaluation = lowEvaluation;                          // 45 SKIP, the verdict you gave it
  dom.window.revealJob(skipped.id, { seen: true, status: 'skipped' });
  dom.window.applyPendingReveal();
  dom.window.render();
  assert(dom.window.currentFilter === 'active', 'the filter you are on does not change, got ' + dom.window.currentFilter);
  assert(dom.window.searchQuery === '' && doc.getElementById('search-input').value === '', 'an active search is cleared so the card can show');
  const heads = Array.prototype.map.call(doc.querySelectorAll('.group-head'), function (el) { return el.getAttribute('data-group'); });
  assert(heads[0] === 'captured' && /Just captured/.test(doc.querySelector('.group-head').textContent),
    'the captured job is pinned to the top under "Just captured", got ' + heads.join('|'));
  const card = doc.getElementById('body-' + skipped.id);
  assert(!!card, 'the card shows even though its state is filtered out');
  const seen = card.querySelector('.seen-row');
  assert(!!seen && /You captured this before/.test(seen.textContent), 'the card says you captured it before');
  assert(/evaluated Sep 29/.test(seen.textContent) && /45 SKIP/.test(seen.textContent) && /you skipped it/.test(seen.textContent),
    'it names when it was evaluated, the verdict and what you did, got ' + seen.querySelector('.seen-text').textContent);
  const labels = Array.prototype.map.call(seen.querySelectorAll('button'), function (b) { return b.textContent.trim(); });
  assert(labels.join('|') === 'Leave it|Evaluate again', 'the two ways out are Leave it and Evaluate again, got ' + labels.join('|'));
  // Evaluate again posts, Leave it unpins
  const posted = [];
  const rf = dom.window.fetch;
  dom.window.fetch = function (url, opts) { posted.push(String(url)); return rf(url, opts); };
  seen.querySelectorAll('button')[1].click();
  assert(!posted.some(function (u) { return /\/evaluate$/.test(u); }), 'one click on Evaluate again only arms it');
  doc.querySelector('.seen-row button.armed').click();
  dom.window.fetch = rf;
  assert(posted.some(function (u) { return /\/evaluate$/.test(u); }), 'Evaluate again posts to /evaluate on the second click');
  for (var k in dom.window.inFlight) delete dom.window.inFlight[k];
  dom.window.render();
  cardFor('skipped').querySelector('.seen-row button').click();
  assert(dom.window.revealedId === null && !doc.getElementById('body-' + skipped.id), 'Leave it unpins the card and it drops out of Active again');
  // a job you capture that is not in the list yet carries no seen row
  dom.window.revealJob(jobsByStatus.scored.id, { seen: false });
  dom.window.applyPendingReveal(); dom.window.render();
  assert(!cardFor('scored').querySelector('.seen-row'), 'a first capture shows no seen-before row');
  dom.window.clearReveal();
  delete skipped.evaluated_at; skipped.evaluation = null;
  dom.window.currentFilter = 'all'; dom.window.render();
})();

// =====================================================================
// Finished cards keep a way back to the posting
// =====================================================================
console.log('\n-- Open the posting --');
(function () {
  ['applied', 'skipped'].forEach(function (st) {
    expand(st);
    const a = cardFor(st).querySelector('.action-area a.btn-secondary');
    assert(!!a && a.getAttribute('href') === jobsByStatus[st].url && a.getAttribute('target') === '_blank' && /Open the posting/.test(a.textContent), st + ': an "Open the posting" link to the job URL');
  });
  ['scored', 'built', 'captured'].forEach(function (st) {
    expand(st);
    assert(!cardFor(st).querySelector('.action-area a.btn-secondary'), st + ': no posting link while the job is live');
  });
})();

// =====================================================================
// Handoff link on an applied card in process (UI audit step 12)
// =====================================================================
console.log('\n-- Handoff link --');
(function () {
  const j = jobsByStatus.applied;
  const links = function () { return Array.prototype.slice.call(cardFor('applied').querySelectorAll('.action-area a.btn-secondary')); };
  expand('applied');
  assert(links().length === 1 && !links().some(function (a) { return /Handoff/.test(a.textContent); }), 'no note yet: no Handoff link');
  j.handoff = { name: 'HANDOFF.md', at: '2026-10-09T16:30:00' };
  expand('applied');
  const hl = links().filter(function (a) { return /Handoff/.test(a.textContent); })[0];
  assert(!!hl && hl.getAttribute('href') === 'http://127.0.0.1:8790/api/jobs/' + encodeURIComponent(j.id) + '/handoff' && hl.getAttribute('target') === '_blank',
    'a note exists: a Handoff link opens it in a new tab');
  assert(links().length === 2 && /Open the posting/.test(links()[0].textContent), 'the posting link stays first');
  const url = j.url; j.url = '';
  expand('applied');
  assert(links().length === 1 && /Handoff/.test(links()[0].textContent), 'with no posting link the Handoff link stands alone');
  j.url = url;
  const sk = jobsByStatus.skipped; sk.handoff = { name: 'HANDOFF.md' };
  expand('skipped');
  assert(!cardFor('skipped').querySelector('.action-area a.btn-secondary[aria-label="Open the interview handoff note"]'), 'a skipped job never shows one');
  delete sk.handoff; delete j.handoff;
  expand('applied');
})();

// Decision row sits at the top, right under the header
expand('scored');
(function () {
  const body = cardFor('scored').querySelector('.card-body');
  assert(body.firstElementChild && body.firstElementChild.classList.contains('action-area'), 'the decision row is the first thing under the header');
  assert(!/Ready to approve/.test(cardFor('scored').querySelector('.card-header').textContent), 'the redundant "Ready to..." line is gone on the expanded card');
})();
dom.window.expandedId = null; dom.window.render();
assert(/Ready to approve/.test(cardFor('scored').querySelector('.card-header').textContent), 'the collapsed card keeps its status line');
assert(!!cardFor('scored') && /Strengths/.test((function(){ expand('scored'); return cardFor('scored').textContent; })()), 'reasoning cards are titled Strengths and Gaps');

// =====================================================================
// Thumbnail on the built card: the page itself, an eye on hover, click opens the PDF
// =====================================================================
console.log('\n-- Thumbnail --');
(function () {
  expand('built');
  var card = cardFor('built');
  var thumb = card.querySelector('.action-area .thumb');
  assert(!!thumb, 'built: a thumbnail sits in the action area');
  assert(thumb && thumb.tagName === 'BUTTON' && thumb.getAttribute('aria-label') === 'Open the resume', 'the thumbnail is a button named "Open the resume"');
  var img = thumb && thumb.querySelector('img.thumb-img');
  assert(!!img && img.getAttribute('src') === 'http://127.0.0.1:8790/jobs/' + jobsByStatus.built.id + '/thumb?doc=resume&v=', 'the image comes from /jobs/<id>/thumb?doc=resume, got ' + (img && img.getAttribute('src')));
  assert(!!img && img.getAttribute('alt') === 'Page 1 of the resume', 'the image has alt text');
  assert(!!(thumb && thumb.querySelector('.thumb-eye .icon svg')), 'an eye overlay is present for hover');
  assert(thumb && thumb.compareDocumentPosition(card.querySelector('.action-pair')) & 4, 'the thumbnail sits above the decision pair');
  assert(/Resume/.test(card.querySelector('.doc-tile[data-doc="resume"] .doc-caption').textContent), 'the resume tile is captioned Resume');
  var opened = [];
  var realFetch = dom.window.fetch;
  dom.window.fetch = function (url, opts) { opened.push({ url: String(url), body: opts && opts.body }); return realFetch(url, opts); };
  thumb.click();
  dom.window.fetch = realFetch;
  assert(opened.length === 1 && /\/jobs\/[^/]+\/open$/.test(opened[0].url) && /"what":"resume"/.test(opened[0].body), 'clicking the resume tile opens the resume alone');
  img.dispatchEvent(new dom.window.Event('error'));
  assert(thumb.closest('.doc-tile').hidden === true, 'a thumbnail that fails to load hides its tile');
  assert(thumb.getAttribute('draggable') === 'true', 'the resume tile is draggable');
  // the second tile: a dashed Generate box without a cover letter, a real tile with one
  var box = card.querySelector('.thumb.thumb-empty');
  assert(!!box && /Generate cover letter/.test(box.textContent) && !!box.querySelector('.icon svg'), 'no cover letter: a dashed box with a plus says Generate cover letter');
  var posted = [];
  var rf = dom.window.fetch;
  dom.window.fetch = function (url, opts) { posted.push(String(url)); return rf(url, opts); };
  box.click();
  dom.window.fetch = rf;
  assert(posted.some(function (u) { return /\/jobs\/[^/]+\/cover$/.test(u); }), 'clicking the box posts to /cover');
  expand('built_with_cover');
  var card2 = cardFor('built_with_cover');
  var tiles = card2.querySelectorAll('.doc-tile[data-doc]');
  assert(tiles.length === 2 && tiles[1].getAttribute('data-doc') === 'cover', 'with a cover letter: two document tiles, resume then cover letter');
  assert(/Cover letter/.test(tiles[1].textContent) && /doc=cover/.test(tiles[1].querySelector('img').getAttribute('src')), 'the cover tile shows the cover thumbnail with its caption');
  assert(!card2.querySelector('.thumb-empty'), 'with a cover letter there is no Generate box');
  assert(/Desktop/.test(actionArea('built_with_cover').textContent) && /until you mark it submitted or skip/.test(actionArea('built_with_cover').textContent), 'the Desktop note says when the copies go away');
  jobsByStatus.built.cover_busy = true; jobsByStatus.built.cover_started_at = '2026-09-14T16:00:00';
  dom.window.render(); expand('built');
  assert(!!cardFor('built').querySelector('.thumb-empty.busy .working-timer'), 'while the cover letter writes, the box carries a timer');
  delete jobsByStatus.built.cover_busy; delete jobsByStatus.built.cover_started_at;
  jobsByStatus.built.cover_error = 'Cover letter came back without paragraphs.';
  dom.window.render(); expand('built');
  assert(/without paragraphs/.test(cardFor('built').querySelector('.doc-error').textContent), 'a failed cover letter shows its reason under the box');
  delete jobsByStatus.built.cover_error; dom.window.render();
  ['scored', 'captured', 'building', 'applied'].forEach(function (st) {
    expand(st);
    assert(!cardFor(st).querySelector('.thumb'), st + ': no thumbnail before a build');
  });
})();

dom.window.jobs = jobList;
dom.window.currentFilter = 'all';
dom.window.expandedId = null;
dom.window.render();

// The Claude button on an evaluation opens the question box with the cursor in it.
(async function () {
  // Where an applied job stands: a stage picker, In process filter, status line.
  dom.window.currentFilter = 'all'; dom.window.expandedId = jobsByStatus.applied.id; dom.window.render();
  const sel = cardFor('applied').querySelector('.stage-select');
  const saveBtn = cardFor('applied').querySelector('.stage-save');
  assert(!!sel && sel.value === 'applied' && saveBtn.hidden, 'an applied card has a stage picker, Save hidden until something changes');
  sel.value = 'interviewing'; sel.dispatchEvent(new dom.window.Event('change'));
  assert(!saveBtn.hidden, 'choosing a stage shows Save');
  const sposted = [];
  const srf = dom.window.fetch;
  dom.window.fetch = function (url, opts) { sposted.push({ url: String(url), body: opts && opts.body }); return srf(url, opts); };
  saveBtn.click();
  dom.window.fetch = srf;
  const sp = sposted.find(function (x) { return /\/jobs\/[^/]+\/stage$/.test(x.url); });
  assert(sp && JSON.parse(sp.body).stage === 'interviewing', 'Save posts the stage');
  jobsByStatus.applied.stage = 'interviewing'; jobsByStatus.applied.stage_at = '2026-10-07T10:00:00'; jobsByStatus.applied.stage_note = 'Panel with the team';
  dom.window.render();
  assert(/Interviewing/.test(cardFor('applied').querySelector('.stage-status-text').textContent), 'the status line says Interviewing');
  assert(/Panel with the team/.test(cardFor('applied').textContent), 'the last note shows under the picker');
  dom.window.currentFilter = 'process'; dom.window.render();
  assert(!!doc.getElementById('body-' + jobsByStatus.applied.id) && doc.querySelectorAll('.card').length === 1, 'In process lists only open stages');
  jobsByStatus.applied.stage = 'rejected'; dom.window.render();
  assert(!doc.getElementById('body-' + jobsByStatus.applied.id), 'a rejection leaves In process');
  delete jobsByStatus.applied.stage; delete jobsByStatus.applied.stage_at; delete jobsByStatus.applied.stage_note;
  dom.window.currentFilter = 'all'; dom.window.render();

  // Mark submitted follows you down a long card: a pinned bar, only while the card's own button is out of view.
  let ioCallback = null, observed = null;
  dom.window.IntersectionObserver = function (cb) { ioCallback = cb; this.observe = function (el) { observed = el; }; this.disconnect = function () {}; };
  dom.window.expandedId = jobsByStatus.built.id; dom.window.render();
  const dock = cardFor('built').querySelector('.submit-dock');
  assert(!!dock && dock.hidden, 'a built card carries a Mark submitted bar, hidden while its own button is in view');
  assert(!!observed && /Mark submitted/.test(observed.textContent), 'the bar watches the card\'s own Mark submitted button');
  ioCallback([{ isIntersecting: false }]);
  assert(!dock.hidden && /Northbridge Logistics/.test(dock.textContent) && /Mark submitted/.test(dock.textContent), 'scrolled past it, the bar shows with the company and Mark submitted');
  ioCallback([{ isIntersecting: true }]);
  assert(dock.hidden, 'back in view, the bar hides so the two are never on screen together');
  const dposted = [];
  const drf = dom.window.fetch;
  dom.window.fetch = function (url, opts) { dposted.push(String(url)); return drf(url, opts); };
  dock.querySelector('button.primary').click();
  dom.window.fetch = drf;
  assert(dposted.some(function (u) { return /\/jobs\/[^/]+\/submitted$/.test(u); }), 'the bar\'s button marks the job submitted');
  dom.window.expandedId = jobsByStatus.scored.id; dom.window.render();
  assert(!cardFor('scored').querySelector('.submit-dock'), 'a card that is not built has no bar');
  delete dom.window.IntersectionObserver;

  expand('scored');
  const chat = cardFor('scored').querySelector('.card-header .btn-icon[aria-label="Ask about this job"]');
  if (chat) {
    chat.click();
    await new Promise(function (r) { setTimeout(r, 300); });
    dom.window.render();   // a poll redraws the cards while you are typing
    const active = doc.activeElement;
    assert(!!active && active.classList.contains('ask-input'), 'the Claude button puts the cursor in the question box, got ' + (active && active.className));
  } else {
    assert(false, 'the scored card has the Claude button');
  }
  // The inbox watch in the panel (UI audit 2026-10-09, step 4): the sentence on an applied card and the bell.
  console.log('\n-- Inbox in the panel --');
  (function () {
    const w = dom.window;
    const base = Object.assign({}, jobsByStatus.applied, { stage: 'interviewing', stage_at: '2026-10-08T10:00:00' });
    assert(!/last email/.test(w.statusSentence(Object.assign({}, base, { inbox: { count: 0, last_kind: null, last_at: null, needs: 0 } }))),
      'no email, no "last email" in the sentence');
    assert(/^Interviewing · .* · last email: interview, Oct 8$/.test(w.statusSentence(Object.assign({}, base,
      { inbox: { count: 5, last_kind: 'interview', last_at: '2026-10-08T08:04:13', needs: 1 } }))), 'the applied sentence ends with the newest email: ' +
      w.statusSentence(Object.assign({}, base, { inbox: { count: 5, last_kind: 'interview', last_at: '2026-10-08T08:04:13', needs: 1 } })));
    assert(/^Applied · last email: acknowledgement, Oct 6$/.test(w.statusSentence(Object.assign({}, jobsByStatus.applied,
      { inbox: { count: 1, last_kind: 'received', last_at: '2026-10-06T23:18:08', needs: 0 } }))), 'an applied job with no stage reads Applied, then the email');
  })();
  const realFetch = dom.window.fetch;
  function bellFor(n) {
    dom.window.fetch = function (url) { return String(url).indexOf('/notifications') !== -1 ? jsonResponse(n) : realFetch(url); };
    dom.window.pollBell();
    return new Promise(function (r) { setTimeout(r, 50); }).then(function () { dom.window.fetch = realFetch; return doc.getElementById('bell-btn'); });
  }
  let bellEl = await bellFor({ people: 0, approve: 0, linkedin: 0, failed: 0, inbox: 2, total: 2 });
  assert(/2 emails to confirm/.test(bellEl.title) && doc.getElementById('bell-count').textContent === '2', 'the bell counts and names emails to confirm');
  assert(bellEl.getAttribute('data-tab') === 'inbox', 'with only mail waiting the bell opens the Inbox tab');
  bellEl = await bellFor({ people: 1, approve: 0, linkedin: 0, failed: 0, inbox: 1, total: 2 });
  assert(bellEl.getAttribute('data-tab') === 'outreach' && /1 person to approve, 1 email to confirm/.test(bellEl.title), 'outreach work still wins the bell: ' + bellEl.title);
  bellEl = await bellFor({ people: 0, approve: 0, linkedin: 0, failed: 0, inbox: 0, total: 0 });
  assert(bellEl.getAttribute('data-tab') === 'jobs', 'nothing waiting: the bell opens the dashboard');

  // Person capture (UI audit steps 8 and 14). The extraction itself is tested in extract.test.js; this is the card, and
  // every button on it is clicked and the request it sends is asserted.
  console.log('\n-- Person capture card --');
  await (async function () {
    const w = dom.window;
    const baseFetch = w.fetch;
    const posts = [], opened = [], sent = [];
    let tabUrl = 'https://www.linkedin.com/in/pat-jones-123/';
    w.chrome = { tabs: { create: function (o) { opened.push(o.url); }, query: function (q, cb) { cb([{ id: 1, url: tabUrl }]); } },
      storage: { session: { remove: function () {} } }, runtime: { sendMessage: function (m) { sent.push(m); return Promise.resolve(); } } };
    let personState = null;
    w.fetch = function (url, opts) {
      const u = String(url);
      if (opts && opts.method === 'POST') {
        posts.push({ url: u, body: JSON.parse(opts.body || '{}') });
        if (/\/attach$/.test(u)) return jsonResponse(personState.afterAttach);
        if (/\/draft$/.test(u)) return jsonResponse(personState.afterDraft);
        if (/\/find_email$/.test(u)) return jsonResponse(personState.afterEmail);
        if (/\/forget$/.test(u)) return jsonResponse({ removed: 'contact-pat' });
      }
      return baseFetch(url, opts);
    };
    const acme = { id: 'j-acme', company: 'Acme Health', title: 'Strategy Lead', stage: null, match: true, group: 1, reason: 'Same company', hold: null };
    const acmeHold = { id: 'j-held', company: 'Acme Health', title: 'Ops Lead', stage: 'interviewing', match: true, group: 1, reason: 'Same company',
      hold: 'you are in Acme Health\'s process (Interviewing), so nothing automated goes to them' };
    const other = { id: 'j-nb', company: 'Northbridge Logistics', title: 'Consultant', stage: null, match: false, group: 2, reason: '', hold: null };
    const person = { id: 'contact-pat', job_id: null, name: 'Pat Jones', title: 'Director, Strategy', headline: 'Director, Strategy at Acme Health', company: 'Acme Health',
      company_url: 'https://www.linkedin.com/company/acme-health', linkedin_url: 'https://www.linkedin.com/in/pat-jones-123', location: 'Denver, CO', email: null, email_source: null, status: 'approved', manual: true };
    const attachedJob = { id: 'j-acme', company: 'Acme Health', title: 'Strategy Lead', stage: null, hold: null };
    const result = { created: true, tracked: [], person: person, job: null, messages: [], busy: null, error: null, jobs: [acme, acmeHold, other] };
    personState = {
      afterAttach: Object.assign({}, result, { person: Object.assign({}, person, { job_id: 'j-acme' }), job: attachedJob }),
      afterDraft: Object.assign({}, result, { person: Object.assign({}, person, { job_id: 'j-acme' }), job: attachedJob, busy: { what: 'draft', since: new Date().toISOString() } }),
      afterEmail: Object.assign({}, result, { person: Object.assign({}, person, { job_id: 'j-acme' }), job: attachedJob, busy: { what: 'email', since: new Date().toISOString() } })
    };
    const tick = function (ms) { return new Promise(function (r) { setTimeout(r, ms || 20); }); };
    const card = function () { return doc.querySelector('.person-card'); };
    const btn = function (label) { return Array.from(card().querySelectorAll('button')).filter(function (b) { return b.textContent.replace(/\s+/g, ' ').trim() === label; })[0]; };
    const act = function (name) { return card().querySelector('[data-pc="' + name + '"]'); };
    const text = function () { return card().textContent.replace(/\s+/g, ' '); };

    w.onProfile = false; w.updateCaptureButton();
    const cap = doc.getElementById('capture-btn');
    assert(cap.getAttribute('aria-label') === 'Look at this page' && !cap.querySelector('circle[r="3.75"]'), 'off a profile the eye says "Look at this page"');
    w.onProfile = true; w.updateCaptureButton();
    assert(cap.getAttribute('aria-label') === 'Capture this person' && /Capture this person/.test(cap.title) && !!cap.querySelector('circle[r="3.75"]'),
      'on a profile the one button says "Capture this person" and shows a person');
    w.onProfile = false; w.updateCaptureButton();
    assert(cap.getAttribute('aria-label') === 'Look at this page', 'and goes back when the tab is not a profile');

    // The card, first state: who they are and one primary action for the best job.
    w.showPerson(result);
    assert(!!card() && w.jobsListEl.firstChild === card(), 'the captured person is pinned at the top of the list');
    assert(card().querySelector('.pc-avatar').textContent === 'PJ' && /Pat Jones/.test(text()) && /Director, Strategy/.test(text()) && /Acme Health · Denver, CO/.test(text()),
      'the card shows initials, name, title, company and place');
    assert(!!btn('Add to Acme Health, Strategy Lead') && !btn('Add to Acme Health, Strategy Lead').disabled && !!btn('Add to Acme Health, Strategy Lead').querySelector('.icon'),
      'one primary action with a plus names the best job (the first match), got "' + (act('attach') && act('attach').textContent) + '"');
    assert(/Same company\./.test(text()), 'and says why it is the best match');
    assert(!card().querySelector('.pc-jobs') && act('choose').getAttribute('aria-expanded') === 'false', 'the job list is closed while there is a best job');
    assert(btn('Draft a note').disabled && /Add this person to a job first/.test(text()), 'Draft a note waits for a job, and says why');
    assert(!!act('email') && /about 3 cents/.test(act('email').textContent) && /A paid lookup: about 3 cents when it finds one/.test(text()), 'Find their email is its own button and says what it costs');
    assert(!!act('save') && /Save as contact/.test(act('save').textContent) && !!act('save').querySelector('.icon') && !!act('refresh') && !!act('dismiss'), 'Save as contact, Refresh from profile and Dismiss are there');
    assert(!card().querySelector('select') && posts.length === 0, 'no native select, and nothing was posted by capturing: no draft, no lookup, no attach (' + posts.length + ')');

    // Choose another job: a radio list of rows.
    act('choose').click();
    assert(!!card().querySelector('.pc-jobs[role="radiogroup"]') && act('choose').getAttribute('aria-expanded') === 'true', 'Choose another job opens the list');
    const rows = Array.from(card().querySelectorAll('.pc-job'));
    assert(rows.length === 3 && rows.every(function (r) { return r.getAttribute('role') === 'radio'; }), 'one radio row per job');
    assert(rows.filter(function (r) { return r.getAttribute('aria-checked') === 'true'; }).length === 1 && rows[0].getAttribute('aria-checked') === 'true', 'the best job is the checked one');
    assert(Array.from(card().querySelectorAll('.pc-group')).map(function (g) { return g.textContent; }).join('|') === 'At Acme Health|Other open applications', 'grouped: at their company, then the rest');
    assert(/Interviewing/.test(card().querySelector('.pc-job[data-job="j-held"]').textContent) && !!card().querySelector('.pc-job[data-job="j-held"] .pc-tag.warn'), 'a job in process says so on its row');
    card().querySelector('.pc-job[data-job="j-held"]').click();
    assert(!!btn('Add to Acme Health, Ops Lead') && !card().querySelector('.pc-jobs') && /no note can be drafted for this job/.test(text()),
      'picking a row changes the primary to that job, closes the list, and warns that a job in process cannot be drafted for');
    assert(posts.length === 0, 'picking is not a request');
    act('choose').click(); card().querySelector('.pc-job[data-job="j-acme"]').click();

    // Save as contact is a local choice (the contact was saved at capture); then real buttons: Add to a job, Remove.
    act('save').click();
    assert(/Saved as a contact\. Nothing was drafted or paid for\./.test(text()) && !!btn('Add to a job') && !!btn('Remove') && !!btn('Add to a job').querySelector('.icon') && !!btn('Remove').querySelector('.icon'),
      'Save as contact shows a saved state with Add to a job and Remove as buttons');
    assert(posts.length === 0, 'saving as a contact posts nothing (it is already saved)');
    act('add').click();
    assert(!!act('attach') && !!btn('Add to Acme Health, Strategy Lead'), 'Add to a job brings the primary action back with the best job chosen');
    act('save').click();
    const before = posts.length;
    act('remove').click();
    await tick();
    assert(posts.length === before + 1 && /\/api\/people\/contact-pat\/forget$/.test(posts[before].url) && !card(), 'Remove posts to /forget and the card goes');

    // Add to this job.
    w.showPerson(result);
    act('attach').click();
    await tick();
    assert(posts.length === before + 2 && /\/api\/people\/contact-pat\/attach$/.test(posts[before + 1].url) && posts[before + 1].body.job_id === 'j-acme', 'the primary button posts /attach with the chosen job');
    assert(/On the Acme Health, Strategy Lead list\./.test(text()) && !act('attach') && !card().querySelector('.pc-jobs'), 'then the card says which list they are on');
    assert(!btn('Draft a note').disabled, 'and Draft a note opens up');

    // Draft a note.
    act('draft').click();
    await tick();
    assert(/\/draft$/.test(posts[posts.length - 1].url), 'Draft a note posts to /draft');
    assert(btn('Drafting') && btn('Drafting').disabled && !!card().querySelector('.working-timer'), 'it shows Drafting with a running clock');
    w.stopPersonPoll();
    w.applyPerson(Object.assign({}, personState.afterDraft, { busy: null, messages: [{ id: 'm1', channel: 'linkedin', status: 'review' }] }));
    assert(!!act('open-notes'), 'a finished LinkedIn note says so');
    act('open-notes').click();
    assert(doc.getElementById('li-btn').getAttribute('aria-pressed') === 'true', 'and opens LinkedIn notes');
    w.setLiMode(false);
    w.applyPerson(Object.assign({}, personState.afterDraft, { busy: null, messages: [{ id: 'm2', channel: 'email', status: 'review' }] }));
    act('open-dashboard').click();
    assert(/#outreach$/.test(opened[opened.length - 1]), 'a finished email opens the dashboard on Outreach');

    // Find their email.
    w.showPerson(Object.assign({}, result, { person: Object.assign({}, person, { job_id: 'j-acme' }), job: attachedJob }));
    const n0 = posts.length;
    act('email').click();
    await tick();
    assert(posts.length === n0 + 1 && /\/find_email$/.test(posts[n0].url) && !('again' in posts[n0].body), 'Find their email posts to /find_email, without "again"');
    w.stopPersonPoll();
    assert(/Looking for an email/.test(text()) && !!card().querySelector('.working-timer'), 'it shows the lookup running');
    w.applyPerson(Object.assign({}, personState.afterEmail, { busy: null, person: Object.assign({}, person, { job_id: 'j-acme', email: 'pat.jones@acmehealth.com', email_source: 'finder' }) }));
    assert(/pat\.jones@acmehealth\.com/.test(text()) && !act('email'), 'a found address is shown and the button goes');
    w.applyPerson(Object.assign({}, personState.afterEmail, { busy: null, person: Object.assign({}, person, { job_id: 'j-acme', email_source: 'not_found' }) }));
    assert(/Look again/.test(act('email').textContent) && /No email was found last time/.test(text()), 'nothing found: it offers Look again and says so');
    act('email').click();
    await tick(); w.stopPersonPoll();
    assert(posts[posts.length - 1].body.again === true, 'Look again posts "again": true, an explicit yes to paying again');

    // Refresh from profile: has to be on that person's profile; asks the background script to read the page.
    w.showPerson(result);
    tabUrl = 'https://www.linkedin.com/in/someone-else/';
    act('refresh').click();
    assert(/Open Pat Jones's profile first/.test(text()) && sent.length === 0 && !act('refresh').disabled, 'on another page Refresh says "Open Pat Jones\'s profile first" and sends nothing');
    tabUrl = 'https://www.linkedin.com/in/Pat-Jones-123/?trk=x';
    act('refresh').click();
    assert(sent.length === 1 && sent[0].type === 'refresh-person' && sent[0].person_id === 'contact-pat' && /pat-jones-123$/.test(sent[0].linkedin_url) && sent[0].name === 'Pat Jones',
      'on the profile it asks the extension to read the page for that person, got ' + JSON.stringify(sent[0]));
    assert(/Reading the profile/.test(act('refresh').textContent) && act('refresh').disabled && !/Open Pat Jones/.test(text()), 'and shows that it is reading');
    const refreshed = Object.assign({}, result, { refreshed: true, read: 'model',
      person: Object.assign({}, person, { title: 'VP, Operations', company: 'Northbridge Logistics', company_url: 'https://www.linkedin.com/company/northbridge-logistics', location: 'Chicago, IL' }),
      jobs: [Object.assign({}, other, { match: true, group: 0, reason: 'Same company page on LinkedIn' }), acme, acmeHold] });
    w.personRefreshed({ type: 'person-refreshed', person_id: 'contact-pat', result: refreshed });
    assert(/VP, Operations/.test(text()) && /Northbridge Logistics · Chicago, IL/.test(text()) && /Read again: VP, Operations at Northbridge Logistics\./.test(text()) && !act('refresh').disabled, 'a refreshed person shows the new title, company and place, and says what was read');
    assert(!!btn('Add to Northbridge Logistics, Consultant') && /Same company page on LinkedIn\./.test(text()), 'and the best job is re-chosen for the new company');
    w.personRefreshed({ type: 'person-refreshed', person_id: 'someone-else', result: Object.assign({}, refreshed, { person: Object.assign({}, person, { id: 'someone-else', title: 'Wrong' }) }) });
    assert(!/Wrong/.test(text()), 'a refresh for another person is ignored');
    act('refresh').click();
    w.personRefreshFailed({ type: 'person-refresh-failed', person_id: 'contact-pat', message: 'The server is not running.' });
    assert(/The server is not running\./.test(text()) && !act('refresh').disabled, 'a failed refresh shows why and the button comes back');
    w.showPerson(result);
    assert(!!act('refresh') && /Their title and company were not read/.test(text()) === false, 'a card with title and company has no "not read" note');
    w.showPerson(Object.assign({}, result, { person: Object.assign({}, person, { title: '', headline: '', company: '' }) }));
    assert(/Their title and company were not read from the page\./.test(text()), 'a card with neither says so, next to Refresh from profile');

    // No job at their company: nothing is chosen, the list is open, the primary waits, Add a job opens the dashboard.
    w.showPerson(Object.assign({}, result, { jobs: [other] }));
    assert(!!card().querySelector('.pc-jobs') && act('attach').disabled && /No open application at Acme Health\./.test(text()), 'no job at their company: the list is open, nothing is chosen, the primary waits');
    act('add-job').click();
    assert(opened.length >= 1 && /#jobs\?add=Acme%20Health&li=https%3A%2F%2Fwww\.linkedin\.com%2Fcompany%2Facme-health$/.test(opened[opened.length - 1]), 'Add a job opens the dashboard form with the company filled in, got ' + opened[opened.length - 1]);
    const np = posts.length;
    card().querySelector('.pc-job[data-job="j-nb"]').click();
    assert(!!btn('Add to Northbridge Logistics, Consultant') && !act('attach').disabled && posts.length === np, 'picking a job in the list enables the primary, still posts nothing');
    act('attach').click();
    await tick();
    assert(posts.length === np + 1 && posts[np].body.job_id === 'j-nb', 'and the primary posts that job');
    w.showPerson(Object.assign({}, result, { jobs: [] }));
    assert(act('attach').disabled && !act('choose') && /No open application/.test(text()), 'no open applications at all: nothing to choose, nothing breaks');

    // Already tracked.
    w.showPerson(Object.assign({}, result, { created: false, tracked: [{ id: 'j1-pat', job_id: 'j1', status: 'approved', job: { id: 'j1', company: 'Acme Health', title: 'Ops Lead' } }] }));
    assert(/Already tracked: on the Acme Health, Ops Lead list \(approved\)\./.test(text()), 'a profile already on a list says which, got ' + text().slice(0, 200));
    act('open-tracked').click();
    assert(/#outreach$/.test(opened[opened.length - 1]), 'Open goes to Outreach');
    w.showPerson(Object.assign({}, result, { created: false, tracked: [{ id: 'contact-pat', job_id: null, status: 'approved', job: null }] }));
    assert(/Already saved as a contact\./.test(text()) && !act('save') && !!act('remove'), 'a profile already saved as a contact says so and offers Remove, not Save');
    const nf = posts.length;
    act('remove').click();
    await tick();
    assert(posts.length === nf + 1 && /\/forget$/.test(posts[nf].url) && !card(), 'and Remove posts to /forget');

    // A job in process: attach is allowed, drafting is refused and says why.
    w.showPerson(Object.assign({}, result, { person: Object.assign({}, person, { job_id: 'j-held' }),
      job: { id: 'j-held', company: 'Acme Health', title: 'Ops Lead', stage: 'interviewing', hold: acmeHold.hold } }));
    assert(btn('Draft a note').disabled && /process \(Interviewing\)/.test(text()), 'a person on a job in process cannot be drafted for, and it says why');

    // The dead-button guard: a redraw while a press that began on the card is down waits for the release.
    w.showPerson(result);
    const pressed = act('choose');
    pressed.dispatchEvent(new w.Event('pointerdown', { bubbles: true }));
    w.render();
    assert(act('choose') === pressed && doc.body.contains(pressed), 'a redraw while the mouse is down on the card leaves its buttons in place');
    w.document.dispatchEvent(new w.Event('pointerup'));
    pressed.click();
    await tick(150);
    assert(!!card().querySelector('.pc-jobs'), 'the click still lands, and the redraw that waited has run after the release');
    assert(act('choose') !== pressed && !doc.body.contains(pressed), 'the deferred redraw replaced the nodes only after the release');
    const stale = pressed, n1 = posts.length;
    stale.click();
    assert(posts.length === n1 && !!card(), 'a click on a node from an old redraw does nothing and breaks nothing');

    // A refusal from the server is shown as it came, and the button comes back; Dismiss clears the card.
    w.fetch = function () { return Promise.resolve({ ok: false, status: 409, json: function () { return Promise.resolve({ error: 'Not drafting: Acme Health is marked rejected.' }); } }); };
    w.showPerson(Object.assign({}, result, { person: Object.assign({}, person, { job_id: 'j-acme' }), job: personState.afterAttach.job }));
    act('draft').click();
    await tick();
    assert(/Not drafting: Acme Health is marked rejected\./.test(text()) && !btn('Drafting') && !!card().querySelector('[role="alert"]'), 'a refusal is shown as it came, as an alert, and the button comes back');
    act('dismiss').click();
    assert(!card(), 'Dismiss clears the card');
    w.fetch = baseFetch;

    // Saved contacts at the company show on the job's card (item 4): one button each, posts /attach for that job.
    const appliedJob = Object.assign({}, jobsByStatus.applied, { id: 'job-contacts', company: 'Northbridge Logistics', stage: 'heard_back',
      contacts: [{ id: 'contact-jl', name: 'Jordan Lee', title: 'Senior Recruiter', company: 'Lakeview Consulting', reason: 'Same company' }] });
    const keepJobs = w.jobs, keepFilter = w.currentFilter;
    w.jobs = [appliedJob]; w.expandedId = appliedJob.id; w.currentFilter = 'all'; w.render();
    const sc = doc.querySelector('.saved-contacts');
    assert(!!sc && /Saved contacts at Northbridge Logistics/.test(sc.textContent) && /Jordan Lee/.test(sc.textContent) && /Senior Recruiter/.test(sc.textContent), 'an applied job card lists saved contacts at its company');
    w.fetch = function (url, opts) {
      if (opts && opts.method === 'POST') { posts.push({ url: String(url), body: JSON.parse(opts.body || '{}') }); return jsonResponse(personState.afterAttach); }
      return baseFetch(url, opts);
    };
    const n2 = posts.length;
    sc.querySelector('button[data-sc="contact-jl"]').click();
    await tick();
    assert(posts.length === n2 + 1 && /\/api\/people\/contact-jl\/attach$/.test(posts[n2].url) && posts[n2].body.job_id === 'job-contacts', 'Add to this job posts /attach for that contact and this job');
    w.jobs = [Object.assign({}, appliedJob, { contacts: [] })]; w.render();
    assert(!doc.querySelector('.saved-contacts'), 'a job with no saved contacts shows no such block');
    w.fetch = baseFetch; w.jobs = keepJobs; w.currentFilter = keepFilter; w.expandedId = null; w.render();
  })();

  // =====================================================================
  // Server address setting, optional features hidden when off, onboarding empty state
  // =====================================================================
  console.log('\n-- Server address, features off, onboarding --');
  const wait = function () { return new Promise(function (r) { setTimeout(r, 0); }); };
  const settle = async function () { for (let i = 0; i < 8; i++) await wait(); };
  function freshPanel(opts) {
    const calls = [];
    const d = new JSDOM(htmlSource, { url: 'http://localhost/sidepanel.html', runScripts: 'outside-only' });
    const win = d.window;
    const stored = Object.assign({}, opts.stored || {});
    win.fetch = function (url) {
      const u = String(url);
      calls.push(u);
      if (/\/api\/profile\/status$/.test(u)) {
        if (opts.status === null) return jsonResponse({}, false);
        return jsonResponse(opts.status);
      }
      if (/\/jobs$/.test(u)) return jsonResponse(opts.jobs || []);
      if (/\/settings$/.test(u)) return jsonResponse({ auto: false, threshold: 70 });
      return jsonResponse({ ok: true, claude: 'ready' });
    };
    win.navigator.clipboard = { writeText: function () { return Promise.resolve(); } };
    win.chrome = {
      tabs: { query: function (q, cb) { cb([]); }, create: function () {}, update: function () {}, onActivated: { addListener: function () {} }, onUpdated: { addListener: function () {} } },
      storage: {
        session: { get: function () { return Promise.resolve({}); }, set: function () { return Promise.resolve(); } },
        local: {
          get: function (k) { const o = {}; o[k] = stored[k]; return Promise.resolve(o); },
          set: function (o) { Object.assign(stored, o); return Promise.resolve(); },
          remove: function (k) { delete stored[k]; return Promise.resolve(); }
        }
      },
      runtime: { sendMessage: function () { return Promise.resolve(); }, onMessage: { addListener: function () {} } }
    };
    win.eval(jsSource);
    return { win: win, doc: win.document, calls: calls, stored: stored };
  }

  // Default address, and a field that shows it.
  const def = freshPanel({ status: statusBody });
  await settle();
  assert(def.win.SERVER === 'http://127.0.0.1:8790', 'server: the default address is 127.0.0.1:8790');
  assert(def.doc.getElementById('server-input').value === 'http://127.0.0.1:8790', 'server: the settings field shows the default');
  assert(def.calls.some(function (u) { return u.indexOf('http://127.0.0.1:8790/jobs') === 0; }), 'server: the default address is used for calls');

  // A saved address is picked up at start and used for every call.
  const custom = freshPanel({ status: statusBody, stored: { serverUrl: 'http://127.0.0.1:9911' } });
  await settle();
  assert(custom.win.SERVER === 'http://127.0.0.1:9911', 'server: a saved address replaces the default');
  assert(custom.doc.getElementById('server-input').value === 'http://127.0.0.1:9911', 'server: the field shows the saved address');
  assert(custom.calls.length > 0 && custom.calls.every(function (u) { return u.indexOf('http://127.0.0.1:9911/') === 0; }), 'server: every call goes to the saved address');

  // Typing a new address and saving it stores it and switches calls to it.
  const typed = freshPanel({ status: statusBody });
  await settle();
  typed.doc.getElementById('server-input').value = 'http://127.0.0.1:9000/';
  typed.doc.getElementById('server-save').click();
  await settle();
  assert(typed.stored.serverUrl === 'http://127.0.0.1:9000', 'server: saving stores the address without a trailing slash');
  assert(typed.calls.some(function (u) { return u.indexOf('http://127.0.0.1:9000/jobs') === 0; }), 'server: after saving, calls use the new address');
  typed.doc.getElementById('server-input').value = 'not a url';
  typed.doc.getElementById('server-save').click();
  assert(typed.stored.serverUrl === 'http://127.0.0.1:9000' && !typed.doc.getElementById('banner').hidden, 'server: a bad address is refused and the old one kept');
  typed.doc.getElementById('server-input').value = '';
  typed.doc.getElementById('server-save').click();
  await settle();
  assert(typed.stored.serverUrl === undefined && typed.win.SERVER === 'http://127.0.0.1:8790', 'server: an empty field returns to the default');

  // Features off: no sponsorship or LCA chips, no visa wording, no outreach controls.
  const visaJob = baseJob({ status: 'scored', id: 'job-visa', evaluation: Object.assign({}, evaluation, { sponsorship_flag: 'explicit_no' }),
    prescreen: [{ kind: 'visa', hard: true, label: 'Needs a work visa you do not hold', evidence: 'no visa sponsorship' },
                { kind: 'clearance', hard: true, label: 'Needs a security clearance', evidence: 'clearance required' }] });
  const appliedJob2 = baseJob({ status: 'applied', id: 'job-applied', evaluation: evaluation, build: build, company_url: 'https://www.linkedin.com/company/northbridge-logistics' });
  const off = freshPanel({ status: { onboarded: true, features: { sponsorship: false, outreach: false, email: false, alerts: false } }, jobs: [visaJob, appliedJob2] });
  await settle();
  off.win.currentFilter = 'all'; off.win.expandedId = 'job-visa'; off.win.render();
  const offChips = Array.from(off.doc.querySelectorAll('.chips-row .chip')).map(function (c) { return c.textContent; });
  assert(offChips.indexOf('No sponsorship in the JD') === -1, 'features off: no "No sponsorship" chip');
  assert(!offChips.some(function (t) { return /Sponsors|Sponsored|LCA/.test(t); }), 'features off: no sponsorship or LCA chips, got ' + offChips.join(' | '));
  assert(!offChips.some(function (t) { return /visa/i.test(t); }), 'features off: the visa blocker wording is hidden');
  assert(offChips.indexOf('Needs a security clearance') !== -1, 'features off: other hard blockers still show');
  assert(!/LCA|visa/i.test(off.doc.getElementById('body-job-visa').textContent), 'features off: no LCA or visa text anywhere in the card');
  off.win.expandedId = 'job-applied'; off.win.render();
  assert(!off.doc.querySelector('.outreach-prompt, .outreach-row, .outreach-form'), 'features off: no outreach controls on an applied card');
  assert(off.doc.getElementById('li-btn').hidden, 'features off: the LinkedIn notes button is hidden');

  // The same jobs with the features on show them.
  const on = freshPanel({ status: statusBody, jobs: [visaJob, appliedJob2] });
  await settle();
  on.win.currentFilter = 'all'; on.win.expandedId = 'job-visa'; on.win.render();
  const onChips = Array.from(on.doc.querySelectorAll('.chips-row .chip')).map(function (c) { return c.textContent; });
  assert(onChips.indexOf('No sponsorship in the JD') !== -1 && onChips.indexOf('Needs a work visa you do not hold') !== -1, 'features on: sponsorship chip and visa blocker show');
  assert(!on.doc.getElementById('li-btn').hidden, 'features on: the LinkedIn notes button shows');

  // A server with no status route: everything optional is off, no empty state.
  const none = freshPanel({ status: null, jobs: [visaJob] });
  await settle();
  none.win.currentFilter = 'all'; none.win.expandedId = 'job-visa'; none.win.render();
  const noneChips = Array.from(none.doc.querySelectorAll('.chips-row .chip')).map(function (c) { return c.textContent; });
  assert(noneChips.indexOf('No sponsorship in the JD') === -1 && none.doc.getElementById('li-btn').hidden, 'no status route: optional features are treated as off');
  assert(!none.doc.getElementById('setup-empty') && !none.doc.getElementById('jobs-list').hidden, 'no status route: no onboarding empty state, the list still shows');

  // Not onboarded: a clear empty state in place of the list.
  const fresh = freshPanel({ status: { onboarded: false, features: { sponsorship: false, outreach: false, email: false, alerts: false } } });
  await settle();
  const setup = fresh.doc.getElementById('setup-empty');
  assert(!!setup && !setup.hidden && setup.textContent === 'Set up your profile first: open this folder in Claude Code and run /onboard.', 'not onboarded: the setup message shows');
  assert(fresh.doc.getElementById('jobs-list').hidden, 'not onboarded: the job list is hidden');

  console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed > 0 ? 1 : 0);
})();

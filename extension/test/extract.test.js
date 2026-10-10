// Loads content.js into a jsdom document and exercises extractJob() against
// three handcrafted fixtures: a LinkedIn-like page, a Workday-like page, and
// a generic page. Run with: node extract.test.js
'use strict';
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const contentJsPath = path.join(__dirname, '..', 'content.js');
const contentJsSource = fs.readFileSync(contentJsPath, 'utf8');

let passed = 0;
let failed = 0;

function assert(cond, msg) {
  if (cond) {
    passed++;
    console.log('  PASS  ' + msg);
  } else {
    failed++;
    console.log('  FAIL  ' + msg);
  }
}

function extractFromHtml(html, url) {
  const dom = new JSDOM(html, { url: url, runScripts: 'outside-only' });
  dom.window.eval(contentJsSource);
  const result = dom.window.extractJob();
  dom.window.close();
  return result;
}

// ---------- Fixture 1: LinkedIn-like ----------
console.log('LinkedIn-like fixture');
const linkedinHtml = `
<!doctype html><html><head><title>Strategy Consultant | LinkedIn</title></head>
<body>
  <div class="job-details-jobs-unified-top-card__job-title">
    <h1>Strategy Insights &amp; Planning Consultant</h1>
  </div>
  <div class="job-details-jobs-unified-top-card__company-name">
    <a href="/company/zs-associates">ZS</a>
  </div>
  <div class="job-details-jobs-unified-top-card__primary-description-container">Chicago, IL (Hybrid)</div>
  <div id="job-details">
${'We are looking for a strategy consultant to join our team. '.repeat(60)}


See more</div>
</body></html>`;
const linkedinResult = extractFromHtml(linkedinHtml, 'https://www.linkedin.com/jobs/view/4396843644/');
// The URL already names the clicked job (Alpha Corp) while the pane still shows the previous one (Beta Corp).
const stalePane = extractFromHtml(
  linkedinHtml.replace('<div class="job-details-jobs-unified-top-card__company-name">',
    '<div class="job-details-jobs-unified-top-card__job-title"><h1><a href="/jobs/view/4457528207/?refId=abc">Solutions Architect</a></h1></div>' +
    '<div class="job-details-jobs-unified-top-card__company-name">'),
  'https://www.linkedin.com/jobs/search-results/?currentJobId=4429389320&eBP=x');
const linkedinAbs = extractFromHtml(
  linkedinHtml.replace('href="/company/zs-associates"', 'href="https://www.linkedin.com/company/ZS-Associates/life/?trk=top-card"'),
  'https://www.linkedin.com/jobs/view/4396843644/');
assert(linkedinResult.source === 'linkedin', 'source is linkedin, got ' + linkedinResult.source);
assert(linkedinResult.title === 'Strategy Insights & Planning Consultant', 'title extracted, got "' + linkedinResult.title + '"');
assert(linkedinResult.company === 'ZS', 'company extracted, got "' + linkedinResult.company + '"');
assert(linkedinResult.company_url === 'https://www.linkedin.com/company/zs-associates',
  'company LinkedIn URL from a relative href, got "' + linkedinResult.company_url + '"');
assert(linkedinResult.location === 'Chicago, IL (Hybrid)', 'location extracted, got "' + linkedinResult.location + '"');
assert(linkedinResult.text.length > 800, 'text length over 800 chars, got ' + linkedinResult.text.length);
assert(!/See more\s*$/i.test(linkedinResult.text), 'trailing "See more" stripped');
assert(linkedinResult.page_title === 'Strategy Consultant | LinkedIn', 'page_title captured');
assert(stalePane.shown_job_id === '4457528207', 'reads the job the pane shows, not the one the URL names, got "' + stalePane.shown_job_id + '"');
assert(linkedinResult.shown_job_id === '', 'no title link means no pane id (the server then trusts the URL), got "' + linkedinResult.shown_job_id + '"');
assert(linkedinAbs.company_url === 'https://www.linkedin.com/company/zs-associates',
  'company LinkedIn URL normalised from an absolute /life link, got "' + linkedinAbs.company_url + '"');

// ---------- Fixture 2: Workday-like ----------
console.log('Workday-like fixture');
const workdayHtml = `
<!doctype html><html><head><title>Careers</title></head>
<body>
  <div data-automation-id="jobPostingHeader">Senior Data Analyst</div>
  <div data-automation-id="locations">Remote - USA</div>
  <div data-automation-id="jobPostingDescription">
${'This role focuses on data analysis and reporting for the operations team. '.repeat(40)}
  </div>
</body></html>`;
const workdayResult = extractFromHtml(workdayHtml, 'https://acme.wd1.myworkdayjobs.com/en-US/ACME/job/Senior-Data-Analyst_R00012');
assert(workdayResult.source === 'workday', 'source is workday, got ' + workdayResult.source);
assert(workdayResult.title === 'Senior Data Analyst', 'title extracted, got "' + workdayResult.title + '"');
assert(workdayResult.company === 'acme', 'company from hostname, got "' + workdayResult.company + '"');
assert(workdayResult.location === 'Remote - USA', 'location extracted, got "' + workdayResult.location + '"');
assert(workdayResult.text.length > 800, 'text length over 800 chars, got ' + workdayResult.text.length);

// ---------- Fixture 3: Generic ----------
console.log('Generic fixture');
const genericHtml = `
<!doctype html><html><head>
  <title>Backend Engineer - Acme Careers</title>
  <meta property="og:title" content="Backend Engineer">
  <meta property="og:site_name" content="Acme Careers">
</head>
<body>
  <nav>Home About Careers</nav>
  <main>
    <h1>Backend Engineer</h1>
    <article>
${'We need a backend engineer who loves distributed systems and clean APIs. '.repeat(30)}
    </article>
  </main>
  <footer>Copyright Acme</footer>
</body></html>`;
const genericResult = extractFromHtml(genericHtml, 'https://careers.example.com/jobs/backend-engineer');
assert(genericResult.source === 'generic', 'source is generic, got ' + genericResult.source);
assert(genericResult.title === 'Backend Engineer', 'title extracted, got "' + genericResult.title + '"');
assert(genericResult.company === 'Acme Careers', 'company extracted, got "' + genericResult.company + '"');
assert(genericResult.text.length > 800, 'text length over 800 chars, got ' + genericResult.text.length);

// ---------- Fixtures 4 to 8: a LinkedIn profile (UI audit step 8) ----------
// HAND-WRITTEN, not saved from a live profile (LinkedIn needs a login). They pin down what extractPerson() does with
// the structure it expects; whether the real page matches is unverified. jsdom has no innerText, so the elements sit on
// their own lines the way innerText would break them.
console.log('LinkedIn profile fixtures');
const profileHtml = `
<!doctype html><html><head><title>(3) Pat Jones - Director, Strategy - Acme Health | LinkedIn</title></head>
<body><main>
  <section class="top-card">
    <h1>Pat Jones (She/Her)</h1>
    <div>· 2nd</div>
    <div class="text-body-medium break-words">Director, Strategy at Acme Health</div>
    <div><span class="text-body-small inline t-black--light break-words">Chicago, Illinois, United States</span></div>
    <div><a href="#">Contact info</a></div>
    <div>500+ connections</div>
    <button>Message</button>
  </section>
  <section><div id="about" class="pv-profile-card__anchor"></div>
    <h2>About</h2>
    <div><span>I lead strategy for a regional health system and care about turning messy operating data into decisions.</span>
    <span>…see more</span></div>
  </section>
  <section><div id="experience" class="pv-profile-card__anchor"></div>
    <h2>Experience</h2>
    <ul>
      <li class="artdeco-list__item">
        <a href="https://www.linkedin.com/company/Acme-Health/?trk=profile"><img alt="Acme Health logo"></a>
        <div><span>Director, Strategy</span>
        <span class="visually-hidden">Director, Strategy</span></div>
        <div><span>Acme Health · Full-time</span>
        <span class="visually-hidden">Acme Health · Full-time</span></div>
        <div>Jan 2022 - Present · 3 yrs 9 mos</div>
      </li>
      <li class="artdeco-list__item">
        <a href="https://www.linkedin.com/company/oldco/"><img alt="Old Co"></a>
        <div>Manager</div>
        <div>Old Co · Full-time</div>
        <div>2018 - 2021 · 3 yrs</div>
      </li>
    </ul>
  </section>
</main></body></html>`;
const person = extractFromHtml(profileHtml, 'https://www.linkedin.com/in/Pat-Jones-123/?miniProfileUrn=x');
assert(person.kind === 'person', 'a /in/ page is a person, not a job, got "' + person.kind + '"');
assert(person.name === 'Pat Jones (She/Her)', 'name from the h1 (the server drops the pronouns), got "' + person.name + '"');
assert(person.headline === 'Director, Strategy at Acme Health', 'headline, got "' + person.headline + '"');
assert(person.location === 'Chicago, Illinois, United States', 'location, got "' + person.location + '"');
assert(person.title === 'Director, Strategy', 'title is the current role from the first Experience entry, got "' + person.title + '"');
assert(person.company === 'Acme Health', 'company from the entry\'s second line, got "' + person.company + '"');
assert(person.company_url === 'https://www.linkedin.com/company/acme-health', 'company link normalised, got "' + person.company_url + '"');
assert(person.linkedin_url === 'https://www.linkedin.com/in/Pat-Jones-123', 'profile link is the clean /in/ address, got "' + person.linkedin_url + '"');
assert(/^I lead strategy/.test(person.about) && !/see more/i.test(person.about), 'About text without the see-more toggle, got "' + person.about + '"');
assert(person.text === '' && person.source === 'linkedin_profile', 'no job text, source says profile');

// A company with its roles listed under it: the company is the first line, the role is the first nested one.
const groupedHtml = `<!doctype html><html><head><title>Lee Park | LinkedIn</title></head><body><main>
  <section><h1>Lee Park</h1>
    <div class="text-body-medium break-words">Head of Talent</div>
    <div class="text-body-small inline t-black--light break-words">New York, NY</div></section>
  <section><div id="experience"></div><h2>Experience</h2><ul><li class="artdeco-list__item">
    <a href="/company/beta-co/"><img alt="Beta Co"></a>
    <div>Beta Co</div>
    <div>Full-time · 6 yrs</div>
    <ul>
      <li>
        <div>Head of Talent</div>
        <div>Jan 2023 - Present · 2 yrs</div>
      </li>
      <li>
        <div>Recruiter</div>
        <div>2019 - 2022 · 3 yrs</div>
      </li>
    </ul>
  </li></ul></section></main></body></html>`;
const grouped = extractFromHtml(groupedHtml, 'https://www.linkedin.com/in/lee-park/');
assert(grouped.company === 'Beta Co' && grouped.title === 'Head of Talent', 'grouped roles: company, then the first role, got "' + grouped.company + '" / "' + grouped.title + '"');
assert(grouped.company_url === 'https://www.linkedin.com/company/beta-co', 'grouped roles: company link from a relative href, got "' + grouped.company_url + '"');

// The first entry has ended: that is not where they work now, so the headline says it or nothing does.
const pastHtml = `<!doctype html><html><head><title>Kim Ro | LinkedIn</title></head><body><main>
  <section><h1>Kim Ro</h1><div class="text-body-medium break-words">Senior Manager at Gamma Inc | Ex-Acme</div></section>
  <section><div id="experience"></div><h2>Experience</h2><ul><li class="artdeco-list__item">
    <a href="/company/acme-health/"></a><div>Analyst</div><div>Acme Health · Full-time</div><div>2016 - 2019 · 3 yrs</div></li></ul></section>
</main></body></html>`;
const past = extractFromHtml(pastHtml, 'https://www.linkedin.com/in/kim-ro/');
assert(past.company === 'Gamma Inc' && past.company_url === '' && past.title === 'Senior Manager',
  'an ended job is not the current company; the headline\'s "at Gamma Inc" is, got "' + past.company + '" / "' + past.company_url + '" / "' + past.title + '"');

// A profile that has not loaded yet: the name comes from the tab title, everything else is empty, nothing throws.
const bareHtml = '<!doctype html><html><head><title>(1) Ana Ruiz - Founder - Delta | LinkedIn</title></head><body><main></main></body></html>';
const bare = extractFromHtml(bareHtml, 'https://www.linkedin.com/in/ana-ruiz/');
assert(bare.kind === 'person' && bare.name === 'Ana Ruiz' && bare.company === '' && bare.about === '', 'a half-loaded profile gives the name from the tab title only, got ' + JSON.stringify(bare));

const longHtml = '<!doctype html><html><head><title>Zed | LinkedIn</title></head><body><main><section><h1>Zed Long</h1></section>' +
  '<section><div id="about"></div><h2>About</h2><div>' + 'Long about text. '.repeat(200) + '</div></section></main></body></html>';
const long = extractFromHtml(longHtml, 'https://www.linkedin.com/in/zed-long/');
assert(long.about.length <= 1000 && long.about.length > 900, 'About is cut to 1,000 characters, got ' + long.about.length);

// ---------- Fixture 9: a profile with hashed class names and no section ids ----------
// Modelled on LinkedIn's current markup: every class is a hash that changes with each deploy, there is no
// <section id="experience">, headings are <h2><span>Experience</span></h2>, titles are written twice (one visually
// hidden), company links wrap a logo. The heuristics cannot be trusted here; the raw material the server's model
// reads must still carry the experience text and every company link. Hand-written, like the others, not saved from a
// live profile.
console.log('LinkedIn profile with hashed markup (raw material for the model)');
const hashedHtml = `
<!doctype html><html><head><title>(2) Jordan Lee - Senior Recruiter - Northbridge Logistics | LinkedIn</title></head>
<body>
<header class="_h0a1"><a href="https://www.linkedin.com/company/linkedin/">LinkedIn for Business</a></header>
<main class="_9f2c1">
  <div class="a7d3e3" data-view-name="profile-top-card">
    <div class="b81f0c"><img alt="Jordan Lee"><h1 class="x2c9a1">Jordan Lee</h1><span class="c4d7e2">&middot; 2nd</span></div>
    <div class="d9a0b4">Senior Recruiter at Northbridge Logistics</div>
    <div class="e31f2d"><span class="f7a1c9">Denver, Colorado, United States</span></div>
    <div><a class="g88e1" href="#">Contact info</a></div>
    <ul class="_i1">
      <li><a class="_j2" href="https://www.linkedin.com/company/northbridge/" aria-label="Current company: Northbridge Logistics. Click to skip to experience card"><img alt="Northbridge Logistics"></a></li>
      <li><a class="_j3" href="https://www.linkedin.com/school/lakeview-university/">Lakeview University</a></li>
    </ul>
    <div>500+ connections</div>
    <button class="_k9">Message</button>
  </div>
  <div class="k3m2p0" componentkey="about-1">
    <h2 class="l9q"><span>About</span></h2>
    <div class="m0z"><span>I partner with hiring leaders across North America. Open to a short chat anytime.</span></div>
  </div>
  <div class="n5r8" componentkey="exp-1">
    <h2 class="o7s"><span>Experience</span></h2>
    <div class="p1t">
      <a class="q2u" href="https://www.linkedin.com/company/northbridge/life?trk=x"><img alt="Northbridge Logistics logo"></a>
      <div class="r3v">
        <div class="s4w"><span aria-hidden="true">Senior Recruiter</span><span class="_vh">Senior Recruiter</span></div>
        <div class="t5x"><span>Northbridge Logistics &middot; Full-time</span></div>
        <div class="u6y">Jun 2024 - Present &middot; 1 yr 4 mos</div>
        <div class="u6z">Denver, Colorado, United States</div>
      </div>
    </div>
    <div class="p1t">
      <a class="q2u" href="/company/meridian/"><img alt="Meridian Systems"></a>
      <div class="r3v">
        <div class="s4w"><span aria-hidden="true">Technical Recruiter</span><span class="_vh">Technical Recruiter</span></div>
        <div class="t5x"><span>Meridian Systems &middot; Full-time</span></div>
        <div class="u6y">2019 - 2024 &middot; 5 yrs</div>
      </div>
    </div>
  </div>
  <div class="v7a">
    <h2 class="w8b"><span>Education</span></h2>
    <div><a href="https://www.linkedin.com/school/lakeview-university/"><span>Lakeview University</span></a></div>
  </div>
  <aside class="_z0">
    <h2><span>People also viewed</span></h2>
    <div><a href="/company/summitadvisory/"><span>Summit Advisory</span></a></div>
  </aside>
</main></body></html>`;
const hashed = extractFromHtml(hashedHtml, 'https://www.linkedin.com/in/jlee/');
const rawH = hashed.raw || {};
assert(hashed.kind === 'person' && hashed.name === 'Jordan Lee', 'hashed markup: still a person with the name, got "' + hashed.name + '"');
assert(rawH.h1 === 'Jordan Lee' && /Senior Recruiter - Northbridge Logistics/.test(rawH.page_title), 'hashed markup: raw carries the h1 and the tab title, got ' + JSON.stringify([rawH.h1, rawH.page_title]));
assert(/Senior Recruiter at Northbridge Logistics/.test(rawH.top_card) && /Denver, Colorado/.test(rawH.top_card) && !/Technical Recruiter/.test(rawH.top_card),
  'hashed markup: the top card text has the headline and the place and stops before Experience, got "' + rawH.top_card + '"');
assert(/Senior Recruiter/.test(rawH.experience) && /Northbridge Logistics . Full-time/.test(rawH.experience) && /Jun 2024 - Present/.test(rawH.experience) && /Technical Recruiter/.test(rawH.experience),
  'hashed markup: the Experience text is there with the current role and its dates, got "' + (rawH.experience || '').replace(/\n/g, ' / ') + '"');
assert(!/Education|Lakeview|People also viewed/.test(rawH.experience), 'hashed markup: the Experience text stops at the next heading, got "' + (rawH.experience || '').replace(/\n/g, ' / ') + '"');
const hrefs = (rawH.company_links || []).map(function (l) { return l.href; });
assert(hrefs.length >= 3 && /company\/northbridge/.test(hrefs[0]) && hrefs.some(function (h) { return /company\/meridian/.test(h); }) && !hrefs.some(function (h) { return /school/.test(h); }),
  'hashed markup: every /company/ link is sent, none of the /school/ ones, got ' + JSON.stringify(hrefs));
const nbLink = (rawH.company_links || []).filter(function (l) { return /company\/northbridge\/\?|company\/northbridge\/life/.test(l.href) || /northbridge\/$/.test(l.href); });
assert((rawH.company_links || []).some(function (l) { return /northbridge/.test(l.href) && /Northbridge Logistics/.test(l.text); }), 'hashed markup: a link carries its text from the logo or its label, got ' + JSON.stringify(rawH.company_links));
assert(hrefs.indexOf(hrefs.filter(function (h) { return /meridian/.test(h); })[0]) > hrefs.indexOf(hrefs.filter(function (h) { return /northbridge/.test(h); })[0]) && /summitadvisory/.test(hrefs[hrefs.length - 1]),
  'hashed markup: links are in page order, got ' + JSON.stringify(hrefs));
assert(hashed.company === 'Northbridge Logistics' && hashed.title === 'Senior Recruiter', 'hashed markup: the heuristics fall back to the headline, got "' + hashed.company + '" / "' + hashed.title + '"');
assert(/^I partner with hiring leaders/.test(hashed.about), 'hashed markup: About comes from the lines under its heading, got "' + hashed.about + '"');
const rawSize = (rawH.h1 + rawH.page_title + rawH.top_card + rawH.experience).length;
assert(rawSize > 100 && rawSize <= 8000, 'hashed markup: the raw text is within 8,000 characters, got ' + rawSize);

// A very long Experience section is cut so the whole payload stays near 8,000 characters.
const bigExp = hashedHtml.replace('<div class="u6z">Denver, Colorado, United States</div>',
  '<div class="u6z">' + 'Led a very large programme of work. '.repeat(600) + '</div>');
const bigH = extractFromHtml(bigExp, 'https://www.linkedin.com/in/jlee/');
const bigSize = bigH.raw.h1.length + bigH.raw.page_title.length + bigH.raw.top_card.length + bigH.raw.experience.length;
assert(bigSize <= 8000 && bigH.raw.experience.length > 4000 && /Senior Recruiter/.test(bigH.raw.experience), 'hashed markup: a huge Experience section is cut to the cap, got ' + bigSize);

// A page where nothing is findable still returns raw material (the page heading) and never throws.
const emptyRaw = extractFromHtml('<!doctype html><html><head><title>Ana Ruiz | LinkedIn</title></head><body><main><h1>Ana Ruiz</h1></main></body></html>', 'https://www.linkedin.com/in/ana-ruiz/');
assert(emptyRaw.raw && emptyRaw.raw.h1 === 'Ana Ruiz' && Array.isArray(emptyRaw.raw.company_links) && emptyRaw.raw.company_links.length === 0, 'a bare profile still carries its raw object, got ' + JSON.stringify(emptyRaw.raw));

// A LinkedIn job page is still a job.
const jobStill = extractFromHtml(linkedinHtml, 'https://www.linkedin.com/jobs/view/4396843644/');
assert(jobStill.kind === undefined && jobStill.title === 'Strategy Insights & Planning Consultant', 'a /jobs/ page still reads as a job, got ' + jobStill.kind);

console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed > 0 ? 1 : 0);

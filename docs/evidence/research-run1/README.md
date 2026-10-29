# Research run 1 (pilot): 50-site study on the Raspberry Pi, 28 October 2026

Run `20261027T1404Z` (UTC; 01:04 Sydney time, 28 October). Raspberry Pi 5, 4 GB, Debian 13, system Chromium (headless, default user agent), Playwright; resolver 1.1.1.1/1.0.0.1 (recorded in `rq1-status.json`); home broadband via Wi-Fi; dwell 8 s, timeout 30 s, no consent interaction, fresh browser per site.

## RQ1: what the 50 home pages contacted (`rq1-report.md`, `rq1-crawl.log`)

- Capture coverage: **34 ok, 2 partial, 14 failed**. By sector, ok captures: government 8/10, health 9/10, education 6/10, news media 7/10, e-commerce 4/10. Most failures returned one request or an identical 17-request page (bot-protection responses to the automated browser): ato.gov.au, homeaffairs.gov.au, news.com.au, dailytelegraph.com.au, woolworths.com.au, officeworks.com.au, bigw.com.au (HTTP/2 error), ebay.com.au, catch.com.au, kogan.com, amazon.com.au, mayoclinic.org, unimelb.edu.au, monash.edu, qut.edu.au, deakin.edu.au; 7news.com.au timed out. Coles, Harvey Norman and Bupa returned challenge scripts (193 fingerprint-API events each).
- 5,166 requests: 3,542 third-party, 776 to listed trackers, 0 configured-identifier matches (no identity configured; the crawler does not enter data, so this is expected, not evidence of absence).
- Mean per-site share of requests to listed trackers (successful captures): health 17.2%, education 16.6%, news media 13.0%, government 10.5%, e-commerce 3.5% (only 4 e-commerce sites captured).
- Located requests estimated outside Australia (GeoLite2, request level): e-commerce 94%, health 85%, news 80%, education 74%, government 67%. Much of this is CDN infrastructure whose addresses GeoLite2 places in the US; an estimate of the answering address, not of data storage.
- Notable recipients (sites that sent at least one request): Google Analytics/Tag Manager 28 sites; LinkedIn 7; Microsoft Clarity session recording 7, including amsa.gov.au and betterhealth.vic.gov.au; Bing Ads 6; TikTok analytics 5 (healthdirect.gov.au, medibank.com.au, rmit.edu.au, usyd.edu.au, uts.edu.au); Reddit 5; Hotjar 4, including abs.gov.au; Snapchat 3. A request to a tracker is an observation, not proof of what was sent or how it is used.

## RQ2: the product's link checker on the same sites (`rq2-summary.md`, `rq2-scores.csv`)

- 49 of 50 assessed (7news.com.au timed out). **0 rated Dangerous** (no false alarms), 28 Low risk, 21 Be careful. Median score 20.
- "Be careful" on these legitimate sites came from tracking signals (trackers 45 sites, third parties 45, servers outside AU 48, fingerprinting reads 22) and, on 9 sites, the scam-wording rule.
- 48 of 49 sites had at least one third-party server outside Australia (US 48, SG 6).

## Design change found by the evaluation: scam wording

The scam-wording rule fired on 9 legitimate sites, each time on one everyday phrase: "gift card" (6 retailers/insurers), "act now" (homeaffairs.gov.au), "unusual activity" (Kogan's bot-check page). The rule now counts one strong phrase ("verify your account", "verify you are human", "press Win + R"…) or at least two weaker ones. Recomputed from the recorded reasons and the phrases seen when the nine sites were re-checked:

| Site | Phrase | Score before | Score after | Rating before → after |
| --- | --- | ---: | ---: | --- |
| homeaffairs.gov.au | act now | 25 | 15 | caution → low |
| bupa.com.au | gift card | 35 | 25 | caution → caution |
| medibank.com.au | gift card | 35 | 25 | caution → caution |
| amazon.com.au | gift card | 25 | 15 | caution → low |
| ebay.com.au | not seen in the re-check | 35 | 35 or 25 | caution → caution |
| kogan.com | unusual activity | 25 | 15 | caution → low |
| jbhifi.com.au | gift card | 55 | 45 | caution → caution |
| coles.com.au | gift card | 40 | 30 | caution → caution |
| officeworks.com.au | gift card | 35 | 25 | caution → caution |

Ratings with the refined rule: 31 Low risk, 18 Be careful, 0 Dangerous, 1 not assessed. The four sample links keep their ratings (their phrases are strong ones). Because the change was informed by these same 50 sites, these figures are not an independent test; a fresh set of sites would be needed for that.

## Coverage and method notes

- The pilot found that bot protection answers the headless crawler with block pages on about a third of the sites. **No attempt was made to bypass it**: the crawler keeps its own user agent, and RQ1 conclusions are limited to the captured sites. A change to disguise the crawler was considered and rejected as bot-check circumvention.
- The product's sandbox uses an ordinary browser user agent by design, so that scam pages that hide from automated browsers are still seen. In RQ2 it was therefore served normal pages by several sites that had blocked the crawler; RQ1 and RQ2 coverage differ for that reason.
- One run, one network, one time of day. Repeat runs on other days with the same protocol before comparing sectors.

# Link checker on the frozen site list

Run 2026-10-27 14:21 UTC on `Lab`; 49 of 50 sites assessed. DNS: 1.1.1.1, 1.0.0.1.
Every site is a legitimate organisation's home page: a "Dangerous" rating is a false alarm. "Be careful" on these sites reflects tracking and advertising signals, not malicious behaviour.

| Rating | Sites | Share |
| --- | ---: | ---: |
| Low risk | 28 | 56% |
| Be careful | 21 | 42% |
| Dangerous | 0 | 0% |
| Not assessed | 1 | 2% |

Median score: 20. False alarms (Dangerous): **0**.

## By sector

| Sector | Sites | Low | Careful | Dangerous | Not assessed | Median score | Mean trackers | Sites with servers outside AU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| government | 10 | 9 | 1 | 0 | 0 | 20.0 | 2.7 | 10 |
| health | 10 | 7 | 3 | 0 | 0 | 20.0 | 8.1 | 10 |
| education | 10 | 7 | 3 | 0 | 0 | 20.0 | 8.9 | 10 |
| news_media | 10 | 3 | 6 | 0 | 1 | 25 | 16.7 | 10 |
| ecommerce | 10 | 2 | 8 | 0 | 0 | 30.0 | 5.4 | 9 |

## What drove the scores (sites with each rule)

- `offshore`: 48
- `trackers`: 45
- `third_parties`: 45
- `fingerprinting`: 22
- `scam_wording`: 9
- `cross_site_redirects`: 4
- `device_prompt`: 2
- `notification_prompt`: 2

## Servers outside Australia: 48 of 49 sites

- US: 48 sites
- SG: 6 sites
- DE: 2 sites
- KR: 2 sites
- FR: 1 sites
- CN: 1 sites
- VN: 1 sites

## Most common tracker owners

- Google: 37 sites
- Microsoft: 18 sites
- Adobe: 13 sites
- ByteDance: 10 sites
- Optimizely: 7 sites
- Cloudflare: 6 sites
- Reddit: 6 sites
- Tealium: 6 sites
- Akamai: 5 sites
- Snap: 5 sites

## Not assessed

- https://www.7news.com.au: Page.goto: Timeout 15000ms exceeded.

## Limits

- One anonymous visit per site, home page only, no consent banner interaction.
- Country is a GeoLite2 estimate of the server address, not where data is stored (APP 8 needs more than this).
- Tracker labels come from EasyPrivacy and Tracker Radar; unknown stays unknown.
- This measures false alarms on legitimate sites only. Detection of real scams needs a labelled set of phishing links, which this run does not include.

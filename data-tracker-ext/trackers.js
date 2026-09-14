// trackers.js - Enhanced tracker intelligence database
// Each entry maps a domain fragment to its parent company, country, and category.
export const TRACKER_DATABASE = {
  // === GOOGLE (USA) ===
  "google-analytics.com":   { company: "Google",       country: "US", category: "Analytics" },
  "googletagmanager.com":   { company: "Google",       country: "US", category: "Tag Manager" },
  "doubleclick.net":        { company: "Google",       country: "US", category: "Advertising" },
  "googlesyndication.com":  { company: "Google",       country: "US", category: "Advertising" },
  "googleadservices.com":   { company: "Google",       country: "US", category: "Advertising" },
  "google.com/pagead":      { company: "Google",       country: "US", category: "Advertising" },
  "youtube.com":            { company: "Google",       country: "US", category: "Embedded Media" },

  // === META / FACEBOOK (USA) ===
  "facebook.com":           { company: "Meta",         country: "US", category: "Social Tracking" },
  "facebook.net":           { company: "Meta",         country: "US", category: "Social Tracking" },
  "fbcdn.net":              { company: "Meta",         country: "US", category: "CDN / Tracking" },
  "instagram.com":          { company: "Meta",         country: "US", category: "Social Tracking" },
  "connect.facebook.net":   { company: "Meta",         country: "US", category: "Social SDK" },

  // === MICROSOFT (USA) ===
  "clarity.ms":             { company: "Microsoft",    country: "US", category: "Analytics" },
  "bing.com":               { company: "Microsoft",    country: "US", category: "Advertising" },

  // === AMAZON (USA) ===
  "amazon-adsystem.com":    { company: "Amazon",       country: "US", category: "Advertising" },

  // === AD NETWORKS (VARIOUS) ===
  "criteo.com":             { company: "Criteo",       country: "FR", category: "Advertising" },
  "criteo.net":             { company: "Criteo",       country: "FR", category: "Advertising" },
  "outbrain.com":           { company: "Outbrain",     country: "US", category: "Content Ads" },
  "taboola.com":            { company: "Taboola",      country: "US", category: "Content Ads" },
  "adzerk.net":             { company: "Kevel",        country: "US", category: "Ad Serving" },
  "rubiconproject.com":     { company: "Magnite",      country: "US", category: "Ad Exchange" },
  "pubmatic.com":           { company: "PubMatic",     country: "US", category: "Ad Exchange" },
  "openx.net":              { company: "OpenX",        country: "US", category: "Ad Exchange" },
  "adnxs.com":              { company: "Xandr (Microsoft)", country: "US", category: "Ad Exchange" },

  // === ANALYTICS & MEASUREMENT ===
  "hotjar.com":             { company: "Hotjar",       country: "MT", category: "Session Recording" },
  "scorecardresearch.com":  { company: "comScore",     country: "US", category: "Audience Measurement" },
  "quantserve.com":         { company: "Quantcast",    country: "US", category: "Audience Measurement" },
  "newrelic.com":           { company: "New Relic",    country: "US", category: "Performance" },
  "segment.io":             { company: "Twilio",       country: "US", category: "Data Pipeline" },
  "segment.com":            { company: "Twilio",       country: "US", category: "Data Pipeline" },
  "mixpanel.com":           { company: "Mixpanel",     country: "US", category: "Analytics" },
  "amplitude.com":          { company: "Amplitude",    country: "US", category: "Analytics" },

  // === CUSTOMER DATA / IDENTITY ===
  "demdex.net":             { company: "Adobe",        country: "US", category: "Data Management" },
  "omtrdc.net":             { company: "Adobe",        country: "US", category: "Analytics" },
  "liveramp.com":           { company: "LiveRamp",     country: "US", category: "Identity Resolution" },
  "rlcdn.com":              { company: "LiveRamp",     country: "US", category: "Identity Resolution" },
  "onetrust.com":           { company: "OneTrust",     country: "US", category: "Consent Management" },
  "cookielaw.org":          { company: "OneTrust",     country: "US", category: "Consent Management" },

  // === SOCIAL ===
  "twitter.com":            { company: "X Corp",       country: "US", category: "Social Tracking" },
  "x.com":                  { company: "X Corp",       country: "US", category: "Social Tracking" },
  "tiktok.com":             { company: "ByteDance",    country: "CN", category: "Social Tracking" },
  "linkedin.com":           { company: "Microsoft",    country: "US", category: "Social Tracking" },
  "snap.com":               { company: "Snap Inc.",    country: "US", category: "Social Tracking" },
  "snapchat.com":           { company: "Snap Inc.",    country: "US", category: "Social Tracking" },
  "pinterest.com":          { company: "Pinterest",    country: "US", category: "Social Tracking" },
};

// Country full names for display
export const COUNTRY_NAMES = {
  "US": "United States",
  "FR": "France",
  "CN": "China",
  "MT": "Malta",
  "AU": "Australia",
  "GB": "United Kingdom",
  "DE": "Germany",
  "SG": "Singapore",
  "JP": "Japan",
  "IE": "Ireland",
};

// Country flag emojis
export const COUNTRY_FLAGS = {
  "US": "🇺🇸", "FR": "🇫🇷", "CN": "🇨🇳", "MT": "🇲🇹", "AU": "🇦🇺",
  "GB": "🇬🇧", "DE": "🇩🇪", "SG": "🇸🇬", "JP": "🇯🇵", "IE": "🇮🇪",
};

/**
 * Look up tracker info for a given domain.
 * Returns { company, country, category } or null if not a known tracker.
 */
export function lookupTracker(domain) {
  for (const [pattern, info] of Object.entries(TRACKER_DATABASE)) {
    if (domain.includes(pattern)) {
      return info;
    }
  }
  return null;
}

/**
 * Check if a domain is a known tracker.
 */
export function isTracker(domain) {
  return lookupTracker(domain) !== null;
}

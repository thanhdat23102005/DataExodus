# Try DataExodus Box with your own phone

DataExodus Box is a Raspberry Pi 5 privacy prototype. It runs its own Wi-Fi network. Suspicious links are opened on the Pi, never on your phone.

## 1. Join the Wi-Fi

Scan the first QR code on the card, or join **DataExodus-Box** with the password printed on the card. The welcome page should open by itself: "Sign in to network" on Android, or a pop-up window on iPhone. If it does not, open **http://10.42.0.1** in your browser.

## 2. Choose what is recorded

- **Show my device's connections:** records the server names your phone looks up (DNS) for 24 hours, so the *My device* page can show them to you. Only your phone can see them. Untick it and nothing is recorded.
- **Block known trackers:** advertising and analytics names get no answer, for your phone only. Some adverts or apps may stop working while it is on.

Press **Join and continue**. You are now online.

## 3. Check a link

Open **Check a link**. Try the four samples. They are fictional sites served by the Pi itself, with nothing harmful on them. You can also paste a link, or a whole text message or email that contains one: a real scam message you have received works best.

The Pi opens the link in a throwaway browser that has no cookies or logins and is firewalled from this network. It then shows:

- a **score from 0 to 100** and every reason behind it (for example: a password form that sends what you type to another site, a forced download, writing to the clipboard, a notification request, a lookalike brand name, trackers, servers outside Australia);
- where the link really goes (the redirect chain), with a screenshot;
- a clean copy of the link without click-tracking IDs.

## 4. Safe Browse

On a result, press **Open in Safe Browse**. The page runs on the Pi and you see pictures of it. Tap the picture to click. Use the arrow buttons to scroll or go back. To type, tap a field in the picture, then use the text box under it. Try it on the fake bank sample: tap *Password*, type anything, then press **Enter ↵**. The page then shows where the form sent your typing. Never type real passwords here.

## 5. My device (if you ticked it)

Use a few apps or websites, then open **My device**. It shows which companies your phone contacted, where their servers are, and which lookups were trackers. Switch on **Block known trackers** and watch the *blocked* labels appear.

## 6. When you finish

Press **Forget this device**. Your choices and recorded lookups are deleted at once. Then forget the Wi-Fi network on your phone.

**Limits.** A score comes from one anonymous visit, and scam pages can show different content to automated browsers. A low score is not a guarantee. The DNS view cannot see apps that use a VPN or encrypted DNS (Private DNS, Secure DNS). The full scoring rules are on the portal's *How it works* page.

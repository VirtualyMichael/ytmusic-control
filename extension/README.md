# ytmusic-control: YouTube Music bridge (browser extension)

A small Chrome / Edge extension that lets the **ytmusic-control helper on your own PC** (its CLI, an AI agent skill or an MCP server) search and play songs in **your signed-in YouTube Music**, in the tab or app window you already have open.

It is three short files you can read in a few minutes: `manifest.json`, `background.js`, `content.js`.

## What it does

1. `background.js` keeps a connection to the helper at `ws://127.0.0.1:47821` (ports 47821 to 47825). That address only exists on your computer; nothing goes to the internet.
2. The helper sends one of a few commands: `search`, `click`, `state`, `control` (play/pause/next/previous), `ping`.
3. `library` (only when you press *Refresh* in the app, or once a day): `background.js` asks YouTube Music, from inside your own signed-in page and exactly as the page does, for the names of your playlists and the title and artist of every track in them, and hands that list to the helper so it can recognise what you ask for.
4. `content.js`, which runs only on `music.youtube.com`, does what you would do by hand: types into the page's own search box, reads the visible result rows (title, subtitle, play button), presses the play button of the one the helper picked, and reports the player's title and paused/playing state.

The helper ranks the results and decides what to click; the extension only reports and clicks.

## What it can access

- **Sites:** only `https://music.youtube.com/*` (`host_permissions`). It cannot read any other site.
- **Browser permissions:** `tabs` (to find your YouTube Music tab and tell whether it is playing), `scripting` (to inject its page script into a YouTube Music tab that was already open when you installed it), `alarms` (to reconnect to the app if the browser put the extension to sleep).
- **Data it sends to the helper:** search result titles and subtitles, the currently playing title and artist, paused/playing, and (on refresh) your playlist names with each track's title, artist and video id. Nothing else: no cookies, no account details, no watch history. The helper keeps that list in `~/.ytm-control` on your PC.

## Who can talk to it

The helper accepts a connection only from `127.0.0.1`, and only from an extension: the browser itself reports who is connecting, so a web page shows up as its own `https://` origin and is refused. The first extension that connects is remembered (its ID is saved in `~/.ytm-control/extension-id`) and the only one accepted from then on. The `key` in `manifest.json` is there so the extension keeps the same ID on every PC and reinstall; the matching private key was discarded and is not needed to run it.

## Install (one time)

1. Run `ytm-control extension-path` (or use the `extension` folder of this repository).
2. In Chrome or Edge open `chrome://extensions` (or `edge://extensions`) and switch on **Developer mode**.
3. Click **Load unpacked** and choose the `extension` folder.
4. Keep the browser open and run `ytm-control status`: it should say the extension is connected.

Browsers show a "disable developer mode extensions" notice when they start, for any extension loaded this way. Dismiss it; it is the browser's standard warning, not a problem with this one.

## Remove

Remove it on `chrome://extensions`. Nothing else is installed in the browser.

## Limits

- Browsers can block a page from starting audio by itself if you have never interacted with that tab; YouTube Music in an app window you use normally is not affected. If that happens the helper says it opened the song and that you need to press play.
- It works with the current YouTube Music web page layout. If YouTube Music changes its page, the selectors in `content.js` may need updating; the helper then reports that it could not read the page.
- Tested in Chrome; Edge uses the same extension format.

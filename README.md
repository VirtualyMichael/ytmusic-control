# ytmusic-control

Let a script, an AI agent or an MCP-capable app **play and control the YouTube Music you are already signed in to**, in your normal browser. No API keys, no paid credits, no separate browser profile, no screenshots.

```text
$ ytm-control play "Continuum by SLVM Lord"
Playing Continuum by SLVMLORD (a song) in YouTube Music.

$ ytm-control playlist "early morning"
Playing your playlist 'Early Morning', starting with Dance With Me by Sam Smith.

$ ytm-control play "Continuum by Metallica"
Could not find 'Continuum by Metallica'. Nothing played. The closest results were: Continuum by Lemaitre; Continuum by SLVMLORD.
```

It comes in four small parts, all in this repository and all readable:

| Part | What it is |
| --- | --- |
| `extension/` | A Chrome / Edge extension (plain JavaScript, about 250 lines). It works inside your own YouTube Music tab: types into the page's search box, reads the visible results, presses play, reads the player. |
| `ytm_control/` | A small Python helper that talks to the extension over `127.0.0.1` and offers a CLI and an MCP server. |
| `skills/youtube-music/SKILL.md` | A skill file that teaches an AI agent (Claude Code or any agent that loads skills) to use the CLI well. |
| `ytm-control mcp` | An MCP server (stdio) with the same abilities as tools, for any MCP-capable app. |

Any app that can run a shell command or speak MCP can use it.

## Why a browser extension

YouTube Music has no public API for controlling playback. This works the way you would: through the page itself, in your already signed-in session. That is also why it needs no login from the tool and why your account details never leave your browser.

## Install

You need Python 3.10+, Chrome or Edge, and YouTube Music open in a tab or installed as an app window.

```bash
pip install git+https://github.com/VirtualyMichael/ytmusic-control
```

1. Run `ytm-control extension-path` and note the folder it prints.
2. In Chrome or Edge open `chrome://extensions` (or `edge://extensions`), turn on **Developer mode**, press **Load unpacked** and pick that folder.
3. Keep the browser open, then run `ytm-control status`. It should say the extension is connected (it can take up to about 30 seconds after the helper first starts).
4. `ytm-control play "Maps by Maroon 5"`.

The helper starts itself in the background the first time you run a command; `ytm-control serve` runs it in the foreground.

### As an agent skill

Copy `skills/youtube-music` into your agent's skills folder (for Claude Code: `~/.claude/skills/youtube-music`). The agent then runs the CLI for requests like "play something by Stellardrone" or "skip this song".

### As an MCP server

Add this to your MCP client's configuration:

```json
{ "mcpServers": { "youtube-music": { "command": "python", "args": ["-m", "ytm_control", "mcp"] } } }
```

Tools: `play_music`, `play_playlist`, `music_action` (like, unlike, shuffle, radio), `search_music`, `play_result`, `music_control`, `now_playing`, `library_find`, `library_refresh`. `search_music` followed by `play_result` lets the model read the whole result list and choose, instead of trusting one guess.

## What makes it dependable

- **Names are compared with spaces ignored**, so a speech recogniser's "SLVM Lord" finds "SLVMLORD".
- **It never plays a different artist's song with the right title.** If nothing matches it says so and lists the closest results, so an agent can look at them and decide.
- **Real songs beat lyric videos, karaoke and covers**, and "Eternity" beats "Eternity (Reprise)".
- **It checks that the right song actually started** instead of reporting success after a click.
- **Names that cannot be read aloud**: stylised spellings are matched by how they sound, so "Slum Lord" finds SLVMLORD (V stands in for U), "Kr3w" finds Krew, and spelling the first letters ("S L V M lord") works too. A sound-alike is never allowed to beat an exact spelling, and a different artist with the right title is still refused.
- **Your library**: `ytm-control library refresh` reads all your playlists and the title and artist of every song in them (from your signed-in page, saved on your PC in `~/.ytm-control/ytm-library.json`). Spoken or typed names are then put into your own spelling before searching.

## Security and privacy

- The extension is allowed on `https://music.youtube.com/*` only, with the permissions `tabs`, `scripting` and `alarms`. It talks only to `ws://127.0.0.1:47821-47825`, never the internet. See [`extension/README.md`](extension/README.md).
- The helper accepts a WebSocket connection only from an extension (the browser reports the origin, so a web page is refused), and only from the **first extension that connects**, which it then remembers.
- The command-line / MCP side talks to the helper over a local HTTP API on `127.0.0.1:47830-47832` that requires a secret token stored in `~/.ytm-control/token`, refuses any request a browser makes cross-site (an `Origin` header), and refuses unexpected `Host` names (DNS rebinding).
- Nothing is sent anywhere. There is no telemetry.

## Limits, honestly

- Unofficial. It drives YouTube Music's web page, which Google can change; if it stops finding results, the selectors in `extension/content.js` need updating. Using it is your decision under YouTube's terms of service.
- Needs the browser open with a YouTube Music tab (it opens one for you if none is open).
- A browser can block a page from starting audio when you have never interacted with that tab; the tool then says the song is loaded and you need to press play.
- Playlists: only your *saved* playlists can be played by name (run `ytm-control library refresh` once). A name that is not in your library is refused, with the closest names listed, rather than guessed.
- Tested with fake browsers and a fake page, plus live checks in Chrome on Windows. Not yet tested on macOS or Linux.

## Development

```bash
pip install -e ".[dev]"
pytest
node tests/extension_test.mjs
```

## Origin

Extracted from the YouTube Music control in [Voice Assistant](https://github.com/VirtualyMichael/voice-assistant), a hands-free Windows voice assistant.

## License

MIT, see [LICENSE](LICENSE).

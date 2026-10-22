---
name: youtube-music
description: Play, pause, skip and look up music in the user's own signed-in YouTube Music (in their normal browser) by running the `ytm-control` command. Use when the user asks to play a song, artist or album, pause or resume, skip, go back, or asks what is playing.
---

# YouTube Music

Controls the YouTube Music tab or app window the user already has open and is signed in to, through the `ytmusic-control` browser extension. No API keys, no credits.

## Commands

Run these in a shell. They start the background helper automatically.

| Goal | Command |
| --- | --- |
| Play a song | `ytm-control play "Maps by Maroon 5"` (use `Song by Artist` when the artist is known) |
| See what the page offers, without playing | `ytm-control search "Maps Maroon 5"` |
| Play one of those results | `ytm-control click row 2` (the kind and number printed by `search`) |
| Play one of the user's saved playlists | `ytm-control playlist "early morning"` (needs the library; run `library refresh` once if it says none is saved) |
| Like / unlike the playing song, play more like it, shuffle | `ytm-control like`, `ytm-control unlike`, `ytm-control radio`, `ytm-control shuffle` |
| Pause / resume / next / previous | `ytm-control pause`, `ytm-control resume`, `ytm-control next`, `ytm-control previous` |
| What is playing | `ytm-control now` |
| Is the song in the user's saved playlists, and how is it spelled there | `ytm-control library find "continuum by slvm lord"` |
| Check the setup | `ytm-control status` |

If the project provides MCP tools instead (`play_music`, `search_music`, `play_playlist`, `music_action`, `play_result`, `music_control`, `now_playing`, `library_find`), use those the same way.

## How to handle requests

1. For "play X", run `play` with the user's words as spoken. Speech and typing often split or misspell names ("SLVM Lord" is "SLVMLORD"); the helper compares names with spaces ignored and uses the spelling from the user's own library when it knows the song.
2. Believe the result. `Playing ...` means the page really started that song. `Could not find ...` means nothing on the page matched both the title and the artist; it deliberately did not play a different artist's song with the same title.
3. When it could not find the song, do not guess. Run `search` with other wording (artist first, drop extra words, try the album), read the list yourself, and use `click` on the result that really is what the user asked for. Say which one you picked. If none is right, tell the user it is not on YouTube Music rather than playing something similar.
4. For a vague request ("something relaxing"), pick a concrete song or ask the user which; do not play random results.
5. If a command says the extension is not connected, tell the user: load the `extension` folder in Chrome or Edge (`ytm-control extension-path` prints where it is) and keep the browser open. Do not try to work around it.
6. Never run `library refresh` unless the user asks (it reads every playlist from their signed-in page and can take a minute).

## What it will not do

It controls only YouTube Music in the user's browser. It cannot like, add to playlists, or change the account. Playlists it can play are only the user's saved ones. If it says no saved playlist has that name, read the closest names it lists and ask the user which they meant; do not substitute a song search.

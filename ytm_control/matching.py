"""Matching a spoken or typed music request to YouTube Music search results.

Pure functions, no browser needed: names are compared with spaces ignored ('SLVM Lord' = 'SLVMLORD'), real songs beat lyric/karaoke/cover uploads, a song with
the right title by a different artist is never accepted, and when nothing really matches `choose` raises YtmNoMatch instead of picking something else.
An optional `judge(query, candidates)` callback (a language model, or an agent) can decide the shaky cases."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

STOPWORDS = {"by", "the", "a", "an", "song", "music", "play", "from", "feat", "ft", "on", "in", "youtube", "and", "of"}
KINDS = {"song": 0.45, "video": 0.05, "single": 0.30}  # what a spoken "play X" almost always means
WANT_WORDS = {"album": "album", "ep": "ep", "playlist": "playlist", "mix": "playlist", "radio": "playlist"}



class YtmError(RuntimeError):
    pass



def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9']+", text.lower().replace("&", " and ")) if t]


def kind_of(sub: str) -> tuple[str, str]:
    """('song', 'Stellardrone') from a subtitle like 'Song • Stellardrone • 3.1M plays'."""
    parts = [p.strip() for p in re.split(r"[••]", sub) if p.strip()]
    if not parts:
        return "", ""
    first = parts[0].lower()
    artist = parts[1] if len(parts) > 1 else ""
    artist = re.sub(r"\s+[\d.,]+\s*[KMB]?\s*(plays|views|subscribers|likes).*$", "", artist, flags=re.I).strip()  # "Stellardrone 3.1M plays" -> "Stellardrone"
    return first, artist


JUNK = {"lyrics", "lyric", "cover", "karaoke", "live", "remix", "instrumental", "reaction", "slowed", "reverb", "sped", "8d", "nightcore", "tutorial", "originally",
        "tribute", "version", "acoustic", "piano", "mashup", "bass", "boosted", "loop", "hour"}


def split_request(query: str) -> tuple[list[str], list[str]]:
    """'Maps by Maroon 5' -> (['maps'], ['maroon', '5']); without 'by' the artist part is empty and everything counts as the title."""
    parts = re.split(r"\s+by\s+", query, maxsplit=1, flags=re.I)
    if len(parts) == 2:
        return [t for t in tokens(parts[0]) if t not in STOPWORDS] or tokens(parts[0]), [t for t in tokens(parts[1]) if t not in STOPWORDS] or tokens(parts[1])
    return [t for t in tokens(query) if t not in STOPWORDS] or tokens(query), []


class YtmNoMatch(YtmError):
    """The page has no result that matches what was asked for (so the wrong song must not be played instead)."""

    def __init__(self, message: str, closest: list[str] | None = None):
        super().__init__(message)
        self.closest = closest or []


def compact(text: str) -> str:
    return "".join(tokens(text))


def similarity(a: str, b: str) -> float:
    """0..1 how alike two names are with spaces ignored: 'SLVM Lord' and 'SLVMLORD' are the same name to a speech recogniser."""
    a, b = compact(a), compact(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0 if min(len(a), len(b)) >= 3 else 0.0
    return SequenceMatcher(None, a, b).ratio()


def rank(query: str, cands: list[dict]) -> list[tuple[float, dict]]:
    """Candidates best first (each gets `_title_hit` / `_artist_hit`, 0..1). Rewards a title that covers the requested song name and an artist that covers the
    requested artist (names compared with spaces ignored), prefers real songs, and penalises extra title words (so 'Eternity' beats 'Eternity (Reprise)'),
    lyric/karaoke/cover uploads, albums and playlists (unless asked for) and artist pages."""
    title_q, artist_q = split_request(query)
    all_q = set(title_q) | set(artist_q)
    wanted = {WANT_WORDS[t] for t in all_q if t in WANT_WORDS}
    title_q = [t for t in title_q if t not in WANT_WORDS] or title_q
    out = []
    for c in cands:
        kind, artist = kind_of(c.get("sub", ""))
        title_t, artist_t = set(tokens(c.get("title", ""))), set(tokens(artist))
        if not title_t or not (title_q or artist_q):
            continue
        t_cover = sum(t in title_t for t in title_q) / max(1, len(title_q)) if title_q else 0.0
        title_hit = max(t_cover, similarity(" ".join(title_q), c["title"])) if title_q else 0.0
        if artist_q:
            a_cover = sum(t in artist_t or t in title_t for t in artist_q) / len(artist_q)
            artist_hit = max(a_cover, similarity(" ".join(artist_q), artist) if artist else 0.0)
            artist_hit = artist_hit if artist_hit >= 0.75 else min(artist_hit, a_cover)  # a loose resemblance is not a match
            score = title_hit * 1.6 + artist_hit * 1.4
        else:  # just a name: it may be a title, an artist or both
            artist_hit = 0.0
            have = title_t | artist_t
            score = max(sum(t in have for t in title_q) / max(1, len(title_q)), similarity(" ".join(title_q), artist)) * 2.4
        extra = len(title_t - set(title_q) - set(artist_q)) / max(1, len(title_t))
        score -= extra * 0.5
        score += KINDS.get(kind, 0.0)
        score -= 0.6 * len((title_t & JUNK) - all_q)
        if kind in ("album", "ep", "playlist") and kind not in wanted:
            score -= 2.0
        if kind in wanted:
            score += 1.0
        if kind in ("artist", "profile") or not kind:
            score -= 1.5
        out.append((score, {**c, "_title_hit": title_hit, "_artist_hit": artist_hit}))
    return sorted(out, key=lambda x: -x[0])


def describe(c: dict) -> str:
    kind, artist = kind_of(c.get("sub", ""))
    return f"{c['title']} by {artist}" if artist else c["title"]


def choose(query: str, cands: list[dict], judge=None) -> dict:
    """The best candidate for the request. When the top result is shaky (the requested artist does not match, a weak title match, or two near-equal
    candidates) and a `judge` is given, the judge (a language model reading the whole list) decides. When nothing really matches, raises YtmNoMatch rather
    than playing a different song."""
    ranked = rank(query, cands)
    if not ranked:
        raise YtmNoMatch(f"No results for '{query}' showed up on the page.")
    score, best = ranked[0]
    _, artist_q = split_request(query)
    weak = score < 1.0 or best["_title_hit"] < 0.6 or (bool(artist_q) and best["_artist_hit"] < 0.6)
    close_call = len(ranked) > 1 and score - ranked[1][0] < 0.2 and describe(ranked[1][1]) != describe(best)
    if weak or close_call:
        pick = judge(query, [c for _, c in ranked[:12]]) if judge else None
        if pick is not None:
            return pick
        if weak:
            raise YtmNoMatch(f"Nothing in the results matched '{query}'.", [describe(c) for _, c in ranked[:5]])
    return best


def search_queries(query: str) -> list[str]:
    """The request as spoken, then the same words in 'artist title' order (YouTube Music's search often finds the right song that way)."""
    parts = re.split(r"\s+by\s+", query, maxsplit=1, flags=re.I)
    return [query] + ([f"{parts[1].strip()} {parts[0].strip()}"] if len(parts) == 2 and parts[0].strip() and parts[1].strip() else [])


def no_match_message(query: str, closest: list[str]) -> str:
    seen = list(dict.fromkeys(closest))[:5]
    return f"Could not find '{query}' on YouTube Music. Nothing played." + (" The closest results were: " + "; ".join(seen) + "." if seen else "")


def started(best: dict, state: dict) -> str | None:
    """A 'Playing ...' sentence when the page is really playing the chosen song (not a stale queue entry), else None."""
    if state.get("paused") is False and state.get("title"):
        want = set(tokens(best["title"])) - STOPWORDS
        got = set(tokens(state["title"]))
        if want and len(want & got) / len(want) < 0.5:
            return None
        kind, artist = kind_of(best["sub"])
        what = f"{state['title']} by {artist}" if artist else state["title"]
        return f"Playing {what} (a {kind or 'result'}) in YouTube Music."
    return None

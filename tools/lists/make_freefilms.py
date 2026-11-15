#!/usr/bin/env python3
"""
🎬 "Cinema without a ticket" – the free full-length films that rights holders put on YouTube
themselves (Nathan, 11 Nov 2026: "youtube has so many films … could we make a collector that finds
them all, sorts them and offers them our way?").

Only official, licensed channels (the allowlist below – never user uploads). Once a week (CI,
.github/workflows/freefilms.yml) the channels' uploads are read with the YouTube Data API (about 400
of the project's 10 000 daily units), every video of 60 minutes to 4 hours is kept, and the list
ships inside the app (app/src/main/assets/freefilms.json) – the app itself never spends quota.
The key comes from the environment (YOUTUBE_API_KEY) and is never printed.

What is kept (14 Nov 2026 – "cinema for free hardly works … get the lists a bit better"):
  * only films YouTube lets play inside another app (status.embeddable) and that need no sign-in
    (not age-restricted) – the others never started in the app's player;
  * public, finished uploads, no live streams, no trailers, clips, episodes or compilations;
  * one entry per film and channel: a film put up twice keeps its most watched upload;
  * one entry per film over all channels too (merge_twins): the same name, language and length on
    FilmRise and Popcornflix, or twice on Netzkino under another headline, is shown once.
What each film carries: v video · t title (the channel's advertising words taken off) · c channel ·
l language (the upload's own audio language when YouTube knows it) · m minutes · p day put up ·
y year (from the title or the description, when it says one) · g kinds of film (the letters of
tools/cream: b action, t thriller, c comedy …, from the channel's own words) · n views in thousands ·
x 1 when YouTube has the big picture (maxresdefault) · a/b countries allowed/blocked.

The same run writes the picture of every YouTube channel of Free TV into assets/youtube.json
("pic": the channel's own picture, one API unit for all of them).

Usage: YOUTUBE_API_KEY=… python3 make_freefilms.py app/src/main/assets/freefilms.json
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# The allowlist: (how to find it, language, a short name for the app). Official channels of the
# rights holders and licensed free-film distributors only.
CHANNELS = [
    ({"forUsername": "Netzkino"}, "de", "Netzkino"),
    ({"forHandle": "@FilmRiseMovies"}, "en", "FilmRise"),
    ({"forHandle": "@Popcornflix"}, "en", "Popcornflix"),
    ({"forHandle": "@Grjngo"}, "en", "Grjngo Westerns"),
]
PER_CHANNEL = 2000          # the newest uploads read per channel
MIN_MIN, MAX_MIN = 60, 240  # a feature film's length

KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
API = "https://www.googleapis.com/youtube/v3/"
units = 0


def call(path, **params):
    global units
    units += 1
    again = params.pop("_again", False)
    params["key"] = KEY
    url = API + path + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # (the address holds the key: only the code is told)
        print(f"  {path}: HTTP {e.code}", file=sys.stderr)
        # (YouTube's own hiccup: once more after a moment)
        if e.code >= 500 and not again:
            time.sleep(4)
            params.pop("key", None)
            units -= 1
            return call(path, _again=True, **params)
        return None
    except Exception as e:  # noqa: BLE001
        print(f"  {path}: {type(e).__name__}", file=sys.stderr)
        return None


def minutes(iso):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return d * 1440 + h * 60 + mi + (1 if s >= 30 else 0)


JUNK = re.compile(
    r"(?i)(\b(trailer|teaser|making of|behind the scenes|compilation|playlist|full episodes?|folge \d+|episode \d+|staffel|season \d+"
    r"|best of|interview|podcast|preview|sneak peek|featurette|bloopers|outtakes|deleted scenes|clips?|recap|review|reaction"
    r"|livestream|live stream|24/7|marathon|double feature|triple feature|\d+ (movies|filme)|movie collection|filmnacht|hörbuch|audiobook|hörspiel)\b|#shorts)")

# The words channels put around a title to be found ("ganzer Film Deutsch", "Full Movie", "HD" …)
AD = (r"ganze[rs]? (spiel)?film(e)?( auf| in)? ?(deutsch|german)?|kompletter film|ganzer film|filme? in voller länge|in voller länge|kostenlos(er)?( anschauen)?"
      r"|full (length )?(movie|film)s?|free (full )?(movie|film)s?|full movie english|english (full )?movie|watch free|movie central"
      r"|neue? filme? \d{4}|filme? \d{4}|deutsch|german|english|hd|full hd|4k|uhd|1080p|720p|stream|ganzer|subtitles?|untertitel|engsub|multi ?sub|exklusiv|exclusive|premiere|neu|new")
KIND = (r"action|thriller|krimi|crime|kom[öo]die|comedy|drama|horror|sci-?fi|science[- ]fiction|fantasy|western|abenteuer|adventure|romanze|romance|romcom|romantic|liebesfilm"
        r"|family|familienfilm|kinderfilm|animation|zeichentrick|weihnachtsfilm|christmas|xmas|krieg(sfilm)?|war|mystery|doku(mentation)?|documentary|biopic|biography|historienfilm"
        r"|martial arts|kung fu|superhero|dark|suspense|classic|klassiker|kultfilm|cult|sports?|heist|spy|agenten(film)?|katastrophenfilm|disaster|zombie|vampire?|slasher|erotik|noir")
AD_RE = re.compile(rf"(?i)\b({AD})\b")
KIND_RE = re.compile(rf"(?i)\b({KIND})\b")

# the kinds of film as the cat's list writes them (tools/cream/make_cream.py), with German words
GENRES = [
    ("c", r"comed|kom[öo]die|romcom|satire|parod"), ("d", r"drama"), ("r", r"romanc|romanze|romantic|liebesfilm|romcom"),
    ("t", r"thriller|suspense|mystery"), ("k", r"crime|krimi|heist|gangster|mafia|detektiv|detective"),
    ("s", r"sci-?fi|science[- ]fiction|alien|endzeit|dystop"), ("y", r"fantasy|märchen|fairy ?tale"),
    ("h", r"horror|slasher|zombie|vampir|grusel"), ("b", r"\baction|martial arts|kung fu|superhero|agenten|katastrophenfilm|disaster"),
    ("v", r"adventure|abenteuer"), ("u", r"documentar|doku"), ("w", r"\bwar\b|krieg|histor|biopic|biogra"),
    ("e", r"western"), ("f", r"family|familienfilm|kinderfilm|for kids|für kinder"), ("a", r"animat|zeichentrick|anime|cartoon"),
    ("o", r"\bsports?\b|sportfilm"), ("x", r"christmas|weihnacht|xmas"),
]
GENRE_RES = [(k, re.compile(w, re.I)) for k, w in GENRES]


def genre_letters(*texts):
    hay = " ".join(t for t in texts if t)
    return "".join(k for k, rx in GENRE_RES if rx.search(hay))


SMALL = {"der", "die", "das", "und", "von", "zu", "zur", "zum", "im", "in", "am", "an", "auf", "aus", "mit", "es", "ist", "ein", "eine", "the", "of",
         "a", "and", "to", "for", "on", "at", "by", "is", "la", "le", "de", "el", "du", "des", "für", "vor", "nach", "bei", "oder", "or"}
STAR_WORD = r"(?:[A-ZÄÖÜ][A-ZÄÖÜ.'’\-]*|Mc[A-Z]+|Mac[A-Z]+|De[A-Z]+|&|und|and|präsentiert|presents|ist|is|als|as|von|by|mit|with)"
STAR_RE = re.compile(rf"(?:[A-ZÄÖÜ][A-ZÄÖÜ.'’\-]+ )(?:{STAR_WORD} )*?(?:in|ist|is) (?P<name>[^a-zäöü]{{2,}})")


def clean_title(t):
    """The film's name out of the channel's headline."""
    raw = t
    t = re.sub(r"[\U0001F000-\U0001FFFF☀-➿⬀-⯿️]", " ", t)
    # "Name | Action Thriller | Ganzer Film" · "Name ｜ …" · "Name // …" · "Name • …": the name stands first
    parts = [p.strip() for p in re.split(r"\s*(?:[|｜•]|//| - Full Movie| – Full Movie)\s*", t) if p.strip()]
    def wordy(p):  # a piece that is only advertising or kinds of film
        rest = KIND_RE.sub("", AD_RE.sub("", p))
        return len(re.sub(r"[\W\d_]+", "", rest)) < 3
    parts = [p for p in parts if not wordy(p)] or parts[:1]
    t = parts[0] if parts else t
    # brackets that hold advertising: "(ACTION THRILLER ganzer Film Deutsch, Filme in voller Länge)"
    t = re.sub(r"\s*[\(\[]([^\)\]]*)[\)\]]", lambda m: "" if (AD_RE.search(m.group(1)) or KIND_RE.search(m.group(1)) or re.fullmatch(r"\s*(19|20)\d\d\s*", m.group(1))) else m.group(0), t)
    # "Name - Ganzer Film …", "Name: Full Movie …", "Name – kostenloser Spielfilm"
    t = re.sub(rf"(?i)\s*[-–—:,]\s*({AD})\b.*$", "", t)
    # "Name Action, Superhero, Dark Sci-Fi, HD" – a row of kinds at the end (two or more, with commas)
    t = re.sub(rf"(?i)\s+((?:{KIND}|{AD})\s*(?:[,/&]\s*|\s+)){{1,}}(?:{KIND}|{AD})\s*$", lambda m: "" if "," in m.group(0) or "/" in m.group(0) else m.group(0), t)
    t = re.sub(r"(?i)\b(full movie|ganzer film|free movie|full film)\b", "", t)
    t = re.sub(r"\s+", " ", t).strip(" -–—:|,.")
    # "MERYL STREEP in SOLANGE ES NOCH HOFFNUNG GIBT", "RALPH FIENNES ist SPIDER", "VAL KILMER ist JIM
    # MORRISON in THE DOORS": the stars in capitals before the film's name – the name is what follows
    m = STAR_RE.fullmatch(t)
    if m:
        t = m.group("name").strip(" -–—:|,.")
    # a headline all in capitals: as a title ("BERUF: REPORTER" → "Beruf: Reporter")
    letters = [c for c in t if c.isalpha()]
    if len(letters) >= 6 and sum(c.isupper() for c in letters) > 0.85 * len(letters):
        t = " ".join(w.lower() if (i > 0 and w.lower() in SMALL) else w.capitalize() for i, w in enumerate(t.split(" ")))
    return t or raw.strip()


YEAR_TITLE = re.compile(r"[\(\[]\s*((?:19[1-9]|20[0-3])\d)\s*[\)\]]")
YEAR_DESC = re.compile(
    r"(?i)(?:produktionsjahr|erscheinungsjahr|jahr|year|released?|release date|production year|©|\(c\)|copyright)\s*[:\-]?\s*((?:19[1-9]|20[0-3])\d)\b"
    r"|directed by [^#|\n]{2,80}?\s((?:19[1-9]|20[0-3])\d)\b"
    r"|\b(?:usa|us|uk|gb|deutschland|germany|frankreich|france|italien|italy|kanada|canada|spanien|spain|australien|australia|japan|china|hongkong|hong kong|südkorea|south korea|dänemark|schweden|norwegen|irland|ireland|belgien|niederlande|österreich|schweiz|russland|indien|india|mexiko|mexico)\s*,?\s*((?:19[1-9]|20[0-3])\d)\b")


def year_of(title, desc, published):
    m = YEAR_TITLE.search(title)
    y = int(m.group(1)) if m else None
    if y is None:
        m = YEAR_DESC.search(desc[:1500])
        if m:
            y = int(next(g for g in m.groups() if g))
    # (a film cannot be younger than its upload)
    if y and published[:4].isdigit() and y > int(published[:4]):
        return None
    return y


def film_key(title):
    """A film's name as two uploads of it share it: small letters, no brackets, no punctuation."""
    t = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", " ", title.lower())
    return re.sub(r"[\W_]+", "", t)


def merge_twins(films):
    """One entry per film over all channels: the same name (brackets aside) in the same language and of
    the same length (±5 min) – a film on FilmRise and Popcornflix, or put up twice by Netzkino with
    another headline – keeps its most watched upload; a year only the other knew is kept, and the
    plainer name (without a bracket) wins."""
    groups = {}
    for r in films:
        groups.setdefault((film_key(r["t"]), r["l"]), []).append(r)
    out, twins = [], 0
    for rows in groups.values():
        rows = sorted(rows, key=lambda r: r.get("n", 0), reverse=True)
        kept = []
        for r in rows:
            same = next((k for k in kept if abs(k["m"] - r["m"]) <= 5), None) if film_key(r["t"]) else None
            if same is None:
                kept.append(dict(r))
                continue
            twins += 1
            if not same.get("y") and r.get("y"):
                same["y"] = r["y"]
            if not same.get("g") and r.get("g"):
                same["g"] = r["g"]
            if re.search(r"[\(\[]", same["t"]) and not re.search(r"[\(\[]", r["t"]):
                same["t"] = r["t"]
        out += kept
    out.sort(key=lambda r: r["p"], reverse=True)
    return out, twins


def tube_pictures(path):
    """The picture of every YouTube channel of Free TV, written into youtube.json ("pic")."""
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"youtube.json: {type(e).__name__}")
        return
    rows = [c for key in ("channels", "live") for c in data.get(key, []) if isinstance(c, dict) and c.get("id")]
    ids = sorted({c["id"] for c in rows})
    pics = {}
    for i in range(0, len(ids), 50):
        ans = call("channels", part="snippet", id=",".join(ids[i:i + 50]), maxResults=50)
        for it in (ans or {}).get("items", []):
            th = it.get("snippet", {}).get("thumbnails", {})
            url = (th.get("high") or th.get("medium") or th.get("default") or {}).get("url")
            if url and url.startswith("https://"):
                pics[it["id"]] = url
    for c in rows:
        if c["id"] in pics:
            c["pic"] = pics[c["id"]]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"channel pictures: {len(pics)} of {len(ids)}")


def main(out, tube=None):
    if not KEY:
        print("no YOUTUBE_API_KEY – nothing done")
        return 1
    films = []
    samples, descs = [], []
    for how, lang, name in CHANNELS:
        ch = call("channels", part="contentDetails", **how)
        items = (ch or {}).get("items") or []
        if not items:
            print(f"{name}: channel not found")
            continue
        uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        ids, token = [], None
        while len(ids) < PER_CHANNEL:
            page = call("playlistItems", part="contentDetails", playlistId=uploads, maxResults=50, **({"pageToken": token} if token else {}))
            if not page:
                break
            ids += [it["contentDetails"]["videoId"] for it in page.get("items", [])]
            token = page.get("nextPageToken")
            if not token:
                break
        why = {"length": 0, "junk": 0, "not public": 0, "not embeddable": 0, "age": 0, "twice": 0}
        mine = {}
        for i in range(0, len(ids), 50):
            vids = call("videos", part="contentDetails,snippet,status,statistics", id=",".join(ids[i:i + 50]), maxResults=50)
            for v in (vids or {}).get("items", []):
                sn, cd, st = v.get("snippet", {}), v.get("contentDetails", {}), v.get("status", {})
                mins = minutes(cd.get("duration"))
                title = sn.get("title", "")
                if not (MIN_MIN <= mins <= MAX_MIN):
                    why["length"] += 1
                    continue
                if JUNK.search(title):
                    why["junk"] += 1
                    continue
                if st.get("privacyStatus") != "public" or st.get("uploadStatus", "processed") != "processed" or sn.get("liveBroadcastContent", "none") != "none":
                    why["not public"] += 1
                    continue
                # (a film that may not play inside another app never started in ours)
                if st.get("embeddable") is False:
                    why["not embeddable"] += 1
                    continue
                if (cd.get("contentRating") or {}).get("ytRating") == "ytAgeRestricted":
                    why["age"] += 1
                    continue
                desc = sn.get("description", "") or ""
                published = (sn.get("publishedAt") or "")[:10]
                clean = clean_title(title)
                audio = (sn.get("defaultAudioLanguage") or "")[:2].lower()
                row = {"v": v["id"], "t": clean, "c": name, "l": audio if re.fullmatch(r"[a-z]{2}", audio) else lang, "m": mins, "p": published}
                y = year_of(title, desc, published)
                if y:
                    row["y"] = y
                # (the kinds come from the channel's own words around the name – never from the name
                # itself: "War of the Worlds" is no war film – and from its tags)
                around = re.sub(re.escape(clean), " ", title, flags=re.I) if clean else title
                g = genre_letters(around, " ".join(sn.get("tags") or [])[:300])
                if g:
                    row["g"] = g
                views = int((v.get("statistics") or {}).get("viewCount") or 0)
                if views >= 1000:
                    row["n"] = views // 1000
                if "maxres" in (sn.get("thumbnails") or {}):
                    row["x"] = 1
                rr = cd.get("regionRestriction") or {}
                if rr.get("allowed"):
                    row["a"] = rr["allowed"]
                if rr.get("blocked"):
                    row["b"] = rr["blocked"]
                # one entry per film: the same name (and year) twice on a channel keeps the most watched
                key = (re.sub(r"[\W_]+", "", clean.lower()), row.get("y"), row["l"])
                old = mine.get(key)
                if old is not None:
                    why["twice"] += 1
                    if old.get("n", 0) >= row.get("n", 0):
                        continue
                mine[key] = row
                if len(samples) < 400 and clean != title:
                    samples.append((name, title, clean))
                if len(descs) < 12 and len([d for d in descs if d[0] == name]) < 4 and not y:
                    descs.append((name, re.sub(r"\s+", " ", desc[:700])))
        films += mine.values()
        print(f"{name}: {len(ids)} uploads read, {len(mine)} feature films (left out: " + ", ".join(f"{k} {n}" for k, n in why.items() if n) + ")")
    if len(films) < 50:
        # (the key over its day's quota, YouTube not answering: the list of last week stays)
        print(f"only {len(films)} films – the old list stays")
        return 1
    films, twins = merge_twins(films)
    print(f"the same film on two channels (or twice on one): {twins} left out")
    data = {"made": datetime.date.today().isoformat(), "films": films}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    with_year = sum(1 for r in films if r.get("y"))
    with_kind = sum(1 for r in films if r.get("g"))
    print(f"{len(films)} films · {with_year} with a year · {with_kind} with a kind · {units} API units")
    # a look at the titles (for whoever tunes clean_title): every 9th changed headline
    for name, raw, clean in samples[::9]:
        print(f"  [{name}] {raw[:110]!r} → {clean!r}")
    # (and how the channels word their descriptions – where a year could be read from)
    for name, d in descs:
        print(f"  [{name}] description: {d!r}")
    if tube:
        tube_pictures(tube)
        print(f"{units} API units in all")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "freefilms.json", sys.argv[2] if len(sys.argv) > 2 else None))

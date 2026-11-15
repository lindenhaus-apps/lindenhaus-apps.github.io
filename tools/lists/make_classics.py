#!/usr/bin/env python3
"""
🎞 "Classics without a ticket" – public-domain feature films from the Internet Archive
(archive.org), for the preview shelf beside the free films (Nathan, 14 Nov 2026).

Once a week (CI, .github/workflows/freefilms.yml) the Archive's "Feature Films" collection is read
through its public search and metadata interfaces (no key, no login), most watched first, and a
film is kept only when

  * its own metadata says it is free of copyright: a licence address that is the Public Domain Mark
    or CC0 (creativecommons.org/publicdomain/…, or the old "licenses/publicdomain"). Films with no
    licence line, and every Creative Commons licence with conditions (BY, SA, NC, ND), stay out –
    the Archive itself guarantees nothing about an item's rights (help.archive.org/help/rights);
  * it has a picture file players read (an MP4 the Archive made, "h.264"), 55 minutes to 4 hours;
  * it is not adult material, and not war or camp footage, propaganda, a newsreel or an
    instruction film (the collection holds those too; words in the title and the subject lines),
    not a double bill or a collection, and not on the short list of films that do not belong here;
  * its year is known and not after 1977 (a newer film marked "public domain" is an uploader's
    mistake), and the same film is taken once (its most watched copy).

⚠ "Public domain" on archive.org means: free in the USA, by the uploader's word. A film can be free
there and still protected elsewhere. 🇪🇺 Nathan's decision (14 Nov 2026): the whole list in the USA,
everywhere else only the films that are free in the EU too ("eu": true – data/Classics.kt). The EU
counts 70 years after the death of the last of four people: the principal director, the author of
the screenplay, the author of the dialogue and the composer of music made for the film; the term
ends at the end of that 70th year (a death in 1955: free from 1 January 2026). So a film is
"eu": true only when

  * Wikidata knows it for sure – by the IMDb number in the Archive's own metadata (P345), else by
    its exact English title, instance of film, and a release year (P577) within one year of ours,
    with exactly one such film;
  * its director (P57) and its screenwriter (P58) are known, and its composer (P86) too – a silent
    film (language zxx, or 1929 and before) may have none;
  * every one of them known has a death date (P570) in or before this year − 71.

Anything unsure is false: outside the USA such a film does not show. "who" lists the people with
their death years, for the curious. Wikidata is asked in batches (SPARQL, a polite pause between).

🇪🇺 The EU pool (Nathan, 14 Nov 2026 – two films outside the USA are no shelf): the most watched list
is mostly Hollywood of the 1930s–60s, whose makers lived long. So a second search looks where films
free in the EU are: the Archive's silent films (collection silent_films) and the older feature films
(up to 1950), and the silent years uploaded to the Archive's other collections – the same licence rule
(Public Domain Mark or CC0), the same filters – and only those
that pass the same Wikidata check join the list (a picture file players read, 40 minutes or more – a
feature by the old definition; 30 for a silent film, whose four or five reels the Archive's copy often
runs at sound speed – and a cover). A silent film's year may be two years off (its making, a later
release). They are
free everywhere, so the USA sees them too. The title is looked up by its labels and other names in
the languages of these films (English, German, French, Italian, Swedish, Danish). And Wikidata itself
is asked for the films it knows an Internet Archive item of (P724), up to 1950, whose director and
screenwriter it knows and whose makers all died long enough ago – a match as sure as the IMDb number:
Wikidata names the Archive's item itself. Each still goes through the same check and the same rules
for the item (licence, picture file, length, cover).

The list ships inside the app (app/src/main/assets/classics.json); the films play in the app's own
player straight from archive.org/download/<item>/<file>, the cover is the item's own picture
(archive.org/services/img/<item>). Nothing is copied to anywhere else.

Each film: i item · t title · y year · m minutes · f file · l language · n views in thousands ·
g kinds of film (the letters of tools/cream) · c "pd" or "cc0" · eu free in the EU too (true/false) ·
who its director, screenwriter and composer with their death years (when Wikidata knows the film).

Usage: python3 make_classics.py app/src/main/assets/classics.json
"""
import datetime
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "LindenhausPlayer-classics/1.0 (https://lindenhaus-apps.github.io)"
SEARCH = "https://archive.org/advancedsearch.php"
META = "https://archive.org/metadata/"
ROWS = 1000
PAGES = 6            # the 6000 most watched of the collection are looked at
KEEP = 400           # at most this many films ship
MIN_MIN, MAX_MIN = 55, 240
WIKIDATA = "https://query.wikidata.org/sparql"
WD_BATCH = 40        # films per question to Wikidata
WD_PAUSE = 2.0       # seconds between the questions
IMDB = re.compile(r"\btt\d{7,8}\b")
WD_TITLES = 20       # films per title question (each with up to four names in six languages)
LABEL_LANGS = ("en", "de", "fr", "it", "sv", "da")
EU_QUERIES = [
    "collection:(silent_films) AND mediatype:(movies)",
    "collection:(feature_films) AND mediatype:(movies) AND year:[1890 TO 1950]",
    # (the silent years uploaded anywhere else on the Archive – many features sit in the open collections)
    "mediatype:(movies) AND year:[1890 TO 1930] AND NOT collection:(silent_films) AND NOT collection:(feature_films)",
]
EU_PAGES = 5         # pages of 1000 per question, most watched first
EU_LOOK = 3500       # at most this many candidates go to Wikidata by their title
EU_KEEP = 250        # at most this many films join for the EU
EU_MIN_MIN = 40      # a feature film by the old definition (over 40 minutes)
EU_MIN_SILENT = 30   # a silent feature: four or five reels, often shown at sound speed in the Archive's copy (shorter)
ARTICLE = re.compile(r"(?i)^(the|a|an|der|die|das|le|la|les|il|el) (.+)$")
EU_MAX_YEAR = 1950

FREE = re.compile(r"creativecommons\.org/(publicdomain/(mark|zero)/|licenses/publicdomain)", re.I)
ADULT = re.compile(r"(?i)\b(adult|erotic|erotica|sexploitation|exploitation|nudity|nudist|nudie|nude|naked|sex|stag film|porn|xxx|burlesque|softcore|hentai|striptease)\b")
# not a feature film for an evening: war and camp footage, propaganda, newsreels, instruction films
# films that do not belong on a friendly shelf whatever their rights (curated by hand – add to it)
NOT_HERE = re.compile(r"(?i)\b(child bride|birth of a nation|triumph of the will|triumph des willens|jud s[uü]ß|der ewige jude|mom and dad)\b")
# no single film: double bills, collections, serial chapters, an uploader's notes
BUNDLE = re.compile(r"(?i)\b(double feature|triple feature|collection|compilation|marathon|festival|grindhouse experience|chapter \d+|episode \d+|part \d+ of|vol(ume)?\.? ?\d+|the three stooges)\b")
MAX_YEAR = 1977  # from 1978 on a US film is practically never free of copyright; a newer "public domain" mark is an uploader's mistake
NOT_A_FILM = re.compile(r"(?i)\b(concentration camps?|holocaust|nazi|propaganda|newsreel|atrocit|execution|war footage|training film|educational film|instructional|ephemeral|home movie|stock footage|trailer)\b")
GENRES = [
    ("c", r"comed|slapstick|satire"), ("d", r"drama"), ("r", r"romanc|romantic"), ("t", r"thriller|suspense|mystery|film noir|noir"),
    ("k", r"crime|gangster|detective|heist"), ("s", r"science fiction|sci-?fi"), ("y", r"fantasy|fairy ?tale"),
    ("h", r"horror|zombie|vampire|monster"), ("b", r"\baction|martial arts|kung fu|spy"), ("v", r"adventure|swashbuckler"),
    ("u", r"documentar"), ("w", r"\bwar\b|histor|biograph|biopic"), ("e", r"western"), ("q", r"musical"),
    ("f", r"family|children"), ("a", r"animat|cartoon"), ("x", r"christmas"),
]
GENRE_RES = [(k, re.compile(w, re.I)) for k, w in GENRES]
LANGS = {"english": "en", "eng": "en", "en": "en", "german": "de", "deutsch": "de", "ger": "de", "deu": "de", "de": "de", "french": "fr", "fre": "fr",
         "fra": "fr", "fr": "fr", "italian": "it", "ita": "it", "it": "it", "spanish": "es", "spa": "es", "es": "es", "russian": "ru", "rus": "ru",
         "japanese": "ja", "jpn": "ja", "silent": "zxx", "no linguistic content": "zxx"}


def get(url, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code} from archive.org", file=sys.stderr)
            if e.code not in (429, 500, 502, 503, 504):
                return None
        except Exception as e:  # noqa: BLE001
            print(f"  {type(e).__name__} from archive.org", file=sys.stderr)
        time.sleep(3 * (k + 1))
    return None


def one(v):
    return (v[0] if v else "") if isinstance(v, list) else (v or "")


def many(v):
    return [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])


def seconds(length):
    s = str(length or "").strip()
    if not s:
        return 0
    if ":" in s:
        n = 0
        for part in s.split(":"):
            try:
                n = n * 60 + float(part)
            except ValueError:
                return 0
        return int(n)
    try:
        return int(float(s))
    except ValueError:
        return 0


def clean_title(t):
    t = re.sub(r"\s+", " ", str(t)).strip()
    # an uploader's notes: "(complete & clearer)", "video quality upgrade", "- John Wayne"
    t = re.sub(r"(?i)\s*\((complete|clearer|upgrade|better|improved|new|hq|high quality|full)[^)]*\)", "", t)
    t = re.sub(r"(?i)\s+video quality upgrade\s*$", "", t)
    year = None
    m = re.search(r"\s*[\(\[]\s*((?:18[89]|19\d|20[0-2])\d)\s*[\)\]]\s*$", t)
    if m:
        year = int(m.group(1))
        t = t[:m.start()].strip()
    t = re.sub(r"(?i)\s*[-–:]\s*(full movie|public domain( movie| film)?|feature film|complete film)\s*$", "", t)
    t = re.sub(r"(?i)\s*\((full movie|public domain|restored|hd|remastered)[^)]*\)\s*$", "", t)
    # "Little Princess, The" → "The Little Princess"
    m = re.fullmatch(r"(.+), (The|A|An|Der|Die|Das|Le|La|Les|Il|El)", t)
    if m:
        t = m.group(2) + " " + m.group(1)
    # a headline all in capitals: as a title
    letters = [c for c in t if c.isalpha()]
    if len(letters) >= 6 and sum(c.isupper() for c in letters) > 0.85 * len(letters):
        t = t.title()
    return t.strip(" -–:"), year


def pick_file(files):
    """The MP4 the Archive made for players (h.264), else the uploader's own MP4 when it is not huge."""
    best = None
    for f in files or []:
        name = str(f.get("name") or "")
        fmt = str(f.get("format") or "").lower()
        if not name.lower().endswith(".mp4") or f.get("private") == "true":
            continue
        derived = f.get("source") == "derivative"
        size = int(f.get("size") or 0) if str(f.get("size") or "").isdigit() else 0
        if not derived and size > 2_500_000_000:
            continue
        rank = (0 if ("h.264" in fmt and derived) else 1 if "h.264" in fmt else 2 if "mpeg4" in fmt else 3, size or 10**12)
        secs = seconds(f.get("length"))
        if best is None or rank < best[0]:
            best = (rank, name, secs)
    return (best[1], best[2]) if best else (None, 0)


# ---------------------------------------------------------------- 🇪🇺 free in the EU too? (Wikidata)

def sparql(query):
    """One question to Wikidata's SPARQL service: the rows, or None when it would not answer."""
    body = urllib.parse.urlencode({"query": query, "format": "json"}).encode()
    for k in range(3):
        try:
            req = urllib.request.Request(WIKIDATA, data=body, headers={
                "User-Agent": UA, "Accept": "application/sparql-results+json", "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)["results"]["bindings"]
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code} from Wikidata", file=sys.stderr)
            if e.code == 429:
                time.sleep(min(120, int(e.headers.get("Retry-After") or 30)))
                continue
            if e.code not in (500, 502, 503, 504):
                return None
        except Exception as e:  # noqa: BLE001
            print(f"  {type(e).__name__} from Wikidata", file=sys.stderr)
        time.sleep(5 * (k + 1))
    return None


def lit(s):
    """A string as a SPARQL literal."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def year_of(b, key):
    v = (b.get(key) or {}).get("value", "")
    m = re.match(r"^(\d{4})-", v)
    return int(m.group(1)) if m else None


def imdb_of(md):
    """The film's IMDb number from the Archive's own metadata – only when it names exactly one."""
    found = set()
    for key in ("imdb", "external-identifier", "external_identifier", "description", "notes", "source"):
        for v in many(md.get(key)):
            if key in ("description", "notes", "source") and "imdb.com/title/" not in v:
                continue
            found.update(IMDB.findall(v))
    return found.pop() if len(found) == 1 else None


def wikidata_match(films):
    """film row → Wikidata item, only for a sure match (the IMDb number, else the title and year)."""
    # (an item Wikidata itself names – its Internet Archive ID, P724 – needs no search)
    qid = {r["i"]: r["_qid"] for r in films if r.get("_qid")}
    by_imdb = {r["_imdb"]: r for r in films if r.get("_imdb") and r["i"] not in qid}
    ids = list(by_imdb)
    for k in range(0, len(ids), WD_BATCH):
        part = ids[k:k + WD_BATCH]
        rows = sparql("SELECT ?film ?imdb WHERE { VALUES ?imdb { " + " ".join(lit(i) for i in part) + " } ?film wdt:P345 ?imdb . }")
        time.sleep(WD_PAUSE)
        hits = {}
        for b in rows or []:
            hits.setdefault(b["imdb"]["value"], set()).add(b["film"]["value"].rsplit("/", 1)[-1])
        for i, q in hits.items():
            if len(q) == 1:
                qid[by_imdb[i]["i"]] = q.pop()
    rest = [r for r in films if r["i"] not in qid and r.get("y")]

    def names(t):
        """The title, and for "Bronenosets Potyomkin (Battleship Potemkin)" each of its two names; with and without
        "The" ("Phantom of the Opera" is labelled "The Phantom of the Opera")."""
        m = re.fullmatch(r"(.+?)\s*\((.+)\)", t)
        out = [t] + ([m.group(1).strip(), m.group(2).strip()] if m else [])
        a = ARTICLE.match(t)
        out.append(a.group(2) if a else "The " + t)
        return list(dict.fromkeys(out))
    for k in range(0, len(rest), WD_TITLES):
        part = rest[k:k + WD_TITLES]
        titles = sorted({n for r in part for n in names(r["t"])})
        # (its label or another name, in the languages of these films; one film per name and year)
        def ask(names_):
            r_ = sparql("SELECT ?t ?film (MIN(?d) AS ?date) WHERE { VALUES ?t { " + " ".join(lit(t) + "@" + l for t in names_ for l in LABEL_LANGS) + " } "
                        "?film rdfs:label|skos:altLabel ?t . ?film wdt:P31/wdt:P279* wd:Q11424 ; wdt:P577 ?d . } GROUP BY ?t ?film")
            time.sleep(WD_PAUSE)
            return r_
        rows = ask(titles)
        # (Wikidata gave up on it – too long: the same question in two halves)
        if rows is None and len(titles) > 1:
            half = len(titles) // 2
            rows = (ask(titles[:half]) or []) + (ask(titles[half:]) or [])
        cands = {}
        for b in rows or []:
            cands.setdefault(b["t"]["value"], []).append((b["film"]["value"].rsplit("/", 1)[-1], year_of(b, "date")))
        for r in part:
            # (a silent film's year is often its making or a later release: two years either way)
            tol = 2 if r["y"] <= 1929 else 1
            near = {q for n in names(r["t"]) for q, y in cands.get(n, []) if y and abs(y - r["y"]) <= tol}
            if len(near) == 1:
                qid[r["i"]] = near.pop()
    return qid


def wikidata_people(qids):
    """item → {role: [(name, death year or None)]} for director P57, screenwriter P58, composer P86."""
    out = {}
    items = sorted(set(qids))
    for k in range(0, len(items), WD_BATCH):
        part = items[k:k + WD_BATCH]
        rows = sparql("SELECT ?film ?role ?p ?name (MAX(?d) AS ?death) WHERE { VALUES ?film { " + " ".join("wd:" + q for q in part) + " } "
                      "VALUES ?role { wdt:P57 wdt:P58 wdt:P86 } ?film ?role ?p . OPTIONAL { ?p wdt:P570 ?d . } "
                      "OPTIONAL { ?p rdfs:label ?name . FILTER(LANG(?name) = \"en\") } } GROUP BY ?film ?role ?p ?name")
        time.sleep(WD_PAUSE)
        if rows is None:
            continue
        for q in part:
            out.setdefault(q, {"P57": {}, "P58": {}, "P86": {}})
        for b in rows:
            q = b["film"]["value"].rsplit("/", 1)[-1]
            role = b["role"]["value"].rsplit("/", 1)[-1]
            who = b["p"]["value"].rsplit("/", 1)[-1]
            name = (b.get("name") or {}).get("value") or who
            # (an "unknown value" death is no date: unsure)
            out[q][role][who] = (name, year_of(b, "death"))
    return out


def mark_eu(films):
    """Sets "eu" (and "who") on every film; returns (free in the EU, matched, free if the composer were not asked)."""
    last = datetime.date.today().year - 71   # in 2026: died in 1955 or before
    for r in films:
        r["eu"] = False
    qid = wikidata_match(films)
    people = wikidata_people(qid.values()) if qid else {}
    free = loose = 0
    for r in films:
        q = qid.get(r["i"])
        if q:
            r["_q"] = q
        roles = people.get(q) if q else None
        if not roles:
            continue
        directors, writers, composers = (list(roles[k].values()) for k in ("P57", "P58", "P86"))
        everyone = {who: v for role in roles.values() for who, v in role.items()}
        silent = r.get("l") == "zxx" or r.get("y", 9999) <= 1929
        all_gone = bool(everyone) and all(d is not None and d <= last for _, d in everyone.values())
        if directors and writers and all_gone:
            loose += 1
            if composers or silent:
                r["eu"] = True
                free += 1
        if everyone:
            r["who"] = "; ".join(f"{n} †{d}" if d else f"{n} †?" for n, d in list(everyone.values())[:6])
    return free, len(qid), loose


def search(query, pages, extra=()):
    """The Archive's search, most watched first: every item's few fields, page by page."""
    docs = []
    for page in range(1, pages + 1):
        q = urllib.parse.urlencode(
            [("q", query), ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "year"),
             ("fl[]", "downloads"), ("fl[]", "licenseurl"), ("fl[]", "language"), ("fl[]", "subject"), ("fl[]", "collection")]
            + [("fl[]", f) for f in extra] + [("sort[]", "downloads desc"), ("rows", str(ROWS)), ("page", str(page)), ("output", "json")])
        ans = get(SEARCH + "?" + q)
        got = ((ans or {}).get("response") or {}).get("docs") or []
        if not got:
            break
        docs += got
        time.sleep(1)
    return docs


def has_cover(files):
    """The item has a picture of its own (the Archive's tile, a thumbnail or an image file)."""
    for f in files or []:
        name = str(f.get("name") or "").lower()
        fmt = str(f.get("format") or "").lower()
        if "thumb" in fmt or "tile" in fmt or fmt in ("jpeg", "png", "gif") or name.endswith((".jpg", ".jpeg", ".png")):
            return True
    return False


def wikidata_archive_films(last):
    """Films Wikidata knows an Internet Archive item of (P724), up to 1950, with a director and a
    screenwriter, none of whose makers died after [last] or without a date: Archive item → (item, year, title)."""
    rows = sparql(
        "SELECT ?ia ?film (MIN(?d) AS ?date) (SAMPLE(?n) AS ?name) WHERE { "
        "?film wdt:P724 ?ia ; wdt:P57 ?dir ; wdt:P58 ?wr ; wdt:P577 ?d . "
        "FILTER(YEAR(?d) <= " + str(EU_MAX_YEAR) + ") "
        "FILTER NOT EXISTS { ?film wdt:P57|wdt:P58|wdt:P86 ?p . FILTER NOT EXISTS { ?p wdt:P570 ?x . FILTER(isLiteral(?x)) } } "
        "FILTER NOT EXISTS { ?film wdt:P57|wdt:P58|wdt:P86 ?q . ?q wdt:P570 ?y . FILTER(!isLiteral(?y) || YEAR(?y) > " + str(last) + ") } "
        "OPTIONAL { ?film rdfs:label ?n . FILTER(LANG(?n) = \"en\") } "
        "} GROUP BY ?ia ?film")
    time.sleep(WD_PAUSE)
    out = {}
    for b in rows or []:
        ia = b["ia"]["value"].strip()
        if re.fullmatch(r"[A-Za-z0-9._-]{3,100}", ia):
            out.setdefault(ia, (b["film"]["value"].rsplit("/", 1)[-1], year_of(b, "date"), (b.get("name") or {}).get("value", "")))
    return out


def eu_pool(main_rows, seen):
    """🇪🇺 Silent and older films from the Archive that are free in the EU too (see the top)."""
    docs, idents = [], {r["i"] for r in main_rows}
    # (Wikidata's own list of films with an Archive item: the surest matches)
    known = wikidata_archive_films(datetime.date.today().year - 71)
    print(f"🇪🇺 Wikidata names {len(known)} Archive items of films up to {EU_MAX_YEAR} whose makers all died long enough ago")
    for q in EU_QUERIES:
        docs += search(q, EU_PAGES, extra=("runtime",))
    docs.sort(key=lambda d: -int(d.get("downloads") or 0))
    cands, keys = [], set(seen)
    for d in docs:
        ident = str(d.get("identifier") or "")
        if ident in idents or not re.fullmatch(r"[A-Za-z0-9._-]{3,100}", ident) or not FREE.search(one(d.get("licenseurl")) or ""):
            continue
        idents.add(ident)
        subjects = " ; ".join(many(d.get("subject")))
        title, year = clean_title(one(d.get("title")))
        if ADULT.search(subjects) or ADULT.search(title) or NOT_A_FILM.search(subjects) or NOT_A_FILM.search(title) \
                or NOT_HERE.search(title) or BUNDLE.search(str(one(d.get("title")))):
            continue
        if not year:
            ys = re.search(r"\b(18[89]\d|19\d\d)\b", str(one(d.get("year")) or ""))
            year = int(ys.group(1)) if ys else None
        if not year or year > EU_MAX_YEAR:
            continue
        # (a runtime the search already knows: a short is no feature)
        rt = seconds(one(d.get("runtime")))
        if 0 < rt < EU_MIN_SILENT * 60:
            continue
        key = re.sub(r"[\W_]+", "", re.sub(r"\(.*?\)", "", title).lower())
        if not key or key in keys:
            continue
        keys.add(key)
        row = {"i": ident, "t": title, "y": year, "_d": d}
        lang = LANGS.get(str(one(d.get("language"))).strip().lower(), "")
        if lang:
            row["l"] = lang
        cands.append(row)
        if len(cands) >= EU_LOOK:
            break
    # (Wikidata's own: by its item number; the title only for the duplicate check)
    for ia, (q, y, name) in known.items():
        if ia in idents or not y:
            continue
        key = re.sub(r"[\W_]+", "", re.sub(r"\(.*?\)", "", name).lower()) if name else ""
        if key and key in keys:
            continue
        idents.add(ia)
        if key:
            keys.add(key)
        cands.append({"i": ia, "t": name or ia, "y": y, "_qid": q, "_d": {}, "_wd": True})
    print(f"🇪🇺 the EU pool: {len(docs)} silent and older items looked at, {len(cands)} candidates to Wikidata")
    free, matched, _ = mark_eu(cands)
    print(f"🇪🇺 the EU pool: Wikidata knew {matched} for sure, {free} free in the EU too")
    out, why = [], {"no answer": 0, "dark or no free licence": 0, "no mp4": 0, "length": 0, "no cover": 0, "the same film twice": 0}
    taken = {r.get("_q") for r in main_rows if r.get("_q")}
    copies = []

    def take(r):
        """The item's own check (as for every other): free licence, picture file, length, cover – its row or None."""
        meta = get(META + urllib.parse.quote(r["i"]))
        time.sleep(0.25)
        if not meta or not meta.get("files"):
            why["no answer"] += 1
            return None
        md = meta.get("metadata") or {}
        if meta.get("is_dark") or md.get("access-restricted-item") in ("true", True) or "noindex" in many(md.get("noindex")) \
                or not FREE.search(one(md.get("licenseurl"))) or ADULT.search(" ; ".join(many(md.get("subject")))):
            why["dark or no free licence"] += 1
            # (a film Wikidata named, but this copy carries no free licence: another copy of it is looked for)
            if r.get("_wd"):
                copies.append(r)
            return None
        name, secs = pick_file(meta.get("files"))
        if not name:
            why["no mp4"] += 1
            return None
        if not secs:
            secs = seconds(one(md.get("runtime")))
            if not secs:
                m = re.search(r"(?i)(?:(\d+)\s*h\w*\s*)?(\d+)\s*min", str(one(md.get("runtime"))))
                if m:
                    secs = (int(m.group(1) or 0) * 60 + int(m.group(2))) * 60
        mins = round(secs / 60)
        if not ((EU_MIN_SILENT if r["y"] <= 1929 else EU_MIN_MIN) <= mins <= MAX_MIN):
            why["length"] += 1
            return None
        if not has_cover(meta.get("files")):
            why["no cover"] += 1
            return None
        d = r.get("_d") or {}
        title = r["t"]
        if r.get("_wd") or r.get("_copy") or not d:
            # (named by Wikidata, or another copy: the Archive's own title, the same filters as every other item)
            t2, _ = clean_title(one(md.get("title")) or title)
            subjects = " ; ".join(many(md.get("subject")))
            if ADULT.search(t2) or NOT_A_FILM.search(subjects) or NOT_A_FILM.search(t2) or NOT_HERE.search(t2) or BUNDLE.search(str(one(md.get("title")))):
                why["dark or no free licence"] += 1
                return None
            title = t2 or title
            d = {"subject": md.get("subject"), "downloads": d.get("downloads") or md.get("downloads") or 0}
        row = {"i": r["i"], "t": title, "m": mins, "f": name, "c": "cc0" if "zero" in one(md.get("licenseurl")) else "pd", "y": r["y"]}
        lang = r.get("l") or LANGS.get(str(one(md.get("language"))).strip().lower(), "")
        if lang:
            row["l"] = lang
        views = int(d.get("downloads") or 0) if str(d.get("downloads") or "0").isdigit() else 0
        if views >= 1000:
            row["n"] = views // 1000
        g = "".join(k for k, rx in GENRE_RES if rx.search(" ; ".join(many(d.get("subject")))))
        if g:
            row["g"] = g
        row["eu"] = True
        if r.get("who"):
            row["who"] = r["who"]
        return row

    for r in [r for r in cands if r["eu"]]:
        if len(out) >= EU_KEEP:
            break
        # (one copy per film: two Archive items of the same Wikidata film – the most watched first)
        if r.get("_q") in taken:
            why["the same film twice"] += 1
            continue
        row = take(r)
        if row:
            taken.add(r.get("_q"))
            out.append(row)
    # 🔁 films free in the EU whose Wikidata-named copy has no free licence: another copy on the Archive that has
    # one – the same title (or a name Wikidata knows), its year within two, Public Domain Mark or CC0
    found = 0
    for r in copies:
        if len(out) >= EU_KEEP:
            break
        if r.get("_q") in taken or not r.get("t") or r["t"] == r["i"]:
            continue
        want = re.sub(r"[\W_]+", "", r["t"].lower())
        q = 'title:("' + r["t"].replace('"', " ") + '") AND mediatype:(movies)'
        for d in search(q, 1):
            ident = str(d.get("identifier") or "")
            if ident in idents or not re.fullmatch(r"[A-Za-z0-9._-]{3,100}", ident) or not FREE.search(one(d.get("licenseurl")) or ""):
                continue
            t, y = clean_title(one(d.get("title")))
            if not y:
                ys = re.search(r"\b(18[89]\d|19\d\d)\b", str(one(d.get("year")) or ""))
                y = int(ys.group(1)) if ys else None
            if re.sub(r"[\W_]+", "", t.lower()) != want or not y or abs(y - r["y"]) > 2:
                continue
            idents.add(ident)
            row = take({"i": ident, "t": t, "y": r["y"], "_d": d, "_copy": True, "who": r.get("who"), "l": LANGS.get(str(one(d.get("language"))).strip().lower(), "")})
            if row:
                taken.add(r.get("_q"))
                out.append(row)
                found += 1
                break
    print(f"🇪🇺 the EU pool: {found} of {len(copies)} films without a free copy found another one with a free licence")
    print(f"🇪🇺 the EU pool: {len(out)} films join (left out: " + ", ".join(f"{k} {n}" for k, n in why.items() if n) + ")")
    return out


def main(out):
    found, seen_licence = [], {}
    for d in search("collection:(feature_films) AND mediatype:(movies)", PAGES):
        lic = one(d.get("licenseurl"))
        kind = "none" if not lic else ("free" if FREE.search(lic) else re.sub(r"^https?://(www\.)?", "", lic)[:44])
        seen_licence[kind] = seen_licence.get(kind, 0) + 1
        if FREE.search(lic or ""):
            found.append(d)
    print("licence lines among the most watched:", ", ".join(f"{k}: {n}" for k, n in sorted(seen_licence.items(), key=lambda kv: -kv[1])[:8]))
    print(f"{len(found)} items say public domain or CC0")
    films, why, seen = [], {"adult": 0, "not a feature film": 0, "twice": 0, "no year or too new": 0, "no mp4": 0, "length": 0, "no answer": 0, "dark": 0}, set()
    for d in found:
        if len(films) >= KEEP:
            break
        ident = str(d.get("identifier") or "")
        if not re.fullmatch(r"[A-Za-z0-9._-]{3,100}", ident):
            continue
        subjects = " ; ".join(many(d.get("subject")))
        title, year = clean_title(one(d.get("title")))
        if ADULT.search(subjects) or ADULT.search(title):
            why["adult"] += 1
            continue
        if NOT_A_FILM.search(subjects) or NOT_A_FILM.search(title) or NOT_HERE.search(title) or BUNDLE.search(str(one(d.get("title")))):
            why["not a feature film"] += 1
            continue
        key = re.sub(r"[\W_]+", "", re.sub(r"\(.*?\)", "", title).lower())
        if not key or key in seen:
            why["twice"] += 1
            continue
        meta = get(META + urllib.parse.quote(ident))
        time.sleep(0.25)
        if not meta or not meta.get("files"):
            why["no answer"] += 1
            continue
        md = meta.get("metadata") or {}
        # (taken down or locked since the search: "is_dark", or lending/restricted collections)
        if meta.get("is_dark") or md.get("access-restricted-item") in ("true", True) or "noindex" in many(md.get("noindex")):
            why["dark"] += 1
            continue
        if not FREE.search(one(md.get("licenseurl"))):
            continue
        if ADULT.search(" ; ".join(many(md.get("subject")))):
            why["adult"] += 1
            continue
        name, secs = pick_file(meta.get("files"))
        if not name:
            why["no mp4"] += 1
            continue
        if not secs:
            secs = seconds(one(md.get("runtime")))
            # ("90 min", "1 hr 30 min")
            if not secs:
                m = re.search(r"(?i)(?:(\d+)\s*h\w*\s*)?(\d+)\s*min", str(one(md.get("runtime"))))
                if m:
                    secs = (int(m.group(1) or 0) * 60 + int(m.group(2))) * 60
        mins = round(secs / 60)
        if not (MIN_MIN <= mins <= MAX_MIN):
            why["length"] += 1
            continue
        y = year
        if not y:
            ys = re.search(r"\b(18[89]\d|19\d\d|20[0-2]\d)\b", str(one(md.get("year")) or one(md.get("date")) or one(d.get("year")) or ""))
            y = int(ys.group(1)) if ys else None
        # (a film without a year, or from 1978 on: its "public domain" mark cannot be trusted)
        if not y or y > MAX_YEAR:
            why["no year or too new"] += 1
            continue
        seen.add(key)
        lang = LANGS.get(str(one(md.get("language")) or one(d.get("language"))).strip().lower(), "")
        row = {"i": ident, "t": title, "m": mins, "f": name, "c": "cc0" if "zero" in one(md.get("licenseurl")) else "pd"}
        imdb = imdb_of(md)
        if imdb:
            row["_imdb"] = imdb
        if y:
            row["y"] = y
        if lang:
            row["l"] = lang
        views = int(d.get("downloads") or 0)
        if views >= 1000:
            row["n"] = views // 1000
        g = "".join(k for k, rx in GENRE_RES if rx.search(subjects))
        if g:
            row["g"] = g
        films.append(row)
    print(f"{len(films)} classics (left out: " + ", ".join(f"{k} {n}" for k, n in why.items() if n) + ")")
    for r in films[:25]:
        print(f"  {r.get('y', '????')} {r['t'][:60]} · {r['m']} min · {r.get('l', '?')} · {r.get('n', 0)}k · {r.get('g', '')}")
    if len(films) < 20:
        print("too few – the old list stays")
        return 1
    # 🇪🇺 which of them are free in the EU too (outside the USA only these show)
    try:
        free, matched, loose = mark_eu(films)
    except Exception as e:  # noqa: BLE001
        print(f"Wikidata: {type(e).__name__} – no film counts as free in the EU this week", file=sys.stderr)
        free, matched, loose = 0, 0, 0
        for r in films:
            r["eu"] = False
    for r in films:
        r.pop("_imdb", None)
    print(f"🇪🇺 free in the EU too: {free} of {len(films)} (Wikidata knew {matched} for sure; "
          f"{loose} if a sound film's unknown composer were let through)")
    try:
        extra = eu_pool(films, seen)
    except Exception as e:  # noqa: BLE001
        print(f"the EU pool: {type(e).__name__} – none this week", file=sys.stderr)
        extra = []
    films += extra
    for r in films:
        r.pop("_q", None)
    print(f"🇪🇺 outside the USA {sum(1 for r in films if r['eu'])} films show; the USA shows all {len(films)}")
    for r in [r for r in films if r["eu"]][:12]:
        print(f"  EU {r.get('y')} {r['t'][:50]} · {r.get('who', '')[:110]}")
    data = {"made": datetime.date.today().isoformat(), "source": "Internet Archive (archive.org), Feature Films – items marked public domain or CC0", "films": films}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "classics.json"))

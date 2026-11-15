"""
Cream list: well-known films and series from Wikidata (CC0), for ratings and the Box shelves.

Runs in GitHub Actions once a week (workflow "Refresh cream list") and writes
app/src/main/assets/cream.bin, which ships inside the app. No own server, no API key.

Per title: Wikidata number, year, sitelinks (= in how many Wikipedia languages it has an article:
how well-known it is worldwide), IMDb and TMDb ids, English and German title, Rotten Tomatoes and
Metacritic scores, box office (USD), Oscars, flags (animated, family, christmas and the genres,
see GENRE_WORDS) and the series
it belongs to. Usage: python3 make_cream.py <out.json.gz>
"""
import gzip, json, re, sys, time, urllib.parse, urllib.request, datetime

ENDPOINT = "https://query.wikidata.org/sparql"
UA = "LindenhausPlayer-CreamList/1.0 (https://lindenhaus-apps.github.io; build script)"
MIN_SL = 18          # films known in at least this many Wikipedia languages
MIN_SL_SERIES = 25

FILM_TYPES = "wd:Q11424 wd:Q24869 wd:Q29168811 wd:Q202866 wd:Q506240"
SERIES_TYPES = "wd:Q5398426 wd:Q581714 wd:Q1259759"

def run(q, tries=5):
    data = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
    time.sleep(3)   # be gentle with the public query service
    for i in range(tries):
        try:
            req = urllib.request.Request(ENDPOINT, data=data, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)["results"]["bindings"]
        except Exception as e:
            print("  query failed (%s), retry %d" % (e, i + 1), flush=True)
            time.sleep(20 * (i + 1))
    return []

def qid(b, k="item"):
    v = b.get(k, {}).get("value", "")
    m = re.search(r"Q(\d+)$", v)
    return int(m.group(1)) if m else None

def val(b, k):
    return b.get(k, {}).get("value")

# Genre letters (lower case; a f x h y m were there before and keep their meaning):
# c comedy · d drama · r romance · t thriller/mystery · k crime · s science fiction · y fantasy
# h horror · b action · v adventure · u documentary · w war/history · e western · q music
# f family · a animation · o sport · x christmas · l reality/talk
GENRE_WORDS = [
    ("c", r"comed|sitcom|parody|satir|slapstick|mockumentary|sketch"),
    ("d", r"drama|melodrama|soap opera|tragedy"),
    ("r", r"\bromanc|\bromantic"),
    ("t", r"thriller|suspense|mystery|neo-noir|film noir|whodunit"),
    ("k", r"crime|heist|gangster|detective|police|legal|mafia|procedural|caper|courtroom"),
    ("s", r"science fiction|sci-fi|cyberpunk|space opera|dystopi|post-apocalyptic|time travel|alien invasion|tech noir"),
    ("y", r"fantasy|sword and sorcery|fairy tale|supernatural|magic"),
    ("h", r"horror|slasher|zombie|vampire|splatter|ghost|monster"),
    ("b", r"action|martial arts|superhero|spy|disaster|kung fu|wuxia|swashbuckler"),
    ("v", r"adventure"),
    ("u", r"documentar|docudrama|nature"),
    ("w", r"\bwar\b|historical|history|biographical|biopic|period drama|epic film|sword-and-sandal"),
    ("e", r"western"),
    ("q", r"musical|music|dance|concert"),
    ("f", r"family|children"),
    ("a", r"animat|anime|cartoon|stop-motion"),
    ("o", r"\bsport"),
    ("x", r"christmas"),
    ("l", r"reality|talk show|game show|variety|talent show|cooking"),
]
GENRE_RES = [(k, re.compile(w, re.I)) for k, w in GENRE_WORDS]

def genre_letters(label):
    return "".join(k for k, rx in GENRE_RES if rx.search(label))

def base(types, min_sl):
    return f"VALUES ?type {{ {types} }} ?item wdt:P31 ?type ; wikibase:sitelinks ?sl . FILTER(?sl >= {min_sl})"

def collect(types, min_sl, label):
    items = {}
    print(f"{label}: base", flush=True)
    for b in run(f"""SELECT ?item (MAX(?sl) AS ?s) (MIN(YEAR(?d)) AS ?y) (SAMPLE(?imdb) AS ?i) (SAMPLE(?tmdb) AS ?t) WHERE {{
        {base(types, min_sl)}
        OPTIONAL {{ ?item wdt:{'P577' if label == 'films' else 'P580'} ?d }} OPTIONAL {{ ?item wdt:P345 ?imdb }} OPTIONAL {{ ?item wdt:{'P4947' if label == 'films' else 'P4983'} ?tmdb }}
      }} GROUP BY ?item"""):
        q = qid(b)
        if q is None: continue
        items[q] = dict(sl=int(float(val(b, "s") or 0)), y=int(float(val(b, "y"))) if val(b, "y") else None,
                        imdb=val(b, "i"), tmdb=val(b, "t"))
    print(f"  {len(items)} titles", flush=True)
    for lang in ("en", "de"):
        print(f"{label}: labels {lang}", flush=True)
        for b in run(f"""SELECT ?item ?l WHERE {{ {base(types, min_sl)} ?item rdfs:label ?l . FILTER(LANG(?l) = "{lang}") }}"""):
            q = qid(b)
            if q in items: items[q][lang] = val(b, "l")
    print(f"{label}: review scores", flush=True)
    for b in run(f"""SELECT ?item ?score ?by ?method WHERE {{ {base(types, min_sl)}
        ?item p:P444 ?st . ?st ps:P444 ?score ; pq:P447 ?by . VALUES ?by {{ wd:Q105584 wd:Q150248 }}
        OPTIONAL {{ ?st pq:P459 ?method }} }}"""):
        q = qid(b)
        if q not in items: continue
        s, by, method = val(b, "score") or "", qid(b, "by"), qid(b, "method")
        if by == 105584:
            m = re.match(r"\s*(\d{1,3})\s*%", s)
            # Tomatometer (critics) wins over the audience score
            if m and (method in (None, 108403393) or "rt" not in items[q]):
                items[q]["rt"] = int(m.group(1))
        elif by == 150248:
            m = re.match(r"\s*(\d{1,3})\s*/\s*100", s)
            if m: items[q]["mc"] = int(m.group(1))
    if label == "films":
        print("films: box office", flush=True)
        for b in run(f"""SELECT ?item (MAX(?a) AS ?box) WHERE {{ {base(types, min_sl)}
            ?item p:P2142 ?st . ?st psv:P2142 ?v . ?v wikibase:quantityAmount ?a ; wikibase:quantityUnit wd:Q4917 }} GROUP BY ?item"""):
            q = qid(b)
            if q in items and val(b, "box"): items[q]["box"] = int(float(val(b, "box")) / 1_000_000)
        print("films: oscars", flush=True)
        for b in run(f"""SELECT ?item (COUNT(DISTINCT ?aw) AS ?n) WHERE {{ {base(types, min_sl)}
            ?item wdt:P166 ?aw . ?aw wdt:P31 wd:Q19020 }} GROUP BY ?item"""):
            q = qid(b)
            if q in items: items[q]["osc"] = int(val(b, "n") or 0)
    print(f"{label}: genres", flush=True)
    flags = {"Q202866": "a", "Q29168811": "a", "Q1361932": "f", "Q1762165": "x", "Q200092": "h", "Q157394": "y", "Q1342372": "m"}
    for b in run(f"""SELECT ?item ?g WHERE {{ {base(types, min_sl)}
        {{ ?item wdt:P136 ?g }} UNION {{ ?item wdt:P31 ?g }} VALUES ?g {{ {' '.join('wd:' + k for k in flags)} }} }}"""):
        q = qid(b)
        g = (val(b, "g") or "").rsplit("/", 1)[-1]
        if q in items and g in flags:
            items[q]["fl"] = "".join(sorted(set(items[q].get("fl", "") + flags[g])))
    # Genres by their English name (Wikidata P136), as letters next to the flags above, so moods
    # ("Purr laughs", "Wet whiskers" …) find films even where the provider's lists are named after
    # platforms ("Netflix", "4K") instead of genres. The app reads the letters (Cream.Entry.genres).
    print(f"{label}: genre names", flush=True)
    for b in run(f"""SELECT ?item ?gl WHERE {{ {base(types, min_sl)}
        ?item wdt:P136 ?g . ?g rdfs:label ?gl . FILTER(LANG(?gl) = "en") }}"""):
        q = qid(b)
        if q not in items: continue
        letters = genre_letters(val(b, "gl") or "")
        if letters:
            items[q]["fl"] = "".join(sorted(set(items[q].get("fl", "") + letters)))
    # free posters: the poster file on Wikimedia Commons (only freely licensed files live there –
    # mostly old films and some studios' own releases); the app shows them as covers without a provider
    print(f"{label}: posters", flush=True)
    for b in run(f"""SELECT ?item (SAMPLE(?p) AS ?poster) WHERE {{ {base(types, min_sl)} ?item wdt:P3383 ?p . }} GROUP BY ?item"""):
        q, p = qid(b), val(b, "poster")
        if q in items and p: items[q]["poster"] = urllib.parse.unquote(p.rsplit("/", 1)[-1])
    print(f"{label}: series", flush=True)
    ser_of = {}
    for b in run(f"""SELECT ?item ?ser WHERE {{ {base(types, min_sl)} ?item wdt:P179 ?ser . }}"""):
        q, sq = qid(b), qid(b, "ser")
        if q in items and sq: ser_of[q] = sq
    ids = sorted(set(ser_of.values()))
    names = {}
    for i in range(0, len(ids), 400):
        chunk = " ".join("wd:Q%d" % x for x in ids[i:i + 400])
        for b in run(f"""SELECT ?ser ?l WHERE {{ VALUES ?ser {{ {chunk} }} ?ser rdfs:label ?l . FILTER(LANG(?l) = "en") }}"""):
            names[qid(b, "ser")] = val(b, "l")
    for q, sq in ser_of.items():
        if sq in names: items[q]["ser"] = names[sq]
    return items

def pack(items):
    out = []
    for q, d in sorted(items.items(), key=lambda kv: -kv[1]["sl"]):
        if not d.get("en") and not d.get("de"): continue
        imdb = d.get("imdb")
        out.append([q, d.get("y"), d["sl"], int(imdb[2:]) if imdb and imdb.startswith("tt") and imdb[2:].isdigit() else None,
                    int(d["tmdb"]) if d.get("tmdb", "") and str(d.get("tmdb")).isdigit() else None,
                    d.get("en"), d.get("de") if d.get("de") != d.get("en") else None,
                    d.get("rt"), d.get("mc"), d.get("box"), d.get("osc"), d.get("fl"), d.get("ser"), d.get("poster")])
    return out

def main():
    films = collect(FILM_TYPES, MIN_SL, "films")
    series = collect(SERIES_TYPES, MIN_SL_SERIES, "series")
    doc = {"v": 1, "made": datetime.date.today().isoformat(), "source": "Wikidata (CC0)",
           "fields": ["qid", "year", "sitelinks", "imdb", "tmdb", "en", "de", "rt", "mc", "box_musd", "oscars", "flags", "series", "poster"],
           "films": pack(films), "series": pack(series)}
    for k in ("films", "series"):
        rows = doc[k]
        def share(i): return sum(1 for r in rows if r[i] is not None) * 100 // max(1, len(rows))
        print(f"{k}: {len(rows)} titles · year {share(1)}% · imdb {share(3)}% · tmdb {share(4)}% · de {share(6)}% · rt {share(7)}% · mc {share(8)}% · box {share(9)}% · oscars {share(10)}% · flags {share(11)}% · series {share(12)}% · posters {share(13)}%")
    if len(doc["films"]) < 2000:
        print("too few films, keeping the old list"); sys.exit(1)
    raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()
    # (mtime=0: the same list gives the same bytes – the shelf then sends nothing new)
    with gzip.GzipFile(sys.argv[1], "wb", compresslevel=9, mtime=0) as f: f.write(raw)
    print(f"written {sys.argv[1]}: {len(raw)//1024} KB raw")

if __name__ == "__main__":
    main()

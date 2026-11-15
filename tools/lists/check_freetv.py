#!/usr/bin/env python3
"""
📺 Free TV that works – the weekly check of every stream in app/src/main/assets/freetv.json
(Nathan, 14 Nov 2026: "the free tv channels hardly work").

For each channel: its playlist is asked for the way a player does it (the master playlist, one of
its qualities, the first piece of picture), with the app's own name and – if that is refused – a
browser's. What comes back decides:

  ok      a piece of the picture came
  geo     the broadcaster answers "not from this country" (401/403/451) – the check runs on a server
          in the USA, so German, Austrian and British channels may well say so; such a channel stays,
          the app itself looks from the user's own network
  unsure  the channel's address answers, but its qualities or pieces do not (or the channel only
          sends to its own country): it cannot be told from a server abroad – the channel stays
  dead    the channel's own address is gone: no such host, "not found", no answer, no playlist

A channel that is not ok is looked up in the list it was curated from (github.com/Free-TV/IPTV,
its `source`): when the broadcaster's address has changed there and the new one answers, the new
one is taken. A plain http:// address is tried as https://. A channel that is dead in two weekly
checks in a row is taken out; after the first it carries "failed": the day it was first found gone.

📺↗ Public broadcasters (Nathan, 14 Nov 2026): a channel with "live" – the broadcaster's own live page
(and "app", the services.json id of its app) – is never played inside the app (LG München I, 28 May
2025, and OLG Köln against Joyn's embedding of ARD/ZDF). Its stream ("url") is still asked, but only
for the record: such a channel is never taken out for a dead stream. Its live page is asked instead
(as a browser, like a person opens it): its title is printed, and a page that is gone carries
"liveFailed" and a warning – it is not taken out, a person picks the new address.

Nothing is ever added here: the list stays curated by hand – official broadcaster streams only, no
FAST platforms (Pluto TV, Samsung TV Plus …), no restreams, no Mediathek streams
(handbook/video-apps-ein-platz.md). The script refuses a list that holds a forbidden host.

Usage: python3 check_freetv.py app/src/main/assets/freetv.json [--dry]
"""
import concurrent.futures
import datetime
import html
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

APP_UA = "LindenhausPlayer/1.0 (check)"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
FORBIDDEN = ("pluto.tv", "plex.tv", "samsungtvplus", "samsung.wurl", "rakuten", "roku", "tubi", "xumo", "joyn", "amagi.tv")
UPSTREAM = "https://raw.githubusercontent.com/Free-TV/IPTV/master/lists/%s.md"
TIMEOUT = 12


def fetch(url, ua, limit=200_000):
    """(status, content type, first bytes, final url) – status 0 with a word when nothing came."""
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read(limit), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", b"", url
    except urllib.error.URLError as e:
        why = e.reason
        if isinstance(why, socket.gaierror):
            return 0, "dns", b"", url
        if isinstance(why, (socket.timeout, TimeoutError)):
            return 0, "timeout", b"", url
        return 0, type(why).__name__, b"", url
    except (socket.timeout, TimeoutError):
        return 0, "timeout", b"", url
    except Exception as e:  # noqa: BLE001
        return 0, type(e).__name__, b"", url


def variants(text, base):
    """A master playlist's qualities (their addresses)."""
    out = []
    lines = [ln.strip() for ln in text.splitlines()]
    for i, ln in enumerate(lines):
        if ln.startswith("#EXT-X-STREAM-INF"):
            for nxt in lines[i + 1:]:
                if nxt and not nxt.startswith("#"):
                    out.append(urllib.parse.urljoin(base, nxt))
                    break
    return out


def probe(url, ua):
    """('ok'|'geo'|'dead'|'unsure', a few words). Dead is only said of the channel's own address."""
    status, ctype, body, final = fetch(url, ua)
    if status in (401, 403, 451):
        return "geo", f"HTTP {status}"
    if status == 0:
        return "dead", ctype
    if status >= 400:
        return "dead", f"HTTP {status}"
    text = body.decode("utf-8", "replace")
    if url.split("?")[0].endswith(".mp4") or ctype.startswith("video/mp4"):
        return "ok", "mp4"
    if not text.lstrip().startswith("#EXTM3U"):
        return "dead", "no playlist (" + (ctype or "?")[:30] + ")"
    # a master playlist: one of its qualities (the first three are tried); then a piece of picture
    if "#EXT-X-STREAM-INF" in text:
        why, gone = "master without qualities", 0
        tried = variants(text, final)[:3]
        for nxt in tried:
            status, ctype, body, base = fetch(nxt, ua)
            if status in (401, 403, 451):
                return "geo", f"quality HTTP {status}"
            if 200 <= status < 300 and body.decode("utf-8", "replace").lstrip().startswith("#EXTM3U"):
                text, final, why = body.decode("utf-8", "replace"), base, ""
                break
            why = f"quality {status or ctype}"
            gone += status in (404, 410)
        if why:
            # every quality "not found": no player can show this channel (in the Windows app such a
            # channel ended in a network error) – dead. Anything else cannot be told from here.
            return ("dead" if tried and gone == len(tried) else "unsure"), why
    pieces = [urllib.parse.urljoin(final, ln.strip()) for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if not pieces:
        return "unsure", "playlist without pieces"
    # (a piece from the middle: the newest may not be out yet, the oldest may just have gone)
    status, ctype, body, _ = fetch(pieces[len(pieces) // 2], ua, limit=4096)
    if status in (401, 403, 451):
        return "geo", f"piece HTTP {status}"
    if status == 0 or status >= 400 or not body:
        return "unsure", f"piece {status or ctype}"
    return "ok", "picture"


def check(url):
    state, why = probe(url, APP_UA)
    if state != "ok":
        s2, w2 = probe(url, BROWSER_UA)
        if s2 == "ok":
            return "ok", "only as a browser", True
        if state == "dead" and s2 != "dead":
            return s2, w2, False
    return state, why, False


def page(url):
    """A broadcaster's live page, asked like a browser: ('ok'|'geo'|'dead', its title and where it led)."""
    status, ctype, body, final = fetch(url, BROWSER_UA, limit=400_000)
    if status in (401, 403, 451):
        return "geo", f"HTTP {status}"
    if status == 0:
        return "dead", ctype
    if status >= 400:
        return "dead", f"HTTP {status}"
    m = re.search(rb"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    title = re.sub(r"\s+", " ", html.unescape(m.group(1).decode("utf-8", "replace"))).strip()[:70] if m else (ctype or "?")[:30]
    moved = "" if final.rstrip("/") == url.rstrip("/") else " → " + final
    return "ok", f"HTTP {status} „{title}“{moved}"


def norm(name):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"[ⒼⓈⓎⓃⓃ]", "", name).lower())


def upstream(lists):
    """Every channel of the lists ours were curated from: name → (url, epg id)."""
    out = {}
    for lst in lists:
        status, _, body, _ = fetch(UPSTREAM % lst, APP_UA, limit=2_000_000)
        if status != 200:
            print(f"  upstream list {lst}: {status}")
            continue
        for row in body.decode("utf-8", "replace").splitlines():
            m = re.match(r"\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*\[>\]\(([^)]+)\)\s*\|[^|]*\|\s*([^|]*?)\s*\|", row)
            if m:
                name, url, epg = m.groups()
                out.setdefault((lst, norm(name)), (url, epg.strip()))
                if epg.strip():
                    out.setdefault((lst, "epg:" + epg.strip().lower()), (url, epg.strip()))
    return out


def main(path, dry):
    data = json.load(open(path, encoding="utf-8"))
    channels = data["channels"]
    bad = [c["id"] for c in channels if any(f in (c["url"] + " " + (c.get("live") or "")).lower() for f in FORBIDDEN)]
    if bad:
        print("forbidden hosts in the list:", bad)
        return 2
    # (a live page is the broadcaster's own, an https address – nothing else is opened from the app)
    bad = [c["id"] for c in channels if "live" in c and not str(c["live"]).startswith("https://")]
    if bad:
        print("live pages that are not https:", bad)
        return 2
    lists = sorted({m.group(1) for c in channels for m in [re.search(r"\(([a-z_]+)\)", c.get("source") or "")] if m})
    up = upstream(lists)
    print(f"{len(channels)} channels · upstream rows {len(up)}")

    def one(c):
        r = stream(c)
        return r + ((page(c["live"]),) if c.get("live") else (None,))

    def stream(c):
        url = c["url"]
        state, why, browser = check(url)
        note = ""
        if state != "ok":
            tries = []
            if url.startswith("http://"):
                tries.append("https://" + url[7:])
            lst = (re.search(r"\(([a-z_]+)\)", c.get("source") or "") or [None, None])[1]
            for key in ("epg:" + (c.get("epgId") or "").lower(), norm(c["name"])):
                u = up.get((lst, key))
                if u and u[0] != url and not any(f in u[0].lower() for f in FORBIDDEN):
                    tries.append(u[0])
            for t in dict.fromkeys(tries):
                s2, w2, b2 = check(t)
                if s2 == "ok" and (t.startswith("https://") or not url.startswith("https://")):
                    return c, "ok", "new address", b2, t
                note = f" (also tried {urllib.parse.urlsplit(t).netloc}: {s2})"
        elif url.startswith("http://"):
            s2, w2, b2 = check("https://" + url[7:])
            if s2 == "ok":
                return c, "ok", "https now", b2, "https://" + url[7:]
        return c, state, why + note, browser, None

    with concurrent.futures.ThreadPoolExecutor(12) as ex:
        results = list(ex.map(one, channels))

    today = datetime.date.today().isoformat()
    keep, counts = [], {"ok": 0, "geo": 0, "unsure": 0, "dead": 0, "removed": 0, "moved": 0}
    pages = {"ok": 0, "geo": 0, "dead": 0}
    for c, state, why, browser, new, live in results:
        host = urllib.parse.urlsplit(c["url"]).netloc
        print(f"  {state:6s} {c['id']:34s} {(c.get('geo') or '-'):3s} {why:40s} {host}")
        if live:
            lstate, lwhy = live
            pages[lstate] += 1
            print(f"         ↗ live page {lstate:4s} {c['live']}  {lwhy}")
            if lstate == "dead":
                c["liveFailed"] = c.get("liveFailed") or today
                print(f"::warning::{c['id']}: its live page {c['live']} is gone ({lwhy}) – pick the broadcaster's new address")
            else:
                c.pop("liveFailed", None)
                if lstate == "ok":
                    c["liveOk"] = today
        if new:
            c["url"] = new
            counts["moved"] += 1
        # (a channel that only sends to its own country cannot be judged from a server in the USA)
        if state == "dead" and c.get("geo"):
            state = "unsure"
        counts[state] += 1
        # (↗ a public broadcaster's channel opens outside: its stream is not used, it is never taken out for it)
        if state == "dead" and c.get("live"):
            state = "unsure"
        if state == "dead":
            # gone today: remembered with its day; still gone a week later (the next weekly check) → out
            first = c.get("failed") or today
            c["failed"] = first
            if (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(first)).days >= 6:
                counts["removed"] += 1
                continue
        else:
            c.pop("failed", None)
        c.pop("fails", None)
        if state == "ok":
            c["ok"] = today
        keep.append(c)
    print(f"live pages (public broadcasters, open outside): ok {pages['ok']} · not from the USA {pages['geo']} · gone {pages['dead']}")
    print(f"ok {counts['ok']} · not from the USA {counts['geo']} · cannot be told from here {counts['unsure']} · dead {counts['dead']} · taken out {counts['removed']} · new address {counts['moved']}")
    if dry:
        return 0
    data["channels"] = keep
    data["checked"] = today
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], "--dry" in sys.argv))

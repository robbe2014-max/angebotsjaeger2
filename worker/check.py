#!/usr/bin/env python3
"""Holt die Wochenangebote (marktguru), filtert auf Lidl/REWE/ALDI SÜD, prüft die
Märkte im Umkreis (OpenStreetMap) und verschickt Web-Push bei neuem Bestpreis.
Aufruf:  python worker/check.py [--demo] [--no-push]"""
import json, os, re, sys, time, unicodedata, datetime as dt
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
OUT = (ROOT / "docs" / "data") if (ROOT / "docs").is_dir() else (ROOT / "data")  # Seite liegt in docs/ oder direkt im Hauptordner
UA = {"User-Agent": "Mozilla/5.0 (privater Angebotsvergleich)"}
S = requests.Session(); S.headers.update(UA)

def norm(n):
    n = n.upper().replace("Ü", "UE")
    return "ALDI" if "ALDI" in n else "LIDL" if "LIDL" in n else "REWE" if "REWE" in n else n

WANTED = {norm(m) for m in CFG["maerkte"]}

def _watch_extra():
    """Zusätzliche Produkte aus dem GitHub-Secret WATCHLIST (JSON-Liste), damit die Einkaufsliste nicht öffentlich im Repo steht."""
    try:
        v = json.loads(os.environ.get("WATCHLIST") or "[]")
        return [str(x).strip() for x in v if str(x).strip()][:40]
    except (ValueError, TypeError):
        print("WATCHLIST ist kein gültiges JSON – ignoriert"); return []
WATCH_EXTRA = _watch_extra()

# ---------- marktguru ----------
def mg_keys():
    html = S.get("https://www.marktguru.de/", timeout=30).text
    k = re.search(r'"apiKey"\s*:\s*"([^"]+)"', html); c = re.search(r'"clientKey"\s*:\s*"([^"]+)"', html)
    if not (k and c): raise RuntimeError("marktguru: API-Schlüssel nicht gefunden (Seite geändert?)")
    return k.group(1), c.group(1)

def mg_search(term, keys):
    r = S.get("https://api.marktguru.de/api/v1/offers/search",
              params={"as": "web", "q": term, "zipCode": CFG["plz"], "limit": 100, "offset": 0},
              headers={"x-apikey": keys[0], "x-clientkey": keys[1]}, timeout=30)
    r.raise_for_status()
    out = []
    for o in r.json().get("results", []):
        adv = (o.get("advertisers") or [{}])[0].get("name", "")
        if norm(adv) not in WANTED: continue
        v = (o.get("validityDates") or [{}])[0]
        price = o.get("price")
        if price is None: continue
        unit = (o.get("unit") or {}).get("shortName", "")
        out.append({"markt": adv, "produkt": (o.get("product") or {}).get("name", ""),
                    "beschreibung": o.get("description", ""), "preis": float(price),
                    "alt": o.get("oldPrice"), "grundpreis": o.get("referencePrice"),
                    "menge": o.get("quantity"), "einheit": unit,
                    "von": (v.get("from") or "")[:10], "bis": (v.get("to") or "")[:10], "suche": term})
    return out

# ---------- Märkte im Umkreis (OpenStreetMap) ----------
# Nominatim/Overpass verlangen einen eindeutigen User-Agent (der Browser-ähnliche von oben wird oft abgewiesen).
OSM_UA = {"User-Agent": "angebotsjaeger-privat/1.0 (privater Preisvergleich, GitHub Actions)"}

def geocode_plz(plz):
    """Koordinaten der PLZ: erst Nominatim, dann Photon als Ersatz."""
    fehler = []
    try:
        r = S.get("https://nominatim.openstreetmap.org/search", headers=OSM_UA, timeout=30,
                  params={"postalcode": plz, "country": "Germany", "format": "json", "limit": 1})
        if r.status_code == 200 and r.json(): g = r.json()[0]; return float(g["lat"]), float(g["lon"])
        fehler.append(f"Nominatim HTTP {r.status_code}")
    except Exception as e: fehler.append(f"Nominatim: {e}")
    try:
        r = S.get("https://photon.komoot.io/api/", headers=OSM_UA, timeout=30, params={"q": f"{plz} Deutschland", "limit": 1})
        f = r.json()["features"]
        if r.status_code == 200 and f: lon, lat = f[0]["geometry"]["coordinates"]; return float(lat), float(lon)
        fehler.append(f"Photon HTTP {r.status_code}")
    except Exception as e: fehler.append(f"Photon: {e}")
    raise RuntimeError("PLZ nicht auffindbar (" + "; ".join(fehler) + ")")

def stores_nearby():
    cache = OUT / "maerkte.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < 30 * 86400:
        return json.loads(cache.read_text(encoding="utf-8"))
    lat, lon = geocode_plz(CFG["plz"]); R = int(CFG["umkreis_km"] * 1000)
    q = f'[out:json][timeout:40];(nwr["shop"~"supermarket|discount"](around:{R},{lat},{lon}););out center tags;'
    els = None; last = ""
    for url in ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
                "https://overpass.private.coffee/api/interpreter"):
        for _ in range(2):  # Overpass ist oft kurz überlastet -> einmal wiederholen
            try:
                r = S.post(url, data={"data": q}, headers=OSM_UA, timeout=70)
                if r.status_code == 200 and r.text.lstrip().startswith("{"):
                    els = r.json()["elements"]; break
                last = f"{url}: HTTP {r.status_code}"
            except Exception as e: last = f"{url}: {e}"
            time.sleep(5)
        if els is not None: break
    if els is None: raise RuntimeError("Overpass nicht erreichbar (" + last + ")")
    res = {}
    for e in els:
        t = e.get("tags", {}); n = t.get("brand") or t.get("name") or ""
        if norm(n) in WANTED:
            res.setdefault(norm(n), []).append({"name": t.get("name", n), "strasse": t.get("addr:street", ""), "ort": t.get("addr:city", "")})
    if res: cache.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")  # leere Ergebnisse nicht merken
    return res

# ---------- Demo ----------
def demo_offers():
    d = dt.date.today(); bis = (d + dt.timedelta(days=5)).isoformat(); von = d.isoformat()
    rows = [("Lidl","Hackfleisch gemischt",3.99,500,"g"),("REWE","Rinderhackfleisch",4.49,500,"g"),
            ("ALDI SÜD","Hackfleisch gemischt",3.79,500,"g"),("Lidl","Butter Deutsche Markenbutter",1.39,250,"g"),
            ("REWE","Butter",1.59,250,"g"),("ALDI SÜD","Butter",1.45,250,"g"),("Lidl","Vollmilch 3,5%",0.99,1000,"ml"),
            ("ALDI SÜD","Eier 10 Stück",2.29,10,"Stk"),("REWE","Nudeln 500 g",0.89,500,"g")]
    return [{"markt":m,"produkt":p,"beschreibung":"","preis":pr,"alt":None,"grundpreis":None,"menge":q,"einheit":u,
             "von":von,"bis":bis,"suche":p.split()[0]} for m,p,pr,q,u in rows]

def _fold(x):
    x = unicodedata.normalize("NFD", x.lower().replace("ß", "ss"))
    return "".join(c for c in x if not unicodedata.combining(c))
_EXCL = {"milch": re.compile(r"(reis|schnitte|schoko|choco|brotchen|kakao|drink|pudding|riegel|kondens|shake|kokos|muller|mause|bonbon|freunde|alpen|kaffee|pflanz)"),
         "eier": re.compile(r"(advent|schoko|oster|nougat|marzipan|likor|nudel|kuchen|salat|farbe)")}
_FALSE = {"milch": re.compile(r"^(butter|kondens|kokos|sauer|schoko|mandel|hafer|soja|reis|muller|alpen)")}
def matches(term, o):
    """Treffer nur, wenn das Suchwort am ENDE eines Produktworts steht (Butter ≠ Butterkeks); Plural erlaubt."""
    words = [w for w in re.split(r"[^a-z0-9]+", _fold(o["produkt"] + " " + (o.get("beschreibung") or ""))) if w]
    toks = [t for t in re.split(r"[^a-z0-9]+", _fold(term)) if len(t) >= 3 and not t.isdigit()] or [_fold(term).strip()]
    def ok(w, t):
        stem = re.sub(r"(en|n|e|s)$", "", t) if len(t) >= 6 else t
        return bool(re.search(re.escape(stem) + r"(?:en|n|e|s)?$", w)) and not (t in _FALSE and _FALSE[t].match(w))
    full = _fold(o["produkt"] + " " + (o.get("beschreibung") or ""))
    return all(t and any(ok(w, t) for w in words) and not (t in _EXCL and _EXCL[t].search(full)) for t in toks)

def unit_price(o):
    """(Preis pro kg/l/Stück, Einheit). marktguru: 'grundpreis' + 'einheit'; 'menge' ist nur die Stückzahl."""
    try: g = float(o.get("grundpreis") or 0)
    except (TypeError, ValueError): g = 0
    return (g, o["einheit"]) if g > 0 and o.get("einheit") else None

def best_of(hits, today=None):
    """Günstigstes derzeit GÜLTIGES Angebot (nach Grundpreis, wenn alle gleiche Einheit haben, sonst nach Packungspreis)."""
    today = today or dt.date.today().isoformat()
    hits = [o for o in hits if (o.get("von") or "") <= today <= (o.get("bis") or "9999")]
    if not hits: return None
    us = [unit_price(o) for o in hits]
    if all(us) and len({u[1] for u in us}) == 1:
        return min(zip(hits, us), key=lambda x: x[1][0])[0]
    return min(hits, key=lambda o: o["preis"])

# ---------- Push ----------
def push(title, body):
    if "--no-push" in sys.argv: print("(--no-push)", title, "-", body); return
    subs = json.loads(os.environ.get("PUSH_SUBSCRIPTIONS") or "[]")
    if not subs: print("Keine Push-Abos hinterlegt:", title, "-", body); return
    from pywebpush import webpush, WebPushException
    claims = {"sub": os.environ.get("VAPID_SUBJECT", "mailto:privat@example.com")}
    for s in subs:
        try:
            webpush(s, json.dumps({"title": title, "body": body}), vapid_private_key=os.environ["VAPID_PRIVATE_KEY"], vapid_claims=dict(claims))
        except WebPushException as e: print("Push-Fehler:", e)

def main():
    demo = "--demo" in sys.argv; OUT.mkdir(parents=True, exist_ok=True)
    offers, fehler = [], []
    if demo: offers = demo_offers()
    else:
        keys = mg_keys()
        terms = [w["suche"] for w in CFG["watchlist"]] + WATCH_EXTRA + CFG["zusatz_suchbegriffe"]
        for t in dict.fromkeys(terms):
            try: offers += mg_search(t, keys)
            except Exception as e: fehler.append(f"{t}: {e}")
            time.sleep(1)
    try: maerkte = {} if demo else stores_nearby()
    except Exception as e: maerkte = {}; fehler.append(f"Umkreissuche: {e}")
    if maerkte:  # nur Märkte, die wirklich im Umkreis liegen
        offers = [o for o in offers if norm(o["markt"]) in maerkte]
    seen, uniq = set(), []
    for o in offers:
        k = (norm(o["markt"]), o["produkt"], o["preis"], o["von"], o["bis"])
        if k not in seen: seen.add(k); uniq.append(o)
    uniq = [o for o in uniq if not o["bis"] or o["bis"] >= dt.date.today().isoformat()]  # Abgelaufenes weglassen
    old, best_seen = {}, set()
    p = OUT / "best.json"
    if p.exists(): old = json.loads(p.read_text(encoding="utf-8"))
    best = {}
    for w in CFG["watchlist"] + [{"suche": t} for t in WATCH_EXTRA]:
        s = w["suche"].lower()
        if s in best_seen: continue
        best_seen.add(s)
        hits = [o for o in uniq if matches(w["suche"], o)]
        if not hits: continue
        b = best_of(hits)
        if not b: continue  # nur Angebote, die jetzt gelten, lösen Push aus
        best[w["suche"]] = b
        if w.get("max_preis") and b["preis"] > w["max_preis"]: continue
        if old.get(w["suche"], {}).get("preis") != b["preis"] or old.get(w["suche"], {}).get("markt") != b["markt"]:
            push(f"Bestpreis {w['suche']}", f"{b['produkt']} bei {b['markt']}: {b['preis']:.2f} € (bis {b['bis']})")
    (OUT / "offers.json").write_text(json.dumps({"stand": dt.datetime.now().isoformat(timespec="minutes"), "demo": demo,
        "plz": CFG["plz"], "maerkte": maerkte, "fehler": fehler, "angebote": uniq}, ensure_ascii=False), encoding="utf-8")
    p.write_text(json.dumps(best, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(uniq)} Angebote, {len(best)} Watchlist-Treffer, Fehler: {fehler}")
    if fehler and not uniq: sys.exit(1)

if __name__ == "__main__": main()

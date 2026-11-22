"""Sondagem (só imprime): aluguéis com ofurô, jacuzzi, hidromassagem, banheira ou piscina privativa na unidade.

Usa as mesmas APIs e parâmetros dos coletores (grupozap e quintoandar), com área mínima de 85 m², nos bairros
dos Jardins, Itaim, Vila Nova e Pinheiros. Lista primeiro os mobiliados; depois os demais, para conferência.
"""
import collections
import json
import re

from imoveis import geo
from imoveis.common import Config
from imoveis.http import Http
from imoveis.sources import grupozap as gz, quintoandar as qa

AREA_MIN = 85
cfg = Config.load()
cfg.min_area = AREA_MIN
http = Http(0.6, 1.2)
POLY = cfg.area_polygon

BAIRROS = ["Jardim Paulista", "Cerqueira César", "Jardim América", "Jardim Europa", "Jardim Paulistano",
           "Itaim Bibi", "Vila Nova Conceição", "Pinheiros"]
MAX = {"zap": 2400, "vivareal": 600}

# Códigos de comodidade e trechos de texto que indicam água na unidade.
CODE = re.compile(r"JACUZZI|HOT_?TUB|WHIRLPOOL|HYDRO|HIDRO|OFURO|BATH_?TUB|BANHEIRA|SPA|PRIVATE_POOL|PISCINA_PRIVATIVA",
                  re.I)
TEXT = re.compile(r"ofur[oô]|jacuzz?i|hidromassagem|banheira|piscina privativa|spa privativo", re.I)

found = {}          # chave -> dict
code_seen = collections.Counter()


def snippet(txt: str) -> str:
    m = TEXT.search(txt or "")
    return txt[max(0, m.start() - 50): m.end() + 50].replace("\n", " ") if m else ""


def add(key, **kw):
    if key not in found:
        found[key] = kw


# --- ZAP e Viva Real (glue-api), como em imoveis/sources/grupozap.py ---
for portal in ("zap", "vivareal"):
    site = gz.SITES[portal]
    headers = {"x-domain": site["domain"], "Origin": site["site"], "Referer": site["site"] + "/",
               "Accept": "application/json"}
    for nb in BAIRROS:
        n = off = 0
        while off < MAX[portal]:
            try:
                data = gz._get_page(http, portal,
                                    lambda rung, size, sort: gz._api_params(cfg, "aluguel", nb, off, rung, size, sort),
                                    headers)
            except Exception as e:
                print(f"[{portal} {nb}] ERRO", str(e)[:200]); break
            search = data.get("search") or {}
            page = (search.get("result") or {}).get("listings") or []
            for it in page:
                n += 1
                lst = it.get("listing", it)
                am = set(lst.get("amenities") or [])
                codes = sorted(c for c in am if CODE.search(c))
                code_seen.update(codes)
                text = " ".join(str(lst.get(k) or "") for k in ("title", "description"))
                snip = snippet(text)
                if not codes and not snip:
                    continue
                l = gz.parse_listing(it, portal, "aluguel")
                if not l or (l.area or 0) < AREA_MIN:
                    continue
                add(f"{portal}:{l.id}", portal=portal, bairro=l.neighborhood, end=l.address, area=l.area,
                    q=l.bedrooms, total=l.total_monthly, mob=bool(l.furnished), ac=bool(l.air_conditioning),
                    codes=codes, snip=snip, lat=l.lat, lon=l.lon, url=l.url)
            off += len(page)
            if not page or off >= (search.get("totalCount") or 0):
                break
        print(f"[{portal} {nb}] {n} anúncios lidos (≥ {AREA_MIN} m²)")

# --- QuintoAndar, como em imoveis/sources/quintoandar.py (amenities = unidade, installations = condomínio) ---
hdr = {"Origin": qa.SITE, "Referer": qa.SITE + "/", "Content-Type": "application/json"}
vps = qa.area_tiles(POLY, 3) + [qa.VIEWPORTS["itaim bibi"], qa.VIEWPORTS["vila nova conceicao"],
                                 {"north": -23.555, "south": -23.575, "east": -46.675, "west": -46.700}]
unit_codes, condo_codes = collections.Counter(), collections.Counter()
for vi, vp in enumerate(vps):
    n, off = 0, 0
    while off < 1000:
        body = qa._body(cfg, "aluguel", off, qa.PAGE_SIZE, cfg.neighborhoods[0], vp)
        r = http.post(qa.API, json=body, headers=hdr)
        if r.status_code != 200:
            if not off:
                print(f"[quintoandar faixa {vi}] HTTP {r.status_code}: {r.text[:200]}")
            break
        d = r.json()
        hits = (d.get("hits") or {}).get("hits") or []
        for h in hits:
            s = h.get("_source", h); n += 1
            am, ins = set(s.get("amenities") or []), set(s.get("installations") or [])
            unit_codes.update(am); condo_codes.update(ins)
            codes = sorted(c for c in am if CODE.search(c))
            if not codes:
                continue
            l = qa.parse_house(s, "aluguel")
            if not l or (l.area or 0) < AREA_MIN:
                continue
            add(f"quintoandar:{l.id}", portal="quintoandar", bairro=l.neighborhood, end=l.address, area=l.area,
                q=l.bedrooms, total=l.total_monthly, mob=bool(l.furnished), ac=bool(l.air_conditioning),
                codes=codes, snip="", lat=l.lat, lon=l.lon, url=l.url)
        total = (d.get("hits") or {}).get("total") or {}
        total = total.get("value", 0) if isinstance(total, dict) else total
        off += qa.PAGE_SIZE
        if not hits or off >= (total or 0):
            break
    print(f"[quintoandar faixa {vi}] {n} imóveis lidos")

print("\nCódigos aquáticos vistos no ZAP/Viva Real:", code_seen.most_common())
print("QuintoAndar, comodidades da unidade com água:", sorted((k, v) for k, v in unit_codes.items() if CODE.search(k)))
print("QuintoAndar, do condomínio com água:", sorted((k, v) for k, v in condo_codes.items() if CODE.search(k)))

# Mesmo imóvel em vários portais/anunciantes: agrupa por endereço + área + total.
seen, rows = set(), []
for k, f in sorted(found.items(), key=lambda kv: (not kv[1]["mob"], kv[1]["total"] or 0)):
    dk = (f["end"], round(f["area"] or 0), round((f["total"] or 0) / 100))
    f["dup"] = dk in seen
    seen.add(dk)
    f["na_area"] = bool(f["lat"] and POLY and geo.inside(f["lat"], f["lon"], POLY))
    f["dist_m"] = round(geo.distance_m(f["lat"], f["lon"], POLY)) if f["lat"] and POLY else None
    rows.append(f)

print(f"\n=== {len(rows)} anúncios com água na unidade (≥ {AREA_MIN} m²) ===")
for f in rows:
    print(json.dumps({k: v for k, v in f.items() if k not in ("lat", "lon")}, ensure_ascii=False))

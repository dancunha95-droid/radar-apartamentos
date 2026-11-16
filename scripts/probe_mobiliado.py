"""Sondagem (só imprime): como os portais informam "mobiliado" nos aluguéis do Jardim Paulista."""
import collections
import json
import re

from imoveis.common import Config
from imoveis.http import Http
from imoveis.sources import grupozap as gz, quintoandar as qa

cfg = Config.load()
http = Http(0.6, 1.2)
PAT = re.compile(r"FURNI|MOBIL|MÓVE|MOVE", re.I)
nb = "Jardim Paulista"
for portal in ("zap", "vivareal"):
    site = gz.SITES[portal]
    headers = {"x-domain": site["domain"], "Origin": site["site"], "Referer": site["site"] + "/", "Accept": "application/json"}
    am, n, title_hits, keys = collections.Counter(), 0, 0, collections.Counter()
    sample = None
    for off in (0, 24, 48, 72, 96, 120):
        try:
            data = gz._get_page(http, portal, lambda rung, size, sort: gz._api_params(cfg, "aluguel", nb, off, rung, size, sort), headers)
        except Exception as e:
            print(f"[{portal}] ERRO", e); break
        for it in data["search"]["result"]["listings"] or []:
            n += 1
            lst = it.get("listing", it)
            am.update(set(lst.get("amenities") or []))
            keys.update(lst.keys())
            txt = json.dumps(lst, ensure_ascii=False)
            if re.search(r"mobiliad", txt, re.I):
                title_hits += 1
                if sample is None:
                    sample = {k: v for k, v in lst.items() if re.search(r"mobiliad|furni", json.dumps(v, ensure_ascii=False), re.I)}
    print(f"[{portal} aluguel {nb}] {n} anúncios")
    print("  amenities com móveis:", sorted((k, v) for k, v in am.items() if PAT.search(k)))
    print("  todas as amenities (top 60):", am.most_common(60))
    print("  campos do listing:", sorted(keys))
    print(f"  anúncios com 'mobiliad' em algum campo: {title_hits}; exemplo de campos: {str(sample)[:600]}")

hdr = {"Origin": qa.SITE, "Referer": qa.SITE + "/", "Content-Type": "application/json"}
EXTRA = ["installations", "isFurnished", "furnished", "hasFurniture", "furniture", "amenitiesLabels", "shortRentDescription"]
am, ins, n, other = collections.Counter(), collections.Counter(), 0, collections.Counter()
for off in range(0, 240, 60):
    body = qa._body(cfg, "aluguel", off, 60, "jardim paulista")
    body["fields"] = qa.FIELDS + EXTRA
    try:
        hits = (http.post(qa.API, json=body, headers=hdr).json().get("hits") or {}).get("hits") or []
    except Exception as e:
        print("[quintoandar] ERRO", e); break
    for h in hits:
        s = h.get("_source", {}); n += 1
        am.update(set(s.get("amenities") or [])); ins.update(set(s.get("installations") or []))
        for k in EXTRA:
            if k in s:
                other[(k, str(s[k])[:40])] += 1
print(f"[quintoandar aluguel] {n} imóveis")
print("  amenities com móveis:", sorted((k, v) for k, v in am.items() if PAT.search(k)))
print("  todas as amenities (top 60):", am.most_common(60))
print("  campos extras:", other.most_common(30))

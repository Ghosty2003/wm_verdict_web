"""只读导出：同卷对比页（data/samecase_pages.json）的标注，旧标注另列。不改数据库任何内容。
    export SUPABASE_SERVICE_KEY=...
    python3 tools/export_samecase.py --out /mnt/qnap/chenmg93/wm_verdict/libero/out/annotation/samecase_20261115/export.json \
        [--cutoff 2026-11-16T00:00:00Z]
输出两张表：
  samecase：同卷页上的每个问题（页 id、模型、REAL/IMAGINED、unit_id、card_id）× 每条标注（标注员匿名编号、label、note、updated_at）；
            pre_redesign = 该标注早于 --cutoff（同卷页上线时刻），即沿用旧卡时在旧版页面上标的；
  old：round 1/2/3 里不在同卷页上的卡的全部标注（旧版页面留下的，原样保留）。
不导出邮箱；标注员编号 = user_id 的 sha256 前 8 位。"""
import argparse
import datetime
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def base_url():
    s = open(os.path.join(HERE, "config.js"), encoding="utf-8").read()
    return re.search(r'SUPABASE_URL:\s*"([^"]+)"', s).group(1).rstrip("/")


def get(url, key, table, params):
    out, off, step = [], 0, 1000
    while True:
        q = urllib.parse.urlencode({**params, "limit": step, "offset": off})
        r = urllib.request.Request(f"{url}/rest/v1/{table}?{q}", headers={"apikey": key, "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(r, timeout=60) as f:
            rows = json.load(f)
        out += rows
        if len(rows) < step:
            return out
        off += step


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cutoff", default=None, help="同卷页上线时刻（ISO，UTC）；早于它的标注记 pre_redesign")
    a = ap.parse_args()
    key = os.environ.get("SUPABASE_SERVICE_KEY"); assert key, "先 export SUPABASE_SERVICE_KEY=..."
    url = base_url()
    P = json.load(open(os.path.join(HERE, "data", "samecase_pages.json")))["pages"]
    cards = get(url, key, "cards", {"select": "id,round_id,model,task,family,level,unit_id", "order": "id"})
    by = {(c["round_id"], c["unit_id"]): c for c in cards}
    qs, on_page = [], set()
    for p in P:
        for r in p["rows"]:
            for kind, rid in (("real", 2), ("imag", 3)):
                if r[kind] and (rid, r[kind]) in by:
                    c = by[(rid, r[kind])]; on_page.add(c["id"])
                    qs.append(dict(page_id=p["id"], T=p["T"], level=p["level"], group=p.get("group"),
                                   model=r["model"], kind=kind, unit_id=r[kind], card_id=c["id"]))
    ids = [c["id"] for c in cards]
    ann = []
    for i in range(0, len(ids), 200):
        ann += get(url, key, "annotations", {"select": "card_id,user_id,label,note,updated_at",
                                             "card_id": f"in.({','.join(map(str, ids[i:i + 200]))})", "order": "id"})
    for x in ann:
        x["annotator"] = hashlib.sha256(x.pop("user_id").encode()).hexdigest()[:8]
        x["pre_redesign"] = bool(a.cutoff and x["updated_at"] < a.cutoff)
    A = {}
    for x in ann:
        A.setdefault(x["card_id"], []).append(x)
    same = [dict(q, annotations=A.get(q["card_id"], [])) for q in qs]
    cid = {c["id"]: c for c in cards}
    old = [dict(card=cid[k], annotations=v) for k, v in sorted(A.items()) if k not in on_page]
    out = dict(exported_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), cutoff=a.cutoff,
               n_pages=len(P), n_questions=len(qs), samecase=same, old=old)
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    n_ans = sum(len(q["annotations"]) for q in same)
    print(f"同卷页 {len(P)} 页，问题 {len(qs)} 个，已有标注 {n_ans} 条（其中改版前 {sum(x['pre_redesign'] for q in same for x in q['annotations'])} 条）；"
          f"旧标注另列 {sum(len(o['annotations']) for o in old)} 条（{len(old)} 张卡） → {a.out}")


if __name__ == "__main__":
    main()

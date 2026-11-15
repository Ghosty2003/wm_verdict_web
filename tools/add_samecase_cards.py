"""同卷对比改版（2026-11-15）：把新卡插入已有的 round 2（REAL）/ round 3（IMAGINED），按 unit_id 对应，不建新轮次。
已在库里的 unit_id 一律跳过（沿用旧卡和它上面的旧标注，不改不删）。卡片图已在本仓库 cards/r2/、cards/r3/。
不带 --yes 只检查（轮次名、已有卡数、图片是否齐全），不写库。

  export SUPABASE_SERVICE_KEY=...      # 只在本机终端用，绝不写进仓库
  python3 tools/add_samecase_cards.py --manifest /mnt/qnap/chenmg93/wm_verdict/libero/out/annotation/samecase_20261115/manifest_samecase.json [--yes]
"""
import argparse
import json
import os
import re
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECT = {2: "round2", 3: "r3_imagined"}          # 轮次名前缀核对，防止 id 对错


def base_url():
    s = open(os.path.join(HERE, "config.js"), encoding="utf-8").read()
    return re.search(r'SUPABASE_URL:\s*"([^"]+)"', s).group(1).rstrip("/")


def req(url, key, method, path, body=None):
    r = urllib.request.Request(f"{url}/rest/v1/{path}", method=method,
                               data=None if body is None else json.dumps(body).encode(),
                               headers={"apikey": key, "Authorization": f"Bearer {key}",
                                        "Content-Type": "application/json", "Prefer": "return=representation"})
    with urllib.request.urlopen(r, timeout=120) as f:
        t = f.read()
        return json.loads(t) if t else None


def get_all(url, key, path):
    out, off = [], 0
    while True:
        rows = req(url, key, "GET", f"{path}&limit=1000&offset={off}")
        out += rows
        if len(rows) < 1000:
            return out
        off += 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("SUPABASE_SERVICE_KEY"); assert key, "先 export SUPABASE_SERVICE_KEY=..."
    url = base_url()
    cards = json.load(open(a.manifest))["cards"]
    rounds = {r["id"]: r["name"] for r in req(url, key, "GET", "rounds?select=id,name&order=id")}
    print("rounds:", rounds)
    for rid, pre in EXPECT.items():
        if not rounds.get(rid, "").startswith(pre):
            print(f"STOP: round {rid} is {rounds.get(rid)!r}, expected name starting with {pre!r}; nothing written"); return
    plan = {}
    for rid in (2, 3):
        have = get_all(url, key, f"cards?select=unit_id,sort_key&round_id=eq.{rid}")
        done = {c["unit_id"] for c in have}
        new = [c for c in cards if c["round_id"] == rid and c["unit_id"] not in done]
        miss = [c["unit_id"] for c in new if not any(os.path.exists(f"{HERE}/cards/r{rid}/{c['unit_id']}.{x}") for x in ("webp", "png"))]
        start = max([c["sort_key"] or 0 for c in have] + [0]) + 1
        plan[rid] = (new, start)
        print(f"round {rid}: {len(have)} cards in db; manifest {sum(c['round_id'] == rid for c in cards)}; to add {len(new)}; images missing {len(miss)} {miss[:3]}")
        if miss:
            print("STOP: images missing, nothing written"); return
    if not a.yes:
        print("dry run only (add --yes to insert)"); return
    for rid, (new, start) in plan.items():
        rows = [dict(round_id=rid, model=c["model"], task=c["task"], family=c["family"], level=c["level"], unit_id=c["unit_id"],
                     img_url=None, ref_url=c.get("ref"), question=c["question"], label_set=c["labels"], sort_key=start + n)
                for n, c in enumerate(new)]
        for i in range(0, len(rows), 200):
            req(url, key, "POST", "cards", rows[i:i + 200])
        print(f"DONE round {rid}: inserted {len(rows)}")


if __name__ == "__main__":
    main()

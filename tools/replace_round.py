"""把某一轮的卡片整体替换成新清单（2026-11-12：round2 想象帧卡片 → 闭环真实画面卡片）。
步骤：① 把这一轮现有的 cards 和 annotations 全部备份成 JSON（删除会级联删掉标注，所以先备份）；
② 删除这一轮的旧卡片；③ 按新清单插入新卡片（图片在本仓库 cards/r<id>/，Dropbox 直链只作后备）；④ 改轮次名。
不带 --yes 只做 ① 和检查，不删不插。

  export SUPABASE_SERVICE_KEY=...      # 只在本机终端用，绝不写进仓库
  python3 tools/replace_round.py --round-id 2 --new-name round2_闭环真实画面 \
      --manifest /mnt/qnap/chenmg93/wm_verdict/libero/out/annotation/round2_real/manifest_real.json [--yes]
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.request

URL = "https://jrkbstpomsyyxfbpshmt.supabase.co"


def req(key, method, path, body=None):
    r = urllib.request.Request(f"{URL}/rest/v1/{path}", method=method,
                               data=None if body is None else json.dumps(body).encode(),
                               headers={"apikey": key, "Authorization": f"Bearer {key}",
                                        "Content-Type": "application/json", "Prefer": "return=representation"})
    try:
        with urllib.request.urlopen(r, timeout=120) as f:
            t = f.read()
            return json.loads(t) if t else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} on {method} {path.split('?')[0]}: {e.read().decode(errors='replace')[:500]}")


def get_all(key, path):
    out, off = [], 0
    while True:
        page = req(key, "GET", f"{path}&limit=1000&offset={off}")
        out += page; off += len(page)
        if len(page) < 1000:
            return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round-id", type=int, required=True)
    ap.add_argument("--new-name", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    key = os.environ["SUPABASE_SERVICE_KEY"]
    rid = a.round_id
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    man = json.load(open(a.manifest))
    miss = [m["unit_id"] for m in man if not any(os.path.exists(f"{here}/cards/r{rid}/{m['unit_id']}.{x}") for x in ("webp", "png"))]
    old = get_all(key, f"cards?select=*&round_id=eq.{rid}&order=id")
    ids = [c["id"] for c in old]
    ann = []
    for i in range(0, len(ids), 200):
        ann += get_all(key, f"annotations?select=*&card_id=in.({','.join(map(str, ids[i:i + 200]))})&order=id")
    rnd = req(key, "GET", f"rounds?select=*&id=eq.{rid}")
    bk = f"{here}/backups/round{rid}_before_replace_{time.strftime('%Y%m%d_%H%M%S')}.json"
    os.makedirs(os.path.dirname(bk), exist_ok=True)
    json.dump(dict(round=rnd, cards=old, annotations=ann), open(bk, "w"), ensure_ascii=False)
    print(f"round {rid} {rnd[0]['name'] if rnd else '?'}: {len(old)} old cards, {len(ann)} annotations -> backup {bk}")
    print(f"new manifest: {len(man)} cards; missing images in cards/r{rid}: {len(miss)}")
    if not a.yes or miss:
        print("dry run only (add --yes to replace)" if not miss else "STOP: images missing, nothing changed")
        return
    for i in range(0, len(ids), 200):
        req(key, "DELETE", f"cards?id=in.({','.join(map(str, ids[i:i + 200]))})")
    man.sort(key=lambda m: (m["task"], m["family"], m["level"], m["model"], m["unit_id"]))
    rows = [dict(round_id=rid, model=m["model"], task=m["task"], family=m["family"], level=m["level"],
                 unit_id=m["unit_id"], img_url=m.get("img_url") or f"cards/r{rid}/{m['unit_id']}.webp", ref_url=None, question=m["question"],
                 label_set=m["labels"], sort_key=n) for n, m in enumerate(man)]
    for i in range(0, len(rows), 200):
        req(key, "POST", "cards", rows[i:i + 200])
    req(key, "PATCH", f"rounds?id=eq.{rid}", dict(name=a.new_name))
    print(f"DONE: round {rid} renamed to {a.new_name}, {len(rows)} cards inserted")


if __name__ == "__main__":
    main()

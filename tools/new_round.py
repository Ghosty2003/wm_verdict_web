"""新建一轮标注并整轮插入卡片（2026-11-13：r3_imagined = 闭环想象末帧卡片）。
图片在本仓库 cards/r<round_id>/<unit_id>.webp（网页按 round_id 找目录）。为避免目录和库里的 id 对不上：
新建 round 后若数据库给的 id 不等于 --expect-id，立即删掉这条空 round 并退出，不插任何卡片。
不带 --yes 只做检查（图片齐不齐、同名 round 是否已存在），不写库。

  export SUPABASE_SERVICE_KEY=...      # 只在本机终端用，绝不写进仓库
  python3 tools/new_round.py --manifest /mnt/qnap/chenmg93/wm_verdict/libero/out/annotation/round3_imagined/manifest_r3.json \
      --expect-id 3 [--yes]
"""
import argparse
import json
import os
import urllib.parse
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--expect-id", type=int, required=True)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    key = os.environ["SUPABASE_SERVICE_KEY"]
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    M = json.load(open(a.manifest)); name, cards = M["round_name"], M["cards"]
    rid = a.expect_id
    miss = [c["unit_id"] for c in cards if not any(os.path.exists(f"{here}/cards/r{rid}/{c['unit_id']}.{x}") for x in ("webp", "png"))]
    refs = sorted({c["ref"] for c in cards if c.get("ref")}); miss_ref = [r for r in refs if not os.path.exists(f"{here}/{r}")]
    rounds = req(key, "GET", "rounds?select=id,name&order=id")
    print(f"existing rounds: {rounds}")
    print(f"round {name}: {len(cards)} cards; missing images in cards/r{rid}: {len(miss)}; refs {refs} missing {miss_ref}")
    if any(r["name"] == name for r in rounds):
        print("STOP: a round with this name already exists"); return
    if miss or miss_ref:
        print("STOP: images missing, nothing written"); return
    if not a.yes:
        print("dry run only (add --yes to create the round and insert cards)"); return
    rnd = req(key, "POST", "rounds", [dict(name=name, master_seed=M["seed"], frac="fail_all + 5 success/cell")])[0]
    if rnd["id"] != rid:
        req(key, "DELETE", f"rounds?id=eq.{rnd['id']}")
        print(f"STOP: database assigned id {rnd['id']} (expected {rid}); empty round deleted. "
              f"Rename cards/r{rid} -> cards/r{rnd['id']} (git mv) and rerun with --expect-id {rnd['id']}."); return
    cards.sort(key=lambda c: (c["task"], c["family"], c["level"], c["model"], c["unit_id"]))
    rows = [dict(round_id=rid, model=c["model"], task=c["task"], family=c["family"], level=c["level"], unit_id=c["unit_id"],
                 img_url=f"cards/r{rid}/{c['unit_id']}.webp", ref_url=c.get("ref"), question=c["question"], label_set=c["labels"], sort_key=n)
            for n, c in enumerate(cards)]
    for i in range(0, len(rows), 200):
        req(key, "POST", "cards", rows[i:i + 200])
    print(f"DONE: round {name} id={rid}, {len(rows)} cards inserted")


if __name__ == "__main__":
    main()

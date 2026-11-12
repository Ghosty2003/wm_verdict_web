"""往已有的一轮标注里追加卡片（例：Cosmos Policy T4 闭环想象链并入 round2）。
卡片图已放进本仓库 cards/r<round_id>/（网页优先读仓库内图片），Dropbox 直链只作后备。
已在库里的 unit_id 不会重复插入，可重复运行。

  export SUPABASE_SERVICE_KEY=...   # service_role / secret key，只在本机用，绝不写进仓库
  python3 tools/add_cards.py --round-name round2_闭环想象链_t4t6 \
      --manifest /mnt/qnap/chenmg93/wm_verdict/libero/out/annotation/round2_closed/manifest_cosmos.json \
      --dbx-dir wm_verdict/libero/out/annotation/round2_closed/cards [--dry]
"""
import argparse
import json
import os
import subprocess
import urllib.parse
import urllib.request

URL = "https://jrkbstpomsyyxfbpshmt.supabase.co"


def req(key, method, path, body=None):
    r = urllib.request.Request(f"{URL}/rest/v1/{path}", method=method,
                               data=None if body is None else json.dumps(body).encode(),
                               headers={"apikey": key, "Authorization": f"Bearer {key}",
                                        "Content-Type": "application/json", "Prefer": "return=representation"})
    with urllib.request.urlopen(r) as f:
        return json.loads(f.read() or "null")


def dlink(path):
    out = subprocess.run(["rclone", "link", f"dbx:{path}"], capture_output=True, text=True).stdout.strip()
    return out.replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("&dl=0", "").replace("?dl=0", "") or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round-name", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--dbx-dir", required=True)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    key = os.environ["SUPABASE_SERVICE_KEY"]
    rnd = req(key, "GET", "rounds?select=id,name&name=eq." + urllib.parse.quote(a.round_name))
    assert len(rnd) == 1, f"round not found / ambiguous: {rnd}"
    rid = rnd[0]["id"]
    have = req(key, "GET", f"cards?select=unit_id,sort_key&round_id=eq.{rid}&limit=100000")
    done = {c["unit_id"] for c in have}
    start = max([c["sort_key"] or 0 for c in have] + [0]) + 1
    man = [m for m in json.load(open(a.manifest)) if m["unit_id"] not in done]
    man.sort(key=lambda m: (m["task"], m["family"], m["level"], m["unit_id"]))
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    miss = [m["unit_id"] for m in man if not os.path.exists(f"{here}/cards/r{rid}/{m['unit_id']}.png")]
    print(f"round {a.round_name} id={rid}: {len(have)} cards in db, {len(man)} to add; missing in repo cards/r{rid}: {len(miss)}")
    if a.dry or not man:
        return
    rows = []
    for n, m in enumerate(man):
        rows.append(dict(round_id=rid, model=m["model"], task=m["task"], family=m["family"], level=m["level"],
                         unit_id=m["unit_id"], img_url=dlink(f"{a.dbx_dir}/{m['unit_id']}.png"), ref_url=None,
                         question=m["question"], label_set=m["labels"], sort_key=start + n))
        if len(rows) == 80:
            req(key, "POST", "cards", rows); rows = []
    if rows:
        req(key, "POST", "cards", rows)
    print("DONE added", len(man))


if __name__ == "__main__":
    main()

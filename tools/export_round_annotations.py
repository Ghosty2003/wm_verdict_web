"""只读导出某一轮的卡片与标注（给乐观率报告用）。不改数据库任何内容。
服务密钥只从环境变量读，不写进任何文件：
    export SUPABASE_SERVICE_KEY=...
    python3 tools/export_round_annotations.py --round-id 3 \
        --out /mnt/qnap/chenmg93/wm_verdict/libero/out/optimism/r3_annotations_export.json
导出内容：轮次信息、每张卡（id / model / task / family / level / unit_id）、每条标注（card_id / 标注员匿名编号 / label / updated_at）。
不导出邮箱；标注员编号 = user_id 的 sha256 前 8 位。"""
import argparse
import datetime
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def base_url():
    s = open(os.path.join(HERE, "..", "config.js"), encoding="utf-8").read()
    return re.search(r'SUPABASE_URL:\s*"([^"]+)"', s).group(1).rstrip("/")


def get(url, key, table, params):
    out, off, step = [], 0, 1000
    while True:
        q = urllib.parse.urlencode({**params, "limit": step, "offset": off})
        req = urllib.request.Request(f"{url}/rest/v1/{table}?{q}", headers={"apikey": key, "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            rows = json.load(r)
        out += rows
        if len(rows) < step:
            return out
        off += step


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round-id", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    assert key, "先 export SUPABASE_SERVICE_KEY=..."
    url = base_url()
    rnd = get(url, key, "rounds", {"select": "id,name,master_seed,frac,note,created_at", "id": f"eq.{a.round_id}"})
    assert rnd, f"round {a.round_id} 不存在"
    cards = get(url, key, "cards", {"select": "id,model,task,family,level,unit_id", "round_id": f"eq.{a.round_id}", "order": "id"})
    ids = [c["id"] for c in cards]
    ann = []
    for i in range(0, len(ids), 200):
        chunk = ",".join(map(str, ids[i:i + 200]))
        ann += get(url, key, "annotations", {"select": "card_id,user_id,label,updated_at", "card_id": f"in.({chunk})", "order": "id"})
    for x in ann:
        x["annotator"] = hashlib.sha256(x.pop("user_id").encode()).hexdigest()[:8]
    out = dict(exported_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               round=rnd[0], n_cards=len(cards), n_annotations=len(ann), cards=cards, annotations=ann)
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    done = len({x["card_id"] for x in ann})
    print(f"round {rnd[0]['id']} {rnd[0]['name']}: 卡片 {len(cards)}，已标卡片 {done}，标注 {len(ann)} 条，"
          f"标注员 {len({x['annotator'] for x in ann})} 人 → {a.out}")


if __name__ == "__main__":
    main()

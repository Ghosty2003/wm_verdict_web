"""生成一轮标注：每个（模型 × 任务 × 扰动档）从 50 个 unit 里按种子抽 1/10（choice(50, 5)），
为抽中的卡片图生成 Dropbox 直链，并把 round + cards 写入 Supabase。

抽样规则与基准一致：RandomState(master_seed) 对每格独立 choice(50, 5, replace=False)，
格子按 (model, task, family, level) 字典序遍历，种子入 rounds 表备案。

用法（在 NAS 上，需要 rclone 已配好 dbx: 且 Supabase service key 在环境变量里）：
  export SUPABASE_URL=https://xxx.supabase.co
  export SUPABASE_SERVICE_KEY=...          # service_role key，只在服务器用，绝不进前端
  python tools/make_round.py --name round1_famO --seed 20261115 \
      --spec specs/round1_famO.json [--dry]

spec 文件格式（JSON）——一格一条，png_dir 下需有 <unit_id>.png 的预渲染卡片图：
[
  {"model":"lingbot","task":"T1","family":"O","level":"O3",
   "png_dir":"wm_verdict/libero/out/content_review/lingbot_famO/cards",
   "units_glob_jsonl":"wm_verdict/libero/out/runs/lingbot_famO/records_t3.*.jsonl",
   "unit_filter_level":"O3",
   "ref":"wm_verdict/libero/out/content_review/lingbot_famO/jasmine/real_reference.png",
   "question":"抽屉是否关好、碗是否已出（按整段判）？",
   "labels":["looks_success","borderline","not_success_but_triggered","uncertain"]}
]
说明：units 从 records jsonl 里取 unit_id（按 setting_id == unit_filter_level 过滤）；
png_dir / ref 都是 Dropbox 上相对 dbx: 的路径（NAS 与 Dropbox 同构，已由备份保证）。
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import urllib.request

import numpy as np

RCLONE = os.path.expanduser("~/bin/rclone")
NAS_ROOT = "/mnt/qnap/chenmg93"


def dlink(path):
    """rclone link -> 直链（dl.dropboxusercontent.com，无 dl=0）。"""
    out = subprocess.run([RCLONE, "link", f"dbx:{path}"], capture_output=True, text=True, check=True).stdout.strip()
    return out.replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("&dl=0", "").replace("?dl=0", "")


def sb_post(url_base, key, table, rows, params=""):
    req = urllib.request.Request(
        f"{url_base}/rest/v1/{table}{params}", data=json.dumps(rows).encode(),
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json", "Prefer": "return=representation"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def units_of(spec):
    uids = []
    for f in sorted(glob.glob(os.path.join(NAS_ROOT, spec["units_glob_jsonl"]))):
        for line in open(f):
            r = json.loads(line)
            lev = r.get("setting_id") or r.get("level") or "none"
            if lev == spec.get("unit_filter_level", lev):
                uids.append(r["unit_id"])
    uids = sorted(set(uids))
    if len(uids) != 50:
        print(f"  [warn] {spec['model']}/{spec['task']}/{spec['level']}: {len(uids)} units (期望 50)")
    return uids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--k", type=int, default=5, help="每格抽几条（默认 5 = 1/10）")
    ap.add_argument("--dry", action="store_true", help="只打印抽样结果，不生成链接、不写库")
    a = ap.parse_args()

    specs = sorted(json.load(open(a.spec)), key=lambda s: (s["model"], s["task"], s["family"], s["level"]))
    rng = np.random.RandomState(a.seed)
    plan = []
    for s in specs:
        uids = units_of(s)
        pick = sorted(rng.choice(len(uids), size=min(a.k, len(uids)), replace=False).tolist())
        plan += [dict(spec=s, unit_id=uids[i]) for i in pick]
    print(f"{len(specs)} 格，共抽 {len(plan)} 张卡（seed={a.seed}, k={a.k}）")
    if a.dry:
        for p in plan[:20]:
            print("  ", p["spec"]["model"], p["spec"]["task"], p["spec"]["level"], p["unit_id"])
        return

    url, key = os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    rnd = sb_post(url, key, "rounds", [dict(name=a.name, master_seed=a.seed, frac=f"{a.k}/50")])[0]
    ref_cache = {}
    rows = []
    for n, p in enumerate(plan):
        s = p["spec"]
        img = dlink(f"{s['png_dir']}/{p['unit_id']}.png")
        ref = None
        if s.get("ref"):
            ref = ref_cache.get(s["ref"]) or dlink(s["ref"])
            ref_cache[s["ref"]] = ref
        rows.append(dict(round_id=rnd["id"], model=s["model"], task=s["task"], family=s["family"],
                         level=s["level"], unit_id=p["unit_id"], img_url=img, ref_url=ref,
                         question=s["question"], label_set=s["labels"], sort_key=n))
        if len(rows) == 100:
            sb_post(url, key, "cards", rows); rows = []
        if n % 50 == 0:
            print(f"  {n}/{len(plan)} 链接已生成", flush=True)
    if rows:
        sb_post(url, key, "cards", rows)
    print(f"完成：round '{a.name}' (id={rnd['id']})，{len(plan)} 张卡已入库。")


if __name__ == "__main__":
    sys.exit(main())

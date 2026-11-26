"""Create a round and insert its cards, or export a round's labels, addressing the round by NAME (not by id).

Card images live in the folder given by the manifest ("img_dir", e.g. cards/r5); every card row stores its own
img_url, so the database id of the round does not have to match the folder name.
Standard library only. The service key is read from the environment and never written anywhere.

  # dry run (checks only, writes nothing):
  SUPABASE_SERVICE_KEY=... python3 tools/round_by_name.py insert --manifest <manifest.json>
  # create the round and insert the cards (only after a clean dry run):
  SUPABASE_SERVICE_KEY=... python3 tools/round_by_name.py insert --manifest <manifest.json> --yes
  # read-only export (no emails; annotator = first 8 hex of sha256(user_id)):
  SUPABASE_SERVICE_KEY=... python3 tools/round_by_name.py export --name <round name> --out <file.json>

Manifest format (JSON):
  {"round_name": str, "seed": int, "frac": str (short description stored in rounds.frac), "img_dir": "cards/rN",
   "cards": [{"unit_id", "model", "task", "family", "level", "question", "labels": [...], "sort_key": int}, ...]}
Rows are inserted in sort_key order; if any insert fails, the new round is deleted again (cards cascade).
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def base_url():
    s = open(os.path.join(HERE, "config.js"), encoding="utf-8").read()
    return re.search(r'SUPABASE_URL:\s*"([^"]+)"', s).group(1).rstrip("/")


def req(url, key, method, path, body=None, prefer="return=representation"):
    r = urllib.request.Request(f"{url}/rest/v1/{path}", method=method,
                               data=None if body is None else json.dumps(body).encode(),
                               headers={"apikey": key, "Authorization": f"Bearer {key}",
                                        "Content-Type": "application/json", "Prefer": prefer})
    try:
        with urllib.request.urlopen(r, timeout=120) as f:
            t = f.read()
            return json.loads(t) if t else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} on {method} {path.split('?')[0]}: {e.read().decode(errors='replace')[:500]}")


def get_all(url, key, table, params):
    out, off, step = [], 0, 1000
    while True:
        q = urllib.parse.urlencode({**params, "limit": step, "offset": off})
        rows = req(url, key, "GET", f"{table}?{q}")
        out += rows
        if len(rows) < step:
            return out
        off += step


def check_manifest(M):
    cards, d = M["cards"], M["img_dir"].strip("/")
    probs = []
    ids = [c["unit_id"] for c in cards]
    if len(set(ids)) != len(ids):
        probs.append("duplicate unit_id in manifest")
    sk = [c["sort_key"] for c in cards]
    if sorted(sk) != list(range(len(cards))):
        probs.append("sort_key is not 0..n-1")
    miss = [u for u in ids if not os.path.exists(os.path.join(HERE, d, f"{u}.webp"))]
    extra = sorted(f for f in os.listdir(os.path.join(HERE, d)) if f.endswith(".webp") and f[:-5] not in set(ids)) \
        if os.path.isdir(os.path.join(HERE, d)) else []
    return probs, miss, extra


def cmd_insert(a, key):
    M = json.load(open(a.manifest, encoding="utf-8"))
    name, cards, d = M["round_name"], M["cards"], M["img_dir"].strip("/")
    url = base_url()
    probs, miss, extra = check_manifest(M)
    rounds = req(url, key, "GET", "rounds?select=id,name&order=id")
    print(f"existing rounds: {[(r['id'], r['name']) for r in rounds]}")
    print(f"round {name}: {len(cards)} cards; images in {d}: missing {len(miss)}, extra {len(extra)}; manifest problems: {probs or 'none'}")
    if any(r["name"] == name for r in rounds):
        print("STOP: a round with this name already exists; nothing written"); return 1
    if miss or extra or probs:
        print("STOP: manifest / image check failed; nothing written"); return 1
    if not a.yes:
        print("dry run only (add --yes to create the round and insert cards)"); return 0
    rnd = req(url, key, "POST", "rounds", [dict(name=name, master_seed=M["seed"], frac=M.get("frac", ""))])[0]
    rid = rnd["id"]
    rows = [dict(round_id=rid, model=c["model"], task=c["task"], family=c["family"], level=c["level"], unit_id=c["unit_id"],
                 img_url=f"{d}/{c['unit_id']}.webp", ref_url=None, question=c["question"], label_set=c["labels"],
                 sort_key=c["sort_key"]) for c in sorted(cards, key=lambda c: c["sort_key"])]
    try:
        for i in range(0, len(rows), 200):
            req(url, key, "POST", "cards", rows[i:i + 200], prefer="return=minimal")
        got = req(url, key, "GET", f"cards?select=id&round_id=eq.{rid}&limit=5000")
        if len(got) != len(rows):
            raise RuntimeError(f"read back {len(got)} cards, expected {len(rows)}")
    except Exception as e:
        req(url, key, "DELETE", f"rounds?id=eq.{rid}", prefer="return=minimal")
        print(f"STOP: insert failed ({e}); round {rid} deleted again (its cards cascade). Nothing is left behind."); return 1
    print(f"DONE: round {name} id={rid}, {len(rows)} cards inserted (read back {len(got)})")
    return 0


def cmd_export(a, key):
    url = base_url()
    rnd = get_all(url, key, "rounds", {"select": "id,name,master_seed,frac,note,created_at", "name": f"eq.{a.name}"})
    if not rnd:
        print(f"round {a.name} not found"); return 1
    rid = rnd[0]["id"]
    cards = get_all(url, key, "cards", {"select": "id,unit_id,task,sort_key", "round_id": f"eq.{rid}", "order": "id"})
    ids = [c["id"] for c in cards]
    ann = []
    for i in range(0, len(ids), 200):
        chunk = ",".join(map(str, ids[i:i + 200]))
        ann += get_all(url, key, "annotations", {"select": "card_id,user_id,label,note,updated_at", "card_id": f"in.({chunk})", "order": "id"})
    for x in ann:
        x["annotator"] = hashlib.sha256(x.pop("user_id").encode()).hexdigest()[:8]
    out = dict(exported_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               round=rnd[0], n_cards=len(cards), n_annotations=len(ann), cards=cards, annotations=ann)
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"round {rid} {a.name}: cards {len(cards)}, labelled cards {len({x['card_id'] for x in ann})}, "
          f"labels {len(ann)}, annotators {len({x['annotator'] for x in ann})} -> {a.out}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("insert"); p.add_argument("--manifest", required=True); p.add_argument("--yes", action="store_true")
    p = sp.add_parser("export"); p.add_argument("--name", required=True); p.add_argument("--out", required=True)
    a = ap.parse_args()
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not key:
        print("SUPABASE_SERVICE_KEY is not set"); return 1
    return cmd_insert(a, key) if a.cmd == "insert" else cmd_export(a, key)


if __name__ == "__main__":
    sys.exit(main())

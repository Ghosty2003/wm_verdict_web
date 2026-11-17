# WM-Verdict 标注站

给朋友 / 审稿人用的在线标注网站：GitHub Pages（静态前端）+ Supabase（登录与标注存储）+ Dropbox 直链（图床）。
每轮从每个（模型 × 任务 × 扰动档）的 50 个 unit 里按种子抽 **1/10（5 条）**，抽样种子入库备案。

## 架构

```
浏览器 ── GitHub Pages (index.html, 纯静态)
   │  supabase-js（anon key + RLS）
   ├── Supabase：Auth 登录（邮箱白名单）· rounds/cards/annotations 表
   └── Dropbox 直链：卡片图与参考图（dl.dropboxusercontent.com，<img> 热链）
```

- 标注权限由数据库 Row Level Security 控制：不在 `allowed_emails` 白名单的账号登录后什么都看不到。
- 每人每卡一条标注（可修改覆盖）；多人标同一卡，便于算标注者一致性（κ）。
- 卡片顺序、抽样、问题与标签集都由 `tools/make_round.py` 按 spec 生成，网页端不含任何口径逻辑。

## 一次性部署

1. **Supabase**：新建免费项目 → SQL Editor 整段执行 `supabase/schema.sql`
   → Table Editor 往 `allowed_emails` 里加受邀邮箱
   → （可选）Authentication → Providers → Email 关闭 "Confirm email" 可免邮箱验证。
2. **前端**：把 Settings → API 里的 Project URL 和 anon key 填进 `config.js`，push。
3. **GitHub Pages**：仓库 Settings → Pages → Source 选 `main` 分支 `/ (root)`，保存。
   网址：`https://ghosty2003.github.io/wm_verdict_web/`。

## 发一轮标注（在 NAS 上）

前提：结果图已由 Dropbox 备份同步（`dropbox_backup.sh`），`~/bin/rclone` 配好 `dbx:`。

```bash
export SUPABASE_URL=https://xxx.supabase.co
export SUPABASE_SERVICE_KEY=...   # service_role key，只在服务器上用，绝不写进本仓库
python tools/make_round.py --name round1_xxx --seed 20261115 --spec specs/round1.json --dry   # 先看抽样
python tools/make_round.py --name round1_xxx --seed 20261115 --spec specs/round1.json         # 正式入库
```

spec 文件格式见 `tools/make_round.py` 顶部注释（每格一条：unit 来源 jsonl、卡片图目录、参考图、问题、标签集）。

## 导出标注

Supabase SQL Editor：
```sql
select c.model, c.task, c.family, c.level, c.unit_id, a.email, a.label, a.note, a.updated_at
from annotations a join cards c on c.id = a.card_id
where c.round_id = <轮次id> order by c.sort_key, a.email;
```
或 Dashboard 直接导 CSV。导出后进 `agent_human_agreement.py` 的流程算一致性。

脚本导出（只读，不带邮箱，乐观率报告用）：`SUPABASE_SERVICE_KEY=... python3 tools/export_round_annotations.py --round-id 3 --out <文件>`。

## 页面流程（2026-11-16 起 v4：每档 5 组，不再按 seed 对齐）

- 一页 = 一个 任务×扰动档 的第 g 组（g = 1–5）：同一任务、同一扰动档，四个模型（LingBot-VA / OpenWAM-α / Cosmos Policy / UVA）各放一次自己的闭环运行，一个模型一行。各模型的初始条件 / 种子不要求相同，页面上也不显示 seed。
- 每行两区：REAL（闭环真实帧条，round 2 的卡）+ IMAGINED（想象末帧，round 3 的卡），按 unit_id 对应；想象帧只在与真实画面来自同一次运行时才放，否则标“无”、不出问题。
- 挑单元：每模型优先“齐全”的单元（真实画面 + 同一次运行的想象帧），v3 页上齐全的旧单元留在原组位置；凑不齐 5 个才用只有真实画面的补。规则见 select_pages.py 文件头。
- 页面表在 `data/samecase_pages.json`（哪页放哪几张卡），由 `wm_verdict/libero/out/annotation/samecase_20261115/` 的脚本生成：
  inventory.py（四模型逐单元盘点，标运行来源与是否齐全）→ select_pages.py（每格每模型挑 5 个，确定性排序）→ build_cards.py（出图 + 页面表 + 入库清单；LingBot latent 在 CPU 上解码）→ check_pages.py（抽页核对 + 全表同一运行核对）→ check_real_consistency.py（真实帧成败与记录一致）。
- v5（2026-11-17）：页面与 v4 相同，只给 351 个 Cosmos T2/T3 单元（页上已有 REAL 卡、IMAGINED 原为“无”）补上想象末帧：同一次原执行最后一次规划在原存档输入上的末窗重算（输入哈希一致；原 trace 里保存下来的动作片段逐值一致，多数单元原 episode 提前结束，只能核对已保存的前缀）。脚本 `v5_cosmos_imag.py`，统计 `v5_stats.json`。
- 导航：第一个下拉选 任务×档位，第二个选 Group 1–5；←/→ 在组间翻，翻到头接下一个档。进度条按问题数计。键盘 1–4 回答当前高亮（第一个未答）的问题。
- 新卡入库：`SUPABASE_SERVICE_KEY=... python3 tools/add_samecase_cards.py --manifest <manifest_samecase.json> [--yes]`，插入已有的 round 2 / round 3，库里已有的 unit_id 跳过（旧卡与旧标注不动）。
- 导出：`SUPABASE_SERVICE_KEY=... python3 tools/export_samecase.py --out <文件> [--cutoff <上线时刻>]`，同卷页标注与旧标注分两张表。
- 改版前的页面存档：`wm_verdict/libero/out/annotation/samecase_20261115/index_before_samecase_20261115.html`。

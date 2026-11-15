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

## 页面流程（2026-11-14 起三轮合并，全站一套流程）

- 一页 = 一个闭环单元（unit_id）。页面从上到下：参考图 → IMAGINED 区（round 3 想象末帧卡，只看想象画面本身作答）→ REAL 区（round 2 闭环真实帧条卡，问题照 round 2 原样）。两区同时可见、各自独立作答。
- 合页规则：同一 unit_id 在 round 2 和 round 3 都有卡 → 合成一页（两区）；只在 round 3 → 单独成页，只有 IMAGINED 区；只在 round 2 → 照旧，只有 REAL 区；round 1 的卡照旧单独成页。
- 答案仍按卡片写 `annotations`：IMAGINED 区记在 round 3 的卡上，REAL 区记在 round 2 的卡上；数据库结构和已有标注不变。
- 没有轮次下拉框；进度与“只看没做完的”按页计算，一页所有区都答完才算完成。键盘：上区 1–4，下区 5–8。

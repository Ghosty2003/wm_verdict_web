// Supabase 项目配置（anon key 是公开安全的，数据权限由数据库 RLS 控制）。
// 部署前把下面两行换成你 Supabase 项目 Settings -> API 里的值。
window.WMV_CONFIG = {
  SUPABASE_URL: "https://jrkbstpomsyyxfbpshmt.supabase.co",
  SUPABASE_ANON_KEY: "sb_publishable_tAPGEkCGEQ-LszK6YduWRA_PuTfmoI3",
  // true = 任何注册用户都能标注（数据库里也要执行 supabase/open_access.sql）；
  // false = 只有 allowed_emails 白名单内的邮箱能用。
  OPEN_ACCESS: true,
};

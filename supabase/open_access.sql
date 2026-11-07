-- 放开白名单：任何注册登录的用户都能看卡片、写标注。
-- 在 Supabase SQL Editor 执行本文件（可随时用下面注释里的语句改回白名单制）。
create or replace function is_allowed() returns boolean
language sql stable security definer set search_path = public as
$$ select true $$;

-- 改回白名单制时执行：
-- create or replace function is_allowed() returns boolean
-- language sql stable security definer set search_path = public as
-- $$ select exists(select 1 from allowed_emails where email = auth.jwt() ->> 'email') $$;

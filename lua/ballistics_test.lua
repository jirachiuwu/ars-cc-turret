-- 段0: ballistics.lua の純粋テスト（ゲーム不要・即回る）
-- design.md §3.6 準拠。命中判定: 弾の到達点と標的の未来位置が 0.5block 以内。
package.path = package.path .. ";./?.lua;" .. (arg and arg[0] and arg[0]:gsub("[^/\\]+$","") or "") .. "?.lua"
local b = require("ballistics")

local function sub(a,c) return {x=a.x-c.x,y=a.y-c.y,z=a.z-c.z} end
local function add(a,c) return {x=a.x+c.x,y=a.y+c.y,z=a.z+c.z} end
local function scale(a,k) return {x=a.x*k,y=a.y*k,z=a.z*k} end
local function len(a) return math.sqrt(a.x*a.x+a.y*a.y+a.z*a.z) end
local function norm(a) local l=len(a); return {x=a.x/l,y=a.y/l,z=a.z/l} end
-- setProjectileSpeed のクランプ相当（design §2.4: max(0.05, min(2.5, s))）
local function clampSpeed(s) return math.max(0.05, math.min(2.5, s)) end

local T = {x=0,y=0,z=0}
local pass, fail = 0, 0

-- 命中ケース: 弾を s*t だけ飛ばし、標的の未来位置と一致するか
local function hitCase(name, P, V, sRaw)
  local s = clampSpeed(sRaw)
  local aim, t = b.lead(T, P, V, s)
  if not aim then
    print(string.format("FAIL %-28s lead=nil (t=%s)", name, tostring(t))); fail = fail + 1; return
  end
  local bullet = add(T, scale(norm(sub(aim, T)), s * t))
  local target = add(P, scale(V, t))
  local err = len(sub(bullet, target))
  if err < 0.5 then
    print(string.format("PASS %-28s err=%.4f t=%.2f s=%.3f", name, err, t, s)); pass = pass + 1
  else
    print(string.format("FAIL %-28s err=%.4f (>=0.5) t=%.2f", name, err, t)); fail = fail + 1
  end
end

-- 逃走判定ケース: escapes() の真偽が期待通りか
local function escapeCase(name, P, V, sRaw, expect)
  local e = b.escapes(T, P, V, clampSpeed(sRaw))
  if e == expect then
    print(string.format("PASS %-28s escapes=%s", name, tostring(e))); pass = pass + 1
  else
    print(string.format("FAIL %-28s escapes=%s want=%s", name, tostring(e), tostring(expect))); fail = fail + 1
  end
end

-- 命中
hitCase("static",              {x=20,y=0,z=0},  {x=0,y=0,z=0},      1.5)
hitCase("crossing",            {x=20,y=0,z=0},  {x=0,y=0,z=1.0},    1.5)
hitCase("approach-diagonal",   {x=30,y=5,z=0},  {x=-0.5,y=0,z=0.5}, 2.0)
hitCase("receding-slow",       {x=15,y=0,z=2},  {x=0.4,y=0,z=0},    1.5)
hitCase("vertical-up",         {x=10,y=10,z=0}, {x=0,y=0.3,z=0},    1.5)
-- クランプ境界（design §3.6 監査medium）
-- 弾速下限0.05は射程が短い(maxT=200tick × 0.05 = 10block以内)。下限クランプ適用の検証は近距離で
hitCase("clamp-low 0.04->0.05",  {x=8,y=0,z=0},  {x=0,y=0,z=0},     0.04)
hitCase("clamp-high 3.0->2.5",   {x=15,y=0,z=0}, {x=0,y=0,z=0.3},   3.0)
-- 逃走(撃たない)判定
escapeCase("escaping V>s along LoS", {x=20,y=0,z=0}, {x=2.0,y=0,z=0}, 1.5, true)
escapeCase("not-escaping crossing",  {x=20,y=0,z=0}, {x=0,y=0,z=1.0}, 1.5, false)

print(string.format("\n=== %d passed, %d failed ===", pass, fail))
if fail > 0 then os.exit(1) end

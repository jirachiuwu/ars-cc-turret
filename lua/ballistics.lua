-- ballistics.lua — 偏差(リード)の反復解。純関数・ゲーム不要でテスト可。
-- 砲口 T、標的位置 P、標的速度 V、弾速 s（全て blocks/tick）。
-- design.md §3.2 準拠。単位は blocks/tick（秒ではない）。
local M = {}
local function sub(a,b) return {x=a.x-b.x,y=a.y-b.y,z=a.z-b.z} end
local function add(a,b) return {x=a.x+b.x,y=a.y+b.y,z=a.z+b.z} end
local function scale(a,k) return {x=a.x*k,y=a.y*k,z=a.z*k} end
local function len(a) return math.sqrt(a.x*a.x+a.y*a.y+a.z*a.z) end

-- 戻り: aimPoint(未来位置), t  /  解なし(NaN・射程外)は nil, t
-- A=加速度(任意)。未来位置 = P + V·t + 0.5·A·t²(2次予測=曲線運動対応)。A 省略で従来の等速直線。
function M.lead(T, P, V, s, opts, A)
  opts = opts or {}
  A = A or { x = 0, y = 0, z = 0 }
  local t = len(sub(P, T)) / s              -- 初期推定(標的静止扱い)
  for _ = 1, (opts.maxIter or 6) do
    local future = add(add(P, scale(V, t)), scale(A, 0.5 * t * t))
    local tNew = len(sub(future, T)) / s
    if math.abs(tNew - t) < (opts.eps or 0.01) then t = tNew; break end
    t = tNew
  end
  local future = add(add(P, scale(V, t)), scale(A, 0.5 * t * t))
  if t ~= t or t > (opts.maxT or 200) then return nil, t end  -- NaN/射程外ガード
  return future, t
end

-- 視線方向に弾速以上で逃げる標的を先に弾く(安い早期判定)
function M.escapes(T, P, V, s)
  local d = sub(P, T); local dl = len(d)
  if dl < 1e-6 then return false end
  return (V.x*d.x + V.y*d.y + V.z*d.z) / dl >= s
end

return M

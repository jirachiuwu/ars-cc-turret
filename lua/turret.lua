-- turret.lua — 追従ループ(状態機械)。design.md §3.4。
-- 頭脳は全部 Lua。Java(peripheral)は列挙・照準・発射の口だけ。Ctrl+T で停止。
local config     = require("config")
local targeting  = require("targeting")
local ballistics = require("ballistics")

-- peripheral 解決: modem名 → ダメなら型で find(直接隣接でも拾える)
local P = peripheral.wrap(config.name) or peripheral.find(config.type)
if not P then error("タレットが見つからない (name=" .. config.name .. " / type=" .. config.type .. ")") end

P.setProjectileSpeed(config.speed)     -- 偏差で使う弾速と実弾速を一致させる(命中の前提)
local lock, cooldown = nil, 0

while true do
  local T    = P.getMuzzle()
  local ents = P.listEntities(config.range)
  local tgt  = targeting.select(ents, T, config.filter, config.prio, lock)

  if not tgt then
    lock = nil                          -- 標的ロスト: 照準維持(再捕捉が速い)
  else
    lock = tgt.uuid
    local Pp = { x = tgt.x, y = tgt.y, z = tgt.z }
    local V  = { x = tgt.vx, y = tgt.vy, z = tgt.vz }
    local s  = P.getProjectileSpeed()   -- ★必ず Java クランプ後の真値を読む(config.speed 直読み禁止)
    local aimPt = (not ballistics.escapes(T, Pp, V, s)) and ballistics.lead(T, Pp, V, s, config.lead) or Pp
    if aimPt then                        -- 射程外/解なしで Pp にもならない時は撃たない
      P.aim(aimPt.x, aimPt.y, aimPt.z)   -- 毎ループ最新解で照準更新(固定して待たない)
      local err  = P.getAimError(aimPt.x - T.x, aimPt.y - T.y, aimPt.z - T.z)
      local cost = P.getSpellCost()
      local ok   = P.isLoaded() and (P.getCreative() or P.getSource() >= cost)  -- canFire を Lua で合成
      if err <= config.aimTolDeg and cooldown <= 0 and ok then
        if P.fire() then cooldown = config.fireCooldownTicks end
      end
    end
  end
  if cooldown > 0 then cooldown = cooldown - 1 end
  os.sleep(0.05)                         -- 約20Hz(server tick 同期)
end

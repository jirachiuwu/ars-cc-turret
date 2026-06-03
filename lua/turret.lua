-- turret.lua — 火器管制1ステップ(状態機械)。ループ/描画は main.lua、ここは純ロジック(lupaでテスト可)。
-- require しない: deps(ballistics)/tg(targeting)は引数で受ける = モック注入してテストできる。
local M = {}

local function short(t) return (tostring(t or "?")):gsub("^.-:", "") end  -- "minecraft:zombie" -> "zombie"

local function pushlog(s, line)
  s.log[#s.log + 1] = line
  while #s.log > s.logSize do table.remove(s.log, 1) end
end

function M.new(logSize)
  return { lock = nil, cooldown = 0, status = "IDLE", target = nil, sol = nil,
           log = {}, logSize = logSize or 9, shots = 0 }
end

-- 1tick分の火器管制。P=turret peripheral, cfg=設定, s=状態(破壊更新), deps=ballistics, tg=targeting。
function M.step(P, cfg, s, deps, tg)
  local T    = P.getMuzzle()
  local ents = P.listEntities(cfg.range)
  local prio = tg.priorities[cfg.priority] or tg.priorities.nearest
  local tgt  = tg.select(ents, T, cfg.filter, prio, s.lock)

  if not tgt then
    if s.status ~= "IDLE" then pushlog(s, "... target lost") end
    s.lock, s.status, s.target, s.sol = nil, "IDLE", nil, nil
    if s.cooldown > 0 then s.cooldown = s.cooldown - 1 end
    return s
  end

  local isNew = (not s.target) or s.target.uuid ~= tgt.uuid
  s.lock = tgt.uuid
  local Pp = { x = tgt.x, y = tgt.y + (tgt.height or 0) * 0.5, z = tgt.z }  -- 胴体中心
  local vy = (math.abs(tgt.vy) < 0.1) and 0 or tgt.vy                       -- 重力ノイズ無視
  local V  = { x = tgt.vx, y = vy, z = tgt.vz }
  local sp = P.getProjectileSpeed()                                        -- クランプ後の真値
  local esc = deps.escapes(T, Pp, V, sp)
  local aimPt, flight
  if esc then aimPt = Pp else aimPt, flight = deps.lead(T, Pp, V, sp, cfg.lead) end

  if isNew then pushlog(s, ("TRK %s d=%.1f"):format(short(tgt.type), tgt.distance)) end

  local fired, err = false, 999
  if aimPt then
    P.aim(aimPt.x, aimPt.y, aimPt.z)
    err = P.getAimError(aimPt.x - T.x, aimPt.y - T.y, aimPt.z - T.z)
    local ok = P.isLoaded() and (P.getCreative() or P.getSource() >= P.getSpellCost())
    if err <= cfg.aimTolDeg and s.cooldown <= 0 and ok and not esc then
      if P.fire() then
        s.cooldown, fired, s.shots = cfg.fireCooldownTicks, true, s.shots + 1
        pushlog(s, ("SOL %.0f,%.0f,%.0f t=%.0f e=%.1f"):format(aimPt.x, aimPt.y, aimPt.z, flight or 0, err))
        pushlog(s, (">> FIRE %s"):format(short(tgt.type)))
      end
    end
  end

  s.status = fired and "FIRING" or (esc and "ESCAPING" or "TRACKING")
  s.target = { type = tgt.type, distance = tgt.distance, closeSpeed = tgt.closeSpeed or 0, uuid = tgt.uuid }
  s.sol = { x = aimPt and aimPt.x, y = aimPt and aimPt.y, z = aimPt and aimPt.z,
            err = err, flight = flight, esc = esc }
  if s.cooldown > 0 then s.cooldown = s.cooldown - 1 end
  return s
end

return M

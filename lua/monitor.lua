-- monitor.lua — 火器管制ステーション GUI v2(design §12.6)。
-- 2枚=MAIN+CONFIG / 1枚=タブ式([MAIN|CONFIG]切替) / 0枚=ヘッドレス。
-- render系は {x1,x2,y,action} の領域表を返す → M.hit が同じ表で突合(描画と判定が一致)。
local M = {}

local STATUS_COLOR = {
  IDLE = colors.gray, TRACKING = colors.yellow, FIRING = colors.red, ESCAPING = colors.orange,
}

-- ===== 純ロジック(lupaでテスト可) =====

-- 数値設定の増減(範囲クランプ + 小数ドリフト対策で3桁丸め)
function M.clampStep(v, st, dir)
  v = v + dir * st.step
  if v < st.min then v = st.min end
  if v > st.max then v = st.max end
  return math.floor(v * 1000 + 0.5) / 1000
end

-- ボタン押下を設定へ適用(cfg破壊更新 + P反映 + settings永続)。ui.tab 切替もここ。
function M.applyAction(a, cfg, P, ui)
  if a.tab then ui.tab = a.tab; return end
  if a.cycleTarget then
    local modes, i = cfg.targetModes, 1
    for k, mn in ipairs(modes) do if mn == cfg.targetMode then i = k end end
    cfg.targetMode = modes[(i % #modes) + 1]; settings.set("turret.target", cfg.targetMode)
  elseif a.set == "priority" then
    cfg.priority = a.val; settings.set("turret.priority", a.val)
  elseif a.set == "creative" then
    cfg.creativeForce = a.val; P.setCreative(a.val); settings.set("turret.creative", a.val)
  elseif a.step == "speed" then
    cfg.speed = M.clampStep(cfg.speed, cfg.steps.speed, a.dir); P.setProjectileSpeed(cfg.speed); settings.set("turret.speed", cfg.speed)
  elseif a.step == "burst" then
    cfg.burst = M.clampStep(cfg.burst, cfg.steps.burst, a.dir); P.setBurst(cfg.burst); settings.set("turret.burst", cfg.burst)
  elseif a.step == "range" then
    cfg.range = M.clampStep(cfg.range, cfg.steps.range, a.dir); settings.set("turret.range", cfg.range)
  elseif a.step == "cooldown" then
    cfg.fireCooldownTicks = M.clampStep(cfg.fireCooldownTicks, cfg.steps.cooldown, a.dir); settings.set("turret.cooldown", cfg.fireCooldownTicks)
  elseif a.step == "aimTol" then
    cfg.aimTolDeg = M.clampStep(cfg.aimTolDeg, cfg.steps.aimTol, a.dir); settings.set("turret.aimtol", cfg.aimTolDeg)
  elseif a.step == "leadLag" then
    cfg.leadLag = M.clampStep(cfg.leadLag, cfg.steps.leadLag, a.dir); settings.set("turret.leadlag", cfg.leadLag)
  end
  settings.save(".turret")
end

-- (x,y)を領域表で突合 → action(無ければ nil)
function M.hit(regions, x, y)
  for _, r in ipairs(regions) do
    if y == r.y and x >= r.x1 and x <= r.x2 then return r.action end
  end
  return nil
end

-- モニター解決 → {mode="dual"|"single"|"none", main=, config=, single=} (各 {obj,name})
function M.resolve(cfg)
  local mons = { peripheral.find("monitor") }
  local named = {}
  for _, m in ipairs(mons) do named[#named + 1] = { obj = m, name = peripheral.getName(m) } end
  table.sort(named, function(a, b) return a.name < b.name end)
  if #named == 0 then return { mode = "none" } end
  local function byName(n) for _, e in ipairs(named) do if e.name == n then return e end end end
  if #named == 1 then return { mode = "single", single = named[1] } end
  local main = (cfg.mainMonitor and byName(cfg.mainMonitor)) or named[1]
  local config = cfg.configMonitor and byName(cfg.configMonitor)
  if not config or config.name == main.name then
    for _, e in ipairs(named) do if e.name ~= main.name then config = e; break end end
  end
  return { mode = "dual", main = main, config = config }
end

-- ===== 描画 =====

function M.setup(m, scale)
  m.setTextScale(scale or 0.5); m.setBackgroundColor(colors.black); m.clear()
end

-- 内容(needCols×needRows)が収まる最大の文字スケールを選ぶ。手動スケール当ては不要に。
function M.fitScale(m, needCols, needRows)
  for _, sc in ipairs({ 2, 1.5, 1, 0.75, 0.5 }) do
    m.setTextScale(sc)
    local w, h = m.getSize()
    if w >= needCols and h >= needRows then return sc end
  end
  return 0.5   -- どれも入らない: 最小(直前ループで0.5設定済み)
end

-- CONFIG用: 内容が収まる最大スケールに合わせてから初期化
function M.setupFit(m, needCols, needRows)
  M.fitScale(m, needCols, needRows)
  m.setBackgroundColor(colors.black); m.clear()
end

local function put(m, w, y, txt, fg, bg)
  m.setCursorPos(1, y)
  m.setTextColor(fg or colors.white); m.setBackgroundColor(bg or colors.black)
  m.write((txt .. string.rep(" ", w)):sub(1, w))
end

-- ボタン描画 + 領域記録。返り値=次のx
local function button(m, x, y, label, active, regions, action)
  local txt = " " .. label .. " "
  m.setCursorPos(x, y)
  m.setBackgroundColor(active and colors.green or colors.gray)
  m.setTextColor(active and colors.white or colors.lightGray)
  m.write(txt)
  m.setBackgroundColor(colors.black)
  regions[#regions + 1] = { x1 = x, x2 = x + #txt - 1, y = y, action = action }
  return x + #txt + 1
end

-- MAIN: 火器管制ライブ。top=内容開始行(既定1)。操作領域なし。
function M.renderMain(m, name, s, cfg, top)
  local oy = (top or 1) - 1
  local w, h = m.getSize()
  put(m, w, oy + 1, "== ARS-CC FIRE CONTROL ==", colors.cyan)
  put(m, w, oy + 2, "STATUS " .. s.status, STATUS_COLOR[s.status] or colors.white)
  if s.target then
    put(m, w, oy + 3, ("TGT  %s d=%.1f"):format((s.target.type:gsub("^.-:", "")), s.target.distance))
    put(m, w, oy + 4, ("CLOSE %+.2f b/t"):format(s.target.closeSpeed))
  else
    put(m, w, oy + 3, "TGT  --", colors.gray); put(m, w, oy + 4, "", colors.gray)
  end
  if s.sol and s.sol.x then
    put(m, w, oy + 5, ("LEAD %.0f,%.0f,%.0f"):format(s.sol.x, s.sol.y, s.sol.z), colors.lime)
    put(m, w, oy + 6, ("AIM  %.1f deg  t=%.0ft"):format(s.sol.err or 0, s.sol.flight or 0), colors.lime)
    -- 偏差の証拠: VEL=標的速度, LEADd=リード量(現在位置からのズレ)。VEL>0でLEADd>0なら偏差が効いてる。
    put(m, w, oy + 7, ("VEL %.2f  LEADd %.2f"):format(s.sol.vel or 0, s.sol.leadOff or 0), colors.orange)
  else
    put(m, w, oy + 5, "LEAD --", colors.gray); put(m, w, oy + 6, "", colors.gray); put(m, w, oy + 7, "", colors.gray)
  end
  put(m, w, oy + 8, "------- fire log -------", colors.gray)
  local startY, n = oy + 9, #s.log
  local rows = h - startY            -- 最下行(h)はフッタ
  for i = 1, rows do
    local li = n - rows + i
    put(m, w, startY + i - 1, (li >= 1 and s.log[li]) or "", colors.lightGray)
  end
  put(m, w, h, ("%s  shots %.0f"):format(name, s.shots), colors.gray)
  return {}
end

-- CONFIG: 設定ボタン。領域表を返す。top=内容開始行(既定1)。
function M.renderConfig(m, name, cfg, top)
  local oy = (top or 1) - 1
  local w, h = m.getSize()
  local R = {}
  put(m, w, oy + 1, "==== ARS-CC CONFIG ====", colors.cyan)
  put(m, w, oy + 2, "TARGET", colors.white)
  button(m, 9, oy + 2, cfg.targetMode, true, R, { cycleTarget = true })   -- タップで巡回(hostile/mobs/all/players)
  put(m, w, oy + 4, "PRIORITY", colors.white)
  local x = button(m, 1, oy + 5, "nearest", cfg.priority == "nearest", R, { set = "priority", val = "nearest" })
  button(m, x, oy + 5, "fastestClose", cfg.priority == "fastestClose", R, { set = "priority", val = "fastestClose" })
  put(m, w, oy + 7, "CREATIVE", colors.white)
  x = button(m, 1, oy + 8, "OFF", not cfg.creativeForce, R, { set = "creative", val = false })
  button(m, x, oy + 8, "ON", cfg.creativeForce, R, { set = "creative", val = true })
  local function numrow(ry, label, val, kind)
    put(m, w, ry, label, colors.white)
    button(m, 10, ry, "-", false, R, { step = kind, dir = -1 })
    m.setCursorPos(14, ry); m.setTextColor(colors.white); m.setBackgroundColor(colors.black); m.write(val)
    button(m, 19, ry, "+", false, R, { step = kind, dir = 1 })
  end
  numrow(oy + 10, "SPEED",  ("%.2f"):format(cfg.speed),             "speed")
  numrow(oy + 11, "BURST",  ("%.0f"):format(cfg.burst),            "burst")
  numrow(oy + 12, "RANGE",  ("%.0f"):format(cfg.range),             "range")
  numrow(oy + 13, "COOLDN", ("%.0f"):format(cfg.fireCooldownTicks), "cooldown")
  numrow(oy + 14, "AIMTOL", ("%.1f"):format(cfg.aimTolDeg),         "aimTol")
  numrow(oy + 15, "LAG",    ("%.1f"):format(cfg.leadLag),           "leadLag")
  put(m, w, h, ("%s  [CONFIG]"):format(name), colors.gray)
  return R
end

-- 単画面: 行1に [MAIN|CONFIG] 切替 → 行2以降に内容。領域表を返す。
function M.renderSingle(m, name, s, cfg, ui)
  local w = (m.getSize())
  local R = {}
  local x = button(m, 1, 1, "MAIN", ui.tab == "MAIN", R, { tab = "MAIN" })
  button(m, x, 1, "CONFIG", ui.tab == "CONFIG", R, { tab = "CONFIG" })
  put(m, w, 2, string.rep("-", w), colors.gray)
  local R2 = (ui.tab == "CONFIG") and M.renderConfig(m, name, cfg, 3) or M.renderMain(m, name, s, cfg, 3)
  for _, r in ipairs(R2) do R[#R + 1] = r end
  return R
end

return M

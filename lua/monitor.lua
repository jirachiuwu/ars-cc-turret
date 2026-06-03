-- monitor.lua — 火器管制モニター。fast refresh、タップで設定切替。CC グローバル(peripheral/colors/settings)を使う。
local M = {}

local STATUS_COLOR = {
  IDLE = colors.gray, TRACKING = colors.yellow, FIRING = colors.red, ESCAPING = colors.orange,
}

function M.attach()
  local m = peripheral.find("monitor")
  if not m then return nil end
  m.setTextScale(0.5)
  m.setBackgroundColor(colors.black)
  m.clear()
  return m
end

-- パディングで上書き描画(全消去しない=20Hzでもちらつかない)
local function put(m, w, y, txt, fg)
  m.setCursorPos(1, y)
  m.setTextColor(fg or colors.white)
  m.write((txt .. string.rep(" ", w)):sub(1, w))
end

function M.render(m, s, cfg)
  local w, h = m.getSize()
  put(m, w, 1, "== ARS-CC FIRE CONTROL ==", colors.cyan)
  put(m, w, 2, "STATUS " .. s.status, STATUS_COLOR[s.status] or colors.white)
  if s.target then
    put(m, w, 3, ("TGT  %s d=%.1f"):format((s.target.type:gsub("^.-:", "")), s.target.distance), colors.white)
    put(m, w, 4, ("CLOSE %+.2f b/t"):format(s.target.closeSpeed), colors.white)
  else
    put(m, w, 3, "TGT  --", colors.gray); put(m, w, 4, "", colors.gray)
  end
  if s.sol and s.sol.x then
    put(m, w, 5, ("LEAD %.0f,%.0f,%.0f"):format(s.sol.x, s.sol.y, s.sol.z), colors.lime)
    put(m, w, 6, ("AIM  %.1f deg  t=%.0ft"):format(s.sol.err or 0, s.sol.flight or 0), colors.lime)
  else
    put(m, w, 5, "LEAD --", colors.gray); put(m, w, 6, "", colors.gray)
  end
  put(m, w, 7, string.rep("-", w), colors.gray)
  -- 設定ボタン(行で判定: 8=PRIO, 9=CRE)
  put(m, w, 8, "[PRIO] " .. cfg.priority, colors.orange)
  put(m, w, 9, ("[CRE] %s   SPD %.2f  RNG %.0f"):format(tostring(cfg.creativeForce), cfg.speed, cfg.range), colors.orange)
  put(m, w, 10, ("shots %.0f"):format(s.shots), colors.gray)
  put(m, w, 11, "------- fire log -------", colors.gray)
  -- ログ(残り行に最新を詰める)
  local startY = 12
  local rows = h - startY + 1
  local n = #s.log
  for i = 1, rows do
    local li = n - rows + i
    put(m, w, startY + i - 1, (li >= 1 and s.log[li]) or "", colors.lightGray)
  end
end

-- タップ: 行8=優先順位トグル, 行9=creativeトグル。settings に永続化。
function M.onTouch(m, x, y, cfg, P)
  if y == 8 then
    cfg.priority = (cfg.priority == "nearest") and "fastestClose" or "nearest"
    settings.set("turret.priority", cfg.priority)
  elseif y == 9 then
    cfg.creativeForce = not cfg.creativeForce
    P.setCreative(cfg.creativeForce)
    settings.set("turret.creative", cfg.creativeForce)
  else
    return false
  end
  settings.save(".turret")
  return true
end

return M

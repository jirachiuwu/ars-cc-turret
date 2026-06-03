-- main.lua — エントリ。設定読込(config+settings)→周辺機器/モニター解決→制御+描画+タッチを並行実行。
-- 実行: コンピュータで `main`。停止: Ctrl+T。
local config     = require("config")
local targeting  = require("targeting")
local ballistics = require("ballistics")
local turret     = require("turret")
local monitor    = require("monitor")

-- 設定: config 既定 + settings(.turret) 永続上書き
settings.load(".turret")
local cfg = {}
for k, v in pairs(config) do cfg[k] = v end
cfg.priority          = settings.get("turret.priority", config.priority)
cfg.targetMode        = settings.get("turret.target", config.targetMode)
cfg.creativeForce     = settings.get("turret.creative", config.creativeForce)
cfg.speed             = settings.get("turret.speed", config.speed)
cfg.burst             = settings.get("turret.burst", config.burst)
cfg.range             = settings.get("turret.range", config.range)
cfg.fireCooldownTicks = settings.get("turret.cooldown", config.fireCooldownTicks)
cfg.aimTolDeg         = settings.get("turret.aimtol", config.aimTolDeg)
cfg.leadLag           = settings.get("turret.leadlag", config.leadLag)

-- タレット解決: modem名 → ダメなら型で find
local P = peripheral.wrap(config.name) or peripheral.find(config.type)
if not P then error("turret not found (name=" .. config.name .. " type=" .. config.type .. ")") end
P.setProjectileSpeed(cfg.speed)
P.setBurst(cfg.burst)
if cfg.creativeForce then P.setCreative(true) end

-- モニター解決(2枚=MAIN+CONFIG / 1枚=タブ / 0枚=ヘッドレス)
local mons = monitor.resolve(cfg)
if mons.mode == "dual" then
  monitor.setupFit(mons.main.obj, 26, 14)        -- MAIN も自動サイズ(パネルが読める最大スケール、ログは残りを埋める)
  monitor.setupFit(mons.config.obj, 22, 17)      -- CONFIG は内容が収まる最大スケールに自動調整
elseif mons.mode == "single" then
  monitor.setupFit(mons.single.obj, 26, 16)
end

local state = turret.new(config.logSize)
local ui = { tab = "MAIN" }
local regionsByName = {}   -- monitor名 → 領域表(タッチ突合用)

local function control()
  local prevClock = os.clock()
  while true do
    local nowC = os.clock()
    -- 実測ループ周期[game tick]を EMA で平滑(瞬間値の jitter=「たまに先撃ち」を除去。複数の時刻情報から総合)
    state.loopLag = state.loopLag * 0.8 + ((nowC - prevClock) * 20) * 0.2
    prevClock = nowC
    turret.step(P, cfg, state, ballistics, targeting)
    if mons.mode == "dual" then
      regionsByName[mons.main.name]   = monitor.renderMain(mons.main.obj, mons.main.name, state, cfg)
      regionsByName[mons.config.name] = monitor.renderConfig(mons.config.obj, mons.config.name, cfg)
    elseif mons.mode == "single" then
      regionsByName[mons.single.name] = monitor.renderSingle(mons.single.obj, mons.single.name, state, cfg, ui)
    end
    os.sleep(cfg.updateInterval)
  end
end

local function touch()
  if mons.mode == "none" then while true do os.sleep(1) end end
  while true do
    local _, mname, x, y = os.pullEvent("monitor_touch")
    local regs = regionsByName[mname]
    if regs then
      local a = monitor.hit(regs, x, y)
      if a then monitor.applyAction(a, cfg, P, ui) end
    end
  end
end

print("ARS-CC turret online. priority=" .. cfg.priority .. "  monitors=" .. mons.mode)
print("Ctrl+T to stop.")
parallel.waitForAny(control, touch)

-- main.lua — エントリ。設定読込(config+settings)→周辺機器解決→制御ループ＋モニター＋タップを並行実行。
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
cfg.priority      = settings.get("turret.priority", config.priority)
cfg.creativeForce = settings.get("turret.creative", config.creativeForce)
cfg.speed         = settings.get("turret.speed", config.speed)
cfg.range         = settings.get("turret.range", config.range)

-- タレット解決: modem名 → ダメなら型で find(直接隣接でも拾う)
local P = peripheral.wrap(config.name) or peripheral.find(config.type)
if not P then error("turret not found (name=" .. config.name .. " type=" .. config.type .. ")") end
P.setProjectileSpeed(cfg.speed)
if cfg.creativeForce then P.setCreative(true) end

local mon   = monitor.attach()
local state = turret.new(config.logSize)

local function control()
  while true do
    turret.step(P, cfg, state, ballistics, targeting)
    if mon then monitor.render(mon, state, cfg) end
    os.sleep(cfg.updateInterval)
  end
end

local function touch()
  if not mon then while true do os.sleep(1) end end   -- モニター無し: 何もしない
  while true do
    local _, _, x, y = os.pullEvent("monitor_touch")
    monitor.onTouch(mon, x, y, cfg, P)
  end
end

print("ARS-CC turret online. priority=" .. cfg.priority .. (mon and "  [monitor]" or "  [no monitor]"))
print("Ctrl+T to stop.")
parallel.waitForAny(control, touch)

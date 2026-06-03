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

-- タレット解決: modem名 → ダメなら型で find
local P = peripheral.wrap(config.name) or peripheral.find(config.type)
if not P then error("turret not found (name=" .. config.name .. " type=" .. config.type .. ")") end
P.setProjectileSpeed(cfg.speed)
P.setBurst(cfg.burst)
if cfg.creativeForce then P.setCreative(true) end

-- モニター解決(2枚=MAIN+CONFIG / 1枚=タブ / 0枚=ヘッドレス)
local mons = monitor.resolve(cfg)
if mons.mode == "dual" then
  monitor.setup(mons.main.obj, 0.5)     -- MAIN は情報密度優先で小さめ
  monitor.setup(mons.config.obj, 0.75)  -- CONFIG は項目数とサイズのバランスで 0.75
elseif mons.mode == "single" then
  monitor.setup(mons.single.obj, 0.5)
end

local state = turret.new(config.logSize)
local ui = { tab = "MAIN" }
local regionsByName = {}   -- monitor名 → 領域表(タッチ突合用)

local function control()
  while true do
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

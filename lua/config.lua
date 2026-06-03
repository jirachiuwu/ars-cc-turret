-- config.lua — 既定値。実行時に変えたいものは settings(.turret)で上書き(main.lua)。
return {
  type = "ars_cc_turret",      -- peripheral.find 用。直接隣接でも modem 経由でも拾える
  name = "ars_cc_turret_0",    -- modem ネットワーク名(あれば優先)。無ければ type で find
  range = 30,
  speed = 1.5,                 -- blocks/tick。setProjectileSpeed への入力。偏差は getProjectileSpeed() を読む
  aimTolDeg = 2.0,             -- 収束ゲート[度]
  fireCooldownTicks = 5,       -- 連射間隔[tick]
  lead = { maxIter = 6, eps = 0.01, maxT = 200 },
  filter = function(e) return not e.isPlayer and e.isAlive and e.los end,  -- 非プレイヤー生存+視線あり
  priority = "fastestClose",   -- "nearest" | "fastestClose"。モニタータップで実行時切替
  creativeForce = false,       -- 起動時に setCreative(true) するか(マナ源無しでも撃つ)
  updateInterval = 0.05,       -- 制御+モニター更新[s]。0.05=20Hz(速い)
  logSize = 9,                 -- 火器管制ログの保持行数

  -- モニター役割(nil=接続名のソート順で自動: monitor_0=MAIN, monitor_1=CONFIG)。名前で上書き可。
  mainMonitor = nil,
  configMonitor = nil,
  -- CONFIG 画面の数値ボタンの刻み・範囲
  steps = {
    speed    = { step = 0.25, min = 0.05, max = 2.5 },
    range    = { step = 5,    min = 5,    max = 64 },
    cooldown = { step = 1,    min = 1,    max = 40 },
    aimTol   = { step = 0.5,  min = 0.5,  max = 10 },
  },
}

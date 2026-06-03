-- config.lua — 既定値。実行時に変えたいものは settings(.turret)で上書き(main.lua)。
return {
  type = "ars_cc_turret",      -- peripheral.find 用。直接隣接でも modem 経由でも拾える
  name = "ars_cc_turret_0",    -- modem ネットワーク名(あれば優先)。無ければ type で find
  range = 30,
  speed = 1.5,                 -- blocks/tick。setProjectileSpeed への入力。偏差は getProjectileSpeed() を読む
  burst = 1,                   -- 1トリガーで撃つ弾数(弾幕)。Nが増えるほど自動で扇状に拡散。1=厳密命中
  aimTolDeg = 2.0,             -- 収束ゲート[度]
  leadLag = 1.0,               -- 遅延補償の基本分[tick](spawn等)。実測ループ周期が自動で加算される。残像撃ちの微調整用
  fireCooldownTicks = 5,       -- 連射間隔[tick]
  lead = { maxIter = 6, eps = 0.01, maxT = 200 },
  targetMode = "hostile",      -- 狙う対象。CONFIG の TARGET タップで巡回切替。下の targetModes 順
  targetModes = { "hostile", "mobs", "all", "players" },  -- 敵対のみ/非プレイヤー生物/全部/プレイヤーのみ
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
    burst    = { step = 1,    min = 1,    max = 10 },
    leadLag  = { step = 0.5,  min = 0,    max = 6 },
  },
}

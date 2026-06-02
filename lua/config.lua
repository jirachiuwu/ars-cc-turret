-- config.lua — 運用パラメータ。design.md §3.5。
return {
  type = "ars_cc_turret",      -- peripheral.find 用の型名。直接隣接でも modem 経由でも拾える
  name = "ars_cc_turret_0",    -- modem ネットワーク名(あれば優先)。無ければ type で find にフォールバック
  range = 30,
  speed = 1.5,                 -- blocks/tick。setProjectileSpeed への入力。偏差は getProjectileSpeed() の戻りを読む
  aimTolDeg = 2.0,             -- 収束ゲート[度]。getAimError がこの値以内で発射
  fireCooldownTicks = 5,       -- 連射間隔[tick]
  lead = { maxIter = 6, eps = 0.01, maxT = 200 },
  filter = function(e) return not e.isPlayer and e.isAlive end,  -- 既定:非プレイヤー生存
  prio = require("targeting").priorities.nearest,
}

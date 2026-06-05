-- ballistics.lua — 偏差(リード)の反復解。純関数・ゲーム不要でテスト可。
-- 砲口 T、標的位置 P、標的速度 V、弾速 s（全て blocks/tick）。
-- design.md §3.2 準拠。単位は blocks/tick（秒ではない）。
local M = {}
-- Lua 5.1/5.2: math.atan2(y,x), Lua 5.3+: math.atan(y,x)。CC=5.1, lupa=5.5 両対応。
local atan2 = math.atan2 or math.atan
local function sub(a,b) return {x=a.x-b.x,y=a.y-b.y,z=a.z-b.z} end
local function add(a,b) return {x=a.x+b.x,y=a.y+b.y,z=a.z+b.z} end
local function scale(a,k) return {x=a.x*k,y=a.y*k,z=a.z*k} end
local function len(a) return math.sqrt(a.x*a.x+a.y*a.y+a.z*a.z) end

-- 戻り: aimPoint(未来位置), t  /  解なし(NaN・射程外)は nil, t
-- A=加速度(任意・§12.18で実質撤回=常0、引数は後方互換で残す)。
-- omega=水平面の角速度[rad/tick](任意・§12.19 CTモデル)。|omega|>omegaEps で等角速度旋回予測、それ以下でCVに自動フォールバック。
-- dtCenter=「P/V のサンプル中央時刻」と「現在時刻」の差[tick](任意・既定0)。線形最小二乗の V は中央時刻の接線速度なので、CT予測ではこの分の時刻補正が必須(これを入れないとCT予測の中心が真旋回中心からズレる)。Pには「中央時刻の位置=lsq標本平均」を渡すのが整合的。
-- omegaTMax=|ω·t|の上限[rad](任意・既定π/4≈45°)。§12.20: 実エリトラがCT前提(等速・等ω)を満たさないため ω推定が暴れて ω·t_flight が大きくなりすぎ「半周回った真逆」を撃つ事故を防ぐ。閾値を超えたら角度だけクランプ(半径rは ω/v 由来のまま)。
-- 未来位置: |omega|<=ε なら P+V·t+0.5·A·t² / |omega|>ε なら水平=円弧式(角度クランプ込)・垂直=V.y·t。tはサンプル中央時刻からの経過なので飛翔時間 + dtCenter。
function M.lead(T, P, V, s, opts, A, omega, omegaEps, dtCenter, omegaTMax)
  opts = opts or {}
  A = A or { x = 0, y = 0, z = 0 }
  omega = omega or 0
  omegaEps = omegaEps or 0.005
  dtCenter = dtCenter or 0
  omegaTMax = omegaTMax or (math.pi / 4)         -- §12.20 既定: π/4=45°(半周予測を物理的に禁止)
  local useCT = math.abs(omega) > omegaEps
  local heading, r
  if useCT then
    heading = atan2(V.z, V.x)                     -- 水平面の進行方向(Lua版互換: 上のローカル参照)
    local vh = math.sqrt(V.x * V.x + V.z * V.z)
    r = vh / omega                                -- 符号付き旋回半径(ω>0=反時計回り)
  end
  -- tFlight=現在からの弾飛翔時間。CT式は「中央時刻からの経過」で展開するので te = tFlight + dtCenter。
  -- CV式は線形なので dtCenter を直接織り込み(P が中央時刻位置なら V·(t+dtCenter)=現在からt後の位置)。
  local function predict(tFlight)
    local te = tFlight + dtCenter
    if useCT then
      -- §12.20 ω·t クランプ: |ω·te| が omegaTMax を超えたら角度だけ上限値に止める(半径はそのまま=同じ弧上の途中で予測終了)
      local omegaT = omega * te
      if math.abs(omegaT) > omegaTMax then
        omegaT = (omegaT > 0) and omegaTMax or -omegaTMax
      end
      local phi = heading + omegaT
      -- 微分(d/dt_e)すると (v·cos(φ), v·sin(φ)) = 接線速度に一致。ω→0 で v·te に収束(連続)。
      return {
        x = P.x + r * (math.sin(phi) - math.sin(heading)),
        y = P.y + V.y * te,                       -- 垂直はCV(初版非対応・§12.19)
        z = P.z - r * (math.cos(phi) - math.cos(heading)),
      }
    else
      return add(add(P, scale(V, te)), scale(A, 0.5 * te * te))
    end
  end
  local t = len(sub(P, T)) / s                    -- 初期推定(標的静止扱い)
  for _ = 1, (opts.maxIter or 6) do
    local future = predict(t)
    local tNew = len(sub(future, T)) / s
    if math.abs(tNew - t) < (opts.eps or 0.01) then t = tNew; break end
    t = tNew
  end
  local future = predict(t)
  if t ~= t or t > (opts.maxT or 200) then return nil, t end  -- NaN/射程外ガード
  return future, t
end

-- 視線方向に弾速以上で逃げる標的を先に弾く(安い早期判定)
function M.escapes(T, P, V, s)
  local d = sub(P, T); local dl = len(d)
  if dl < 1e-6 then return false end
  return (V.x*d.x + V.y*d.y + V.z*d.z) / dl >= s
end

return M

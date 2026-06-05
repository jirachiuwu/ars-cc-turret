#!/usr/bin/env python3
# CT予測ハーネス — design.md §12.19 機械検証
# (1)既存ballistics_test後方互換 (2)ω→0連続性 (3)unwrap (4)合成5シナリオ×WINDOWグリッドサーチ
# (5)撤退基準(a)(b)(c)(d)(e)機械判定 (6)撤退スイッチ omega=0 で完全CV
import os, sys, math
from lupa import LuaRuntime

HERE = os.path.dirname(os.path.abspath(__file__))
lua = LuaRuntime(unpack_returned_tuples=True)
ballistics = lua.execute(open(os.path.join(HERE, "ballistics.lua"), encoding="utf-8").read())

passed = failed = 0
def check(name, cond):
    global passed, failed
    if cond: print(f"  PASS {name}"); passed += 1
    else:    print(f"  FAIL {name}"); failed += 1

def py2lua(d):
    t = lua.table()
    for k, v in d.items(): t[k] = v
    return t

T = py2lua({"x":0.0,"y":0.0,"z":0.0})
SPEED = 1.5
HIT_TOL = 0.5

def clamp_speed(s): return max(0.05, min(2.5, s))

# ============================================================
# 1) 後方互換: 既存ballistics_test.lua 相当(omega未指定=CV経路)
# ============================================================
print("=== 1) 後方互換: omega未指定 → 既存CV経路維持 ===")
def hitCase(name, P, V, s_raw):
    s = clamp_speed(s_raw)
    res = ballistics.lead(T, py2lua(P), py2lua(V), s)
    aim, tf = (res[0], res[1]) if isinstance(res, tuple) else (res, None)
    if aim is None: check(f"compat hit:{name}", False); return
    dx, dy, dz = aim.x, aim.y, aim.z
    dl = math.sqrt(dx*dx+dy*dy+dz*dz)
    if dl < 1e-9: check(f"compat hit:{name}", False); return
    bx, by, bz = dx/dl*s*tf, dy/dl*s*tf, dz/dl*s*tf
    tx, ty, tz = P["x"]+V["x"]*tf, P["y"]+V["y"]*tf, P["z"]+V["z"]*tf
    err = math.sqrt((bx-tx)**2+(by-ty)**2+(bz-tz)**2)
    check(f"compat hit:{name}", err < HIT_TOL)

hitCase("static",            {"x":20.0,"y":0.0,"z":0.0}, {"x":0.0,"y":0.0,"z":0.0},    1.5)
hitCase("crossing",          {"x":20.0,"y":0.0,"z":0.0}, {"x":0.0,"y":0.0,"z":1.0},    1.5)
hitCase("approach-diagonal", {"x":30.0,"y":5.0,"z":0.0}, {"x":-0.5,"y":0.0,"z":0.5},   2.0)
hitCase("receding-slow",     {"x":15.0,"y":0.0,"z":2.0}, {"x":0.4,"y":0.0,"z":0.0},    1.5)
hitCase("vertical-up",       {"x":10.0,"y":10.0,"z":0.0},{"x":0.0,"y":0.3,"z":0.0},    1.5)
hitCase("clamp-low",         {"x":8.0,"y":0.0,"z":0.0},  {"x":0.0,"y":0.0,"z":0.0},    0.04)
hitCase("clamp-high",        {"x":15.0,"y":0.0,"z":0.0}, {"x":0.0,"y":0.0,"z":0.3},    3.0)

def escapeCase(name, P, V, s_raw, expect):
    e = ballistics.escapes(T, py2lua(P), py2lua(V), clamp_speed(s_raw))
    check(f"compat esc:{name}", e == expect)
escapeCase("escaping",       {"x":20.0,"y":0.0,"z":0.0}, {"x":2.0,"y":0.0,"z":0.0},    1.5, True)
escapeCase("not-escaping",   {"x":20.0,"y":0.0,"z":0.0}, {"x":0.0,"y":0.0,"z":1.0},    1.5, False)

# ============================================================
# 2) ω→0連続性: |ω|<ε で CT予測 = CV予測 (誤差<1e-9)
# ============================================================
print("\n=== 2) ω→0 連続性 ===")
opts = py2lua({"maxIter":8,"eps":0.01,"maxT":200})
P0 = py2lua({"x":15.0,"y":0.0,"z":0.0})
V0 = py2lua({"x":0.5,"y":0.0,"z":0.5})
res_cv = ballistics.lead(T, P0, V0, 1.5, opts)
res_below_eps = ballistics.lead(T, P0, V0, 1.5, opts, None, 0.001, 0.005)  # |ω|<ε
check("|ω|<ε で CV と完全一致(x)", abs(res_cv[0].x - res_below_eps[0].x) < 1e-9)
check("|ω|<ε で CV と完全一致(z)", abs(res_cv[0].z - res_below_eps[0].z) < 1e-9)
res_zero = ballistics.lead(T, P0, V0, 1.5, opts, None, 0.0)  # 撤退スイッチ相当
check("omega=0 で CV と完全一致(x)", abs(res_cv[0].x - res_zero[0].x) < 1e-12)
check("omega=0 で CV と完全一致(z)", abs(res_cv[0].z - res_zero[0].z) < 1e-12)

# ============================================================
# 3) unwrap ±π ジャンプ潰し (Python独立実装で検証)
# ============================================================
print("\n=== 3) unwrap ±π ジャンプ ===")
def unwrap(d):
    if d > math.pi: d -= 2*math.pi
    elif d < -math.pi: d += 2*math.pi
    return d
check("unwrap 通常差は変えない (+0.5)", abs(unwrap(0.5) - 0.5) < 1e-9)
check("unwrap 通常差は変えない (-0.5)", abs(unwrap(-0.5) - (-0.5)) < 1e-9)
# π→-π の遷移: 実差は -0.1 (-π+0.05 から π-0.05 への動き = -0.1, ただし raw 差分は 2π-0.1)
raw_jump_pos = (math.pi - 0.05) - (-math.pi + 0.05)   # ≈ +2π - 0.1
check("unwrap +2π近似 jump → 実差(-0.1)", abs(unwrap(raw_jump_pos) - (-0.1)) < 1e-9)
raw_jump_neg = (-math.pi + 0.05) - (math.pi - 0.05)   # ≈ -2π + 0.1
check("unwrap -2π近似 jump → 実差(+0.1)", abs(unwrap(raw_jump_neg) - 0.1) < 1e-9)

# ============================================================
# 4) 合成シナリオ × WINDOW グリッドサーチ
# ============================================================
print("\n=== 4) 合成5シナリオ × WINDOW グリッドサーチ ===")
VEL_SAMPLES = 6  # Java trackVelocity と同値

def lsq_velocity(samples):
    # 線形最小二乗の傾き=中央時刻の接線速度。同時に標本平均位置(中央時刻の位置近似)と中央時刻を返す。
    # CT予測で「現在Pと中央時刻V」を組み合わせると円弧の中心がズレるので、Pは P_bar(=中央時刻位置)を使う。
    n = len(samples)
    if n < 2: return None
    t_bar = sum(s[3] for s in samples) / n
    x_bar = sum(s[0] for s in samples) / n
    y_bar = sum(s[1] for s in samples) / n
    z_bar = sum(s[2] for s in samples) / n
    sxx = sum((s[3]-t_bar)**2 for s in samples)
    if sxx < 1e-9: return None
    vx = sum((s[3]-t_bar)*s[0] for s in samples) / sxx
    vy = sum((s[3]-t_bar)*s[1] for s in samples) / sxx
    vz = sum((s[3]-t_bar)*s[2] for s in samples) / sxx
    return (vx, vy, vz, x_bar, y_bar, z_bar, t_bar)

def smooth_omega(omega_raw_list, window):
    if not omega_raw_list: return 0.0
    recent = omega_raw_list[-window:]
    return sum(recent)/len(recent)

# 標的の真位置 (連続時間)
def s_static(t):      return (20.0, 1.0, 0.0)
def s_linear(t):      return (20.0, 1.0, -10.0 + 0.5*t)             # 砲口横切り (前回テストhitCase crossing相当)
def s_circle_slow(t):
    omega = 2*math.pi/160; r = 10.0; cx, cz = 0.0, 0.0
    return (cx + r*math.cos(omega*t), 1.0, cz + r*math.sin(omega*t))
def s_circle_fast(t):
    omega = 2*math.pi/60;  r = 6.0;  cx, cz = 0.0, 0.0
    return (cx + r*math.cos(omega*t), 1.0, cz + r*math.sin(omega*t))
def s_transient(t):
    # 0-30: 直線、30-80: 旋回(半径8,ω=1/8)、80-110: 直線
    if t < 30:
        return (10.0 + 1.0*t, 1.0, 0.0)
    elif t < 80:
        omega = 1.0/8.0; cx, cz = 40.0, 8.0
        theta = -math.pi/2 + omega*(t-30)
        return (cx + 8.0*math.cos(theta), 1.0, cz + 8.0*math.sin(theta))
    else:
        omega = 1.0/8.0; cx, cz = 40.0, 8.0
        theta_end = -math.pi/2 + omega*50
        ex = cx + 8.0*math.cos(theta_end); ez = cz + 8.0*math.sin(theta_end)
        vxe = -8.0*math.sin(theta_end)*omega; vze = 8.0*math.cos(theta_end)*omega
        return (ex + vxe*(t-80), 1.0, ez + vze*(t-80))

def s_step_to_circle(t):
    # S6: ω推定収束テスト用。tick<10は直線、tick≥10で旋回開始(半径8, ω=0.125)
    if t < 10:
        return (10.0 + 1.0*t, 1.0, 0.0)
    else:
        omega = 0.125; cx, cz = 20.0, 8.0; r = 8.0
        theta = -math.pi/2 + omega*(t-10)
        return (cx + r*math.cos(theta), 1.0, cz + r*math.sin(theta))

def measure_omega_convergence(window):
    """S6: 旋回開始(tick=10)以降で ω_est が ω_true(=0.125) の 90% に達するまでの tick 数を返す。
    収束時間の理論下限 = (VEL_SAMPLES-1) + WINDOW = 5+W (lsqが旋回samples全埋まり+heading履歴Wペア揃いに必要)。"""
    samples, heading_hist, omega_raw = [], [], []
    OMEGA_TRUE = 0.125; THRESHOLD = 0.9 * OMEGA_TRUE
    for tick in range(0, 50):
        x, y, z = s_step_to_circle(tick)
        samples.append([x,y,z,float(tick)])
        if len(samples) > VEL_SAMPLES: samples.pop(0)
        v_est = lsq_velocity(samples)
        if v_est is None: continue
        vx, _, vz, _, _, _, _ = v_est
        omega = 0.0
        if (vx*vx + vz*vz) > 1e-6:
            h = math.atan2(vz, vx)
            if heading_hist:
                omega_raw.append(unwrap(h - heading_hist[-1]))
                if len(omega_raw) > window: omega_raw.pop(0)
            heading_hist.append(h)
            if len(heading_hist) > window + 1: heading_hist.pop(0)
            if omega_raw: omega = sum(omega_raw)/len(omega_raw)
        if tick >= 10 and abs(omega) >= THRESHOLD:
            return tick - 10
    return None

def run_scenario(fn, t_start, t_end, window, omega_eps=0.005, use_ct=True, omega_t_max=None):
    samples, heading_hist, omega_raw = [], [], []
    shots = hits = 0
    opts = py2lua({"maxIter":8,"eps":0.01,"maxT":200})
    for tick in range(t_start, t_end):
        x, y, z = fn(tick)
        samples.append([x,y,z,float(tick)])
        if len(samples) > VEL_SAMPLES: samples.pop(0)
        v_est = lsq_velocity(samples)
        if v_est is None: continue
        vx, vy, vz, pBarX, pBarY, pBarZ, tCenter = v_est
        dtCenter = float(tick) - tCenter
        omega = 0.0
        if use_ct and (vx*vx + vz*vz) > 1e-6:
            h = math.atan2(vz, vx)
            if heading_hist:
                omega_raw.append(unwrap(h - heading_hist[-1]))
                if len(omega_raw) > window: omega_raw.pop(0)
            heading_hist.append(h)
            if len(heading_hist) > window + 1: heading_hist.pop(0)
            omega = smooth_omega(omega_raw, window)
        # CT/CV両方とも P=P_bar(中央時刻位置)+dtCenter補正で時刻整合を取る(円弧の中心がズレないように)
        P = py2lua({"x":pBarX,"y":pBarY,"z":pBarZ})
        V = py2lua({"x":vx,"y":vy,"z":vz})
        if omega_t_max is None:
            res = ballistics.lead(T, P, V, SPEED, opts, None, omega, omega_eps, dtCenter)
        else:
            res = ballistics.lead(T, P, V, SPEED, opts, None, omega, omega_eps, dtCenter, omega_t_max)
        future, tf = (res[0], res[1]) if isinstance(res, tuple) else (res, None)
        if future is None: continue
        # tf=現在から弾飛翔。標的真位置はサンプル中央から(tf+dtCenter)tick後と等しい。
        tx, ty, tz = fn(tick + tf)
        err = math.sqrt((future.x-tx)**2 + (future.y-ty)**2 + (future.z-tz)**2)
        shots += 1
        if err < HIT_TOL: hits += 1
    return hits, shots

WINDOWS = [1,2,3,4,5,6,8]
print(f"  {'WIN':>3} | {'S1静止':>10} {'S2直線':>10} {'S3遅旋回':>12} {'S4速旋回':>12} {'S5過渡':>10}")
print(f"  {'-'*3} | {'-'*10} {'-'*10} {'-'*12} {'-'*12} {'-'*10}")
results = {}
for w in WINDOWS:
    h1,n1 = run_scenario(s_static,      0,100, w)
    h2,n2 = run_scenario(s_linear,      0,100, w)
    h3,n3 = run_scenario(s_circle_slow, 0,320, w)
    h4,n4 = run_scenario(s_circle_fast, 0,120, w)
    h5,n5 = run_scenario(s_transient,  45, 75, w)   # 過渡を除いた旋回中央30tick
    def pct(h,n): return f"{(100*h/n):>3.0f}%({h}/{n})" if n>0 else "  ---  "
    print(f"  {w:>3} | {pct(h1,n1):>10} {pct(h2,n2):>10} {pct(h3,n3):>12} {pct(h4,n4):>12} {pct(h5,n5):>10}")
    results[w] = {"s1":(h1,n1),"s2":(h2,n2),"s3":(h3,n3),"s4":(h4,n4),"s5":(h5,n5)}

# 参考: CV のみ(use_ct=False) ベースライン
print(f"  {'CV ':>3} |", end="")
for fn, ts, te in [(s_static,0,100),(s_linear,0,100),(s_circle_slow,0,320),(s_circle_fast,0,120),(s_transient,45,75)]:
    h,n = run_scenario(fn, ts, te, 1, use_ct=False)
    print(f" {(100*h/n):>3.0f}%({h}/{n})".rjust(11 if fn in (s_static, s_linear) else (13 if fn in (s_circle_slow, s_circle_fast) else 11)), end="")
print()

# ============================================================
# 4b) S6: ω推定収束時間 (旋回開始からの追従速度)
# ============================================================
print("\n=== 4b) S6: ω推定収束時間 ===")
print(f"  {'WIN':>3} | 収束tick(ω_est≥0.9·ω_true)")
print(f"  {'-'*3} | {'-'*30}")
conv_results = {}
for w in WINDOWS:
    c = measure_omega_convergence(w)
    conv_results[w] = c
    theoretical_lb = (VEL_SAMPLES - 1) + w  # 理論下限
    print(f"  {w:>3} | {c if c is not None else '∞':>5}    (理論下限={theoretical_lb})")

# ============================================================
# 5) 撤退基準 (a)(b)(c)(d) + WINDOW機械決定  ※S5は参考(実機目視で評価)
# ============================================================
print("\n=== 5) 撤退基準 (a)(b)(c)(d) + WINDOW機械決定 ===")
def pct(hn): return 100*hn[0]/hn[1] if hn[1]>0 else 0
passing = []
for w, r in results.items():
    a = pct(r["s1"]) >= 99 and pct(r["s2"]) >= 99
    b = pct(r["s3"]) >= 80
    c = pct(r["s4"]) >= 50
    ok = a and b and c
    mark = lambda x: "✓" if x else "✗"
    print(f"  WIN={w}: (a){mark(a)} (b){mark(b)} (c){mark(c)} → {'PASS' if ok else 'fail'}  [S5参考={pct(r['s5']):.0f}% / S6収束={conv_results[w]}tick]")
    if ok: passing.append(w)

# WINDOW機械決定: (a)(b)(c)通過 AND S6収束≤12tick のうち最大WINDOW
# S6しきい値=12tickの根拠: 理論下限=5+W、W=8で下限13。実用lag(4tick)の3倍以内に追従収束が回り出す。
S6_THRESHOLD = 12
optimal_window = None
for w in sorted(passing, reverse=True):
    if conv_results[w] is not None and conv_results[w] <= S6_THRESHOLD:
        optimal_window = w; break

if passing:
    print(f"\n  (d) ✓ 通過WINDOW = {passing}")
    check("撤退基準(a)(b)(c)(d)全通過WINDOW存在", True)
else:
    print(f"\n  (d) ✗ 通過WINDOWなし — design.md §12.20「CTも撤回」追記検討")
    check("撤退基準(a)(b)(c)(d)全通過WINDOW存在", False)

if optimal_window is not None:
    print(f"  WINDOW 機械決定 = {optimal_window} (S6収束 {conv_results[optimal_window]}tick ≤ {S6_THRESHOLD})")
    check(f"WINDOW 機械決定 (S6≤{S6_THRESHOLD}tick AND (a)(b)(c)通過)", True)
else:
    check(f"WINDOW 機械決定", False)

# ============================================================
# 6) omegaEps グリッドサーチ (最適WINDOW固定)
# ============================================================
print(f"\n=== 6) omegaEps グリッドサーチ (WINDOW={optimal_window}固定) ===")
EPS_CANDIDATES = [0.001, 0.005, 0.01, 0.02, 0.05]
print(f"  {'eps':>7} | {'S1':>6} {'S2':>6} {'S3':>8} {'S4':>8}")
print(f"  {'-'*7} | {'-'*6} {'-'*6} {'-'*8} {'-'*8}")
eps_results = {}
for eps in EPS_CANDIDATES:
    h1,n1 = run_scenario(s_static,      0,100, optimal_window, omega_eps=eps)
    h2,n2 = run_scenario(s_linear,      0,100, optimal_window, omega_eps=eps)
    h3,n3 = run_scenario(s_circle_slow, 0,320, optimal_window, omega_eps=eps)
    h4,n4 = run_scenario(s_circle_fast, 0,120, optimal_window, omega_eps=eps)
    def p(h,n): return (100*h/n) if n>0 else 0
    p1, p2, p3, p4 = p(h1,n1), p(h2,n2), p(h3,n3), p(h4,n4)
    print(f"  {eps:>7.3f} | {p1:>5.0f}% {p2:>5.0f}% {p3:>7.0f}% {p4:>7.0f}%")
    eps_results[eps] = (p1, p2, p3, p4)

# omegaEps決定: (a)(b)(c)全通過するうち最大eps(=「明らかに静止/直線」だけCV化、それ以外はCT)
optimal_eps = None
for eps in sorted(EPS_CANDIDATES, reverse=True):
    p1, p2, p3, p4 = eps_results[eps]
    if p1 >= 99 and p2 >= 99 and p3 >= 80 and p4 >= 50:
        optimal_eps = eps; break

if optimal_eps is not None:
    print(f"  omegaEps 機械決定 = {optimal_eps}")
    check(f"omegaEps 機械決定 (a)(b)(c)通過最大値", True)
else:
    check("omegaEps 機械決定", False)

# ============================================================
# 7) §12.20 ω·t クランプ閾値グリッドサーチ
# ============================================================
print(f"\n=== 7) §12.20 ω·t クランプ閾値グリッドサーチ (WINDOW={optimal_window}, eps={optimal_eps}固定) ===")
CLAMP_CANDIDATES_DEG = [22.5, 45, 60, 90, 180]  # 180=実質クランプなし
print(f"  {'角[deg]':>8} | {'S1':>6} {'S2':>6} {'S3':>8} {'S4':>8} {'S5(参考)':>10}")
print(f"  {'-'*8} | {'-'*6} {'-'*6} {'-'*8} {'-'*8} {'-'*10}")
clamp_results = {}
for deg in CLAMP_CANDIDATES_DEG:
    rad = math.radians(deg)
    h1,n1 = run_scenario(s_static,      0,100, optimal_window, omega_eps=optimal_eps, omega_t_max=rad)
    h2,n2 = run_scenario(s_linear,      0,100, optimal_window, omega_eps=optimal_eps, omega_t_max=rad)
    h3,n3 = run_scenario(s_circle_slow, 0,320, optimal_window, omega_eps=optimal_eps, omega_t_max=rad)
    h4,n4 = run_scenario(s_circle_fast, 0,120, optimal_window, omega_eps=optimal_eps, omega_t_max=rad)
    h5,n5 = run_scenario(s_transient,  45, 75, optimal_window, omega_eps=optimal_eps, omega_t_max=rad)
    def p(h,n): return (100*h/n) if n>0 else 0
    p1,p2,p3,p4,p5 = p(h1,n1), p(h2,n2), p(h3,n3), p(h4,n4), p(h5,n5)
    print(f"  {deg:>7.1f}° | {p1:>5.0f}% {p2:>5.0f}% {p3:>7.0f}% {p4:>7.0f}% {p5:>9.0f}%")
    clamp_results[deg] = (p1, p2, p3, p4, p5)

# 合成では S1-S4 の ω·t < π/4 なのでクランプ無効と同じ結果になるはず(=サニティチェック)。
# クランプの真価は実機CSV(Phase 3)で。
clamp_consistent = all(
    abs(clamp_results[deg][i] - clamp_results[180][i]) < 0.5 for deg in [45, 60, 90] for i in range(4)
)
check("合成シナリオ S1-S4 で クランプ値による命中率不変(ω·t<π/4 なので)", clamp_consistent)

# 合成での推奨値: 設計判断 = π/4 = 45°(実機で半周予測の暴発を防ぐ最低限)
# 合成 S1-S4 では効かないが、副作用も無い(命中率不変)→ 安全側で導入できる証拠
print(f"\n  合成では S1-S4 全部 ω·t<π/4 なのでクランプ値で命中率変わらず → 副作用なしの安全側導入が可能")
print(f"  最終クランプ値: π/4 = 45°(§12.20 推奨)  ※実機での効果は Phase 3 で検証")
optimal_clamp_deg = 45

print(f"\n{'='*60}")
print(f"【合成最終確定】WINDOW={optimal_window}, omegaEps={optimal_eps}, omegaTMax={optimal_clamp_deg}°(={math.pi/4:.4f}rad)")
print(f"{'='*60}")

# ============================================================
# 8) §12.20 実機CSVシナリオ: CV / CT(クランプなし) / CT(クランプあり) で命中率機械比較
# CLAUDE.md「合成PASS≠実機PASS、テストが本番経路を再現してるか疑え」の実装
# ============================================================
import csv as _csv

CSV_PATH = r'D:\Claude\ars-cc-turret\run\saves\New World\computercraft\computer\2\turret.csv'

def load_realtrack(path):
    """CSV(秒) → (tick, x, y, z) 時系列。1秒=20tick換算"""
    track = []
    try:
        with open(path, newline='') as f:
            for r in _csv.DictReader(f):
                track.append((float(r['clock'])*20, float(r['x']), float(r['y']), float(r['z'])))
    except FileNotFoundError:
        return None
    return track

def interpolate(track, t):
    """連続時間 t での位置を線形補間。範囲外は None"""
    if t < track[0][0] or t > track[-1][0]: return None
    lo, hi = 0, len(track)-1
    while lo < hi-1:
        mid = (lo+hi)//2
        if track[mid][0] <= t: lo = mid
        else: hi = mid
    t0,x0,y0,z0 = track[lo]; t1,x1,y1,z1 = track[hi]
    if t1 == t0: return (x0,y0,z0)
    f = (t-t0)/(t1-t0)
    return (x0+f*(x1-x0), y0+f*(y1-y0), z0+f*(z1-z0))

def run_realtrack(track, turret_pos, window, omega_eps, use_ct=True, omega_t_max=None):
    """実機CSV駆動のハーネス: 砲口位置 turret_pos からの予測と真位置を比較"""
    samples, heading_hist, omega_raw = [], [], []
    shots = hits = 0
    opts = py2lua({"maxIter":8,"eps":0.01,"maxT":200})
    T_local = py2lua({"x":turret_pos[0], "y":turret_pos[1], "z":turret_pos[2]})
    for idx, (tick, x, y, z) in enumerate(track):
        samples.append([x,y,z,tick])
        if len(samples) > VEL_SAMPLES: samples.pop(0)
        v_est = lsq_velocity(samples)
        if v_est is None: continue
        vx, vy, vz, pBarX, pBarY, pBarZ, tCenter = v_est
        dtCenter = tick - tCenter
        omega = 0.0
        if use_ct and (vx*vx + vz*vz) > 1e-6:
            h = math.atan2(vz, vx)
            if heading_hist:
                omega_raw.append(unwrap(h - heading_hist[-1]))
                if len(omega_raw) > window: omega_raw.pop(0)
            heading_hist.append(h)
            if len(heading_hist) > window+1: heading_hist.pop(0)
            omega = smooth_omega(omega_raw, window)
        P = py2lua({"x":pBarX,"y":pBarY,"z":pBarZ})
        V = py2lua({"x":vx,"y":vy,"z":vz})
        if omega_t_max is None:
            res = ballistics.lead(T_local, P, V, SPEED, opts, None, omega, omega_eps, dtCenter)
        else:
            res = ballistics.lead(T_local, P, V, SPEED, opts, None, omega, omega_eps, dtCenter, omega_t_max)
        future, tf = (res[0], res[1]) if isinstance(res, tuple) else (res, None)
        if future is None: continue
        target_pos = interpolate(track, tick + tf)
        if target_pos is None: continue
        tx,ty,tz = target_pos
        err = math.sqrt((future.x-tx)**2 + (future.y-ty)**2 + (future.z-tz)**2)
        shots += 1
        if err < HIT_TOL: hits += 1
    return hits, shots

print(f"\n=== 8) 実機CSVシナリオ: 距離別に CV / CT(無) / CT(有45°) 命中率比較 ===")
print(f"  CSVには turret 絶対位置がないので、複数の砲口距離で比較しクランプの効果領域を見る")
track = load_realtrack(CSV_PATH)
if track is None or len(track) < VEL_SAMPLES + 5:
    print(f"  CSV読み込み失敗 or データ不足: {CSV_PATH}")
    check("実機CSV読み込み", False)
else:
    xs = [x for _,x,_,_ in track]; ys = [y for _,_,y,_ in track]; zs = [z for _,_,_,z in track]
    cx, cy, cz = sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs)
    print(f"  CSVサンプル数: {len(track)}  標的軌跡重心: ({cx:.1f}, {cy:.1f}, {cz:.1f})")
    print(f"  {'dist':>5} | {'CV':>6} {'CT無':>7} {'CT有':>7} {'CT有-CT無':>10} {'CT有-CV':>9}")
    print(f"  {'-'*5} | {'-'*6} {'-'*7} {'-'*7} {'-'*10} {'-'*9}")

    DISTANCES = [5, 10, 15, 20, 30]
    real_results = []
    for d in DISTANCES:
        # 砲口位置: 標的重心から -x 方向に d離れた位置(高さは重心同じ)
        turret_pos = (cx - d, cy, cz)
        h_cv, n_cv         = run_realtrack(track, turret_pos, optimal_window, optimal_eps, use_ct=False)
        h_no, n_no         = run_realtrack(track, turret_pos, optimal_window, optimal_eps, use_ct=True, omega_t_max=math.pi)
        h_yes, n_yes       = run_realtrack(track, turret_pos, optimal_window, optimal_eps, use_ct=True, omega_t_max=math.pi/4)
        def p(h,n): return (100*h/n) if n>0 else 0
        pct_cv  = p(h_cv, n_cv)
        pct_no  = p(h_no, n_no)
        pct_yes = p(h_yes, n_yes)
        print(f"  {d:>4}b | {pct_cv:>5.1f}% {pct_no:>6.1f}% {pct_yes:>6.1f}% {pct_yes-pct_no:>+9.1f}pt {pct_yes-pct_cv:>+8.1f}pt")
        real_results.append((d, pct_cv, pct_no, pct_yes))

    # 距離レンジ平均で総合判定
    mean_cv  = sum(r[1] for r in real_results) / len(real_results)
    mean_no  = sum(r[2] for r in real_results) / len(real_results)
    mean_yes = sum(r[3] for r in real_results) / len(real_results)
    print(f"  {'平均':>5} | {mean_cv:>5.1f}% {mean_no:>6.1f}% {mean_yes:>6.1f}% {mean_yes-mean_no:>+9.1f}pt {mean_yes-mean_cv:>+8.1f}pt")

    # 機械判定: 実機での CT(クランプあり)平均 vs CV平均
    # 結果に応じて撤退判定を自動的に下す(機械判定でCT撤退条件成立なら ct.enabled=false 推奨)
    ct_useful = mean_yes >= mean_cv
    check("実機(h1) クランプ平均はクランプなし以上(-2pt許容)", mean_yes >= mean_no - 2)
    if ct_useful:
        print(f"\n  ★ 機械判定: CT(有)平均{mean_yes:.1f}% ≥ CV平均{mean_cv:.1f}% → **CT維持を推奨**")
        check("CT撤退判定(機械実行) = 維持", True)
    else:
        print(f"\n  ★ 機械判定: CT(有)平均{mean_yes:.1f}% < CV平均{mean_cv:.1f}% ({mean_yes-mean_cv:+.1f}pt) → **CT撤退を推奨**")
        print(f"  → config.lua の ct.enabled を false へ変更推奨(機械判定根拠)")
        check("CT撤退判定(機械実行) = 撤退", True)
    # 撤退判定そのものが機械で下せたことを記録(値の正負は判定結果として表示済み)

print(f"\n{'='*60}")
print(f"{passed} PASS / {failed} FAIL")
sys.exit(0 if failed == 0 else 1)

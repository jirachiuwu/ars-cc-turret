#!/usr/bin/env python3
# turret.csv 解析: ω推定, 標的軌道, aim点の動きを切り分け
import csv, math, sys

CSV = r'D:\Claude\ars-cc-turret\run\saves\New World\computercraft\computer\2\turret.csv'

rows = []
with open(CSV, newline='') as f:
    for r in csv.DictReader(f):
        rows.append(r)

def to_f(v):
    try: return float(v)
    except: return None

# 1) 速度の大きい区間(|V|>0.2 b/t)を抽出
moving = []
for r in rows:
    vx, vz = float(r['vx']), float(r['vz'])
    if vx*vx + vz*vz > 0.04:  # |V|>0.2
        moving.append(r)

print(f"=== 統計 ===")
print(f"全tick:        {len(rows)}")
print(f"移動中(|V|>0.2): {len(moving)}")
print(f"発射数:        {rows[-1]['shots']}")

# 2) ω分布(移動中のみ)
if moving:
    omegas = [float(r['omega']) for r in moving]
    omegas_abs = [abs(o) for o in omegas]
    pos = [o for o in omegas if o > 0.02]
    neg = [o for o in omegas if o < -0.02]
    near0 = [o for o in omegas if abs(o) <= 0.02]
    print(f"\n=== ω分布(移動中) ===")
    print(f"min/mean/max: {min(omegas):+.4f} / {sum(omegas)/len(omegas):+.4f} / {max(omegas):+.4f}")
    print(f"  |ω|       : min={min(omegas_abs):.4f} mean={sum(omegas_abs)/len(omegas_abs):.4f} max={max(omegas_abs):.4f}")
    print(f"  CT有効   (|ω|>0.02): {len(pos)+len(neg)} tick (正{len(pos)} / 負{len(neg)})")
    print(f"  CV(|ω|≤0.02): {len(near0)} tick")

# 3) CT予測が効いてる(|ω|>0.02)区間で、リードベクトルが妥当か?
#   CT予測点 = aim、現在位置 = (x,y,z)、リードベクトル L = aim - (x,y,z)
#   Lの水平成分が標的速度 V_h と「ほぼ平行」か「逆向き」かを見る(直進なら平行・旋回ならズレが出るが範囲内)
print(f"\n=== CT予測 vs 速度の整合(|ω|>0.02 のtick) ===")
print(f"  {'idx':>4} {'x':>6} {'z':>6} {'vx':>7} {'vz':>7} {'ω':>8} {'aimX':>6} {'aimZ':>6} {'L角度':>7} {'V角度':>7} {'角度差':>7}")
ct_active = [(i, r) for i, r in enumerate(rows) if abs(float(r['omega'])) > 0.02 and r['aimX'] and float(r['vx'])**2+float(r['vz'])**2 > 0.04]
sample_idx = ct_active[::max(1, len(ct_active)//15)] if ct_active else []
for i, r in sample_idx[:15]:
    x, z = float(r['x']), float(r['z'])
    vx, vz = float(r['vx']), float(r['vz'])
    omega = float(r['omega'])
    aimX, aimZ = float(r['aimX']), float(r['aimZ'])
    Lx, Lz = aimX - x, aimZ - z
    L_deg = math.degrees(math.atan2(Lz, Lx))
    V_deg = math.degrees(math.atan2(vz, vx))
    diff = ((L_deg - V_deg + 540) % 360) - 180
    print(f"  {i:>4} {x:>6.1f} {z:>6.1f} {vx:>+7.3f} {vz:>+7.3f} {omega:>+8.4f} {aimX:>6.1f} {aimZ:>6.1f} {L_deg:>+7.1f} {V_deg:>+7.1f} {diff:>+7.1f}")

# 4) 旋回方向と ω の符号の対応をチェック
#    弧上の3点 (i-3, i, i+3) から実旋回方向を出して、ω推定の符号と比較
print(f"\n=== 実軌道の旋回 vs ω推定の符号 (|ω|>0.02 連続区間) ===")
def turn_sign(p_prev, p_now, p_next):
    """3点から旋回方向を算出。cross > 0 なら反時計回り(数学的に正の旋回方向)"""
    ax, az = p_now[0]-p_prev[0], p_now[1]-p_prev[1]
    bx, bz = p_next[0]-p_now[0], p_next[1]-p_now[1]
    return ax*bz - az*bx
samples = []
for i in range(3, len(rows)-3):
    r = rows[i]
    if not r['aimX']: continue
    omega = float(r['omega'])
    if abs(omega) < 0.02: continue
    v = float(r['vx'])**2 + float(r['vz'])**2
    if v < 0.04: continue
    p_prev = (float(rows[i-3]['x']), float(rows[i-3]['z']))
    p_now  = (float(rows[i]['x']),   float(rows[i]['z']))
    p_next = (float(rows[i+3]['x']), float(rows[i+3]['z']))
    ts = turn_sign(p_prev, p_now, p_next)
    if abs(ts) < 0.001: continue  # ほぼ直進
    samples.append((i, omega, ts))
if samples:
    agree = sum(1 for _, o, ts in samples if (o > 0) == (ts > 0))
    disagree = len(samples) - agree
    print(f"  符号一致: {agree}/{len(samples)}  ({100*agree/len(samples):.0f}%)")
    print(f"  符号逆転: {disagree}/{len(samples)}  ({100*disagree/len(samples):.0f}%)")
    print(f"  → 100%近く一致なら符号OK、半々ならランダム=ω推定が物理に追従してない、ほぼ逆ならA仮説(符号エラー)")

# 5) 発射時の aim 誤差と命中の関係(命中は確認できないが、aimErr が大きい時の状況)
fires = [r for r in rows if r['fired'] == '1']
print(f"\n=== 発射時(計{len(fires)}発) ===")
if fires:
    errs = [float(r['aimErr']) for r in fires]
    print(f"  aimErr: min/mean/max = {min(errs):.2f} / {sum(errs)/len(errs):.2f} / {max(errs):.2f}")
    moving_fires = [r for r in fires if float(r['vx'])**2+float(r['vz'])**2 > 0.04]
    print(f"  移動標的時の発射: {len(moving_fires)}/{len(fires)}")

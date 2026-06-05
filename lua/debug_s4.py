#!/usr/bin/env python3
# S4 (一周60tick半径6) を 1tick 詳細トレース
import os, sys, math
from lupa import LuaRuntime

HERE = os.path.dirname(os.path.abspath(__file__))
lua = LuaRuntime(unpack_returned_tuples=True)
ballistics = lua.execute(open(os.path.join(HERE, "ballistics.lua"), encoding="utf-8").read())
def py2lua(d):
    t = lua.table()
    for k, v in d.items(): t[k] = v
    return t
def unwrap(d):
    if d > math.pi: d -= 2*math.pi
    elif d < -math.pi: d += 2*math.pi
    return d

def s_circle_fast(t):
    omega = 2*math.pi/60;  r = 6.0
    return (r*math.cos(omega*t), 1.0, r*math.sin(omega*t))

T = py2lua({"x":0.0,"y":0.0,"z":0.0})
opts = py2lua({"maxIter":8,"eps":0.01,"maxT":200})
SPEED = 1.5
WINDOW = 4

samples, heading_hist, omega_raw = [], [], []
for tick in range(0, 30):
    x, y, z = s_circle_fast(tick)
    samples.append([x,y,z,float(tick)])
    if len(samples) > 6: samples.pop(0)
    if len(samples) < 2: continue
    n = len(samples); t_bar = sum(s[3] for s in samples)/n
    sxx = sum((s[3]-t_bar)**2 for s in samples)
    vx = sum((s[3]-t_bar)*s[0] for s in samples)/sxx
    vy = sum((s[3]-t_bar)*s[1] for s in samples)/sxx
    vz = sum((s[3]-t_bar)*s[2] for s in samples)/sxx
    omega = 0.0
    if vx*vx+vz*vz > 1e-6:
        h = math.atan2(vz, vx)
        if heading_hist:
            omega_raw.append(unwrap(h - heading_hist[-1]))
            if len(omega_raw) > WINDOW: omega_raw.pop(0)
        heading_hist.append(h)
        if len(heading_hist) > WINDOW+1: heading_hist.pop(0)
        if omega_raw: omega = sum(omega_raw)/len(omega_raw)
    P = py2lua({"x":x,"y":y,"z":z})
    V = py2lua({"x":vx,"y":vy,"z":vz})
    res = ballistics.lead(T, P, V, SPEED, opts, None, omega, 0.005)
    future, tf = res[0], res[1]
    if future is None:
        print(f"tick={tick:>2} P=({x:.2f},{z:.2f}) V=({vx:.3f},{vz:.3f}) |V|={math.sqrt(vx*vx+vz*vz):.3f} omega={omega:.4f} future=NIL t={tf}")
        continue
    tx, _, tz = s_circle_fast(tick + tf)
    err = math.sqrt((future.x-tx)**2 + (future.z-tz)**2)
    omega_true = 2*math.pi/60
    print(f"tick={tick:>2} P=({x:>5.2f},{z:>5.2f}) V=({vx:>6.3f},{vz:>6.3f}) ω_est={omega:>6.3f} ω_true={omega_true:.3f} t_fl={tf:.2f} fut=({future.x:>5.2f},{future.z:>5.2f}) true=({tx:>5.2f},{tz:>5.2f}) err={err:.3f}")

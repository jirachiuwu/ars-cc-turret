#!/usr/bin/env python3
# S5 過渡応答シナリオの詳細トレース
import os, math
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

def s_transient(t):
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

T = py2lua({"x":0.0,"y":0.0,"z":0.0})
opts = py2lua({"maxIter":8,"eps":0.01,"maxT":200})
SPEED = 1.5
WINDOW = 4

samples, heading_hist, omega_raw = [], [], []
for tick in range(40, 76):
    x, y, z = s_transient(tick)
    samples.append([x,y,z,float(tick)])
    if len(samples) > 6: samples.pop(0)
    if len(samples) < 2: continue
    n = len(samples); t_bar = sum(s[3] for s in samples)/n
    x_bar = sum(s[0] for s in samples)/n
    z_bar = sum(s[2] for s in samples)/n
    sxx = sum((s[3]-t_bar)**2 for s in samples)
    vx = sum((s[3]-t_bar)*s[0] for s in samples)/sxx
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
    dt = float(tick) - t_bar
    P = py2lua({"x":x_bar,"y":1.0,"z":z_bar})
    V = py2lua({"x":vx,"y":0.0,"z":vz})
    res = ballistics.lead(T, P, V, SPEED, opts, None, omega, 0.005, dt)
    future, tf = res[0], res[1]
    if future is None:
        print(f"tick={tick:>2} fut=NIL tf={tf}")
        continue
    tx, _, tz = s_transient(tick + tf)
    err = math.sqrt((future.x-tx)**2 + (future.z-tz)**2)
    dist = math.sqrt(x*x+z*z)
    print(f"tick={tick:>2} dist={dist:>5.1f} V=({vx:>6.3f},{vz:>6.3f}) ω={omega:>6.4f} tf={tf:>5.2f} dt_c={dt:>4.1f} fut=({future.x:>6.2f},{future.z:>6.2f}) true=({tx:>6.2f},{tz:>6.2f}) err={err:.3f} {'HIT' if err<0.5 else ''}")

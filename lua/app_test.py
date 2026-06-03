#!/usr/bin/env python3
# 火器管制アプリ(turret/monitor/main 等)を lupa(本物の Lua)で機械検証する。
# 1) 全 lua の構文チェック(compile) 2) turret.step の状態機械+ログ 3) monitor.render が無エラーで走る。
import os, sys
from lupa import LuaRuntime

HERE = os.path.dirname(os.path.abspath(__file__))
lua = LuaRuntime(unpack_returned_tuples=True)
G = lua.globals()
passed = failed = 0

def check(name, cond):
    global passed, failed
    if cond: print(f"PASS {name}"); passed += 1
    else:    print(f"FAIL {name}"); failed += 1

def read(f): return open(os.path.join(HERE, f), encoding="utf-8").read()

def py2lua(v):
    if isinstance(v, dict):
        t = lua.table()
        for k, x in v.items(): t[k] = py2lua(x)
        return t
    if isinstance(v, list):
        t = lua.table()
        for i, x in enumerate(v): t[i + 1] = py2lua(x)
        return t
    return v

# --- 1) 全 lua 構文チェック(load = compile のみ、実行しない) ---
loadfn = lua.eval("load")
for f in ["ballistics.lua", "targeting.lua", "turret.lua", "config.lua", "monitor.lua", "main.lua", "install.lua"]:
    res = loadfn(read(f), "@" + f)
    fn, err = (res[0], res[1]) if isinstance(res, tuple) else (res, None)  # 成功は関数1個, 失敗は nil+err
    check(f"syntax {f}", fn is not None and err is None)
    if err: print("   ", err)

# --- モジュール読込(CCグローバル非依存のもの) ---
ballistics = lua.execute(read("ballistics.lua"))
targeting  = lua.execute(read("targeting.lua"))
turret     = lua.execute(read("turret.lua"))
config     = lua.execute(read("config.lua"))

# --- 2) turret.step: モック peripheral で状態機械+ログ ---
fired_flag = {"n": 0}
def make_P(scenario):
    # scenario: listEntities が返すエンティティ列(各 dict)。固定 muzzle/aim 値。
    P = lua.table()
    P["getMuzzle"]         = lambda: py2lua({"x": 0.0, "y": 0.0, "z": 0.0})
    P["listEntities"]      = lambda rng=None: py2lua({i+1: e for i, e in enumerate(scenario)})
    P["getProjectileSpeed"]= lambda: 1.5
    P["getAimError"]       = lambda dx, dy, dz: 0.5   # 常に収束圏内
    P["getSpellCost"]      = lambda: 10
    P["isLoaded"]          = lambda: True
    P["getCreative"]       = lambda: True
    P["getSource"]         = lambda: 1e9
    P["aim"]               = lambda x, y, z: None
    def fire():
        fired_flag["n"] += 1; return True
    P["fire"] = fire
    return P

cfg = config  # config.lua の戻りをそのまま使う(filter/priority/lead 等)

# (a) 標的なし → IDLE
s = turret.new(9)
turret.step(make_P([]), cfg, s, ballistics, targeting)
check("step: no target -> IDLE", s.status == "IDLE")

# (b) 接近する zombie(視線あり) → TRACKING/FIRING、発射、ログに TRK と FIRE
zombie = {"uuid": "z1", "type": "minecraft:zombie", "x": 12.0, "y": 0.0, "z": 0.0,
          "vx": -1.0, "vy": -0.078, "vz": 0.0, "height": 2.0,
          "distance": 12.0, "isAlive": True, "isPlayer": False, "los": True}
fired_flag["n"] = 0
s = turret.new(9)
turret.step(make_P([zombie]), cfg, s, ballistics, targeting)
check("step: target -> fired", fired_flag["n"] == 1)
check("step: status FIRING", s.status == "FIRING")
check("step: locked uuid", s.lock == "z1")
log = [s.log[i] for i in range(1, len(s.log) + 1)]
check("step: log has TRK", any(l.startswith("TRK zombie") for l in log))
check("step: log has FIRE", any(l.startswith(">> FIRE zombie") for l in log))
check("step: log has SOL(計算ログ)", any(l.startswith("SOL ") for l in log))

# (c) 視線なし(los=false) → フィルタで除外 → IDLE(撃たない)
blocked = dict(zombie); blocked["los"] = False
fired_flag["n"] = 0
s = turret.new(9)
turret.step(make_P([blocked]), cfg, s, ballistics, targeting)
check("step: no-LoS excluded -> no fire", fired_flag["n"] == 0 and s.status == "IDLE")

# --- 3) monitor.render: CCグローバルをモックして無エラー描画 ---
# colors / 簡易 monitor を inject
G["colors"] = py2lua({k: i for i, k in enumerate(
    ["white","orange","magenta","lightBlue","yellow","lime","pink","gray",
     "lightGray","cyan","purple","blue","brown","green","red","black"])})
writes = []
mon = lua.table()
mon["getSize"]            = lambda: (25, 20)
mon["setCursorPos"]       = lambda x, y: None
mon["setTextColor"]       = lambda c: None
mon["setBackgroundColor"] = lambda c: None
mon["setTextScale"]       = lambda s: None
mon["clear"]              = lambda: None
mon["write"]              = lambda t: writes.append(t)
G["peripheral"] = py2lua({})
G["peripheral"]["find"] = lambda kind=None: mon
monitor = lua.execute(read("monitor.lua"))

ok_render = True
try:
    monitor.render(mon, s, cfg)            # IDLE 状態
    # FIRING 状態でも描画
    s2 = turret.new(9)
    turret.step(make_P([zombie]), cfg, s2, ballistics, targeting)
    monitor.render(mon, s2, cfg)
except Exception as e:
    ok_render = False; print("   render error:", e)
check("monitor.render runs (no error)", ok_render)
check("monitor.render wrote lines", len(writes) > 10)
check("monitor shows FIRE CONTROL header", any("FIRE CONTROL" in w for w in writes))

print(f"\n=== {passed} passed, {failed} failed ===")
sys.exit(1 if failed else 0)

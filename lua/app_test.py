#!/usr/bin/env python3
# 火器管制アプリを lupa(本物の Lua)で機械検証。1)全lua構文 2)turret.step状態機械/ログ
# 3)monitor GUI v2: clampStep/resolve/renderConfig→hit→applyAction の全経路 + render無エラー。
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

# --- 1) 全 lua 構文チェック(load=compileのみ、実行しない) ---
loadfn = lua.eval("load")
for f in ["ballistics.lua", "targeting.lua", "turret.lua", "config.lua", "monitor.lua", "main.lua", "install.lua"]:
    res = loadfn(read(f), "@" + f)
    fn, err = (res[0], res[1]) if isinstance(res, tuple) else (res, None)
    check(f"syntax {f}", fn is not None and err is None)
    if err: print("   ", err)

# --- モジュール読込(CCグローバル非依存) ---
ballistics = lua.execute(read("ballistics.lua"))
targeting  = lua.execute(read("targeting.lua"))
turret     = lua.execute(read("turret.lua"))
config     = lua.execute(read("config.lua"))

# --- mock peripheral(turret) ---
fired = {"n": 0}
def make_P(scenario, aim_err=0.5):
    P = lua.table()
    def scan(rng=None):
        return py2lua({
            "muzzle": {"x": 0.0, "y": 0.0, "z": 0.0},
            "entities": {i + 1: e for i, e in enumerate(scenario)},
            "speed": 1.5, "creative": True, "cost": 10, "loaded": True, "source": 1e9,
        })
    P["scan"] = scan
    P["aim"]  = lambda x, y, z: aim_err          # aim は照準誤差を返す
    P["setProjectileSpeed"] = lambda v: None
    P["setCreative"]        = lambda b: None
    P["setBurst"]           = lambda n: None
    def f(): fired["n"] += 1; return True
    P["fire"] = f
    return P

cfg = config

# --- 2) turret.step ---
s = turret.new(9)
turret.step(make_P([]), cfg, s, ballistics, targeting)
check("step: no target -> IDLE", s.status == "IDLE")

zombie = {"uuid": "z1", "type": "minecraft:zombie", "x": 12.0, "y": 0.0, "z": 0.0,
          "vx": -1.0, "vy": -0.078, "vz": 0.0, "height": 2.0,
          "distance": 12.0, "isAlive": True, "isPlayer": False, "hostile": True, "los": True}
fired["n"] = 0
s = turret.new(9)
turret.step(make_P([zombie]), cfg, s, ballistics, targeting)
check("step: target -> fired", fired["n"] == 1)
check("step: status FIRING", s.status == "FIRING")
log = [s.log[i] for i in range(1, len(s.log) + 1)]
check("step: log TRK/SOL/FIRE", any(l.startswith("TRK") for l in log)
      and any(l.startswith("SOL") for l in log) and any(l.startswith(">> FIRE") for l in log))
check("step: VEL computed (|V|~1.0)", abs(s.sol.vel - 1.0) < 0.05)       # vx=-1.0, vy clamped, vz=0
check("step: LEADd>0 (偏差が効いてる)", s.sol.leadOff > 0.5)             # |V|*t ぶん前を狙う
# leadLag(遅延補償): 標的を V*lag 先に進めるぶんリードが増える
cfg.leadLag = 0;  s0 = turret.new(9); turret.step(make_P([zombie]), cfg, s0, ballistics, targeting)
cfg.leadLag = 3;  s3 = turret.new(9); turret.step(make_P([zombie]), cfg, s3, ballistics, targeting)
check("step: leadLag increases lead (遅延補償)", s3.sol.leadOff > s0.sol.leadOff + 1.0)
# s.loopLag(実測ループ周期)も遅延補償に効く。lag = leadLag + loopLag
cfg.leadLag = 0
sL = turret.new(9); sL.loopLag = 3; turret.step(make_P([zombie]), cfg, sL, ballistics, targeting)
check("step: loopLag adds to lead (自動遅延)", sL.sol.leadOff > s0.sol.leadOff + 1.0)
check("step: sol.lag = leadLag + loopLag", abs(sL.sol.lag - 3.0) < 1e-9)
cfg.leadLag = config.leadLag

# 2次リード: 加速度ありで未来位置が曲がる(曲線運動対応)
_T = py2lua({"x": 0.0, "y": 0.0, "z": 0.0})
_P = py2lua({"x": 10.0, "y": 0.0, "z": 0.0})
_V = py2lua({"x": 0.0, "y": 0.0, "z": 0.5})
_A = py2lua({"x": 0.0, "y": 0.0, "z": 0.05})        # 小さめ(intercept が存在する範囲)
_opt = py2lua({"maxIter": 8, "eps": 0.01, "maxT": 200})
f1 = ballistics.lead(_T, _P, _V, 1.5, _opt)[0]        # 加速度なし(戻りは future,t のタプル)
f2 = ballistics.lead(_T, _P, _V, 1.5, _opt, _A)[0]    # 加速度あり
check("lead: A bends future (2次予測)", f1 is not None and f2 is not None and (f2.z - f1.z) > 0.3)
blocked = dict(zombie); blocked["los"] = False
fired["n"] = 0
s = turret.new(9)
turret.step(make_P([blocked]), cfg, s, ballistics, targeting)
check("step: no-LoS -> no fire/IDLE", fired["n"] == 0 and s.status == "IDLE")

# --- 2b) 標的モード filter ---
def E(**kw):
    d = {"isAlive": True, "los": True, "hostile": False, "isPlayer": False}; d.update(kw); return py2lua(d)
fh, fm, fp, fa = (targeting.makeFilter("hostile"), targeting.makeFilter("mobs"),
                  targeting.makeFilter("players"), targeting.makeFilter("all"))
check("filter hostile: 敵対MOB yes",    fh(E(hostile=True)) == True)
check("filter hostile: 受動MOB no",     fh(E(hostile=False)) == False)
check("filter hostile: player no",      fh(E(hostile=True, isPlayer=True)) == False)
check("filter mobs: 受動MOB yes",       fm(E(hostile=False)) == True)
check("filter mobs: player no",         fm(E(isPlayer=True)) == False)
check("filter players: player yes",     fp(E(isPlayer=True)) == True)
check("filter players: MOB no",         fp(E(hostile=True)) == False)
check("filter all: player yes",         fa(E(isPlayer=True)) == True)
check("filter all: no-LoS no",          fa(E(los=False)) == False)

# --- 3) monitor GUI v2 ---
G["colors"] = py2lua({k: i for i, k in enumerate(
    ["white","orange","magenta","lightBlue","yellow","lime","pink","gray",
     "lightGray","cyan","purple","blue","brown","green","red","black"])})
_settings = {}
sm = lua.table()
sm["load"] = lambda f=None: True
sm["save"] = lambda f=None: True
sm["get"]  = lambda k, d=None: _settings.get(k, d)
sm["set"]  = lambda k, v: _settings.update({k: v})
G["settings"] = sm

def make_mon(name, w=24, h=18):
    m = lua.table()
    m["_name"] = name
    m["getSize"]            = lambda: (w, h)
    m["setCursorPos"]       = lambda x, y: None
    m["setTextColor"]       = lambda c: None
    m["setBackgroundColor"] = lambda c: None
    m["setTextScale"]       = lambda s_: None
    m["clear"]              = lambda: None
    m["write"]              = lambda t: None
    return m

def set_monitors(mons):
    p = lua.table()
    p["find"]    = lambda kind=None: tuple(mons)
    p["getName"] = lambda obj: obj["_name"]
    p["wrap"]    = lambda name=None: None
    G["peripheral"] = p

set_monitors([])
monitor = lua.execute(read("monitor.lua"))

# clampStep
sp = py2lua({"step": 0.25, "min": 0.05, "max": 2.5})
rg = py2lua({"step": 5, "min": 5, "max": 64})
check("clampStep up",        abs(monitor.clampStep(1.5, sp, 1) - 1.75) < 1e-9)
check("clampStep clamp max", abs(monitor.clampStep(2.5, sp, 1) - 2.5) < 1e-9)
check("clampStep down",      monitor.clampStep(30, rg, -1) == 25)
check("clampStep clamp min", monitor.clampStep(5, rg, -1) == 5)

# resolve
set_monitors([]);                              check("resolve 0 -> none", monitor.resolve(cfg).mode == "none")
set_monitors([make_mon("monitor_0")]);         check("resolve 1 -> single", monitor.resolve(cfg).mode == "single")
m0, m1 = make_mon("monitor_0"), make_mon("monitor_1")
set_monitors([m1, m0])                          # 非ソート順で渡す
r = monitor.resolve(cfg)
check("resolve 2 -> dual",            r.mode == "dual")
check("resolve main=sorted first",    r.main.name == "monitor_0")
check("resolve config=sorted second", r.config.name == "monitor_1")

# renderConfig → 領域 → hit → applyAction(全経路)
cfg2 = lua.execute(read("config.lua"))
P2 = make_P([]); ui = py2lua({"tab": "MAIN"})
cm = make_mon("monitor_1")

def apply_first(regs, pred):
    for i in range(1, len(regs) + 1):
        a = regs[i].action
        if pred(a):
            monitor.applyAction(a, cfg2, P2, ui)
            return True
    return False

cfg2.priority = "nearest"
regs = monitor.renderConfig(cm, "monitor_1", cfg2)
check("config tap fastestClose",
      apply_first(regs, lambda a: a.set == "priority" and a.val == "fastestClose") and cfg2.priority == "fastestClose")
sp0 = cfg2.speed
regs = monitor.renderConfig(cm, "monitor_1", cfg2)
check("config tap SPEED+", apply_first(regs, lambda a: a.step == "speed" and a.dir == 1) and cfg2.speed > sp0)
b0 = cfg2.burst
regs = monitor.renderConfig(cm, "monitor_1", cfg2)
check("config tap BURST+", apply_first(regs, lambda a: a.step == "burst" and a.dir == 1) and cfg2.burst == b0 + 1)
lg0 = cfg2.leadLag
regs = monitor.renderConfig(cm, "monitor_1", cfg2)
check("config tap LAG+", apply_first(regs, lambda a: a.step == "leadLag" and a.dir == 1) and cfg2.leadLag > lg0)
regs = monitor.renderConfig(cm, "monitor_1", cfg2)
check("config tap CRE ON", apply_first(regs, lambda a: a.set == "creative" and a.val == True) and cfg2.creativeForce == True)
cfg2.targetMode = "hostile"
regs = monitor.renderConfig(cm, "monitor_1", cfg2)
check("config tap TARGET cycles hostile->mobs",
      apply_first(regs, lambda a: a.cycleTarget == True) and cfg2.targetMode == "mobs")
check("settings persisted", _settings.get("turret.priority") == "fastestClose" and _settings.get("turret.creative") == True)

# hit
r1 = regs[1]
check("hit returns action in region", monitor.hit(regs, r1.x1, r1.y) is not None)
check("hit returns nil outside",      monitor.hit(regs, 999, 999) is None)

# render no-error(main/single両タブ)
okr = True
try:
    s2 = turret.new(9); turret.step(make_P([zombie]), cfg2, s2, ballistics, targeting)
    monitor.renderMain(make_mon("monitor_0"), "monitor_0", s2, cfg2)
    monitor.renderSingle(make_mon("monitor_0"), "monitor_0", s2, cfg2, py2lua({"tab": "MAIN"}))
    rs = monitor.renderSingle(make_mon("monitor_0"), "monitor_0", s2, cfg2, py2lua({"tab": "CONFIG"}))
    has_tab = any(rs[i].action.tab is not None for i in range(1, len(rs) + 1))
except Exception as e:
    okr = False; has_tab = False; print("   render error:", e)
check("renderMain/Single no error", okr)
check("single has tab-switch region", has_tab)

# fitScale: スケールでサイズが変わるモニターで、内容が収まる最大スケールを選ぶ
def scalable_mon(base_w, base_h):
    st = {"s": 1.0}
    m = lua.table()
    m["setTextScale"]       = lambda s: st.__setitem__("s", s)
    m["getSize"]            = lambda: (int(base_w / st["s"]), int(base_h / st["s"]))
    m["setBackgroundColor"] = lambda c: None
    m["clear"]              = lambda: None
    return m
check("fitScale picks 1.0 (25x18 monitor, need 22x16)", abs(monitor.fitScale(scalable_mon(25, 18), 22, 16) - 1.0) < 1e-9)
check("fitScale picks 1.5 (40x30 monitor)",              abs(monitor.fitScale(scalable_mon(40, 30), 22, 16) - 1.5) < 1e-9)
check("fitScale falls to 0.5 (tiny monitor)",           abs(monitor.fitScale(scalable_mon(10, 8), 22, 16) - 0.5) < 1e-9)

print(f"\n=== {passed} passed, {failed} failed ===")
sys.exit(1 if failed else 0)

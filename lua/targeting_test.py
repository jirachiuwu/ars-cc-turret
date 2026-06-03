#!/usr/bin/env python3
# targeting.lua の select / priorities を等価移植して機械判定するテスト(段0 と同じ方式・ゲーム不要)。
# closeSpeed = -(V·(P-T))/|P-T|（正=接近）。fastestClose=closeSpeed降順, nearest=dist昇順。
import math, sys

def make_select():
    def nearest(a, b):       return a["dist"] < b["dist"]
    def fastest_close(a, b): return a["closeSpeed"] > b["closeSpeed"]
    priorities = {"nearest": nearest, "fastestClose": fastest_close}

    def select(ents, T, filt, prio_less, lock_uuid=None):
        cands = []
        for e in ents:
            if e["isAlive"] and filt(e):
                e["dist"] = e["distance"]
                dx, dy, dz = e["x"] - T["x"], e["y"] - T["y"], e["z"] - T["z"]
                d = math.sqrt(dx*dx + dy*dy + dz*dz)
                e["closeSpeed"] = -((e["vx"]*dx + e["vy"]*dy + e["vz"]*dz) / d) if d > 1e-6 else 0.0
                cands.append(e)
        if not cands:
            return None
        if lock_uuid:
            for e in cands:
                if e["uuid"] == lock_uuid:
                    return e
        # table.sort 相当(prio_less で昇順) → 先頭が最優先。安定性は問わない(同値は同等)。
        import functools
        cands.sort(key=functools.cmp_to_key(lambda a, b: -1 if prio_less(a, b) else (1 if prio_less(b, a) else 0)))
        return cands[0]
    return select, priorities

def ent(uuid, x, y, z, vx=0, vy=0, vz=0, alive=True, player=False):
    T = {"x":0,"y":0,"z":0}
    dist = math.sqrt((x-T["x"])**2 + (y-T["y"])**2 + (z-T["z"])**2)
    return {"uuid":uuid,"x":x,"y":y,"z":z,"vx":vx,"vy":vy,"vz":vz,
            "distance":dist,"isAlive":alive,"isPlayer":player}

def main():
    select, prio = make_select()
    T = {"x":0,"y":0,"z":0}
    alive_nonplayer = lambda e: (not e["isPlayer"]) and e["isAlive"]
    p, f = 0, 0
    def check(name, got, want):
        nonlocal p, f
        if got == want:
            print(f"PASS {name:34} -> {got}"); p += 1
        else:
            print(f"FAIL {name:34} got={got} want={want}"); f += 1

    # near静止 vs 遠方だが高速接近
    near_static = ent("near", 5, 0, 0, 0, 0, 0)            # dist5, closeSpeed 0
    far_closing = ent("far", 20, 0, 0, -1.0, 0, 0)         # dist20, T方向へ-1.0 → closeSpeed +1.0
    ents = [near_static, far_closing]
    check("nearest picks near", select(ents, T, alive_nonplayer, prio["nearest"])["uuid"], "near")
    check("fastestClose picks far-closing", select(ents, T, alive_nonplayer, prio["fastestClose"])["uuid"], "far")

    # 後退する標的は closeSpeed 負 → 接近/静止より下位
    receding = ent("recede", 10, 0, 0, 1.5, 0, 0)          # closeSpeed -1.5
    crossing = ent("cross", 12, 0, 0, 0, 0, 1.0)           # 横切り closeSpeed ~0
    ents2 = [receding, crossing, far_closing]
    check("fastestClose excludes receding", select(ents2, T, alive_nonplayer, prio["fastestClose"])["uuid"], "far")

    # フィルタ: 死亡/プレイヤーを除外
    dead = ent("dead", 2, 0, 0, alive=False)
    player = ent("plyr", 3, 0, 0, player=True)
    ents3 = [dead, player, near_static]
    check("filter drops dead+player", select(ents3, T, alive_nonplayer, prio["nearest"])["uuid"], "near")

    # ロック継続: lockUuid が候補にあればそれを返す(最優先を上書き)
    check("lock holds target", select(ents, T, alive_nonplayer, prio["fastestClose"], "near")["uuid"], "near")

    # 候補なし → None
    check("no candidates -> None", select([dead], T, alive_nonplayer, prio["nearest"]), None)

    print(f"\n=== {p} passed, {f} failed ===")
    sys.exit(1 if f else 0)

if __name__ == "__main__":
    main()

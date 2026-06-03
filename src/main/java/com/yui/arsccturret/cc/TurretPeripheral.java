package com.yui.arsccturret.cc;

import com.yui.arsccturret.CCTurretTile;
import dan200.computercraft.api.lua.LuaFunction;
import dan200.computercraft.api.peripheral.IPeripheral;
import net.minecraft.world.phys.Vec3;
import org.jetbrains.annotations.Nullable;

import java.util.Map;
import java.util.Optional;

// design.md §2.5: @LuaFunction の薄い口。tileに委譲するだけ。
// world走査read / writeは mainThread=true(CCがサーバメインスレ同期+結果待ち)。純フィールドreadのみ素の@LuaFunction。
public class TurretPeripheral implements IPeripheral {
    private final CCTurretTile tile;

    public TurretPeripheral(CCTurretTile t) { this.tile = t; }

    @Override public String getType() { return "ars_cc_turret"; }
    @Override public boolean equals(@Nullable IPeripheral o) { return o instanceof TurretPeripheral p && p.tile == this.tile; }
    @Override public Object getTarget() { return tile; }

    // --- world走査read: mainThread=true ---
    @LuaFunction(mainThread = true) public final Map<Integer, Map<String, Object>> listEntities(Optional<Double> range) { return tile.luaListEntities(range.orElse(30.0)); }
    @LuaFunction(mainThread = true) public final Map<String, Double> getMuzzle() { return tile.luaMuzzle(); }
    @LuaFunction(mainThread = true) public final Map<String, Double> getAimDir() { return tile.luaAimDir(); }
    @LuaFunction(mainThread = true) public final double getAimError(double dx, double dy, double dz) { return tile.luaAimError(dx, dy, dz); }
    @LuaFunction(mainThread = true) public final double getSource() { return tile.luaMaxSingleSource(); }
    @LuaFunction(mainThread = true) public final int getSpellCost() { return tile.getManaCost(); }
    @LuaFunction(mainThread = true) public final boolean isLoaded() { return !tile.getSpellCaster().getSpell().isEmpty(); }

    // --- 純フィールドread: mainThread不要 ---
    @LuaFunction public final double getProjectileSpeed() { return tile.getProjectileSpeed(); }
    @LuaFunction public final boolean getCreative() { return tile.getCreative(); }
    @LuaFunction public final int getBurst() { return tile.getBurst(); }

    // --- write: mainThread=true(メインスレで直接適用) ---
    @LuaFunction(mainThread = true) public final void aim(double x, double y, double z) { tile.aimVec(new Vec3(x, y, z)); }
    @LuaFunction(mainThread = true) public final boolean fire() { return tile.requestFire(); }
    @LuaFunction(mainThread = true) public final void setProjectileSpeed(double s) { tile.setProjectileSpeed(s); }
    @LuaFunction(mainThread = true) public final void setCreative(boolean on) { tile.setCreative(on); }
    @LuaFunction(mainThread = true) public final void setBurst(int n) { tile.setBurst(n); }
}

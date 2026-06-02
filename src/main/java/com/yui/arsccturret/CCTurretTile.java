package com.yui.arsccturret;

import com.hollingsworth.arsnouveau.api.spell.ISpellCaster;
import com.hollingsworth.arsnouveau.common.block.RotatingSpellTurret;
import com.hollingsworth.arsnouveau.common.block.tile.RotatingTurretTile;
import dan200.computercraft.api.peripheral.IPeripheral;
import com.yui.arsccturret.cc.TurretPeripheral;
import net.minecraft.core.BlockPos;
import net.minecraft.core.BlockSourceImpl;
import net.minecraft.core.Position;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.registries.ForgeRegistries;

import java.util.HashMap;
import java.util.Map;

// design.md §7.2: RotatingTurretTile を継承。弾速(Lua可変/NBT)、aimVec(小数照準)、発射消化、Lua read。
// ★禁止: rotation系フィールドの再宣言(§9.1 Adam's地雷) / 3引数tickのoverride(§1.5)。親フィールド+無引数tick()を使う。
public class CCTurretTile extends RotatingTurretTile {

    private double projectileSpeed = 1.5;            // blocks/tick(config.speed既定と一致)。NBT永続・Lua可変
    private boolean creative = false;                // NBT永続
    private static final double SPEED_MIN = 0.05, SPEED_MAX = 2.5;
    private long lastFireTick = Long.MIN_VALUE;
    private static final long MIN_FIRE_INTERVAL = 1;
    private TurretPeripheral peripheral;

    public CCTurretTile(BlockPos pos, BlockState state) {
        super(CCRegistry.CC_TURRET_TILE.get(), pos, state);
    }

    public IPeripheral getPeripheral() {
        if (peripheral == null) peripheral = new TurretPeripheral(this);
        return peripheral;
    }

    public double getProjectileSpeed() { return projectileSpeed; }
    public void setProjectileSpeed(double v) { projectileSpeed = Math.max(SPEED_MIN, Math.min(SPEED_MAX, v)); setChanged(); }
    public boolean getCreative() { return creative; }
    public void setCreative(boolean b) { creative = b; setChanged(); }

    @Override
    public int getManaCost() { return creative ? 0 : super.getManaCost(); }

    @Override
    public void tick() {                              // 無引数。ITickable経由(§1.5)
        super.tick();                                 // ★必須: 親の server側旋回補間を効かせる
        // 自律探索はJavaに置かない(頭脳=Lua)。発射は peripheral.fire()→requestFire() がメインスレで消化。
    }

    // peripheral(mainThread=true ゆえメインスレ)からの発射要求。器に徹し標的判定はしない。
    public boolean requestFire() {
        if (level == null || level.isClientSide) return false;
        long now = level.getGameTime();
        if (now - lastFireTick < MIN_FIRE_INTERVAL) return false;          // 1tick1発ガード
        if (getSpellCaster().getSpell().isEmpty()) return false;           // 未装填
        if (!(getBlockState().getBlock() instanceof CCTurret block)) return false;
        // Source枯渇は shootSpell 内の takeSourceWithParticles が厳密判定する(二重消費を避けここでは事前チェックしない)。
        block.shootSpell((ServerLevel) level, getBlockPos());              // 正規ルート。Block#tickは使わない
        lastFireTick = now;
        return true;
    }

    // aim(BlockPos,Player) のVec3化(角度式は親と同一、Player依存処理は除去、updateBlock封印・§6.3)
    public void aimVec(Vec3 target) {
        if (level == null) return;
        Vec3 thisVec = Vec3.atCenterOf(getBlockPos());
        Vec3 diff = target.subtract(thisVec);
        Vec3 diff2D = new Vec3(diff.x, diff.z, 0);
        float ax = (float) (angleBetween(new Vec3(0, 1, 0), diff2D) / Math.PI * 180.0);
        if (target.x < thisVec.x) ax = -ax;
        neededRotationX = ax + 90f;                   // 親フィールドへ書く
        Vec3 rotVec = new Vec3(diff.x, 0, diff.z);
        float ay = (float) (angleBetween(diff, rotVec) * 180.0 / Math.PI);
        if (target.y < thisVec.y) ay = -ay;
        neededRotationY = ay;
        setChanged();                                 // ★updateBlock()は呼ばない。tickの0.1f補間で実回転が追従
    }

    // --- Lua向け read(mainThread=true でメインスレ実行される前提) ---
    public Map<Integer, Map<String, Object>> luaListEntities(double range) {
        Map<Integer, Map<String, Object>> out = new HashMap<>();
        Vec3 c = Vec3.atCenterOf(getBlockPos());
        int i = 1;
        for (Entity e : level.getEntities(null, new AABB(getBlockPos()).inflate(range))) {
            if (!(e instanceof LivingEntity)) continue;
            Vec3 dm = e.getDeltaMovement();
            Map<String, Object> m = new HashMap<>();
            m.put("uuid", e.getUUID().toString());
            m.put("type", ForgeRegistries.ENTITY_TYPES.getKey(e.getType()).toString());
            m.put("x", e.getX());  m.put("y", e.getY());  m.put("z", e.getZ());
            m.put("vx", dm.x);     m.put("vy", dm.y);     m.put("vz", dm.z);
            m.put("distance", c.distanceTo(e.position()));
            m.put("isAlive", e.isAlive());
            m.put("isPlayer", e instanceof Player);
            out.put(i++, m);
        }
        return out;
    }

    public Map<String, Double> luaMuzzle() {
        Position p = RotatingSpellTurret.getDispensePosition(new BlockSourceImpl((ServerLevel) level, getBlockPos()), this);
        Map<String, Double> m = new HashMap<>();
        m.put("x", p.x()); m.put("y", p.y()); m.put("z", p.z());
        return m;
    }

    public Map<String, Double> luaAimDir() {
        Vec3 v = getShootAngle().normalize();
        Map<String, Double> m = new HashMap<>();
        m.put("x", v.x()); m.put("y", v.y()); m.put("z", v.z());
        return m;
    }

    public double luaAimError(double dx, double dy, double dz) {
        Vec3 target = new Vec3(dx, dy, dz);
        Vec3 cur = getShootAngle();
        return Math.toDegrees(angleBetween(cur, target));   // angleBetween は radians を返す
    }

    public double luaMaxSingleSource() {
        if (creative) return Double.MAX_VALUE;
        // TODO[実機検証] SourceUtil の単一プロバイダ供給判定API(§2.3)で正確化する。
        // 暫定: 装填コスト相当を返す。実消費は shootSpell の takeSourceWithParticles が厳密判定する。
        return getManaCost();
    }

    @Override
    public void saveAdditional(CompoundTag t) {
        super.saveAdditional(t);                       // spellCaster + rotation系が乗る(継承)
        t.putDouble("projectileSpeed", projectileSpeed);
        t.putBoolean("creative", creative);
    }

    @Override
    public void load(CompoundTag t) {
        super.load(t);
        projectileSpeed = t.contains("projectileSpeed") ? t.getDouble("projectileSpeed") : 1.5;
        creative = t.getBoolean("creative");
    }
}

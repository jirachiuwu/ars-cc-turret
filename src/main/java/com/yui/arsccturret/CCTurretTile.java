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
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.registries.ForgeRegistries;

import java.util.HashMap;
import java.util.Map;

// design.md §7.2: RotatingTurretTile を継承。弾速(Lua可変/NBT)、aimVec(小数照準)、発射消化、Lua read。
// ★禁止: rotation系フィールドの再宣言(§9.1 Adam's地雷) / 3引数tickのoverride(§1.5)。親フィールド+無引数tick()を使う。
public class CCTurretTile extends RotatingTurretTile {

    private double projectileSpeed = 1.5;            // blocks/tick(config.speed既定と一致)。NBT永続・Lua可変
    private boolean creative = false;                // NBT永続
    private int burst = 1;                            // 1トリガーで撃つ弾数(弾幕)。Nが増えるほど自動で扇状に拡散。NBT永続・Lua可変
    private static final double SPEED_MIN = 0.05, SPEED_MAX = 2.5;
    private static final int BURST_MIN = 1, BURST_MAX = 10;
    private long lastFireTick = 0L;                  // 「未発射」。Long.MIN_VALUE だと初弾で now - lastFireTick が long桁あふれ→負値化し連射ガードが常時trueになり永久に撃てない。gameTimeは単調増加で必ず≥0なので0Lが正しい番兵。
    private static final long MIN_FIRE_INTERVAL = 1;
    private TurretPeripheral peripheral;
    // uuid -> 直近サンプルの履歴(各 {x,y,z,gameTime})。複数サンプルの最小二乗で速度を出す(単一差分のノイズを平滑・多角化)。
    // プレイヤーの getDeltaMovement≈0 も位置差分なので回避。
    private final Map<java.util.UUID, java.util.ArrayDeque<double[]>> velHist = new HashMap<>();
    private static final int VEL_SAMPLES = 6;
    // §12.19 CTモデル: uuid -> heading[rad] の履歴。平滑速度からの atan2(vz,vx) を毎tick追加し、unwrap差分の移動平均で水平面ωを出す。
    private final Map<java.util.UUID, java.util.ArrayDeque<Double>> headingHist = new HashMap<>();
    private static final int OMEGA_WINDOW = 8;     // ハーネス機械決定値(§12.19 (f))。S6収束 ≤ 12tick かつ (a)(b)(c)通過の最大平滑。

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
    public int getBurst() { return burst; }
    public void setBurst(int b) { burst = Math.max(BURST_MIN, Math.min(BURST_MAX, b)); setChanged(); }

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
        // ★即時照準(CIWS の高速サーボ相当): 現在角を目標へスナップ。
        // 親の tick は diff×0.1 の緩慢補間で、動く標的だと砲身が lead 点に追いつかず getShootAngle がラグ→
        // 収束ゲート(getAimError≤tol)が常に外れて「追従中ずっと撃てない」。即時化で追従しながら連続射撃できる。
        rotationX = neededRotationX;
        rotationY = neededRotationY;
        setChanged();                                 // updateBlock()は呼ばない(§6.3)。getShootAngle は即 lead 点を向く
    }

    // --- Lua向け read(mainThread=true でメインスレ実行される前提) ---
    public Map<Integer, Map<String, Object>> luaListEntities(double range) {
        Map<Integer, Map<String, Object>> out = new HashMap<>();
        Vec3 c = Vec3.atCenterOf(getBlockPos());
        Vec3 muzzle = muzzleVec();                      // LoS の起点(砲口)
        long now = level.getGameTime();
        java.util.Set<java.util.UUID> seen = new java.util.HashSet<>();
        int i = 1;
        for (Entity e : level.getEntities(null, new AABB(getBlockPos()).inflate(range))) {
            if (!(e instanceof LivingEntity)) continue;
            double[] vel = trackVelocity(e, now);       // 位置差分速度(プレイヤーの getDeltaMovement≈0 を回避)
            double omega = trackOmega(e.getUUID(), vel[0], vel[2]);  // §12.19 水平面ω
            seen.add(e.getUUID());
            double h = e.getBbHeight();
            Vec3 center = new Vec3(e.getX(), e.getY() + h * 0.5, e.getZ());   // 胴体中心
            Map<String, Object> m = new HashMap<>();
            m.put("uuid", e.getUUID().toString());
            m.put("type", ForgeRegistries.ENTITY_TYPES.getKey(e.getType()).toString());
            m.put("x", e.getX());  m.put("y", e.getY());  m.put("z", e.getZ());
            m.put("vx", vel[0]);   m.put("vy", vel[1]);   m.put("vz", vel[2]);
            m.put("ax", vel[3]);   m.put("ay", vel[4]);   m.put("az", vel[5]);   // 加速度(§12.18で実質撤回=常0、フィールドは後方互換で残す)
            // §12.19 CT予測用: 標本平均位置(P_bar)と中央→現在の経過(dtCenter)。Lua側はP_barを始点に dtCenter+lag を渡して時刻整合を取る。
            // ★重要: dtCenter は Java で計算して渡す(Luaは gameTime を持たないため自前計算不能=実機直線でも外すバグの原因になる)。
            m.put("pBarX", vel[6]); m.put("pBarY", vel[7]); m.put("pBarZ", vel[8]);
            m.put("tCenter", vel[9]);
            m.put("dtCenter", (double) now - vel[9]);
            m.put("omega", omega);                       // §12.19 水平面の角速度[rad/tick](Lua側 |ω|>omegaEps で円弧予測、それ以下でCV)
            m.put("height", h);                          // ★足元→胴体中心狙い用(Lua: y + height/2)
            m.put("distance", c.distanceTo(e.position()));
            m.put("isAlive", e.isAlive());
            m.put("isPlayer", e instanceof Player);
            m.put("hostile", e instanceof Enemy);        // ★敵対MOB(Monster/Enemy実装)。Lua の標的モード絞り込み用(modded敵も拾う)
            m.put("los", hasLos(muzzle, center));        // ★視線(砲口→中心にブロックが無いか)。壁越し/地下を撃たない
            out.put(i++, m);
        }
        velHist.keySet().retainAll(seen);                // 範囲外/消えた標的の追跡を掃除
        headingHist.keySet().retainAll(seen);            // §12.19 同じく heading 履歴も
        return out;
    }

    // 速度を複数サンプルの線形最小二乗(傾き)で出す。平滑で安定、定常運動では厳密。
    // 加速度(2次)はサンプルレートが低く(lag 数tick)ノイズが暴れて偏差が荒ぶるため不採用(ax/ay/az=0・§12.18)。曲線は§12.19 CTモデルで吸収。
    // getDeltaMovement に頼らない(プレイヤーでサーバ側≈0=残像撃ちの元)。
    // 返り値 {vx, vy, vz, 0, 0, 0, xBar, yBar, zBar, tBar}: lsqの傾き=中央時刻の接線速度 + 標本平均位置(=中央時刻位置近似) + 中央時刻。
    private double[] trackVelocity(Entity e, long now) {
        java.util.ArrayDeque<double[]> hist = velHist.computeIfAbsent(e.getUUID(), k -> new java.util.ArrayDeque<>());
        if (hist.isEmpty() || hist.peekLast()[3] < now) {          // 同tick重複は追加しない
            hist.addLast(new double[]{e.getX(), e.getY(), e.getZ(), now});
            while (hist.size() > VEL_SAMPLES) hist.removeFirst();
        }
        int n = hist.size();
        if (n < 2) { Vec3 dm = e.getDeltaMovement(); return new double[]{dm.x, dm.y, dm.z, 0, 0, 0, e.getX(), e.getY(), e.getZ(), (double) now}; }
        double tBar = 0, xBar = 0, yBar = 0, zBar = 0;
        for (double[] s : hist) { tBar += s[3]; xBar += s[0]; yBar += s[1]; zBar += s[2]; }
        tBar /= n; xBar /= n; yBar /= n; zBar /= n;
        double sxx = 0, sx = 0, sy = 0, sz = 0;
        for (double[] s : hist) { double dt = s[3] - tBar; sxx += dt * dt; sx += dt * s[0]; sy += dt * s[1]; sz += dt * s[2]; }
        if (sxx < 1e-9) { Vec3 dm = e.getDeltaMovement(); return new double[]{dm.x, dm.y, dm.z, 0, 0, 0, xBar, yBar, zBar, tBar}; }
        return new double[]{sx / sxx, sy / sxx, sz / sxx, 0, 0, 0, xBar, yBar, zBar, tBar};
    }

    // §12.19 平滑速度の heading=atan2(vz,vx) 差分(±πラップ補正=unwrap)を OMEGA_WINDOW 個の移動平均で水平面ω[rad/tick]を出す。
    // 速度がほぼゼロ(|V_h|²<1e-6)の時は heading が定義できないので履歴クリア+0返し(=純CV扱い)。
    private double trackOmega(java.util.UUID uuid, double vx, double vz) {
        if (vx * vx + vz * vz < 1e-6) { headingHist.remove(uuid); return 0.0; }
        double heading = Math.atan2(vz, vx);
        java.util.ArrayDeque<Double> hh = headingHist.computeIfAbsent(uuid, k -> new java.util.ArrayDeque<>());
        hh.addLast(heading);
        while (hh.size() > OMEGA_WINDOW + 1) hh.removeFirst();      // 差分OMEGA_WINDOW個取れる分だけ
        int n = hh.size();
        if (n < 2) return 0.0;
        Double[] arr = hh.toArray(new Double[0]);
        double sum = 0;
        int cnt = 0;
        for (int k = 1; k < n; k++) {
            double d = arr[k] - arr[k - 1];
            if (d >  Math.PI) d -= 2 * Math.PI;                    // unwrap(±πジャンプ潰し)
            else if (d < -Math.PI) d += 2 * Math.PI;
            sum += d; cnt++;
        }
        return sum / cnt;
    }

    // ループ高速化: 1回の mainThread 同期で必要データを全部返す(getMuzzle+listEntities+弾速+マナ等の個別呼びを集約)。
    public Map<String, Object> luaScan(double range) {
        Map<String, Object> r = new HashMap<>();
        r.put("muzzle", luaMuzzle());
        r.put("entities", luaListEntities(range));
        r.put("speed", projectileSpeed);
        r.put("creative", creative);
        r.put("cost", getManaCost());
        r.put("loaded", !getSpellCaster().getSpell().isEmpty());
        r.put("source", luaMaxSingleSource());
        return r;
    }

    // aim + 結果の照準誤差[度]を1呼びで返す(aim と getAimError の往復を1回に)。
    public double luaAimAndErr(double x, double y, double z) {
        aimVec(new Vec3(x, y, z));
        Vec3 mz = muzzleVec();
        return luaAimError(x - mz.x, y - mz.y, z - mz.z);
    }

    public Map<String, Double> luaMuzzle() {
        Vec3 p = muzzleVec();
        Map<String, Double> m = new HashMap<>();
        m.put("x", p.x); m.put("y", p.y); m.put("z", p.z);
        return m;
    }

    // 砲口位置(発射点 = ブロック中心 + 0.5·照準ベクトル)。luaMuzzle と LoS 起点で共用。
    private Vec3 muzzleVec() {
        Position p = RotatingSpellTurret.getDispensePosition(new BlockSourceImpl((ServerLevel) level, getBlockPos()), this);
        return new Vec3(p.x(), p.y(), p.z());
    }

    // 砲口 from → 標的中心 to の間に遮蔽ブロックがあるか。MISS(到達) か、ヒットが自分のブロック(自己ヒット)なら視線あり。
    private boolean hasLos(Vec3 from, Vec3 to) {
        BlockHitResult hit = level.clip(new ClipContext(from, to, ClipContext.Block.COLLIDER, ClipContext.Fluid.NONE, null));
        return hit.getType() == HitResult.Type.MISS || hit.getBlockPos().equals(getBlockPos());
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
        t.putInt("burst", burst);
    }

    @Override
    public void load(CompoundTag t) {
        super.load(t);
        projectileSpeed = t.contains("projectileSpeed") ? t.getDouble("projectileSpeed") : 1.5;
        creative = t.getBoolean("creative");
        burst = t.contains("burst") ? t.getInt("burst") : 1;
    }
}

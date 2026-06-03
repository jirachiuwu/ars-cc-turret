package com.yui.arsccturret;

import com.hollingsworth.arsnouveau.api.ANFakePlayer;
import com.hollingsworth.arsnouveau.api.spell.*;
import com.hollingsworth.arsnouveau.api.spell.wrapped_caster.TileCaster;
import com.hollingsworth.arsnouveau.api.util.SourceUtil;
import com.hollingsworth.arsnouveau.common.block.RotatingSpellTurret;
import com.hollingsworth.arsnouveau.common.entity.EntityProjectileSpell;
import com.hollingsworth.arsnouveau.common.network.Networking;
import com.hollingsworth.arsnouveau.common.network.PacketOneShotAnimation;
import com.hollingsworth.arsnouveau.common.spell.method.MethodProjectile;
import net.minecraft.core.BlockPos;
import net.minecraft.core.BlockSourceImpl;
import net.minecraft.core.Direction;
import net.minecraft.core.Position;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.player.Player;
import net.minecraft.sounds.SoundSource;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.common.util.FakePlayer;

import java.util.HashMap;

// design.md §5.3 / §6.1: RotatingSpellTurret を継承。自前 CC_BEHAVIOR_MAP(Form許可リスト=Projectile主軸)、
// shootSpell override(弾速=Lua可変フィールド)、redstone発射経路の封鎖(Block#tick / neighborChanged を空に)。
public class CCTurret extends RotatingSpellTurret {

    public static final HashMap<AbstractCastMethod, ITurretBehavior> CC_BEHAVIOR_MAP = new HashMap<>();

    static {
        // Projectile: 効果/VFX/色/寿命/衝突は EntityProjectileSpell + resolver に委譲(器に徹する)。自前は弾速だけ。
        CC_BEHAVIOR_MAP.put(MethodProjectile.INSTANCE, new ITurretBehavior() {
            @Override
            public void onCast(SpellResolver resolver, ServerLevel world, BlockPos pos, Player fakePlayer, Position ipos, Direction dir) {
                if (!(world.getBlockEntity(pos) instanceof CCTurretTile tile)) return;
                EntityProjectileSpell spell = new EntityProjectileSpell(world, resolver); // ← 効果/色/VFXはここで乗る
                spell.setOwner(fakePlayer);
                spell.setPos(ipos.x(), ipos.y(), ipos.z());
                Vec3 v = tile.getShootAngle().normalize();          // 継承した照準ベクトル(pure luck式・触らない)
                float velocity = (float) tile.getProjectileSpeed(); // AN標準式を捨て、フィールド値=Lua可変
                spell.shoot(v.x(), v.y(), v.z(), velocity, 0);      // inaccuracy=0 必須(velocity厳密化)
                world.addFreshEntity(spell);
            }
        });
        // MethodTouch は §11(初版後追い)
    }

    // redstone発射経路の封鎖(§6.1): 親 BasicSpellTurret.tick(...) は redstone scheduleTick から shootSpell を直叩きする。
    // CC完全主役を成立させるため、Block#tick と neighborChanged を空 override して塞ぐ。
    @Override
    public void tick(BlockState s, ServerLevel w, BlockPos p, RandomSource r) { /* redstone発射を無効化 */ }

    @Override
    public void neighborChanged(BlockState s, Level w, BlockPos p, Block b, BlockPos from, boolean moving) {
        /* scheduleTick を張らない: redstoneトリガを無効化(CC専用) */
    }

    // shootSpell: 正規ルート。引数を本体 RotatingSpellTurret.shootSpell と1対1一致させる(効果不乗の回避)。
    @Override
    public void shootSpell(ServerLevel world, BlockPos pos) {
        if (!(world.getBlockEntity(pos) instanceof CCTurretTile tile)) return;
        ISpellCaster caster = tile.getSpellCaster();
        if (caster.getSpell().isEmpty()) return;
        int manaCost = tile.getManaCost();                                       // creative時 tile が0返す
        if (manaCost > 0 && SourceUtil.takeSourceWithParticles(pos, world, 10, manaCost) == null) return;
        Networking.sendToNearby(world, pos, new PacketOneShotAnimation(pos));     // recoilアニメ
        Position ipos = getDispensePosition(new BlockSourceImpl(world, pos), tile); // 継承(Rotating版)
        FakePlayer fake = ANFakePlayer.getPlayer(world);
        fake.setPos(pos.getX(), pos.getY(), pos.getZ());
        EntitySpellResolver resolver = new EntitySpellResolver(
                new SpellContext(world, caster.getSpell(), fake, new TileCaster(tile, SpellContext.CasterType.TURRET)));
        if (resolver.castType != null && CC_BEHAVIOR_MAP.containsKey(resolver.castType)) {
            CC_BEHAVIOR_MAP.get(resolver.castType)
                    .onCast(resolver, world, pos, fake, ipos, orderedByNearest(tile)[0].getOpposite());
            caster.playSound(pos, world, null, caster.getCurrentSound(), SoundSource.BLOCKS);
        }
    }

    // getRenderShape は親(ENTITYBLOCK_ANIMATED)のまま=GeckoLib の GeoBlockRenderer(client.CCTurretRenderer)が
    // Ars 純正タレットの geo/texture/反動アニメで描画する。静的モデルには戻さない。
    @Override
    public BlockEntity newBlockEntity(BlockPos pos, BlockState state) {
        return new CCTurretTile(pos, state);
    }
    // ★ setPlacedBy / getShootAngle / orderedByNearest / getDispensePosition は override しない(§9.1の罠回避)
}

package com.yui.arsccturret.client;

import com.yui.arsccturret.CCTurretTile;
import net.minecraft.resources.ResourceLocation;
import software.bernie.geckolib.model.GeoModel;

// Ars 純正 rotating spell turret の geo/texture/animation を流用(依存している Ars 本体のアセットを参照)。
// tile は BasicSpellTurretTile(GeoBlockEntity+registerControllers)を継承済みなので、これで反動アニメも乗る。
public class CCTurretModel extends GeoModel<CCTurretTile> {
    private static final ResourceLocation MODEL = new ResourceLocation("ars_nouveau", "geo/spell_turret.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("ars_nouveau", "textures/block/spell_turret.png");
    private static final ResourceLocation ANIM = new ResourceLocation("ars_nouveau", "animations/spell_turret_animations.json");

    @Override public ResourceLocation getModelResource(CCTurretTile t) { return MODEL; }
    @Override public ResourceLocation getTextureResource(CCTurretTile t) { return TEXTURE; }
    @Override public ResourceLocation getAnimationResource(CCTurretTile t) { return ANIM; }
}

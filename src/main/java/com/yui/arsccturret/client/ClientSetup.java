package com.yui.arsccturret.client;

import com.yui.arsccturret.CCRegistry;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.client.event.EntityRenderersEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

// クライアント専用。MOD バスの RegisterRenderers で GeoBlockRenderer を CCTurretTile に登録。
@Mod.EventBusSubscriber(modid = CCRegistry.MODID, bus = Mod.EventBusSubscriber.Bus.MOD, value = Dist.CLIENT)
public class ClientSetup {
    @SubscribeEvent
    public static void onRegisterRenderers(EntityRenderersEvent.RegisterRenderers event) {
        event.registerBlockEntityRenderer(CCRegistry.CC_TURRET_TILE.get(), ctx -> new CCTurretRenderer());
    }
}

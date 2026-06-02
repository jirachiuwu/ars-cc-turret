package com.yui.arsccturret;

import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;

// @Mod エントリ。レジストリを MOD バスに載せる。
@Mod(CCRegistry.MODID)
public class ArsCcTurret {
    public ArsCcTurret() {
        IEventBus bus = FMLJavaModLoadingContext.get().getModEventBus();
        CCRegistry.init(bus);
    }
}

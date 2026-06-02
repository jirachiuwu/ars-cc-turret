package com.yui.arsccturret.cc;

import com.yui.arsccturret.CCRegistry;
import com.yui.arsccturret.CCTurretTile;
import dan200.computercraft.api.ForgeComputerCraftAPI;
import net.minecraftforge.common.util.LazyOptional;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.event.lifecycle.FMLCommonSetupEvent;

// design.md §7.6: IPeripheralProvider を ForgeComputerCraftAPI で FMLCommonSetupEvent.enqueueWork 内に登録。
// 依存は forge-api の公開APIのみ。内部 shared.Capabilities には触れない。
@Mod.EventBusSubscriber(modid = CCRegistry.MODID, bus = Mod.EventBusSubscriber.Bus.MOD)
public class CcPeripheralSetup {

    @SubscribeEvent
    static void onSetup(FMLCommonSetupEvent e) {
        e.enqueueWork(() -> ForgeComputerCraftAPI.registerPeripheralProvider(
                (world, pos, side) -> (world.getBlockEntity(pos) instanceof CCTurretTile tile)
                        ? LazyOptional.of(tile::getPeripheral)
                        : LazyOptional.empty()));
    }
}

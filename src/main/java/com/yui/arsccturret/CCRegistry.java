package com.yui.arsccturret;

import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.ForgeRegistries;
import net.minecraftforge.registries.RegistryObject;

// design.md §7.1: 自前 DeferredRegister。本体ANのprivate registryヘルパは使えないので標準で再現。
public class CCRegistry {
    public static final String MODID = "arsccturret";

    public static final DeferredRegister<Block> BLOCKS = DeferredRegister.create(ForgeRegistries.BLOCKS, MODID);
    public static final DeferredRegister<Item> ITEMS = DeferredRegister.create(ForgeRegistries.ITEMS, MODID);
    public static final DeferredRegister<BlockEntityType<?>> TILES = DeferredRegister.create(ForgeRegistries.BLOCK_ENTITY_TYPES, MODID);

    // CCTurret は引数なしctor(親 BasicSpellTurret() の defaultProperties を継承)。Properties版はchainにRotatingSpellTurret(Properties)が無く不可。
    public static final RegistryObject<CCTurret> CC_TURRET = BLOCKS.register("cc_turret", CCTurret::new);
    public static final RegistryObject<BlockItem> CC_TURRET_ITEM = ITEMS.register("cc_turret",
            () -> new BlockItem(CC_TURRET.get(), new Item.Properties()));
    // tick駆動の保証(§1.5): CC_TURRET_TILE 自身をBE-typeに使うので createTickerHelper の type2==type1 が成立
    public static final RegistryObject<BlockEntityType<CCTurretTile>> CC_TURRET_TILE = TILES.register("cc_turret",
            () -> BlockEntityType.Builder.of(CCTurretTile::new, CC_TURRET.get()).build(null));

    public static void init(IEventBus bus) {
        BLOCKS.register(bus);
        ITEMS.register(bus);
        TILES.register(bus);
    }
}

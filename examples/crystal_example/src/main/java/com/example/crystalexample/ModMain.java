package com.example.crystalexample;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.itemgroup.v1.ItemGroupEvents;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.CreativeModeTabs;
import net.minecraft.world.item.Item;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockBehaviour;

public class ModMain implements ModInitializer {
    public static final String MOD_ID = "crystal_example";

    private static ResourceLocation id(String path) {
        return ResourceLocation.fromNamespaceAndPath(MOD_ID, path);
    }

    public static final Item SKY_CRYSTAL = Registry.register(BuiltInRegistries.ITEM, id("sky_crystal"), new Item(new Item.Properties()));
    public static final Item LUNAR_GEM = Registry.register(BuiltInRegistries.ITEM, id("lunar_gem"), new Item(new Item.Properties()));
    public static final Item SAPPHIRE = Registry.register(BuiltInRegistries.ITEM, id("sapphire"), new Item(new Item.Properties()));
    public static final Block CRYSTAL_STONE = Registry.register(BuiltInRegistries.BLOCK, id("crystal_stone"), new Block(BlockBehaviour.Properties.of().strength(3.0F)));
    public static final Item CRYSTAL_STONE_ITEM = Registry.register(BuiltInRegistries.ITEM, id("crystal_stone"), new BlockItem(CRYSTAL_STONE, new Item.Properties()));

    @Override
    public void onInitialize() {
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.INGREDIENTS).register(entries -> entries.accept(SKY_CRYSTAL));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.INGREDIENTS).register(entries -> entries.accept(LUNAR_GEM));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.INGREDIENTS).register(entries -> entries.accept(SAPPHIRE));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.BUILDING_BLOCKS).register(entries -> entries.accept(CRYSTAL_STONE_ITEM));
    }
}

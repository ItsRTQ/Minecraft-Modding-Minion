package com.example.crystalexample;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.itemgroup.v1.ItemGroupEvents;
import net.minecraft.block.AbstractBlock;
import net.minecraft.block.Block;
import net.minecraft.item.BlockItem;
import net.minecraft.item.Item;
import net.minecraft.item.ItemGroups;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;
import net.minecraft.util.Identifier;

public class ModMain implements ModInitializer {
    public static final String MOD_ID = "crystal_example";
    public static final Item SKY_CRYSTAL = Registry.register(Registries.ITEM, Identifier.of(MOD_ID, "sky_crystal"), new Item(new Item.Settings()));
    public static final Item LUNAR_GEM = Registry.register(Registries.ITEM, Identifier.of(MOD_ID, "lunar_gem"), new Item(new Item.Settings()));
    public static final Block CRYSTAL_STONE = Registry.register(Registries.BLOCK, Identifier.of(MOD_ID, "crystal_stone"), new Block(AbstractBlock.Settings.create().strength(3.0F)));
    public static final Item CRYSTAL_STONE_ITEM = Registry.register(Registries.ITEM, Identifier.of(MOD_ID, "crystal_stone"), new BlockItem(CRYSTAL_STONE, new Item.Settings()));
    @Override public void onInitialize() {
        ItemGroupEvents.modifyEntriesEvent(ItemGroups.INGREDIENTS).register(entries -> entries.add(SKY_CRYSTAL));
        ItemGroupEvents.modifyEntriesEvent(ItemGroups.INGREDIENTS).register(entries -> entries.add(LUNAR_GEM));
        ItemGroupEvents.modifyEntriesEvent(ItemGroups.BUILDING_BLOCKS).register(entries -> entries.add(CRYSTAL_STONE_ITEM));
    }
}

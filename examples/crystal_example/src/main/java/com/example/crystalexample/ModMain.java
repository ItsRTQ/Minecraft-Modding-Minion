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
import net.fabricmc.fabric.api.itemgroup.v1.FabricItemGroup;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.item.ItemStack;

public class ModMain implements ModInitializer {
    public static final String MOD_ID = "crystal_example";

    private static ResourceLocation id(String path) {
        return ResourceLocation.fromNamespaceAndPath(MOD_ID, path);
    }

    public static final Item SKY_CRYSTAL = Registry.register(BuiltInRegistries.ITEM, id("sky_crystal"), new Item(new Item.Properties()));
    public static final Item LUNAR_GEM = Registry.register(BuiltInRegistries.ITEM, id("lunar_gem"), new Item(new Item.Properties()));
    public static final Block CRYSTAL_STONE = Registry.register(BuiltInRegistries.BLOCK, id("crystal_stone"), new Block(BlockBehaviour.Properties.of().strength(3.0F)));
    public static final Item CRYSTAL_STONE_ITEM = Registry.register(BuiltInRegistries.ITEM, id("crystal_stone"), new BlockItem(CRYSTAL_STONE, new Item.Properties()));
    public static final Block CRYSTAL_ORE = Registry.register(BuiltInRegistries.BLOCK, id("crystal_ore"), new Block(BlockBehaviour.Properties.of().strength(3.0F)));
    public static final Item CRYSTAL_ORE_ITEM = Registry.register(BuiltInRegistries.ITEM, id("crystal_ore"), new BlockItem(CRYSTAL_ORE, new Item.Properties()));

    public static final ResourceKey<CreativeModeTab> TAB_KEY = ResourceKey.create(Registries.CREATIVE_MODE_TAB, id("crystal_example_tab"));
    public static final CreativeModeTab TAB = FabricItemGroup.builder()
        .icon(() -> new ItemStack(SKY_CRYSTAL))
        .title(Component.translatable("itemGroup.crystal_example.crystal_example_tab"))
        .displayItems((params, output) -> {
            output.accept(SKY_CRYSTAL);
            output.accept(LUNAR_GEM);
            output.accept(CRYSTAL_STONE_ITEM);
            output.accept(CRYSTAL_ORE_ITEM);
        })
        .build();

    @Override
    public void onInitialize() {
        Registry.register(BuiltInRegistries.CREATIVE_MODE_TAB, TAB_KEY, TAB);
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.INGREDIENTS).register(entries -> entries.accept(SKY_CRYSTAL));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.INGREDIENTS).register(entries -> entries.accept(LUNAR_GEM));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.BUILDING_BLOCKS).register(entries -> entries.accept(CRYSTAL_STONE_ITEM));
        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.BUILDING_BLOCKS).register(entries -> entries.accept(CRYSTAL_ORE_ITEM));
    }
}

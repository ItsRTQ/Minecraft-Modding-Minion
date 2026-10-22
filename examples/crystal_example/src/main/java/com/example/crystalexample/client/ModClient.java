package com.example.crystalexample.client;

import com.example.crystalexample.ModMain;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.rendering.v1.EntityRendererRegistry;

public class ModClient implements ClientModInitializer {
    @Override
    public void onInitializeClient() {
        EntityRendererRegistry.register(ModMain.CRYSTAL_CRITTER, CrystalCritterRenderer::new);
    }
}

package com.example.crystalexample.client;

import com.example.crystalexample.ModMain;
import com.example.crystalexample.entity.CrystalCritterEntity;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraft.resources.ResourceLocation;
import software.bernie.geckolib.model.DefaultedEntityGeoModel;
import software.bernie.geckolib.renderer.GeoEntityRenderer;

public class CrystalCritterRenderer extends GeoEntityRenderer<CrystalCritterEntity> {
    public CrystalCritterRenderer(EntityRendererProvider.Context context) {
        super(context, new DefaultedEntityGeoModel<>(ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "crystal_critter")));
    }
}

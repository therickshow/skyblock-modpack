package io.github.therickshow.skyblockqol;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.packs.PackSelectionScreen;
import net.minecraft.network.chat.Component;

/**
 * Opens the vanilla Resource Packs screen, built exactly the way Options → Resource Packs
 * builds it in Minecraft 26.2 (OptionsScreen, read with javap).
 */
final class ResourcePacksButton {

    private ResourcePacksButton() {
    }

    static Screen open(Screen parent) {
        Minecraft minecraft = Minecraft.getInstance();
        return new PackSelectionScreen(
                minecraft.getResourcePackRepository(),
                // Runs when you leave the screen: save the chosen packs (vanilla's applyPacks
                // does the same), then go back to Mod Menu.
                packs -> {
                    minecraft.options.updateResourcePacks(packs);
                    minecraft.gui.setScreen(parent);
                },
                minecraft.getResourcePackDirectory(),
                Component.translatable("resourcePack.title"));
    }
}

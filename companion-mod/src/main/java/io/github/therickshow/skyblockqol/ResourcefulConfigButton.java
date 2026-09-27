package io.github.therickshow.skyblockqol;

import com.teamresourceful.resourcefulconfig.api.client.ResourcefulConfigScreen;
import com.terraformersmc.modmenu.api.ConfigScreenFactory;
import net.minecraft.client.gui.screens.Screen;

/**
 * Opens a mod's settings through Resourceful Config.
 *
 * getFactory(modId) looks up the configs that mod registered (Feesh, SkyBlock Profile Viewer
 * and Auth Me each register one under their mod ID) and returns "given the screen to go back
 * to, build the settings screen". Kept in its own class so Resourceful Config's classes are
 * only loaded when it's actually installed.
 */
final class ResourcefulConfigButton {

    private ResourcefulConfigButton() {
    }

    static ConfigScreenFactory<Screen> forMod(String modId) {
        // Looked up when the button is clicked, not at startup, because mods register their
        // configs during their own startup, which may run after Mod Menu asks us.
        return parent -> ResourcefulConfigScreen.getFactory(modId).apply(parent);
    }
}

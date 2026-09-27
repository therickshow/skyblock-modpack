package io.github.therickshow.skyblockqol;

import com.terraformersmc.modmenu.api.ConfigScreenFactory;
import net.caffeinemc.mods.sodium.client.gui.VideoSettingsScreen;
import net.minecraft.client.gui.screens.Screen;

/**
 * Opens Sodium's video settings, the same method Sodium itself calls when you click
 * Options → Video Settings. Kept in its own class so Sodium's classes are only loaded when
 * Sodium is installed.
 */
final class SodiumButton {

    private SodiumButton() {
    }

    static ConfigScreenFactory<Screen> forVideoSettings() {
        return VideoSettingsScreen::createScreen;
    }
}

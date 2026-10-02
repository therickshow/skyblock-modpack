package io.github.therickshow.skyblockqol;

import com.terraformersmc.modmenu.api.ConfigScreenFactory;
import com.terraformersmc.modmenu.api.ModMenuApi;
import net.fabricmc.loader.api.FabricLoader;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Mod Menu calls this once at startup. The map we return says "for mod X, this is how to
 * open its settings screen". Mod Menu then shows a settings button for X.
 *
 * Mod Menu only uses our entry when X has no button of its own, so this can never replace a
 * mod's real button. Each entry is also only added when that mod is actually installed.
 */
public class ModMenuButtons implements ModMenuApi {

    @Override
    public Map<String, ConfigScreenFactory<?>> getProvidedConfigScreenFactories() {
        FabricLoader loader = FabricLoader.getInstance();
        Map<String, ConfigScreenFactory<?>> buttons = new HashMap<>();

        // Sodium's video settings screen also holds Sodium Extra's pages, and Reese's Sodium
        // Options restyles it, so all three buttons open the same screen.
        if (loader.isModLoaded("sodium")) {
            for (String modId : List.of("sodium", "sodium-extra", "reeses-sodium-options")) {
                if (loader.isModLoaded(modId)) {
                    buttons.put(modId, SodiumButton.forVideoSettings());
                }
            }
        }

        // Catharsis has no settings of its own: each texture pack that uses it has options,
        // found in the Resource Packs screen.
        if (loader.isModLoaded("catharsis")) {
            buttons.put("catharsis", ResourcePacksButton::open);
        }

        return buttons;
    }
}

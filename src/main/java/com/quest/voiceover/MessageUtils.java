package com.quest.voiceover;

import javax.inject.Inject;
import java.util.regex.Pattern;

public class MessageUtils {

    private static final String PLAYER = "Player";
    private static final String PLAYER_NAME_PLACEHOLDER = "[player name]";
    // Pattern to match RuneScape color tags like <col=0000ff> and </col>
    private static final Pattern COLOR_TAG_PATTERN = Pattern.compile("</?col[^>]*>");

    @Inject
    private HashUtil hashUtil;

    String name;
    String text;
    String id;

    public MessageUtils(String message, String playerName) {
        String[] messageArray = message.split("\\|", 2);

        // Convert player's character name to "Player" for database matching
        String rawName = messageArray[0];
        this.name = isPlayerName(rawName, playerName) ? PLAYER : rawName;

        // Strip color tags and replace player name with placeholder for matching
        String rawText = messageArray[1].trim();
        rawText = stripColorTags(rawText);
        this.text = replacePlayerName(rawText, playerName);

        this.id = HashUtil.convertToMD5(this.name + "|" + this.text);
    }

    /**
     * Check if the given name matches the player's name.
     * Uses case-insensitive comparison to handle variations.
     */
    private static boolean isPlayerName(String name, String playerName) {
        if (name == null || playerName == null) {
            return false;
        }
        // Normalize spaces: replace non-breaking space (char 160) with regular space (char 32)
        // RuneScape uses non-breaking spaces in chat messages
        String normalizedName = normalizeSpaces(name.trim());
        String normalizedPlayerName = normalizeSpaces(playerName.trim());

        return normalizedName.equalsIgnoreCase(normalizedPlayerName);
    }

    /**
     * Normalize all whitespace characters to regular spaces.
     * Handles non-breaking spaces (char 160) used by RuneScape.
     */
    private static String normalizeSpaces(String text) {
        // Replace non-breaking space (U+00A0, char 160) with regular space
        return text.replace('\u00A0', ' ');
    }

    /**
     * Remove RuneScape color tags from text.
     * Handles tags like <col=0000ff>, <col=000000>, </col>, etc.
     */
    private static String stripColorTags(String text) {
        return COLOR_TAG_PATTERN.matcher(text).replaceAll("");
    }

    /**
     * Replace the player's actual name with [player name] placeholder
     * to match the database format.
     */
    private static String replacePlayerName(String text, String playerName) {
        if (playerName == null || playerName.isEmpty()) {
            return text;
        }
        // Normalize spaces in text first (handle non-breaking spaces)
        String normalizedText = normalizeSpaces(text);
        String normalizedPlayerName = normalizeSpaces(playerName);
        // Case-insensitive replacement
        return normalizedText.replaceAll("(?i)" + Pattern.quote(normalizedPlayerName), PLAYER_NAME_PLACEHOLDER);
    }
}

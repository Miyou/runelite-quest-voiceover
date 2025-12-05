package com.quest.voiceover;

import javax.inject.Inject;
import java.util.regex.Pattern;

public class MessageUtils {

    private static final String PLAYER = "Player";
    // Pattern to match RuneScape color tags like <col=0000ff> and </col>
    private static final Pattern COLOR_TAG_PATTERN = Pattern.compile("</?col[^>]*>");

    @Inject
    private HashUtil hashUtil;

    String name;
    String text;
    String id;

    public MessageUtils(String message, String playerName) {
        String[] messageArray = message.split("\\|", 2);
        this.name = messageArray[0].equals(playerName) ? PLAYER : messageArray[0];
        // Strip color tags from text before matching
        this.text = stripColorTags(messageArray[1].trim());
        this.id = HashUtil.convertToMD5(this.name + "|" + this.text);
    }

    /**
     * Remove RuneScape color tags from text.
     * Handles tags like <col=0000ff>, <col=000000>, </col>, etc.
     */
    private static String stripColorTags(String text) {
        return COLOR_TAG_PATTERN.matcher(text).replaceAll("");
    }
}

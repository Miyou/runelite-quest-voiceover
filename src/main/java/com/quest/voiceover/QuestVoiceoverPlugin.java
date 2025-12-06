package com.quest.voiceover;

import com.google.inject.Provides;
import javax.inject.Inject;
import lombok.extern.slf4j.Slf4j;
import net.runelite.api.coords.WorldPoint;
import net.runelite.client.eventbus.Subscribe;
import net.runelite.client.plugins.PluginDescriptor;

import com.quest.voiceover.database.*;
import net.runelite.api.*;
import net.runelite.api.events.*;
import net.runelite.api.widgets.InterfaceID;
import net.runelite.api.widgets.Widget;
import net.runelite.client.config.ConfigManager;
import net.runelite.client.plugins.Plugin;
import net.runelite.client.eventbus.EventBus;
import okhttp3.OkHttpClient;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.ScheduledExecutorService;

@Slf4j
@PluginDescriptor(
	name = "Quest Voiceover"
)
public class QuestVoiceoverPlugin extends Plugin
{
	@Inject
	private Client client;

	@Inject
	private DatabaseManager databaseManager;

	@Inject
	private EventBus eventBus;

	@Inject
	private SoundEngine soundEngine;

	@Inject
	private DialogEngine dialogEngine;

	@Inject
	private OkHttpClient okHttpClient;

	@Inject
	private ScheduledExecutorService executor;

	private String playerName = null;
	private Boolean isQuestDialog = false;
	private String questName = null;
	// Track the last matched text per character to handle incremental dialog
	private String lastMatchedCharacter = null;
	private String lastMatchedText = null;

	@Override
	protected void startUp() throws Exception
	{
		eventBus.register(soundEngine);
		log.info("Quest Voiceover plugin started!");

		executor.submit(() -> {
			DatabaseVersionManager.prepareDatabaseSource(okHttpClient);
			this.databaseManager.initializeConnection();
		});
	}

	@Override
	protected void shutDown() throws Exception
	{
		eventBus.unregister(soundEngine);
		log.info("Quest Voiceover plugin stopped!");

		databaseManager.closeConnection();
	}

	@Subscribe
	public void onChatMessage(ChatMessage chatMessage) {
		if (chatMessage.getType().equals(ChatMessageType.DIALOG)) {
			if (this.playerName == null) {
				this.playerName = this.client.getLocalPlayer().getName();
				log.info("Player name set to: '{}'", this.playerName);
			}

			String rawMessage = chatMessage.getMessage();
			log.info("Raw message: '{}'", rawMessage);
			MessageUtils message = new MessageUtils(rawMessage, this.playerName);
			log.info("Dialog received - Character: '{}', Text: '{}' (playerName: '{}')", message.name, message.text, this.playerName);

			try {
				String textToSearch = message.text;

				// Check if this message is an incremental update (starts with the last matched text)
				// If so, extract just the new part to search for
				if (lastMatchedCharacter != null && lastMatchedText != null
						&& message.name.equals(lastMatchedCharacter)
						&& message.text.startsWith(lastMatchedText)) {
					// Extract the new portion after the last matched text
					String remainder = message.text.substring(lastMatchedText.length()).trim();
					if (!remainder.isEmpty()) {
						log.info("Detected incremental dialog, searching for remainder: '{}'", remainder);
						textToSearch = remainder;
					}
				}

				// Try to find a match for the text
				String[] result = findDialogMatch(message.name, textToSearch);

				// If no match found for remainder, try the full text
				if (result == null && !textToSearch.equals(message.text)) {
					log.info("No match for remainder, trying full text");
					result = findDialogMatch(message.name, message.text);
					if (result != null) {
						textToSearch = message.text; // Update for tracking
					}
				}

				if (result != null) {
					String fileName = result[0];
					String matchedQuestName = result[1];

					// Update tracking for incremental dialog detection
					lastMatchedCharacter = message.name;
					lastMatchedText = message.text;

					this.questName = matchedQuestName;
					isQuestDialog = true;
					soundEngine.play(fileName);
					return;
				} else {
					log.info("No match found in database");
				}

				isQuestDialog = false;
			} catch (SQLException e) {
				log.error("Encountered an SQL error", e);
			}
		}
	}

	/**
	 * Find a dialog match in the database.
	 * First tries exact match, then falls back to fuzzy MATCH.
	 * @return String array [fileName, questName] or null if not found
	 */
	private String[] findDialogMatch(String character, String text) throws SQLException {
		// First try exact match
		try (PreparedStatement exactStatement = databaseManager.prepareStatement(
				"SELECT quest, uri FROM dialogs WHERE character = ? AND text = ?")) {
			exactStatement.setString(1, character);
			exactStatement.setString(2, text);

			try (ResultSet resultSet = exactStatement.executeQuery()) {
				if (resultSet.next()) {
					String fileName = resultSet.getString("uri");
					String questName = resultSet.getString("quest");
					log.info("Exact match found! Quest: '{}', URI: '{}'", questName, fileName);
					return new String[]{fileName, questName};
				}
			}
		}

		// If no exact match, try fuzzy MATCH
		try (PreparedStatement fuzzyStatement = databaseManager.prepareStatement(
				"SELECT quest, uri FROM dialogs WHERE character = ? AND text MATCH ?")) {
			fuzzyStatement.setString(1, character.replace("'", "''"));
			fuzzyStatement.setString(2, text.replace("'", "''"));

			try (ResultSet resultSet = fuzzyStatement.executeQuery()) {
				if (resultSet.next()) {
					String fileName = resultSet.getString("uri");
					String questName = resultSet.getString("quest");
					log.info("Fuzzy match found! Quest: '{}', URI: '{}'", questName, fileName);
					return new String[]{fileName, questName};
				}
			}
		}

		return null;
	}

	@Subscribe
	public void onMenuOptionClicked(MenuOptionClicked event)
	{
		if (event.getMenuOption().equals("Continue"))
		{
			soundEngine.stop();
		}
	}

	@Subscribe
	public void onWidgetLoaded(WidgetLoaded widgetLoaded)
	{
		// Check if the loaded widget is the dialog widget
		if (widgetLoaded.getGroupId() == InterfaceID.DIALOG_NPC || widgetLoaded.getGroupId() == InterfaceID.DIALOG_PLAYER || widgetLoaded.getGroupId() == InterfaceID.DIALOG_OPTION)
		{
			if(dialogEngine.isPlayerOrNpcDialogOpen() && isQuestDialog) {
				Widget dialogWidget = dialogEngine.getPlayerOrNpcWidget();
				dialogEngine.addMuteButton(dialogWidget);
				if(questName != null) {
					dialogEngine.addQuestNameText(dialogWidget, this.questName);
				}
			}
		}
	}

	@Subscribe
	public void onWidgetClosed(WidgetClosed widgetClosed)
	{
		if (widgetClosed.getGroupId() == InterfaceID.DIALOG_NPC ||
				widgetClosed.getGroupId() == InterfaceID.DIALOG_PLAYER ||
				widgetClosed.getGroupId() == InterfaceID.DIALOG_OPTION)
		{
			soundEngine.stop();
		}
	}

	@Provides
	QuestVoiceoverConfig provideConfig(ConfigManager configManager)
	{
		return configManager.getConfig(QuestVoiceoverConfig.class);
	}
}

#!/usr/bin/env python3
"""
Automatic voiceover generator for The Tourist Trap quest.

Supports two TTS backends:
- ElevenLabs: High quality, but costs credits ($)
- Kokoro: Free local TTS, good quality

Usage:
    # Use Kokoro (free, default)
    uv run python auto_generate_tourist_trap.py

    # Use ElevenLabs (requires ELEVENLABS_API_KEY)
    uv run python auto_generate_tourist_trap.py --backend elevenlabs
"""
import os
import argparse
from tqdm import tqdm
from dotenv import load_dotenv
import voiceover_cli.wiki_utils as wiki_utils
import voiceover_cli.database as database

# Load environment variables
load_dotenv()


def get_elevenlabs_voice_map():
    """Voice mapping for ElevenLabs backend."""
    from voiceover_cli.elevenlabs import ElevenlabsSDK

    sdk = ElevenlabsSDK()
    all_voices = sdk.get_voices()
    voice_lookup = {v.name: v.voice_id for v in all_voices}

    # Character to ElevenLabs voice name mapping
    char_to_voice = {
        'Irena': 'Jessica',
        'Ana': 'Matilda',
        'Ana (in a Barrel)': 'Matilda',
        'Ana-in-barrel': 'Matilda',
        'Ana (in-a-barrel),': 'Matilda',
        'Player': 'Chris',
        'Mercenary': 'Harry',
        'Guard': 'Liam',
        'Mercenary Captain': 'George',
        'Al Shabim': 'Roger',
        'Mine cart driver': 'Callum',
        'Male slave': 'Will',
        'Escaping slave': 'Eric',
        'Rowdy slave': 'Charlie',
        'Bedabin Nomad': 'Adam',
        'Captain Siad': 'Brian',
        'Bedabin Nomad Guard': 'Daniel',
    }

    # Convert voice names to IDs
    character_voice_ids = {}
    for char, voice_name in char_to_voice.items():
        if voice_name in voice_lookup:
            character_voice_ids[char] = voice_lookup[voice_name]

    return sdk, character_voice_ids


def get_kokoro_voice_map():
    """Voice mapping for Kokoro backend (free local TTS)."""
    from voiceover_cli.kokoro import KokoroSDK, get_voice_mapping_kokoro

    sdk = KokoroSDK(lang_code='a')  # American English
    voice_map = get_voice_mapping_kokoro()

    return sdk, voice_map


def main():
    parser = argparse.ArgumentParser(description='Generate voiceovers for The Tourist Trap quest')
    parser.add_argument(
        '--backend',
        choices=['kokoro', 'elevenlabs'],
        default='kokoro',
        help='TTS backend to use (default: kokoro - free local TTS)'
    )
    parser.add_argument(
        '--start-line',
        type=int,
        default=0,
        help='Line number to start from (0-indexed, for resuming)'
    )
    args = parser.parse_args()

    print("=== Initializing ===")
    print(f"Backend: {args.backend}")

    # Get quest info
    quests = wiki_utils.get_quests()
    tourist_trap = next((q for q in quests if 'Tourist Trap' in q['title']), None)

    if not tourist_trap:
        print("ERROR: Could not find The Tourist Trap quest")
        return

    print(f"Quest: {tourist_trap['title']}")

    # Initialize backend
    if args.backend == 'elevenlabs':
        if not os.getenv('ELEVENLABS_API_KEY'):
            print("ERROR: ELEVENLABS_API_KEY environment variable not set")
            return
        sdk, character_voice_ids = get_elevenlabs_voice_map()
        print(f"\nUsing ElevenLabs (costs credits!)")
    else:
        sdk, character_voice_ids = get_kokoro_voice_map()
        print(f"\nUsing Kokoro (free local TTS)")

    # Show voice assignments
    print("\n=== Voice Assignments ===")
    female_chars = ['Irena', 'Ana', 'Ana (in a Barrel)', 'Ana-in-barrel', 'Ana (in-a-barrel),']
    for char, voice_id in character_voice_ids.items():
        gender = "F" if char in female_chars else "M"
        print(f"  [{gender}] {char} → {voice_id}")

    # Get characters and transcript
    characters = wiki_utils.get_quest_characters(tourist_trap['link'])
    transcript = wiki_utils.get_transcript(tourist_trap['link'], characters)
    dialogue_lines = transcript['flattened_transcript']

    # Handle resume from specific line
    if args.start_line > 0:
        print(f"\n=== Resuming from line {args.start_line} ===")
        dialogue_lines = dialogue_lines[args.start_line:]

    print(f"\n=== Generating {len(dialogue_lines)} voiceover files ===")
    print("This will take a while...")

    generated_data = []
    skipped_count = 0

    for idx, (character, text) in enumerate(tqdm(dialogue_lines, desc="Generating")):
        actual_idx = idx + args.start_line

        if character not in character_voice_ids:
            tqdm.write(f"Skipping {character} - no voice assigned")
            skipped_count += 1
            continue

        try:
            previous_line = dialogue_lines[idx - 1][1] if idx > 0 else None
            next_line = dialogue_lines[idx + 1][1] if idx < len(dialogue_lines) - 1 else None

            voice_id = character_voice_ids[character]
            file_name = sdk.generate(character, voice_id, text, next_line, previous_line)

            generated_data.append({
                'quest': tourist_trap['title'],
                'character': character,
                'text': text,
                'uri': file_name
            })

        except Exception as e:
            tqdm.write(f"Error on line {actual_idx + 1}: {e}")
            # For ElevenLabs quota errors, stop
            if 'quota_exceeded' in str(e):
                tqdm.write("\n⚠️  ElevenLabs quota exceeded! Consider using --backend kokoro (free)")
                tqdm.write(f"   Resume with: --start-line {actual_idx}")
                break
            continue

    # Save to database
    print("\n=== Saving to database ===")
    conn = database.create_connection()
    database.init_virtual_table(conn)

    for item in generated_data:
        database.insert_quest_voiceover(
            conn,
            item['quest'],
            item['character'],
            item['text'],
            item['uri']
        )

    conn.close()

    print(f"\n✅ Complete!")
    print(f"  Generated: {len(generated_data)} voiceover files")
    print(f"  Skipped: {skipped_count} (no voice assigned)")
    print(f"  Audio files: output_voiceover/")
    print(f"  Database: output_db/quest_voiceover.db")

    if args.backend == 'kokoro':
        print(f"\n💡 Kokoro is free! No API costs incurred.")


if __name__ == '__main__':
    main()

#!/usr/bin/env -S uv run --python 3.12
# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#   "kokoro>=0.9.0",
#   "scipy>=1.11.0",
#   "soundfile>=0.12.1",
#   "numpy",
#   "pydub>=0.25.1",
#   "beautifulsoup4>=4.12.3",
#   "requests>=2.32.3",
#   "tqdm>=4.66.4",
#   "pip",
# ]
# [tool.uv]
# exclude-newer = "2025-06-01T00:00:00Z"
# ///
"""
Voiceover generator using Kokoro TTS (free local TTS).

Usage:
    ./generate_kokoro.py                    # Generate all missing voiceovers
    ./generate_kokoro.py --start-line 237   # Resume from line 237
    ./generate_kokoro.py --list-voices      # List available voices
"""

import os
import io
import sys
import shutil
import hashlib
import sqlite3
import argparse
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wavfile
from pydub import AudioSegment
from kokoro import KPipeline
from tqdm import tqdm
import requests
from bs4 import BeautifulSoup

# Add voiceover_cli to path for wiki_utils
sys.path.insert(0, str(Path(__file__).parent))
import voiceover_cli.wiki_utils as wiki_utils


# ============ Configuration ============

OUTPUT_DIR = Path("output_voiceover")
DB_DIR = Path("output_db")
DB_PATH = DB_DIR / "quest_voiceover.db"

# Kokoro voice mapping for The Tourist Trap characters
VOICE_MAP = {
    # Female characters
    'Irena': 'af_jessica',
    'Ana': 'af_bella',
    'Ana (in a Barrel)': 'af_bella',
    'Ana-in-barrel': 'af_bella',
    'Ana (in-a-barrel),': 'af_bella',

    # Male characters
    'Player': 'am_michael',
    'Mercenary': 'am_fenrir',
    'Guard': 'am_liam',
    'Mercenary Captain': 'am_onyx',
    'Al Shabim': 'am_adam',
    'Mine cart driver': 'am_puck',
    'Male slave': 'am_echo',
    'Escaping slave': 'am_eric',
    'Rowdy slave': 'am_fenrir',
    'Bedabin Nomad': 'am_adam',
    'Captain Siad': 'am_onyx',
    'Bedabin Nomad Guard': 'am_liam',
}

AVAILABLE_VOICES = {
    # American English - Female
    'af_heart': 'Heart (F)',
    'af_alloy': 'Alloy (F)',
    'af_aoede': 'Aoede (F)',
    'af_bella': 'Bella (F)',
    'af_jessica': 'Jessica (F)',
    'af_kore': 'Kore (F)',
    'af_nicole': 'Nicole (F)',
    'af_nova': 'Nova (F)',
    'af_river': 'River (F)',
    'af_sarah': 'Sarah (F)',
    'af_sky': 'Sky (F)',
    # American English - Male
    'am_adam': 'Adam (M)',
    'am_echo': 'Echo (M)',
    'am_eric': 'Eric (M)',
    'am_fenrir': 'Fenrir (M)',
    'am_liam': 'Liam (M)',
    'am_michael': 'Michael (M)',
    'am_onyx': 'Onyx (M)',
    'am_puck': 'Puck (M)',
    'am_santa': 'Santa (M)',
}




# ============ Database ============

def init_database():
    """Initialize the SQLite database."""
    DB_DIR.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create FTS4 virtual table for fast text search
    cursor.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS dialogs USING fts4(
            quest TEXT NOT NULL,
            character TEXT NOT NULL,
            text TEXT NOT NULL,
            uri TEXT NOT NULL
        )
    ''')

    conn.commit()
    return conn


def insert_dialog(conn, quest: str, character: str, text: str, uri: str):
    """Insert a dialog entry into the database."""
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO dialogs (quest, character, text, uri) VALUES (?, ?, ?, ?)',
        (quest, character, text, uri)
    )
    conn.commit()


def dialog_exists(conn, character: str, text: str) -> bool:
    """Check if a dialog already exists in the database."""
    cursor = conn.cursor()
    cursor.execute(
        'SELECT 1 FROM dialogs WHERE character = ? AND text = ?',
        (character, text)
    )
    return cursor.fetchone() is not None


# ============ Kokoro TTS ============

class KokoroTTS:
    """Kokoro TTS wrapper for generating voiceovers."""

    def __init__(self, lang_code: str = 'a'):
        self._check_espeak()
        self.lang_code = lang_code
        self.pipeline = None

    def _check_espeak(self):
        """Check if espeak-ng is installed."""
        if not any([shutil.which("espeak"), shutil.which("espeak-ng")]):
            print("ERROR: Kokoro requires espeak-ng. Install with:")
            print("  macOS: brew install espeak-ng")
            print("  Ubuntu: sudo apt-get install espeak-ng")
            sys.exit(1)

    def _get_pipeline(self) -> KPipeline:
        """Lazy initialization of Kokoro pipeline."""
        if self.pipeline is None:
            self.pipeline = KPipeline(lang_code=self.lang_code)
        return self.pipeline

    def _strip_silence(self, audio: np.ndarray, threshold: float = 0.01) -> np.ndarray:
        """Strip silence from start and end of audio."""
        mask = np.abs(audio) > threshold
        indices = np.where(mask)[0]
        if len(indices) == 0:
            return audio
        start = max(0, indices[0] - 1000)
        end = min(len(audio), indices[-1] + 1000)
        return audio[start:end]

    def generate(self, character: str, voice_id: str, text: str) -> str:
        """Generate audio file for a line of dialogue.

        Returns the filename of the generated MP3.
        """
        OUTPUT_DIR.mkdir(exist_ok=True)

        # Generate unique filename based on content
        unique_id = hashlib.md5(f'{character}|{text}'.encode()).hexdigest()
        file_name = f"{unique_id}.mp3"
        file_path = OUTPUT_DIR / file_name

        # Skip if already exists
        if file_path.exists():
            return file_name

        # Clean text
        clean_text = text.replace("[player name]", "adventurer")

        # Generate audio
        pipeline = self._get_pipeline()
        audio_segments = []
        for _, _, audio in pipeline(clean_text, voice=voice_id, speed=1.0):
            audio_segments.append(audio)

        if not audio_segments:
            raise ValueError("No audio generated")

        # Combine segments
        audio = np.concatenate(audio_segments)
        audio = self._strip_silence(audio)

        # Normalize
        if np.max(np.abs(audio)) > 1.0:
            audio = audio / np.max(np.abs(audio))

        # Convert to 16-bit
        audio_int16 = (audio * 32767).astype(np.int16)

        # Save as WAV in memory
        wav_buffer = io.BytesIO()
        wavfile.write(wav_buffer, 24000, audio_int16)
        wav_buffer.seek(0)

        # Convert to MP3
        audio_segment = AudioSegment.from_wav(wav_buffer)
        audio_segment.export(str(file_path), format="mp3", bitrate="128k")

        return file_name


# ============ Main ============

def main():
    parser = argparse.ArgumentParser(
        description='Generate voiceovers for The Tourist Trap using Kokoro TTS (free!)'
    )
    parser.add_argument(
        '--start-line', type=int, default=0,
        help='Line number to start from (for resuming)'
    )
    parser.add_argument(
        '--list-voices', action='store_true',
        help='List available voices and exit'
    )
    args = parser.parse_args()

    if args.list_voices:
        print("Available Kokoro voices (American English):\n")
        print("Female voices:")
        for vid, name in AVAILABLE_VOICES.items():
            if vid.startswith('af_'):
                print(f"  {vid}: {name}")
        print("\nMale voices:")
        for vid, name in AVAILABLE_VOICES.items():
            if vid.startswith('am_'):
                print(f"  {vid}: {name}")
        return

    print("=" * 50)
    print("Kokoro TTS Voiceover Generator")
    print("The Tourist Trap Quest")
    print("=" * 50)
    print("\n💡 Using Kokoro TTS - completely FREE!\n")

    # Get transcript
    print("Fetching quest transcript from wiki...")
    
    # Get quest from wiki
    quests = wiki_utils.get_quests()
    tourist_trap = next((q for q in quests if 'tourist trap' in q['title'].lower()), None)
    
    if not tourist_trap:
        print("ERROR: Could not find The Tourist Trap quest")
        sys.exit(1)
    
    # Get characters and transcript
    characters = wiki_utils.get_quest_characters(tourist_trap['link'])
    transcript_data = wiki_utils.get_transcript(tourist_trap['link'], characters)
    transcript = transcript_data['flattened_transcript']

    print(f"Found {len(transcript)} dialog lines")
    print(f"Characters: {', '.join(set(c for c, _ in transcript))}\n")

    # Show voice assignments
    print("Voice assignments:")
    female_chars = {'Irena', 'Ana', 'Ana (in a Barrel)', 'Ana-in-barrel', 'Ana (in-a-barrel),'}
    for char in set(c for c, _ in transcript):
        if char in VOICE_MAP:
            voice = VOICE_MAP[char]
            gender = "F" if char in female_chars else "M"
            print(f"  [{gender}] {char} → {voice}")
        else:
            print(f"  [?] {char} → NO VOICE ASSIGNED")

    # Initialize TTS early to catch any errors before we start
    print("\nInitializing Kokoro TTS...")
    tts = KokoroTTS()
    # Force initialization now (downloads models if needed)
    try:
        tts._get_pipeline()
        print("Kokoro TTS initialized successfully!")
    except Exception as e:
        print(f"ERROR: Failed to initialize Kokoro TTS: {e}")
        print("\nTroubleshooting:")
        print("  1. Make sure espeak-ng is installed: brew install espeak-ng")
        print("  2. Check your internet connection for model downloads")
        sys.exit(1)

    conn = init_database()

    # Handle resume
    if args.start_line > 0:
        print(f"\nResuming from line {args.start_line}")
        transcript = transcript[args.start_line:]

    print(f"\nGenerating {len(transcript)} voiceovers...")
    print("(This may take a while on first run - models need to download)\n")

    generated = 0
    skipped = 0
    errors = 0

    for idx, (character, text) in enumerate(tqdm(transcript, desc="Generating")):
        if character not in VOICE_MAP:
            skipped += 1
            continue

        try:
            voice_id = VOICE_MAP[character]
            file_name = tts.generate(character, voice_id, text)

            # Add to database if not exists
            if not dialog_exists(conn, character, text):
                insert_dialog(conn, "The Tourist Trap", character, text, file_name)

            generated += 1

        except Exception as e:
            tqdm.write(f"Error on line {args.start_line + idx}: {e}")
            errors += 1
            continue

    conn.close()

    print("\n" + "=" * 50)
    print("✅ Generation complete!")
    print(f"  Generated: {generated}")
    print(f"  Skipped (no voice): {skipped}")
    print(f"  Errors: {errors}")
    print(f"\n  Audio files: {OUTPUT_DIR}/")
    print(f"  Database: {DB_PATH}")
    print("\n💡 To use in RuneLite, copy database to:")
    print(f"   cp {DB_PATH} ~/.runelite/quest-voiceover/quest_voiceover.db")


if __name__ == '__main__':
    main()

"""
Kokoro TTS backend for generating voiceovers.
Free, local TTS - no API costs!
"""

import os
import io
import shutil
from dataclasses import dataclass
from typing import List

import numpy as np
import scipy.io.wavfile as wavfile
from pydub import AudioSegment
from kokoro import KPipeline

import voiceover_cli.utils as utils

OUTPUT_DIR = "output_voiceover"


@dataclass
class KokoroVoice:
    """Voice information for Kokoro TTS."""
    voice_id: str
    name: str
    gender: str  # 'male' or 'female'


class KokoroSDK:
    """Kokoro TTS backend - free local text-to-speech."""

    # Available voices for American English (lang_code='a')
    VOICES = {
        # Female voices
        'af_heart': KokoroVoice('af_heart', 'Heart', 'female'),
        'af_alloy': KokoroVoice('af_alloy', 'Alloy', 'female'),
        'af_aoede': KokoroVoice('af_aoede', 'Aoede', 'female'),
        'af_bella': KokoroVoice('af_bella', 'Bella', 'female'),
        'af_jessica': KokoroVoice('af_jessica', 'Jessica', 'female'),
        'af_kore': KokoroVoice('af_kore', 'Kore', 'female'),
        'af_nicole': KokoroVoice('af_nicole', 'Nicole', 'female'),
        'af_nova': KokoroVoice('af_nova', 'Nova', 'female'),
        'af_river': KokoroVoice('af_river', 'River', 'female'),
        'af_sarah': KokoroVoice('af_sarah', 'Sarah', 'female'),
        'af_sky': KokoroVoice('af_sky', 'Sky', 'female'),
        # Male voices
        'am_adam': KokoroVoice('am_adam', 'Adam', 'male'),
        'am_echo': KokoroVoice('am_echo', 'Echo', 'male'),
        'am_eric': KokoroVoice('am_eric', 'Eric', 'male'),
        'am_fenrir': KokoroVoice('am_fenrir', 'Fenrir', 'male'),
        'am_liam': KokoroVoice('am_liam', 'Liam', 'male'),
        'am_michael': KokoroVoice('am_michael', 'Michael', 'male'),
        'am_onyx': KokoroVoice('am_onyx', 'Onyx', 'male'),
        'am_puck': KokoroVoice('am_puck', 'Puck', 'male'),
        'am_santa': KokoroVoice('am_santa', 'Santa', 'male'),
    }

    # British English voices (lang_code='b')
    BRITISH_VOICES = {
        'bf_alice': KokoroVoice('bf_alice', 'Alice', 'female'),
        'bf_emma': KokoroVoice('bf_emma', 'Emma', 'female'),
        'bf_isabella': KokoroVoice('bf_isabella', 'Isabella', 'female'),
        'bf_lily': KokoroVoice('bf_lily', 'Lily', 'female'),
        'bm_daniel': KokoroVoice('bm_daniel', 'Daniel', 'male'),
        'bm_fable': KokoroVoice('bm_fable', 'Fable', 'male'),
        'bm_george': KokoroVoice('bm_george', 'George', 'male'),
        'bm_lewis': KokoroVoice('bm_lewis', 'Lewis', 'male'),
    }

    def __init__(self, lang_code: str = 'a') -> None:
        """Initialize Kokoro TTS.

        Args:
            lang_code: Language code ('a' for American English, 'b' for British English)
        """
        self._check_espeak()
        self.lang_code = lang_code
        self.pipeline = None
        self._voices = self.VOICES if lang_code == 'a' else self.BRITISH_VOICES

    def _check_espeak(self):
        """Check if espeak/espeak-ng is installed (required by Kokoro)."""
        if not any([shutil.which("espeak"), shutil.which("espeak-ng")]):
            raise RuntimeError(
                "Kokoro requires espeak or espeak-ng. Install with:\n"
                "  macOS: brew install espeak-ng\n"
                "  Ubuntu: sudo apt-get install espeak-ng\n"
                "  Windows: Download from https://github.com/espeak-ng/espeak-ng/releases"
            )

    def _get_pipeline(self) -> KPipeline:
        """Get or create the Kokoro pipeline (lazy initialization)."""
        if self.pipeline is None:
            self.pipeline = KPipeline(lang_code=self.lang_code)
        return self.pipeline

    def get_voices(self) -> List[KokoroVoice]:
        """Get all available voices."""
        return list(self._voices.values())

    def get_female_voices(self) -> List[KokoroVoice]:
        """Get all female voices."""
        return [v for v in self._voices.values() if v.gender == 'female']

    def get_male_voices(self) -> List[KokoroVoice]:
        """Get all male voices."""
        return [v for v in self._voices.values() if v.gender == 'male']

    def _strip_silence(
        self,
        audio_data: np.ndarray,
        threshold: float = 0.01,
        min_silence_duration: int = 1000,
    ) -> np.ndarray:
        """Strip silence from the beginning and end of audio data."""
        abs_audio = np.abs(audio_data)
        mask = abs_audio > threshold
        non_silent = np.where(mask)[0]

        if len(non_silent) == 0:
            return audio_data

        start = max(0, non_silent[0] - min_silence_duration)
        end = min(len(audio_data), non_silent[-1] + min_silence_duration)

        return audio_data[start:end]

    def generate(
        self,
        character: str,
        voice_id: str,
        line: str,
        next_line: str | None = None,
        previous_line: str | None = None,
        speed: float = 1.0
    ) -> str:
        """Generate audio for a line of dialogue.

        Args:
            character: Character name (for filename generation)
            voice_id: Kokoro voice ID (e.g., 'af_heart', 'am_adam')
            line: The text to synthesize
            next_line: Next line (unused, for API compatibility with ElevenLabs)
            previous_line: Previous line (unused, for API compatibility with ElevenLabs)
            speed: Speech speed (0.5 to 2.0, default 1.0)

        Returns:
            Filename of the generated audio file
        """
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        unique_id = utils.str_to_md5(f'{character}|{line}')
        file_name = f"{unique_id}.mp3"
        file_path = os.path.join(OUTPUT_DIR, file_name)

        # Skip if already generated
        if os.path.exists(file_path):
            return file_name

        try:
            # Clean the text
            text = utils.remove_special_characters(line.strip())

            # Get pipeline
            pipeline = self._get_pipeline()

            # Validate voice
            if voice_id not in self._voices:
                raise ValueError(f"Voice {voice_id} not found. Available: {list(self._voices.keys())}")

            # Generate audio
            audio_segments = []
            for _, _, audio in pipeline(text, voice=voice_id, speed=speed):
                audio_segments.append(audio)

            if not audio_segments:
                raise ValueError("No audio generated")

            # Concatenate audio segments
            audio = np.concatenate(audio_segments)

            # Strip silence
            audio = self._strip_silence(audio)

            # Normalize to [-1, 1] range
            if np.max(np.abs(audio)) > 1.0:
                audio = audio / np.max(np.abs(audio))

            # Convert to 16-bit integer format
            audio_int16 = (audio * 32767).astype(np.int16)

            # Save as WAV first
            wav_buffer = io.BytesIO()
            wavfile.write(wav_buffer, 24000, audio_int16)
            wav_buffer.seek(0)

            # Convert to MP3 using pydub
            audio_segment = AudioSegment.from_wav(wav_buffer)
            audio_segment.export(file_path, format="mp3", bitrate="128k")

            return file_name

        except Exception as e:
            raise RuntimeError(f"Failed to generate audio: {e}") from e


def get_voice_mapping_kokoro() -> dict[str, str]:
    """Get a suggested voice mapping for The Tourist Trap quest using Kokoro voices.

    Returns a dict mapping character names to Kokoro voice IDs.
    """
    return {
        # Female characters
        'Irena': 'af_jessica',          # Mother - warm female voice
        'Ana': 'af_bella',              # Daughter - younger female voice
        'Ana (in a Barrel)': 'af_bella',
        'Ana-in-barrel': 'af_bella',
        'Ana (in-a-barrel),': 'af_bella',

        # Male characters - varied voices
        'Player': 'am_michael',         # Player character
        'Mercenary': 'am_fenrir',       # Guard type - gruff
        'Guard': 'am_liam',             # Guard type
        'Mercenary Captain': 'am_onyx', # Authority figure - deep voice
        'Al Shabim': 'am_adam',         # Quest giver
        'Mine cart driver': 'am_puck',  # Worker
        'Male slave': 'am_echo',        # Slave
        'Escaping slave': 'am_eric',    # Slave
        'Rowdy slave': 'am_fenrir',     # Slave - reuse gruff voice
        'Bedabin Nomad': 'am_adam',     # Nomad
        'Captain Siad': 'am_onyx',      # Captain - deep voice
        'Bedabin Nomad Guard': 'am_liam', # Guard
    }

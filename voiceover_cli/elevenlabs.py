

import os
from typing import List
from elevenlabs.client import ElevenLabs
from elevenlabs import AddPronunciationDictionaryResponseModel, PronunciationDictionaryVersionLocator, VoiceSettings, Voice, play, stream, save
import voiceover_cli.utils as utils


ELEVENLABS_API_BASE_URL = "https://api.elevenlabs.io/v1"
OUTPUT_DIR = "output_voiceover"

class ElevenlabsSDK:
    def __init__(self) -> None:
        self.api_key = os.getenv('ELEVENLABS_API_KEY')
        self.client = ElevenLabs(
            api_key=self.api_key
        )

    def get_voices(self) -> List[Voice]:
        voices = self.client.voices.get_all().voices
        return voices
    
    def generate(self, character: str, voice_id: str, line: str, next_line: str | None, previous_line: str | None) -> str:
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        unique_id = utils.str_to_md5(f'{character}|{line}')
        file_name = f"{unique_id}.mp3"
        file_path = os.path.join(OUTPUT_DIR, file_name)

        if not os.path.exists(file_path):
            try:
                # request_options with previous/next text not supported in current SDK version
                # request_options = {
                #     "additional_body_parameters": {
                #         "previous_text": None if previous_line == None else utils.remove_special_characters(previous_line),
                #         "next_text": None if next_line == None else utils.remove_special_characters(next_line),
                #     }
                # }

                # Pronunciation dictionary disabled - not available in current SDK version
                # with open("pronunciation_dictionary.pls", "rb") as f:
                #     pronunciation_dictionary: AddPronunciationDictionaryResponseModel = self.client.pronunciation_dictionary.add_from_file(
                #         file=f.read(), name="example"
                #     )
                
                audio = self.client.text_to_speech.convert(
                    text=utils.remove_special_characters(line.strip()),
                    voice_id=voice_id,
                    model_id="eleven_multilingual_v2",
                    voice_settings=VoiceSettings(stability=0.3, style=0.4, similarity_boost=0.7)
                )
                                                 # pronunciation_dictionary_locators=[
                                                 #    PronunciationDictionaryVersionLocator(
                                                 #        pronunciation_dictionary_id=pronunciation_dictionary.id,
                                                 #        version_id=pronunciation_dictionary.version_id,
                                                 #    )
                                                 # ])
                
                save(audio, file_path)

                return file_name
            except Exception as e:
                raise e
    
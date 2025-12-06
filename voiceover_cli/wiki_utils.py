import requests
from bs4 import BeautifulSoup
from typing import TypedDict, List, Dict, Optional
import time

QUESTS_TRANSCRIPT_WIKI_URL = "https://oldschool.runescape.wiki/w/Category:Quest_transcript"
QUEST_TRANSCRIPT_WIKI_BASE_URL = "https://oldschool.runescape.wiki"
HEADERS = {
    'User-Agent': 'QuestVoiceoverBot/1.0 (https://github.com/Miyou/runelite-quest-voiceover)'
}

# Cache for character genders to avoid repeated requests
_gender_cache: Dict[str, Optional[str]] = {}

class QuestTranscriptMetadata(TypedDict):
    idx: int
    title: str
    link: str


class QuestTranscript(TypedDict):
    transcript: dict[str, list[str]]
    flattened_transcript: list[(str, str)]


def get_quests() -> List[QuestTranscriptMetadata]:
    response = requests.get(QUESTS_TRANSCRIPT_WIKI_URL, headers=HEADERS)
    soup = BeautifulSoup(response.content, 'html.parser')

    quest_transcripts_list: List[QuestTranscriptMetadata] = []

    for i, li in enumerate(soup.select('div.mw-category-group li')):
        if li.name == 'li' and li.find('a', recursive=False):
            a = li.find('a', recursive=False)
            quest_transcripts_list.append({'idx': i,
                                            'title': a.get_text(strip=True, separator=' '),
                                            'link': f"{QUEST_TRANSCRIPT_WIKI_BASE_URL}{a.attrs['href']}"})

    return quest_transcripts_list


def get_transcript(url: str, characters: list[str]) -> QuestTranscript:
    response = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(response.content, 'html.parser')

    transcript_list = soup.find('div', class_='mw-parser-output')
    if not transcript_list:
        raise Exception("Dialog list not found")

    transcript: dict[str, list[str]] = {}
    flatten_transcript: list[(str, str)] = []
    character = None

    for elem in transcript_list.find_all('li'):
        if elem.name == 'li' and elem.find('b', recursive=False):
            character = elem.find('b', recursive=False).extract().text.strip().replace(":", "")

            if character not in characters: continue

            if character not in transcript:
                transcript[character] = []

            line = elem.get_text(strip=True, separator=' ')
            transcript[character].append(line)
            flatten_transcript.append((character, line))

    return {'transcript': transcript, 'flattened_transcript': flatten_transcript}

def get_quest_characters(url) -> List[str]:
    response = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(response.content, 'html.parser')

    transcript_list = soup.find('div', class_='mw-parser-output')
    if not transcript_list:
        raise Exception("Dialog list not found")

    characters: list[str] = []

    for elem in transcript_list.find_all('li'):
        if elem.name == 'li' and elem.find('b', recursive=False):
            character = elem.find('b', recursive=False).extract().text.strip().replace(":", "")

            if character not in characters:
                characters.append(character)

    return characters


def get_character_gender(character_name: str, delay: float = 0.1) -> Optional[str]:
    """Fetch character gender from the OSRS wiki.

    Args:
        character_name: The name of the character/NPC
        delay: Delay between requests to be respectful to the wiki

    Returns:
        'male', 'female', or None if gender couldn't be determined
    """
    # Check cache first
    if character_name in _gender_cache:
        return _gender_cache[character_name]

    # Clean up character name for URL (handle variations like "Ana (in a Barrel)")
    clean_name = character_name.split('(')[0].strip()

    # Skip generic/non-character entries
    skip_patterns = ['player', 'narrator', 'unknown', 'voice', 'note', 'book', 'scroll']
    if any(pattern in clean_name.lower() for pattern in skip_patterns):
        _gender_cache[character_name] = None
        return None

    # Construct wiki URL
    url_name = clean_name.replace(' ', '_')
    url = f"{QUEST_TRANSCRIPT_WIKI_BASE_URL}/w/{url_name}"

    try:
        time.sleep(delay)  # Be respectful to the wiki
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code != 200:
            _gender_cache[character_name] = None
            return None

        soup = BeautifulSoup(response.content, 'html.parser')

        # Look for gender in the infobox
        # OSRS wiki uses class "infobox" or "infobox-npc"
        infobox = soup.find('table', class_=lambda x: x and 'infobox' in x)

        if infobox:
            # Look for gender row in the infobox
            for row in infobox.find_all('tr'):
                header = row.find('th')
                if header and 'gender' in header.get_text().lower():
                    data = row.find('td')
                    if data:
                        gender_text = data.get_text(strip=True).lower()
                        if 'female' in gender_text:
                            _gender_cache[character_name] = 'female'
                            return 'female'
                        elif 'male' in gender_text:
                            _gender_cache[character_name] = 'male'
                            return 'male'

        # If no infobox gender, try to find gender mentions in the page content
        # Some NPCs have gender mentioned in the first paragraph
        content = soup.find('div', class_='mw-parser-output')
        if content:
            first_para = content.find('p')
            if first_para:
                para_text = first_para.get_text().lower()
                # Check for pronouns that indicate gender
                if any(word in para_text for word in [' she ', ' her ', ' herself ']):
                    _gender_cache[character_name] = 'female'
                    return 'female'
                elif any(word in para_text for word in [' he ', ' his ', ' him ', ' himself ']):
                    _gender_cache[character_name] = 'male'
                    return 'male'

        _gender_cache[character_name] = None
        return None

    except Exception:
        _gender_cache[character_name] = None
        return None


def get_characters_genders(characters: List[str], delay: float = 0.1) -> Dict[str, Optional[str]]:
    """Fetch genders for multiple characters.

    Args:
        characters: List of character names
        delay: Delay between requests

    Returns:
        Dictionary mapping character names to their genders ('male', 'female', or None)
    """
    result = {}
    for character in characters:
        result[character] = get_character_gender(character, delay)
    return result

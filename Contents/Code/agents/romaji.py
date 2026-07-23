# coding=utf-8

# Deterministic Hepburn romanization of a hiragana reading. Used to romanize
# actress-name readings exactly, instead of letting an LLM guess from kanji.
# Readings on the source sites are hiragana (e.g. the actress-page slug
# "ほんだ-ひとみ"), so only hiragana is handled here.

# Two-kana sequences (yoon and small-kana combos) - checked before singles.
YOON = {
    u"きゃ": u"kya", u"きゅ": u"kyu", u"きょ": u"kyo",
    u"しゃ": u"sha", u"しゅ": u"shu", u"しょ": u"sho",
    u"ちゃ": u"cha", u"ちゅ": u"chu", u"ちょ": u"cho",
    u"にゃ": u"nya", u"にゅ": u"nyu", u"にょ": u"nyo",
    u"ひゃ": u"hya", u"ひゅ": u"hyu", u"ひょ": u"hyo",
    u"みゃ": u"mya", u"みゅ": u"myu", u"みょ": u"myo",
    u"りゃ": u"rya", u"りゅ": u"ryu", u"りょ": u"ryo",
    u"ぎゃ": u"gya", u"ぎゅ": u"gyu", u"ぎょ": u"gyo",
    u"じゃ": u"ja", u"じゅ": u"ju", u"じょ": u"jo",
    u"ぢゃ": u"ja", u"ぢゅ": u"ju", u"ぢょ": u"jo",
    u"びゃ": u"bya", u"びゅ": u"byu", u"びょ": u"byo",
    u"ぴゃ": u"pya", u"ぴゅ": u"pyu", u"ぴょ": u"pyo",
    u"ふぁ": u"fa", u"ふぃ": u"fi", u"ふぇ": u"fe", u"ふぉ": u"fo",
    u"てぃ": u"ti", u"でぃ": u"di", u"じぇ": u"je",
    u"ちぇ": u"che", u"しぇ": u"she",
}

# Single-kana mappings.
KANA = {
    u"あ": u"a", u"い": u"i", u"う": u"u", u"え": u"e", u"お": u"o",
    u"か": u"ka", u"き": u"ki", u"く": u"ku", u"け": u"ke", u"こ": u"ko",
    u"さ": u"sa", u"し": u"shi", u"す": u"su", u"せ": u"se", u"そ": u"so",
    u"た": u"ta", u"ち": u"chi", u"つ": u"tsu", u"て": u"te", u"と": u"to",
    u"な": u"na", u"に": u"ni", u"ぬ": u"nu", u"ね": u"ne", u"の": u"no",
    u"は": u"ha", u"ひ": u"hi", u"ふ": u"fu", u"へ": u"he", u"ほ": u"ho",
    u"ま": u"ma", u"み": u"mi", u"む": u"mu", u"め": u"me", u"も": u"mo",
    u"や": u"ya", u"ゆ": u"yu", u"よ": u"yo",
    u"ら": u"ra", u"り": u"ri", u"る": u"ru", u"れ": u"re", u"ろ": u"ro",
    u"わ": u"wa", u"ゐ": u"i", u"ゑ": u"e", u"を": u"o", u"ん": u"n",
    u"が": u"ga", u"ぎ": u"gi", u"ぐ": u"gu", u"げ": u"ge", u"ご": u"go",
    u"ざ": u"za", u"じ": u"ji", u"ず": u"zu", u"ぜ": u"ze", u"ぞ": u"zo",
    u"だ": u"da", u"ぢ": u"ji", u"づ": u"zu", u"で": u"de", u"ど": u"do",
    u"ば": u"ba", u"び": u"bi", u"ぶ": u"bu", u"べ": u"be", u"ぼ": u"bo",
    u"ぱ": u"pa", u"ぴ": u"pi", u"ぷ": u"pu", u"ぺ": u"pe", u"ぽ": u"po",
    u"ぁ": u"a", u"ぃ": u"i", u"ぅ": u"u", u"ぇ": u"e", u"ぉ": u"o",
    u"ゃ": u"ya", u"ゅ": u"yu", u"ょ": u"yo",
}

VOWELS = u"aeiou"


def kana_to_romaji(text):
    """Romanize a hiragana string using modified Hepburn.

    Handles yoon digraphs, the sokuon (small tsu, consonant doubling) and the
    prolonged-sound mark. Unknown characters are dropped.

    Args:
        text (str): A hiragana string.

    Returns:
        str: The romanized string (lower case).
    """
    result = []
    i = 0
    n = len(text)
    while i < n:
        pair = text[i:i + 2]
        if pair in YOON:
            result.append(YOON[pair])
            i += 2
            continue
        ch = text[i]
        if ch == u"っ":  # sokuon: geminate the following consonant
            nxt = YOON.get(text[i + 1:i + 3]) or KANA.get(text[i + 1:i + 2], u"")
            if nxt and nxt[0] not in VOWELS:
                result.append(nxt[0])
            i += 1
            continue
        if ch == u"ー":  # prolonged sound: repeat the previous vowel
            if result and result[-1] and result[-1][-1] in VOWELS:
                result.append(result[-1][-1])
            i += 1
            continue
        if ch in KANA:
            result.append(KANA[ch])
        elif ch.strip() and ord(ch) < 128:
            result.append(ch)  # keep stray ASCII
        i += 1
    return u"".join(result)


def romanize_reading(reading):
    """Romanize a name reading into capitalized words in Western order.

    The reading uses a space or middle dot between name parts. Each part is
    romanized and capitalized. A two-part reading is family-first at the source
    (e.g. `はら さおり`), so it is emitted given-first (`Saori Hara`) to match the
    Western order used by the translation prompt. An undelimited reading has no
    part boundary, so it is returned as a single word.

    Args:
        reading (str): A hiragana reading such as `はら さおり`.

    Returns:
        str or None: The romanized name (e.g. `Saori Hara`), or `None`.
    """
    if not reading:
        return None
    parts = [p for p in reading.replace(u"・", u" ").split() if p]
    words = []
    for part in parts:
        romaji = kana_to_romaji(part)
        if romaji:
            words.append(romaji[0].upper() + romaji[1:])
    if len(words) == 2:
        words = [words[1], words[0]]  # family given -> given family
    return u" ".join(words) or None

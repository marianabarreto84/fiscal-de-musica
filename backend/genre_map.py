"""Mapeamento de subgêneros do Spotify para macro-gêneros.

Spotify devolve gêneros como strings finas e específicas ('shoegaze',
'post-rock', 'art rock', 'neo-psychedelic', 'deep house', 'bossa nova',
'mpb', 'lo-fi hip hop', etc). Pra filtrar em UI a gente agrupa em macros
('rock', 'pop', 'jazz', ...).

Cada macro tem uma lista de substrings. O classificador percorre os macros
NA ORDEM e usa o primeiro cujo padrão bate no nome do subgênero. Por isso
a ordem importa — colocamos os macros mais específicos primeiro (metal
antes de rock; brasileira antes de pop; etc) pra "death metal" não cair
em rock só porque tem a substring 'metal' antes de 'rock'.

Adicionar macro novo: insere na lista MACRO_PATTERNS na posição certa
(mais específico → mais genérico). Não precisa ser exaustivo — gêneros
que não batem em nada caem em 'outros'.
"""
from __future__ import annotations


MACRO_PATTERNS: list[tuple[str, list[str]]] = [
    ("brasileira", [
        "mpb", "samba", "bossa nova", "bossa", "sertanejo", "forró", "forro",
        "axé", "axe", "pagode", "tropicalia", "tropicália",
        "brazilian", "brasileira", "brasileiro", "música popular brasileira",
        "choro", "manguebeat", "frevo",
    ]),
    ("hip hop", [
        "hip hop", "hip-hop", "rap", "trap", "drill", "grime", "boom bap",
        "g funk", "g-funk", "conscious hip hop",
    ]),
    ("jazz", [
        "jazz", "bebop", "swing", "big band", "fusion", "cool jazz",
        "hard bop", "free jazz", "smooth jazz",
    ]),
    ("classical", [
        "classical", "opera", "baroque", "romantic", "symphony", "symphonic",
        "chamber music", "minimalism", "contemporary classical", "orchestral",
        "early music", "renaissance",
    ]),
    ("metal", [
        "metal", "doom", "thrash", "djent", "metalcore", "deathcore",
        "grindcore", "sludge", "stoner",
    ]),
    ("punk", [
        "punk", "hardcore", "emo", "post-hardcore", "screamo",
    ]),
    ("electronic", [
        "house", "techno", "trance", "dnb", "drum and bass", "drum'n'bass",
        "ambient", "idm", "electro", "edm", "synthwave", "vaporwave",
        "dubstep", "breakbeat", "garage", "uk garage", "footwork", "jungle",
        "downtempo", "trip hop", "trip-hop", "minimal", "glitch",
        "electronic", "electronica", "industrial",
    ]),
    ("rnb", [
        "r&b", "rnb", "rhythm and blues", "neo soul", "neo-soul",
        "contemporary r&b",
    ]),
    ("soul", [
        "soul", "motown", "funk", "northern soul",
    ]),
    ("country", [
        "country", "bluegrass", "honky tonk", "outlaw country", "americana",
    ]),
    ("folk", [
        "folk", "singer-songwriter", "freak folk", "anti-folk",
    ]),
    ("blues", [
        "blues", "delta blues", "chicago blues",
    ]),
    ("reggae", [
        "reggae", "dub", "ska", "dancehall", "rocksteady",
    ]),
    ("world", [
        "afrobeat", "world", "latin", "k-pop", "kpop", "j-pop", "jpop",
        "cumbia", "salsa", "bachata", "merengue", "fado", "flamenco",
        "highlife", "raï", "rai music", "ethio", "afro",
    ]),
    ("rock", [
        "rock", "grunge", "shoegaze", "psychedelic", "psych", "noise",
        "no wave", "post-rock", "math rock", "krautrock", "garage rock",
        "indie", "alternative", "alt-rock",
    ]),
    ("pop", [
        "pop",
    ]),
]


def classify_genre(g: str) -> str | None:
    """Retorna o macro do subgênero, ou None se não bate em nada."""
    s = (g or "").lower().strip()
    if not s:
        return None
    for macro, patterns in MACRO_PATTERNS:
        for p in patterns:
            if p in s:
                return macro
    return None


def classify_genres(genres: list[str] | None) -> list[str]:
    """Retorna lista de macros únicos (ordem estável) pros subgêneros dados.

    Se nenhum subgênero classificar, retorna ['outros']. Lista vazia/None → []."""
    if not genres:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for g in genres:
        m = classify_genre(g)
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    if not out:
        # Tinha gêneros mas nenhum mapeou → fica como 'outros' pra ser filtrável.
        return ["outros"]
    return out


# Ordem de apresentação na UI (macros mais comuns primeiro).
MACRO_DISPLAY_ORDER = [
    "rock", "pop", "hip hop", "electronic", "jazz", "soul", "rnb",
    "folk", "country", "blues", "metal", "punk", "reggae", "classical",
    "brasileira", "world", "outros",
]

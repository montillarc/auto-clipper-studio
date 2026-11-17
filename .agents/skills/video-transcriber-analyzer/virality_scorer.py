"""
Motor Oficial de Evaluación — La Guía Definitiva de Puntuación de Viralidad (10 Puntos Clave)
y Analítica Adaptativa por Categoría para CreadorStudio (Videos VOD y Directos LIVE).

Soporta evaluación genérica y evaluación ponderada por categoría de contenido:
- `opinion_monologo`: Video de Opinión (1 Persona) / Commentary
- `reacciones`: Video Reacciones
- `videojuegos`: Videojuegos / Gaming Streams
- `podcast`: Podcast / Entrevista / Mesa Redonda
- `realitys`: Realitys / Show Social / Calle / Concho
- `storytime_anecdota`: Storytime / Anécdota Personal
- `tutorial_curiosidad`: Curiosidades / Datos Perturbadores / Tech
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple


GREETING_DEAD_PATTERNS = re.compile(
    r"^\s*(hola\b|buenas\b|cómo están|como estan|bienvenidos|qué tal gente|que tal gente|saludos a todos)",
    re.IGNORECASE,
)

HOOK_STRONG_PATTERNS = re.compile(
    r"(\?|!|mira esto|escucha esto|no puede ser|mentira|qué es eso|que es eso|cuidado|increíble|increible|"
    r"loco|diablo|mierda|coño|espérate|esperate|pero ven acá|pero ven aca|tú supiste|tu supiste|jamás|jamas|"
    r"secreto|nadie sabe|te voy a decir|la verdad|peligro|estafa|engaño|imposible|brutal|clutch|épico|epico)",
    re.IGNORECASE,
)

DOMINICAN_PANA_PATTERNS = re.compile(
    r"\b(loco|manín|manin|pana|hermano|vaina|tigueraje|tíguere|tiguere|concho|barrio|coro|chercha|"
    r"klk|qué lo qué|que lo que|jevi|bulto|cotorra|dema|fiao|cuarto|chele|guagua|colmado|mamaguevo|"
    r"diablo|coño|anda la porra|mi loco|gente|ustedes|nosotros)\b",
    re.IGNORECASE,
)

MYSTERY_TENSION_PATTERNS = re.compile(
    r"(\?|por qué|por que|cómo es posible|como es posible|qué pasó|que paso|adivina|espera al final|"
    r"mira lo que pasa|todavía falta|todavia falta|lo peor es que|pero ahí no termina|secreto|misterio|"
    r"nadie entiende|descubr|oculto|trampa|último segundo|ultimo segundo)",
    re.IGNORECASE,
)

VISCERAL_EMOTION_PATTERNS = re.compile(
    r"(!|jajaja|ahahaha|increíble|increible|no me digas|qué locura|que locura|me da pique|indignante|"
    r"abuso|bárbaro|barbaro|asombroso|susto|miedo|grit|corre|cuidado|madre mía|madre mia|dios mío|dios mio|"
    r"diablo|coño|mierda|maldita sea|espectacular|épico|epico|clutch|ganamos|perdimos|bug|final)",
    re.IGNORECASE,
)

DEBATE_COMMENTS_PATTERNS = re.compile(
    r"\b(opinan|creen ustedes|quién tiene la razón|quien tiene la razon|están de acuerdo|estan de acuerdo|"
    r"mejor que|peor que|sobrevalorado|infravalorado|mentira|verdad|polémica|polemica|debate|vs|contra|"
    r"culpa|justo|injusto|debería|deberia|jamás|jamas|siempre|nunca|fracasa|éxito|exito|enseñaron|ensenaron)\b",
    re.IGNORECASE,
)

VALUE_CURIOSITY_PATTERNS = re.compile(
    r"\b(sabías|sabias|dato|historia|realidad|explicación|explicacion|funciona|secreto|detalle|"
    r"descubrieron|científico|cientifico|psicología|psicologia|dinero|millones|porcentaje|años|anos|"
    r"nunca habías visto|nunca habias visto|diferencia|truco|técnica|tecnica|mentalidad|cambia|vida|entiendes)\b",
    re.IGNORECASE,
)

SHAREABLE_DM_PATTERNS = re.compile(
    r"\b(cuando tú|cuando tu|tu amigo|tu pareja|tu novia|tu novio|tu mamá|tu mama|literalmente yo|"
    r"soy yo|somos nosotros|a todo el mundo le pasa|siempre pasa|típico|tipico|etiqueta|mándale|mandale)\b",
    re.IGNORECASE,
)

CLOSING_LOOP_PATTERNS = re.compile(
    r"(\?|!|y por eso|así que ya sabes|asi que ya sabes|al final|eso era todo|increíble|increible|"
    r"qué locura|que locura|mira cómo terminó|mira como termino|jamás lo olvides|jamas lo olvides|para siempre\.?)$",
    re.IGNORECASE,
)

DEFAULT_10_WEIGHTS: Dict[str, int] = {
    "p1_gancho_hipnotico": 15,
    "p2_ritmo_cero_friccion": 10,
    "p3_factor_un_pana_mio": 10,
    "p4_tension_misterio": 10,
    "p5_activacion_emocional": 10,
    "p6_carne_de_comentarios": 10,
    "p7_valor_dato_curioso": 10,
    "p8_clickbait_estrategico": 10,
    "p9_potencial_remix_dm": 10,
    "p10_factor_cierre_loop": 5,
}

CATEGORY_ANALYTICS_PROFILES: Dict[str, Dict[str, Any]] = {
    "opinion_monologo": {
        "key": "opinion_monologo",
        "label": "Video de Opinión (1 Persona)",
        "description": (
            "Evalúa monólogos y comentarios en solitario priorizando ganchos inquisitivos, "
            "escalada de conflicto/opinión polarizante (Hot Takes) y cadencia verbal sin pausas."
        ),
        "key_signals": [
            "Gancho inquisitivo o denuncia en primeros 2s (20 pts)",
            "Polarización / toma de postura para encender comentarios (20 pts)",
            "Velocidad de entrega verbal sin silencios (15 pts)",
            "Tensión argumentativa y cierre contundente",
        ],
        "weights": {
            "p1_gancho_hipnotico": 20,
            "p2_ritmo_cero_friccion": 15,
            "p3_factor_un_pana_mio": 10,
            "p4_tension_misterio": 10,
            "p5_activacion_emocional": 5,
            "p6_carne_de_comentarios": 20,
            "p7_valor_dato_curioso": 5,
            "p8_clickbait_estrategico": 5,
            "p9_potencial_remix_dm": 5,
            "p10_factor_cierre_loop": 5,
        },
        "keywords": re.compile(
            r"\b(opino|verdad|mentira|nadie dice|estafa|problema|sociedad|crítica|critica| escuchen|miren)\b",
            re.IGNORECASE,
        ),
    },
    "reacciones": {
        "key": "reacciones",
        "label": "Video Reacciones",
        "description": (
            "Mide la intensidad de micro-expresiones y exclamaciones viscerales del creador, "
            "el timing de interrupción verbal y el morbo o curiosidad del video reaccionado."
        ),
        "key_signals": [
            "Activación emocional visceral: gritos, risa o shock (25 pts)",
            "Gancho visual/auditivo inmediato sobre el clip base (15 pts)",
            "Potencial de envío por DM / reacción compartible (10 pts)",
            "Interjecciones rápidas sin quedarse callado mirando (10 pts)",
        ],
        "weights": {
            "p1_gancho_hipnotico": 15,
            "p2_ritmo_cero_friccion": 10,
            "p3_factor_un_pana_mio": 10,
            "p4_tension_misterio": 10,
            "p5_activacion_emocional": 25,
            "p6_carne_de_comentarios": 5,
            "p7_valor_dato_curioso": 5,
            "p8_clickbait_estrategico": 5,
            "p9_potencial_remix_dm": 10,
            "p10_factor_cierre_loop": 5,
        },
        "keywords": re.compile(
            r"\b(reacción|reaccion|mira esto|no puede ser|qué locura|que locura|viste eso|increíble|jajaja)\b",
            re.IGNORECASE,
        ),
    },
    "videojuegos": {
        "key": "videojuegos",
        "label": "Videojuegos / Gaming",
        "description": (
            "Detecta clímax de partida, picos de decibeles, jugadas clutch en el último segundo, "
            "contraste fallo vs. triunfo y bugs caóticos con alta velocidad visual."
        ),
        "key_signals": [
            "Clímax de adrenalina / emoción visceral y gritos (25 pts)",
            "Ritmo frenético y acción cero-fricción (20 pts)",
            "Gancho de setup de jugada imposible (15 pts)",
            "Empaque de momento épico / clutch / fail (10 pts)",
        ],
        "weights": {
            "p1_gancho_hipnotico": 15,
            "p2_ritmo_cero_friccion": 20,
            "p3_factor_un_pana_mio": 5,
            "p4_tension_misterio": 10,
            "p5_activacion_emocional": 25,
            "p6_carne_de_comentarios": 0,
            "p7_valor_dato_curioso": 0,
            "p8_clickbait_estrategico": 10,
            "p9_potencial_remix_dm": 10,
            "p10_factor_cierre_loop": 5,
        },
        "keywords": re.compile(
            r"\b(clutch|partida|juego|gaming|gameplay|jefe|boss|vida|hp|ganamos|perdimos|bug|nivel|final|kill|fps)\b",
            re.IGNORECASE,
        ),
    },
    "podcast": {
        "key": "podcast",
        "label": "Podcast / Entrevista",
        "description": (
            "Prioriza el Índice Contrarian (desafiar creencias comunes), la densidad de epifanías "
            "('Aha! Moments'), frases citables de alto valor y comprensión autónoma fuera de contexto."
        ),
        "key_signals": [
            "Índice Contrarian / Hot Take que genera debate profundo (25 pts)",
            "Densidad de Epifanía / sabiduría o revelación psicológica (25 pts)",
            "Gancho conversacional autónomo en primeros 3s (15 pts)",
            "Química de diálogo e intriga intelectual (20 pts)",
        ],
        "weights": {
            "p1_gancho_hipnotico": 15,
            "p2_ritmo_cero_friccion": 5,
            "p3_factor_un_pana_mio": 10,
            "p4_tension_misterio": 10,
            "p5_activacion_emocional": 0,
            "p6_carne_de_comentarios": 25,
            "p7_valor_dato_curioso": 25,
            "p8_clickbait_estrategico": 0,
            "p9_potencial_remix_dm": 5,
            "p10_factor_cierre_loop": 5,
        },
        "keywords": re.compile(
            r"\b(podcast|entrevista|mentalidad|éxito|exito|psicología|psicologia|dinero|fracasa|enseñaron|ensenaron|realidad)\b",
            re.IGNORECASE,
        ),
    },
    "realitys": {
        "key": "realitys",
        "label": "Realitys / Show Social",
        "description": (
            "Evalúa el Índice de Fricción Social (discusiones, careos, silencios incómodos, "
            "ironía dramática), códigos de calle/barrio y polarización para que el público tome bando."
        ),
        "key_signals": [
            "Choque emocional, careo o tensión interpersonal (20 pts)",
            "Código callejero / Factor 'Un Pana Mío' (15 pts)",
            "Guerra de bandos en comentarios: ¿quién tiene la razón? (15 pts)",
            "Intriga dramática de desenlace (15 pts)",
        ],
        "weights": {
            "p1_gancho_hipnotico": 15,
            "p2_ritmo_cero_friccion": 5,
            "p3_factor_un_pana_mio": 15,
            "p4_tension_misterio": 15,
            "p5_activacion_emocional": 20,
            "p6_carne_de_comentarios": 15,
            "p7_valor_dato_curioso": 0,
            "p8_clickbait_estrategico": 5,
            "p9_potencial_remix_dm": 5,
            "p10_factor_cierre_loop": 5,
        },
        "keywords": re.compile(
            r"\b(reality|casa|pelea|discusión|discusion|problema|dijo|cara|respeto|barrio|coro|pana|chisme)\b",
            re.IGNORECASE,
        ),
    },
    "storytime_anecdota": {
        "key": "storytime_anecdota",
        "label": "Storytime / Anécdota",
        "description": (
            "Categoría adicional: mide estructura narrativa en 3 actos (suceso chocante, "
            "complicación creciente con Open Loop y giro o remate inesperado al final)."
        ),
        "key_signals": [
            "Open Loop / tensión de misterio sostenida (25 pts)",
            "Gancho de historia personal chocante (15 pts)",
            "Empatía y cercanía narrativa (15 pts)",
            "Plot twist / remate final memorable (10 pts)",
        ],
        "weights": {
            "p1_gancho_hipnotico": 15,
            "p2_ritmo_cero_friccion": 10,
            "p3_factor_un_pana_mio": 15,
            "p4_tension_misterio": 25,
            "p5_activacion_emocional": 10,
            "p6_carne_de_comentarios": 5,
            "p7_valor_dato_curioso": 5,
            "p8_clickbait_estrategico": 0,
            "p9_potencial_remix_dm": 5,
            "p10_factor_cierre_loop": 10,
        },
        "keywords": re.compile(
            r"\b(storytime|historia|pasó|paso|día|dia|cuando|recuerdo|resulta|al final|jamás olvidaré)\b",
            re.IGNORECASE,
        ),
    },
    "tutorial_curiosidad": {
        "key": "tutorial_curiosidad",
        "label": "Curiosidades / Tech / Datos",
        "description": (
            "Categoría adicional: optimizada para píldoras educativas, datos perturbadores, "
            "secretos tecnológicos y tutoriales rápidos con alta retención por revelación."
        ),
        "key_signals": [
            "Densidad de dato oculto / curiosidad o truco (30 pts)",
            "Gancho de revelación inmediata en 2s (20 pts)",
            "Explicación directa sin relleno (15 pts)",
            "Misterio resuelto con efecto Loop (20 pts)",
        ],
        "weights": {
            "p1_gancho_hipnotico": 20,
            "p2_ritmo_cero_friccion": 15,
            "p3_factor_un_pana_mio": 0,
            "p4_tension_misterio": 15,
            "p5_activacion_emocional": 5,
            "p6_carne_de_comentarios": 5,
            "p7_valor_dato_curioso": 30,
            "p8_clickbait_estrategico": 5,
            "p9_potencial_remix_dm": 0,
            "p10_factor_cierre_loop": 5,
        },
        "keywords": re.compile(
            r"\b(sabías|sabias|secreto|truco|funciona|ciencia|tecnología|tecnologia|dato|descubrieron|explicación)\b",
            re.IGNORECASE,
        ),
    },
}


def get_category_analytics_profiles() -> List[Dict[str, Any]]:
    """Devuelve la lista serializable de perfiles de analítica por categoría."""
    result: List[Dict[str, Any]] = []
    for key, prof in CATEGORY_ANALYTICS_PROFILES.items():
        result.append(
            {
                "key": key,
                "label": prof["label"],
                "description": prof["description"],
                "key_signals": list(prof["key_signals"]),
                "weights": dict(prof["weights"]),
            }
        )
    return result


def detect_content_category(text: str, title: str = "") -> str:
    """Detecta automáticamente la categoría más probable a partir del texto y título del clip."""
    combined = f"{title} {text}".strip()
    best_cat = "opinion_monologo"
    best_hits = 0

    for key, prof in CATEGORY_ANALYTICS_PROFILES.items():
        hits = len(prof["keywords"].findall(combined))
        if hits > best_hits:
            best_hits = hits
            best_cat = key

    return best_cat


@dataclass
class ViralityScoreBreakdown:
    p1_gancho_hipnotico: int          # Max 15 en base (o ponderado por categoría)
    p2_ritmo_cero_friccion: int
    p3_factor_un_pana_mio: int
    p4_tension_misterio: int
    p5_activacion_emocional: int
    p6_carne_de_comentarios: int
    p7_valor_dato_curioso: int
    p8_clickbait_estrategico: int
    p9_potencial_remix_dm: int
    p10_factor_cierre_loop: int
    total_points: int                 # 0 - 100
    final_grade: float                # 0.0 - 10.0
    classification: str               # Oro / Buen video / Meh / Bodrio
    qualifies_for_youtube: bool       # total_points >= 85
    category: str = "opinion_monologo"
    category_label: str = "Video de Opinión (1 Persona)"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_virality_10_points(
    text: str,
    duration: float,
    words: Optional[List[Dict[str, Any]]] = None,
    title: str = "",
    llm_scores: Optional[Dict[str, Any]] = None,
    category: str = "auto",
    acoustic_score: Optional[float] = None,
) -> ViralityScoreBreakdown:
    """
    Evalúa un segmento candidato según los 10 puntos clave, pondera cada eje
    usando la matriz específica de la categoría (`category`) e integra la señal
    dual de picos acústicos (`acoustic_score`) y ejes semánticos del LLM
    (`hook_strength`, `standalone_value`, `virality_potential`).
    """
    clean_text = (text or "").strip()
    words = words or []
    dur = max(1.0, float(duration))

    resolved_cat = (
        detect_content_category(clean_text, title)
        if not category or category == "auto" or category not in CATEGORY_ANALYTICS_PROFILES
        else category
    )
    cat_profile = CATEGORY_ANALYTICS_PROFILES[resolved_cat]
    cat_weights = cat_profile["weights"]

    if words:
        first_t = words[0].get("start", 0.0) if isinstance(words[0], dict) else getattr(words[0], "start", 0.0)
        first_3s_words = [
            (w.get("word", "") if isinstance(w, dict) else getattr(w, "word", ""))
            for w in words
            if ((w.get("start", 0.0) if isinstance(w, dict) else getattr(w, "start", 0.0)) - first_t) <= 3.5
        ]
        first_3s_text = " ".join(first_3s_words).strip()
        last_3s_words = [
            (w.get("word", "") if isinstance(w, dict) else getattr(w, "word", ""))
            for w in words[-12:]
        ]
        last_text = " ".join(last_3s_words).strip()
    else:
        word_tokens = clean_text.split()
        first_3s_text = " ".join(word_tokens[:12])
        last_text = " ".join(word_tokens[-12:])

    # 1. Gancho Hipnótico (base max 15)
    if llm_scores and "p1_gancho_hipnotico" in llm_scores:
        p1 = int(llm_scores["p1_gancho_hipnotico"])
    else:
        if GREETING_DEAD_PATTERNS.search(first_3s_text):
            p1 = 0
        elif HOOK_STRONG_PATTERNS.search(first_3s_text) or len(first_3s_text.split()) >= 7:
            p1 = 15
        else:
            p1 = 7

    # 2. Ritmo y Cero-Fricción Visual (base max 10)
    if llm_scores and "p2_ritmo_cero_friccion" in llm_scores:
        p2 = int(llm_scores["p2_ritmo_cero_friccion"])
    else:
        wps = len(clean_text.split()) / dur
        max_gap = 0.0
        if len(words) > 2:
            for i in range(len(words) - 1):
                w_next = words[i + 1]
                w_curr = words[i]
                s_next = float(w_next.get("start", 0.0) if isinstance(w_next, dict) else getattr(w_next, "start", 0.0))
                e_curr = float(w_curr.get("end", 0.0) if isinstance(w_curr, dict) else getattr(w_curr, "end", 0.0))
                gap = s_next - e_curr
                if gap > max_gap:
                    max_gap = gap
        if wps >= 2.2 and max_gap <= 1.8:
            p2 = 10
        elif wps >= 1.4 and max_gap <= 3.0:
            p2 = 5
        else:
            p2 = 0

    # 3. Factor "Un Pana Mío" (base max 10)
    if llm_scores and "p3_factor_un_pana_mio" in llm_scores:
        p3 = int(llm_scores["p3_factor_un_pana_mio"])
    else:
        pana_hits = len(DOMINICAN_PANA_PATTERNS.findall(clean_text))
        if pana_hits >= 2:
            p3 = 10
        elif pana_hits == 1 or "tú" in clean_text.lower() or "ustedes" in clean_text.lower() or "tu " in clean_text.lower():
            p3 = 5
        else:
            p3 = 0

    # 4. Tensión del Misterio (base max 10)
    if llm_scores and "p4_tension_misterio" in llm_scores:
        p4 = int(llm_scores["p4_tension_misterio"])
    else:
        mys_hits = len(MYSTERY_TENSION_PATTERNS.findall(clean_text))
        if mys_hits >= 2:
            p4 = 10
        elif mys_hits == 1:
            p4 = 5
        else:
            p4 = 0

    # 5. Activación Emocional Visceral (base max 10)
    if llm_scores and "p5_activacion_emocional" in llm_scores:
        p5 = int(llm_scores["p5_activacion_emocional"])
    else:
        emo_hits = len(VISCERAL_EMOTION_PATTERNS.findall(clean_text))
        if emo_hits >= 3:
            p5 = 10
        elif emo_hits >= 1:
            p5 = 5
        else:
            p5 = 0

    # 6. Carne de Comentarios / Polarización (base max 10)
    if llm_scores and "p6_carne_de_comentarios" in llm_scores:
        p6 = int(llm_scores["p6_carne_de_comentarios"])
    else:
        deb_hits = len(DEBATE_COMMENTS_PATTERNS.findall(clean_text))
        if deb_hits >= 2:
            p6 = 10
        elif deb_hits == 1 or "?" in clean_text:
            p6 = 5
        else:
            p6 = 0

    # 7. Valor Agregado / Dato Curioso / Epifanía (base max 10)
    if llm_scores and "p7_valor_dato_curioso" in llm_scores:
        p7 = int(llm_scores["p7_valor_dato_curioso"])
    else:
        val_hits = len(VALUE_CURIOSITY_PATTERNS.findall(clean_text))
        if val_hits >= 2 or len(clean_text.split()) >= 110:
            p7 = 10
        elif val_hits == 1 or len(clean_text.split()) >= 65:
            p7 = 5
        else:
            p7 = 0

    # 8. Clickbait Estratégico (base max 10)
    if llm_scores and "p8_clickbait_estrategico" in llm_scores:
        p8 = int(llm_scores["p8_clickbait_estrategico"])
    else:
        if title and len(title) >= 18 and "REACCIÓN ÉPICA EN VIVO SIN FILTRO" not in title:
            p8 = 10
        elif HOOK_STRONG_PATTERNS.search(clean_text):
            p8 = 5
        else:
            p8 = 0

    # 9. Potencial de Remix o Compartir en DM (base max 10)
    if llm_scores and "p9_potencial_remix_dm" in llm_scores:
        p9 = int(llm_scores["p9_potencial_remix_dm"])
    else:
        dm_hits = len(SHAREABLE_DM_PATTERNS.findall(clean_text))
        if dm_hits >= 2 or (p3 == 10 and p5 == 10):
            p9 = 10
        elif dm_hits >= 1 or p5 == 10:
            p9 = 5
        else:
            p9 = 0

    # 10. Factor de Cierre o Loop (base max 5)
    if llm_scores and "p10_factor_cierre_loop" in llm_scores:
        p10 = int(llm_scores["p10_factor_cierre_loop"])
    else:
        if CLOSING_LOOP_PATTERNS.search(last_text) or len(last_text.split()) >= 6:
            p10 = 5
        elif len(last_text.split()) >= 3:
            p10 = 2
        else:
            p10 = 0

    # Escalar cada componente desde su máximo base (DEFAULT_10_WEIGHTS) al peso de la categoría activa
    raw_map = {
        "p1_gancho_hipnotico": p1,
        "p2_ritmo_cero_friccion": p2,
        "p3_factor_un_pana_mio": p3,
        "p4_tension_misterio": p4,
        "p5_activacion_emocional": p5,
        "p6_carne_de_comentarios": p6,
        "p7_valor_dato_curioso": p7,
        "p8_clickbait_estrategico": p8,
        "p9_potencial_remix_dm": p9,
        "p10_factor_cierre_loop": p10,
    }

    weighted_map: Dict[str, int] = {}
    for k, raw_val in raw_map.items():
        base_max = DEFAULT_10_WEIGHTS[k]
        target_max = cat_weights.get(k, base_max)
        if base_max > 0 and target_max > 0:
            ratio = min(1.0, max(0.0, float(raw_val) / float(base_max)))
            weighted_map[k] = int(round(ratio * target_max))
        else:
            weighted_map[k] = 0

    # Bono de afinidad de categoría cuando el contenido contiene señales directas de la categoría evaluada
    cat_keyword_hits = len(cat_profile["keywords"].findall(f"{title} {clean_text}"))
    affinity_bonus = min(8, cat_keyword_hits * 2)

    base_total = sum(weighted_map.values()) + affinity_bonus

    # Señal Dual: Ejes Semánticos LLM (hook_strength, standalone_value, virality_potential) + Energía Acústica (0-10)
    dual_signal_delta = 0.0
    if llm_scores and any(k in llm_scores for k in ("hook_strength", "standalone_value", "virality_potential")):
        hs = float(llm_scores.get("hook_strength", 7.5))
        sv = float(llm_scores.get("standalone_value", 7.5))
        vp = float(llm_scores.get("virality_potential", 7.5))
        llm_mean_10 = (hs * 0.40) + (sv * 0.30) + (vp * 0.30)
        # Centrado en 6.5: si el LLM califica 9.5 suma +9 pts; si califica 4.0 resta -7.5 pts
        dual_signal_delta += (llm_mean_10 - 6.5) * 3.0

    if acoustic_score is not None:
        ac_val = max(0.0, min(10.0, float(acoustic_score)))
        # Centrado en 5.5: picos fuertes de energía (ej. 9.5) suman hasta +8 pts; audio plano (2.0) resta -7 pts
        dual_signal_delta += (ac_val - 5.5) * 2.0

    total = max(0, min(100, int(round(base_total + dual_signal_delta))))
    grade = round(total / 10.0, 1)

    if total >= 90:
        classification = "Oro en las manos (9.0 - 10.0) 🔥"
    elif total >= 75:
        classification = "Buen video (7.5 - 8.9) ⚡"
    elif total >= 50:
        classification = "Meh (5.0 - 7.4) 😐"
    else:
        classification = "Bodrio total (< 5.0) ❌"

    return ViralityScoreBreakdown(
        p1_gancho_hipnotico=weighted_map["p1_gancho_hipnotico"],
        p2_ritmo_cero_friccion=weighted_map["p2_ritmo_cero_friccion"],
        p3_factor_un_pana_mio=weighted_map["p3_factor_un_pana_mio"],
        p4_tension_misterio=weighted_map["p4_tension_misterio"],
        p5_activacion_emocional=weighted_map["p5_activacion_emocional"],
        p6_carne_de_comentarios=weighted_map["p6_carne_de_comentarios"],
        p7_valor_dato_curioso=weighted_map["p7_valor_dato_curioso"],
        p8_clickbait_estrategico=weighted_map["p8_clickbait_estrategico"],
        p9_potencial_remix_dm=weighted_map["p9_potencial_remix_dm"],
        p10_factor_cierre_loop=weighted_map["p10_factor_cierre_loop"],
        total_points=total,
        final_grade=grade,
        classification=classification,
        qualifies_for_youtube=True,
        category=resolved_cat,
        category_label=cat_profile["label"],
    )


def select_and_order_shorts_by_virality_rules(
    candidates: List[Dict[str, Any]],
    max_total_shorts: int = 8,
    youtube_min_score: int = 0,
    max_youtube_shorts: int = 24,
    min_acceptable_score: int = 50,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Ordena los candidatos válidos por viralidad sin bloquear ningún Short para YouTube:
    todos los Shorts seleccionados se habilitan para YouTube, Instagram, TikTok y Facebook.
    """
    valid = [c for c in candidates if int(c.get("virality_score", 0)) >= min_acceptable_score]
    valid.sort(key=lambda x: (int(x.get("virality_score", 0)), float(x.get("score", 0.0))), reverse=True)

    top_selected = valid[:max_total_shorts]

    high_tier = [c for c in top_selected if int(c.get("virality_score", 0)) >= youtube_min_score]
    low_tier = [c for c in top_selected if int(c.get("virality_score", 0)) < youtube_min_score]

    youtube_list = high_tier[:max_youtube_shorts]
    for c in top_selected:
        c["publish_to_youtube"] = True
        c["publish_to_other_networks"] = True

    ordered_all = high_tier + low_tier
    other_networks_only_list = [c for c in ordered_all if not c["publish_to_youtube"]]

    return ordered_all, youtube_list, other_networks_only_list

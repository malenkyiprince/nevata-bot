"""Прозорий індекс ознак подачі, окремий від достовірності фактів."""
import re
import unicodedata

CRITERIA = (
    ("emotional_pressure", "Емоційний тиск", 25),
    ("misleading_context", "Викривлення контексту", 25),
    ("unsupported_certainty", "Безпідставна категоричність", 20),
    ("logical_pressure", "Хибний вибір або висновок", 15),
    ("loaded_framing", "Нав’язана передумова й ярлики", 15),
)

RUBRIC = """Окремо оціни маніпулятивність САМЕ вхідного матеріалу, не знайдених джерел і не власної відповіді.
Робоче визначення: подача, що підштовхує до висновку через тиск, викривлення або приховану передумову замість достатніх доказів.
Це оцінка ознак тексту, не доведення наміру автора і не діагноз його особистості.
emotional_pressure: тиск страхом, гнівом, соромом або провиною; емоційна тема сама по собі не ознака.
misleading_context: істотний контекст викривлено або вибірково подано; потрібен source_ids з прямими доказами відмінності.
unsupported_certainty: невизначене, узагальнення чи прогноз подано як гарантований факт.
logical_pressure: хибна дилема, висновок без логічного зв’язку, вимога погодитися замість аргументу.
loaded_framing: навідне запитання, необґрунтована прихована передумова, ярлик замість опису.
Для КОЖНОГО критерію: level=0 ознак не виявлено, 1 є можливий/помірний сигнал, 2 є виразний сигнал.
При level>0 quote — точний короткий уривок вхідного тексту до 220 символів; reason — пояснення механізму в 1 реченні, source_ids — потрібні зовнішні докази.
Для level=0 quote="", reason="", source_ids=[]. Не нараховуй бали без конкретного уривка.
Не плутай хибний факт з маніпулятивною подачею: неправдива нейтральна фраза може мати низький індекс, правдива подача з тиском — високий.
Не штрафуй звичайні запитання, цитування чужої риторики для аналізу, сарказм чи емоції автоматично; враховуй контекст.
Підтекст формулюй як можливе прочитання, не як прихований намір, який ти начебто знаєш.
tone: короткий опис тону; subtext: можливий підтекст або «Виразного прихованого посилу не виявлено».
summary: чому індекс низький/високий, до 1 речення; neutral_rewrite: нейтральне формулювання зі збереженням змісту, без вигаданих нових фактів.
Не виводь відсоток сам: його обчислить сервер за фіксованими вагами."""


def normalized(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def unavailable(reason="Аналіз маніпулятивності ще не виконано."):
    return {"score": None, "label": "Не оцінено", "summary": reason, "signals": []}


def assess(data, material, sources):
    if not isinstance(data, dict) or not isinstance(material, str) or not material.strip():
        return unavailable("Немає достатнього прочитаного тексту для окремої оцінки подачі.")
    criteria = data.get("criteria")
    if not isinstance(criteria, dict) or any(key not in criteria for key, _, _ in CRITERIA):
        return unavailable("Модель не завершила оцінювання всіх критеріїв.")
    corpus = normalized(material)
    by_id = {source["id"]: source for source in sources}
    signals, weighted, rejected = [], 0, False
    for key, title, weight in CRITERIA:
        value = criteria[key]
        if not isinstance(value, dict) or type(value.get("level")) is not int or value["level"] not in (0, 1, 2):
            return unavailable("Отримано некоректну оцінку критерію.")
        level = value["level"]
        if not level:
            continue
        quote, reason, ids = value.get("quote"), value.get("reason"), value.get("source_ids")
        valid = isinstance(quote, str) and 3 <= len(quote.strip()) <= 220 and normalized(quote) in corpus
        valid = valid and isinstance(reason, str) and bool(reason.strip()) and len(reason) <= 600
        valid = valid and isinstance(ids, list) and all(type(i) is int and i in by_id for i in ids)
        if key == "misleading_context":
            valid = valid and any(by_id[i].get("extracted") for i in ids)
        if not valid:
            rejected = True
            continue
        weighted += weight * level
        signals.append({"criterion": title, "weight": weight, "level": level, "quote": quote.strip(), "reason": reason.strip(),
            "sources": [{"id": i, "url": by_id[i]["url"]} for i in dict.fromkeys(ids)]})
    # Невалідні докази — не нульові бали: це неповне оцінювання.
    if rejected:
        result = unavailable("Частину ознак не вдалося підтвердити точними уривками або джерелами. Відсоток не обчислено.")
        result["signals"] = signals
        return result
    score = min(100, ((weighted + 5) // 10) * 5)
    def short(field, limit):
        value = data.get(field)
        return value.strip()[:limit] if isinstance(value, str) else ""
    return {"score": score, "label": "Високий індекс" if score >= 65 else "Помірний індекс" if score >= 30 else "Низький індекс",
        "summary": short("summary", 600), "tone": short("tone", 300), "subtext": short("subtext", 600),
        "neutral_rewrite": short("neutral_rewrite", 1000), "signals": signals,
        "note": "Індекс ознак подачі за рубрикою v1, крок 5%. Не ймовірність обману й не доведення наміру автора. 0% означає, що рубрика не виявила ознак, а не гарантію їх відсутності."}

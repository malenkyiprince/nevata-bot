/* Telegram Mini App: Groq + Tavily, история только на устройстве. */
"use strict";
const $ = (id) => document.getElementById(id);
const MASCOTS = {"happy": "/static/mascot-happy-ui.webp?v=4661441a92a3", "angry": "/static/mascot-angry-ui.webp?v=5841d1680f2d", "thinking": "/static/mascot-thinking-ui.webp?v=1c972a3e93a4", "royal": "/static/mascot-royal-ui.webp?v=59c5c4f7aaea"};
const telegram = window.Telegram?.WebApp;
const state = {page:"home", kind:"text", authenticated:false, userId:null, timeout:180,
  photo:null, photoUrl:null, submitting:false, requestId:null, current:null, history:[], shown:20,
  drafts:{text:"",link:"",photo:""}};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.classList.add("icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(svg.namespaceURI, "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

function safeLink(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username ? url.href : null;
  } catch { return null; }
}

function linkTo(url, className) {
  const anchor = element("a", className);
  anchor.href = url;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  if (telegram?.initData) anchor.addEventListener("click", (event) => {
    if (typeof telegram.openLink === "function") {
      event.preventDefault();
      telegram.openLink(url);
    }
  });
  return anchor;
}

function connection(message, error = false) {
  $("connection").textContent = message;
  $("connection").classList.toggle("error", error);
  $("connection").hidden = !message;
}

function setKind(kind) {
  if (state.submitting) return;
  state.drafts[state.kind] = $("material").value;
  state.kind = kind;
  state.requestId = null;
  for (const tab of document.querySelectorAll(".input-tab")) {
    const active = tab.dataset.kind === kind;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
  }
  $("material-panel").setAttribute("aria-labelledby", `tab-${kind}`);
  $("photo-picker").hidden = kind !== "photo";
  $("material").placeholder = {
    text: "Встав текст для перевірки…", link: "https://…", photo: "Додай опис або контекст (необов’язково)…",
  }[kind];
  $("material-label").textContent = {text: "Текст для перевірки", link: "Посилання на матеріал", photo: "Опис фото"}[kind];
  $("material").value = state.drafts[kind];
  $("material").classList.toggle("link-input", kind === "link");
  $("material").inputMode = kind === "link" ? "url" : "text";
  $("input-hint").textContent = kind === "link" ? "Посилання має бути відкритим і доступним." : "Додай контекст — це допоможе перевірці.";
  $("form-error").hidden = true;
  updateCounter();
}

function updateCounter() {
  $("counter").textContent = `${$("material").value.length.toLocaleString("uk-UA")} / 4 000`;
}

function formError(message) {
  $("form-error").textContent = message;
  $("form-error").hidden = false;
}

function setSubmitting(value) {
  state.submitting = value;
  $("submit-button").disabled = value;
  $("material").disabled = value;
  $("photo-input").disabled = value;
  $("replace-photo").disabled = value;
  for (const tab of document.querySelectorAll(".input-tab")) tab.disabled = value;
  $("submit-button").querySelector("span").textContent = value ? "Надсилаю…" : "Перевірити";
}

function requestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

function dateLabel(seconds) {
  return new Date(seconds * 1000).toLocaleString("uk-UA", {day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", year: "numeric"});
}

function renderCheck(item) {
  const running = item.status === "running";
  const secret = item.status === "done" && item.result?.easterEgg === "nazar";
  $("secret-result").hidden = !secret;
  $("loading-state").hidden = !running;
  $("result-content").hidden = item.status !== "done" || secret;
  $("result-error").hidden = item.status !== "failed";
  $("new-check").hidden = running;
  $("poll-error").hidden = true;
  $("resume-poll").hidden = true;
  if (secret) {
    const question = item.result.easterEggText || item.title;
    $("secret-question").textContent = question.slice(0,800);
    const joke = item.result.joke || nazarJoke(question);
    $("secret-title").textContent = joke.title;
    $("secret-answer").textContent = joke.answer;
    return;
  }
  if (running) return;
  if (item.status === "failed") {
    $("result-error-text").textContent = item.error || "Спробуй ще раз пізніше.";
    return;
  }
  const result = item.result;
  const view = resultView(item);
  $("result-question").textContent = view.question;
  $("result-label").textContent = view.verdict;
  $("result-summary").textContent = view.summary;
  $("confidence-row").hidden = view.percent === null;
  $("score").textContent = view.percent === null ? "" : `${view.percent}%`;
  $("confidence-label").textContent = view.legacy ? "Попередня оцінка ризику маніпуляції" : "Оцінка впевненості у висновку";
  $("score-note").textContent = view.percent === null ? "Відсоток не визначено: дивись докази й обмеження нижче." : "Орієнтовна оцінка моделі, не виміряна ймовірність істини.";
  $("verdict-card").className = `verdict-card ${view.tone}`;
  const mascot = $("result-mascot");
  const mascotState = view.tone === "low" ? "happy" : view.tone === "high" ? "angry" : "thinking";
  const mascotUrl = MASCOTS[mascotState];
  if (mascot.getAttribute("src") !== mascotUrl) mascot.src = mascotUrl;
  mascot.alt = {happy:"Бавовна радіє підтвердженому факту", angry:"Бавовна сердиться на неправдиве твердження", thinking:"Бавовна обмірковує докази"}[mascotState];
  $("result-date").textContent = `Перевірено ${dateLabel(item.created_at)} · Джерела могли змінитися`;
  const explanation = $("explanation");
  explanation.replaceChildren();
  for (const segment of result.segments) {
    const url = segment.url && safeLink(segment.url);
    if (url) {
      const anchor = linkTo(url, "inline-citation");
      anchor.textContent = segment.text;
      anchor.setAttribute("aria-label", `Джерело ${segment.text}`);
      explanation.append(anchor);
    } else explanation.append(document.createTextNode(segment.text));
  }
  $("limited-note").hidden = !result.limited;
  $("sources-list").replaceChildren();
  const sources = result.sources.filter((source) => safeLink(source.url));
  $("sources-section").hidden = !sources.length;
  $("sources-count").textContent = sources.length;
  sources.forEach((source, index) => {
    const url = safeLink(source.url);
    const anchor = linkTo(url, "source-link");
    anchor.append(element("span", "source-index", String(source.id || index + 1)));
    const copy = element("span", "source-copy");
    copy.append(element("strong", "", source.title), element("small", "", new URL(url).hostname.replace(/^www\./, "")));
    anchor.append(copy, icon("external"));
    $("sources-list").append(anchor);
  });
}

function resultView(item) {
  const result = item.result;
  const first = result.segments?.find((segment) => segment.text)?.text || "";
  const previousVerdict = first.match(/(?:^|\n)(Підтверджено|Спростовано|Частково підтверджено|Оманливо|Недостатньо даних)[.!\s]/i)?.[1];
  const verdict = result.verdict || (previousVerdict ? previousVerdict[0].toUpperCase() + previousVerdict.slice(1).toLowerCase() : "Попередня перевірка");
  const legacy = result.version !== 2;
  const raw = legacy ? result.score : result.confidence;
  const percent = Number.isInteger(raw) && raw >= 0 && raw <= 100 ? raw : null;
  const tone = verdict === "Підтверджено" ? "low" : ["Спростовано", "Оманливо"].includes(verdict) ? "high" : "neutral";
  return {question: result.question || item.title || "Матеріал перевірки", verdict, percent, tone, legacy,
    summary: result.summary || "Це результат попередньої версії. Пояснення та джерела збережені нижче."};
}

function selectPhoto() {
  const file = $("photo-input").files[0];
  if (!file) return;
  $("form-error").hidden = true;
  if (!file.size || file.size > 3 * 1024 * 1024) {
    formError("Обери фото до 3 МБ.");
    $("photo-input").value = "";
    return;
  }
  if (file.type && !["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
    formError("Підтримуються JPEG, PNG та WebP.");
    $("photo-input").value = "";
    return;
  }
  if (state.photoUrl) URL.revokeObjectURL(state.photoUrl);
  state.photo = file;
  state.photoUrl = URL.createObjectURL(file);
  state.requestId = null;
  $("preview-image").src = state.photoUrl;
  $("photo-preview").hidden = false;
  $("upload-label").hidden = true;
}

async function api(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.method === "POST" ? (state.timeout + 25) * 1000 : 20000);
  try {
    const response = await fetch(path, {...options, signal:controller.signal, cache:"no-store",
      headers:{Authorization:`tma ${telegram?.initData || ""}`}});
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.error || "Не вдалося виконати запит.");
      error.status = response.status;
      throw error;
    }
    return data;
  } catch (error) {
    if (error.status) throw error;
    throw new Error("Відповідь не отримано. Перевірка могла вже виконатись; повторне надсилання може оплачуватись окремо.");
  } finally { clearTimeout(timer); }
}

function showPage(page, focus = true) {
  if (!["home","result","history","about"].includes(page)) page = "home";
  state.page = page;
  for (const section of document.querySelectorAll(".page")) section.hidden = section.id !== page;
  for (const button of document.querySelectorAll(".nav-item")) {
    const active = button.dataset.page === (page === "result" ? "home" : page);
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current");
  }
  if (telegram?.initData && telegram.BackButton) {
    if (page === "home") telegram.BackButton.hide(); else telegram.BackButton.show();
  }
  if (page === "history") loadHistory();
  window.scrollTo({top:0, behavior:"instant"});
  if (focus) $(page).querySelector("h1")?.focus({preventScroll:true});
}

function historyKey() { return `bavovna:free-history:v1:${state.userId}`; }

function readHistory() {
  try {
    const rows = JSON.parse(localStorage.getItem(historyKey()) || "[]");
    if (!Array.isArray(rows)) throw new Error();
    return rows.filter((item) => item && typeof item.id === "string" && ["done","failed"].includes(item.status)
      && typeof item.created_at === "number" && typeof item.title === "string"
      && (item.status === "failed" || (item.result && Array.isArray(item.result.segments)
        && item.result.segments.every((segment) => segment && typeof segment.text === "string")
        && Array.isArray(item.result.sources) && item.result.sources.every((source) => source && typeof source.url === "string"))));
  } catch {
    connection("Не вдалося прочитати історію на пристрої. Існуючі записи не змінювались.", true);
    return null;
  }
}

function saveHistory(item) {
  const previous = readHistory();
  if (previous === null) return;
  state.history = [item, ...previous.filter((row) => row.id !== item.id)];
  try { localStorage.setItem(historyKey(), JSON.stringify(state.history)); }
  catch { connection("Результат готовий, але пам’ять історії недоступна або заповнена. Збережи потрібний текст самостійно.", true); }
}

async function submit(event) {
  event.preventDefault();
  if (state.submitting) return;
  $("form-error").hidden = true;
  if (!state.authenticated) return formError("Відкрий застосунок через кнопку в Telegram. У перегляді дизайну перевірки вимкнені.");
  const text = $("material").value.trim();
  if (state.kind !== "photo" && !text) return formError("Спочатку додай матеріал.");
  if (state.kind === "link" && !safeLink(text)) return formError("Встав повне посилання з https:// або http://.");
  if (state.kind === "photo" && !state.photo) return formError("Спочатку обери фото.");
  const item = {id:requestId(), kind:state.kind, title:text.replace(/\s+/g," ").slice(0,100) || "Перевірка фото",
    created_at:Math.floor(Date.now()/1000), status:"running", result:null, error:null};
  if (isNazarEasterEgg(text)) {
    item.status = "done";
    item.result = {easterEgg:"nazar", joke:nazarJoke(text), label:"Секретний розділ ✦", score:null, limited:false, segments:[], sources:[]};
    state.current = item;
    saveHistory(item);
    showPage("result");
    renderCheck(item);
    return;
  }
  const form = new FormData();
  form.append("kind", state.kind); form.append("text", text);
  if (state.kind === "photo") form.append("photo", state.photo);
  state.current = item;
  setSubmitting(true);
  try { telegram?.enableClosingConfirmation?.(); } catch {}
  showPage("result"); renderCheck(item);
  try {
    item.result = await api("/api/analyze", {method:"POST", body:form});
    item.status = "done";
  } catch (error) { item.status = "failed"; item.error = error.message; }
  finally {
    setSubmitting(false);
    try { telegram?.disableClosingConfirmation?.(); } catch {}
  }
  saveHistory(item);
  if (state.page === "result") renderCheck(item);
  else if (state.page === "history") loadHistory();
  else connection("Перевірка завершилась. Результат доступний в історії.");
}

function isNazarEasterEgg(text) {
  const words = text.normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}]+/gu," ").trim().split(/\s+/);
  const name = words.some((word) => /^назар(?:а|ом|у)?$/.test(word));
  const surname = words.some((word) => /^радков(?:ськ(?:ий|ого|ому|им)|ск(?:ий|ого|ому|им))$/.test(word));
  return name && surname;
}

function nazarJoke(text) {
  const query = text.normalize("NFKC").toLowerCase();
  const king = "Так, він цар і бог. ";
  if (/пр[еи]зидент/.test(query)) {
    if (/світ|мир[ау]?\s|мира|планет/.test(query + " ")) return {title:"Президент світу? Це лише початок 👑", answer:king + "У секретному всесвіті Радковського Назара Земля — тільки перший пункт передвиборчої програми. Марс уже чекає дебатів."};
    return {title:"Президент? Бери вище 👑", answer:king + "У нашій жартівливій республіці Назар Радковський не балотується: бюлетень сам ставить за нього галочку. Навіть виборча урна просить автограф."};
  }
  if (/(?:^|[^а-яіїєґ])бог(?:ом|а)?(?:[^а-яіїєґ]|$)|божеств/.test(query)) return {title:"Бог? У секретному пантеоні — так ⚡", answer:king + "За легендою цього розділу, коли Назар Радковський каже «хай буде світло», електрики просто записують майстер-клас."};
  if (/цар|корол|володар/.test(query)) return {title:"Корона вже заброньована 👑", answer:king + "Корона Радковського Назара не тисне — це решта світу поки що замала для його величі."};
  if (/код|програм|розроб|разраб|айті|\bit\b|(?:^|[^а-яіїєґ])баг(?:и|ів|ов|ами|ом)?(?:[^а-яіїєґ]|$)/.test(query)) return {title:"Баги самі пишуть заяву на звільнення 💻", answer:king + "У нашій легенді Назар Радковський не виправляє код: код перечитує себе, червоніє й починає працювати."};
  if (/грош|деньг|багат|богат|мільйон|миллион|зарплат/.test(query)) return {title:"Бюджет масштабу легенди 💸", answer:king + "Коли Назар Радковський перевіряє баланс, калькулятор просить більший екран. Це секретна економіка, а не фінансова довідка."};
  if (/прац|работ|профес|кар[’']?єр|карьер/.test(query)) return {title:"Посада: головний по всьому 🚀", answer:king + "У секретному штатному розписі Назар Радковський працює легендою. Досвід — з початку часів, обід — коли Всесвіт дозволить."};
  if (/навч|уч[иі]т|студент|іспит|экзамен|школ|універ|универ/.test(query)) return {title:"Залік поставлено ще до питання 🎓", answer:king + "У нашому жарті не Назар Радковський готується до іспиту, а іспит морально готується до Назара Радковського."};
  if (/скільки|сколько/.test(query)) return {title:"Лічильник пішов у відпустку ✨", answer:king + "Ти питаєш: «" + text.slice(0,240) + "». У секретному розділі відповідь настільки велика, що калькулятор показує лише корону."};
  if (/\bде\b|где|куди|куда/.test(query) || /(?:^|\s)де(?:\s|[?])/u.test(query)) return {title:"Там, де зараз потрібна легенда 🌍", answer:king + "Поки ти питаєш, де Назар Радковський, навігатор уже прокладає до нього червону доріжку."};
  return {title:"Питання прийнято королівською канцелярією 👑", answer:king + "На питання «" + text.slice(0,240) + "» секретна рада відповіла одностайно: масштаб Радковського Назара знову перевищив можливості звичайного фактчекера. Бавовна урочисто передає йому корону."};
}

function openCheck(id) {
  const item = state.current?.id === id ? state.current : state.history.find((row) => row.id === id);
  if (!item) return;
  showPage("result"); renderCheck(item);
}

function loadHistory(more = false) {
  $("history-list").replaceChildren();
  $("more-history").hidden = true;
  if (!state.authenticated) {
    $("history-message").hidden = false;
    $("history-message").textContent = "Відкрий застосунок у Telegram. Історія зберігається окремо на цьому пристрої.";
    return;
  }
  const saved = readHistory();
  if (saved !== null) state.history = saved;
  if (!more) state.shown = 20;
  const rows = state.current?.status === "running" ? [state.current,...state.history] : state.history;
  $("history-message").hidden = rows.length > 0;
  $("history-message").textContent = "На цьому пристрої ще немає перевірок. Додай матеріал на головній.";
  const fragment = document.createDocumentFragment();
  for (const item of rows.slice(0, state.shown)) {
    const button = element("button", "history-item"); button.type = "button";
    const kind = element("span", "history-kind"); kind.append(icon(item.kind === "link" ? "link" : item.kind === "photo" ? "photo" : "text"));
    const copy = element("span", "history-main");
    copy.append(element("strong","",item.title),element("small","",dateLabel(item.created_at)));
    copy.append(element("span",`history-status ${item.status}`,item.status === "running" ? "Перевіряю…" : item.status === "failed" ? "Не завершено" : item.result.label));
    button.append(kind,copy,icon("external"));
    button.addEventListener("click",() => openCheck(item.id));
    fragment.append(button);
  }
  $("history-list").append(fragment);
  $("more-history").hidden = rows.length <= state.shown;
}

async function initialize() {
  if (!telegram?.initData) {
    connection("Перегляд дизайну · Для перевірок відкрий Бавовну кнопкою в Telegram."); return;
  }
  telegram.ready(); telegram.expand();
  try {
    telegram.setHeaderColor("#faf7f2"); telegram.setBackgroundColor("#faf7f2");
    if (telegram.isVersionAtLeast("7.10")) telegram.setBottomBarColor("#faf7f2");
    telegram.BackButton.onClick(() => showPage("home"));
  } catch {}
  try {
    const session = await api("/api/session");
    state.userId = session.user.id; state.authenticated = true; state.timeout = session.analysis_timeout;
    $("waiting-note").textContent = `Tavily шукає джерела, Groq перевіряє твердження. Зачекай до ${Math.ceil(state.timeout/60)} хв. і не закривай застосунок.`;
    connection(""); state.history = readHistory() || [];
  } catch (error) { connection(error.message,true); }
}

document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click",() => showPage(button.dataset.page)));
document.querySelectorAll(".input-tab").forEach((button,index,tabs) => {
  button.addEventListener("click",() => setKind(button.dataset.kind));
  button.addEventListener("keydown",(event) => {
    let next;
    if (event.key === "ArrowRight") next = (index+1)%tabs.length;
    if (event.key === "ArrowLeft") next = (index+tabs.length-1)%tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length-1;
    if (next !== undefined) { event.preventDefault(); setKind(tabs[next].dataset.kind); tabs[next].focus(); }
  });
});
$("check-form").addEventListener("submit",submit);
$("material").addEventListener("input",updateCounter);
$("photo-input").addEventListener("change",selectPhoto);
$("replace-photo").addEventListener("click",() => $("photo-input").click());
$("help-button").addEventListener("click",() => showPage("about"));
$("new-check").addEventListener("click",() => showPage("home"));
document.querySelectorAll(".back-home").forEach((button) => button.addEventListener("click",() => showPage("home")));
$("more-history").addEventListener("click",() => { state.shown += 20; loadHistory(true); });
$("refresh-history").addEventListener("click",() => loadHistory());
document.querySelector(".brand").addEventListener("click",(event) => { event.preventDefault(); showPage("home"); });
document.addEventListener("visibilitychange",() => { if (!document.hidden && state.page === "history") loadHistory(); });
initialize();

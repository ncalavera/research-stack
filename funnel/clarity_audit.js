export const meta = {
  name: "clarity-audit",
  description:
    "Веер ясности: N узких агентов-искателей по критериям → находки единой схемой → опус-правщик чинит по close_condition → цикл, пока блокеров нет. Заменяет один субъективный clarity-проход; штамп прежний (clarity.lock). Хардкод-словарь term_gate остаётся бесплатным пред-фильтром, но «✓» ясности теперь даёт веер.",
  whenToUse:
    "Шаг 8.5 воронки вместо одиночного опус-редактора ясности. Запуск: Workflow({scriptPath:'./funnel/clarity_audit.js', args:{topic:'<topic>'}}). После — stamp_clarity + run.py.",
  phases: [
    {
      title: "Find",
      detail:
        "Узкие искатели по критериям ясности (sonnet), read-only, находки единой схемой",
    },
    {
      title: "Fix",
      detail:
        "Опус-правщик чинит narratives.json по находкам, проверяет close_condition",
    },
  ],
};

// Пути темы и корень репозитория НЕ строим от текущей папки — workflow зовут
// через scriptPath из любого cwd. ROOT выводим из расположения самого файла
// (он лежит на уровень глубже, в funnel/), переопределяется RESEARCH_STACK_ROOT.
// DATA_ROOT учитывает хранилище (RESEARCH_VAULT) для данных тем, иначе — корень репо.
import { fileURLToPath } from "url";
import { dirname } from "path";
const ROOT =
  process.env.RESEARCH_STACK_ROOT ||
  dirname(dirname(fileURLToPath(import.meta.url))); // корень репозитория для `cd ${ROOT} && python3 funnel/...`
const DATA_ROOT = process.env.RESEARCH_VAULT || ROOT; // корень данных тем

// args иногда приходит JSON-строкой — нормализуем; молчаливого дефолта
// темы НЕТ (иначе при сбое передачи веер правит чужой отчёт).
let _A = args;
if (typeof _A === "string") {
  try {
    _A = JSON.parse(_A);
  } catch {
    _A = {};
  }
}
_A = _A || {};
const TOPIC = _A.topic;
if (typeof TOPIC !== "string" || !/^[a-z0-9][a-z0-9_-]{2,}$/.test(TOPIC)) {
  throw new Error(
    `clarity_audit: некорректная тема «${TOPIC}» (args тип=${typeof args}). ` +
      `Передай args:{topic:'<topic>'} явной строкой. Молчаливого дефолта нет, ` +
      `чтобы при сбое передачи args не править чужой отчёт.`,
  );
}
const NARR = `${DATA_ROOT}/topics/${TOPIC}/narratives.json`;
const CFG = `${DATA_ROOT}/topics/${TOPIC}/config.json`;
const FINDINGS = `${DATA_ROOT}/topics/${TOPIC}/clarity_findings.json`;
const MAX_ROUNDS = 3;

// ─── Схема находки: детерминированный контракт между искателем и правщиком ───
const FINDING_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["findings"],
  properties: {
    findings: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: [
          "criterion",
          "severity",
          "location",
          "span",
          "problem",
          "fix_hint",
          "close_condition",
        ],
        properties: {
          criterion: {
            type: "string",
            description:
              "ключ критерия (jargon|self_contained|number_referent|abstract|org_abbrev)",
          },
          severity: { type: "string", enum: ["block", "warn"] },
          location: {
            type: "string",
            description:
              "где: _infographic.caption | _infographic.stats[i] | _tldr[i] | глава <точное название>",
          },
          span: {
            type: "string",
            description:
              "ТОЧНАЯ цитата проблемного места из текста (для поиска и проверки закрытия)",
          },
          problem: { type: "string", description: "что не так, одна строка" },
          fix_hint: {
            type: "string",
            description:
              "чем заменить / что добавить (пояснение 3-7 слов и т.п.)",
          },
          close_condition: {
            type: "string",
            description:
              "проверяемое условие: когда находка считается закрытой",
          },
        },
      },
    },
  },
};

// ─── Критерии (MECE). Каждый искатель видит ВЕСЬ текст в порядке чтения, но
//     ищет только свой класс проблем — узкая задача = меньше промахов. ───
const READING_ORDER = `Порядок чтения (как видит читатель отчёта): сначала _infographic (title, каждый stats[].label, caption), затем _tldr[] по порядку, затем главы строго в порядке section_order из config.json. ВАЖНО: инфографика и _tldr идут РАНЬШЕ глав — термин, впервые встреченный там, должен быть раскрыт там, а не в главе ниже.`;

const COMMON = `Читаешь два файла: ${NARR} (проза) и ${CFG} (порядок глав в section_order). ${READING_ORDER}
Цитатные ссылки (<a href=...>...</a>) — это будущие сноски, НЕ жаргон; их содержимое игнорируй. Аудитория отчёта — читатель без технического бэкграунда.
Ты ТОЛЬКО находишь, НЕ правишь. Верни находки строго схемой. Если по твоему критерию чисто — верни {"findings": []}. span — дословная короткая цитата (8-15 слов), по которой правщик найдёт место.`;

const FINDERS = [
  {
    key: "jargon",
    label: "find:jargon",
    prompt: `${COMMON}

ТВОЙ КРИТЕРИЙ — «жаргон без пояснения при ПЕРВОМ упоминании (глобально, в порядке чтения)».
Пройди текст в порядке чтения и для КАЖДОГО термина/аббревиатуры/названия алгоритма/продукта/фреймворка/протокола найди ПЕРВОЕ вхождение и проверь: есть ли вплотную (в той же фразе/скобках) пояснение простыми словами в 3-7 слов?
Промах (severity=block): первое вхождение БЕЗ пояснения — даже если ниже в главе оно потом объясняется. Особо проверь инфографику и _tldr: термины там часто впервые и без раскрытия.
Не считай промахом: общеупотребимые слова (поиск, выдача, ссылка, сайт), имена-площадки, уже раскрытые при первом вхождении.
close_condition формулируй как: «у первого вхождения '<термин>' стоит пояснение 3-7 слов».`,
  },
  {
    key: "self_contained",
    label: "find:self_contained",
    prompt: `${COMMON}

ТВОЙ КРИТЕРИЙ — «самодостаточность главы».
Читатель может открыть отчёт на любой главе. Для каждой главы проверь: вводит ли она впервые в СВОЁМ тексте ключевой термин/аббревиатуру без короткого пояснения, опираясь на то, что «раскрыто в другой главе или в _tldr»?
Промах (severity=warn): глава использует жаргон без локального мини-пояснения при первом упоминании ВНУТРИ этой главы.
Не дублируй находки искателя jargon про инфографику/_tldr — тебя интересуют именно главы и их внутренняя самодостаточность.
close_condition: «в главе '<название>' первое упоминание '<термин>' несёт локальное пояснение».`,
  },
  {
    key: "number_referent",
    label: "find:numbers",
    prompt: `${COMMON}

ТВОЙ КРИТЕРИЙ — «число без единицы или явного референта».
Найди числа/диапазоны/проценты, у которых из текста рядом непонятно, ЧТО именно измеряется или в чём единица (пример плохого: голый «20–40»; хорошего: «20–40 позиций в выдаче»).
Промах (severity=warn): число без единицы/референта. НЕ трогай даты, доли с явным референтом, номера версий.
ВАЖНО: не предлагай добавлять НОВЫЕ числа — только привязать существующее к референту словами. close_condition: «у числа '<n>' назван референт/единица».`,
  },
  {
    key: "abstract",
    label: "find:abstract",
    prompt: `${COMMON}

ТВОЙ КРИТЕРИЙ — «абстрактный оборот без разворота ‘— то есть…’».
Найди абстрактные именные обороты в выводах/_tldr/главах, которые непонятны без примера и НЕ развёрнуты (пример плохого: «проверяемая репутация» без расшифровки; хорошего: «… — то есть публикации, профиль в каталоге»).
Промах (severity=warn): абстракция, по которой читатель не поймёт «а что конкретно?», без разворота через «— то есть…», «например», скобку-пример.
close_condition: «оборот '<span>' развёрнут примером/расшифровкой».`,
  },
  {
    key: "org_abbrev",
    label: "find:org_abbrev",
    prompt: `${COMMON}

ТВОЙ КРИТЕРИЙ — «аббревиатура организации/продукта в выводах без полного имени».
В _tldr, инфографике и выводных предложениях глав найди аббревиатуры организаций/сервисов, поданные без полного имени при первом упоминании.
Промах (severity=warn): орг/продукт-аббревиатура без полного имени при первом упоминании в выводном контексте.
Не дублируй термины-механизмы (их ловит jargon): тебя интересуют именно ИМЕНА организаций/инструментов.
close_condition: «первое упоминание '<аббр>' несёт полное имя».`,
  },
];

phase("Find");
log(
  `Веер ясности по теме ${TOPIC}: ${FINDERS.length} искателей, до ${MAX_ROUNDS} раундов.`,
);

let round = 0;
let history = [];
let lastFindings = [];

while (round < MAX_ROUNDS) {
  round++;
  // ── Find: искатели параллельно (барьер — правщику нужен полный список) ──
  const results = await parallel(
    FINDERS.map(
      (f) => () =>
        agent(f.prompt, {
          label: `${f.label}:r${round}`,
          phase: "Find",
          schema: FINDING_SCHEMA,
          model: "sonnet",
        }),
    ),
  );
  const findings = results
    .filter(Boolean)
    .flatMap((r) => r.findings || [])
    .map((x, i) => ({ id: `r${round}-${i + 1}`, ...x }));

  const blockers = findings.filter((f) => f.severity === "block");
  log(
    `Раунд ${round}: находок ${findings.length} (блокеров ${blockers.length}, предупреждений ${findings.length - blockers.length}).`,
  );
  history.push({
    round,
    total: findings.length,
    blockers: blockers.length,
    findings,
  });
  lastFindings = findings;

  if (findings.length === 0) {
    log(`Раунд ${round}: чисто — выходим.`);
    break;
  }

  // ── Fix: один опус-правщик по всему списку (правки в одном файле нельзя параллелить) ──
  const fixPrompt = `Ты — редактор ясности. Чинишь файл ${NARR} по списку находок ниже. Правишь САМ через Edit.

НАХОДКИ (JSON, у каждой span = точная цитата места, fix_hint = как чинить, close_condition = когда закрыта):
${JSON.stringify(findings, null, 2)}

ПРАВИЛА:
- По каждой находке внеси минимальную правку, удовлетворяющую close_condition (добавь пояснение 3-7 слов вплотную к термину, разверни абстракцию, привяжи число к референту словами).
- Пояснение термину ставь ВПЛОТНУЮ к ПЕРВОМУ вхождению по порядку чтения (инфографика/‑_tldr раньше глав). Если термин впервые в инфографике/_tldr — раскрывай там, а не только в главе.
- Для самодостаточности глав допускается краткий повтор пояснения в главе (это норма, не дублирование).
ЖЁСТКИЕ РАМКИ:
- JSON обязан остаться валидным (проверь json.load после правок).
- Цитатные скобки (<a href=...>...</a>) НЕ трогай.
- НИКАКИХ новых цифр (ворот prose_gate). Числам только привязывай референт словами.
- Пояснения аббревиатур — в скобках сразу после слова (ворот term_gate ловит первое вхождение).
- Стиль: чистый язык без лишних англицизмов, инфостиль, как объяснил бы нетехническому читателю.
ПОСЛЕ ПРАВОК прогони и добейся зелёного:
  cd ${ROOT} && python3 -c "import json;json.load(open('${NARR}'))" && python3 funnel/prose_gate.py ${TOPIC} && python3 funnel/term_gate.py ${TOPIC}
Верни кратко: сколько находок закрыл, какие не смог и почему.`;

  const fixReport = await agent(fixPrompt, {
    label: `fix:r${round}`,
    phase: "Fix",
    model: "opus",
  });
  log(`Раунд ${round} правки: ${String(fixReport).slice(0, 200)}`);

  // Сходимость — ТОЛЬКО по блокерам. Предупреждения (самодостаточность глав,
  // абстракции) совещательные: чинятся в проходе, но петлю НЕ держат — иначе
  // self_contained плодит их почти без конца и петля не сходится.
  if (blockers.length === 0) {
    log(
      `Раунд ${round}: блокеров нет — сходимся (предупреждений ${findings.length} отдано правщику в этом проходе).`,
    );
    break;
  }
}

const lastBlockers = lastFindings.filter((f) => f.severity === "block").length;
return {
  topic: TOPIC,
  rounds: round,
  converged: lastBlockers === 0,
  remaining_blockers: lastBlockers,
  remaining: lastFindings,
  history,
};

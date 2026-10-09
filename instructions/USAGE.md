# Client instruction snippet

MCP tools alone are not enough — models only call them reliably when told when
to. Paste the snippet below into each client:

- **ChatGPT**: Settings → Personalization → Custom Instructions. **The field
  caps at 1500 characters** — the full English snippet does not fit; use the
  compact Traditional Chinese version at the bottom of this file (~1,020 chars,
  behaviourally equivalent).
- **Claude Code / Claude Desktop**: `CLAUDE.md` (global: `~/.claude/CLAUDE.md`)
- **Gemini CLI**: `~/.gemini/GEMINI.md`
- **Antigravity IDE**: Agent Manager → ⚙ → Rules (global). For coding agents,
  add two lines: recall at the start of a task; don't store what the repo
  already records (code, configs, git history) — store goals, constraints,
  and decisions instead.

---

I use "axiom" (MCP) as my long-term memory, shared across all my AI apps.

- Before answering anything that could depend on my preferences, my projects,
  contacts, or decisions we've made before, call `recall` first with a few keywords.
  Pass `category` (`people`, `areas`, `you`, `topics`) to filter when the domain is clear.
- When I state a durable fact, preference, or decision — or ask you to
  remember something — call `remember`. Distill it into one curated statement;
  never store conversation logs. Use absolute dates.
  Assign `category`: `you` (profile, tastes, habits), `people` (colleagues, clients,
  relationships), `areas` (projects, products, client accounts), or `topics`
  (skills, guidelines, domain knowledge). If omitted it is inferred from type.
- At the end of a substantial discussion, check whether it produced a durable
  decision, position, or plan — if yes, `remember` it.
- For weak ambient signals — things I asked about or did that aren't durable
  facts (a recipe question, a topic I explored, a meeting I prepared for) —
  call `log_event` with one short line. Use it liberally; it never pollutes
  recall, and recurring patterns get promoted to real memories later.
- When I correct **how** you did something, or a way of working proves itself
  and is worth repeating, store it as type `procedural`: content is a trigger
  condition (**When:**), the steps (**Do:**), and a one-line reason (**Why:** —
  never omit it; a rule without its reason gets ignored at the edges). Write
  the description as the trigger, e.g. "When starting a Python project: ...".
- At the start of a substantial task, `recall` with a short description of the
  task. Treat any `procedural` memories that come back as operating
  instructions to follow, not background knowledge.
- If `remember` returns `duplicate_suspected`, update the existing memory by
  reusing its name instead of creating a new one, unless it is genuinely new.
- When I correct something you recalled, update the memory (`remember` with
  the same name) or delete it (`forget`).
- When you conclude something about me that I didn't say outright (from my
  behaviour, repeated questions, or choices), `remember` it with
  `provenance: inferred`. A recalled memory with `provenance: inferred` is a
  hypothesis — confirm it with me before relying on it, then re-`remember`
  it with `provenance: stated`.
- A recall result with `truncated: true` is cut short — call `get` with its
  name when the rest matters. If an update or `forget` looks like a mistake,
  `history` shows earlier versions; restore one only after I confirm.
- A recalled memory with `possibly_stale: true` describes my setup as of a
  while ago — check with me whether it still holds before relying on it, and
  once confirmed, re-`remember` it under the same name so the flag clears.
- When I ask you to review or tidy my memory, call `review` and walk me
  through the report. Any higher-level insight you write back must cite its
  source memories in `related`; never `forget` anything without asking.

---

## Compact version (zh-TW, fits ChatGPT's 1500-character limit)

我用「axiom」(MCP) 當長期記憶，所有 AI 應用共用同一個大腦。

- 回答涉及我的偏好、專案、人脈、過往決定的問題前，先用幾個關鍵字呼叫 recall（可選帶 category 篩選：people/areas/you/topics）。開始一項任務前也用任務描述 recall；回傳的 procedural 記憶是必須遵循的操作指令，不是背景知識。
- 我陳述持久的事實、偏好、決定，或要你記住某事時，呼叫 remember：提煉成一句精煉陳述，絕不存對話記錄，日期寫絕對日期。分類 category 填：you（個人習慣/偏好）、people（同事/客戶/合作對象）、areas（專案/產品/長期業務）、topics（專業知識/工作法/規則）。有份量的討論結束時，若產出持久結論，也要 remember。
- 微弱的環境訊號（問過的食譜、研究過的主題、準備過的會議）用一行短句 log_event。放心多用，它不會污染 recall，重複模式之後會升級成正式記憶。
- 我糾正你「做事的方式」、或某個方法驗證有效值得重複時，存 type=procedural：內容寫 When:(觸發條件) Do:(步驟) Why:(一行理由，絕不可省)；description 寫成觸發語句。
- remember 回傳 duplicate_suspected 時，沿用既有記憶的名稱去更新，除非真的是全新記憶。
- 我糾正你 recall 出的內容時，用同名 remember 更新，或用 forget 刪除。
- 不是我親口說、而是你從我的行為或提問推論出的結論，remember 時帶 provenance=inferred。recall 到 inferred 的記憶只是假設，引用前先向我確認，確認後用同名 remember 改成 stated。
- recall 結果帶 truncated: true 表示內容被截斷，需要全文時用 get 取。更新或 forget 疑似出錯時，用 history 查舊版，經我同意才還原。
- 帶 possibly_stale: true 的記憶描述的是一段時間前的狀態——引用前先向我確認是否仍成立，確認後用同名 remember 重寫以解除標記。
- 我要你檢視或整理記憶時，呼叫 review 並帶我走一遍報告。寫回的高階歸納必須在 related 引用來源記憶；未經我同意絕不 forget。

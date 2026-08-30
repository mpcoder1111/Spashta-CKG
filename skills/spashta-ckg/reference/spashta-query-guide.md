# Spashta CKG — Full Utilization & Query Guide

How to get the most out of the Spashta Code Knowledge Graph, including every capability contributed back to the tool. Read this when a task involves **impact prediction**, **coupling questions**, or **dead-code cleanup**.

> **Stack applicability.** The core graph (Python `calls`/`imports`/`defines`, JS calls/events, CSS `defines`) works on any project. The **full-stack + CSS coupling** below (routes, templates, HTMX, `uses_style`) is **Django + HTMX + CSS**-specific and each rule is **config-gated** — an empty config leaves the graph byte-identical, so a non-Django project simply doesn't emit those edges.

---

## The Mental Model

- **Nodes** = code entities: `Function`, `Class`, `Model`, `Route`, `Template`, `StyleClass`, `StyleID`, `Event`, `Keyframes`, `Constant`, `Field`.
- **Edges** = typed relationships between them (`calls`, `imports`, `renders_template`, `uses_style`, `resolves_to`, `dispatches_event`/`listens_to`, `includes_urlconf`, `queries_dom`, `oob_swaps`).
- **Placeholders join by name.** Several emitters (Python, HTML, JS, CSS) each create a node for the same logical thing (a route, an event, a CSS class) and Spashta **joins them by name** — it does not merge them into one node. `impact`/`dependencies` **union same-name siblings** for `Route` / `Event` / `StyleID`, so one CLI query resolves cross-emitter coupling.
- **Deterministic-when-literal.** A rule fires only when the value is a literal (`hx-get="{% url 'app:x' %}"`, `render(…, "t.html")`, `class="a b"`). A computed/templated value (`{% url v %}`, `_field_form_{type}.html`) is recorded as an **ambiguity**, never guessed.

---

## Key Query Commands

```bash
spashta_ckg impact "Name" --depth 2
spashta_ckg dependencies "Name"
spashta_ckg routes
spashta_ckg dead-code css
spashta_ckg class-usage "btn-primary"
spashta_ckg dup-styles
```

- `spashta_ckg impact "X"` → **what is affected if I change X** (inbound: callers, renderers, references).
- `spashta_ckg dependencies "X"` → **what X depends on** (outbound).
- **Rule:** for a model/service change, run `impact` on the **model class**, not just the service — field changes cascade from `Field` nodes and a service-only query misses upstream consumers.
- **Accepted keys:** a bare name; a **Route** as `"app:url_name"`; an **Event** or **StyleID** by bare name (siblings unioned). A **Template** resolves by its logical name or full path.

---

## Edge Catalog — "Which Question → Which Edge/Command"

### 1. Python Structure (Core, Always On)
| Question | Edge / Command |
|---|---|
| Who calls this function? | `calls` (`spashta_ckg impact <fn>`) |
| What does this module import? | `imports` (`spashta_ckg dependencies <mod>`) |
| Class members / definitions | `contains_member` / `defines` |

### 2. Frontend → Django Routes
| Question | How |
|---|---|
| What breaks if I rename URL `app:x`? | `spashta_ckg impact "app:x"` — unions the `Route('app:x')` siblings |
| Which templates call this URL? | `hx-get`/`href="{% url 'app:x' %}"` → resolved to Route (`resolves_to`) |
| Which view serves this URL? | `spashta_ckg dependencies "app:x"` → the view via `resolves_to` (`path(…, view, name='x')`) |
| Which views redirect here? | `reverse()`/`redirect()`/`reverse_lazy('app:x')` → `calls_api` to the Route |

### 3. View ↔ Template
| Question | Edge |
|---|---|
| Which view renders this template? | `render(request, "t.html", …)` → `renders_template` |
| If I change this base/partial, which templates break? | `{% extends %}` → `extends_template`; `{% include %}` → `includes_template` |
| URLconf include tree | `include('app.urls')` → `includes_urlconf` (File→File) |

### 4. HTMX Behavior Coupling
| Question | Edge |
|---|---|
| This event is dispatched here — who listens? | JS `dispatches_event` / `HX-Trigger` header ↔ `hx-trigger="evt from:…"` `listens_to`, joined by name on one `Event` node |
| Inline `HX-Trigger` (no helper) | `response['HX-Trigger'] = 'ev'` → `dispatches_event` |
| Which fragments OOB-refresh `#thing`? | `hx-swap-oob` on `id=X` → `oob_swaps` Template→StyleID |

### 5. CSS Coverage
| Question | Command / Edge |
|---|---|
| Who uses `.btn-primary`? | `spashta_ckg class-usage "btn-primary"` — `uses_style` (markup) + `queries_dom` (JS `classList`/`querySelector`) |
| Is `.btn-primary` dead? | `spashta_ckg dead-code css` (dynamic usage safe) |
| Duplicate style / animation blocks | `spashta_ckg dup-styles` — normalized hash over rules + `@keyframes` |
| Animation reuse | `@keyframes` → `Keyframes` node + `uses_animation` |

### 6. JS Internals
| Question | Edge |
|---|---|
| Who calls this JS function? | `calls` |
| Callback passed by reference (`addEventListener('evt', fn)`) | resolved via `calls` (same registry+ambiguity as a direct call) |
| Which DOM class/id does this function touch? | `queries_dom` → `StyleClass` / `StyleID` (joined to CSS by name) |

### 7. Django Forms / Signals
| Question | Edge |
|---|---|
| Which model does this ModelForm use? | `ModelForm` + `Meta.model` → `uses_model` |
| What does `@receiver(SIG)` listen to? | `@receiver(SIG)` → `listens_to` |

---

## Dead-Code Cleanup — Safe SOP

`spashta_ckg dead-code css` reports **CANDIDATES**, not proof. A class built entirely in host code (string-concatenated, injected by a framework) cannot be seen. **Never bulk-delete off the raw list.** The four-fold accuracy check:

1. **Literals interleaved with dynamic syntax** are real uses — the tokenizer strips `{% %}`/`{{ }}` and keeps a literal class between tags (`class="a {% if x %}b{% endif %}"` → both `a` and `b`).
2. **A naming ambiguity is soft evidence of use** — a class named in a `dynamic_class_unresolved` ambiguity is dynamically referenced, not dead.
3. **Framework-injected symbols** (`htmx-*`) are allowlisted, not dead.
4. **A variable-filled BEM modifier** (`x--{{ status }}`) means `x--active` etc. are dynamically referenced via their base.

# Klucz OpenAI przekazuje repozytorium wywołujące

`fix-failures.yml` deklaruje wymagany secret `OPENAI_API_KEY` w `on.workflow_call.secrets`, a repozytorium wywołujące mapuje na niego własny secret w bloku `secrets:` joba, który wywołuje workflow. Klucz trafia do `env` tylko w kroku agenta; kroki zbierania go nie widzą. SDK `@openai/agents` czyta `OPENAI_API_KEY` ze środowiska.

Reużywalny workflow działa w kontekście repozytorium wywołującego i widzi wyłącznie secrety przekazane przez nie. Secretów repozytorium `gha-ai-shared-workflows` nie da się użyć, nawet gdy wszystkie repozytoria mają tego samego właściciela. Osobny klucz na projekt jest przy tym pożądany: koszty i limity są rozdzielone.

Rozważone i odrzucone na teraz:

- Secret organizacji z `secrets: inherit`: działa tylko w obrębie jednej organizacji lub enterprise, nie na koncie prywatnym.
- Klucz w zewnętrznym magazynie sekretów wydawany przez OIDC na podstawie `job_workflow_ref`: jedno miejsce przechowywania, ale wymaga `id-token: write` i osobnej infrastruktury.
- Agent uruchamiany w tym repozytorium, pobierający logi innych repozytoriów przez PAT lub GitHub App: `workflow_run` nie działa między repozytoriami, a `repository_dispatch` wymaga tokenu u wywołującego, więc zostaje tylko odpytywanie z opóźnieniem.

Konsekwencje:

- `required: true` sprawdza tylko, czy secret jest przekazany, nie czy ma wartość.
- PR z forków nie dostają secretów, więc triage się tam nie powiedzie.
- Proces agenta ma klucz i czyta niezaufane logi, dlatego agent zostaje read-only, bez narzędzi sieciowych i shella w swoim procesie. Code interpreter po stronie OpenAI opisuje [ADR 0003](0003-log-analyst-code-interpreter.md).

Zastępuje decyzję ze specyfikacji `.scratch/fix-failures/spec.md`, że etap diagnostyczny nie dostaje secretów i że triage LLM jest poza zakresem. Nadal obowiązuje: brak uprawnień zapisu (`actions: read`, `contents: read`) i brak checkoutu niezaufanego kodu.

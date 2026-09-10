# Kontekst failure dla agentów

`fix-failures.yml` przed uruchomieniem agentów zbiera deterministycznie dane o nieudanym runie repozytorium wywołującego. Każdy rodzaj danych trafia do osobnego pliku JSON w `$RUNNER_TEMP`, a krok agenta dostaje ścieżkę do każdego pliku w osobnej zmiennej środowiskowej. Uzasadnienie: [ADR 0001](adr/0001-failure-context-as-files.md).

## Pliki i zmienne

| Zmienna | Plik | Krok | Obecność |
|---|---|---|---|
| `RUN_CONTEXT_PATH` | `run-context.json` | `Describe the caller run` | zawsze; błąd kroku przerywa job |
| `FAILED_JOBS_PATH` | `failed-jobs.json` | `Fetch failed jobs from the caller attempt` | zawsze; `[]`, gdy nic nie padło |
| `ERROR_EXCERPTS_PATH` | `error-excerpts.json` | `Extract error excerpts from the failed job logs` | zawsze; `[]`, gdy nic nie padło |
| `CHANGES_SINCE_LAST_SUCCESS_PATH` | `changes-since-last-success.json` | `Find changes since the last successful run` | może nie istnieć (`continue-on-error`) |
| `RECENT_RUNS_PATH` | `recent-runs.json` | `Fetch recent runs of the caller workflow` | może nie istnieć (`continue-on-error`) |

Agent musi obsłużyć brak dwóch ostatnich plików oraz ich wersje zdegradowane opisane niżej. Summary z logami renderuje się przed nowymi krokami, więc ich błąd go nie ukrywa.

## `run-context.json`

Metadane runu z `GET actions/runs/{run_id}` i domyślna gałąź repozytorium.

```json
{
  "repository": "owner/repo",
  "default_branch": "main",
  "workflow": "Fixture failing pipeline",
  "workflow_path": ".github/workflows/fixture-failing-pipeline.yml",
  "run_id": 34532923793,
  "attempt": 1,
  "url": "https://github.com/owner/repo/actions/runs/34532923793",
  "event": "workflow_dispatch",
  "branch": "main",
  "sha": "7fd8421dec797525afa1a468ca60bd2e5c101f1c",
  "title": "Fixture failing pipeline",
  "created_at": "2026-09-10T21:34:25Z",
  "pull_requests": [{ "number": 7, "head_branch": "feature/x", "base_branch": "main", "base_sha": "…" }]
}
```

- `attempt` pochodzi z wejścia `source_run_attempt`, czyli z próby, która padła.
- `branch` może być `null`, gdy run nie ma gałęzi.
- `pull_requests` jest puste dla `push`, `workflow_dispatch` i PR z forków (API ich nie zwraca).

## `failed-jobs.json`

Nieudane joby z bieżącej próby.

```json
[{ "id": 103057723145, "name": "fail", "conclusion": "failure",
   "failed_steps": ["Run intentionally failing fixture"],
   "log_path": "/home/runner/work/_temp/failed-job-103057723145.log" }]
```

`log_path` wskazuje pełny, surowy log joba, z kodami kolorów ANSI.

## `error-excerpts.json`

Fragmenty logów wokół błędów, oczyszczone z ANSI, ze znacznikami czasu.

```json
[{ "job_id": 103057723145, "job_name": "fail", "excerpt": "…\n2026-09-10T21:34:31.5061721Z ##[error]Process completed with exit code 1.\n" }]
```

- Runner pisze `##[error]`, gdy krok pada. Dla każdego znacznika zostaje do 80 wcześniejszych linii (`EXCERPT_CONTEXT_LINES`) i sam znacznik.
- Nakładające się okna są łączone; przerwę między oknami oznacza linia `...`.
- Bez żadnego `##[error]` fragment to ostatnie 80 linii logu.

## `changes-since-last-success.json`

Zmiany między bazą a commitem, który padł, z `GET compare/{base}...{sha}`. Porównanie trzykropkowe liczy zmiany od merge base, więc działa też po force-pushu, dopóki commit bazowy istnieje.

Wybór bazy (`base_kind`), pierwszy pasujący:

1. `last_successful_run`: najnowszy udany run tego samego workflowu na tej samej gałęzi, utworzony przed runem, który padł (spośród 20 ostatnich udanych). Diff zawiera tylko to, co mogło zepsuć pipeline. Wynik `status: "identical"` bez plików oznacza, że ten sam commit już przechodził, czyli prawdopodobnie flaky test.
2. `base_branch`: gdy gałąź różni się od gałęzi bazowej PR (bez PR: od gałęzi domyślnej). Diff to zmiany gałęzi.
3. `parent_commit`: commit nadrzędny. Tak wygląda baza dla fixture'a, który nigdy nie przechodzi.

```json
{
  "base_kind": "parent_commit",
  "base_ref": "8853bef1553cc9d520333324deb39b8c2382d648",
  "base_run": null,
  "status": "ahead", "ahead_by": 1, "behind_by": 0, "total_commits": 1,
  "merge_base_sha": "8853bef1553cc9d520333324deb39b8c2382d648",
  "commits": [{ "sha": "7fd8421…", "author": "…", "message": "pierwsza linia wiadomości" }],
  "files_truncated": false,
  "files": [{ "filename": "src/a.ts", "previous_filename": null, "status": "modified", "additions": 30, "deletions": 2 }]
}
```

- `base_run` ma postać `{id, sha, created_at, url}` tylko dla `last_successful_run`, w pozostałych przypadkach `null`.
- Brak bazy: `{"base_kind": "none", "reason": "…"}`.
- Nieudane porównanie (np. commit bazowy już nie istnieje): `{"base_kind": "…", "base_ref": "…", "reason": "…"}`, bez listy zmian.

## `recent-runs.json`

Historia pozwala odróżnić regresję od flaky testu albo czerwonej gałęzi domyślnej.

```json
{
  "branch": { "name": "feature/x", "runs": [{ "id": 1, "attempt": 1, "sha": "…", "event": "push", "conclusion": "failure", "created_at": "…", "url": "…" }] },
  "default_branch": { "name": "main", "runs": [] },
  "previous_attempts": [{ "attempt": 1, "conclusion": "success", "url": "…" }]
}
```

- `runs` to do 10 ostatnich zakończonych runów tego workflowu (`RECENT_RUN_COUNT`), bez runu, który jest analizowany.
- `default_branch.runs` jest `null`, gdy run jest na gałęzi domyślnej; ta sama lista jest wtedy w `branch.runs`. To celowe.
- `branch.name` jest `""`, a `branch.runs` jest `null`, gdy run nie ma gałęzi.
- `previous_attempts` jest puste dla pierwszej próby.

## Ograniczenia

- Compare API zwraca najwyżej 250 commitów i 300 plików (`files_truncated`). Patchy nie zapisujemy.
- `recent-runs.json` może zawierać runy utworzone po runie, który padł. Przy triage zaraz po błędzie to bez znaczenia, przy ponownym triage starego runu może mylić.
- Historia jest na poziomie wyniku całego runu, nie pojedynczego joba.
- Nie zbieramy adnotacji (wymagają `checks: read`) ani opisu PR dla runów z `push` (`pull-requests: read`); oba wymagałyby nowych uprawnień u wywołującego.
- Usuwanie ANSI używa `\x1b` w `sed`, co działa w GNU sed na runnerze, ale nie w BSD sed na macOS.

## Uwagi o środowisku agentów

- Agenci są w tym repozytorium, więc workflow robi checkout `job.workflow_repository` na `job.workflow_sha`, a nie repozytorium wywołującego. actionlint 1.7.12 nie zna tych pól, stąd wąski wyjątek w `.github/actionlint.yaml` do czasu naprawy [rhysd/actionlint#705](https://github.com/rhysd/actionlint/issues/705).
- Node 24 uruchamia pliki `.ts` bez kompilacji (usuwanie typów). `tsconfig.json` ma `erasableSyntaxOnly` i `allowImportingTsExtensions`, żeby `tsc` odrzucał kod, którego Node nie uruchomi (`enum`, `namespace`, importy bez `.ts`).
- Lint i formatowanie robi Biome, a nie ESLint, bo `typescript-eslint` obsługuje tylko TypeScript poniżej 6.1, a projekt używa TypeScript 7.

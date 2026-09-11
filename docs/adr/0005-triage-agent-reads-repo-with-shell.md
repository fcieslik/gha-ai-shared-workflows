# Triage Agent czyta repozytorium wywołującego przez shell

Triage Agent zgłaszał w `missing_context` braki, których nie dało się uzupełnić z logów: kodu pliku z błędu, informacji, czy workflow ma celowo padać, oraz historii i diffu. Historię i zmiany workflow już zbierał, więc czyta je nowy analityk historii, uruchamiany równolegle z analitykiem logów. Kodu nie było, więc:

- `fix-failures.yml` robi checkout repozytorium wywołującego na `inputs.source_sha` do `source/` (`fetch-depth: 1`, `persist-credentials: false`, `continue-on-error`). Z tego checkoutu nic nie jest instalowane ani uruchamiane.
- Lider dostaje `shellTool({ shell, needsApproval: false })` z lokalną implementacją `Shell` w `agents/source-shell.ts` i działa z `maxTurns: 20`. `toolChoice: "required"` wymusza co najmniej jeden odczyt, bo z samym promptem lider nie uruchamiał shella. Po limicie kod wymusza werdykt z wyłączonymi narzędziami, jak u analityka logów.
- Każde polecenie działa przez `bash -c` w `SOURCE_CHECKOUT_PATH`, ze środowiskiem ograniczonym do `PATH`, `HOME` i `LANG`, z timeoutem do 30 s i outputem obciętym do 20 000 znaków na strumień. Brak checkoutu zwraca komunikat w `stderr`, a nie błąd, więc triage trwa dalej.
- Prompt pozwala tylko na polecenia do odczytu (`ls`, `find`, `cat`, `sed -n`, `grep -rn`). To prośba do modelu, a nie blokada.

Zmienia decyzje:

- [ADR 0001](0001-failure-context-as-files.md): proces agenta nadal nie dostaje tokenu GitHub, ale nie czyta już tylko przygotowanych plików.
- [ADR 0002](0002-openai-key-from-the-caller.md): „bez shella w swoim procesie” i „brak checkoutu niezaufanego kodu”.
- [ADR 0004](0004-triage-lead-summarizes-code-loops.md): lider nie jest już bez narzędzi i nie działa w jednej turze. O kolejnych rundach nadal decyduje kod.

Ryzyko zaakceptowane świadomie:

- Shell działa w procesie, który ma `OPENAI_API_KEY`, a model czyta niezaufane logi, wiadomości commitów i kod. Czyste środowisko dziecka nie chroni klucza: polecenie działa jako ten sam użytkownik, więc może odczytać `/proc/<pid rodzica>/environ`, a runner ma dostęp do sieci. Prompt injection może więc wyprowadzić klucz OpenAI.
- `persist-credentials: false` jest konieczne, a nie tylko porządkowe: bez niego shell odczytałby token GitHub z `.git/config`.
- Polecenia mogą zmieniać pliki w `source/` i `$RUNNER_TEMP`; job jest efemeryczny i nie ma uprawnień zapisu (`actions: read`, `contents: read`).

Rozważone i odłożone:

- Uruchamianie poleceń jako inny użytkownik (`sudo -u nobody`) albo bez sieci: zamyka odczyt `/proc` i wyprowadzenie klucza, kolejny krok.
- `SandboxAgent` z `@openai/agents`: izolacja poza procesem, ale więcej konfiguracji niż potrzeba do czytania plików.
- Osobny analityk zmian z patchami z compare API: lider czyta kod sam, a lista zmienionych plików od analityka historii wystarcza do reguły „plik z błędu jest na liście zmian”.

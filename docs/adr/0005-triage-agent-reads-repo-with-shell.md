# Triage Agent czyta repozytorium wywołującego przez shell

Triage Agent zgłaszał w `missing_context` braki, których nie dało się uzupełnić z logów: kodu pliku z błędu, informacji, czy workflow ma celowo padać, oraz historii i diffu. Historię i zmiany workflow już zbierał, więc czyta je nowy analityk historii, uruchamiany równolegle z analitykiem logów. Kodu nie było, więc:

- `fix-failures.yml` robi checkout repozytorium wywołującego na `inputs.source_sha` do `source/` (`fetch-depth: 1`, `persist-credentials: false`, `continue-on-error`). Z tego checkoutu nic nie jest instalowane ani uruchamiane.
- Lider dostaje `shellTool({ shell, needsApproval: false })` z lokalną implementacją `Shell` w `agents/source-shell.ts` i działa z `maxTurns: 20`. `toolChoice: "required"` wymusza co najmniej jeden odczyt, bo z samym promptem lider nie uruchamiał shella. Po limicie kod wymusza werdykt z wyłączonymi narzędziami, jak u analityka logów.
- Każde polecenie działa jako użytkownik `nobody` przez `sudo -n -u nobody -- env -i … bash -c` w `SOURCE_CHECKOUT_PATH`, z timeoutem do 30 s i outputem obciętym do 20 000 znaków na strumień. `env -i` ustawia tylko `PATH`, `HOME=/tmp`, `LANG` i `safe.directory` dla gita, który inaczej odmawia pracy w repozytorium innego właściciela. `nobody` nie wejdzie do `/home/runner` (na Ubuntu prawa `0750`), więc workflow kopiuje checkout do `/tmp/fix-failures-source` z prawami do odczytu dla wszystkich.
- Przed pierwszym poleceniem shell raz sprawdza izolację (`sudo -n -u nobody -- test -r .`). Gdy się nie uda (brak `sudo` bez hasła, brak użytkownika, katalog nieczytelny), żadne polecenie nie jest uruchamiane, a model dostaje powód w `stderr`; shell nigdy nie wraca do uruchamiania jako `runner`. Brak checkoutu też zwraca komunikat w `stderr`, a nie błąd, więc triage trwa dalej.
- Prompt pozwala tylko na polecenia do odczytu (`ls`, `find`, `cat`, `sed -n`, `grep -rn`). To prośba do modelu, a nie blokada.

Zmienia decyzje:

- [ADR 0001](0001-failure-context-as-files.md): proces agenta nadal nie dostaje tokenu GitHub, ale nie czyta już tylko przygotowanych plików.
- [ADR 0002](0002-openai-key-from-the-caller.md): „bez shella w swoim procesie” i „brak checkoutu niezaufanego kodu”.
- [ADR 0004](0004-triage-lead-summarizes-code-loops.md): lider nie jest już bez narzędzi i nie działa w jednej turze. O kolejnych rundach nadal decyduje kod.

Ryzyko zaakceptowane świadomie:

- Model czyta niezaufane logi, wiadomości commitów i kod, a proces Node ma `OPENAI_API_KEY`. Samo czyste środowisko dziecka nie chroniłoby klucza, bo polecenie jako ten sam użytkownik mogłoby odczytać `/proc/<pid rodzica>/environ`. Jako `nobody` nie może: `environ` ma prawa `0400`, a `ptrace` procesu innego użytkownika wymaga roota. Wyciek klucza przez prompt injection jest więc zamknięty.
- Sieć zostaje otwarta. Polecenie może wysłać tylko to, co `nobody` może przeczytać: kod repozytorium i pliki czytelne dla wszystkich. Na runnerze nie sprawdzono praw `/home/runner`, od których zależy, czy `nobody` widzi `$RUNNER_TEMP`.
- `persist-credentials: false` jest konieczne, a nie tylko porządkowe: bez niego shell odczytałby token GitHub z `.git/config`.
- Zapis w kopii repozytorium blokuje system, bo jej właścicielem jest `runner`. `nobody` może pisać tylko w katalogach otwartych dla wszystkich, np. `/tmp`; job jest efemeryczny i nie ma uprawnień zapisu (`actions: read`, `contents: read`).

Rozważone i odłożone:

- Polecenia bez sieci (Docker z `networkMode`, `SandboxAgent`): zamknęłyby też wysyłanie kodu, ale wymagają przejścia lidera na `SandboxAgent` i kontenera w każdym runie.
- `UnixLocalSandboxClient`: nie izoluje poleceń. SDK pisze w `unixLocal.d.ts` „This does not confine shell commands”, a polecenia uruchamia jako ten sam użytkownik, więc klucz byłby tak samo dostępny jak bez sandboxa.
- `SandboxAgent` z `@openai/agents`: izolacja poza procesem, ale więcej konfiguracji niż potrzeba do czytania plików.
- Osobny analityk zmian z patchami z compare API: lider czyta kod sam, a lista zmienionych plików od analityka historii wystarcza do reguły „plik z błędu jest na liście zmian”.

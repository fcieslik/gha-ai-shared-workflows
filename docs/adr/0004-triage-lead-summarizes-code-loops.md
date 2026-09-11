# Triage Agent tylko podsumowuje, a o kolejnych rundach dochodzenia decyduje kod

Stan: częściowo zaimplementowane. Działają pola `next_action: investigate`, `follow_ups` i `missing_context` w `agents/schema.ts`. Pętli rund jeszcze nie ma, więc `follow_ups` trafiają tylko do raportu triage. Zmienione przez [ADR 0005](0005-triage-agent-reads-repo-with-shell.md): lider ma shell do czytania repozytorium i działa z `maxTurns: 20`, a zamiast osobnego analityka zmian zmiany czyta analityk historii.

Kolejnością agentów steruje `triage.ts`. Specjaliści (analityk logów i analityk historii) prowadzą dochodzenie. Triage Agent (lider) nie ma handoffów ani specjalistów jako narzędzi: czyta wyniki specjalistów, w razie potrzeby kod repozytorium, i zwraca werdykt.

Oprócz werdyktu lider zwraca:

- `follow_ups: [{ agent: "logs", request }]`: braki, które specjalista może jeszcze sprawdzić w zebranym kontekście, np. „znajdź w logu pierwszy błąd przed linią 412”. Analityk historii odpowiada w jednej turze z zebranych plików, więc nie przyjmuje próśb; `"history"` dojdzie, gdy to się zmieni.
- `next_action: investigate`: gdy `follow_ups` mogą zmienić werdykt.
- `missing_context: string[]`: danych nie ma w zebranych plikach (patche, adnotacje, raport JUnit). Nie uruchamiają kolejnej rundy, tylko trafiają do podsumowania.

Pętla w kodzie:

1. Runda 1: specjaliści, potem lider.
2. Gdy `follow_ups` nie jest puste, kod uruchamia ponownie tylko wskazanych specjalistów. Każdy dostaje swoje poprzednie wyniki i prośbę lidera, więc rozszerza wynik zamiast zaczynać od zera. Potem znowu lider.
3. Pętla kończy się po 3 rundach, przy pustym `follow_ups`, przy prośbie identycznej jak w poprzedniej rundzie albo gdy wynik specjalisty się nie zmienił. W ostatniej rundzie lider wie, że jest ostatnia, i musi wydać werdykt, w razie potrzeby `uncertain` z `human`.
4. Pętla działa wewnątrz `withUploadedJobLogs` ([ADR 0003](0003-log-analyst-code-interpreter.md)), więc logi są wysyłane raz i usuwane po ostatniej rundzie.

Lider ma podsumować dochodzenie, a nie sam decydować, czego i ile razy szukać. Pętla w kodzie ma górną granicę kosztu i da się ją przetestować bez modelu, podstawiając wyniki agentów.

Rozważone i odrzucone:

- Specjaliści jako narzędzia lidera (`agent.asTool()`): lider sam decyduje, kogo, o co i ile razy pytać, czyli prowadzi dochodzenie, a koszt ogranicza tylko `maxTurns`.
- Handoffy: specjalista przejmuje run i lider nie wraca do podsumowania.
- LangGraph: triage działa w jednym efemerycznym jobie, więc trwałe checkpointy i przerwania w środku grafu nic nie dają. Tę samą decyzję podjęła wcześniejsza wersja w Pythonie.
- Powtarzanie całego przepływu: ci sami agenci na tych samych danych dają ten sam wynik, a każda runda kosztuje wszystkich agentów.

Konsekwencje:

- Lider sam sprawdzi tylko kod w repozytorium. Za logi i historię odpowiadają specjaliści, dlatego zwracają fakty z `job_id` i `log_line` oraz `gaps`.
- Kolejna runda pomaga tylko wtedy, gdy specjalista może zajrzeć tam, gdzie wcześniej nie patrzył, np. analityk w pełny log. Agenci nie mają tokenu GitHub ([ADR 0001](0001-failure-context-as-files.md)), więc nie dociągną nowych danych.
- O pętli decydują pola schematu (`follow_ups`, numer rundy), a nie `confidence` ani tekst odpowiedzi.
- Koszt rośnie z liczbą próśb, najwyżej do trzech rund.
- Nowy specjalista wymaga zmiany kodu i enuma `agent`.

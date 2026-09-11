# Triage Agent tylko podsumowuje, a o kolejnych rundach dochodzenia decyduje kod

Stan: częściowo zaimplementowane. Działa lider bez narzędzi z `maxTurns: 1` oraz pola `next_action: investigate`, `follow_ups` i `missing_context` w `agents/schema.ts`. Pętli rund jeszcze nie ma, więc `follow_ups` trafiają tylko do raportu triage.

Kolejnością agentów steruje `triage.ts`. Specjaliści (analityk logów, później analitycy historii i zmian) prowadzą dochodzenie własnymi narzędziami. Triage Agent (lider) nie ma narzędzi ani handoffów i działa w jednej turze (`maxTurns: 1`): czyta wyniki specjalistów i zwraca werdykt.

Oprócz werdyktu lider zwraca:

- `follow_ups: [{ agent: "logs" | "history" | "changes", request }]`: braki, które specjalista może jeszcze sprawdzić w zebranym kontekście, np. „znajdź w logu pierwszy błąd przed linią 412”. W kodzie `agent` ma na razie tylko `"logs"`; pozostałe wartości dojdą razem z analitykami.
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

- Lider niczego sam nie sprawdzi. Jakość werdyktu zależy od specjalistów, dlatego zwracają fakty z `job_id` i `log_line` oraz `gaps`.
- Kolejna runda pomaga tylko wtedy, gdy specjalista może zajrzeć tam, gdzie wcześniej nie patrzył, np. analityk w pełny log. Agenci nie mają tokenu GitHub ([ADR 0001](0001-failure-context-as-files.md)), więc nie dociągną nowych danych.
- O pętli decydują pola schematu (`follow_ups`, numer rundy), a nie `confidence` ani tekst odpowiedzi.
- Koszt rośnie z liczbą próśb, najwyżej do trzech rund.
- Nowy specjalista wymaga zmiany kodu i enuma `agent`.

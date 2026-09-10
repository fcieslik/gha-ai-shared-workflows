# Kontekst failure trafia do agentów jako pliki

Zbieranie danych o failure zostaje deterministyczne i dzieje się w bashu przed uruchomieniem agentów. Każdy rodzaj danych (kontekst runu, nieudane joby, fragmenty błędów, zmiany od ostatniego zielonego runu, historia runów) jest osobnym plikiem JSON w `$RUNNER_TEMP`, a krok agenta dostaje ścieżkę do każdego w osobnej zmiennej środowiskowej. Kontrakt opisuje [docs/failure-context.md](../failure-context.md).

Treści nie przekazujemy w zmiennych, argumentach ani outputach kroków: logi mają megabajty, a Linux ogranicza pojedynczy argument lub zmienną do ok. 128 KB, outputy kroków też mają limity. Kroki są w jednym jobie, więc dzielą dysk i plik jest najprostszym nośnikiem.

Wszystkie wywołania GitHub API są w krokach zbierania. Proces agenta nie dostaje tokenu GitHub i czyta tylko przygotowane pliki, więc instrukcje wstrzyknięte przez log albo opis zmiany nie mogą sięgnąć do repozytorium.

Kroki heurystyczne (zmiany, historia) mają `continue-on-error`: ich błąd oznacza mniej kontekstu, a nie brak triage. Brak bazy albo nieudane porównanie zapisuje plik z polem `reason`. Summary z logami renderuje się przed nowymi krokami.

Rozważone: skrypt TypeScript zamiast basha w YAML. Byłby testowalny przez `node --test`, ale na razie zostaje przy wzorcu istniejących kroków; logika zbierania rośnie, więc to kandydat do przeniesienia.

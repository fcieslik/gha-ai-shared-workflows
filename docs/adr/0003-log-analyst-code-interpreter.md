# Analityk logów pracuje na pełnych logach w code interpreterze OpenAI

Analityk logów ma hostowane narzędzie `codeInterpreterTool` z kontenerem `auto`. Kontener działa po stronie OpenAI i nie widzi plików runnera. Dlatego `withUploadedJobLogs` przed uruchomieniem agenta wysyła pełne logi nieudanych jobów, bez kodów ANSI, do OpenAI Files (`purpose: user_data`) jako `failed-job-<id>.log`, a po zakończeniu je usuwa. Kontener ma wyłączoną sieć.

Fragmenty z `error-excerpts.json` obejmują tylko linie przed `##[error]`, a czytanie pełnego logu zakresami przez `read_job_log` zużywa tury i kontekst. W kontenerze model przeszukuje, liczy i grupuje linie kodem, a do kontekstu trafia tylko wynik. Usunięcie ANSI nie zmienia liczby linii, więc numery w kontenerze, we fragmentach i w `read_job_log` są te same.

Rozważone i odrzucone:

- Samo `codeInterpreterTool()` bez plików: kontener jest pusty, model mógłby liczyć tylko na tym, co wcześniej przeczytał.
- Lokalne narzędzie `search_job_log(job_id, pattern)`: nic nie wysyła, ale daje tylko wyszukiwanie, bez obliczeń.

Konsekwencje:

- Pełne logi trafiają do OpenAI jako zapisane pliki, a nie tylko jako treść zapytania. GitHub maskuje w logach zarejestrowane secrety, ale nie wartości, których nie zna.
- Pliki są usuwane w `finally`. Gdy proces zostanie zabity, np. przy anulowaniu joba, zostają na koncie OpenAI repozytorium wywołującego.
- Sesje kontenera są płatne osobno, według stawek narzędzi wbudowanych.
- Kod pisze model czytający niezaufane logi. Wykonuje się w kontenerze OpenAI bez sieci i bez klucza, a nie w procesie agenta, więc ograniczenie z [ADR 0002](0002-openai-key-from-the-caller.md) nadal obowiązuje.
- `openai` jest bezpośrednią zależnością.
- Dokumentacja code interpretera nie podaje, jakiego `purpose` wymaga plik w kontenerze. `user_data` nie zostało sprawdzone na API; jeśli API je odrzuci, zapasową wartością jest `assistants`. Błąd wysyłki przerywa cały krok triage.

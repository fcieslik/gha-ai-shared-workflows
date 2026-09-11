# Propozycja naprawy trafia do PR jako komentarz GitHub App

Codex w jobie `fix` zmienia pliki tylko w checkoutcie joba. Propozycja trafia jako komentarz w PR, na którym padło CI. Komentarz zawiera podsumowanie i przyczynę z raportu triage, końcową wiadomość Codexa i `git diff`, a pisze go GitHub App, więc ma własną nazwę i awatar.

- Wywołujący przekazuje Client ID i klucz prywatny App jako opcjonalne sekrety `FIX_FAILURES_APP_CLIENT_ID` i `FIX_FAILURES_APP_PRIVATE_KEY`. Bez nich albo bez PR komentarza nie ma. PR nie ma, gdy `run_context.pull_requests` jest puste: `push`, `workflow_dispatch` i PR z forków.
- Token tworzy `actions/create-github-app-token@v3` z `permission-pull-requests: write`, dopiero po zakończeniu Codexa. Dostaje go tylko krok komentarza.
- Checkout jest na `run_context.sha`, czyli ostatnim commicie PR. Przy `pull_request` `github.sha` to commit testowy łączący PR z gałęzią bazową, więc diff nie pasowałby do gałęzi PR.

Rozważone i odrzucone:

- `GITHUB_TOKEN` z `pull-requests: write`: bez App, ale komentarz podpisuje `github-actions[bot]`, a wywołujący musi nadać uprawnienie zapisu w swoim jobie.
- PR z poprawką do gałęzi PR: wymaga `contents: write`, pushowania gałęzi i obsługi konfliktów. Poprawki w `.github/workflows/` wymagają dodatkowo uprawnienia `workflows`.
- Sugestie w review (`suggestion`): działają tylko dla linii, które są w diffie PR.

Konsekwencje:

- To pierwszy zapis do GitHuba i zmienia [ADR 0002](0002-openai-key-from-the-caller.md). `GITHUB_TOKEN` nadal ma tylko `actions: read` i `contents: read`; pisze wyłącznie token App, zawężony do PR.
- Klucz prywatny pozwala tworzyć tokeny do wszystkich repozytoriów, na których App jest zainstalowana. Dostają go tylko krok `Read the pull request from the triage report`, który sprawdza, czy sekret jest ustawiony, i krok tworzący token. Codex go nie widzi.
- Komentarz zawiera tekst i diff wygenerowane przez model, który czytał niezaufane logi. Wzmianki `@` w komentarzu powiadamiają ludzi. Nic nie jest stosowane automatycznie.
- Każdy run dodaje nowy komentarz; poprzedni nie jest edytowany.
- Wiadomość Codexa jest ucinana do 10 000 bajtów, a diff do 40 000, bo GitHub odrzuca komentarze powyżej 65 536 znaków.
- Nie sprawdzono, czy `gh pr comment` działa z tokenem App mającym tylko „Pull requests: write”. Jeśli nie, App potrzebuje też „Issues: write”.

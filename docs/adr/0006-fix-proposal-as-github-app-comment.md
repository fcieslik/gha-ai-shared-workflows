# Propozycja naprawy trafia do PR jako komentarz GitHub App

Codex w jobie `fix` niczego nie zmienia: skillem `diagnosing-bugs` potwierdza przyczynę w sandboxie tylko do odczytu i proponuje poprawkę. Diagnoza trafia jako komentarz w PR, na którym padło CI. Komentarz zawiera podsumowanie i przyczynę z raportu triage oraz końcową wiadomość Codexa z potwierdzeniem, przyczyną i proponowanym diffem, a pisze go GitHub App, więc ma własną nazwę i awatar.

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
- W PR jest jeden komentarz na workflow, edytowany przy każdym runie. Krok znajduje go po ukrytym znaczniku `<!-- fix-failures:<workflow_path> -->` i autorze `<app-slug>[bot]`, a gdy go nie ma, tworzy nowy. Odrzucone: kolejny komentarz przy każdym runie, bo zaśmieca PR, a stare diagnozy wyglądają na aktualne; usuwanie i dodawanie od nowa, bo gubi historię, choć wysyła powiadomienie.
- Edycja komentarza nie wysyła powiadomienia. Po zielonym runie komentarz zostaje z ostatnią diagnozą, bo job `fix` działa tylko przy błędzie; nagłówek podaje skrócony SHA commita, którego dotyczy.
- Wiadomość Codexa jest ucinana do 60 000 bajtów, bo GitHub odrzuca komentarze powyżej 65 536 znaków.
- Codex działa z `permission-profile: ":read-only"`, bo bez commita ani PR poprawka w checkoutcie by przepadła, a komentarz twierdził, że błąd jest naprawiony. Wcześniej, z domyślnym sandboxem `workspace-write`, Codex poprawiał plik i pisał w komentarzu, że naprawił błąd.
- Z tokenem App mającym tylko „Pull requests: write” `gh pr comment` dodał komentarz w runie fixture'a. Nie sprawdzono, czy to samo uprawnienie wystarcza do listowania i edycji komentarzy przez REST (`issues/{number}/comments`, `issues/comments/{id}`); jeśli nie, App potrzebuje też „Issues: write”.

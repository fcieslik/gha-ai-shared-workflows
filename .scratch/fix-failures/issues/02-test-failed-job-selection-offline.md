# 02: Testuj offline wybór nieudanych jobów

**What to build:** Test offline filtra `jq`, który z odpowiedzi Actions API wybiera nieudane joby i ich nieudane kroki. Dziś filtr jest wpisany w `fix-failures.yml` i da się go sprawdzić tylko prawdziwym runem na GitHubie.

**Blocked by:** None (can start immediately).

**Status:** deferred. Na razie nie jest konieczne; wróć do tego, gdy dojdzie etap agenta i dane trzeba będzie formatować dla niego.

- [ ] Prawdziwa odpowiedź `GET repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs` z runu `Fixture failing pipeline` jest zapisana jako fixture JSON. Zapis w kształcie z `gh api --paginate --slurp`, czyli tablica stron, bo tego oczekuje filtr.
- [ ] Filtr wybierający nieudane joby żyje w osobnym pliku (np. skrypt `jq`), a workflow i test używają tego samego pliku.
- [ ] Test uruchamiany lokalnie sprawdza, że dla fixture'a wybierany jest job `fail` z krokiem `Run intentionally failing fixture`, a joby zakończone sukcesem są pomijane.

## Notes

- W `workflow_call` krok `actions/checkout` pobiera repozytorium konsumenta, nie to repozytorium. Skrypt z filtrem nie będzie więc dostępny na runnerze sam z siebie. Opcje: checkout tego repozytorium w wersji wskazanej przez `job_workflow_sha` (to kod zaufany, więc nie łamie zakazu checkoutu niezaufanego kodu PR), albo zostawić filtr w YAML i w teście wyciągać go z pliku workflowu.
- Fixture z prawdziwej odpowiedzi API może zawierać nazwy i URL-e z repozytorium; przed zapisem sprawdź, czy nie ma w nim nic, czego nie chcesz commitować.

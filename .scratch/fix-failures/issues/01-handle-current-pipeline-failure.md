# 01: Obsłuż aktualne failure pipeline’u

**What to build:** Reużywalny workflow `Fix failures`, który repozytorium konsumenta wywołuje końcowym jobem po failure. Ma przyjąć metadane bieżącego runu, pobrać bezpośrednio z API metadane oraz logi wszystkich nieudanych jobów bieżącej próby i pozostać wyłącznie do odczytu.

**Blocked by:** None (can start immediately).

**Status:** complete

- [x] Workflow jest wywoływalny przez `workflow_call`; konsument przekazuje identyfikator runu, próbę, nazwę workflowu oraz ref lub revision fallback w końcowym jobie `if: failure()`.
- [x] Równoległe obsługiwanie ogranicza się do pojedynczego źródłowego workflow i refu, bez wzajemnego blokowania niezależnych workflowów albo refów.
- [x] Diagnostyka pobiera dane z wejść i GitHub API bez pośredniego joba przekazującego dane, obejmuje wszystkie failed joby właściwej próby i ich logi.
- [x] Uprawnienia są minimalne i tylko do odczytu; workflow nie checkoutuje niezaufanego kodu ani nie korzysta z sekretów lub operacji zapisu.
- [x] Ręcznie uruchamiana fixture pipeline wykonuje plik kończący się failure, wywołuje lokalnie shared workflow i oba pliki YAML przechodzą walidację składni.

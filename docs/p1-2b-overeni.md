# P1.2B — implementace a ověření

Autor 21. 10. 2026 výslovně schválil [B1–B7, kroky B.1–B.3 a T01–T14](p1-2b-navrh-transakce-kontextu.md)
slovy „ok, schvaluji“, včetně sloučení návrhového PR #34 (`cbf19b1`).
Implementace má vlastní větev `codex/p1-2b-feature-transactions` a samostatné PR.
**Sloučení implementace vyžaduje další souhlas autora.**

## Výchozí stav a vlastnictví

Výchozí commit je `cbf19b11a51955de7d409530dc59fea119e96897`.
Jeho produkční kód je shodný s `edf9b8e`, na kterém vznikl schválený návrh;
PR #34 měnilo pouze dokumentaci. Výchozí sada má 1 266 případů.

Audit podporovaných cest:

| Oblast | Čtení přijatých objektů / místo změny |
|---|---|
| Parametry | `num`, `positive` a selektory jen čtou vyčíslená čísla. Prvek nemá oprávnění přepsat parametry ani zadání JSON. |
| Skici | `build_sketch` sestaví místní výsledek a pak uloží vlastní záznam. Vysunutí, rotace a loft čtou dřívější dvojice `Plane/Sketch`. Projekce obnovuje pracovní popis reference. |
| Přidání/odebrání | `apply` vytváří kandidátní těleso; nevyměňuje geometrii uvnitř dříve přijatého objektu. |
| Pole | Lineární transformace používá `moved`, kruhová `rotate`; obě vracejí nový tvar. Pořadí podoperací určuje mapa `operations`. |
| Zrcadlení | `mirror` vrací nový transformovaný tvar; vybrané operace se přehrávají do kandidáta. |
| Úpravy hran a stěn | Zaoblení, sražení a offset vytvářejí místní výsledek před přijetím. Výběry hran/ploch se používají jen pro čtení. |
| Pomocné tvary | Díry, závity a normalizované díly vytvářejí nové nástroje. Roviny se posouvají přes `Plane.offset`, který vytváří novou rovinu. |

Lokální build123d 0.13.0 potvrzuje rozdíl `move/locate` (mění objekt) a
`moved/located/rotate/mirror` (výsledek na kopii). Cesty v `features.py`
nevolají `move/locate` na přijatých objektech. Změna na místě se smí provést jen
na předem vlastněné kopii; tato mez není paměťovou izolací libovolného cizího kódu.
Regrese doplní audit hodnotovým ověřením polohy, materiálu, skic a nástrojů.

## Postup a skutečné výsledky

| Krok | Stav |
|---|---|
| B.1 | Oddělení kontejnerů a neměnnosti vstupů; 13 cílených zkoušek / 0,08 s. Ruff OK, celý pytest **1 279 prošlo / 415,02 s**, bez přeskočení. Hranice `_run_feature` se v tomto kroku zatím nepřepojuje. |
| B.2 | Hranice `_run_feature` přijímá celý kandidát až po validaci. Cílených 79 zkoušek / 0,66 s; Ruff OK, celý pytest **1 300 prošlo / 414,59 s**, bez přeskočení. Pozdní chyby pole, zrcadlení i závitu zachovají kontext včetně starých aliasů. |
| B.3 | Čeká na dokončení B.2. |

Před změnou produkčního kódu vznikla nová baseline stávajícího měřiče P0
a pevné krátké/dlouhé historie podle návrhu. Časy nejsou testovací práh;
paměť je maximum celého procesu, nikoli přírůstek jedné transakce.
Podrobné porovnání bude doplněné po dokončení B.3.

## Zbývající přijetí

Konečná hlava implementačního PR musí mít Ruff a celý pytest, úplné Windows
i macOS workflow včetně self-testu staženého balíčku a protokol vedené ruční
zkoušky podle schváleného návrhu. Rozpracovaný krok ani starší zelené sestavení
se nepovažují za dokončené P1.2B.

Formát zůstává 22; protokol workeru a odborné NDT vymezení se nemění.
R01/export a NDT při chybě, R03/ukládání, R04/reference, R12/popisek formátu pro AI
a odborná NDT-17 zůstávají samostatné. R05 se neuzavírá před celým ověřením
popsané transakční smlouvy. P1.3/P1.4/P2 ani NDT-16 se neimplementují.

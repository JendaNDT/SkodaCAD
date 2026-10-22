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
Regrese doplňuje audit hodnotovým ověřením polohy, materiálu, skic a nástrojů.
Všech 26 ukázek navíc při každém prvku kontroluje původní tvary a roviny;
sada zahrnuje všech 12 registrovaných builderů.

## Postup a skutečné výsledky

| Krok | Stav |
|---|---|
| B.1 | Oddělení kontejnerů a neměnnosti vstupů; 13 cílených zkoušek / 0,08 s. Ruff OK, celý pytest **1 279 prošlo / 415,02 s**, bez přeskočení. Hranice `_run_feature` se v tomto kroku zatím nepřepojuje. |
| B.2 | Hranice `_run_feature` přijímá celý kandidát až po validaci. Cílených 79 zkoušek / 0,66 s; Ruff OK, celý pytest **1 300 prošlo / 414,59 s**, bez přeskočení. Pozdní chyby pole, zrcadlení i závitu zachovají kontext včetně starých aliasů. |
| B.3 | Přenos, skutečný worker, historie a kompatibilita: 59 cílených zkoušek / 8,13 s. Ruff OK, celý pytest **1 311 prošlo / 416,95 s**, bez přeskočení. Lokální měření a nativní self-test níže; konečné CI, vizuální kontrola a ruční přijetí jsou samostatné brány. |

Před změnou produkčního kódu vznikla nová baseline stávajícího měřiče P0
a pevné krátké/dlouhé historie podle návrhu. Časy nejsou testovací práh;
paměť je maximum celého procesu, nikoli přírůstek jedné transakce.
Referencí je čistý `cbf19b1` (produkční strom shodný s `edf9b8e`);
kandidát byl měřen po dokončení zdrojových změn B.2/B.3, před dokumentačním
commitem B.3. Produkční soubory se pak neměnily. Příloha předání obsahuje plné JSON,
jednotlivé vzorky, kontrolní součty vstupů, zdrojů a měřičů i informace prostředí.
Referenční dlouhá historie byla měřena také z archivovaného stromu `cbf19b1`
stejným finálním měřičem; pro srovnání se používá `history-before-final.json`.
Starší pracovní pokusy nejsou srovnávacím podkladem.

Místní prostředí: macOS arm64, Python 3.12.14, build123d 0.13.0, OCCT 8.0.1.1,
PySide6 6.11.2, slvs 3.2. Měření běžela samostatně po ukončení testů a nativních
kontrol, vždy jedno zahřátí a tři opakování. Tabulka uvádí mediány:

| Scénář | Před [ms] | Po [ms] | Rozdíl |
|---|---:|---:|---:|
| Příruba | 28,916 | 30,485 | +5,4 % |
| Krabička | 62,831 | 65,836 | +4,8 % |
| Rám | 141,771 | 148,181 | +4,5 % |
| Svar s NDT studiemi | 42,817 | 44,328 | +3,5 % |
| Přenos příruby | 0,896 | 0,950 | +5,9 % |
| 1 000 paprsků desky | 71,692 | 73,185 | +2,1 % |
| Historie 3 přídavků | 20,279 | 20,556 | +1,4 % |
| Historie 30 přídavků | 1 557,025 | 1 527,293 | −1,9 % |
| Historie 30 přídavků a pozdní odmítnutí | 1 637,696 | 1 597,389 | −2,5 % |

Deset opakovaných dlouhých chybných přepočtů včetně kontrol geometrie:
16,607 → 16,201 s. Maximum paměti celého procesu P0: 412,719 → 412,953 MiB;
u historie 399,969 → 398,828 MiB. To není důkaz absence úniku ani náklad jedné
transakce. Vstupní SHA, geometrické/NDT podpisy, stavy a nezměněné dokumenty
se shodují; nástroje před/po jsou totožné. Příruba má po přenosu stále 57 204 B.

Tři opakování nejsou statistický důkaz zrychlení ani přesná izolace ceny transakce.
Kolísají i neměněné části (přenos/NDT); změnu času nelze celou připsat kopírování.
Rostoucí mapy a seznamy se přesto kopírují pro každý prvek, tedy zůstává riziko
režie velmi dlouhých historií. Nezavádí se časový práh, změna tolerancí ani
vynechání izolace. Měřič historie lze zopakovat z kořene repa:
`python tests/benchmark_p12b.py --output out/p12b-history.json`
(rodičovská složka musí existovat, výstup musí být nový soubor).

## Dohledatelnost T01–T14

| Smlouva | Důkaz v testech |
|---|---|
| T01, T02 | `test_feature_transactions.py`: pět druhů pozdní výjimky, všech pět polí, pořadí i staré aliasy seznamů. |
| T03 | Skutečné přidání a odebrání, poté lineární/kruhové pole a zrcadlení; analytické objemy, materiál a pořadí úplného záznamu. |
| T04 | Skutečný builder skici s řízenou chybou až po zápisu pracovní skici, s tělesem i bez něj; existující úspěšné dokumenty jen ze skic. |
| T05 | Odmítnutí `None`, prázdného a smíšeného výsledku; existující pojistky P1.2A včetně nezměněné identity. |
| T06, T07 | Pozdní chyba po první skutečné podoperaci pole/zrcadlení. Kontext se nemění ani mezi podoperacemi; objem 80 000−40π, po opravě 80 000−80π mm³, 1 solid a bodové kontroly materiálu. |
| T08 | Chyba přípravy závitu po skutečném vrtání obnoví i materiál otvoru. Stávající testy skutečných platných závitů zůstávají. |
| T09, T10 | Neznámý typ, chyba přípravy, první chyba, původní `recording`; odmítnutí změny parametrů, vnořeného JSON, typu i pořadí. |
| T11 | `native_ownership.py` v přepočtu všech ukázek; předchozí díl, skici, roviny a nástroje. Samostatná vlastní kopie tvaru se smí změnit na místě, originál zůstává. Další analytické a materiálové regrese se zachovávají. |
| T12 | `test_feature_transaction_interfaces.py`: BinTools/pickle, skutečný `spawn`, chyba→oprava→chyba, přesná dosavadní sada klíčů přenosu. Dosavadní stop a zahození starých výsledků zůstávají v celé sadě. |
| T13 | Session, skutečný worker v okně s náhradním prohlížečem, oprava/Zpět/Znovu/uložení/otevření kopie a nezměněný originál. CLI a offline AI shodně hlásí chybu i počty. |
| T14 | Celá výchozí sada zachovaná; 26 rekurzivních ukázek, načítání v1–22, obálky/objemy/počty a nezměněný zdrojový JSON. Test pěti polí brání tichému přidání neizolovaného pole. |

## Skutečné okno a ruční soubory

Nativní Cocoa okno se skutečným OCCT prohlížečem i workerem provedlo pro pole
a zrcadlení chybu→opravu formulářem→Zpět→Znovu→uložení a otevření kopie;
objemy, počty, stavy a nezměněné originály byly automaticky ověřené.
Samostatný vestavěný self-test skončil **VÝSLEDEK: OK**.
To není potvrzení autora. Při prvním snímkování byl Mac zamčený: snímky pozadí
byly vyřazené a nepovažují se za vizuální důkaz. Opakování po odemčení
a aktuální stav obou CI běhů jsou zaznamenané v implementačním PR a příloze evidence.

[Vedená ruční zkouška](p1-2b-rucni-zkouska.md) používá šest připravených modelů:
pozdní chybu pole, zrcadlení, přírubu, tři trubky, chybu zaoblení a přerušení závitu.
Jejich objemy/počty i CLI a offline souhrny jsou zkontrolované; skutečné ruční
přijetí autora zůstává otevřené. Průchod na Macu nenahrazuje ruční Windows test.

## Zbývající přijetí

Konečná hlava implementačního PR musí mít Ruff a celý pytest, úplné Windows
i macOS workflow včetně self-testu staženého balíčku a protokol vedené ruční
zkoušky podle schváleného návrhu. Rozpracovaný krok ani starší zelené sestavení
se nepovažují za dokončené P1.2B.

Formát zůstává 22; protokol workeru a odborné NDT vymezení se nemění.
R01/export a NDT při chybě, R03/ukládání, R04/reference, R12/popisek formátu pro AI
a odborná NDT-17 zůstávají samostatné. R05 se neuzavírá před celým ověřením
popsané transakční smlouvy. P1.3/P1.4/P2 ani NDT-16 se neimplementují.

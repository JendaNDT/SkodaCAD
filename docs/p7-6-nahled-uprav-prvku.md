# P7.6 – náhled úpravy existujícího prvku

Datum: **1. 11. 2026**. Navazuje na potvrzování nových prvků P7.5.

## Ovládání

Vyber prvek ve stromu a stiskni **Upravit prvek** vpravo nebo v pásu. Stejný
příkaz otevře dvojklik ve stromu nebo Ctrl+E (na Macu Cmd+E). Běžný formulář
zobrazuje hodnoty jen pro čtení. Volba vodítka, rukojeti, kroku a směru tažení
zůstává dostupná i mimo úpravu, protože jde o nastavení pohledu a ovládání.

Panel **Úprava prvku · náhled** dovolí upravovat hodnoty i vnořené tvary/skicář.
Přepočítá se celý recept včetně všech navazujících otvorů, zaoblení a dalších
prvků. Ve 3D je pracovní výsledek; strom a vlastnosti vlevo stále patří
původnímu dílu. Objem náhledu je uveden v potvrzovacím panelu.

- **Potvrdit** přijme platný, aktuální výsledek jako jediný krok Zpět.
  Potvrzení beze změny nevytvoří krok historie ani neoznačí dokument za změněný.
- **Zrušit**, Esc nebo zavření panelu zahodí úpravu včetně rozpracovaných polí.
  Původní soubor, příznak změn, historie Zpět/Znovu a zobrazení se zachovají.
- Neplatné rozepsané pole, běžící výpočet, pád procesu nebo chyba kteréhokoli
  následníka blokují potvrzení. Při chybě se zobrazí původní díl.
- Úpravu lze otevřít i na spočítaném chybném modelu a opravit chybný prvek.
- Změna hran již existujícího zaoblení/sražení z výběru ve 3D otevře stejný
  náhled. Hrany/plochy vyber před spuštěním příkazu.

Tažení rukojeti přímo ve 3D si ponechává dosavadní postup: náhled během tahu,
ověření a jeden krok historie po puštění myši. Přímý posun plochy a změna
průměru z výběru mají vlastní potvrzovací dialog. Parametry, mazání a pořadí
prvků tento krok nemění. Měření stěny přechodu je dostupné na potvrzeném prvku.

## Provedení

`ModelSession.begin_feature_edit` kopíruje recept do oddělené session. Náhled
na pozadí používá vlastní opakovaně využívaný `BackgroundRebuilder` společný
s náhledy nových prvků. Zrušení ruší jen jeho úlohu. Panel nemodeluje přes OCCT.

`apply_feature_preview` kontroluje shodu původního dokumentu, čerstvost a
platnost celého výsledku, stejný typ/id i pozici cílového prvku a nepřítomnost
jiných změn. Ochrana vloženého STEP zdroje platí i při přijetí náhledu.
Hotový výsledek se předá přes `_change(computed_result=…)`, takže potvrzení
nevyvolává druhý přepočet. Beze změny formátu **34**, bez nové závislosti.

## Ověření

Regrese v `tests/test_feature_preview.py`, `tests/test_gui.py`,
`tests/test_sketcher_gui.py` a `tests/test_background.py` pokrývají oddělení
zdroje, zrušení, jedno potvrzení, neplatný následník, opravu chybného zdroje,
zastarání, nepovolené další změny, skicář, readonly prohlížení, samostatný
worker, jeho pád/obnovu a zrušení běžícího výpočtu.

Referenční deska `examples/deska_workflow.json`: změna vysunutí z 10 na 15 mm
přepočítá čtyři průchozí otvory Ø6 a čtyři svislé rohy R2. Očekávaný objem
je **59760 − 480π = 58252,035526 mm³**, rozměry **80 × 50 × 15 mm**, jedno
platné těleso. Zúžení skici na 5 mm zneplatní pozdější otvory a nelze je potvrdit.

Self-test sestavené aplikace **„Úprava prvku“** používá Qt psaní/kliknutí,
potvrzení, zrušení, neplatný rozepsaný výraz i chybu následníka, Zpět/Znovu,
uložení/otevření a skutečný snímek okna. Artefakty místního ověření jsou v
`out/p7-edit-preview/`; výsledky úplné místní sady, CI Windows/macOS a stažených
balíčků se evidují v implementačním PR. Nejde o autorskou přejímku ergonomie,
ruční přijetí Windows ani odbornou validaci NDT.

# P7.5 – náhled nového prvku, Potvrdit / Zrušit

Datum: **1. 11. 2026**. Autor schválil sjednocení vytváření prvků do náhledu
s výslovným potvrzením nebo zrušením. Navazuje na ověření workflow P7.3;
přejímka vzhledu a ergonomie autorem P7.4 je samostatná.

## Ovládání

Příkazy nového prvku z pásu, nabídky i z výběru ve 3D otevřou v pravém panelu
**Nový prvek · náhled**. Strom, soubor a vlastnosti vlevo stále patří původnímu
dílu. Změny formuláře přepočítávají pracovní kopii, její výsledek je vidět ve 3D
a objem/počet těles v panelu náhledu. Zobrazuje se samotný výsledek náhledu;
koplanární povrchy původního dílu se přes něj nekreslí, aby nevznikaly rušivé
pruhy a trojúhelníky v zobrazení.

- **Potvrdit** přijme aktuální platný výsledek a přidá prvek do stromu jako
  **jeden krok Zpět**, bez dalšího přepočítávání stejného návrhu.
- **Zrušit**, **Esc** v panelu/3D nebo zavření pravého panelu zahodí návrh.
  Obnoví se původní díl, jeho řez, mapy a původně otevřený pravý panel.
  Zavření hlavního okna návrh také zahodí; zrušené zavření jej zachová.
- Tlačítka jsou pod posuvným formulářem, takže zůstávají dostupná i u dlouhých
  prvků. Rozepsané hodnoty se ověřují po krátké pauze, Enterem, opuštěním pole
  nebo tlačítkem **Zobrazit náhled**. Neplatný nebo nedopočítaný návrh nelze
  potvrdit. Při chybě je vidět původní díl, úplný text chyby také v bublině.
- Během náhledu lze otáčet, posouvat a přibližovat pohled a volit standardní
  pohledy. Změny původního dílu, další příkazy, ukládání, export, Zpět/Znovu
  a analytické panely jsou do ukončení příkazu nedostupné.
- Hrany/plochy pro vytvoření z výběru se vybírají **před spuštěním příkazu**.
  Geometrie pracovní kopie se nesmí použít jako výběr původního modelu.
- **Skica – nakreslit obrys** nejprve otevře skicář. Jeho **Hotovo** dokončí
  obrys; potom se v pravém panelu zobrazí náhled skici a její rovina, a teprve
  **Potvrdit** ji uloží do modelu. Předpřipravené tvary mají stejný závěrečný krok.

Úprava již existujícího prvku používá dosavadní editor. Přímý posun plochy a změna
průměru už vlastní náhled měly; jejich potvrzovací tlačítko nyní také říká
**Potvrdit**. Měření stěny přechodu a tažení rukojetí jsou dostupné až na
potvrzeném prvku, nikoli nad pracovní kopií.

## Rozhodnutí o provedení

`ModelSession.begin_feature_preview` vytvoří oddělenou session se zkopírovaným
receptem a sdíleným počátečním výsledkem pouze ke čtení. Vložení a změny prvku
v této kopii dál používají běžné metody `ModelSession`. Kopie nedostává cestu
k souboru původního dílu. Geometrie se v GUI nevytváří.

Náhled na pozadí má **vlastní BackgroundRebuilder**, vytvořený až při prvním
příkazu a opakovaně používaný v okně. Nemůže tak zrušit úlohu původního dílu ani
spotřebovat její odpověď. Nová hodnota ruší starší výpočet náhledu. Zavření okna
uzavře oba pomocné procesní pooly; zrušení samotného příkazu jen jeho úlohu.
Bez runneru pracuje stejná session synchronně pro testy.

`apply_feature_preview` ověří původní dokument, dokončený a platný výsledek,
přesně jeden vložený prvek a shodu otisku výsledku s receptem. Pak předá
hotový výsledek přes `_change(computed_result=…)`. Cizí změna, starý výsledek,
pád procesu, chybějící prvek i již zrušený/potvrzený návrh se odmítnou.
Zrušení nemění dokument, dirty příznak, cestu, historii Zpět/Znovu ani výsledky
původní session. Schéma souboru zůstává ve verzi **34**; bez nové závislosti.

Formulář před potvrzením přečte i rozepsané vnořené tvary. Samotný starší platný
náhled nestačí, pokud je v aktuálním poli chyba. Po pádu procesu lze zkusit
**Zobrazit náhled** i se stejnými hodnotami; původní díl se tím nemění.

## Ověření

- `tests/test_feature_preview.py`: fyzikální objemy/rozměry, opakované úpravy,
  jeden krok historie, uložení/otevření, zachování Znovu při zrušení, neplatný a
  opravený návrh, zastarání, nežádoucí další změna, vložení doprostřed stromu,
  skutečně vybraná hrana, asynchronní nejnovější výsledek a zrušení.
- `tests/test_gui.py`: skutečné QAction a tlačítka, nezměněný původní díl,
  invalidní rozepsaný výraz i ve vnořeném tvaru, zamčené ukládání/export/historie,
  dostupný pohled, čtyři způsoby zrušení, zrušené zavření a dostupný spodek
  panelu v okně 1024 × 720.
- `tests/test_background.py`: vlastní worker, nezměněný zdroj během práce,
  úmyslný pád procesu, obnovení náhledu a přijetí bez druhého přepočtu.
- Self-test balíčku **„Náhled nového prvku“**: skutečné widgety, rozepsaná chyba,
  Zrušit, Qt klik Potvrdit, 12000 → `12000 − 90π` = **11717,256661 mm³**,
  jeden krok Zpět/Znovu a uložení. Dosavadní **„Modelování desky“** nyní používá
  nové potvrzení skici, vysunutí, děr i zaoblení.

Starší zkoušky úprav hotových prvků připravují své modely interním okamžitým
přidáním; uživatelské příkazy ověřují výše uvedené interakční testy.
Konkrétní výsledky úplné místní sady, CI Windows/macOS a obou stažených balíčků
jsou evidované v implementačním PR. Místní snímky a zprávy jsou v
`out/p7-feature-preview/`. Nejde o ruční přijetí Windows ani odbornou validaci NDT.

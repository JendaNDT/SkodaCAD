# P7.3 – ověření modelování dílu od nuly

Datum: **1. 11. 2026**, skutečný MacBook autora. Navazuje na jeho otázku,
zda lze popsané workflow prověřit. Výsledek je technická zkouška, autorská
přejímka ergonomie P7.4 zůstává otevřená.

## Referenční díl a postup

[deska_workflow.json](../examples/deska_workflow.json) vznikl ovládáním skutečného
okna zabalené aplikace. Parametry `delka=80`, `sirka=50`, `tloustka=10`, obdélník
na XY se šířkou `delka` a výškou `sirka`, vysunutí `tloustka`.

Díra: hladká průchozí, vlastní průměr **6 mm**, horní plocha, čtyři pozice:

```text
-delka/2+10; -sirka/2+10
delka/2-10; -sirka/2+10
delka/2-10; sirka/2-10
-delka/2+10; sirka/2-10
```

Středy jsou tedy 10 mm od vnějších stran, při změně rozměrů se posunou.
Hodnota M6 ve volbě tabulky při vlastním Ø6 neznamená závit. Zaoblení R2
se týká čtyř vnějších svislých rohů. V uloženém receptu byly vybrány dvě
hrany na přední a dvě na zadní ploše, vždy rovnoběžné se Z. Vybírat všechny
hrany rovnoběžné se Z by zahrnulo také švy válcových děr.

| Stav | Rozměry [mm] | Objem [mm³] |
|---|---|---|
| Vysunutí | 80 × 50 × 10 | 40 000 |
| Čtyři průchozí Ø6 | 80 × 50 × 10 | `40000 − 360π` = 38 869,026644708 |
| Navíc čtyři vnější R2 | 80 × 50 × 10 | `39840 − 320π` = 38 834,690350851 |
| Délka 100 | 100 × 50 × 10 | `49840 − 320π` = 48 834,690350851 |

V každém hotovém stavu jde o jedno platné těleso. Ztráta za každý roh je
`(2² − π·2²/4)·10`. Kontrola porovnává objem a rozměry, nestačí jen zelený strom.

## Co bylo ověřeno a jak

- **Skutečné ovládání přes přístupnost a klávesnici:** nový díl, název,
  přidání parametrů dialogem, skica, výrazy ve formuláři, vysunutí, čtyři otvory,
  dvě zaoblení, uložení a opětovné otevření. Změna délky 80 → 100,
  Zpět → 80, Znovu → 100, návrat na 80 a uložení. Vlastnosti v GUI odpovídaly
  tabulce (objem se v panelu zaokrouhluje na celé mm³).
- **Nativní Qt/QTest:** skutečné události myši na OCCT ploše, výběr horní
  plochy, vytvoření skici z výběru a Zpět; kliknutí na čtyři vnější rohy
  v pohledech zepředu/zezadu s přidáváním do výběru; zaoblení jedním prvkem.
  Souřadnice pocházejí z OCCT projekce, události procházejí stejným obslužným
  kódem jako myš. Automatizace desktopu pro 3D souřadnicové kliknutí hlásila
  nedostupné okno; tento krok proto neoznačujeme za ruční myšovou zkoušku.
- **Self-test „Modelování desky“ v balíčku:** skutečné widgety a Enter/Tab,
  fyzikální kontrola všech výše uvedených stavů, jeden krok za změnu bodů,
  historie, uložení/otevření a export STEP/STL. Bez grafiky ověří recept,
  s grafikou navíc skutečný výběr plochy a čtyř hran.
- **Cílené regrese GUI:** potvrzení čtyř otvorů Tabem s kontrolou objemu,
  editor po vytvoření z výběru i po přijetí skicáře, zachování panelu při
  zrušení skicáře, nejméně čtyři čitelné řádky stromu při rozbalení skupin.

Místní artefakty jsou v `out/p7-workflow-2026-11-01/`: skutečně uložený
`deska-overeni.json`, mezistav `deska-pred-zaoblenim.json`, záznamy nativních
zkoušek a cílených testů. Původní neuložený prázdný díl byl před testováním
uložen samostatně jako `puvodni-rozpracovany-dil.json`.
Úplné kontroly Windows/macOS a obou stažených balíčků jsou podmínkou sloučení;
konkrétní výsledky a běhy eviduje implementační PR.

## Opravené nálezy

1. **Pád přístupnosti Qt na Macu.** Přidání parametrů a změna formuláře skici
   vedly při čtení `NSAccessibilitySelectedChildren` k SIGSEGV v `libqcocoa`.
   Samostatný minimální případ se stejnou verzí Qt a bez modelování padal
   kódem 139; s opravou dvanáct cyklů skončilo kódem 0.
   Qt popisuje stejnou chybu vlastnictví jako
   [QTBUG-149612, oprava 8148c48](https://github.com/qt/qtbase/commit/8148c48deb8e4345bacb797cb75c011df6f797fa).
   Nativní buňky/řádky mazaly rozhraní stále vlastněná cache Qt.
   ŠkodaCAD přebírá sémantiku upstream opravy pouze pro `invalidate/dealloc`:
   uvolnění nativních polí zůstává, mazání rozhraní Qt se neprovádí.
   Přístupnost zůstává zapnutá. Pomocná knihovna se sestavuje systémovým SDK,
   nevyžaduje další runtime závislost ani privátní hlavičky Qt. Před instalací
   ověří verzi **6.11.3**, přítomnost a typy ivarů/metod. Při změně Qt je nutné
   ověřit opravu a shim odstranit, nikoli automaticky povolit další verzi.
   Self-test „Přístupnost macOS“ opakuje čtení nativních dětí/výběru u dvanácti
   stromů, seznamů a tabulek; kontroluje, že identita Qt dál existuje, a zkouší
   vymazání a zničení widgetů. Původně padající průchod v GUI po opravě prošel.
2. **Tab v souřadnicích vkládal tabulátor.** Nyní opouští pole a platné
   souřadnice potvrdí jednou. Enter nadále přidá nový řádek.
3. **Nový prvek z výběru nebo skicáře neotevřel editor**, pokud byl aktivní
   jiný pravý panel. Po úspěchu se nyní editor ukáže; zrušení skicáře panel nemění.
4. **Rozbalené skupiny vlevo stlačily strom na jeden řádek.** Strom má minimální
   výšku 150 bodů, delší vlastnosti se zalamují. Vnější panel lze posouvat.

Jádro, formát 34 a dosavadní pravidla NDT se nemění. Nový jednoduchý recept
potřebuje pouze verzi 24; nižší uložená verze neznamená ztrátu funkce.

## Samostatně zjištěné omezení prostředí

První otevření souborového dialogu nově podepsané testovací aplikace přes
Launch Services čekalo na oprávnění macOS ke složce Dokumenty. Vzorek procesu
ukazoval blokované `opendir` a log `tccd` žádost o `SystemPolicyDocumentsFolder`;
nešlo o další pád Qt. Nebylo změněno oprávnění ani zabezpečení systému.
Průchod pokračoval spuštěním vlastní aplikace z vývojového prostředí s již
povoleným přístupem do pracovního adresáře; uložení i otevření pak prošly.
Tím není ověřeno udělení oprávnění při běžném spuštění nového sestavení z Finderu.

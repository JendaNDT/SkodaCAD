# P1.5 — nativní ověření agentem na Macu, 24. 10. 2026

Tento protokol doplňuje [matici přijetí](p1-5-overeni.md) podle schváleného
[návrhu F1–F9](p1-5-navrh-prijeti-bezpecne-geometrie.md). Autor svěřil dostupné
zkoušky agentovi; nejde o nové potvrzení autora pro každý jednotlivý krok.

## Přesný způsob a původ

Na místním Macu M4, macOS 27.0.1 arm64 / Python 3.12.14 / PySide6 6.11.2
proběhl skutečný Cocoa `MainWindow` s `OccViewer` a skutečným pomocným procesem
`BackgroundRebuilder` se spawn. Okno bylo otevřené a snímky kontrolované vizuálně.
Pole a akce byly ovládané programově přes Qt; výběr ve 3D byl předaný signálem
skutečného vieweru. Dialogy výběru souboru měly známé testovací cesty; akceptace
skicáře byla nahrazená, jeho skutečné nástroje/obsah a návrat do dokumentu zůstaly.
Nativní dialogy, fyzické klikání, Retina a trackpad tím nejsou plně přijaty.

Běh měl HEAD `c26b47f7dfd91d51e9eb76bc36d3857769579af5` s novým testem a
pracovní dokumentací F.2; produkční kód byl shodný s main `e7f9ac6`.
Zdrojový otisk (shodná metodika jako baseline P0):
`e2fde6065e645b0ed1845f569773d298692eadf91bcd06961ab16abc93ab2399`.
Shoda zdrojů i pěti použitých testovacích pomocníků se ověřuje vůči konečné verzi;
nejde o tvrzení, že zde byl spuštěn budoucí balíček z CI. Ten má samostatný self-test.
Testovací profil je oddělený od autorova `~/SkodaCAD`.

## Skutečné výsledky

Všech 15 kroků dokončeno, žádná nezachycená chyba slotu ani neočekávané varování.
Odmítnutí exportů při R50 jsou očekávaná česká hlášení, nikoli selhání zkoušky.
Objemy níže patří viditelnému tělesu; v chybě jde o výslovně označený mezistav.

| Krok | Provedeno | Objem [mm³] | Výsledek |
|---|---|---:|---|
| 1 | Platný kvádr, všech pět exportů, znovunačtený STEP a oba formáty řezu | 24000.000000 | Doloženo |
| 2 | Výška 40→50, Zpět/Znovu a návrat na 40 | 24000.000000 | Doloženo |
| 3 | Dva válce, všech pět exportů a STEP se dvěma tělesy | 1570.796327 | Doloženo |
| 4 | R50, označený mezistav, odmítnuté přímé exportní akce dílu i řezu | 24000.000000 | Doloženo |
| 5 | Uložená a znovu otevřená chybná pracovní kopie | 24000.000000 | Doloženo |
| 6 | Oprava R50→R2, výstupy dostupné, studie stále zastaralá | 23701.687230 | Doloženo |
| 7 | Zpět obnoví chybu a blokaci výstupů | 24000.000000 | Doloženo |
| 8 | Znovu, kontrola oblasti a výslovné technické potvrzení bez odborného ověření | 23701.687230 | Doloženo |
| 9 | Opravený díl ve všech pěti formátech | 23701.687230 | Doloženo |
| 10 | Opravený řez v DXF i SVG | 23701.687230 | Doloženo |
| 11 | Nová PT mapa a CSV | 23701.687230 | Doloženo |
| 12 | Nový audit jedné PT studie, HTML/CSV/PDF | 23701.687230 | Doloženo |
| 13 | Nejednoznačná hrana, výměna přes výběrovou akci, historie a uložená kopie | 23922.743339 | Doloženo |
| 14 | Reference opravená ve skicáři, Zpět/Znovu, kopie a nové otevření | 24006.283185 | Doloženo |
| 15 | Skutečný spawn, okamžité Zastavit, návrat na výšku 40 a Znovu na 80 | 48000.000000 | Doloženo |

Kvádr po STEP měl 24 000 mm³, obálku 20×30×40 a 1 solid. Dva válce mají
500π mm³ a 2 solidy i po STEP. Průřez kvádru má 600 mm². Po opravě hrany
kontrolní body odlišují správný upravený roh od ostatních; po opravě projekce
vznikne přídavek 2π mm³. Byly ověřené skutečné recepty, výsledek i stav historie,
ne pouze dostupnost tlačítka. Původní vstupní soubory zůstaly shodné.

Snímky `okno-dve-telesa.png`, `okno-chyba-modelu.png` a `okno-projekce.png`
byly otevřené a vizuálně zkontrolované: obě části/počet, trvalé varování a
opravený navazující díl jsou viditelné. Součástí předání jsou také opravená hrana,
PT mapa, osm receptů v22 a výstupy. Surový JSON protokolu obsahuje stavy prvků,
studií, dostupnost exportů a viditelnost varování; otisky vstupů i spouštěcího
skriptu jsou uložené spolu s předáním mimo dočasné CI artefakty.

## Krátká dobrovolná vlastní zkouška

Jednotlivé potvrzování znovu není potřeba. Pokud si chce autor průchod zopakovat,
použije aplikaci a modely z konečného předání:

1. Otevřít `00-platny-kvadr.json`: 24 000 mm³, 1 těleso; výška h=50 má 30 000,
   Zpět/Znovu vrací správné hodnoty. `03-dve-telesa.json` má 2 válce / 500π mm³.
2. Otevřít `01-chyba-modelu.json`: R50, trvalá příčina a diagnostický kvádr;
   exporty dílu/řezu a NDT nejsou dostupné. Uložit jako pracovní kopii a znovu otevřít.
3. Změnit r na 2: model projde a export je dostupný. Zpět vrátí chybu, Znovu opravu.
4. U `04-nejednoznacna-hrana.json` nahradit výběr skutečnou požadovanou hranou;
   `05-opravena-hrana.json` je doložená výsledná kopie. `06-promitnuta-hrana.json`
   se opraví ve skicáři; `07-opravena-projekce.json` je výsledná kopie s referencí.
5. Po změně dílu zkontrolovat celou NDT oblast, případně opravit vazbu a technicky
   potvrdit, teprve pak počítat novou mapu. Technické potvrzení není odborné ověření.
6. Při změně h zkusit Zastavit: návrat k poslednímu spočítanému receptu,
   Znovu změnu zopakuje. Uložením kopie se zachová originál.

## Meze

Zdrojové nativní ověření se neopisuje jako fyzické přijetí balíčku autorem.
Windows se ověřuje v CI, jeho fyzické ovládání zde nebylo provedeno. Plná matice
Retiny, trackpadu a GPU i NDT-17 zůstává samostatná. R03/R04/R12 se neuzavírají.
Nebyla zapsaná žádná skutečná odborná validace studie. NDT-16 mimo rozsah.

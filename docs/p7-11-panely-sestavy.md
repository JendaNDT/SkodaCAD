# P7.11 – více místa pro sestavu

Datum: **1. 11. 2026**. Autor schválil zúžení bočních panelů. Navazuje na
opravu ostrosti P7.10 a vybraný směr **Strom a pravý editor** ze strojního CADu.

## Chování

Strom již nemá pevné minimum 440 bodů. Výchozí šířky stromu/editoru jsou
250/300. Sloupec Soubor je skrytý; zobrazí ho **Zobrazení → Soubory ve stromu**.
Úplná cesta, stav, varování a důvod zůstávají v bublině každého řádku.
Výběr horní komponenty dál ukáže její soubor a volnost v pravém detailu. Texty stavů
se nemažou a nejsou nahrazené samotnou ikonou; úzký sloupec je může zkrátit.
První nativní návrh s automatickým Stretch prvního sloupce vykreslil prázdné
názvy, přestože offscreen geometrie i data byly správné. Sloupec názvu proto
začíná explicitní šířkou 180 bodů a lze jej ručně změnit. Reset obnovuje i
šířky sloupců. Opravený nativní snímek již ukazuje názvy i odsazení podsestav.

Editor má jméno přes celou šířku a tři řádky X/Y/Z, každý s posunem a otočením.
Každé pole má nejméně 90 bodů. Dlouhá pomocná hlášení se zalamují a delší panel
se posouvá svisle. Enter i tlačítko Použít polohu a název fungují jako dřív.

Kontrola sestavy je zpočátku skrytá; spuštění kontroly ji otevře. Nabídka
**Zobrazení** obsahuje přepínače stromu F9, editoru F4, kontrol F8 a
**Obnovit rozložení**. Reset vrátí úzké boční panely, skryje kontroly i sloupec
Soubor. Zavřený panel se dá obnovit, aniž by se ztratil výsledek kontroly.
Panely zůstávají na svých stranách, nelze je odtrhnout. Jejich šířku lze měnit.

Reset ani přepínání neobnovují model, nemažou výběr, historii nebo rozepsané
hodnoty a nepřizpůsobují kameru. Změna velikosti okna běžně upraví poměr stran
3D pohledu. Výchozí rozložení se používá v každém novém okně sestavy; tento
krok nepřidává samostatný trvalý profil sestavy. Formáty a geometrické jádro
zůstávají beze změny.

## Ověření

Na MacBooku M4, Cocoa Qt 6.11.3, Retina 2×, zabalená aplikace: self-test
naměřil šířku 3D **648 bodů při okně 1200** a **472 při 1024**. Všech šest
polí mělo nejméně 90 bodů. Původní běžné okno mělo přibližně 328 bodů pro 3D;
snímek je uložen jako `out/p7-assembly-layout/before.jpg`.

Self-test „Panely sestavy“ ověřuje rozměry před exportem obrazu, také fyzické
Retina rozlišení z P7.10. Skutečným Qt Enterem zadá posun víčka 1,5 mm,
ověří posunutí obálky o 1,5 mm a přes Zpět obnoví celý původní recept.
Otevře/skryje kontroly bez změny sestavy. Celý místní self-test sestavené
aplikace skončil **VÝSLEDEK: OK**, podpis je ověřený.

Cílené regrese pokrývají šířky 1200/1024/960, čitelná pole, přepínání a obnovu
panelů, zachování rozepsaného neplatného výrazu, výběru a řádků Qt, historie
a volání prohlížeče. Další regrese ověřuje otevření kontrol příkazem a zachování
výsledků po resetu. Dosavadní zkoušky poloh, vazeb, podsestav a souborů zůstávají.
Výsledky úplných sad macOS/Windows a stažených balíčků jsou v implementačním PR.

Místní snímky a protokoly: `out/p7-assembly-layout/`. Měření offscreen se může
o několik bodů lišit kvůli stylu Qt; není náhradou nativního snímku. Autorská
přejímka P7.4 ani práce na vlastním dílu se tím neprohlašují za dokončené.

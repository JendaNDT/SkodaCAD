# P7.20 – hromadné otáčení kolem společného středu

Datum: **2. 11. 2026**. Navazuje na P7.18–P7.19. Formát a závislosti beze změny.

## Ovládání a střed

Vyber více dílů nebo celé podsestavy a v panelu **Společné otočení [°]** zvol osu
**X, Y nebo Z celé sestavy**, zadej úhel a potvrď **Otočit vybrané** nebo Enter.
Výchozí je Z a 90°. Desetinná čárka, záporný úhel a výrazy s parametry sestavy
jsou podporované. Kladný úhel odpovídá pravidlu pravé ruky. Osa prochází společným
středem, nikoli počátkem každého dílu. Číselné volby zůstávají v otevřeném okně.

Střed je **geometrické těžiště výběru vážené objemem**: součet objem × těžiště
jednotlivých kopií dělený součtem objemů. Materiál ani hustota ho neovlivňují.
Zahrnuje všechny vybrané větve, i ručně skryté díly a díly mimo izolaci, nikoli
nevybrané okolí. Souřadnice ukazuje panel. U nestejných objemů nejde o průměr
počátků ani střed obálky. Tento bod při tuhém otáčení zůstává na místě; navazující
opačné otočení tak vrátí původní polohu i u nesouměrného výběru.

Každá kopie má nový počátek `c + Q·(p−c)` a natočení `Q·R`. Všechny vybrané
komponenty zachovají vzájemné vzdálenosti a orientace. Vybraný rodič s potomkem
se zpracuje jednou, vnitřní pevnost dílu brání jen pohybu uvnitř jeho podsestavy.
Samostatně vybrané vnitřní díly vyžadují výběr celého rodiče nebo otevření podsestavy.

## Přijetí, historie a parametry

Pevná komponenta nejvyšší úrovně blokuje **celý** příkaz. Požaduje se úplná sestava.
Vazby musí dovolit přesně zadaný pohyb, bez návratu vybraného dílu nebo přitažení
nevybraného souseda. Při chybě se nemění recept, výsledek, Zpět ani Znovu a úhel
zůstává k opravě. Úspěch vytvoří jeden krok Zpět/Znovu. Nulový úhel a násobky 360°
nepřidají historii ani nesmažou Znovu. Soubory zdrojových dílů a podsestav se nepřepisují.

Střed a vyhodnocený úhel jsou snímkem v okamžiku příkazu. Výrazy souřadnic se
transformují stejnou afinní mapou, jejich parametry se nezmění na čísla. Pozdější
změna parametru se proto dál uplatní v otočeném směru kolem tohoto uloženého bodu.
Stejné členy se slučují, takže opakované otáčení výrazy exponenciálně nezvětšuje.
Natočení zadané výrazem se kolem Z zachová přičtením úhlu k poslednímu Eulerovu
úhlu. Pro X/Y jsou potřebné číselné hodnoty natočení; jinak je příkaz vypnutý
s vysvětlením. Parametrické polohy lze použít ve všech osách.

Kamera, viditelnost, izolace, průhlednost, výběr a rozepsaný číselný posun zůstávají.
Plochy rozpracované vazby se po změně geometrie vyčistí jako u ostatních úprav.

## Ověření

Regrese porovnávají skutečné vrcholy a těžiště proti nezávislé Rodriguesově matici,
objemy, platnost těles, nevybrané díly, všechny osy a oba směry. Pokrývají různé
objemy, již natočené díly, blízkost ±90° Eulerovy souřadnice, parametrické polohy
i natočení, opakování a opačný pohyb, neplatné vstupy, nulové otáčky, pevnost,
vnitřní/vnější vazby, celé podsestavy v jiné složce, změnu zdroje, uložení a STEP.

Nativní self-test skutečně přepne osu a potvrdí Enterem **37,5° kolem XYZ**.
Kontroluje oba díly včetně skrytého, stálý společný střed, okolní díly, 35/85 %
průhlednost, kameru, parametry, objem a jeden krok Zpět/Znovu i nulovou historii 360°.
Běží také ve stažených balíčcích Windows a macOS. Místní protokoly a snímky jsou
v `out/p7-batch-rotation/`; konečné výsledky úplných kontrol před sloučením patří do PR.

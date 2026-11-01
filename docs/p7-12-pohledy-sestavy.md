# P7.12 – rychlé pohledy sestavy

Datum: **1. 11. 2026**. Autor schválil přidání pohledů Shora, Zepředu
a Izometrie do sestavy po zúžení panelů P7.11.

## Ovládání

Stávající lišta sestavy obsahuje **Shora (7), Zepředu (1), Izometrie (0)**
a **Celá sestava (F)**. Poslední příkaz vměstná celou sestavu do pohledu
a zachová jeho směr. Standardní pohledy také upraví záběr na celou sestavu.
Příkazy jsou dostupné i v nabídce **Zobrazení**, včetně ostatních směrů
sdílených s dílem: Zprava 3, Zezadu Ctrl+1, Zespodu Ctrl+7 a Izometrie
zezadu Ctrl+0 (na Macu Cmd místo Ctrl).

Na liště jsou stručné příkazy **Otevřít, Vazba a Kontrola**; v menu i bublinách
zůstává úplný popis. První úplná sada Windows odhalila přetečení nových tlačítek
v úzkém okně, které se na Macu neprojevilo. Popisky proto šetří místo bez nové
řádky lišty a bez zmenšení výšky 3D plochy.

Menu, tlačítka a klávesy používají stejné QAction a stejné názvy/zkratky
z `viewer_views.VIEW_LABELS`. Změní se pouze kamera. Recept, polohy komponent,
výběr, historie i rozepsané hodnoty zůstávají zachované. Nezavádí se globální
zachytávání kláves: v textovém poli se 0/1/7/F zapisují jako dosud.

## Ověření

Regrese ověřují všech sedm směrů v menu, sdílení akcí s lištou, viditelnost
čtyř nových tlačítek při šířkách 1200/1024/960 a zachování modelu, výběru,
geometrie, historie a rozepsaného výrazu. Druhý případ skutečně píše `107F`
do pole, pak se přepne do prohlížeče a zkouší stejné klávesy pro pohledy.

Nový self-test „Pohledy sestavy“ používá zabalenou aplikaci, skutečné Qt
kliknutí na tlačítka a klávesy v nativní 3D ploše. Ověří vektory kamery pro
Shora/Zepředu/Izometrii. Potom šestinásobně přiblíží, stiskne F a ověří,
že projekce vrcholů všech kopií leží uvnitř okna a směr kamery se nezměnil.
Kontroluje také recept, délky obou zásobníků historie, výběr a příznak změny.
Předtím kontroluje viditelnost i obdélníky všech čtyř tlačítek uvnitř lišty
při šířkách 1024 a 960 také v nativním zabaleném okně.

Místní sestavená aplikace na MacBooku M4 / Retina 2× prošla celým self-testem
**VÝSLEDEK: OK**. Cíleně prošlo **181 testů**, ruff i kontrola podpisu.
Viditelnost všech čtyř nových tlačítek se kontroluje i při šířce okna 960.
Nativní snímky a protokoly jsou v `out/p7-assembly-views/`. Úplné výsledky
macOS/Windows, stažených balíčků a STEP přenosu jsou v implementačním PR.

P7.4 (autorská přejímka ergonomie) zůstává otevřená; tento krok nepřidává
geometrii, formát dokumentu ani nové závislosti.

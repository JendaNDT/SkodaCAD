# P7.32 — editor parametrů sestavy

Parametry jsou dostupné tlačítkem **Parametry sestavy…** nad stromem komponent
i z nabídky **Úpravy**. Tabulka obsahuje název, číslo nebo výraz a vypočtenou hodnotu.
Přidání, přejmenování, úpravy a mazání jsou nejprve pouze pracovní obsah dialogu.
Enter dokončí buňku; až **Použít změny** přijme celou dávku přes
`AssemblySession.set_parameters`, jedním krokem Zpět. Zrušit nic nepřijme.

## Chování a meze

- Desetinná čárka platí pro samostatné číslo (`12,5`); uvnitř výrazu má desetinné
  číslo tečku (`mezera * 1.5`), čárka odděluje argumenty funkcí (`min(a, b)`).
- Výrazy mohou odkazovat na jiné parametry bez ohledu na pořadí řádků.
- Prázdné nebo duplicitní názvy, rezervované názvy, kruhové odkazy, neznámé parametry,
  nekonečné hodnoty a nespočitatelné výrazy se nepřijmou. Chyba zůstane v dialogu
  spolu s rozepsanými hodnotami, aby je šlo opravit.
- Session před přijetím ověří také použití parametrů v polohách, otočeních a
  vzdálenostních vazbách aktuální úrovně. Smazání nebo přejmenování používané hodnoty
  nesmí odebrat těleso z výsledku ani zneplatnit vazbu. Přejmenování automaticky
  nepřepisuje výrazy jinde v sestavě.
- Nový spor vazeb se odmítá stávající kontrolou `_change`. Po odmítnutí zůstává
  původní model, výsledek a historie Zpět/Znovu.
- Parametry podsestav a rozměry zdrojových dílů mají vlastní kontext, zde se nemění.
  Polohy jsou v mm, otočení ve stupních podle místa použití. Formát souboru,
  geometrické jádro a závislosti se nemění.

## Ověření

`tests/test_assembly_parameters.py` ovládá skutečné editory buněk náhradního okna
a ověřuje fyzickou polohu a natočení kvádru, víčko řízené vzdálenostní vazbou,
závislé výrazy, uložení a nové otevření, jeden krok Zpět/Znovu, nezměněné zdrojové
soubory, odmítnutí neplatných hodnot i nového sporu a zachování existujícího Znovu.

Self-test aplikace obsahuje scénář **Parametry sestavy**. Otevře skutečný modální
editor tlačítkem i akcí menu, zadá `mezera = 12,5` a `polovina = mezera/2`, změří
posun víčka o 12,5 mm a všech sedm splněných vazeb. Ověří historii, kameru,
odmítnuté smazání používaného parametru a zrušení bez změn. Scénář se spouští také
ve stažených balíčcích Windows a macOS. Místní důkazy jsou v
`out/assembly-parameters/`; výsledky úplných kontrol jsou v implementačním PR.

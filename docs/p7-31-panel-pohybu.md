# P7.31 – přehledný panel pohybu sestavy

Datum: **2. 11. 2026**. Součást dávky #107 společně s P7.30 a dávkováním kontrol.

## Ovládání

Pod vybranou komponentou jsou záložky **Posun** a **Otočení**. Zobrazuje se vždy
ovládání aktuální záložky a panel zabírá výšku jejího obsahu. Posun tedy nerezervuje
místo pro vyšší formulář otočení. Stejné rozložení funguje pro jeden i více dílů.

**Posun** obsahuje přírůstky XYZ, potvrzení, posouvací rukojeti a krok tažení.
**Otočení** obsahuje osu, úhel, střed nebo referenci z geometrie, potvrzení,
rotační rukojeti a jejich krok. Zapnutí rukojetí otevře příslušnou záložku.
Samotná volba záložky pouze zobrazí její ovládání; zachovává volby rukojetí.

Pod pohybem jsou standardně sbalené sekce **Absolutní poloha a název** a
**Vzhled výběru**. První obsahuje název, absolutní souřadnice a natočení, pevnost,
rychlé otočení a odkazy na soubor dílu. Druhá obsahuje průhlednost. Šipka sekci
rozbalí; souhrn a práce s vazbou zůstávají samostatně dostupné.

## Zachování práce a bezpečné přepnutí

Přepínání záložek a sbalování sekcí zachovává rozepsaná pole, vybranou komponentu,
převzatou osu, model, stav změn, historii a kameru. Přepnutí záložky ukončí
rozpracovaný náhled a výběr reference ve 3D. Revize panelu je součástí tokenu
pohybu: starý tah se nepřijme ani po návratu na původní záložku. Již převzatá osa
zůstává uložená v dosavadních preferencích okna.

Přechod na konkrétní ovládací prvek přes `ensureWidgetVisible` současně otevře
jeho záložku nebo sbalenou sekci. Platí to pro stávající nativní kontrolní scénáře
a programové zpřístupnění pole; samotné zobrazení neprovádí příkaz modelu.

## Ověření

`tests/test_assembly_motion_panel.py` ověřuje skutečné kliky na záložky, výšku
podle aktuální stránky, dostupnost tlačítka posunu bez rolování v okně 1200 × 800,
zachování rozepsaných polí i preference rukojetí, otevření konkrétního pole,
odmítnutí starého posunu/otočení a zrušení zastaralého výběru osy.

Nativní `--self-test` obsahuje scénář **Panel pohybu sestavy**: skutečné kliky
na záložky a šipky sekcí, zachování modelu, historie, kamery i vstupů a odmítnutí
starého tahu. Ostatní nativní scénáře nadále zkoušejí pohyby a geometrické reference.

Místní protokoly a snímky: `out/assembly-motion-panel/`. Úplné kontroly na obou
systémech a sestavené balíčky patří až k dokončení celé dávky.

# P7.30 – číselný posun a posouvací rukojeti pro jeden díl

Datum: **2. 11. 2026**. Navazuje na P7.29: posun a otočení mají stejnou dostupnost
pro jednu komponentu i celý výběr. Součást rozpracované dávky #107.

Při výběru jednoho dílu je dostupný panel **Posun [mm]**, při výběru více dílů
**Společný posun [mm]**. Číselný přírůstek X/Y/Z potvrdí tlačítko nebo Enter.
Úspěšný číselný posun pole vynuluje; tažení rozepsané přírůstky zachovává.

Volba **Posouvací rukojeti ve 3D** je zapnutá jako dosud. U viditelného vybraného
dílu se zobrazí úchopy XYZ; jejich tažení pracuje v osách celé sestavy.
**Krok tažení**, náhled, přerušení přes Esc a jeden krok Zpět/Znovu platí stejně
jako u více dílů. Zapnutí rotačních rukojetí posouvací rukojeti vypne a naopak.

Pevné komponenty a samostatné vnitřní díly podsestav zůstávají blokované. Celá
vybraná podsestava se posune včetně skrytých dětí. Skrytý díl lze posunout
číselně, ve 3D nemá úchopy. Vazby musí dovolit přesně zadaný pohyb bez pootočení
nebo přitažení okolních dílů; odmítnutí zachová model, historii i rozepsaný vstup.
Ostatní komponenty, otočení, parametrické výrazy a soubory podkladů se nemění.

## Ověření a stav

Regrese v `tests/test_single_part_move.py` kontrolují skutečné vrcholy všech
komponent po posunu XYZ číselně i přes rukojeť, platnost a objem, neměnné okolí
a otočení, Zpět/Znovu, přepínání režimů, starý tah, pevnost, prázdný výběr,
vnořenou komponentu, skrytý díl, zamítnutí vazbou a celé podsestavy se skrytým dítětem.

Nativní scénáře v `gui/app.py` skutečně zadávají přírůstky Enterem a táhnou
úchopy XYZ také pro jeden díl. Kontrolují náhled, průhlednost, historii, okolí,
parametrické polohy a zrušení přes Esc, změnu kroku i přesun fokusu. Jsou součástí
`--self-test` budoucích sestavených balíčků.

Místní evidence a snímky: `out/single-part-move/`. Dávka zůstává rozpracovaná;
nové změny dosud neprošly úplnými kontrolami Windows/macOS ani vydáním.

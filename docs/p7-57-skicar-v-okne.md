# P7.57 – skicář jako režim hlavního okna (vydání D, krok 1)

*Součást [plánu nového okna](p7-48-plan-noveho-okna.md); rozhodnutí R1–R7 schválil
autor 6. 11. 2026. Pokračování na pokyn autora „ok, pokračuj P7.57“ (8. 11. 2026).
Vzorem je rám 2d v [`p7-48-navrh-okna/obrazovky/`](p7-48-navrh-okna/obrazovky/).*

## Co se změnilo

- **Skicář už není samostatné okno.** Otevře se v hlavním okně (Skica – nakreslit obrys,
  Upravit obrys u skici, úprava skici v náhledu prvku):
  - **plátno místo 3D pohledu** – mřížka a barvy podle návrhu (`--skbg`, `--skgrid`,
    neurčený obrys `--skfree`), ve světlém i tmavém vzhledu. „Celý obrys“ se vejde do
    volného místa mezi kartami;
  - **plovoucí paleta Skica**: Výběr S, Úsečka L, Oblouk A, Kružnice R, Pomocná G |
    Kóta D, Promítnout U, Převzít W (fialově) | Zrušit, **Hotovo**. Segment činností nahoře
    ukazuje „Skica“;
  - **levá karta**: strom prvků zkrácený na řádky a pod ním **Vazby skici · N**. Vlevo je
    druh vazby, vpravo hodnota kóty nebo čeho se týká. Dvojklik změní kótu, chybné vazby
    jsou červeně;
  - **pravá karta „Výběr“**: nadpis podle výběru („Úsečka a kružnice“, „2 úsečky“).
    *Přidat vazbu* nabízí jen vazby, které jádro pro výběr přijme. Doporučená je modře
    (např. Tečně), další až tři vedle ní a zbytek ve sbalené sekci *Ostatní vazby*. Dál
    jsou tu „Rozměr mezi výběrem – Kóta… D“, Smazat, Zpět ve skice, Celý obrys a stav
    obrysu (včetně varování, např. kříženích smyček);
  - **pilulka**: „Zbývá určit: N rozměrů | Modrý obrys jde ještě táhnout myší“, nebo
    „✓ plně určeno“ či „✕ Vazby si odporují“.
- **Ovládání zůstává:** zkratky nástrojů a vazeb (H, V, P, K, T, E, C, M, O, Y, F, D,
  Delete, Ctrl+Z ve skice, 0) platí v celém okně. Esc ukončí řetěz čar, druhé Esc zruší
  výběr a třetí přepne na Výběr. Ostatní příkazy okna jsou během skicáře zamčené.
  Zavření okna nejdřív skicu zruší.
- **Hotovo = jeden krok Zpět jako dřív.** U nové skici následuje náhled prvku (P7.5),
  u úpravy se vrátí náhled úpravy. Zrušit nic nemění. Řešič `slvs`, `profile_edit.py`
  ani formát (34) se nemění.
- Technicky zůstává logika v `SketcherDialog`. Nový `gui/sketch_mode.py` si od něj
  vypůjčí plátno, akce a seznam vazeb a čeká v místní smyčce událostí jako dřív
  `QDialog.exec`. Volající proto dostanou obrys stejně a testy skicáře platí beze změny.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_sketch_mode.py` (6) | plátno je dítě 3D pohledu, paleta Skica místo palety příkazů, segment „Skica“, zamčené akce okna a zkratky skicáře v okně, „Prázdná skica“ / „Zbývá určit: …“ v pilulce, vazby v levé kartě, nadpis „Bez výběru · Výběr“; Hotovo → náhled nové skici se 4 čarami a návrat okna (akce, paleta, pohledy); Zrušit beze změny modelu a historie; Esc ukončí čáru a pak zruší výběr; výběr úsečky a kružnice nabídne Tečně jako primární a skutečné kliknutí ho přidá; úprava skici z náhledu se vrátí do náhledu; zavření okna skicu zruší; názvy výběru |
| `tests/test_sketcher_gui.py` (24) | beze změny, prochází (skicář jako samostatná logika) |
| testy okna, náhledů, skicáře, hledání, oblíbených, filtrů | viz PR |
| self-test „Skicář v okně“ (Linux Xvfb, 1440 × 900, skutečné 3D) | plátno místo 3D (`childAt` uprostřed), skutečný klik na Úsečka a pět kliků myší na plátno = obdélník 4 čar, skutečné Esc ukončí čáru, pilulka „Zbývá určit: 2 rozměry“, karta Výběr 302 px se vejde, skutečný klik Hotovo → náhled skici, zrušení bez změny modelu |

Snímek: [skicář v okně](p7-48-snimky/skicar-v-okne.png).

## Meze

- Rám 2d ukazuje vpravo dole „Kolmo na skicu | Celá skica“. Přepínač 3D pohledů je ve
  skicáři skrytý; celou skicu ukáže klávesa 0 nebo tlačítko Celý obrys v kartě Výběr.
- Štítky vazeb u čar zůstávají písmena (H, V, ∥ …) jako dosud, ne malé ikonky 20 × 16.
- Vlastní titulek okna pro Windows (R2) není součástí P7.57.
- Klávesa pod popiskem nástroje v paletě je jen v bublině, ne druhým řádkem.

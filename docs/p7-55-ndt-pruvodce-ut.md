# P7.55 – NDT průvodce UT (vydání C, krok 2)

*Součást [plánu nového okna](p7-48-plan-noveho-okna.md); rozhodnutí R1–R7 schválil
autor 6. 11. 2026. Pokračování na pokyn autora „ok, pokračuj P7.55“ (7. 11. 2026).
Vzorem jsou rámy 2c (průvodce, krok 3) a 3d (krok 4 – geometrické pokrytí) v
[`p7-48-navrh-okna/obrazovky/`](p7-48-navrh-okna/obrazovky/).*

## Co se změnilo

- **Karta NDT u UT studie je průvodce o čtyřech krocích:**
  1 Kontrolovaná oblast → 2 Sonda → 3 Přiložení sondy → 4 Geometrické pokrytí.
  - Hotový krok je jeden řádek: zelený kruh s ✓, název, krátké shrnutí („1 plocha“,
    „Úhlová · β 45° · 1 odraz“, „Přiloženo · směr 0°“) a odkaz **Změnit**.
  - Aktivní krok je vnořená karta s ovládáním. Budoucí krok je šedý a říká, co ho
    odemkne („Po přiložení sondy“).
  - Patička: „Krok 3 ze 4“, **Zpět** a **Další: pokrytí** (u posledního kroku
    **Hotovo**). Další jde jen u splněného kroku. Výjimkou je přiložení: když sonda
    není přiložená, jde krok přeskočit, protože Návrh poloh v kroku 4 hledá polohu sám.
  - Krok se **odvozuje ze stavu studie** jen při jejím výběru (oblast a sonda hotové →
    krok 3). Pak zůstává otevřený: přiložená sonda sama nepřeskočí na pokrytí, jako
    v rámu 2c. Nic se neukládá do modelu ani do `okno.json`.
- **Obsah kroků** jsou dosavadní ovládací prvky panelu NDT, jen přeskupené:
  - krok 1: Oblast z výběru, Cílový objem…, Průřez svarem;
  - krok 2: popis sondy, materiál pro UT, Sonda…, Přepočítat úhel, Použít materiál dílu;
  - krok 3: Přiložit sondu sem, Jezdit sondou myší, Směr paprsku, Krok s ◀ ▶, Délka
    čáry, rámeček stavu přiložení (zeleně přiloženo, oranžově/červeně problém),
    sbalitelná *Dráha paprsku*, Projet čáru, Odebrat sondu;
  - krok 4: Zdroj poloh, Krok, citlivost, **pruh pokrytí** (zelená/červená/žlutá
    v barvách 3D mapy) s procenty, citlivostí na krok a větou „Geometrický podíl
    plochy, ne pravděpodobnost nálezu vady.“; Spočítat pokrytí, Export CSV…, Skrýt
    mapu; sbalitelné *Podrobnosti výpočtu*, *Návrh poloh sondy* a *Plán dráhy sondy*.
- **Hlavička karty:** malý titulek „NDT studie ▾“, velký název studie a štítek stavu
  vpravo (✓ platná, ⚠ neúplná, ⚠ zastaralá, ✕ neplatná vazba).
- **Upozornění podle R7:** povinné upozornění metody je v kartě vždy celé doslova
  (12 px, `--fg2`). Odkaz **Celé upozornění** ukáže celé závazné vymezení metody
  (`docs/ndt/04-…`, `20-…`, `22-…`, `24-…`). Aplikace tyto čtyři soubory nově přibaluje.
- **Zastaralá studie** má nahoře oranžový rámeček s tlačítkem **Potvrdit**.
- **Bez vybrané studie** karta nabídne metodu, Novou studii z výběru a návod. Seznam
  studií a jejich správa (Přejmenovat, Metoda, Poznámka, Ověřit, Kopie, Smazat…) jsou
  v sekci *Studie a jejich správa*. Je sbalená, když je studie vybraná.
- **Levá karta v činnosti NDT:** pod prvky je skupina **NDT studie** s ikonou metody,
  názvem a stavem vpravo a s tlačítkem **+**. Klik na studii ji vybere v kartě NDT.
  Výběr v kartě se ukáže i tady. Řádky se při obnově znovu používají (Cocoa AX).
- **Pilulka v panelu NDT:** „● Přiloženo“ (nebo „● Sonda nedosedá“), po výpočtu
  „● Pokryto 43.36 %“.
- **Úzká karta:** řady tlačítek se zalomí na další řádek (`tool_cards.FlowLayout`),
  nabídky se neroztahují podle nejdelší položky. Dlouhé zaškrtávací popisky mají
  závorku v bublině („ověřit odolnost“ → bublina „Posun řádků o ± půl rozteče.“).
- PT, MT a RT mají zatím dosavadní skupiny (průvodce pro ně přinese P7.56). Společné
  jsou hlavička se štítkem, upozornění s odkazem, potvrzení zastaralé studie a levá
  skupina studií.
- Výpočty, `ModelSession`, NDT jádro ani formát souborů (34) se nemění.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_ndt_wizard.py` (8) | odvození kroku a setrvání po přiložení, Další/Zpět/Změnit/Hotovo, přeskočitelné přiložení, nedostupný krok nejde otevřít, jiná studie = nový krok; vymezení metod přibalená ve spec a obsahují povinné upozornění doslova; UT studie: průvodce, doporučený název „Přístupnost UT sondy“, celé `UT_DISCLAIMER`, nadpis a štítek, Celé upozornění; přiložení (rámeček ok, pilulka, Dráha paprsku), Další → krok 4, pruh pokrytí (součet 100 %, procenta, věta o geometrickém podílu), pilulka „● Pokryto …“, Hotovo; MT studie bez průvodce, zastaralá studie s Potvrdit; skupina NDT studie v levé kartě (činnost NDT, oboustranný výběr, znovupoužité řádky); popisky bez závorky |
| `tests/test_gui.py` – NDT | upraveno: skupina sondy je průvodce (`QWidget` s `title()`), dráha paprsku je v `beam_label`, testy návrhu poloh, plánu a objemu nejdřív otevřou krok 4 a sekci |
| testy okna, NDT oken, sestavy, filtrů, náhledů, `test_ndt_scope` (27 souborů, Linux) | 623 úspěšných, 0 chyb; po poslední úpravě výšky stromu znovu 58 dotčených testů; `ruff check src tests` bez nálezů |
| self-test „NDT průvodce“ (Linux Xvfb, 1440 × 900, skutečné 3D) | skutečný klik na studii v levé kartě, ✓ platná, kroky hotovo/hotovo/aktivní/budoucí, přiložení, skutečné kliknutí „Další: pokrytí“, pokryto 43.36 % v pilulce i pruhu, vymezení UT přibalené, obsah karty 304 px se vejde |

Snímky (Linux Xvfb, `examples/ndt/deska.json`, 1440 × 900):
[krok 3 bez sondy](p7-48-snimky/ndt-krok3.png), [přiloženo](p7-48-snimky/ndt-prilozeno.png),
[krok 4 s pokrytím](p7-48-snimky/ndt-pokryti.png).

## Meze

- Rám 2c ukazuje v činnosti NDT prvky stručně („Upínání · Závity · …“) bez ikon. Strom
  prvků zůstává stejný (filtr, výběr a úpravy fungují dál), jen se zkrátí na výšku řádků.
- Karta NDT u UT studie je při 900 px výšky o něco vyšší než pohled. Zbytek se posune
  (pojistka P7.52). Nejvíc místa zabírá celé povinné upozornění, které podle R7 zkrátit
  nejde.
- Rám 2c má zkrácené upozornění. Podle schváleného R7 zůstává celé.
- Na uloženém plánu dráhy (`plan`) se krok 4 počítá jako hotový i bez spočítané mapy.
  Ověření plánu je dál v sekci *Plán dráhy sondy*.
- Pruh pokrytí používá barvy 3D mapy (`ndt.coverage.COLORS`), ne přesné odstíny
  z rámu 3d. Legenda tak odpovídá tomu, co je vidět ve 3D.

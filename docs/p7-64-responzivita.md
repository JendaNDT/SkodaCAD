# P7.64–P7.67 – responzivní okno

*Navazuje na dávku P7.61–P7.63 (PR #134, `a52f73b`, ověřeně vydaná). Pokyn autora
z 8. 11. 2026: „ok, podívej se na ty zbývající rozdíly. Ale nezapomeň, že veškerý design
musí být plně responzivní.“ Jedna dávka podle rozhodnutí „Větší dávky“.*

## Jak se responzivita zkouší

[Skript `p7-64-responzivita.py`](p7-64-responzivita.py) ovládá skutečné okno (Linux Xvfb,
skutečné 3D). Projde sedm rámů návrhu 1a (2a, 2c, 2d, 3a, 3b, 3c, 3d) v pěti velikostech
okna: 960 × 600 (nejmenší povolená), 1024 × 700, 1280 × 800, 1440 × 900 a 1920 × 1080.
U každého snímku hlídá:

- karty, které se překrývají nebo vyčnívají z 3D pohledu;
- obsah širší než karta a příliš zúženou paletu nebo pilulku;
- vodorovné šipky u záložek činností a posuvníky v kartách;
- volnou šířku pro 3D.

Volitelně `QT_SCALE_FACTOR=1.25` napodobí škálování Windows 125 %.

## Výsledek před a po

| | Před (`a52f73b`) | Po (P7.64–P7.67) |
|---|---|---|
| Paleta příkazů | s vodorovným posuvníkem ve všech velikostech do 1280 × 800 | vejde se vždy: nejdřív popisky, pak jen ikony, pak nabídka „»“ |
| Skicář (2d) | paleta se do 960 px nevejde | ikony bez popisků |
| Záložky činností | „Zobrazení“ uříznuté, šipky ‹ › do 1280 px | celé ve všech velikostech, hledání se zúží na „Najít…“ nebo lupu |
| Pilulka (3d) | přetéká přes přepínač pohledů do 1280 px | text zkrácený „…“, celý v bublině; u pokrytí krátká věta o sondě |
| Karta NDT | navigace průvodce pod posuvníkem, posuvník i v 1440 × 900 | navigace (Krok · Zpět · Další) vždy dole na kartě; posuvník jen u obsahu kroku |
| Problémů ve 35 snímcích | 22 | 7 (jen posuvník obsahu karty NDT, viz Meze) |

Srovnání (vlevo před, vpravo po):
[2a model 960 × 600](p7-64-srovnani/960x600-2a-model.png),
[3d pokrytí 960 × 600](p7-64-srovnani/960x600-3d-ndt-pokryti.png),
[2c průvodce 1280 × 800](p7-64-srovnani/1280x800-2c-ndt-pruvodce.png),
[2d skicář 960 × 600](p7-64-srovnani/960x600-2d-skicar.png).

## Co se změnilo

- **P7.64 Paleta.** Karta palety dostane od rozmístění karet volnou šířku (`fit_width`).
  Když se tlačítka nevejdou, ukážou jen ikonu (název je v bublině a pro čtečky). Když ani to
  nestačí, poslední tlačítka se schovají do nabídky „»“ (podnabídky jako *Další prvky*
  zůstanou podnabídkami). Skryté tlačítko i jeho akce dál existují (hledání příkazů,
  oblíbené, zkratky). Totéž dělá paleta skicáře. Výška palety se nemění podle stránky.
- **P7.65 Hlavní lišta.** Záložky činností mají přednost. Pole *Najít příkaz* se podle
  šířky lišty zúží na „Najít…“ a pak na lupu. Zkratka Ctrl+Shift+P funguje vždy.
- **P7.66 Pilulka.** Zpráva se zkrátí na šířku mezi kartami a končí „…“. Celý text je
  v bublině. U spočítaného pokrytí UT ukáže krátkou větu o sondě („Paprsek s 1 odrazem ·
  horní plocha“) místo dlouhého popisu plochy, stejně jako u přiložené sondy (P7.63).
- **P7.67 Karta NDT.** Patička průvodce (Krok N ze 4 · Zpět · Další / Hotovo) je připnutá
  dole na kartě, mimo posouvaný obsah, pro UT, PT, MT i RT. Kroky jsou o něco nižší. Popisek
  „Rozevření (poloviční úhel) [°]“ je kratší („Rozevření [°]“, plný význam v bublině).
- Model, formát souborů (34), `ModelSession` ani výpočty se nemění. Nejmenší velikost okna
  zůstává 960 × 600.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_tool_cards.py` (+3) | paleta: popisky → ikony → nabídka „»“ se stejnými akcemi jako skrytá tlačítka, podnabídka *Další prvky*; skutečné okno 960 × 600 bez posuvníku palety; lišta: záložky celé, hledání full/short/icon; pilulka zkrácená s bublinou |
| `tests/test_ndt_wizard.py` (+1, upravený 1) | patička je dítětem karty mimo posouvanou oblast, sleduje viditelnost průvodce, přepnutí UT → MT vymění patičku, v 1000 × 600 leží uvnitř karty; pilulka u pokrytí |
| `tests/test_gui.py` (upravený 1) | přetečení palety: místo posuvníku ikony a nabídka „»“, příkaz *Upravit prvek* je vidět nebo v nabídce, po ustálení bez posuvníku |
| testy okna (19 souborů, Linux) | 460 úspěšných a 1 starý test posuvníku palety; po jeho úpravě úspěšný; `ruff check src tests` bez nálezů |
| self-test „Responzivita okna“ (nový, Linux Xvfb) | 960 × 600: paleta s nabídkou „»“, hledání „Najít…“; 1280 × 800: ikony, plné hledání; karta NDT v 960 × 600 bez překryvů a s viditelnou patičkou; celý self-test OK |
| skript responzivity (Linux Xvfb, 5 velikostí × 7 rámů) | z 22 nálezů zbývá 7, všechny jsou posuvník obsahu karty NDT |

Self-test „Responzivita okna“ běží i v balíčcích Windows a macOS. Ověří tak šířky se
skutečným písmem obou systémů, které je jiné než v Linuxu.

## Meze a zbývající rozdíly proti návrhu

- **Karta NDT v nízkém okně posouvá obsah kroku.** Při výšce do 800 px (a v 1440 × 900 u
  kroku 4 s mapou) se obsah kroku 3–4 nevejde. Navigace průvodce je ale vždy vidět. Celé
  povinné upozornění UT zůstává v kartě doslovně (R7), proto se karta víc zkrátit nedá.
- Responzivita je ověřená pro 960 × 600 až 1920 × 1080. Menší okno aplikace nedovolí.
- Zbývající rozdíly proti rámům návrhu 1a, záměrné nebo odložené:
  - 2a: popis polohy „4 díry M6“ (aplikace „Upínání · M6 ×4“); sekce *Vlastní průměr*
    není sbalená.
  - 2c: plné upozornění UT (R7) a sbalené sekce *Návrh poloh*, *Plán dráhy* navíc.
  - 2d: přepínač pohledů ve skicáři chybí, popisky vazeb jsou delší.
  - 3a: pole Název v náhledu, hrany jako „Úsečky na horní ploše“ místo „Obvod horní plochy“.
  - 3c: zaškrtávátko „zapnutý (R)“ místo přepínače.
  - 3d: karta s mapou je delší než v návrhu.

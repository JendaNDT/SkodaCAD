# P7.78–P7.80 – karta Geometrické pokrytí UT podle rámu 3d

*Navazuje na vydání [P7.75–P7.77](p7-75-znacky-vazeb-a-strucna-karta.md) (PR #138,
`7d2a236`, ověřeně vydané). Pokyn autora „srovnat kartu s mapou pokrytí NDT“ (9. 11. 2026).
Jedna dávka podle rozhodnutí „Větší dávky“; změna vzhledu ověřená i na responzivitu
(pravidlo z 8. 11. 2026).*

## Co se změnilo

- **P7.78 Rozevření svazku už není v kroku.** Volba *Rozevření [°]* (poloviční úhel
  svazku, 0 = jen osa paprsku) je ve sbalené sekci *Podrobnosti výpočtu*, jako v rámu 3d, kde
  v kroku není. Volba funguje dál a jde do výpočtu stejně jako dřív. Když přepneš zdroj poloh
  na *Z přímé dráhy* (tam je rozevření nutné), sekce se sama rozbalí, aby volba nebyla
  schovaná.
- **P7.79 Procenta s čárkou.** Pruh pokrytí, pilulka dole („Pokryto 46,8 %“) a shrnutí kroku
  píšou jedno desetinné místo a desetinnou čárku, stejně jako PT, MT a RT. Přesná čísla
  (dvě desetinná místa s tečkou) zůstávají v podrobnostech výpočtu, v CSV a v příkazové řádce.
- **P7.80 Kratší věta o citlivosti a tlačítko.** Pod pruhem je citlivost na krok jedna věta
  („Citlivý na krok (3,0 p. b.) – zjemni krok.“, nebo „Nízká citlivost na krok (0,4 p. b.).“).
  Úplný text se stejným významem a povinné upozornění UT zůstávají v podrobnostech. Hlavní
  tlačítko se jmenuje *Spočítat* (celý název *Spočítat pokrytí* je v nabídce a v bublině).
- Výpočet pokrytí, formát souborů (34), `ModelSession` i povinné upozornění UT (R7) se nemění.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_ndt_wizard.py` (+1, upravený 1) | rozevření mimo hlavní formulář a uvnitř podrobností, přepnutí na čáru sekci rozbalí, volba jde do výpočtu; pruh i pilulka s jedním desetinným místem a čárkou; krátká věta citlivosti bez tečky v čísle, úplný text v podrobnostech |
| testy okna, karet, NDT panelu, skicáře, sestavy a schématu (23 souborů, Linux) | viz závěr dávky v PR; `ruff check src tests` bez nálezů |
| self-test (Linux Xvfb, skutečné 3D) | „NDT průvodce“ s pilulkou i pruhem, „Responzivita okna“ i celý self-test OK |
| skript responzivity (5 velikostí × 7 rámů) | 35 snímků, žádný nový nález; zůstává jen známých 7 posuvníků obsahu karty NDT; obsah kroku s pokrytím 871 → 845 px |

Srovnání s návrhem (Linux Xvfb, 1440 × 900):
[3d pokrytí](p7-78-srovnani/3d-ndt-pokryti-srovnani.png).

## Meze a zbývající rozdíly

- **Karta se v 1440 × 900 pořád posouvá** (obsah 845 px, karta 800 px). Povinné upozornění
  UT (R7) je v kartě celé a dvě sbalené sekce *Návrh poloh sondy* a *Plán dráhy sondy* patří
  ke kroku; rám 3d je nemá.
- Tlačítka *Spočítat*, *Export CSV…* a *Skrýt mapu* se na šířku karty (asi 240 px) nevejdou
  do jedné řady; třetí se zalomí. Návrh má dvě tlačítka, protože už nemá *Spočítat*.
- Pruh pokrytí v návrhu ukazuje celá procenta, aplikace jedno desetinné místo.
- Rám 3d má nahoře „UT horní plocha“ a zkrácené upozornění s odkazem; aplikace nese celé
  povinné upozornění (R7).

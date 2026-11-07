# P7.56 – průvodce PT, MT, RT, audit a návrh úpravy (vydání C, krok 3)

*Součást [plánu nového okna](p7-48-plan-noveho-okna.md); rozhodnutí R1–R7 schválil
autor 6. 11. 2026. Pokračování na pokyn autora „ok, pokračuj P7.56“ (7. 11. 2026).
Navazuje na [P7.55](p7-55-ndt-pruvodce-ut.md) – stejný vzor kroků pro ostatní metody.*

## Co se změnilo

- **PT, MT a RT mají stejný průvodce jako UT** (oblast → nastavení → výpočet → mapa):
  - PT: Kontrolovaná oblast → Nastavení PT → Výpočet → Mapa geometrické přístupnosti PT;
  - MT: Kontrolovaná oblast → Materiál a nastavení MT → Výpočet → Mapa geometrické
    proveditelnosti a směrového pokrytí MT (jho je v sekci *Jho na místě*);
  - RT: Kontrolovaná oblast → Nastavení a projekce → Výpočet → Mapa geometrického
    promítnutí oblasti RT (náhled prozařované tloušťky je v sekci).
  - Shrnutí hotových kroků: „5 ploch“, „výchozí – zvoleno pro výpočet“, „Materiál ocel je
    feromagnetický“, „2 projekce“, „Spočítáno“, „Promítne se … 94,9 %“.
  - Nadpis nad kroky je doporučený název metody ze závazného vymezení
    („Přístupnost povrchu pro PT“, „Přiložení jha a směry magnetizace pro MT“, „Geometrie
    projekce RT“). Povinné upozornění metody je dál nahoře celé doslova (R7).
- **Krok Výpočet:** odhad, primární tlačítko Spočítat mapu / projekce a Zastavit. Když
  výpočet doběhne, průvodce sám přejde na mapu.
- **Krok Mapa:** volba „Ukázat ve 3D“, **pruh s procenty stavů** v barvách 3D mapy a věta
  „Geometrický podíl kontrolované oblasti, ne pravděpodobnost nálezu vady.“ Dál jsou tu
  rámeček s důvody místa po kliknutí, Export CSV…, Skrýt mapu a sbalitelné *Podrobnosti
  výpočtu* (dosavadní souhrn). Legenda barev zůstane jen u pohledu na jednu kontrolu nebo
  směr, u celkového pohledu barvy ukazuje pruh.
- **MT:** stav materiálu je v rámečku – zelený u feromagnetického nebo potvrzeného
  materiálu, oranžový u materiálu k potvrzení, červený, když MT nejde. Krok Nastavení je
  hotový jen s vhodným materiálem.
- **RT:** krok Nastavení a projekce je hotový až s aspoň jednou projekcí. Náhled
  prozařované tloušťky má šířku 220 px, aby se vešel do karty.
- Průvodce metody je vidět jen u vybrané studie té metody (dřív zůstávala skupina PT,
  MT nebo RT vidět i u jiné studie, dokud byla spočítaná mapa).
- **Krok se neodvozuje z přechodného stavu** během přepočtu (po otevření dílu se jinak
  PT zasekl na kroku 1). Rozhoduje až hotový stav studie.
- **Karty NDT audit a Konstrukční návrh:** upozornění 12 px `--fg2` (dřív 8 pt),
  primární tlačítko Spustit audit / Spustit návrh, řady tlačítek se zalomí, tabulky
  a nabídky mají šířku karty (`tool_cards.fit_card`, společné s kartou NDT).
- **Výška plovoucí karty** teď počítá i se zalomenými řádky uvnitř posuvné oblasti
  (`FloatingCard.preferred_height`). Dřív byla karta PT/MT nižší než obsah a zbytečně
  se posouvala.
- Výpočty, `ModelSession`, NDT jádro ani formát souborů (34) se nemění.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_ndt_wizard.py` (+4, celkem 12) | PT a MT: čtyři kroky s názvy, doporučený název, `PT_DISCLAIMER`, stav hotovo/hotovo/aktivní/budoucí, shrnutí, „Další: mapa“ až po výpočtu, materiál MT v zeleném rámečku; RT: „2 projekce“, výpočet sám přejde na mapu, pruh (součet 100 %), věta o geometrickém podílu, sbalené podrobnosti; Audit a Návrh: primární tlačítko, upozornění, tabulky v šířce karty; výška karty ≥ zalomený obsah |
| `tests/test_gui.py` – RT | upraveno: náhled 220 px (`PREVIEW_WIDTH`) |
| testy okna, NDT oken, auditu, sestavy, filtrů, náhledů, `test_ndt_scope` (28 souborů, Linux) | 635 úspěšných, 0 chyb; `ruff check src tests` bez nálezů |
| self-test „NDT průvodce“ (Linux Xvfb, 1440 × 900, skutečné 3D) | k dosavadnímu UT přidáno: PT a MT na kapse (kroky hotovo/hotovo/aktivní/budoucí), RT na desce s otvorem (výpočet → mapa s pruhem), obsah karet 318/318/304 px se vejde |

Snímky (Linux Xvfb, 1440 × 900): [PT krok 3](p7-48-snimky/ndt-pt.png),
[MT krok 3](p7-48-snimky/ndt-mt.png), [RT mapa](p7-48-snimky/ndt-rt-mapa.png),
[NDT audit](p7-48-snimky/ndt-audit.png), [Konstrukční návrh](p7-48-snimky/ndt-navrh.png).

## Meze

- Audit a Konstrukční návrh nejsou průvodce po krocích. Mají jen úpravu karty (tlačítka,
  šířka, upozornění), jejich pracovní postup je beze změny.
- Celá povinná upozornění PT/MT/RT jsou delší než u UT. U RT proto karta při 900 px výšky
  na kroku Mapa posouvá (pojistka P7.52).
- Šířku karet se skutečným písmem Windows a macOS ověří až self-test na GitHubu.

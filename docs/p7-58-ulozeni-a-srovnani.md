# P7.58 – uložení stavu okna a srovnání s návrhem (vydání D, krok 2)

*Součást [plánu nového okna](p7-48-plan-noveho-okna.md); rozhodnutí R1–R7 schválil
autor 6. 11. 2026. Pokračování na pokyn autora „ok, pokračuj P7.58“ (8. 11. 2026).
Volitelná průsvitnost karet se nedělá: R1 platí ve schválené podobě „neprůhledné karty“,
zkouška `QOpenGLWidget` by vyžadovala nové rozhodnutí autora.*

## Co se změnilo

- **`~/SkodaCAD/okno.json` verze 2** (`gui/window_state.py`) ukládá podle oddílu
  *State Management* návrhu:
  - činnost hlavní lišty (`activity`: 3D model, Skica, Výkres, Sestava, NDT, Zobrazení),
  - levou kartu (`left_visible`, záložka `left_tab`, sekce `left_sections` na záložce Díl),
  - pravý panel nebo žádný (`panel`),
  - sbalení palety (`palette_collapsed`),
  - **nově rozbalení sekcí pravé karty** (`inspector`): Uložená měření, Příprava kót
    výkresu, Dráha paprsku, Návrh poloh sondy, Plán dráhy sondy, Podrobnosti výpočtu
    UT/PT/MT/RT, Jho na místě a Náhled prozařované tloušťky. Sekce, které okno otvírá
    samo podle stavu (Studie a jejich správa), se neukládají,
  - vzhled (`appearance`), polohu a velikost okna.
- **Verze 1 se načte a převede** na nová jména. Šířky karet (`model_width`,
  `editor_width`) se zahodí – od P7.49 mají karty pevnou šířku podle návrhu. Stránka
  „Soubor“, která už v liště není, se zahodí také. Neznámé nebo chybné hodnoty se
  zahodí jako dřív. Poškozený soubor ani verze 3 otevření okna nezablokují (prázdné
  nastavení). Krok NDT průvodce se neukládá, odvozuje se ze stavu studie.
- *Obnovit rozložení* vrátí i sekce pravé karty do výchozího stavu.
- **Hrany náhledu prvku jsou plně modré #4782d1** jako v rámu 3a (dřív poloprůhledně
  růžové jako u vybraného prvku). Barva jde do OCCT jako sRGB (past P7.48). Vybraný
  hotový prvek zůstává růžový, jak popisuje README.
- Model, formát souborů (34), `ModelSession` ani výpočty se nemění.

## Srovnání osmi rámů (Linux Xvfb, 1440 × 900)

Snímky pořídil [skript](p7-58-srovnani-ramu.py), který okno ovládá jako uživatel. Vlevo
je referenční obrazovka návrhu, vpravo aplikace ve stejném stavu.

| Rám | Srovnání | Shoda | Zbývající rozdíly |
|---|---|---|---|
| 2a Model, světlý | [2a](p7-58-srovnani/2a-model-svetly-srovnani.png) | lišta s činnostmi a hledáním, paleta, levá karta se záložkami a filtrem, pravá karta, pilulka, přepínač pohledů | pravá karta ukazuje celý formulář prvku jen pro čtení (úprava přes *Upravit prvek*, P7.6), návrh má zkrácený inspektor s „Polohy děr · 4“; řádky stromu mají celý popis („Díra „Upínání“ – M6 …“), návrh jen název a „M6 ×4“; pilulka ukazuje „F1: zkratky…“ místo „Vybráno: …“ |
| 2b Model, tmavý | [2b](p7-58-srovnani/2b-model-tmavy-srovnani.png) | tmavé barvy karet, lišty a pozadí 3D podle tokenů | jako 2a |
| 2c NDT průvodce | [2c](p7-58-srovnani/2c-ndt-pruvodce-srovnani.png) | kroky hotovo / aktivní / budoucí, rámeček přiložení, štítek studie, skupina NDT studie vlevo, patička „Krok 3 ze 4 · Zpět · Další: pokrytí“ | plné povinné upozornění UT (R7, záměrně); navíc sekce *Studie a jejich správa* a tlačítka *Přiložit sondu sem* / *Jezdit sondou myší*; ukázkový díl má jednu UT a jednu MT studii |
| 2d Skicář | [2d](p7-58-srovnani/2d-skicar-srovnani.png) | plátno s mřížkou místo 3D, paleta Skica se Zrušit/Hotovo, vazby skici vlevo, karta Výběr s doporučenou vazbou Tečně, pilulka „Zbývá určit“ | meze P7.57: přepínač pohledů je skrytý, štítky vazeb jsou písmena; stav obrysu je v kartě |
| 3a Náhled prvku | [3a](p7-58-srovnani/3a-nahled-prvku-srovnani.png) | řádek náhledu ve stromu, neaktivní paleta, **modré hrany náhledu**, pilulka „● Náhled · Sražení“, patička Esc zahodí · Zrušit · Potvrdit | popis hran je dlouhý („úsečky na horní ploše …“), návrh „Obvod horní plochy“; navíc pole Název a tlačítko Náhled |
| 3b Měření | [3b](p7-58-srovnani/3b-mereni-srovnani.png) | řádky hodnot, zvýrazněná hlavní hodnota, Uložit (primární), sekce Uložená měření se zkratkou, Příprava kót, zelená čára s hodnotou | chybí řádek „Osy rovnoběžné“ (jádro ho nevrací); desetinná tečka; popisek bez zeleného štítku (pád GDI Generic) |
| 3c Řez | [3c](p7-58-srovnani/3c-rez-srovnani.png) | Rovina, Poloha s posuvníkem a rozsahem, Otočit stranu, Export, Plocha řezu se vzorkem barvy, poznámka „jen pohled“ | zapnutí řezu je zaškrtávátko „zapnutý (klávesa R)“ (meze P7.54) |
| 3d NDT krok 4 | [3d](p7-58-srovnani/3d-ndt-pokryti-srovnani.png) | sbalené hotové kroky, aktivní krok 4, pruh pokrytí s legendou a citlivostí, věta o geometrickém podílu, Export CSV, Skrýt mapu | karta je delší (Rozevření, Spočítat pokrytí, plné upozornění) a při 900 px posouvá; ukázková studie má jinou oblast a krok (46,78 %) |

Společné pro všechny rámy:

- Návrh je kreslený pro macOS (semafor, systémová nabídka). Na Linuxu i Windows je
  nabídka v okně a titulek systémový (R2, R3).
- Díl ve 3D je v návrhu jen schematický náčrt. Skutečně ho kreslí OCCT se stávajícími
  barvami (README návrhu, ř. 13), proto se barva a hrany dílu neporovnávají.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_window_state.py` (+1) | verze 2 se zapíše, neznámé sekce a chybné typy zmizí; verze 1 se převede (stránka „Soubor“ a šířky karet zmizí), uložení zapíše verzi 2; verze 3 = prázdné nastavení |
| `tests/test_gui.py` (+1) | skutečné kliknutí na řádky sekcí Měření, uložení, nové okno sekce obnoví (i panel None), *Obnovit rozložení* je vrátí; zavření okna uloží činnost, sbalení palety a sekce levé karty pod novými jmény |
| `tests/test_tool_cards.py` | náhled zapne modré hrany, zrušení je vrátí na barvu vybraného prvku |
| testy okna, karet, náhledů, skicáře, NDT průvodce, stavu okna (12 souborů, Linux) | 268 úspěšných, 0 chyb; `ruff check src tests` bez nálezů |
| self-test „Prostředí CAD“ (Linux Xvfb) | skutečné kliknutí na sekci Příprava kót, `okno.json` má verzi 2 a sekci pravé karty, bez šířek karet |
| self-test „Karty nástrojů“ (Linux Xvfb, skutečné 3D) | hrany náhledu v OCCT mají barvu sRGB #4782d1 bez průhlednosti |
| skript srovnání | všech 8 rámů nafoceno a složeno vedle referencí |

## Meze

- Rozdíly v tabulce výše zůstávají. Největší jsou zkrácený inspektor prvku (2a/2b)
  a krátké názvy ve stromu. Byly by to samostatné kroky nad editorem prvků, P7.58 je
  jen popisuje.
- Šířky karet se už neukládají. Kdo si je ve verzi 1 změnil, dostane šířku z návrhu.
- Průsvitnost a stín karet se nezkoušely (R1).
- Srovnání je jen z Linuxu. Vzhled na Windows a macOS ověřují nativní self-testy
  stažených balíčků.

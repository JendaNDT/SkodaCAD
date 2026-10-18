# NDT – návrh etapy 08: knihovna sond a materiálových profilů (UT)

Stav: **schváleno autorem 18. 10. 2026 („schvaluji etapu 08 včetně doporučení 1–7“);
implementace po krocích ve vývojové větvi.** Co se při implementaci upřesnilo, je
v [oddílu 11](#11-provedení-a-upřesnění).
Výchozí stav: `main`, commit `a141f00` ([PR #21](https://github.com/JendaNDT/SkodaCAD/pull/21)).
Navazuje na [plán, etapa 08](03-implementacni-plan.md), [virtuální sondu (etapa 03)](07-navrh-etapa-03.md),
[model UT paprsku (etapa 04)](09-navrh-etapa-04.md) a [závazné vymezení UT](04-zavazne-vymezeni-ut.md),
které má přednost. Etapa 07 (svar a cílový objem, 07A–07C) je sloučená; Etapa 08 uzavírá
milník **M2 – hodnotitelný UT**.

## Co tato etapa přinese

**Dnes:**

- Sonda se zadává jen čísly v dialogu *Sonda…* (rozměry, výstupní bod, úhel β **přímo
  v materiálu dílu**). Výchozí úhlová sonda 40 × 20 × 25 mm je obecná.
- Vlastní sondu si nejde uložit a použít v jiném modelu – v každé studii se vyplňuje znovu.
- Program nezná rychlost zvuku v materiálu. Materiál dílu slouží jen pro hmotnost.
  Lom podle Snellova zákona umí jen příkazová řádka (`skodacad sonda --snell α,c1,c2`).
- Úhlová sonda má úhel obvykle vyznačený **v oceli** (45°, 60°, 70°). Na hliníku nebo mědi
  je skutečný úhel jiný – program to dnes nijak nehlídá.

**Po etapě 08:**

1. V dialogu *Sonda…* vybereš **profil** z knihovny (např. *Obecná úhlová 40 × 20 × 25 mm,
   70° v oceli*) nebo ze svých sond (*Moje sondy*). Hodnoty se vyplní a dál je jde přepsat.
2. U každé hodnoty je vidět **původ**: *obecný profil*, *změřeno* (např. výstupní bod a úhel
   na kalibračním bloku), *zadáno ručně* nebo *katalog* (jen s uvedeným zdrojem a datem).
3. Vlastní sondu uložíš do **Moje sondy** (soubor ve složce `~/SkodaCAD`, jako nastavení
   AI) a použiješ ji v dalších modelech.
4. Studie UT dostane **Materiál pro UT** se dvěma rychlostmi zvuku a jejich zdrojem: ze
   seznamu (ocel, nerez, hliník, měď, mosaz) nebo vlastní zadané hodnoty.
5. Když úhel sondy platí v oceli a materiál pro UT je jiný, panel **upozorní** a nabídne
   **Přepočítat úhel** ze Snellova zákona (70° v oceli → asi 65° v hliníku, 41° v mědi).
   Sám nic nepřepočítá; přepočet je jeden krok Zpět.
6. Souhrn, CSV a výpis příkazové řádky uvedou profil sondy, původ hodnot, materiál,
   rychlosti a jejich zdroj.

**Co se nemění:** výpočet přiložení, paprsku i pokrytí, závazné vymezení UT a povinné
upozornění, výrobní geometrie a hmotnost. Bez zvoleného profilu a materiálu se program
chová přesně jako dnes (všechny referenční výsledky zůstanou). Formát souboru přejde na
**verzi 17** jen kvůli novým nepovinným položkám; staré soubory se načtou beze změny.

## 1. Rozsah a hranice

- **Jen UT.** Údaje pro RT (zdroj, detektor), MT (jho, póly) a PT přijdou se svými etapami
  11–13. Teď by je nic nepoužilo.
- **Obecné profily bez značek výrobců.** Rozměry jsou orientační („ověř podle své sondy“).
  Konkrétní komerční sonda může být jen uživatelský záznam se zdrojem (katalogový list,
  datum), nikdy vestavěná „certifikovaná“ předvolba.
- **Frekvence a velikost měniče jen informativně**: uloží se a ukážou, výpočet je
  nepoužívá. Rozevření svazku z frekvence a průměru měniče je fyzikální model svazku –
  případně samostatný návrh (rozevření dnes zadáváš ručně jako předpoklad).
- **Měřené × informační údaje:** úhel a výstupní bod skutečné sondy se ověřují na
  kalibračním bloku (blok č. 1 podle EN ISO 2400, pro miniaturní sondy blok č. 2 podle
  EN ISO 7963). Když hodnotu změříš, označíš ji *změřeno* a protokol to tak uvede.
  Program sám nic neměří ani neověřuje.

## 2. Jediný nový výpočet: úhel v jiném materiálu

Předsádka sondy je pořád stejná, takže podle Snellova zákona platí
$\frac{\sin\beta_m}{c_m} = \frac{\sin\beta_{ref}}{c_{ref}}$ (příčná vlna u úhlové sondy).
Úhel v materiálu dílu je tedy

$$\beta_m = \arcsin\left(\frac{c_m}{c_{ref}}\,\sin\beta_{ref}\right)$$

Není potřeba znát úhel ani rychlost v předsádce – stačí rychlost v materiálu, ve kterém je
úhel udaný (obvykle ocel), a v materiálu dílu.

Příklad (orientační příčné rychlosti: ocel 3 240, hliník 3 130, nerez 3 120, měď 2 260,
mosaz 2 120 m/s):

| Úhel v oceli | hliník | nerez | měď | mosaz |
|---|---|---|---|---|
| 45° | 43,1° | 42,9° | 29,6° | 27,6° |
| 60° | 56,8° | 56,5° | 37,2° | 34,5° |
| 70° | 65,2° | 64,8° | 41,0° | 37,9° |

U hliníku a nerezi jde o 2–5°, u mědi a mosazi o desítky stupňů. Proto upozornění,
ale přepočet jen výslovně. Když by $\sin\beta_m \ge 1$, vlna do materiálu nevstoupí:
česká chyba jako dnes u `refract` (totální odraz). Přímá sonda (β = 0°) se nemění.

Pomůcka *Spočítat ze Snellova zákona* (α v předsádce, $c_1$, $c_2$ → β), plánovaná už
v etapě 04, se přidá i do dialogu *Sonda…*.

## 3. Data a jejich původ

### Vestavěné materiálové profily (orientační)

| Materiál | podélná $c_L$ [m/s] | příčná $c_T$ [m/s] | poznámka |
|---|---|---|---|
| ocel (uhlíková, nízkolegovaná) | 5 920 | 3 240 | výchozí referenční materiál úhlu |
| nerez (austenitická) | 5 660–5 920 | 3 120–3 140 | svary austenitu jsou anizotropní – výsledek jen orientační |
| hliník (válcovaný) | 6 320 | 3 040–3 130 | |
| měď | 4 660–4 760 | 2 260–2 330 | |
| mosaz | 4 430–4 700 | 2 110–2 120 | |
| litina | – | – | rozptyl je velký, **bez výchozí hodnoty** – nutno zadat |

Rozpětí ukazují, že se zdroje liší podle slitiny a stavu materiálu. Při implementaci se
každá vestavěná hodnota ověří **aspoň ze dvou zdrojů** a zdroj se zapíše do docstringu
(stejné pravidlo jako u tabulek děr). Zdroje k ověření: tabulky rychlostí
[Evident/Olympus](https://ims.evidentscientific.com/en/learn/ndt-tutorials/thickness-gauge/appendices-velocities),
[materialwelding.com](https://materialwelding.com/ultrasonic-velocity-chart/),
[Engineering ToolBox](https://engineeringtoolbox.com/sound-speed-solids-d_713.html),
[Checkline](https://www.checkline.com/product/Ultrasonic-Thickness-Gauge-Material-Velocities).
Titan, plasty a další materiály se přidají až s ověřenou příčnou rychlostí. Program vždy
uvede, že jde o **orientační** hodnoty a že přesná rychlost se měří na vzorku.

### Vestavěné profily sond (obecné, bez značek)

| Profil | Rozměry [mm] | Výstupní bod | Úhel |
|---|---|---|---|
| Přímá malá | Ø 10 × 25 | střed | 0° (podélná vlna) |
| Přímá | Ø 20 × 30 | střed | 0° (podélná vlna) |
| Úhlová malá (stísněná místa) | 25 × 12 × 20 | 7 od čela | 45° / 60° / 70° v oceli |
| Úhlová standardní (dnešní výchozí) | 40 × 20 × 25 | 12 od čela | 45° / 60° / 70° v oceli |
| Úhlová velká | 50 × 25 × 30 | 16 od čela | 45° / 60° / 70° v oceli |

Rozměry jsou typické řády velikosti, ne konkrétní výrobek. Profil s výchozím úhlem
45° zachová dnešní chování.

### Moje sondy a moje materiály

- Soubor `~/SkodaCAD/ndt-knihovna.json` (verze souboru, seznam sond a materiálů). Každý
  záznam má název, hodnoty, původ každé hodnoty, zdroj (text), datum a poznámku.
- Poškozený nebo chybějící soubor = česká hláška, vestavěné profily fungují dál.
- **Model zůstává soběstačný:** studie si do `device` uloží **kopii hodnot** a odkaz
  na profil (název, verze knihovny). Změna knihovny studii tiše nezmění; panel jen napíše
  „Profil v knihovně se od sondy ve studii liší – převzít?“.

### Formát 17 (jen nepovinné položky)

- `device`: `profile` (název a verze knihovny), `origins` (původ hodnot, např.
  `{"beam_angle": "změřeno"}`), `angle_material` (materiál, ve kterém platí `beam_angle`;
  chybí = přímo v materiálu dílu jako dnes), `wave`, informativní `frequency_mhz`
  a `crystal_mm`.
- Studie: `material` pro UT – odkaz na profil, nebo vlastní `c_l`, `c_t` se zdrojem.
  Chybí = rychlosti neznámé, žádný přepočet. Změna materiálu pro UT ruší mapu a ověření
  studie (jako změna sondy).
- Soubory verzí 1–16 se načtou beze změny. Bez nových položek je výsledek totožný.

## 4. Okno

- **Dialog *Sonda…*:** nabídka *Profil* (vestavěné + Moje sondy). U hodnot je značka
  původu; ruční změna ji přepne na *zadáno ručně*, u úhlu a výstupního bodu jde zaškrtnout
  *změřeno*. Dále nabídka *Úhel platí v materiálu* (ocel / … / přímo v materiálu dílu),
  frekvence a měnič (informativně), tlačítka **Uložit do Mých sond** a **Spočítat ze
  Snellova zákona…**.
- **Panel NDT:** řádek *Materiál pro UT* s výběrem a rychlostmi. Bez volby napíše
  „Materiál pro UT neurčen (díl: hliník)“ a nabídne **Použít hliník (orientační profil)**.
  Když se materiál úhlu a pro UT liší, oranžové upozornění a tlačítko **Přepočítat úhel**.
- Změnu vzhledu ukážu snímkem skutečného okna.

## 5. Výstupy a AI

- Souhrn, CSV a předpoklady: profil sondy a verze knihovny, původ hodnot, materiál úhlu
  a pro UT, rychlosti se zdrojem, případný přepočet (β_ref → β_m), frekvence s poznámkou
  „informativní, výpočet ji nepoužívá“. Povinné upozornění UT beze změny.
- AI asistent rychlosti ani úhly nevymýšlí: smí je brát jen z knihovny nebo od uživatele
  (doplní se do `assistant.RULES`).

## 6. Ověření před předáním

- **Přenos úhlu:** 45° ocel → hliník 43,1°, 70° → 65,2°, 45° → měď 29,6° (vzorcem);
  stejný materiál = beze změny; nadkritický případ = česká chyba; přímá sonda beze změny.
- **Knihovna:** každý vestavěný záznam má jednotky, rozsahy, zdroj a verzi; žádný není
  označený jako ověřený či certifikovaný (test podobný `test_ndt_scope.py`).
- **Formát 17:** načtení verzí 1–16, uložení a načtení, Zpět/Znovu; bez nových položek
  totožné výsledky (deska 85,5 %, V svar 12,2 % a další referenční testy).
- **Moje sondy:** chybějící, poškozený a cizí soubor; uložení; studie si drží kopii.
- **Okno:** offscreen testy a snímek pod Xvfb; GitHub Actions Windows i macOS.

## 7. Malé kroky po schválení

| Krok | Výstup | Ověření |
|---|---|---|
| **08A – jádro bez okna** | `ndt/library.py` (vestavěné profily, kontrola, Moje sondy), přenos úhlu, formát 17, metody `ModelSession`, `skodacad sonda --profil … --material-ut …`, výstupy | testy výpočtu, knihovny, formátu a regrese |
| **08B – okno** | dialog *Sonda…* s profily, původem, Snellovou pomůckou a uložením; *Materiál pro UT*, upozornění a přepočet | offscreen testy, snímek, balíčky Windows/macOS |
| **08C – tvarovaná předsádka (volitelně)** | válcová kontaktní plocha poloměru R pro trubky (osově/obvodově), kterou etapa 03 odložila sem | mezera pod sondou na trubce Ø 114,3 vzorcem |

Každý krok zvlášť: `ruff`, `pytest`, commit; do `main` až na tvůj pokyn.

## 8. Co etapa 08 nebude

- rozevření svazku z frekvence, blízké pole, útlum, citlivost – fyzika svazku a odezvy,
- komerční katalog bez ověřeného zdroje, „certifikované“ předvolby, kalibrace přístroje,
- automatický přepočet úhlu bez souhlasu,
- anizotropie a zakřivené dráhy svazku (austenitické svary),
- zařízení pro RT, MT a PT.

## 9. Praktická zkouška pro autora (po 08B)

Otevři ukázku *deska*, změň materiál dílu na hliník. V *Sonda…* vyber *Úhlová standardní,
70° v oceli* a přilož ji. Panel upozorní na jiný materiál; **Přepočítat úhel** dá asi 65°
a paprsek ve 3D se znatelně sklopí. Ulož sondu do *Mých sond*, otevři jiný model a vyber ji.
Export CSV musí uvést profil, materiál, rychlosti a jejich zdroj.

## 10. K rozhodnutí

1. **Jen UT**, RT/MT/PT zařízení až s jejich etapami. *Doporučeno: ano.*
2. **Moje sondy** v `~/SkodaCAD/ndt-knihovna.json` a kopie hodnot ve studii. *Doporučeno: ano.*
3. **Úhel v jiném materiálu:** upozornit a přepočítat jen tlačítkem, nikdy sám. *Doporučeno: ano.*
4. **Frekvence a měnič jen informativně**, bez výpočtu rozevření svazku. *Doporučeno: ano.*
5. **Tvarovaná předsádka (08C):** až po 08A a 08B, samostatně. *Doporučeno: odložit.*
6. **Formát 17** s nepovinnými položkami. *Doporučeno: ano.*
7. **Vestavěné materiály a sondy** podle oddílu 3; hodnoty ověřit ze dvou zdrojů při
   implementaci, litina bez výchozí hodnoty. *Doporučeno: ano.*

Schválením se **neschvaluje**: fyzikální model svazku, katalog konkrétních výrobků,
nová knihovna Pythonu, změna výpočtu pokrytí ani sloučení do `main`.

## 11. Provedení a upřesnění

- **08A.1 (hotovo):** `ndt/library.py` – vestavěné materiály ocel, nerez, hliník, měď, mosaz
  (rychlosti ověřené 18. 10. 2026 ze dvou zdrojů, zdroje v docstringu i v záznamu), 11 obecných
  profilů sond (přímá Ø 10 a Ø 20, úhlová malá/standardní/velká × 45°/60°/70° v oceli),
  přenos úhlu `transfer_angle` a kontrola `check_angle` (stavy none / ok / differs / unknown /
  error), přepočet jen funkcí `transferred`, popis `describe` pro výstupy, Moje sondy
  (`load_user_library`, `save_user_probe`, `save_user_material`; poškozený soubor se nikdy
  nepřepíše). `Probe` nese nepovinné `profile`, `library`, `origins`, `angle_material`,
  `angle_note`, `wave`, `frequency_mhz`, `crystal_mm`, `source`; bez nich je záznam totožný
  jako dřív. Původ „přepočteno“ přibyl k původům z návrhu.
- **08A.2 (hotovo):** formát **17** (`document.VERSION`), studie smí mít `material` pro UT
  (kontrola `library.Material`, `study.study_material`), README popisuje nové položky. Soubory
  verzí 1–16 se načtou beze změny, uložení zapisuje 17.
- **08A.3 (hotovo):** `ModelSession.ndt_ut_material`, `set_ndt_ut_material` (název vestavěného
  profilu, vlastní záznam nebo None; ruší ověření), `ndt_angle_check`, `apply_ndt_angle_transfer`
  (jeden krok Zpět), `ndt_device_lines`; výsledek pokrytí nese `device_lines` a `ut_material`,
  souhrn i CSV (plochy i objem) je vypíšou. CLI `sonda` a `pokryti`: `--profil`, `--material-ut`,
  `--prepocet-uhlu`, `--knihovna`; ruční `--celo` u profilu změní původ výstupního bodu na
  „zadáno ručně“. AI asistent rychlosti ani úhly nevymýšlí (`assistant.RULES`). Ukázka: deska
  20 mm, 70° v oceli – půlkrok 54,95 mm; materiál hliník a `--prepocet-uhlu` → 65,2°, půlkrok
  43,28 mm (= 20 · tg 65,2°).

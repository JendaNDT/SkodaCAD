# NDT – návrh etap 00 a 01 ke schválení

> Odpověď Claude Code na zadání v `03-implementacni-plan.md`, kap. 10. Zatím **jen návrh**:
> kód se začne psát až po schválení. Nejde o NDT postup ani o tvrzení o detekovatelnosti vad.

Stav: návrh 16. 10. 2026 · větev `ccr-299f2dcb-9w8xc9` (= main po PR #12)

## 1. Etapa 00 – co v programu už je a na co se NDT napojí

Prošel jsem zdrojový kód (ne jen README). Pro NDT jsou důležitá tato rozhraní:

| Co | Kde | Jak to funguje dnes | Co z toho NDT převezme |
|---|---|---|---|
| Soubor modelu | `document.py` | JSON, `VERSION = 12`; každá nová sekce je nepovinná, starší verze se načtou beze změny | nová sekce `ndt`, verze 13 |
| Otevřený model | `session.py` (`ModelSession`) | každá úprava jde přes `_change`: kopie → kontrola → Zpět/Znovu → přepočet; okno nikdy nesahá na geometrii samo | NDT studie se mění jen jeho metodami, Zpět/Znovu funguje samo |
| Přepočet | `rebuild.py` | postaví díl; na konci přepočítá uložená měření (`measure.evaluate`) a jejich výsledek dá do `BuildResult` | stejně: na konci přepočtu se vyhodnotí stav každé studie |
| Pomocný proces | `worker.py` | přepočet běží mimo okno; tvary přes BinTools, ostatní jen čísla a texty (pickle) | výsledek studie = jen čísla a texty, přenese se beze změny |
| Odkaz na plochu | `measure.face_reference`, `reference_for`, `resolve` → `selectors.find_face` | plocha **významem**: bod `at`, směr `normal`, druh (`plane`, `cylinder` …), poloměr; při uložení se ověří, že odkaz najde právě kliknutou plochu | kontrolovaná oblast studie = odkazy na plochy stejného tvaru |
| Paprsek | `measure.RayCaster` | jeden paprsek přes `IntCurvesFace_ShapeIntersector`, první průsečík dál než 1e-4 mm, „koncové echo“ do 60° | v etapě 02 základ geometrických dotazů – **ne** jako fyzikální model UT (zjednodušení tloušťkoměru) |
| Mapa tloušťky | `thickness_map.py` | síť povrchu, tloušťka v těžištích, barvy, CSV; počítá se v pomocném procesu | vzor pro mapu pokrytí (etapa 06) |
| Řez | `section.py` | jen pohled, model se nemění | UT paprsek v řezu (etapa 04–05) |
| 3D prohlížeč | `gui/viewer.py` | díl, zvýraznění, čáry s popisky, barevná síť; self-test kreslí každý druh značky (pozor na ovladač GDI Generic ve Windows) | sonda, paprsek, kolize – každé nové kreslení i do self-testu |
| Materiál | `materials.py` | jen název a hustota | etapa 01 bere název; rychlosti zvuku až v etapě 04/08 |

**Hranice verze 1 (milníky M0–M1):** jeden pevný díl (žádná sestava), výpočty jen geometrické,
rozhodnutí vždy z přesného tělesa OCCT (síť jen pro barevný náhled). Délky v mm (zobrazení na
0,01 mm), úhly ve stupních (na 0,1°). Přesná dovolená mezera pod sondou a krok vzorkování se
navrhnou v etapách 03 a 06 – teď je nezamykám.

## 2. Etapa 00 – osm referenčních dílů

Nová složka `examples/ndt/` (8 modelů). Každý jde postavit, má objem ověřený vzorcem a k němu
**ručně spočítané očekávané výsledky** pro pozdější etapy. Svar je v jednom tělese (díl +
svarový kov dohromady) – hranice úkosu v tělese vidět není, cílový objem svaru přijde v etapě 07.

Společné předpoklady výpočtů: ocel, paprsek = přímka (žádný svazek), úhel β je úhel lomu
v materiálu, půlkrok = t·tg β, dráha k protější stěně = t / cos β. **Virtuální úhlová sonda:**
kvádr 40 × 20 × 25 mm, výstupní bod paprsku 12 mm od čela (zjednodušení, ne katalog).

| # | Soubor | Díl | Objem (vzorec) | Očekávaný výsledek (ručně) |
|---|---|---|---|---|
| 1 | `deska.json` | deska 200 × 100 × t, t = 20 | 200·100·20 = **400 000 mm³** | přímá sonda shora: dráha 20 mm, kolmo; po změně t = 30 → 30 mm a studie „zastaralá“; 45°: půlkrok 20,0 mm, dráha 28,28 mm |
| 2 | `kapsa.json` | blok 120 × 80 × 40, kapsa 40 × 30 hloubka 25 | 384 000 − 30 000 = **354 000 mm³** | ze spodu pod kapsou 15 mm, jinde 40 mm; sonda Ø 20 se na dno kapsy vejde (střed v poli 20 × 10 mm), Ø 32 ne |
| 3 | `zebro.json` | deska 200 × 100 × 20 + žebro 10 × 60 (pro M1) | 400 000 + 60 000 = **460 000 mm³** | pod osu žebra (dno, x = 0) přímým paprskem: výstupní bod musí být ≥ 5 + 12 = 17 mm od osy (čelo u žebra); 45° (20 mm) **ano, rezerva jen 3 mm** – s manipulační rezervou 5 mm už ne; 60° (34,64 mm) ano |
| 4 | `otvor.json` | deska 200 × 100 × 20, díra Ø 20 | 400 000 − π·10²·20 = **393 716,81 mm³** | přímá sonda Ø 10 dosedne celou plochou až ≥ 15 mm od osy díry; paprsek < 10 mm od osy = „žádný materiál“ |
| 5 | `trubka.json` | trubka 114,3 × 6, délka 300 | π/4·(114,3² − 102,3²)·300 = **612 422,07 mm³** | radiálně 6 mm; rovná sonda šířky 20 napříč obvodem nedosedá – mezera u kraje 0,88 mm; obvodový paprsek nad 63,5° (sin β = 51,15 / 57,15) vnitřní stěnu mine |
| 6 | `tupy_svar.json` | 2 plechy t = 12 (300 × 100), V 60°, převýšení 2 mm šíře 20, podkořen 1 mm | 360 000 + 3 400 + 500 = **363 900 mm³** | kořen (x = 0, dno) přímým paprskem shora: čelo sondy musí zůstat mimo převýšení → výstupní bod ≥ 10 + 12 = 22 mm od osy; 45° (12 mm) ne, **60° (20,78 mm) těsně ne – chybí 1,2 mm**, 70° (32,97 mm) ano; mez β ≥ 61,4° |
| 7 | `koutovy_svar.json` | pásnice 200 × 100 × 10, stojina 10 × 80, koutové svary rameno 7 mm z obou stran | 200 000 + 80 000 + 4 900 = **284 900 mm³** | přímá sonda zespodu pod stojinou: rovina styku (z = 10) v hloubce 10 mm; sonda na pásnici jen ≥ 12 mm od osy stojiny (paty svarů); stojina z boku 10 mm |
| 8 | `pristup.json` | deska 200 × 100 × 15, dvě žebra 10 × 50, mezera mezi nimi 30 mm | 300 000 + 100 000 = **400 000 mm³** | sonda 40 × 20 se do mezery vejde jen podélně (vůle 10 mm), napříč koliduje; paprsek napříč mezerou proto nejde, podél žeber ano; zespodu volně, dráha 15 mm (pod mezerou) |

Díly 3 a 6 jsou schválně na hraně: výsledek se překlopí podle manipulační rezervy a úhlu – na nich se v etapách 03–04 ověří, že program hlásí správnou stranu hranice.

Očekávané výsledky budou v `docs/ndt/05-referencni-dily.md` (vzorce, obrázek, kdo je potvrdil).
Test hlídá: díl jde postavit, je platný (`is_valid`), objem podle vzorce, a kde to jde už dnes,
i rozměry (např. tloušťka desky 20 mm, stěna trubky 6 mm).

## 3. Etapa 01 – NDT studie v souboru modelu

### 3.1 Jak to bude vypadat v JSON (formát verze 13)

```json
"ndt": {
  "studies": [
    {
      "id": "s1",
      "name": "UT desky shora",
      "method": "UT",
      "target": {"kind": "faces",
                 "faces": [{"face": {"at": [0, 0, 20], "normal": [0, 0, 1], "type": "plane"}}]},
      "note": "",
      "created": "2026-10-16",
      "part": "3f9a1c0b7d2e4a65",
      "verified": {"by": "J. N.", "date": "2026-10-16", "part": "3f9a1c0b7d2e4a65"}
    }
  ]
}
```

| Pole | Význam |
|---|---|
| `id`, `name` | jedinečné id a název studie |
| `method` | `UT`, `PT`, `MT` nebo `RT` – společné jádro počítá se všemi čtyřmi |
| `target` | kontrolovaná oblast; v etapě 01 jen `"kind": "faces"` (plochy významem, jako u měření). Objem a svar (`volume`, `weld`) přidá etapa 07 |
| `note` | poznámka (zadání, předpoklady) |
| `created` | datum založení (do protokolu) |
| `part` | **otisk dílu**, ke kterému byla studie naposledy nastavena nebo potvrzena |
| `verified` | nepovinné odborné ověření (kdo, kdy, pro jaký otisk dílu) |

Zařízení, nastavení metody a materiálový profil (rychlosti zvuku) **teď nepřidávám** – byla by to
prázdná pole. Přibudou v etapách 03, 04 a 08, každá se zvýšením verze formátu. Materiál studie
je zatím materiál dílu. Sekce `ndt` je samostatná: nepřidává prvky, nemění těleso.

**Výsledky se neukládají** – stav studie se spočítá při každém přepočtu (jako uložená měření).

### 3.2 Otisk dílu a „zastaralá“ studie

Otisk = krátký kontrolní součet (SHA-256, 16 znaků) z **parametrů, prvků a materiálu**. Při
každém přepočtu se spočítá znovu a porovná s `part` ve studii. Vědomě volím otisk z receptu, ne
z tvaru: změna polohy díry nemění objem ani rozměry, ale otisk ano. Jen přejmenování prvku se
nepočítá. Raději zbytečné „zastaralá“ než tiché „platná“.

Stavy studie (počítané, ne uložené):

| Stav | Kdy | Co uvidíš |
|---|---|---|
| **platná** | otisk sedí a všechny plochy se našly přesně | ✓ |
| **zastaralá** | díl se od nastavení studie změnil | ⚠ „díl se změnil – zkontroluj a potvrď“; u plochy, která se posunula, i o kolik (např. „horní plocha se posunula o 10 mm“) |
| **neúplná** | chybí kontrolovaná oblast | ⚠ „vyber kontrolovanou oblast“ |
| **neplatná vazba** | plocha na dílu už není, nebo díl nejde postavit | ✕ česká zpráva, co zmizelo |

Ověření (`verified`) platí jen pro otisk, pro který se dalo. Po změně dílu se ukáže „ověření
neplatí – díl se od ověření změnil“. Jakákoli úprava studie ověření smaže. Zpět vrátí i stav:
změníš parametr → studie zastaralá → Zpět → zase platná.

### 3.3 Úpravy přes `ModelSession` (každá = jeden krok Zpět)

`add_ndt_study(method, shapes, point, name)` · `rename_ndt_study` · `set_ndt_method` ·
`set_ndt_target(shapes, point)` · `set_ndt_note` · `confirm_ndt_study` (potvrdit pro aktuální díl)
· `verify_ndt_study(by)` / `unverify_ndt_study` · `duplicate_ndt_study` · `remove_ndt_study` ·
`ndt_studies` (stavy z posledního přepočtu). Výběr z rozříznutého dílu se převede na celý díl jako
u měření.

### 3.4 Soubory

| Soubor | Změna |
|---|---|
| `src/skodacad/ndt/__init__.py` | nový balíček NDT, text upozornění „předběžné posouzení…“ |
| `src/skodacad/ndt/study.py` | kontrola struktury, otisk dílu, nová studie, vyhodnocení stavu (`StudyResult`), popis |
| `document.py` | pole `ndt`, `VERSION = 13`, verze 1–12 se načtou beze změny |
| `rebuild.py`, `worker.py` | `BuildResult.ndt` – stavy studií, přenos z pomocného procesu |
| `session.py` | metody z 3.3 |
| `cli.py` | `skodacad build` vypíše stavy studií (i s `--set`) |
| `assistant.py`, README | popis sekce `ndt` ve formátu; AI ji mění jen na výslovné přání a výsledky NDT nevymýšlí |
| `gui/ndt_panel.py` *(volitelné)* | panel NDT: seznam studií se stavem, nová z výběru, přejmenovat, metoda, oblast z výběru, potvrdit, ověřit, duplikovat, smazat; klik na studii zvýrazní plochy; upozornění nahoře |
| `examples/ndt/*.json` | 8 referenčních dílů (každý s ukázkovou studií), v menu Ukázky → NDT, přibalené do exe |
| `docs/ndt/05-referencni-dily.md` | očekávané výsledky ručně |
| CLAUDE.md | rozhodnutí, architektura, pasti |

### 3.5 Testy

- `tests/test_ndt_examples.py` – 8 referenčních dílů: postavit, `is_valid`, objem podle vzorce,
  rozměry, které jdou změřit už dnes.
- `tests/test_ndt_study.py` – staré modely (v1–12) se načtou; uložit → načíst = totéž; chybná
  struktura = česká chyba; otisk se nemění přejmenováním prvku, mění se parametrem, prvkem i
  materiálem; stavy platná / zastaralá / neúplná / neplatná vazba; posunutá plocha hlásí posun;
  Zpět/Znovu; ověření zmizí po úpravě a neplatí po změně dílu; výběr z řezu; pomocný proces;
  příkazová řádka.
- `tests/test_gui.py` *(s panelem)* – každá akce panelu opravdu stisknutá; self-test okna.

### 3.6 Postup po malých krocích (každý = ruff + pytest + commit)

1. Referenční díly + test objemů + `05-referencni-dily.md` (etapa 00).
2. `ndt/study.py` + formát v13 + přepočet + pomocný proces + testy.
3. `ModelSession` + Zpět/Znovu + příkazová řádka + testy.
4. *(volitelné)* panel NDT v okně + testy + snímek okna.
5. README, CLAUDE.md, popis pro AI, Windows sestavení (obě úlohy zelené).

**Ukázka na konec („klikni, nastav, pozoruj“):** otevři Ukázky → NDT → Deska, v panelu NDT je
studie „UT desky shora“ ✓ platná. Změň parametr t na 30 → ⚠ zastaralá, „horní plocha se
posunula o 10 mm“. Ctrl+Z → zase ✓. Bez okna totéž: `skodacad build examples/ndt/deska.json
--set t=30`.

## 4. Co v etapách 00–01 nebude

Žádné simulace signálů, žádný výpočet pokrytí ani paprsku sondy (to je etapa 02+), žádná změna
konstrukční geometrie, žádná AI jako zdroj čísel. Slovo „kontrolovatelné“ se nepoužije bez
vymezení.

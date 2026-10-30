# P5.4 — kontroly sestavy: implementace a ověření

**Stav: implementováno podle schváleného návrhu [P5.4](p5-4-navrh-kontrol.md)
(K1–K12, autor 30. 10. 2026: odpověď „K1–K12“).** P5.4A je jádro (formát 31, kolize, vůle,
kusovník, export STEP, sezení, příkazová řádka, ukázka), P5.4B okno (panel *Kontrola
sestavy*, výpočet v pomocném procesu, self-test). Ruční zkouška a přijetí P5 (P5.5) zůstávají
na autorovi.

## Co přibylo

| Soubor | Co dělá |
|---|---|
| `document.py` | `VERSION = 31`; díly se dál ukládají v nejnižší potřebné verzi (24–28) |
| `assembly.py` | `Checks` (`clearance`, výchozí 0,5 mm; `accepted`) a `Accepted` (`a`, `b` = cesty id, `volume`, `note`; dvojice bez ohledu na pořadí); neznámý klíč, nekladná mez, prázdná cesta, stejná komponenta, záporný objem, zdvojené přijetí = česká chyba; `checks` ve verzi pod 31 = chyba; uloží se 31 jen s neprázdnými `checks`, jinak 30 / 29 jako dosud |
| `assembly_build.py` | `Instance.base` (tvar dílu bez polohy – pro STEP), `AssemblyResult.locations` (poloha každé komponenty i podsestavy) |
| `assembly_check.py` (nový) | `check`: síto obalových kvádrů (s rezervou meze vůle), přesný **nedestruktivní** průnik (`ndt.geometry._common` – kopie sdílí tvar), kolize nad 0,001 mm³ s objemem a těžištěm průniku, nespočítaný průnik / vzdálenost = „nelze ověřit“, vzdálenost do 1·10⁻⁶ mm = dotyk, vůle pod mezí; `with_accepted` přehodnotí nálezy podle přijatých kolizí bez nového výpočtu (změna nad 1 %, nejméně 0,01 mm³ = znovu kolize; přijatá, která zmizela, se ohlásí); `bill` + `write_bill` (rozbalený kusovník po souborech dílů, CSV se středníkem, UTF-8 s BOM, desetinná čárka, materiál česky); `export_step` (XCAF: výrobek = soubor dílu jednou, kopie = id s polohou, podsestava = vnořená sestava, názvy bez diakritiky, jednotky mm, při chybě zůstane starý soubor) |
| `assembly_session.py` | `set_clearance`, `accept_collision`, `unaccept_collision` (každé jeden krok Zpět); smazání komponenty smaže i její přijaté kolize; `check`, `check_key`, `store_check` (výsledek z pozadí se převezme jen pro nezměněnou sestavu), `last_check` (pohled: po změně dílů, poloh nebo meze neplatí), `bill`, `write_bill`, `export_step` (jen úplná sestava) |
| `worker.py` | úloha `assembly_check` (`submit_assembly_check`): sestava se v pomocném procesu postaví ze souborů a zkontroluje, průběh po dvojicích |
| `cli.py` | `skodacad sestava --kontrola [--vule 0,2] --kusovnik k.csv --export s.step`; kód 1 při nepřijaté kolizi nebo nálezu „nelze ověřit“ |
| `examples/sestavy/deska_se_sroubem.json` + `dily/deska_m3.json`, `dily/sroub_m3x10.json` | deska 40 × 30 × 6 (hliník) s dírou M3 skrz, šroub ISO 4762 M3 × 10 dvěma vazbami (souosost, dotyk hlavy), mez vůle 0,3 mm, přijatá kolize 12,959 mm³ „závit M3 – díra je jen vrták pod závit (2,5 mm)“ |
| `gui/assembly_window.py` | dolní panel *Kontrola sestavy*: záložka *Kolize a vůle* (mez vůle, *Zkontrolovat kolize a vůle* F7 na pozadí, *Zastavit*, tabulka nálezů, klik = obě kopie zvýrazněné a kulička ve středu průniku, *Přijmout kolizi…* s poznámkou, *Zrušit přijetí*, upozornění na NDT), záložka *Kusovník* (tabulka, *Uložit kusovník CSV…*), *Soubor → Exportovat STEP…*, nabídka *Kontrola* |
| `gui/app.py` | self-test „✓ Kontrola sestavy: přijatá kolize 12,959 mm³, kusovník 2 řádky, STEP …“ |
| `tests/p35_cross_os.py` | sestava přenášená mezi Windows a macOS má mez vůle (formát 31) a překrytou kopii; druhý systém musí dostat stejné nálezy a objem kolize (21 000 mm³) |
| `README.md` | návod *Kontrola sestavy*, oddíl formátu „Kontroly sestavy (`checks`, verze 31)“ (čte ho i AI asistent), příkaz `skodacad sestava --kontrola …` |

## Ověření (matice C01–C20)

Testy: `tests/test_assembly_checks.py` (C01–C19), `tests/test_assembly_gui.py` (C20).

| Č. | Test | Výsledek |
|---|---|---|
| C01 | `test_c01_…` | obě dosavadní ukázky (verze 29 a 30) se uloží ve stejné verzi a bez `checks` |
| C02 | `test_c02_…` | mez 0,25 + přijatá kolize: verze 31, uložený `checks` totožný, po otevření stejná sestava, ne neuložená |
| C03 | `test_c03_…` (11 případů) | verze 32, `checks` ve verzi 30, neznámý klíč v `checks` i v přijetí, mez −1 a `true`, cesta jako text a prázdná, stejná komponenta, záporný objem, zdvojené přijetí – vše česká chyba |
| C04 | `test_c04_…` | kvádry 20 mm s překryvem 5 mm: kolize **2 000 mm³** (5 × 20 × 20), těžiště průniku (17,5; 10; 10) |
| C05 | `test_c05_…` | kvádry na dotyk: žádný nález, 1 dotyk, „bez kolize“ |
| C06 | `test_c06_…` | mezera 0,3 mm: s mezí 0,5 „vůle 0,3 mm“, s mezí 0,2 nic (dvojice ani neprojde sítem) |
| C07 | `test_c07_…` | ukázka krabičky s vazbami: 15 dvojic, 5 po sítu, 5 dotyků, žádný nález |
| C08 | `test_c08_…` | šroub v díře pod závit: kolize = π (1,5² − 1,25²) · 6 = 12,959 mm³ (relativně 1·10⁻⁶); přijetí = jeden krok Zpět, výsledek se přehodnotí bez výpočtu, Zpět vrátí kolizi |
| C09 | `test_c09_…` | deska 8 mm místo 6: objem 17,279 mm³ → „objem se změnil z 12,959 mm³“, znovu kolize |
| C10 | `test_c10_…` | přijatá kolize, která zmizela: hlášení „už není“, sestava bez kolize |
| C11 | `test_c11_…` | smazání šroubu smaže přijatou kolizi i vazby, mez 0,3 zůstane (verze 31); Zpět vrátí přijetí |
| C12 | `test_c12_…` | kvádr v podsestavě posunuté o 10 mm proti kvádru sestavy: kolize 4 000 mm³, cesta `("pod", "k")`, popis „pod / k“ |
| C13 | `test_c13_…` | chybějící díl: kontrola, kusovník do souboru i STEP odmítnuty česky, žádný soubor nevznikne |
| C14 | `test_c14_…` | náhradní průnik, který jádro nespočítá: „nelze ověřit … kolizi nelze vyloučit“, nikdy „bez kolize“ |
| C15 | `test_c15_…` | kusovník ukázky: 3 řádky (krabička, víčko, nožička), kusy 1 / 1 / 4, objem nožičky π · 5² · 3, id komponent, součet hmotností = hmotnost sestavy; díl s NDT studiemi je má ve sloupci |
| C16 | `test_c16_…` | CSV: UTF-8 s BOM, středník, nadpis, upozornění NDT, řádek nožičky, hmotnosti s desetinnou čárkou, řádek „Celkem“ 6 kusů |
| C17 | `test_c17_…` | STEP ukázky zpět přes XCAF: kořen „Krabicka s vickem a vazbami“, kopie krabicka, vicko, nozicka_1…4, výrobek `nozicka` zapsaný jednou, objem (relativně 1·10⁻⁶) a obálka (1·10⁻⁴ mm) totožné; `ascii_name` |
| C18 | `test_c18_…` | podsestava ve STEP: `pod` je vnořená sestava s kopiemi k1, k2; objem 3 × 8 000 mm³, posun 50 mm zachovaný |
| C19 | `test_c19_…` | `skodacad sestava … --kontrola --kusovnik --export`: výpis přijaté kolize, „Kusovník (2 řádky, 2 kusy)“, soubory vzniknou; kolize = kód 1; `--vule 0,5` → „Malá vůle … 0,3 mm“ |
| C20 | `test_c20_…` (okno, 3 testy) | *Zkontrolovat* → „Přijatá kolize / Deska × Šroub M3 × 10 / 12,959 mm³“; klik na nález: zvýrazněné kopie a kulička v (0; 0; 3); *Zrušit přijetí* a *Přijmout kolizi…* s poznámkou, každé jeden krok Zpět; mez 0,5 → výsledek neplatí, Zpět → zase platí; kusovník 2 řádky, 20,42 g, uložení CSV a export STEP z nabídky; neúplná sestava má tlačítka vypnutá a akce hlásí česky; **na pozadí**: změna polohy během kontroly → výsledek se nepřevezme („během kontroly změnila“), druhá kontrola doběhne, *Zastavit* |

Skutečné okno pod Xvfb: self-test `VÝSLEDEK: OK` včetně „✓ Kontrola sestavy: přijatá kolize
12,959 mm³, kusovník 2 řádky, STEP … (53 521 B)“; snímky okna s vybranou kolizí a s kusovníkem.

V cloudu (změna `worker.py` = společné jádro podle pravidla 6): úplná sada **1 941 testů**
prošla (22:43 min), `ruff check src tests` bez chyb.

## Co se při implementaci ukázalo (a je opravené)

- `build123d.export_step` u kopií sdílejících tvar zapsal všem stejné jméno a češtinu
  rozbil na nesmyslné znaky. Proto vlastní zápis přes XCAF a jména bez diakritiky (K8).
- Zapisovač STEP vypisoval do konzole hlášky OCCT – ztlumené na úroveň chyb.
- Kusovník ukazoval vnitřní klíč materiálu („hlinik“) – teď český název jako v okně dílu.
- Výsledek kontroly z pomocného procesu se mohl přiřadit sestavě, která se mezitím změnila –
  teď se převezme jen se stejným klíčem (díly, polohy kopií, mez vůle) jako při spuštění.

## Omezení a zbývá

- Vůle uvnitř dvojice, která se jinde dotýká (lem víčka 0,3 mm od stěny krabičky), se
  nehlásí – nejmenší vzdálenost dvojice je 0 (dotyk). Hledání místních vůlí by chtělo
  porovnávat plochy po jednotlivých dvojicích; v K2 to není.
- Průnik se ve 3D ukazuje jen kuličkou v jeho těžišti, ne tvarem průniku.
- Rychlost: síto obálek vyřadí vzdálené dvojice; u ukázek trvá kontrola desetiny sekundy.
  Velké sestavy (stovky kopií) zatím změřené nejsou.
- Ruční zkouška na Windows a Macu (kontrola, přijetí, kusovník v Excelu, STEP v jiném CADu)
  a přijetí P5 (P5.5) jsou na autorovi.

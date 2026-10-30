# P5.4 — návrh kontrol sestavy: kolize, vůle, kusovník, export, vymezení NDT

**Stav: schváleno autorem 30. 10. 2026** odpovědí **„K1–K12“** na žádost o schválení
doporučených variant (návrhové [PR #67](https://github.com/JendaNDT/SkodaCAD/pull/67));
opravňuje implementovat P5.4A a P5.4B. `src/` se tímto krokem nemění. Vychází z `main` /
`65c3e21` (sloučené vazby P5.3, [PR #65](https://github.com/JendaNDT/SkodaCAD/pull/65)), z bodu
P5.4 [roadmapy](roadmapa-vyvoje.md#p5--sestavy) („kolize a vůle, kusovníkový základ a export;
vymezit působení NDT mezi komponentami, nepřenášet automaticky závěry z jednoho dílu na
sestavu“) a z rozhodnutí P5.1: S9 (export a kontroly jen z úplné sestavy), S11 (NDT patří
dílu) a S12 (průniky kopií jen nedestruktivně).

## 1. Co to autorovi přinese

- Jedno tlačítko řekne, **které díly do sebe zasahují** (a kolik mm³), které se **dotýkají**
  a kde je mezi díly **mezera menší než zvolená vůle** (např. 0,5 mm pro 3D tisk).
- Záměrný přesah – šroub v díře pod závit (závit je jen vyznačený) – jde **přijmout
  s poznámkou**; ozve se znovu, až se změní.
- **Kusovník**: co a kolikrát v sestavě je, z jakého materiálu a kolik to váží; uložit do CSV.
- **Export celé sestavy do STEP** se stromem dílů pro jiné CAD programy.
- Jasná hranice NDT: studie dílu platí jen pro samotný díl, v sestavě se nic nepřepočítává.

## 2. Rozhodnutí ke schválení K1–K12

| Rozhodnutí | Doporučená varianta | Důsledek / alternativa |
|---|---|---|
| **K1 Kolize** | Zkouší se každá dvojice kopií dílů (i uvnitř podsestav). Nejdřív levné síto podle obalových kvádrů, pak přesný průnik jádrem **nedestruktivně** (`ndt.geometry.overlap`, S12). **Kolize = objem průniku nad 0,001 mm³** (stejná mez jako „dotyk není kolize“ u NDT). Průnik, který jádro nespočítá, je **„nelze ověřit“** – nikdy „bez kolize“. | Dotyk ploch (víčko na okraji) kolize není (průzkum K1, K2: 0 mm³). Překryv kvádrů o 5 mm = 2 000 mm³ přesně podle vzorce. |
| **K2 Vůle** | U dvojic bez kolize, jejichž obalové kvádry jsou blíž než mez, se spočítá **nejmenší vzdálenost** těles. Hlásí se **0 < vzdálenost < mez vůle** (výchozí **0,5 mm**, zvoleno). Vzdálenost do 0,000001 mm = **dotyk** (jen počet, není to vada). | Mezera 0,3 mm mezi kvádry = přesně 0,3000 (K2). **Omezení:** měří se nejmenší vzdálenost celé dvojice – vůle lemu víčka 0,3 mm se nehlásí, protože se víčko o krabičku jinde opírá (K1: vzdálenost 0). Vůle „v místě“ je pozdější krok (měření v sestavě). |
| **K3 Přijatá kolize** | Záměrný přesah jde **přijmout s poznámkou** (např. „závit M3“). Uloží se dvojice a objem průniku. Když se objem změní o víc než 1 % (nejméně 0,01 mm³), je to **znovu kolize**; přijatá kolize, která zmizela, je upozornění. Přijetí i zrušení = jeden krok Zpět; smazání komponenty smaže i její přijetí. | Šroub Ø 3 v díře Ø 2,5 v desce 6 mm: průnik 12,9591 mm³ = π·(1,5² − 1,25²)·6 přesně (K3). Bez přijetí by každý šroub svítil napořád. Alternativa: přijetí neukládat (po otevření sestavy znovu červené). |
| **K4 Formát 31** | Sestava dostane nepovinné `checks`: `{"clearance": 0.5, "accepted": [{"a": ["sroub_1"], "b": ["deska"], "volume": 12.959, "note": "závit M3"}]}`. Komponenta je **cesta id** (seznam – i v podsestavě). Bez `checks` zůstává sestava ve verzi 29 nebo 30. Neznámý klíč = chyba. | Starší aplikace soubor s přijatými kolizemi odmítne („stáhni aktuální aplikaci“), místo aby je tiše zahodila. Výsledky kontroly se neukládají (jsou pohled). |
| **K5 Kdy se počítá** | **Na tlačítko** (*Zkontrolovat*) a v příkazové řádce, ne po každé změně. Výsledek je pohled: každá změna sestavy nebo dílu ho zneplatní. V okně běží v **pomocném procesu** s odhadem (počet dvojic po sítu) a *Zastavit*; příkazová řádka počítá hned. | Ukázka krabičky: 5 kandidátů z 15 dvojic, 0,7 s (K1). Přesný průnik víčko × víčko 93 ms; 40 překrývajících se víček (780 dvojic) by trvalo asi 73 s – proto ne automaticky a ne v hlavním vlákně (K4). |
| **K6 Kusovník** | **Rozbalený** (i díly z podsestav), řádek = **soubor dílu**. Sloupce: pozice, název dílu (ze souboru), soubor (cesta vůči sestavě), kusy, materiál, hmotnost 1 ks a celkem, objem 1 ks, id komponent, **NDT** (počet studií v dílu s poznámkou „platí jen pro díl“). Pořadí = první výskyt v sestavě. Neznámá hustota = „?“ a celková hmotnost neznámá. | Ukázka: krabička 1 ks 26,73 g, víčko 1 ks 11,84 g, nožička 4 ks po 0,30 g (K5). Stejný díl v jiném souboru je samostatný řádek (předvídatelné). Strukturovaný kusovník po úrovních je pozdější krok. |
| **K7 Export kusovníku** | CSV (středník, UTF-8 s BOM jako ostatní CSV aplikace) – **jen z úplné sestavy** (S9). V okně se neúplný kusovník ukáže s nápisem „NEÚPLNÝ – chybí N komponent“. | Excel ho otevře s češtinou. |
| **K8 Export STEP** | **Jen úplná sestava.** Strom XCAF: kořen = sestava, **výrobek = soubor dílu** (zapsaný jednou, kopie ho sdílí), **kopie = id komponenty** s polohou, podsestava = vnořená sestava; jednotky mm. Názvy ve STEP **bez diakritiky** (přepis „Víčko“ → „Vicko“). Nepřijatá kolize export nezastaví, jen upozorní. | Běžný export build123d dal všem čtyřem nožičkám jméno „nozicka_4“ a rozbil češtinu (K6). Vlastní zápis zachová jména kopií a díl uloží jednou (K7: 213 kB, 0,02 s, objem i obálka zpět totožné). OCCT umí češtinu v UTF-8 zapsat i přečíst, norma STEP ale počítá s jiným kódováním – jiný CAD by mohl ukázat nesmysl. STL/3MF/GLB celé sestavy později. |
| **K9 Vymezení NDT** | V sestavě se **nic NDT nepočítá** a výsledky studií dílu se **nikdy nevydávají za výsledek sestavy** (S11): sousední díl může sondě, jhu nebo zdroji zavazet. Kusovník u dílu ukáže, kolik má studií, s poznámkou „platí jen pro díl samotný“; panel kontroly a README to řeknou. NDT v sestavě (sousední díly jako překážky) je **samostatný pozdější návrh**. | Splní bod roadmapy „nepřenášet automaticky závěry z dílu na sestavu“. |
| **K10 Okno** | Panel *Kontrola sestavy*: *Zkontrolovat*, mez vůle, tabulka nálezů (kolize červeně, nelze ověřit šedě, vůle žlutě, přijaté kolize), klik = zvýrazní obě komponenty a **ukáže průnik** ve 3D; *Přijmout kolizi…* s poznámkou, *Zrušit přijetí*. *Kusovník…* (tabulka, *Uložit CSV…*), *Export STEP…* v nabídce *Soubor*. | Stejné ovládání jako mapy NDT (výpočet na pozadí, klik do tabulky). |
| **K11 Příkazová řádka** | `skodacad sestava soubor.json --kontrola [--vule 0,3]`, `--kusovnik kusovnik.csv`, `--export sestava.step`. Kód 1 při neúplné sestavě nebo nepřijaté kolizi (s `--kontrola`). | Kontrola jde spustit i bez okna (a v testech). |
| **K12 Co P5.4 neřeší** | Pružnost, deformace, montážní postup, výrobní tolerance; vůle „v místě“ uvnitř dvojice, která se jinde dotýká; přesah počítaný ze skutečného závitu (závit je vyznačený); kolize s NDT pomůckami; export STL/3MF/GLB sestavy; kusovník po úrovních. | Vše jsou pozdější samostatné kroky. |

Ukázka zápisu (formát 31):

```json
"checks": {
  "clearance": 0.3,
  "accepted": [
    {"a": ["sroub_1"], "b": ["deska"], "volume": 12.959, "note": "závit M3 – díra pod závit"}
  ]
}
```

## 3. Co potvrzuje současný kód

- `ndt.geometry.overlap` počítá objem průniku nedestruktivně (průzkum P4 v P5.1: výchozí
  průnik zapisoval do sdílených hran zdroje) a nespočítaný průnik vrací `None` – rozhodnutí
  K1 ho převezme beze změny.
- `AssemblyResult.instances` drží každou kopii v poloze i s cestou id (`ids`), souborem,
  materiálem, objemem a hmotností – kusovník i kontrola z nich vychází.
- `AssemblySession._change` (jeden krok Zpět, kontrola struktury) přijme přijetí kolize
  stejně jako vazbu; `remove` už maže vazby smazané komponenty, přidá se mazání přijetí.
- Pomocný proces (`worker.py`) už počítá dlouhé úlohy NDT na pozadí se *Zastavit*; kontrola
  sestavy bude další úloha stejného druhu.

## 4. Průzkum

Jednorázový průzkum, **ne test projektu**: [`p5-4-pruzkum-kontrol.py`](p5-4-pruzkum-kontrol.py),
cloud Linux, build123d 0.13.0. Díly: ukázka *Krabička s víčkem a vazbami* a zkušební tělesa.

| Č. | Případ | Výsledek | Závěr |
|---|---|---|---|
| K1 | Ukázka, 6 komponent = 15 dvojic | síto obálek nechalo 5 dvojic (krabička × víčko a × 4 nožičky), průnik všude 0 mm³, vzdálenost 0 (dotyk); celkem 0,7 s, krabička × víčko 50 + 154 ms | K1, K2, K5; vůle lemu 0,3 mm se v nejmenší vzdálenosti neprojeví (K2 omezení) |
| K2 | Kvádry 20 mm: překryv 5 mm / dotyk / mezera 0,3 mm | 2 000 mm³ (= vzorec) / 0 mm³ a vzdálenost 0 / 0 mm³ a vzdálenost 0,3000 | K1, K2 |
| K3 | Šroub Ø 3 v díře pod závit Ø 2,5, deska 6 mm | 12,9591 mm³ = π·(1,5² − 1,25²)·6 | K3 (přijatá kolize) |
| K4 | 40 víček na stejném místě (780 dvojic, všechny se překrývají) | přesný průnik 93 ms na dvojici → asi 73 s | K5 (na tlačítko, na pozadí) |
| K5 | Kusovník ukázky | krabička 1 ks 26,73 g, víčko 1 ks 11,84 g, nožička 4 ks 0,30 g (PETG) | K6 |
| K6 | Export build123d `export_step` se jmény kopií | objem a obálka zpět totožné, ale **všechny nožičky „nozicka_4“** a čeština rozbitá („KrabiÄka“) | K8: vlastní zápis |
| K7 | Vlastní zápis XCAF (výrobek = soubor, kopie = id) | 0,02 s, 213 kB; zpět: krabicka→krabicka, vicko→vicko, nozicka_1…4→nozicka; čeština v UTF-8 zapsaná i přečtená | K8 |

Časy jsou jednorázové měření v cloudu, ne slib.

## 5. Budoucí matice C01–C20

**Specifikace testů pro implementaci, ne přidané testy.**

| Č. | Případ | Očekávání |
|---|---|---|
| C01 | Sestavy verze 29 a 30 bez `checks` | načtou se a uloží beze změny verze |
| C02 | Sestava s `checks`: uložit, otevřít | verze 31, totožné přijaté kolize i mez vůle |
| C03 | Verze 32, neznámý klíč v `checks` / v přijetí, záporná mez, chybná cesta id | odmítnuto česky |
| C04 | Kvádry s překryvem 5 mm | kolize 2 000 mm³ podle vzorce, místo průniku uprostřed překryvu |
| C05 | Kvádry na dotyk | žádná kolize, „dotyk“ |
| C06 | Kvádry s mezerou 0,3 mm a mez 0,5 / 0,2 mm | vůle 0,3 hlášena / nehlášena |
| C07 | Ukázka krabičky s vazbami | žádná kolize ani vůle pod 0,5 mm, 5 dotyků |
| C08 | Šroub v díře pod závit | kolize 12,96 mm³ podle vzorce; přijetí → přijatá, jeden krok Zpět |
| C09 | Přijatá kolize po změně průměru díry (objem jinak o víc než 1 %) | znovu kolize s upozorněním „objem se změnil“ |
| C10 | Přijatá kolize, která zmizela | upozornění, záznam zůstane |
| C11 | Smazání komponenty s přijatou kolizí | přijetí smazáno, jeden krok Zpět |
| C12 | Kopie v podsestavě proti dílu sestavy | dvojice s cestou id, kolize nalezena |
| C13 | Neúplná sestava | kontrola a export kusovníku a STEP odmítnuty česky |
| C14 | Průnik, který jádro nespočítá (náhradní funkce v testu) | „nelze ověřit“, nikdy „bez kolize“ |
| C15 | Kusovník ukázky | 3 řádky, kusy 1/1/4, hmotnosti podle vzorce, id komponent, NDT sloupec |
| C16 | CSV kusovníku | středník, UTF-8 s BOM, čeština čitelná, součet hmotnosti |
| C17 | Export STEP ukázky | zpětné načtení: 6 kopií se jmény id, 3 výrobky, objem a obálka totožné, názvy bez diakritiky |
| C18 | Podsestava ve STEP | vnořená sestava ve stromu |
| C19 | `skodacad sestava --kontrola / --kusovnik / --export` | výpis, soubory, kód 1 při nepřijaté kolizi |
| C20 | Okno: *Zkontrolovat* (na pozadí), klik na kolizi, *Přijmout*, *Kusovník*, *Export STEP* | akce stisknuté v testu okna, jeden krok Zpět u přijetí, snímek okna |

## 6. Navazující kroky a rozsah schválení

1. **P5.4A jádro** – `assembly_check.py` (kolize, vůle, kusovník, export STEP), formát 31,
   `AssemblySession` (přijetí kolize, mez vůle), příkazová řádka, testy C01–C19.
2. **P5.4B okno** – panel *Kontrola sestavy*, výpočet v pomocném procesu, kusovník, export,
   self-test, test C20, snímek okna.
3. **P5.5 přijetí** – ruční průchod sestavami na Windows a macOS (autor).

Schválení K1–K12 opravňuje implementovat P5.4A a P5.4B podle tohoto zápisu. Ruční přijetí
P5 zůstává na autorovi.

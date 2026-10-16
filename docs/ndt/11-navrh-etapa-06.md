# NDT – návrh etapy 06: mapa geometrického pokrytí UT (začátek milníku M2)

> Etapa 06 plánu `03-implementacni-plan.md` a závazného vymezení `04-zavazne-vymezeni-ut.md`.
> Otevírá **milník M2 (hodnotitelný UT)**: na kontrolované oblasti studie (nebo zadané ploše či
> bodu dílu) spočítá a obarví **Mapu geometrického pokrytí UT** ze souboru povolených poloh sondy
> podél přímé dráhy nebo po celé pojezdové ploše.

Stav: návrh 16. 10. 2026 · **schváleno autorem; implementováno ve vývojové větvi, čeká na kontrolu a sloučení**

Autor po místní ruční zkoušce potvrdil funkčnost (16. 10. 2026). Referenční deska při kroku
10 mm vyšla 85,74 % proti analytickému limitu 85,5 %. Místní self-test ve Windows včetně
skutečného 3D kreslení prošel. Ověření této změny v balíčcích Windows a macOS provádějí
GitHub Actions; úspěch místního testu sám nepotvrzuje sestavený balíček ani ruční test na Macu.

## 1. Co etapa přinese a závazné hranice (`04-zavazne-vymezeni-ut.md`)

Etapy 04 a 05 umí přiložit sondu do jednoho místa nebo projet přímou čáru a ukázat osu paprsku.
Etapa 06 odpoví na navazující otázku konstruktéra i NDT technika: **„Která místa kontrolované
oblasti paprsek ze všech povolených poloh sondy geometricky zasáhne a kde zůstane slepé místo?“**

Podle závazného vymezení `docs/ndt/04-zavazne-vymezeni-ut.md`:
- Název v okně i ve výstupech je vždy **„Mapa geometrického pokrytí UT“** (`skodacad.ndt.UT_COVERAGE`).
  Nikdy se nepoužívá označení „mapa prozvučitelnosti“ ani „pravděpodobnost detekce“.
- Každý výstup (panel NDT, příkazová řádka `skodacad pokryti`, export CSV) obsahuje v plném znění
  `UT_DISCLAIMER` a výslovnou větu:
  *„Procento vyjadřuje pouze geometrický podíl zasažené oblasti, nikoli pravděpodobnost nalezení vady.“*
- Každý vzorek (bod nebo trojúhelníková ploška) kontrolované oblasti dostane právě jeden ze **tří
  povinných stavů**:

| Kód stavu | Český název v okně a protokolu | Barva ve 3D | Kdy nastane |
|---|---|---|---|
| `covered` | **Geometricky pokryto** | zelená `(0.15, 0.70, 0.25)` | místo zasahuje geometrický model svazku (přímé rameno nebo povolený odraz s jistým dopadem) aspoň z jedné **platné** polohy sondy (`placement.ok`) |
| `uncovered` | **Geometricky nepokryto** | červená `(0.85, 0.20, 0.15)` | v rámci zadaných poloh sondy, úhlu, počtu odrazů a předpokladů místo nezasáhl žádný platný ani nejistý paprsek |
| `uncertain` | **Nelze spolehlivě vyhodnotit** | žlutá `(0.90, 0.75, 0.15)` | místo není jistě pokryto, ale zasahuje ho paprsek z nejisté polohy sondy (`placement.state == "uncertain"`), nejisté rameno po dopadu na hranu/roh (`not leg.certain`), nebo je v daném místě nejednoznačná geometrie |

## 2. Jak se počítá geometrické pokrytí (`src/skodacad/ndt/coverage.py`)

### A) Vzorkování kontrolované oblasti (cíl)

Kontrolovanou oblastí v etapě 06 jsou:
1. **Plochy kontrolované oblasti studie** (`study["target"]["faces"]`, případně plochy vybrané v příkazové řádce):
   - Každá cílová plocha se rozdělí v parametrech $(u, v)$ na trojúhelníkovou síť s nejdelší stranou
     nejvýše `target_step` mm (výchozí **4,0 mm**; sdílí princip dělení ploch z `thickness_map.py`,
     ale běží jen na vybraných cílových plochách, nikoli nutně na celém tělese).
   - Každý trojúhelník představuje jeden vzorek: má těžiště $\mathbf{T}$, obsah $S_k\ [\text{mm}^2]$
     a venkovní normálu plochy.
2. **Jednotlivé kontrolované body** (např. bod kořene svaru $(0; 0; 0)$ na `tupy_svar.json` nebo bod
   na dně desky pod osou žebra $(0; 0; 0)$ na `zebro.json` pro rychlé analytické testy a dotazy).

*(Poznámka: datová struktura vzorků je připravena tak, aby v etapě 07 přijala bez přepisování i
3D mřížku objemu svaru a tepelně ovlivněné oblasti.)*

### B) Kandidátní polohy sondy (odkud se zkouší)

Podporovány budou dva režimy pohybu sondy po pojezdové ploše (se zachovaným natočením sondy
`angle_deg` a parametry paprsku `beta`, `bounces`, `max_length`, `refraction`):

1. **Po přímé dráze (`mode="line"`):**
   - Z výchozího přiložení sondy se vygenerují polohy podél přímky ve směru paprsku (nebo napříč)
     s krokem `scan_step` mm (výchozí **2,0 mm**) na délce `length_mm`.
2. **Po celé pojezdové ploše (`mode="face"`):**
   - Na pojezdové ploše, na které je sonda přiložena, se vytvoří rovnoměrná mřížka bodů s krokem
     `scan_step` mm (výchozí **5,0 mm**).
   - V každém bodě se ověří přiložení sondy (`devices.place` s mezipamětí poloprostoru z etapy 05):
     - polohy v kolizi (`collision`), s přesahem (`overhang`), nedosedající (`gap`) nebo v úzkém
       místě (`clearance`) **nevysílají platný paprsek**,
     - polohy se stavem `ok` vysílají platný paprsek (`ut.trace_beam`),
     - polohy se stavem `uncertain` vysílají paprsek označený jako nejistý (může změnit stav vzorku
       z `uncovered` na `uncertain`, nikdy však na `covered`).

### C) Podmínka geometrického zásahu vzorku

Nechť rameno paprsku $L = (\mathbf{A}, \mathbf{B})$ má délku $d = |\mathbf{B} - \mathbf{A}|$. Pro
kontrolovaný bod $\mathbf{T}$ najdeme nejbližší bod $\mathbf{Q}$ na úsečce $\mathbf{A}\mathbf{B}$,
jeho vzdálenost od počátku přímé dráhy $s$ a kolmou vzdálenost od osy paprsku $h = |\mathbf{T} - \mathbf{Q}|$.

Vzorek $\mathbf{T}$ je ramenem zasažen, pokud:
$$h \le r_0 + s \cdot \tan(\gamma)$$
kde:
- $r_0$ `[mm]` je **poloměr zachycení (tolerance mřížky)**: výchozí $r_0 = \max(\sqrt{1/2}\cdot\text{target\_step}, k\cdot\text{scan\_step})$,
  kde $k=\sqrt{1/2}$ pro 2D pojezd a $k=0{,}6$ pro přímou dráhu (půl úhlopříčky 2D buňky
  musí být zahrnuto, původně navržené $0{,}6$ by ponechávalo umělé mezery),
  aby souvislý pojezd sondy s krokem mřížky nezanechával mezi sousedními diskrétními paprsky
  umělé pruhy (lze nastavit i ručně jako `tolerance_mm`),
- $\gamma \ge 0^\circ$ je **volitelný poloviční úhel rozevření geometrického svazku** (`spread_deg`,
  výchozí **$0^\circ$ = osový paprsek** podle `05-referencni-dily.md`).

**Upřesnění při implementaci:** numerická tolerance sama neprokazuje zásah osou. Na rovinném
pojezdu se pro vzorek v toleranci dopočítá mezilehlá poloha sondy a znovu se ověří její
otisk, kolize, rezerva i skutečná dráha. U přímé dráhy musí ležet na zadaném úseku; nelze
tak zakrýt slepé místo u žebra tolerancí mřížky. U zakřiveného pojezdu je zásah pouze
v numerické toleranci označen nejistě, pokud neleží ve skutečně zadaném geometrickém svazku.
Za konec ramene se svazek numerickou tolerancí neprodlužuje. Procento z bodových dotazů je
podíl bodů, nikoli plocha; plochy se váží obsahy trojúhelníků.
Při dopočtu mezilehlé polohy po odrazu se cíl postupně zrcadlí zpět přes odrazové roviny
k přímému rameni; posun zdroje totiž nemusí posunout odražené rameno stejným směrem.
Nalezená poloha i všechny odrazy se následně znovu ověří skutečným trasováním.
U přímého osového pojezdu se hodnotí průnik paprsku se skutečnou trojúhelníkovou ploškou,
nemusí projít přesně jejím těžištěm. Obarvený pás má šířku danou rozlišením cílové sítě;
s jejím zjemňováním se zužuje. Podíl plochy z jediné osové čáry proto závisí na rozlišení.

U každého pokrytého vzorku si mapa pamatuje:
- kterým ramenem byl nejdříve zasažen (`1` = přímý paprsek / půlkrok, `2` = po 1. odrazu / celý krok…),
- délku dráhy paprsku v materiálu k místu zásahu `[mm]`,
- výstupní bod sondy, odkud zásah přišel.

### D) Citlivost na krok výpočtu (konvergence)

Podle požadavku plánu (`03-implementacni-plan.md`, etapa 06) nabídne modul funkci
`check_convergence` (volitelně v CLI `--konvergence` a v testech):
- porovná vypočtené procento pokrytí při zvoleném kroku `step` a při hrubším kroku `2 * step`,
- ponechá stejný numerický poloměr zachycení, aby porovnávala rozlišení, nikoli jiný svazek,
- vrátí rozdíl v procentních bodech (`delta_pct`) a informaci, zda se mřížka stabilizovala
  (např. `rozdíl 0,6 % oproti dvojnásobnému kroku`).

## 3. Očekávané výsledky na referenčních dílech (`05-referencni-dily.md`)

| Referenční díl | Zkušební scénář pokrytí | Očekávaný výsledek |
|---|---|---|
| **1. Deska** (`deska.json`, $200 \times 100 \times 20$) | Přímá sonda $\varnothing 10\text{ mm}$ jezdí po horní ploše ($z = 20$), cíl = dolní plocha ($z = 0$) | Střed dolní plochy $190 \times 90\text{ mm}$ je **geometricky pokryt** ($\approx 85{,}5\,\%$); okrajový pás šířky $5\text{ mm}$ po obvodu je **geometricky nepokryt**, protože by sonda přesahovala přes okraj desky |
| **2. Blok s kapsou** (`kapsa.json`) | Přímá sonda $\varnothing 10\text{ mm}$ jezdí po spodní ploše ($z = 0$), cíl = horní plocha kolem kapsy ($z = 40$) a dno kapsy ($z = 15$) | Dno kapsy ($40 \times 30\text{ mm}$) i horní plocha mimo kapsu (s odstupem $5\text{ mm}$ od vnějšího okraje) jsou **geometricky pokryty** přímým paprskem (dráha $15\text{ mm}$ pod kapsou, $40\text{ mm}$ mimo kapsu) |
| **3. Deska se žebrem** (`zebro.json`, $t = 20$, žebro v $x = 0$) | Úhlová sonda na pravé horní ploše ($x > 5, z = 20$) míří k žebru ($180^\circ$), přímý paprsek (`bounces=0`), cíl = bod pod osou žebra $(0; 0; 0)$ a pás dna pod žebrem $x \in [-5; +5]$ | Bez rezervy ($x_{\min} = 17$): pro $\beta = 45^\circ$ je osa $(0; 0; 0)$ **pokryta** (dosah do $x = -3$). S rezervou $5\text{ mm}$ ($x_{\min} = 22$): pro $\beta = 45^\circ$ je osa $(0; 0; 0)$ **nepokryta** (slepé místo pod žebrem, dosah jen do $x = +2$); pro $\beta = 60^\circ$ je celý pás pod žebrem **pokryt** |
| **6. Tupý svar V** (`tupy_svar.json`, $t = 12$, převýšení $c = 20$) | Úhlová sonda na pravém plechu ($x \ge 10, z = 12$) míří k ose svaru ($180^\circ$), přímý paprsek (`bounces=0`), cíl = kořen svaru $(0; 0; 0)$ a spodní plocha podkořene | Čelo sondy zastaveno převýšením v $x_{\min} = 22\text{ mm}$. Pro $\beta = 45^\circ$ a $\beta = 60^\circ$ je kořen $(0; 0; 0)$ **geometricky nepokryt**; pro $\beta = 70^\circ$ je kořen **geometricky pokryt** |
| **8. Obtížný přístup** (`pristup.json`, mezera mezi žebry $30\text{ mm}$) | Úhlová sonda $40 \times 20\text{ mm}$ v mezeře mezi žebry napříč ($0^\circ / 180^\circ$) vs. podél ($90^\circ$) | Napříč mezerou se sonda nikde nevejde (0 platných poloh → **0 % pokryto**); podél žeber ($90^\circ$) se vejde a pokrývá dno pod mezerou ve směru osy Y |

## 4. Ovládání v okně, `ModelSession` a příkazové řádce

### A) Panel NDT a 3D prohlížeč (`gui/ndt_panel.py`, `gui/viewer.py`)

Pod skupinou *Přístupnost UT sondy* přibude v panelu NDT skupina **Mapa geometrického pokrytí UT**:
- **Zdroj poloh sondy:** přepínač *Po ploše přiložení* (celá plocha pod sondou) / *Z přímé dráhy* (úsek z řádku *Délka čáry*).
- **Krok výpočtu `[mm]`:** jemnost pojezdu a sítě cílových ploch (výchozí `5,0 mm`).
- **Tlačítka:** **Spočítat pokrytí** a **Skrýt mapu**.
- **Ve 3D okně:** kontrolované plochy studie se obarví trojúhelníkovou sítí (`AIS_Triangulation`)
  podle tří stavů (**zelená** = pokryto, **červená** = nepokryto, **žlutá** = nelze spolehlivě
  vyhodnotit); přiložená sonda i osa paprsku zůstávají viditelné.
- **V textovém souhrnu panelu:** počet platných poloh sondy, podíl stavů v % i v $\text{mm}^2$,
  přehled zasažení přímým paprskem vs. odrazem a připomenutí, že jde pouze o geometrický podíl.

### B) Veřejné rozhraní v `ModelSession` (`session.py`)

```python
session.compute_ndt_coverage(
    mode="face",          # "face" (po ploše přiložení) nebo "line" (z přímé dráhy)
    step_mm=5.0,          # krok vzorkování pojezdu a cílových ploch [mm]
    bounces=None,         # None = podle sondy / výchozí (1 odraz)
    spread_deg=0.0,       # poloviční úhel rozevření kužele svazku [°]
) -> CoverageMap
session.clear_ndt_coverage()
```

### C) Příkazová řádka (`skodacad pokryti`)

```powershell
python -m skodacad pokryti examples/ndt/zebro.json --plocha 60,0,20 --cil 0,0,0 --sklon 45 --smer 180 --odrazy 0
python -m skodacad pokryti model.json --plocha 60,0,20 --studie s1 --krok 4 --csv pokryti.csv
```
- Vypíše na začátku `UT_DISCLAIMER`, parametry sondy a předpoklady výpočtu, souhrn všech tří stavů
  (`Geometricky pokryto`, `Geometricky nepokryto`, `Nelze spolehlivě vyhodnotit`), citlivost na krok
  a volitelně uloží podrobné CSV.

Zdrojová plocha je vždy výslovně zadaná přes `--plocha` (poloha sondy není uložená v JSON).
`--cil-plocha X,Y,Z` vybere cílovou plochu bodem mimo hrany, `--cil` jednotlivý bod; obě
volby lze opakovat. `--rezim line` použije přímou dráhu, jinak se vzorkuje celá pojezdová
plocha. `--tolerance`, `--krok-cile`, `--rozevreni`, `--dosah` a `--konvergence` zpřesňují
předpoklady, které se vypíší a uloží s CSV. Výpočet v okně běží v pomocném procesu a jde
zastavit stávajícím tlačítkem. Mapa zanikne po změně dílu, sondy, studie nebo přiložení.

Referenčních 85,5 % je analytický limit spojitého osového pojezdu na desce. Výsledek sítě
je aproximace v těžištích plošek; přesnost se kontroluje zjemněním. Změna rozevření je změna
geometrického předpokladu, nikoli pouze zjemnění výpočtu.

## 5. K rozhodnutí

1. **Které režimy pojezdu sondy má etapa 06 umět hned v první verzi?**
   - *Návrh:* **obojí** – **po přímé dráze** (`line`, navazuje přímo na *Projet čáru* z etapy 05)
     **i po celé ploše přiložení** (`face`, mřížka po ploše, na které sonda stojí, se zachovaným
     směrem paprsku).
2. **Jaký má být výchozí model svazku pro vyhodnocení pokrytí?**
   - *Návrh:* **osový paprsek ($\gamma = 0^\circ$)** s tolerancí zachycení úměrnou kroku mřížky
     (aby souvislý pojezd nedělal umělé mezery mezi kroky) + volitelný parametr rozevření kužele
     `spread_deg` ($\gamma \ge 0^\circ$) pro případy, kdy chce uživatel zohlednit divergency svazku.
3. **Měnit v etapě 06 formát souboru JSON (nyní verze 15)?**
   - *Návrh:* **ne (ponechat verzi 15)** – podle plánu (`03-implementacni-plan.md`, etapa 01) se
     výsledky pokrytí přepočítávají z aktuálního dílu a neukládají jako statická pravda do modelu.
     Kontrolovaná oblast (`target.faces`) i sonda (`device`) už ve studii uložené jsou.

## 6. Postup implementace (malé kroky, po každém `ruff` + `pytest`)

| Krok | Soubor | Obsah |
|---|---|---|
| 1 | `src/skodacad/ndt/coverage.py` + `tests/test_ndt_coverage.py` | výpočet `CoverageMap` (vzorkování cílových ploch a bodů, pojezd po přímce i po ploše, 3 stavy `covered`/`uncovered`/`uncertain`, citlivost na krok, CSV export) a testy na referenčních dílech (`deska`, `kapsa`, `zebro`, `tupy_svar`, `pristup`) |
| 2 | `src/skodacad/session.py`, `src/skodacad/cli.py` + `tests/test_ndt_session.py` | metody `compute_ndt_coverage` a `clear_ndt_coverage` v `ModelSession`, příkaz `skodacad pokryti` s povinným `UT_DISCLAIMER` |
| 3 | `src/skodacad/gui/viewer.py`, `src/skodacad/gui/ndt_panel.py`, `src/skodacad/gui/main_window.py` + `tests/test_gui.py` | skupina *Mapa geometrického pokrytí UT* v panelu NDT, 3D vykreslení pokrytí na cílových plochách studie |
| 4 | `README.md`, `CLAUDE.md`, `docs/ndt/` | dokumentace příkazu `skodacad pokryti`, scénář „klikni, nastav, pozoruj“ a aktualizace stavu etap |

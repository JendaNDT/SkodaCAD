# NDT – návrh etapy 10: plán dráhy UT sondy (automatická skenovací trajektorie)

Stav: **návrh k rozhodnutí autora**, nic z něj zatím není naprogramované.
Výchozí stav: `main`, commit `bbc207f` ([PR #23](https://github.com/JendaNDT/SkodaCAD/pull/23)).
Navazuje na [plán, etapa 10](03-implementacni-plan.md), [návrh poloh sondy (etapa 09)](17-navrh-etapa-09.md),
[ruční pohyb sondy (etapa 05)](10-navrh-etapa-05.md), [geometrické pokrytí (etapa 06)](11-navrh-etapa-06.md),
[objemové pokrytí svaru (07B)](13-navrh-etapa-07b.md) a [závazné vymezení UT](04-zavazne-vymezeni-ut.md),
které má přednost. Etapa 10 dokončuje milník **M3 – asistovaný UT** (etapy 09–10).

Zadání z plánu: *„Plán souvislé dráhy po přípustných kontaktních plochách, respektovat rozměry
zařízení, překážky, orientaci a praktický nájezd. Hodnotit pokrytí, délku, počet přestavení
a robustnost. Možnost ručních zakázaných zón a úpravy trasy.“* Podmínka dokončení: *„Každý bod
navržené trasy je bez kolize, pokrytí souhlasí s nezávislým přepočtem.“*

## Co tato etapa přinese

**Dnes:**

- Etapa 09 řekne, **odkud** kontrolovat (plocha, směr, úhel, odrazy) a jaké má varianta
  pokrytí. Neřekne, **jak sondou jezdit**.
- *Spočítat pokrytí* předpokládá, že sonda projede **celou** plochu pojezdu, všude, kde se
  vejde. Skutečný postup (řádky, přesuny, zvednutí sondy) nikde popsaný není.
- *Projet čáru* (etapa 05) projede jednu přímku. Celou dráhu, tabulku poloh ani místa, kam
  sonda nesmí (štítek, upínka, poškozený povrch), zadat nejde.

**Po etapě 10:**

1. V panelu NDT bude skupina **Plán dráhy**. Tlačítko **Naplánovat dráhu** vezme přiloženou
   sondu, nebo vybranou variantu či kombinaci z návrhu poloh. Z ní sestaví **souvislou
   dráhu**: řádky tam a zpět, mezi nimi posun o rozteč (cik-cak).
2. Dráha vede jen tam, kde se sonda **vejde** (bez kolize, dosedá, nepřesahuje, mimo zakázané
   zóny) a odkud paprsek **míří k cíli**. Kde se řádek přerušit musí (žebro, otvor, zóna),
   plán sondu **zvedne a přestaví**. Zkontroluje přitom, že ji jde na nové místo spustit shora
   (**nájezd**).
3. Ke každému plánu ukáže **hodnocení**: geometrické pokrytí cíle, délku dráhy, počet přestavení
   a **robustnost** (o kolik mm smí sonda uhnout bokem, nejmenší volno k překážce).
4. **Tabulka poloh** (pořadí, úsek, souřadnice, směr, stav, volno) a **přehrávání ve 3D**: sonda
   s paprskem jede po dráze a mapa pokrytí přitom narůstá.
5. **Zakázané zóny** (kvádry) a **ruční úpravy** trasy: smazat, zkrátit, obrátit, přeřadit nebo
   přidat úsek. Každá úprava je jeden krok Zpět a plán se po ní znovu ověří.
6. Plán a zóny se **uloží do studie** v souboru modelu (formát **18**), po otevření tam budou.
   Po změně dílu je plán „zastaralý“. Sám se nikdy nepřepočítá ani neposune, stejně jako dnes
   cílový objem.
7. **Nezávislý přepočet**: pokrytí plánu spočítané znovu z uložených poloh (v okně, v příkazové
   řádce, po novém otevření souboru) dá **stejné číslo**.

**Co se nemění:** výpočet přiložení sondy a paprsku, návrh poloh (etapa 09), závazné vymezení
UT a povinné upozornění, výrobní geometrie. Výpočet pokrytí dostane jen jednu novou možnost:
počítat z poloh plánu. Dnešní výsledky zůstanou beze změny, hlídají to regresní testy.

## 1. Rozsah a hranice

- **Jen UT, jen geometrie.** Plán optimalizuje jen **přístupnost sondy a geometrické
  pokrytí**. Každý výstup nese `UT_DISCLAIMER` a větu „Plán dráhy popisuje jen geometrii pohybu
  sondy a geometrické pokrytí, nikoli zjistitelnost vad.“
- **Jen rovinné kontaktní plochy**, stejně jako etapa 09. Zakřivené plochy plán vynechá a ve
  výsledku to výslovně napíše.
- **Směr sondy je v průchodu stálý.** Sonda se během jízdy nenatáčí ani nekývá do stran.
- **Žádný čas, rychlost ani technika pohybu** (vazební prostředek, přítlak, kalibrace). Plán je
  geometrie: kudy a v jakém pořadí.
- **Nemění díl.** Návrhy změny geometrie jsou až v etapách 14–15.
- **Nenalezeno ≠ nemožné.** Výsledek platí pro zadané plochy, směry, rozteč, rozměry sondy
  a zóny („Geometricky nepokryto … není důkaz, že jiný postup kontroly není možný“).

## 2. Jak se dráha skládá

### Pojmy

- **Průchod** = jedna rovinná plocha + stálý směr paprsku + úhel β + počet odrazů. Je to totéž
  co jedna varianta z etapy 09. Plán z kombinace má nejvýš 3 průchody.
- **Řádek** = přímka na ploše, po které sonda jede. Sousední řádky dělí **rozteč** (výchozí
  5 mm = krok výpočtu pokrytí).
- **Úsek** = souvislý kus řádku, kde se sonda vejde a paprsek míří k cíli.
- **Přesun** mezi úseky jde **po povrchu** (sonda se nezvedá), když vede jen přes platné polohy.
  Jinak je to **přestavení**: zvednout, přenést, spustit.

### Dva vzory řádků

| Vzor | Řádky vedou | Posun o rozteč | Kdy se hodí |
|---|---|---|---|
| **k cíli a zpět** | ve směru paprsku (sonda jede k cíli a od něj) | napříč | krátké cíle, překážky podél |
| **podél** | napříč paprsku (u svaru rovnoběžně se svarem) | ve směru paprsku | dlouhé svary: málo dlouhých řádků |

Výchozí volba je *automaticky*: program sestaví oba vzory a vybere ten s **méně přestaveními**,
při shodě **kratší** dráhu (rozdíl nad 5 %), pak ten s méně řádky. Čísla obou vzorů jsou vidět
a jde přepnout.

### Postup (pevná pravidla, žádná náhoda)

1. **Mřížka průchodu**: uzly po rozteči, zarovnané se směrem paprsku, jen uvnitř plochy.
2. **Dosah** (rychlé, změřeno **0,3 ms** na uzel): z uzlu se spustí paprsek bez přiložení. Uzly,
   odkud žádné rameno nevede blízko cíle, se zahodí. Je to stejné síto jako 2. kolo etapy 09.
3. **Přiložení** (změřeno **28–35 ms** na uzel) jen v uzlech v dosahu. Platný uzel = přiloženo
   a mimo zakázané zóny. Nejisté přiložení do plánu nepatří.
4. **Úseky**: v každém řádku souvislé běhy platných uzlů, oříznuté na část v dosahu. Konce se
   **dohledají** půlením až na 0,5 mm k hranici, kde se sonda ještě vejde. Úsek pak začíná
   u překážky, ne o rozteč dřív.
5. **Pořadí**: řádek za řádkem, střídavě tam a zpět. Když všechny polohy přesunu na další úsek
   projdou, jede sonda po povrchu. Jinak se přestaví.
6. **Kontrola celé dráhy po 1 mm** (jako *Projet čáru*): sonda se přiloží po celé délce úseků
   i přesunů po povrchu. Tabulka poloh je po rozteči, kontrola mezi polohami je hustší. Poloha,
   která neprojde, úsek rozdělí. Kontrolní krok jde zvětšit, když by výpočet trval dlouho.
7. **Nájezd**: sonda se na začátku úseku po přestavení spouští a na konci zvedá **kolmo
   k ploše**. Tělo sondy prodloužené nahoru o **výšku nájezdu** (výchozí 20 mm) nesmí narazit do
   dílu ani do zóny. Když nájezd nejde (například pod převisem), úsek začne na nejbližší poloze,
   kde jde, a pod převis sonda dojede po povrchu. Výška 0 kontrolu nájezdu vypne.

### Zakázané zóny

- Zóna je **kvádr v souřadnicích dílu** s názvem („štítek“, „upínka“). Zadává se číselně (střed
  a rozměry) nebo **kolem vybraného bodu či plochy** ve 3D.
- Sonda do zóny nesmí zasáhnout **žádnou částí těla**. Je to stejná kontrola jako kolize
  s dílem (průnik těles OCCT, dnes 3–6 ms).
- Zóny platí pro plán dráhy. Ruční přiložení sondy do zóny panel jen **upozorní**. *Spočítat
  pokrytí* a návrh poloh je v etapě 10 nezohlední (napíše to). Rozdíl „celá plocha / plán“ pak
  ukáže, kolik zóny ubraly.

## 3. Pokrytí plánu a nezávislý přepočet

- Pokrytí počítá **stávající výpočet** (etapa 06 pro plochy a body, 07B pro objem). Jen místo
  všech uzlů plochy dostane **polohy plánu** v pořadí jízdy.
- Dnes výpočet mezi uzly dohledá polohy sondy kdekoli na ploše a každou přesně ověří. V plánu
  smí takové mezipolohy ležet jen **v pásu úseku**: podél od začátku do konce, napříč ± půl
  rozteče. Řádky s roztečí 5 mm se tedy počítají jako **spojitě projetý pás**. Je to stejný
  předpoklad, jaký dnes dělá pojezd po ploše pro celou plochu, a bude výslovně v předpokladech
  výsledku.
- Průchody se sjednotí **vzorek po vzorku** (`access.union` z etapy 09), bez přenormování vah.
- **Nezávislý přepočet** z uloženého plánu po novém otevření souboru, v CLI i v okně musí dát
  stejné číslo (test). Plán bez zón navíc nesmí dát **víc** než pojezd po celé ploše. Na
  referenčním svaru musí dát totéž.

Změřeno 18. 10. 2026 v cloudu (časy kolísají), celý V svar 100 mm, plocha nahoře vpravo,
úhel 70°, směr ke svaru, krok 5 mm. Pás = polohy zarovnané se směrem paprsku jen v daném
rozsahu x, jinak beze změny výpočtu:

| Pojezd | Polohy (platné) | Geometricky pokryto | Čas |
|---|---|---|---|
| bez odrazu, celá plocha (dnešní *Spočítat pokrytí*) | 609 (340) | 11,79 % | 48 s |
| bez odrazu, jen pás x 10–50 mm | 189 (102) | 11,79 % | 33 s |
| bez odrazu, jen pás x 10–35 mm | 126 (51) | 11,79 % | 33 s |
| 1 odraz, celá plocha | 609 (340) | 79,93 % | 125 s |
| 1 odraz, jen pás x 10–95 mm | 378 (255) | 79,93 % | 120 s |

Platné polohy jsou x ≥ 22 mm (čelo sondy naráží na převýšení) a y v ±40 mm (na konci plechu
sonda přesahuje). Sedí to s ručně ověřenou referencí v `15-rozbor-citlivosti-v-svaru.md`.

**Závěr:** oříznutí dráhy na dosah paprsku tady pokrytí **neubere** a výpočet nezpomalí. Většinu
času nezabírá počet poloh, ale přesné ověření paprsků blízko cíle. Kontrola dráhy po 1 mm by
u svaru s odrazem znamenala zhruba 1 300 přiložení, tedy asi 40 s. To je **odhad** z 30 ms na
přiložení, změří se v 10A. Celý plán svaru se tak spočítá za jednotky minut, na pozadí, se
zastavením a s odhadem předem.

## 4. Hodnocení plánu

| Hledisko | Co ukáže |
|---|---|
| **Pokrytí** | geometricky pokryto a nelze spolehlivě vyhodnotit (%, u objemu i mm³); pro srovnání pojezd po celých plochách průchodů |
| **Délka** | dráha po povrchu (úseky + přesuny) a ve vzduchu (přestavení), v mm |
| **Přestavení** | počet zvednutí sondy; zvlášť změny průchodu (jiná plocha nebo směr) a změny úhlu (jiná sonda) |
| **Robustnost** | **boční rezerva**: nejmenší vzdálenost, o kterou smí sonda kdekoli na dráze uhnout napříč, než narazí, přesáhne nebo vjede do zóny; **nejmenší volno** k překážce nad rovinou přiložení; místa „na hraně“ (rezerva pod 1 mm) se v tabulce poloh zvýrazní |
| **Odolnost pokrytí** (volitelně) | pokrytí, když se všechny řádky posunou o ± půl rozteče napříč; řekne, jestli číslo nestojí na přesném umístění řádků; 2 výpočty navíc, proto jen na zaškrtnutí |

Žádné souhrnné „skóre“, jako v etapě 09. Všechna čísla jsou vidět a o volbě vzoru rozhoduje
pravidlo z oddílu 2. Poznámka vysvětlí kompromis česky, například: „řádky u konce plechu
mají boční rezervu 0 mm – sonda tam přesahuje, kdyby uhnula ven“.

## 5. Uložení do souboru (formát 18)

Ve studii přibudou dvě nepovinné položky:

```json
"zones": [{"name": "štítek", "min": [60, -20, 12], "max": [90, 20, 20]}],
"plan": {
  "pattern": "toward", "row_step_mm": 5, "approach_mm": 20, "check_step_mm": 1,
  "passes": [{
    "face": {"at": [40, 0, 12], "normal": [0, 0, 1]},
    "angle_deg": 180, "beta": 70, "bounces": 0,
    "segments": [{"start": [37, -40, 12], "end": [22, -40, 12]}]
  }],
  "part": "…otisk dílu…", "target": "…otisk cíle…", "probe": "…otisk sondy…",
  "edited": false
}
```

- Plocha průchodu se pamatuje **bodem a směrem** jako přiložení sondy (pravidlo 1: nikdy
  indexem). Úseky jsou souřadnice v mm. Po změně dílu se nikam neposouvají.
- **Stav plánu:** *platný*, *zastaralý* (změnil se díl, cíl nebo sonda – podle otisků) nebo
  *neplatný* (některá poloha neprojde kontrolou, s českým důvodem). Zastaralý plán jde
  **Ověřit znovu** (úseky zůstanou, ukáže se, co neprojde) nebo **Sestavit znovu** (ruční úpravy
  se zahodí, okno se nejdřív zeptá).
- Výsledek pokrytí plánu se **neukládá** (jako mapa pokrytí). Vždy se počítá znovu.
- Staré soubory verze 1–17 se načtou beze změny a studie bez plánu zůstane totožná.

## 6. Okno

Nová skupina **Plán dráhy** v panelu NDT pod *Návrhem poloh sondy*:

- **Naplánovat dráhu** z přiložené sondy, z vybrané varianty nebo z kombinace návrhu. Volby:
  vzor (automaticky / k cíli a zpět / podél), rozteč, výška nájezdu. Pod nimi odhad, průběh
  a *Zastavit*.
- **Souhrn hodnocení** a **seznam úseků** (průchod, od–do, délka, návaznost: po povrchu /
  přestavení). Tlačítka *Smazat*, *Obrátit*, *Nahoru* / *Dolů*, *Upravit…* (začátek a konec
  v mm) a *Přidat z přiložené sondy*.
- **Zakázané zóny…**: dialog podobný editoru cílového objemu (název, střed, rozměry, *Z výběru*).
- **Přehrávání**: posuvník polohy, *Přehrát* / *Pauza*, krok ◀ / ▶. Sonda a paprsek se ve 3D
  posouvají, mapa pokrytí narůstá, tabulka poloh zvýrazní aktuální řádek.
- **Ve 3D**: úseky zeleně, přesuny po povrchu šedě, přestavení oranžově obloukem nad dílem
  (ve výšce nájezdu), začátek kuličkou, zóny průhledně červeně. Kreslí se jen čarami
  a kuličkami, které už bezpečně fungují (viz známé pasti, žádný podklad pod popiskem).
- **Spočítat pokrytí plánu** (volitelně s odolností) a **Export CSV…**.
- Během práce AI je skupina zamčená. Změna dílu, cíle nebo sondy plán označí jako zastaralý.

## 7. Výstupy

- **CSV plánu:** povinné upozornění, věta o významu plánu, předpoklady (sonda, materiál,
  rozteč, kontrolní krok, výška nájezdu, zóny, pás = spojitý pojezd, algoritmus), hodnocení,
  úseky a **tabulka poloh**.
- **Příkazová řádka:** `skodacad draha model.json --studie s1 [--plocha X,Y,Z --smer 180 |
  --varianta 1 | --kombinace] [--vzor auto|k-cili|podel] [--roztec 5] [--najezd 20]
  [--zona X1,Y1,Z1:X2,Y2,Z2] [--ulozit] [--csv plan.csv]`. Volba `--prepocet` přepočítá plán
  uložený v souboru.
- **AI asistent** nový nástroj nedostane. Pravidla platí dál: čísla ani plán si nevymýšlí,
  studii mění jen na přání. `replace_model` bez klíče `ndt` plán i zóny ponechá.

## 8. Ověření před předáním

1. **V svar bez odrazu** (`tupy_svar_objem.json`, shora vpravo, 70°): plán bez zón dá
   **11,79 %**, stejně jako pojezd po celé ploše. Úseky začínají u x = 22 mm (± 0,5 mm),
   řádky jen v y ±40 mm, 0 přestavení.
2. **V svar s odrazem:** plán dá **79,93 %** jako celá plocha.
3. **Zakázaná zóna** přes část pásu: řádky se rozdělí nebo přibude přestavení. Nezávislá kontrola
   **každé polohy po 1 mm** znovu (mimo plán) najde nulu kolizí s dílem i se zónou. Pokrytí
   nevyjde víc než bez zóny.
4. **Obtížný přístup** (`pristup.json`): napříč mezerou plán nic nenajde a řekne proč (kolize
   se žebry). Podél mezery vede řádky jen v pásu ±5 mm (vůle 30 − 20 = 10 mm). Nájezd mezi
   žebra 50 mm vysoká projde.
5. **Nájezd zablokovaný převisem** (testovací díl v testu): úsek pod převisem nezačíná, sonda
   tam dojede po povrchu. S výškou nájezdu 0 začít může.
6. **Nezávislý přepočet:** uložit, otevřít, přepočítat → stejné číslo; CLI totéž.
7. **Ruční úpravy:** smazání úseku pokrytí sníží a Zpět ho vrátí přesně. Úsek přidaný přes
   překážku = plán neplatný s českým důvodem.
8. **Formát 18:** načtení verzí 1–17, studie bez plánu beze změny, poškozený plán = česká chyba.
9. **Regrese:** deska 85,5 %, V svar 12,2 % / 15,18 %, žebro, etapa 09 beze změny. Povinné
   upozornění v panelu, CLI i CSV (`test_ndt_scope.py`).
10. **Okno:** offscreen testy (plán, úpravy, Zpět, zóny, přehrávání, zámek AI), snímek pod Xvfb,
    GitHub Actions Windows i macOS. Testy krátké kvůli časovému limitu kroku *Testy*.

## 9. Malé kroky po schválení

| Krok | Výstup | Ověření |
|---|---|---|
| **10A.1 – jádro** | `ndt/plan.py`: mřížka průchodu, dosah, přiložení, úseky s dohledanými konci, cik-cak, přesuny, nájezd, zóny, kontrola po 1 mm, hodnocení; pokrytí z poloh plánu (rozšíření `coverage`) | testy 1–5 a 9 |
| **10A.2 – soubor, ModelSession, CLI** | formát 18 (`plan`, `zones`), stavy plánu, úpravy jako kroky Zpět, výpočet v pomocném procesu, `skodacad draha`, CSV | testy 6–8 |
| **10B – okno** | skupina *Plán dráhy*, dialog zón, seznam úseků, přehrávání, kresba ve 3D | test 10, snímky, balíčky Windows a macOS |

Každý krok zvlášť: `ruff`, `pytest`, commit. Do `main` až na tvůj pokyn.

## 10. Co etapa 10 nebude

- zakřivené kontaktní plochy, natáčení nebo kývání sondy, změna směru uvnitř průchodu,
- matematicky optimální pořadí (problém obchodního cestujícího); jen cik-cak a pravidla výše,
- čas a rychlost kontroly, robot či manipulátor, pojezd s enkodérem,
- kreslení dráhy myší ve 3D (úpravy jsou v seznamu úseků čísly),
- vliv zón na *Spočítat pokrytí* a návrh poloh (jen upozornění),
- cokoli o zjistitelnosti vad, citlivosti nebo signálech (mimo vymezení),
- změna geometrie dílu (etapy 14–15).

## 11. Praktická zkouška pro autora (po 10B)

1. Otevři ukázku V svaru (*NDT – cílové objemy*), přilož sondu shora vpravo směrem ke svaru
   a stiskni **Naplánovat dráhu**. Úseky musí začínat u převýšení a pokrytí plánu musí být
   stejné jako *Spočítat pokrytí*. Pak **Přehrát**.
2. Přidej zakázanou zónu přes kus pásu. Dráha ji musí obejít nebo sondu přestavit a žádná
   poloha nesmí být v zóně.
3. Smaž úsek a dej *Zpět*.
4. Ulož, zavři a otevři. Plán tam je. Změň tloušťku plechu a plán bude „zastaralý“.

## 12. K rozhodnutí

1. **Plán a zóny se ukládají do studie**, formát 18; výsledek pokrytí se neukládá.
   *Doporučeno: ano.* (Bez uložení by se zóny i ruční úpravy po zavření ztratily.)
2. **Skladba dráhy:** průchody → řádky → úseky, dva vzory (k cíli a zpět / podél), výchozí
   *automaticky* podle přestavení, délky a počtu řádků. *Doporučeno: ano.*
3. **Rozteč = krok výpočtu** (výchozí 5 mm), řádek = spojitě projetý pás šířky rozteče jako
   v etapě 06. Pokrytí stávajícím výpočtem z poloh plánu (malé rozšíření výpočtu, dnešní
   výsledky beze změny). *Doporučeno: ano.*
4. **Kontrola celé dráhy po 1 mm**; přesun po povrchu jen přes platné polohy, jinak
   přestavení. *Doporučeno: ano.*
5. **Nájezd kolmo k ploše**, výchozí výška **20 mm** (0 = nekontrolovat). *Doporučeno: ano.*
6. **Zakázané zóny** jako kvádry, platí pro plán. Ruční přiložení jen upozorní, pokrytí
   a návrh poloh je zatím nezohlední. *Doporučeno: ano.*
7. **Hodnocení** pokrytí, délky, přestavení a robustnosti bez souhrnného skóre; odolnost
   posunem jen na zaškrtnutí. *Doporučeno: ano.*
8. **Ruční úpravy** v seznamu úseků (smazat, zkrátit, obrátit, přeřadit, přidat z přiložené
   sondy), každá jeden krok Zpět; bez kreslení myší. *Doporučeno: ano.*
9. **Přehrávání** s narůstající mapou, tabulka poloh a CSV. *Doporučeno: ano.*
10. **CLI `skodacad draha`**, AI bez nového nástroje. *Doporučeno: ano.*

Schválením se **neschvaluje**: zakřivené plochy, natáčení sondy, změna výpočtu přiložení
a paprsku, nová knihovna Pythonu ani sloučení do `main`.

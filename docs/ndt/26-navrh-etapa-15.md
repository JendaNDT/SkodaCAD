# NDT – návrh etapy 15: Konstrukční návrhy bez automatické změny dílu

Stav: **schváleno autorem 20. 10. 2026 („schvaluji etapu 15 včetně doporučení 1–12“);
implementace po krocích ve vývojové větvi; 15A.0, 15A.1 a 15A.2 otestované; 15B implementováno a čeká na finální CI a ruční zkoušku.**
Výchozí stav: `main`, commit `94a78d7` ([PR #28](https://github.com/JendaNDT/SkodaCAD/pull/28)).
Navazuje na [plán, etapa 15](03-implementacni-plan.md), na starší návrh
[v0.2, oddíly 9 a 20](02-navrh-v0.2.md), na závazná vymezení
[UT](04-zavazne-vymezeni-ut.md) (bod 3: doporučení změny geometrie optimalizují **jen
přístupnost a geometrické pokrytí**), [PT](20-vymezeni-pt.md), [MT](22-vymezeni-mt.md)
a [RT](24-vymezeni-rt.md) a na hotové etapy [09](17-navrh-etapa-09.md),
[10](18-navrh-etapa-10.md) a [14](25-navrh-etapa-14.md).

Etapa 15 **dokončí milník M5 – společný audit a konstrukční doporučení**. Etapa 14 říká, kde
je problém. Etapa 15 zkusí, **jestli by pomohla změna rozměrů dílu**, a varianty porovná.
Díl sama nikdy nezmění.

Zadání z plánu:

- **Úkoly:** *„Vygenerovat kandidáty úprav vybraných parametrů modelu: posun žebra, zvětšení
  přístupu, úprava okolí svaru. Stanovit zamčené rozměry, technologické a pevnostní podmínky,
  limity změny; bez těchto vstupů návrh jen informativní. Každou variantu přepočítat a NDT
  vyhodnotit stejnými nastaveními. Zobrazit původní/novou geometrii, pokrytí a dopady na objem
  a hmotnost. Nikdy neprovádět změny bez schválení.“*
- **Výstup:** *„Srovnání konstrukčních variant, ne autonomní překreslování.“*
- **Podmínka dokončení:** *„Původní soubor se nemění; návrh lze odmítnout; při zamčené kótě
  změna neprojde.“*

## Co tato etapa přinese

**Dnes:**

- Audit (etapa 14) ukáže problémová místa, ale neřekne, co by s nimi udělala změna dílu.
- Chceš-li zkusit „větší kapsu“, musíš ručně měnit parametr, potvrzovat studie, počítat znovu,
  zapisovat si čísla a pak vše vracet zpět Zpět/Znovu. Snadno se splete, která čísla patří ke
  které variantě, a nic nehlídá rozměry, které se měnit nesmějí.

**Po etapě 15:**

1. V nabídce **NDT → Konstrukční návrh…** se otevře panel. V něm zadáš:
   - **cílovou studii** (např. „MT dna kapsy“),
   - **které parametry se smějí měnit** a na jaké hodnoty (např. `a` = 40, 60, 80, 100),
   - **zamčené rozměry** – uložená měření, která se změnit nesmějí,
   - **podmínky** – uložené měření s mezí a důvodem (např. „tloušťka stěny kapsy ≥ 15 mm –
     pevnost, zadal konstruktér“), limit změny hmotnosti.
2. **Spustit návrh.** Na pozadí se postupně přepočítá každá varianta (kopie modelu) a cílová
   studie se spočítá **stejným nastavením** jako u původního dílu. *Zastavit* nechá hotové
   varianty.
3. **Tabulka variant**: původní díl (vždy první řádek) a varianty s výsledkem v % i mm²,
   změnou objemu a hmotnosti a stavem: **prošla** / **neprošla – proč** / **nelze vyhodnotit –
   proč**.
4. Klik na variantu = **náhled**: ve 3D se ukáže díl varianty s mapou cílové studie a původní
   díl průhledně. Model se přitom nemění.
5. **Použít variantu…** (po potvrzení, jeden krok Zpět) nebo **Uložit variantu jako…** (nový
   soubor – původní zůstane). **Odmítnout** = nic, model se nezměnil.
6. **Zpráva** „Konstrukční návrh pro NDT – srovnání variant“ (HTML, CSV, z okna i PDF)
   s výrazným označením **„Návrh ke konstruktérskému posouzení“**.
7. Příkaz **`skodacad navrh`** udělá totéž bez okna.

## 1. Rozsah a hranice

**Návrh SMÍ:**

- měnit **jen kopie** modelu v paměti a jen **číselné parametry**, které uživatel povolil,
- každou variantu přepočítat a spočítat stávajícími výpočty NDT se stejným nastavením,
- zkontrolovat zamčené rozměry a podmínky, které zadal uživatel,
- varianty seřadit podle geometrické přístupnosti / pokrytí cílové studie a velikosti změny.

**Návrh NESMÍ:**

- **změnit model ani soubor sám** – změna jen tlačítkem *Použít variantu…* po potvrzení,
- tvrdit cokoli o **pevnosti, únavě, technologii výroby nebo funkci** dílu. Program je
  nepočítá. Hlídá jen podmínky, které zadal uživatel, a to jen geometricky (měřením),
- slibovat **lepší detekci vad** – optimalizuje se jen geometrická přístupnost a pokrytí
  (závazné vymezení UT, bod 3; obdobně PT, MT, RT),
- měnit **cílové objemy, projekce RT, zakázané zóny ani nastavení studií** – ty zůstávají,
  jak jsou (jinak by srovnání nebylo „stejným nastavením“),
- vybrat metodu, postup nebo napsat „vyhovuje“.

**Nejdřív postup, pak díl.** Starší návrh (v0.2, oddíl 9) říká: nejdřív zkusit jinou plochu,
směr, sondu nebo dráhu, teprve pak měnit díl. Panel to připomene větou nahoře: *„Než změníš
díl: zkus návrh poloh, plán dráhy nebo jiné nastavení metody.“* Automaticky to nezkouší –
na to jsou etapy 09 a 10.

**Povinné texty** (v panelu, zprávě i CSV, doslova):

- obecné upozornění `ndt.DISCLAIMER` a povinné upozornění metody cílové studie (a dalších
  zahrnutých studií),
- nová věta (konstanta `DESIGN_NOTE`): *„Návrh ke konstruktérskému posouzení. Program
  posuzuje jen geometrickou přístupnost a pokrytí pro NDT. Pevnost, únavu, technologii výroby
  a funkci dílu neposuzuje – hlídá jen zamčené rozměry a podmínky zadané uživatelem. Změnu
  dílu musí schválit odpovědný konstruktér.“*
- bez zamčených rozměrů a podmínek navíc u každé varianty: *„informativní – bez zadaných
  podmínek“*.

## 2. Zadání návrhu

| Položka | Co to je | Poznámka |
|---|---|---|
| **Cílová studie** | jedna NDT studie dílu, jejíž výsledek se má zlepšit | UT jen s uloženým plánem dráhy (oddíl 3) |
| **Měněné parametry** | 1–3 **číselné** parametry modelu; hodnoty výčtem (`40, 60, 80, 100`) nebo rozsahem s krokem (`40–100 po 20`) | parametr zadaný výrazem (`a/2 + 5`) přímo měnit nejde – mění se sám s ostatními |
| **Varianty** | všechny kombinace hodnot, **nejvýš 24** | pevné pořadí, žádné náhodné hledání |
| **Zamčené rozměry** | uložená měření (panel *Měření* → *Uložit*), např. rozteč děr, délka dílu | změna o víc než 0,01 mm (0,01°) = **neprojde** |
| **Zamčené parametry** | parametry, jejichž **hodnota** se nesmí změnit (i výrazy) | hlídá řetězení výrazů |
| **Podmínky** | uložené měření + mez (`≥`, `≤`, `mezi`) + důvod (text) | např. stěna ≥ 15 mm „pevnost“, mezera ≥ 25 mm „hořák“ |
| **Změna hmotnosti** | nejvýš ± X % proti původnímu dílu | nepovinné |
| **Mapa tloušťky** | „nikde pod mezí mapy“ (jen když má model mez) | nepovinné, sekundy navíc |
| **Ostatní studie** | spočítat i ostatní studie dílu (zda změna jinde neuškodí) | výchozí vypnuto, s odhadem doby |
| **Ověřit pořadí** | nejlepší 3 varianty + původní znovu jemnějším krokem (oddíl 5) | výchozí zapnuto |

**Proč uložená měření.** Měření se ukládají **významem** (plocha u bodu, se směrem, typ
plochy) a spočítají se znovu s každou změnou dílu. Hodí se proto přesně na „kóty, které se
nesmí změnit“ i na podmínky – a jsou ve zprávě dohledatelná. Měření, které ve variantě nejde
spočítat (plocha zmizela), znamená **neprojde** – nikdy „asi v pořádku“.

## 3. Jak se varianta vyhodnotí („stejné nastavení“)

Pro každou variantu, jedna po druhé, v pomocném procesu:

1. **Kopie modelu** s novými hodnotami parametrů. Původní model se nemění.
2. **Přepočet dílu.** Chyba prvku nebo neplatné těleso → *nelze vyhodnotit – „prvek Kapsa: …“*.
3. **Zámky a podmínky** (rychlé, před NDT): zamčené parametry, zamčená měření, podmínky,
   změna hmotnosti, případně mapa tloušťky. Nesplněno → **neprošla** s důvodem
   („zamčená kóta *Rozteč děr* 80,00 → 86,00 mm“). NDT se u ní spočítá jen informativně, když
   je zapnuto *Spočítat i neprošlé* (výchozí zapnuto – konstruktér tak vidí, co by změna
   dala a proč nejde).
4. **Studie v kopii:** oblast se znovu najde **významem** (jako při *Potvrdit*, ale jen
   v kopii – originál zůstane nepotvrzený). Nenajde-li se → *nelze vyhodnotit*. Posunutá
   plocha se uvede („plocha oblasti posunuta o 12 mm“).
5. **Výpočet NDT** stávajícím výpočtem (jako audit, etapa 14), se stejným nastavením:
   - **PT, MT, RT:** nastavení studie, **kroky sítě zamčené podle původního dílu** (automatický
     krok se jinak řídí velikostí oblasti a u každé varianty by vyšel jinak),
   - **RT:** projekce zůstávají v prostoru tam, kde jsou (zaměřený bod, směr, vzdálenost),
   - **UT:** studie musí mít **uložený plán dráhy** (etapa 10). Ve variantě se plán
     **sestaví znovu se stejnými průchody, roztečí, vzorem a zónami** a spočítá se pokrytí.
     Volba *jen ověřit uložený plán* (rychlejší) zjistí, zda tentýž plán na nové geometrii
     ještě projde. Návrh poloh (etapa 09) se pro varianty nespouští – na desce trval přes 22
     minut.
   - **Cílový objem svaru** zůstává, jak je zadaný čísly. Když by z varianty vyčníval,
     varianta je *nelze vyhodnotit*. Ověřeno: ukázka *tupý svar – objem* s nižším převýšením
     h = 1 mm (cíl má převýšení 2,0 mm napevno) → studie má neplatnou vazbu *„Zadaný svar
     není celý v materiálu dílu – chybí 1700 mm³“*. Cíl, který by se měnil s parametry, je mimo
     etapu 15.
6. **Výsledek varianty:** podíl stavů v % **i v mm² / mm³**, velikost oblasti studie,
   „nelze spolehlivě vyhodnotit“, problémová místa (jako audit), objem, hmotnost, změněné
   parametry, splněné/nesplněné podmínky, doba výpočtu.

## 4. Pokusy na referenčních dílech (20. 10. 2026, cloud)

Abych návrh nepsal naslepo, zkusil jsem varianty ručně stávajícími výpočty. Pro rychlost
s „rychlým“ nastavením studií (stejným jako v testech).

**Kapsa (`kapsa.json`), MT dna kapsy** – blok 120 × 80 × 40, kapsa a × b, hloubka 25;
síť 6 mm, středy jha po 12 mm, bez nanesení a prohlídky. Stěna X = (120 − a)/2,
stěna Y = (80 − b)/2.

| a × b | Stěna X / Y | Dno kapsy | Jen část orientací | Nepokryto | Doba |
|---|---|---|---|---|---|
| **40 × 30 (původní)** | 40 / 25 mm | 1 200 mm² | 0 % | 100 % | 6,9 s |
| 60 × 40 | 30 / 20 mm | 2 400 mm² | 0 % | 100 % | 7,0 s |
| 80 × 60 | 20 / 10 mm | 4 800 mm² | 0 % | 100 % | 6,2 s |
| 90 × 60 | 15 / 10 mm | 5 400 mm² | 0 % | 100 % | 7,5 s |
| 96 × 40 | 12 / 20 mm | 3 840 mm² | 25,0 % | 75,0 % | 10,2 s |
| 100 × 40 | 10 / 20 mm | 4 000 mm² | **0 %** (středy po 12 mm) / **53,1 %** (po 6 mm) | 100 / 46,9 % | 7,2 / 30,3 s |
| 100 × 60 | 10 / 10 mm | 6 000 mm² | 56,6 % | 43,4 % | 13,9 s |
| 100 × 70 | 10 / 5 mm | 7 000 mm² | 57,4 % | 42,6 % | 14,8 s |

„Pokryto ve všech orientacích“ nevyšlo v žádné variantě. Co z pokusu plyne:

- **Jho potřebuje kapsu dlouhou zhruba 96–100 mm** (rozteč pólů 75–100 mm + póly). Šířka
  kapsy skoro nehraje roli. Takovou kapsu ale obklopují stěny tlusté jen 10–12 mm. S podmínkou
  „stěna ≥ 15 mm“ by **žádná prošlá varianta MT nezlepšila** – a přesně to má návrh poctivě
  říct: *„V povolených mezích se výsledek nezlepšil. Nejlepší neprošlá varianta: a = 100
  (56,6 % jen část orientací), neprošla: stěna X 10 mm < 15 mm.“*
- **Krok výpočtu umí otočit pořadí.** Kapsa 100 × 40 vyšla se středy jha po 12 mm na 0 %,
  po 6 mm na 53,1 % (u 96 × 40 obě kroky shodně 25 %). Mřížka středů platné polohy jha
  mezi uzly mine (známá past etapy 12). Proto se kroky zamykají podle původního dílu a nejlepší
  varianty se ověří jemnějším krokem (oddíl 5).

**Kapsa, PT dna a stěn** – hloubka kapsy h, síť 8 mm:

| h | Plocha studie | Přístupné | Omezené | Nepřístupné | Doba |
|---|---|---|---|---|---|
| **25 (původní)** | 4 700 mm² | 53,9 % (2 531 mm²) | 34,3 % (1 612 mm²) | 11,8 % (556 mm²) | 22,3 s |
| 15 | 3 300 mm² | 49,0 % (1 617 mm²) | 37,9 % (1 252 mm²) | 13,1 % (431 mm²) | 16,4 s |
| 10 | 2 600 mm² | 43,0 % (1 119 mm²) | 40,1 % (1 044 mm²) | 16,8 % (438 mm²) | 12,1 s |

Mělčí kapsa vyjde v **procentech hůř**, ačkoli nepřístupná plocha v mm² **klesla** (556 → 431
mm²). Zmenšila se totiž sama kontrolovaná plocha (kratší stěny) a pás v rohu u dna zůstal.
Proto tabulka variant ukáže **% i mm²** a velikost oblasti. Když se oblast studie změní o víc
než 5 %, napíše: *„oblast studie se změnila o −45 % – porovnávej i mm²“*.

**Deska se žebrem (`zebro.json`), UT** – ručně spočitatelný případ pro testy. Úhlová sonda
45° s rezervou 5 mm míří pod osu žebra (t = 20 mm): výstupní bod je 20 mm od osy, čelo sondy
8 mm. Žebro tloušťky s se proto vejde jen pro s/2 + 5 ≤ 8, tj. **s ≤ 6 mm** (dnes s = 10,
referenční díly: „chybí 2 mm“). Ztenčení žebra je ale typicky pevnostní otázka – ukázka pro
podmínku „s ≥ 8 mm – pevnost“, se kterou varianta s = 6 **neprojde**.

**4a. Vedlejší nález – tiše ztracený tvar ve skice (chyba, mimo etapu 15).** Ukázka *tupý
svar – objem* s převýšením h = 0 má objem přesně **360 000 mm³** (samotné plechy 300 × 100
× 12), správně by to bylo **360 500 mm³** (plechy + podkořen 5 mm² × 100 mm). Mnohoúhelník
převýšení má při h = 0 nulovou plochu a skica tiše zahodí **i druhý tvar** (podkořen).
Všechny prvky přitom hlásí „ok“. Pro h = 2 / 1 / 0,5 mm vychází objem správně (363 900 /
362 200 / 361 350 mm³). Návrh variant zkouší krajní hodnoty, takže tichá chyba geometrie by
dala nesmyslné srovnání. **Doporučuji opravu jako první krok 15A.1:** tvar skici s nulovou
plochou = česká chyba prvku („tvar 1 skici má nulovou plochu – zkontroluj rozměry“), nikdy
tiché zahození ostatních tvarů. Test s objemem podle vzorce.

**Doby.** Přepočet dílu varianty: 0,02–0,06 s. Výpočet NDT s výchozím nastavením (etapa 14):
PT 17–87 s, MT 46–100 s, RT 3–20 s; UT nové sestavení plánu V svaru 60–197 s (etapa 10).
Příklad: kapsa, MT, 8 variant × ~1 min + ověření 4 výpočtů jemnějším krokem (~4× déle) ≈
**25 minut**. Proto odhad před spuštěním, výpočet na pozadí, *Zastavit* a limit 24 variant.

## 5. Výsledek a pořadí variant

**Stav varianty:**

| Stav | Kdy |
|---|---|
| **Prošla** | díl se přepočítal, zámky a podmínky splněné, studie spočítaná |
| **Neprošla – důvod** | zamčená kóta nebo parametr se změnil, podmínka nesplněna, hmotnost mimo limit. Výsledek NDT jen „informativně“ (je-li zapnuto) a *Použít variantu* nejde |
| **Nelze vyhodnotit – důvod** | prvek dílu chyba, oblast studie se nenašla, cíl vyčnívá, plán nejde sestavit, výpočet skončil chybou, nebo byl zastaven |

**Pořadí** (bez jednoho „skóre“, jako etapy 09 a 10):

1. prošlé varianty před neprošlými, nevyhodnocené na konec,
2. podíl dobrého stavu cílové studie v % (UT geometricky pokryto, PT přístupné, MT pokryto
   ve všech orientacích, RT promítne se – geometrická pravidla platí); při shodě podíl
   „omezeně / jen část“,
3. menší „nelze spolehlivě vyhodnotit“,
4. menší změna parametrů (součet relativních změn),
5. menší změna hmotnosti.

**Původní díl** je vždy první řádek, spočítaný ve stejném běhu stejným nastavením. Varianta
horší než původní je v tabulce šedě.

**Ověření pořadí jemnějším krokem** (výchozí zapnuto): původní díl a nejlepší 3 prošlé
varianty se spočítají znovu s polovičním krokem (MT: krok středů jha, PT a RT: krok sítě, UT:
rozteč řádků a krok cíle). Když se pořadí změní nebo rozdíl klesne pod 2 procentní body:
*„pořadí nejisté – rozhoduje krok výpočtu“*. Je to zkouška, ne důkaz (stejně jako citlivost na
krok v etapách 06–07).

## 6. Náhled, použití a odmítnutí

- **Náhled varianty** (klik v tabulce): ve 3D díl varianty s mapou cílové studie, původní díl
  průhledně (stávající kresba průhledného tělesa – žádný nový druh kreslení). Panel ukáže
  pruh *„Náhled varianty V3 – model se nezměnil“*. Jakákoli úprava modelu náhled ukončí.
- **Použít variantu…** – jen u prošlé varianty, po potvrzení v dialogu se seznamem změn
  (`a: 40 → 90`, `b: 30 → 60`) a větou `DESIGN_NOTE`. Změní parametry v otevřeném modelu
  **jedním krokem Zpět**. Soubor se uloží, až když ho uložíš. NDT studie budou potom
  zastaralé – potvrdíš je jako po každé změně dílu (návrh je sám nepotvrdí).
- **Uložit variantu jako…** – nový soubor s parametry varianty. Otevřený model ani původní
  soubor se nemění.
- **Odmítnout** – zavřít výsledek. Protože se nic neměnilo, není co vracet.

## 7. Zpráva

„**Konstrukční návrh pro NDT – srovnání variant**“, s pruhem **„Návrh ke konstruktérskému
posouzení“**. Obsah:

- povinné texty (oddíl 1), hlavička jako u auditu (model, otisk dílu, materiál, sestavení
  aplikace, knihovny, zpracoval),
- **zadání**: cílová studie, měněné parametry a hodnoty, zamčené rozměry a parametry,
  podmínky s důvody, limity, kroky výpočtu,
- **tabulka variant** (stav, parametry, výsledek v % a mm², nejisté, objem a hmotnost,
  podmínky, ostatní studie, doba),
- u každé varianty: změněné parametry, hodnoty zamčených měření a podmínek, důvod neprošla /
  nelze vyhodnotit, problémová místa cílové studie, záznam studie,
- závěrečná věta, co zpráva neobsahuje (pevnost, technologie, funkce, schválení).

Složka: `navrh.html`, `varianty.csv`; z okna navíc `navrh.pdf` a obrázky variant ze 3D.
Stejné řešení jako zpráva auditu (HTML a PDF přes Qt), žádná nová knihovna.

## 8. Okno

- **NDT → Konstrukční návrh…** otevře panel *Konstrukční návrh* (vedle panelu NDT a auditu):
  - věta „Než změníš díl…“ a povinné texty,
  - **zadání**: cílová studie (nabídka), tabulka měněných parametrů (název, hodnoty), seznam
    uložených měření se zaškrtnutím „zamknout“ a s podmínkou (≥ / ≤ / mezi, hodnota, důvod),
    limit hmotnosti, volby *i ostatní studie*, *spočítat i neprošlé*, *ověřit pořadí*,
    u UT *sestavit plán znovu / jen ověřit*,
  - počet variant a **odhad doby**, **Spustit návrh** / **Zastavit** s průběhem,
  - **tabulka variant**, klik = náhled, **Použít variantu…**, **Uložit variantu jako…**,
    **Exportovat zprávu…**, **Ukončit náhled**.
- Zadání se ukládá do modelu (oddíl 10), takže jde příště zopakovat.
- Během práce AI je panel zamčený (jako ostatní).

## 9. Příkazová řádka a AI

- `skodacad navrh MODEL [--studie s3] [--parametr a=40,60,80,100] [--parametr b=30:70:20]
  [--zamek m1] [--podminka "m2>=15:pevnost"] [--hmotnost 10] [--slozka cesta]
  [--ulozit]` – bez voleb použije zadání uložené v modelu. Vypíše tabulku variant s povinnými
  texty a uloží složku se zprávou. `--ulozit` uloží zadání do modelu.
- **AI asistent** nový nástroj nedostane. Nové pravidlo (`assistant.RULES`): čísla variant
  si nevymýšlí, variantu nepoužije bez výslovného přání uživatele a nikdy netvrdí, že je
  změna pevnostně nebo technologicky v pořádku.

## 10. Uložení do souboru (formát 22)

Zadání návrhu se uloží do sekce `ndt` jako `design` – jedno zadání na model:

```json
"design": {
  "study": "s3",
  "parameters": [{"name": "a", "values": [40, 60, 80, 100]},
                 {"name": "b", "from": 30, "to": 70, "step": 20}],
  "locked": {"measurements": ["m1"], "parameters": ["A"]},
  "conditions": [{"measurement": "m2", "min": 15, "reason": "pevnost stěny – konstruktér"}],
  "mass_change_pct": 10,
  "options": {"others": false, "rejected": true, "verify": true, "ut": "rebuild"}
}
```

- **Formát 22**, soubory verze 1–21 se načtou beze změny. Neznámý parametr, měření nebo
  studie = česká chyba při načtení i v dialogu.
- **Výsledky variant se neukládají** – jsou pohled jako audit (po změně modelu zmizí).
- Nový **referenční díl 10 `navrh_kapsa.json`**: kapsa s MT studií, uloženým měřením tloušťky
  stěny kapsy a zadáním „a = 40–100, b = 30–70, stěna ≥ 15 mm“. Existující ukázky se nemění
  (testy na ně spoléhají).

## 11. Ověření před předáním

1. **Původní soubor se nemění:** po návrhu je dokument i soubor totožný, žádný krok Zpět;
   *Uložit variantu jako…* nový soubor, starý beze změny.
2. **Zamčená kóta neprojde** (ručně spočitatelné):
   - `pristup.json` s uloženým měřením vnější rozteče žeber m + 2s = 50 mm: varianta m = 40,
     s = 10 (60 mm) **neprojde**; m = 34, s = 8 (50 mm) **projde**,
   - zamčený parametr zadaný výrazem, který se změní přes jiný parametr, **neprojde**.
3. **Podmínka:** kapsa se stěnou ≥ 15 mm – a = 90 projde (15 mm), a = 100 neprojde (10 mm).
   Měření, které ve variantě nejde spočítat → neprojde.
4. **Stejné nastavení:** varianta s původními hodnotami dá stejný výsledek jako studie
   v panelu (MT kapsa, PT kapsa, RT deska s otvorem). Kroky sítě zůstávají podle původního
   dílu.
5. **UT, deska se žebrem:** 45° s rezervou 5 mm – cíl pod osou žebra dosažitelný jen pro
   s ≤ 6 mm (ručně, oddíl 4); s podmínkou „s ≥ 8 mm“ varianta s = 6 neprojde.
6. **% a mm²:** PT kapsa h = 25 / 15 / 10 – upozornění na změnu oblasti, mm² v tabulce.
7. **Pořadí a ověření krokem:** pořadí podle pravidel z oddílu 5; kapsa 100 × 40 s hrubým
   krokem středů → „pořadí nejisté“.
8. **Nelze vyhodnotit:** chyba prvku, oblast studie se nenajde, cíl svaru vyčnívá
   (tupý svar – objem, h = 1 mm: chybí 1700 mm³), skica s nulovou plochou (oddíl 4a).
9. **Použití:** *Použít variantu* = jeden krok Zpět, Zpět vrátí původní parametry; neprošlou
   variantu použít nejde.
10. **Rozsah:** povinné texty doslova v panelu, zprávě i CSV; žádné zakázané označení;
    slova „vyhovuje“ a „pevnostně v pořádku“ ve zprávě nejsou.
11. **Okno:** offscreen testy (zadání, odhad, běh, zastavení, tabulka, náhled, použití,
    uložení, export, zámek AI), snímky pod Xvfb, GitHub Actions Windows i macOS. Testy krátké
    – rychlé nastavení a 2–3 varianty.

## 12. Malé kroky po schválení

| Krok | Výstup | Ověření |
|---|---|---|
| **15A.1 – jádro návrhu** | oprava skici s nulovou plochou (oddíl 4a); `ndt/design.py`: kontrola zadání, generování variant, zámky a podmínky přes uložená měření, vyhodnocení varianty na kopii (přepočet, ukotvení studie, výpočet jako audit se zamčenými kroky), pořadí, ověření jemnějším krokem, souhrn, CSV, zpráva HTML | testy 2–8, 10 |
| **15A.2 – spuštění** | formát 22 (`ndt.design`), `ModelSession` (zadání = jeden krok Zpět, odhad, výpočet na pozadí po variantách, *Zastavit*, použít / uložit variantu, export), pomocný proces, `skodacad navrh`, referenční díl 10, AI pravidlo, README | testy 1, 9 |
| **15B – okno** | panel *Konstrukční návrh*, dialog zadání, náhled varianty ve 3D, použití, uložení, export s PDF a obrázky, self-test | test 11, snímky, balíčky Windows a macOS |

Každý krok zvlášť: `ruff`, `pytest`, commit. Do `main` až na tvůj pokyn.

## 13. Co etapa 15 nebude

- změny dílu bez potvrzení, změny původního souboru,
- výpočet pevnosti, únavy, technologičnosti nebo funkce,
- změna cílových objemů, projekcí RT, zón nebo nastavení studií s variantou,
- návrh poloh (etapa 09) pro každou variantu,
- náhodné, evoluční nebo spojité hledání optima – jen pevná mřížka hodnot,
- změny geometrie mimo parametry (přímé úpravy ploch – fáze 4),
- výukové vady a signály (etapa 16).

## 14. Praktická zkouška pro autora (po 15B)

1. Otevři *NDT – referenční díly → Návrh: kapsa pro jho* a dej **NDT → Konstrukční
   návrh…**. Zadání už je vyplněné (a, b, stěna ≥ 15 mm).
2. **Spustit návrh** (odhad se ukáže předem). Tabulka: původní kapsa, varianty a = 40–100.
3. Najdi variantu a = 100: **neprošla – stěna 10 mm < 15 mm**, informativně MT asi 55 %
   jen část orientací. Prošlé varianty MT nezlepšily – panel to napíše.
4. Klikni na variantu – ve 3D je větší kapsa s mapou MT a původní díl průhledně. Model se
   nezměnil (název okna bez hvězdičky).
5. Odškrtni podmínku stěny, spusť znovu, použij variantu a = 100 (**Použít variantu…**),
   pak **Zpět** – kapsa je zase původní.
6. **Exportovat zprávu…** a otevři `navrh.pdf`: nahoře „Návrh ke konstruktérskému
   posouzení“, zadání, tabulka variant.

## 15. K rozhodnutí

1. **Název a hranice:** „Konstrukční návrh pro NDT – srovnání variant“, vše označené
   „Návrh ke konstruktérskému posouzení“ (`DESIGN_NOTE` doslova). Optimalizuje jen
   geometrickou přístupnost a pokrytí; pevnost, únavu, technologii a funkci nepočítá.
   Model ani soubor se nikdy nezmění sám. *Doporučeno: ano.*
2. **Varianty = číselné parametry modelu:** 1–3 parametry, hodnoty výčtem nebo rozsahem,
   všechny kombinace, nejvýš 24 variant, pevné pořadí (žádné náhodné hledání).
   *Doporučeno: ano.*
3. **Zamčené rozměry = uložená měření** (změna nad 0,01 mm / 0,01° → neprojde; měření, které
   nejde spočítat → neprojde) a zamčené parametry (hlídá výrazy). *Doporučeno: ano.*
4. **Podmínky** = uložené měření + mez + důvod, limit změny hmotnosti, volitelně mapa
   tloušťky. Bez zámků a podmínek je každý výsledek „informativní“. *Doporučeno: ano.*
5. **Stejné nastavení:** kopie modelu, oblast studie znovu ukotvená jen v kopii, nastavení
   studie beze změny, **kroky sítě zamčené podle původního dílu**; cíle svaru, projekce RT
   a zóny zůstávají na místě. *Doporučeno: ano.*
6. **UT jen s uloženým plánem dráhy:** ve variantě se plán sestaví znovu se stejnými
   průchody a nastavením (volba: jen ověřit uložený plán). Návrh poloh pro varianty ne.
   *Doporučeno: ano.*
7. **Cílová studie** vždy, **ostatní studie** volitelně (výchozí vypnuto, s odhadem).
   Neprošlé varianty se spočítají informativně (výchozí zapnuto, jde vypnout).
   *Doporučeno: ano.*
8. **Pořadí bez skóre:** prošlé → podíl dobrého stavu v % → nejisté → menší změna parametrů
   → menší změna hmotnosti; vždy i mm²/mm³ a upozornění při změně oblasti o víc než 5 %.
   Původní díl vždy první řádek. *Doporučeno: ano.*
9. **Ověření pořadí poloviční krokem** u původního dílu a 3 nejlepších variant (výchozí
   zapnuto); jinak „pořadí nejisté – rozhoduje krok výpočtu“. *Doporučeno: ano.*
10. **Náhled, použití, odmítnutí:** náhled je jen pohled; *Použít variantu…* jen u prošlé
    varianty po potvrzení, jeden krok Zpět, studie pak potvrdí uživatel; *Uložit variantu
    jako…* nový soubor. *Doporučeno: ano.*
11. **Zadání v modelu** (`ndt.design`, **formát 22**), výsledky jen pohled; zpráva HTML/CSV
    (z okna PDF a obrázky); panel *Konstrukční návrh*, `skodacad navrh`, AI bez nového
    nástroje s pravidlem; nový referenční díl 10 `navrh_kapsa.json`. *Doporučeno: ano.*
12. **Oprava tiché chyby skici** (oddíl 4a) jako první krok: tvar s nulovou plochou = česká
    chyba prvku, ne ztracená geometrie. Týká se celého CADu, ne jen NDT. *Doporučeno: ano.*

Schválením se **neschvaluje**:

- změna cílových objemů nebo projekcí s variantou,
- návrh poloh pro každou variantu,
- jiné hledání než pevná mřížka hodnot,
- nová knihovna Pythonu,
- sloučení do `main`.

## 16. Provedení a upřesnění

- **15A.0 (hotovo):** tvar skici s nulovou plochou je česká chyba prvku („Tvar 1 skici
  (mnohoúhelník) má nulovou plochu – zkontroluj jeho rozměry …“) a přidané těleso s nulovým
  objemem je chyba. Tupý svar – objem s h = 0 dřív tiše ztratil podkořen. Test s objemem podle
  vzorce (lichoběžníky převýšení a podkořene).
- **15A.1 (hotovo):** `ndt/design.py`:
  - zadání `Design` (kontrola, zápis do JSON beze ztráty tvaru výčet / rozsah), varianty jako
    všechny kombinace bez původního dílu, nejvýš 24,
  - `baseline` přepočítá původní díl, ověří zadání a **zamkne kroky** podle odhadu původního
    dílu (PT a RT síť, MT síť a středy jha; UT rozteč z uloženého plánu),
  - `evaluate` počítá variantu na kopii modelu: přepočet, zámky a podmínky (uložená měření,
    parametry, hmotnost, mapa tloušťky), studie znovu ukotvená v kopii, výpočet metody
    (UT: plán sestavený znovu se stejnými průchody, nebo jen ověřený),
  - `rank_and_verify` – pořadí bez skóre a ověření původního dílu a 3 nejlepších prošlých
    variant polovičním krokem,
  - `DesignResult` – závěr, tabulka, souhrn pro CLI, CSV, zpráva HTML.
- **Ověřeno (testy a pokusy, cloud):**
  - deska se dvěma žebry (díl 8), zamčená vnější rozteč m + 2s = 50 mm měřením i parametrem
    `w = m + 2*s`: m = 40, s = 10 **neprojde** (60 mm), m = 34, s = 8 projde,
  - kapsa, podmínka stěna X ≥ 15 mm: a = 90 projde (15 mm), a = 100 neprojde
    („10,00 mm (požadováno ≥ 15 mm)“),
  - původní díl jako varianta 0 dá stejná procenta jako mapa MT v panelu se stejnými kroky,
  - tupý svar – objem: h = 0 → *nelze vyhodnotit* (nulová plocha skici), h = 1 → *nelze
    vyhodnotit* (cíl: chybí 1700 mm³),
  - deska se žebrem, UT s plánem (rozteč 25 mm, 45°, rezerva 5 mm): žebro 10 mm → pokryto
    12,5 % dna, žebro 50 mm → 5,08 % a limit hmotnosti ±10 % ho odmítne (+52,2 %),
  - kapsa MT (a = 40 / 96 / 100, b = 30 / 40, podmínka stěna ≥ 12 mm): 5 variant + ověření
    za 142 s; závěr „Nejlepší prošlá varianta V2 (a: 40 → 96; b = 30): pokryto ve všech
    orientacích vad 0,00 %, jen část orientací nebo omezeně 25,00 %“, a = 100 neprošlo
    (stěna 10 mm).
- **Upřesnění proti návrhu:**
  - **Zlepšení** se posuzuje jako pořadí: víc dobrého stavu, **při shodě víc „omezeně“**.
    U MT kapsy je „všechny orientace“ všude 0 % a zlepšení je jen v „jen část orientací“.
    Stejně porovnává i ověření polovičním krokem.
  - MT se ověřuje polovičním **krokem středů jha** (síť míst zůstává) – právě mřížka středů
    pořadí otáčí a poloviční síť by výpočet zdražila 16×.
  - Odhad doby UT je horní mez odhadu plánu (deska se žebrem: odhad 201 s, skutečně 6 s).
  - Obecná hláška „díl se od nastavení studie změnil“ se u variant nevypisuje (ve variantě je
    to samozřejmost); jiné zprávy studie (posunutá plocha) ano.

## Zdroje

- Zadání etapy: [03-implementacni-plan.md](03-implementacni-plan.md), etapa 15 a milník M5.
- [02-navrh-v0.2.md](02-navrh-v0.2.md), oddíl 9 (nejdřív postup, pak díl; vymezit povolené
  parametry, zakázané oblasti a limity; „Návrh ke konstruktérskému posouzení“; pevnost
  a technologie mimo NDT modul) a oddíl 20 (omezená optimalizace, varianty jako oddělené
  návrhy, „vyžaduje schválení konstruktéra“).
- [04-zavazne-vymezeni-ut.md](04-zavazne-vymezeni-ut.md), bod 3 – doporučení změny geometrie
  optimalizují jen přístupnost a geometrické pokrytí.
- [05-referencni-dily.md](05-referencni-dily.md), díl 3 (deska se žebrem, mez s/2 + 12 + r)
  a díl 8 (obtížný přístup).
- [18-navrh-etapa-10.md](18-navrh-etapa-10.md) – změřené doby sestavení plánu (60–197 s).
- [25-navrh-etapa-14.md](25-navrh-etapa-14.md) – změřené doby výpočtů metod, zpráva, stavy.
- CLAUDE.md, Známé pasti (NDT – MT jho): mřížka středů jha pokrytí jen podhodnotí.
- Pokusy z 20. 10. 2026 v cloudu (oddíl 4): kapsa MT a × b, kapsa PT hloubka h, krok středů
  12 / 6 mm – stávající výpočty `compute_ndt_mt` / `compute_ndt_pt` na kopiích modelu.

### Průběh 15A.2 (20. 10. 2026)

Implementace ve větvi `claude/magical-hawking-h944yz`, zatím **neslučovat**:

- JSON formát 22 s `ndt.design`, validace odkazů, zpětná kompatibilita 1–21;
- `ModelSession`: uložit zadání s možností Zpět, odhad, výpočty variant v pomocném procesu, průběh, zastavení se zachováním dokončených variant, výběr/uložení prošlé varianty;
- `BackgroundRebuilder`: zpráva `design` a průběžné předávání variant;
- `skodacad navrh`: číselné varianty, zámky, podmínky, export HTML a CSV;
- referenční díl `examples/ndt/navrh_kapsa.json`, regresní testy, návod a pravidlo AI.

Validace: `tests/test_ndt_design_session.py`, `pytest -q` a `ruff check src tests` ve Windows a macOS GitHub Actions. **Výsledek CI ještě není potvrzen.**

### Průběh 15B (20. 10. 2026)

Ve větvi `claude/magical-hawking-h944yz` přidány:

- `gui/design_panel.py`: dialog zadání, omezení, odhad doby, volby, průběh, tabulka a bezpečné potvrzení změny;
- 3D náhled varianty s průhledným originálem, deaktivace výběru alternativní geometrie pro úpravy původního modelu;
- export HTML/CSV/PDF s obrázky geometrického porovnání, popis rozsahu a omezení výsledků;
- offscreen testy GUI a self-test zabalené aplikace na příkladu č. 10;
- položka NDT → Konstrukční návrh…, zamčení panelu při práci AI a přebírání výsledků výpočtu na pozadí.

**Zatím neslučovat do `main` bez souhlasu autora.** Čeká se na závěrečné CI Windows/macOS a následnou ruční zkoušku.

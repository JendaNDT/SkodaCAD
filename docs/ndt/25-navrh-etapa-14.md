# NDT – návrh etapy 14: Společný předběžný audit, zpráva a vysvětlení

Stav: **schváleno autorem 20. 10. 2026 („schvaluji etapu 14 včetně doporučení 1–10“);
implementace po krocích ve vývojové větvi.**
Výchozí stav: `main`, commit `43187c8` ([PR #27](https://github.com/JendaNDT/SkodaCAD/pull/27)).
Navazuje na [plán, etapa 14](03-implementacni-plan.md), na závazná vymezení
[UT](04-zavazne-vymezeni-ut.md), [PT](20-vymezeni-pt.md), [MT](22-vymezeni-mt.md)
a [RT](24-vymezeni-rt.md) a na hotové etapy [09](17-navrh-etapa-09.md),
[10](18-navrh-etapa-10.md), [11](19-navrh-etapa-11.md), [12](21-navrh-etapa-12.md)
a [13](23-navrh-etapa-13.md).

Etapa 14 **otevírá milník M5 – společný audit a konstrukční doporučení** (etapy 14–15).
Nepřidává žádný nový fyzikální ani geometrický výpočet. Spouští to, co už metody umí,
pro všechny studie jednoho dílu najednou, sjednotí výsledky a sepíše je do jedné zprávy.

Zadání z plánu:

- **Úkoly:** *„Jedno tlačítko ‚Předběžný NDT audit‘: podle zvolených metod najde omezení, ale
  nikdy nevybere normativní postup automaticky. Výsledky podle metody, oblasti, parametrů,
  stupně jistoty a omezení; export čitelného PDF/HTML nebo CSV. Exportovat pouze skutečně
  vypočtené výsledky a rozlišovat neprovedeno/nedostupné/neznámé.“*
- **Výstup:** *„Sdílitelný předběžný protokol a přehled problémových míst.“*
- **Podmínka dokončení:** *„Uživatel dohledá důvod každého nálezu i nastavení, kterým
  vznikl.“*

## Co tato etapa přinese

**Dnes:**

- Každá metoda má vlastní skupinu v panelu NDT, vlastní tlačítko, mapu, souhrn a CSV.
  Výsledky se počítají po jedné studii a nic je nespojuje.
- Neexistuje dokument, který by na jednom místě ukázal, co se u dílu spočítalo, co ne a proč.
- Všechny sestavené aplikace hlásí verzi `0.1.0`. Z výstupu tedy nejde poznat, kterým
  sestavením vznikl.

**Po etapě 14:**

1. V nabídce **NDT → Předběžný NDT audit…** se otevře panel se seznamem všech studií dílu.
   U každé studie panel ukáže:
   - **co se spočítá** (například „mapa PT s nastavením studie“ nebo „ověření uloženého plánu
     dráhy“),
   - **odhad doby**,
   - zaškrtávátko, kterým jde studii z auditu vynechat.
2. Jedno tlačítko **Spustit audit**. Studie se počítají jedna po druhé na pozadí s průběhem.
   *Zastavit* nechá hotové studie ve výsledku, zbylé označí „neprovedeno – zastaveno“.
3. **Přehled:** tabulka studií se stavem auditu (spočítáno / neprovedeno / nedostupné)
   a s výsledkem ve čtyřech barvách (v %), včetně podílu „nelze spolehlivě vyhodnotit“.
4. **Problémová místa:** sousední body mapy se stejným stavem se spojí do jednoho „místa“.
   Každé má barvu, velikost (mm² nebo mm³), polohu, důvody česky (s podílem) a odkaz na studii
   a nastavení, kterým vzniklo. Klik na místo ukáže ve 3D mapu té studie a místo na ní.
5. **Export do složky:**
   - **zpráva HTML** – jeden soubor, otevře se v každém prohlížeči a jde vytisknout,
   - **CSV problémových míst**,
   - **podrobná CSV každé studie** (ta, která už dnes umí panel),
   - z okna navíc **PDF** a do zprávy **obrázky map ve 3D**.
6. **Dohledatelnost:** zpráva obsahuje u každé studie celý její záznam (oblast, sonda, plán,
   nastavení metody), verze algoritmů, kroky, otisk dílu, čas výpočtu a sestavení aplikace
   (commit z GitHubu).
7. Příkaz **`skodacad audit`** udělá totéž bez okna (zpráva HTML a CSV, bez obrázků 3D).

**Co se nemění:** výpočty UT, PT, MT, RT (audit volá přesně ty stávající), formát souboru
(zůstává verze 21), výrobní geometrie. Audit model nemění – žádný krok Zpět.

## 1. Rozsah a hranice

**Audit SMÍ:**

- spustit u studií uživatele výpočty, které metody už umějí, s nastavením uloženým ve
  studii,
- sjednotit výsledky, najít problémová místa a vypsat jejich důvody,
- rozlišit, co se **spočítalo**, co se **neprovedlo** a co je **nedostupné**, a proč.

**Audit NESMÍ:**

- **vybrat metodu ani normativní postup** – počítá jen studie, které založil uživatel, se
  zadanou metodou; nikdy nenapíše „pro tento díl použij UT“,
- vydat **„vyhovuje / nevyhovuje“**, shodu s normou ani způsobilost kontroly,
- doplnit chybějící vstup odhadem (sondu, projekci, materiál) – chybějící vstup = „nedostupné“
  s důvodem,
- tvrdit nic nad rámec vymezení metod – u každé metody ve zprávě platí její povinné
  upozornění doslova.

**Název výstupu.** Plán mluví o „protokolu“. V NDT se ale „protokolem o zkoušce“ obvykle
myslí záznam o skutečně provedené zkoušce podle postupu – metodické normy (např. ISO 17640,
ISO 3452-1, ISO 9934-1, ISO 17636-1) k němu mají vlastní požadavky. Jejich plné texty jsem
neověřoval – jsou placené. Zpráva auditu žádnou zkoušku nepopisuje, jen výpočet nad modelem.
Proto navrhuji název **„Předběžný NDT audit – zpráva o geometrickém posouzení“**
a nepoužívat slova „protokol o zkoušce“, „zkušební protokol“ ani „osvědčení“.

**Povinné texty ve zprávě (nahoře, doslova):**

- obecné upozornění `ndt.DISCLAIMER` („Předběžné posouzení proveditelnosti NDT…“),
- povinné upozornění každé metody, která je ve zprávě (`UT_DISCLAIMER`, `PT_DISCLAIMER`,
  `MT_DISCLAIMER`, `RT_DISCLAIMER`),
- věta: „Zpráva je seznam podnětů k ověření kvalifikovanou osobou. Neobsahuje výběr metody,
  normativní postup ani rozhodnutí o shodě.“

Test rozsahu (`test_ndt_scope.py`) bude hlídat, že zpráva HTML i CSV obsahují upozornění
všech zahrnutých metod a žádné zakázané označení.

## 2. Co audit u každé metody spočítá

| Metoda | Co audit použije | Kdy „neprovedeno“ / „nedostupné“ | Změřená doba (cloud) |
|---|---|---|---|
| **UT** | 1. **uložený plán dráhy** → ověření plánu a pokrytí (jako *Ověřit a spočítat*); 2. jinak **výsledek spočítaný v tomto sezení** (mapa pokrytí z přiložené sondy nebo návrh poloh), pokud platí pro současný díl – zpráva uvede, odkud sonda jela; 3. jinak **neprovedeno** | neprovedeno: studie nemá plán ani spočítaný výsledek (návrh poloh jde zapnout zaškrtnutím, s odhadem doby) | návrh poloh na desce: **přes 22 min** (zastaveno); ověření plánu V svaru: asi 1–3 min (etapa 10) |
| **PT** | mapa PT s nastavením studie | nedostupné: studie bez oblasti, zastaralá, neplatná vazba | 17–87 s |
| **MT** | mapa MT s nastavením studie | nedostupné: navíc nepotvrzený materiál (nerez, neuvedený) nebo neferomagnetický | 46–100 s |
| **RT** | mapa RT se všemi projekcemi studie | nedostupné: studie bez projekce | 3–20 s |
| **Mapa tloušťky stěny** (nepovinně) | jen když má model nastavenou mez `limit`: místa pod mezí jako problémová místa | neprovedeno: model nemá mez | podle dílu |

**Proč UT nespouštět samo.** Návrh poloh zkouší až 40 variant (plocha × směr × úhel ×
odrazy) a u každé počítá celé pokrytí. Na referenční desce (`deska.json`) s výchozím nastavením
běžel déle než 22 minut a zastavil jsem ho. Jedno tlačítko, které by počítalo půl hodiny, by
nebylo použitelné. Audit proto u UT vezme to, co uživatel už připravil (plán dráhy, spočítaný
výsledek). Návrh poloh pustí, jen když ho uživatel výslovně zaškrtne, a předem ukáže odhad
doby (`ndt_access_estimate`).

**Změřeno 20. 10. 2026** (cloud, výchozí nastavení studií v ukázkách, PT + MT + RT):

| Díl | Studie | Doba |
|---|---|---|
| deska | MT | 46 s |
| kapsa | PT, MT | 80 s + 54 s |
| koutový svar | PT, MT | 29 s + 82 s |
| deska s otvorem | RT | 3 s |
| štěrbina (díl 9) | 3 × PT | 17 + 50 + 87 s |
| trubka | MT | 100 s |
| tupý svar – objem | RT | 20 s |

Celý díl tedy běžně **1–3 minuty**. Proto výpočet na pozadí s průběhem a *Zastavit*.

## 3. Stavy auditu

Každá studie dostane jeden stav auditu:

| Stav | Kdy | Ve zprávě |
|---|---|---|
| **Spočítáno** | výpočet proběhl | výsledek ve čtyřech barvách, problémová místa, nastavení |
| **Neprovedeno** | uživatel studii vynechal, audit byl zastaven, nebo chybí volitelný vstup (UT bez plánu a bez zaškrtnutého návrhu poloh) | důvod a co udělat („založ plán dráhy“, „zaškrtni návrh poloh“) |
| **Nedostupné** | studie je zastaralá, neúplná, má neplatnou vazbu; chybí povinný vstup (RT bez projekce, MT bez potvrzeného materiálu); výpočet skončil chybou | důvod česky, u chyby i její text |

**Neznámé** není stav studie, ale stav míst: **„nelze spolehlivě vyhodnotit“** uvnitř
spočítané studie (paprsek přes hranu, nejistá poloha …). Zpráva ho vždy uvede zvlášť
(podíl v % a vlastní problémová místa) a nikdy ho nesloučí s dobrým výsledkem.

Zastaralou studii audit **nepotvrzuje sám**. Potvrzení je rozhodnutí uživatele, že studie pro
změněný díl platí.

## 4. Problémová místa

- **Která místa:** všechna, která nejsou v nejlepším stavu své metody:
  - UT: nepokryto, nelze spolehlivě vyhodnotit,
  - PT: omezené, nepřístupné, nelze spolehlivě vyhodnotit,
  - MT: jen část orientací nebo omezeně, nepokryto, nelze spolehlivě vyhodnotit,
  - RT: omezeně, nepromítne se, nelze spolehlivě vyhodnotit,
  - mapa tloušťky: pod mezí.
- **Jak se spojují:** dva body mapy patří k jednomu místu, když mají stejný stav a leží
  blíž než 1,6 × krok sítě. Důvody se nespojují – místo je vypíše všechny s podílem plochy.
  Tak vznikne například jedno místo „dno kapsy – nepokryto, 1 200 mm², důvod: jho se nevejde
  v žádném směru (100 %)“ místo 1 024 řádků. Spojovat i podle důvodu by nešlo: u štěrbiny
  (PT) mají body různé první důvody (nástřik jen šikmo 364 bodů, nástřik nejde 328, nástroj
  se nevejde 76) a místo by se rozpadlo na kousky.
- **Co se o místě uvede:**
  - označení (např. „S2-03“ = studie s2, třetí místo),
  - metoda a barva stavu,
  - důvody česky s podílem (tytéž, které dnes ukazuje klik do mapy),
  - velikost v mm² nebo mm³ a podíl z oblasti studie,
  - střed a rozsah v mm (souřadnice dílu),
  - odkaz na oddíl zprávy s nastavením studie.
- **Pořadí:** červená → šedá → oranžová, v každé skupině podle velikosti.
- **Barvy:** použijí se stávající barvy map (zelená, oranžová, červená, šedá) a názvy stavů
  každé metody beze změny. Žádné nové „skóre“ ani „závažnost“ se nevymýšlí.

## 5. Zpráva – co v ní bude

1. **Hlavička:**
   - název zprávy, datum a čas,
   - model (název, soubor, otisk dílu), materiál,
   - ŠkodaCAD: verze, sestavení (commit a datum z GitHubu), knihovny (Open CASCADE,
     build123d, Python),
   - nepovinně jméno zpracovatele (pole v okně, do modelu se neukládá).
2. **Povinná upozornění** podle oddílu 1.
3. **Přehled studií:** metoda, název, oblast, stav studie (platná / zastaralá …), ověření
   (`verified`), stav auditu, výsledek ve čtyřech barvách v %, podíl „nelze spolehlivě
   vyhodnotit“, doba.
4. **Problémová místa** všech studií (tabulka podle oddílu 4).
5. **Detail každé studie:**
   - co se spočítalo a odkud (plán dráhy, výsledek ze sezení, nastavení metody),
   - souhrn metody – ty samé řádky jako dnes v panelu a CSV, včetně předpokladů a zdrojů
     hodnot,
   - verze algoritmů (např. `ndt-pt-pristupnost 1`, `ndt-geometrie 1`) a kroky sítí,
   - obrázek mapy ve 3D (jen z okna) a u RT náhled prozařované tloušťky,
   - problémová místa té studie,
   - **celý záznam studie z modelu** (JSON) – tím jde výpočet kdykoli zopakovat.
6. **Neprovedeno a nedostupné:** seznam s důvody a co udělat.
7. **Co zpráva neobsahuje:** výběr metody, normativní postup, rozhodnutí o shodě,
   detekovatelnost vad, dávku ani radiační ochranu.

**Formáty:**

- **HTML** – jeden soubor bez internetu (styl i obrázky uvnitř), dobře se tiskne (A4).
- **CSV problémových míst** – středník a desetinná čárka jako dnešní CSV, nahoře povinná
  upozornění.
- **Podrobná CSV studií** – stávající `write_csv` každé metody (bod po bodu).
- **PDF** – jen z okna. Udělá ho Qt, které už v aplikaci je (`QTextDocument` + `QPdfWriter`),
  bez nové knihovny. Qt umí jen část HTML, PDF proto bude jednodušší než HTML. Plnohodnotné
  PDF jde vždy vytisknout z prohlížeče.

Export uloží všechno do jedné složky, např. `NDT-audit-kapsa-2026-10-20-1430/`.

**Sestavení aplikace.** Úlohy GitHub Actions před sestavením zapíšou do aplikace commit
a datum (`skodacad/_build.py`). Při vývoji se vezme `git describe`, jinak „vývojová verze“.
Údaj se ukáže ve zprávě, v *Nápověda → O aplikaci* a v self-testu.

## 6. Okno

- **NDT → Předběžný NDT audit…** otevře panel *Předběžný NDT audit* (vedle panelu NDT):
  - **seznam studií** se zaškrtávátkem, tím, co se spočítá, a odhadem doby; u UT bez plánu
    navíc zaškrtávátko „i návrh poloh (pomalé, odhad …)“,
  - **Spustit audit** / **Zastavit**, průběh „studie 2 ze 4 – mapa MT, 312 z 1 024 míst“,
  - **přehled** a **tabulka problémových míst**,
  - **klik na místo** vybere studii v panelu NDT, ukáže její mapu ve 3D a místo na ní
    (stávající kresba map a bodů – žádný nový druh kreslení),
  - **Exportovat zprávu…** (složka s HTML, CSV a PDF; obrázky map se pořídí z 3D okna).
- **Mapy z auditu jsou pohled jako dnes:** po změně dílu zmizí. Po auditu jsou mapy všech
  spočítaných studií k dispozici i v jejich skupinách v panelu NDT – není třeba je počítat
  znovu.
- Během práce AI je panel zamčený (jako ostatní).

## 7. Příkazová řádka a AI

- `skodacad audit MODEL [--studie s1 --studie s3] [--navrh-poloh] [--slozka cesta]
  [--zpracovatel "J. N."]` vypíše přehled a problémová místa s povinnými upozorněními a uloží
  složku se zprávou HTML a CSV (bez obrázků 3D, náhledy RT ano).
- **AI asistent** nový nástroj nedostane. Do pravidel (`assistant.RULES`) přibude věta:
  výsledky auditu si nevymýšlí, audit nevydává za shodu s normou ani výběr metody.

## 8. Uložení do souboru

**Nic nového.** Audit používá nastavení uložená ve studiích. Výsledek auditu (mapy, místa,
zpráva) se do modelu neukládá – je to pohled. Trvalým výstupem je exportovaná složka.
Formát zůstává **21**.

## 9. Ověření před předáním

1. **Shoda s metodami:** audit každé studie dá stejná čísla jako výpočet té studie v jejím
   panelu (PT kapsa, MT deska, RT deska s otvorem, PT štěrbina).
2. **Problémová místa na referenčních dílech:**
   - **kapsa, MT:** jedno místo „nepokryto“ na celém dně kapsy (1 200 mm², všech 1 024 bodů
     se stejným důvodem – ověřeno 20. 10. 2026),
   - **deska s otvorem, RT:** dva pruhy „nepromítne se – mimo detektor“ podél dlouhých okrajů
     desky,
   - **štěrbina, PT s2:** jedno místo „nepřístupné“ přes obě stěny štěrbiny (1 600 mm²; stěny
     jsou 1 mm od sebe, krok sítě 2,8 mm) se třemi důvody.
3. **Stavy auditu:** UT bez plánu = neprovedeno s důvodem; zastaralá studie = nedostupné;
   RT bez projekce = nedostupné; zastavený audit = hotové studie zůstanou, zbylé neprovedeno.
4. **Dohledatelnost (podmínka dokončení):** u každého místa v CSV je důvod a studie; každá
   studie ve zprávě má celý svůj záznam, verze algoritmů, kroky a sestavení aplikace. Test:
   z JSON studie ve zprávě se výpočet zopakuje se stejným výsledkem.
5. **Rozsah:** povinná upozornění všech zahrnutých metod doslova v HTML i CSV; žádné
   zakázané označení; slova „vyhovuje“, „protokol o zkoušce“ ve zprávě nejsou.
6. **Model se nemění:** po auditu je dokument totožný, žádný krok Zpět.
7. **Okno:**
   - offscreen testy (seznam, spuštění, zastavení, přehled, místa, klik, export, zámek AI),
   - snímek pod Xvfb,
   - GitHub Actions Windows i macOS.

   Testy krátké – rychlé nastavení studií (limit kroku *Testy* na Windows je 20 min, teď
   běží asi 12 min).

## 10. Malé kroky po schválení

| Krok | Výstup | Ověření |
|---|---|---|
| **14A.1 – jádro zprávy** | `ndt/audit.py`: stavy, převod výsledků metod na jednotná místa, spojování míst, přehled, CSV, zpráva HTML; údaj o sestavení | testy 1, 2, 4, 5 na hotových mapách |
| **14A.2 – spuštění** | `ModelSession` (co se spočítá a odhad, výpočet po studiích, zastavení), pomocný proces, `skodacad audit`, zápis sestavení v GitHub Actions, AI pravidlo | testy 3, 6 |
| **14B – okno** | panel *Předběžný NDT audit*, klik na místo, export složky, PDF, obrázky 3D | test 7, snímky, balíčky Windows a macOS |

Každý krok zvlášť: `ruff`, `pytest`, commit. Do `main` až na tvůj pokyn.

## 11. Co etapa 14 nebude

- výběr metody nebo postupu, shoda s normou, „vyhovuje“,
- nový výpočet (fyzika, jiné modely sond, automatický plán RT projekcí),
- konstrukční návrhy a srovnání variant dílu – to je etapa 15,
- elektronický podpis zprávy (ověření studie osobou už je – `verified`),
- uložení výsledku auditu do modelu.

## 12. Praktická zkouška pro autora (po 14B)

1. Otevři *NDT – referenční díly → Kapsa* a dej **NDT → Předběžný NDT audit…**. Seznam ukáže
   tři studie: UT (neprovedeno – chybí plán dráhy), PT a MT s odhadem doby.
2. **Spustit audit.** Asi za 2 minuty se objeví přehled: PT ve čtyřech barvách, MT dno kapsy
   červeně.
3. Klikni na místo „dno kapsy“ – ve 3D se ukáže mapa MT a místo na ní.
4. **Exportovat zprávu…** a otevři `zprava.html` v prohlížeči: nahoře upozornění, přehled,
   místa, u každé studie její nastavení a obrázek.
5. Otevři `mista.csv` v Excelu – každé místo má důvod a studii.

## 13. K rozhodnutí

1. **Název a hranice:** „Předběžný NDT audit – zpráva o geometrickém posouzení“, ne „protokol
   o zkoušce“. Audit nevybírá metodu ani postup a nepíše „vyhovuje“. Zpráva nese obecné
   upozornění a upozornění všech zahrnutých metod doslova. *Doporučeno: ano.*
2. **Audit jen spouští stávající výpočty** u studií uživatele s jejich uloženým nastavením.
   Nic nového nepočítá a model nemění. *Doporučeno: ano.*
3. **UT:** uložený plán dráhy, jinak výsledek z tohoto sezení, jinak neprovedeno. Návrh poloh
   jen na zaškrtnutí s odhadem doby (na desce přes 22 min). *Doporučeno: ano.*
4. **Stavy auditu** spočítáno / neprovedeno / nedostupné s důvodem. „Nelze spolehlivě
   vyhodnotit“ = neznámé místo uvnitř výsledku, vždy zvlášť. Zastaralou studii audit sám
   nepotvrdí. *Doporučeno: ano.*
5. **Problémová místa** = spojené sousední body mapy se stejným stavem (do 1,6 × krok),
   s polohou, velikostí a všemi důvody s podílem. Pořadí červená → šedá → oranžová podle
   velikosti, bez nového skóre. *Doporučeno: ano.*
6. **Dohledatelnost:** celý záznam studie (JSON), nastavení, verze algoritmů, kroky, otisk
   dílu, čas a **sestavení aplikace** zapsané v GitHub Actions. *Doporučeno: ano.*
7. **Export do složky:** zpráva HTML, CSV míst a podrobná CSV studií. PDF z okna přes Qt
   (bez nové knihovny), obrázky map ve 3D jen z okna. *Doporučeno: ano.*
8. **Mapa tloušťky stěny** v auditu, jen když má model nastavenou mez. *Doporučeno: ano.*
9. **Výsledek auditu je pohled**, formát zůstává 21. Výpočet na pozadí, *Zastavit* nechá
   hotové studie. Mapy z auditu jsou pak k dispozici i v panelu NDT. *Doporučeno: ano.*
10. **Okno** (panel *Předběžný NDT audit*), **`skodacad audit`**, AI bez nového nástroje
    s novým pravidlem. *Doporučeno: ano.*

Schválením se **neschvaluje**:

- konstrukční návrhy a srovnání variant (etapa 15),
- automatický výběr metody nebo postupu,
- nová knihovna Pythonu,
- sloučení do `main`.

## 14. Provedení a upřesnění

- **14A.1 (hotovo):**
  - `ndt/audit.py`: každý výsledek metody (mapa pokrytí UT na plochách i v objemu, návrh poloh,
    plán dráhy, mapy PT, MT, RT, mapa tloušťky stěny) se převede na jednotná místa. Problémová
    místa se z nich spojí, zpráva se sepíše jako HTML, CSV míst a podrobná CSV studií
    (`AuditResult.write_folder`).
  - `buildinfo.py`: verze, sestavení a knihovny. Při vývoji se bere `git describe`; zápis
    commitu v GitHub Actions přijde v 14A.2.
  - Náhledy RT jsou ve zprávě i bez okna (`rt.png_bytes`).
  - **Ověřeno na referenčních dílech** (rychlé nastavení studií):
    - deska s otvorem RT: dva pruhy „mimo detektor“ u dlouhých okrajů (střed y = ±49 mm),
    - kapsa MT: jedno místo 1 200 mm² na dně kapsy, důvod „jho se nevejde v žádném směru“
      (100 %),
    - štěrbina PT: jedno místo 1 600 mm² přes obě stěny se všemi důvody,
    - mapa tloušťky s mezí 21 mm na 20mm desce: horní a spodní plocha jako dvě místa.
  - Ze záznamu studie ve zprávě se výpočet zopakuje se stejnými stavy (test).
- **14A.2 (hotovo):**
  - `ModelSession.ndt_audit_items`: u každé studie co se spočítá a jak dlouho, nebo proč ne
    (neprovedeno / nedostupné s českým důvodem). Neznámá studie a návrh poloh u jiné než UT
    studie jsou česká chyba.
  - `compute_ndt_audit` počítá studii po studii stávajícími výpočty metod; chyba jedné
    studie audit nezastaví (studie je „nedostupné – výpočet skončil chybou …“). Model se
    nemění, výsledek je pohled, platí pro výsledek přepočtu, záznam studií, materiál
    a nastavení mapy tloušťky.
  - `start_ndt_audit` v okně: studie, které se nepočítají (neprovedeno, nedostupné,
    výsledek UT z tohoto sezení, hotová mapa tloušťky), se zapíšou hned. Ostatní počítá
    pomocný proces a každou hotovou studii posílá zvlášť (`entry`). *Zastavit* hotové
    studie ponechá a zbylé zapíše jako „neprovedeno – audit byl zastaven …“; zpráva pak
    nese „Audit byl zastaven“.
  - `adopt_ndt_audit_map`: mapa studie z auditu se stane mapou v panelu NDT, aby se
    nemusela počítat znovu.
  - `skodacad audit MODEL [--studie …] [--navrh-poloh …] [--slozka …] [--zpracovatel …]`:
    seznam s odhadem, průběh, souhrn a složka se zprávou.
  - Sestavení: GitHub Actions před PyInstallerem zapíše commit a datum do
    `skodacad/_build.py` (v gitu ignorovaný). Údaj je ve zprávě, v self-testu, v logu
    a v okně *O aplikaci*.
  - AI má pravidlo: čísla auditu nevymýšlí, nevybírá metodu a netvrdí „vyhovuje“.
  - **Ověřeno:** deska s otvorem z příkazové řádky s výchozím nastavením za 7,5 s – dvě
    místa „Nepromítne se“ po 500,9 mm² u dlouhých okrajů (y = ±48,3 mm). V testech: UT mapa
    pokrytí z tohoto sezení se do auditu převezme, mapa tloušťky jen s mezí, zastaralá
    studie a RT bez projekce „nedostupné“, audit na pozadí i zastavení.
- **14B (hotovo):**
  - Panel *NDT audit* (`gui/audit_panel.py`, *NDT → Předběžný NDT audit…*): povinná upozornění
    (před auditem obecné, po něm všech metod ve zprávě), seznam studií se zaškrtávátky
    a odhadem, „i návrh poloh“ u UT bez plánu, *Zpracoval(a)*, *Spustit audit* / *Zastavit*,
    průběh „studie 2 z 3 – …, 312 z 1086“, přehled, tabulka míst.
  - Klik na místo vybere studii v panelu NDT, převezme její mapu a ukáže ji ve 3D s modrou
    kuličkou ve středu místa. Mapa místa má přednost před ostatními mapami a kresba projekce
    RT se přitom skryje.
  - *Exportovat zprávu…*: složka se `zprava.html`, `zprava.pdf` (Qt, A4, stránkuje se samo),
    `mista.csv`, CSV studií; obrázek mapy každé spočítané studie se pořídí z 3D okna.
  - Self-test aplikace spustí v okně audit desky s otvorem a uloží zprávu včetně PDF
    a obrázku mapy z 3D (ověří Qt PDF a kreslení v balíčku Windows i macOS).
  - **Ověřeno:** testy okna (seznam, spuštění, místa, klik, export HTML/PDF, zámek AI),
    snímky pod Xvfb – kapsa (UT neprovedeno, PT 2 místa, MT dno kapsy 1 200 mm²; s rychlým
    nastavením 31 s) a deska s otvorem (RT dva pruhy u okrajů, 3 s).
- **Upřesnění proti návrhu:**
  - **Podíl důvodů v místě** se počítá pro každý důvod zvlášť. Jedno místo může mít víc
    důvodů najednou (u štěrbiny „nástroj se nevejde“ i „úzká štěrbina“), součet proto může
    být přes 100 %.
  - **Upozornění metod** jsou ve zprávě v pevném pořadí UT, PT, MT, RT. Upozornění metody je
    ve zprávě i tehdy, když její studie zůstala neprovedená (studie ve zprávě je).

## Zdroje

- Zadání etapy: [03-implementacni-plan.md](03-implementacni-plan.md), etapa 14.
- Požadavky na obsah výstupu ze starších návrhů:
  - [02-navrh-v0.2.md](02-navrh-v0.2.md), oddíl 12: metoda, model a verze, oblast, materiál,
    parametry, krok, polohy zařízení, mapa, varování, čas a verze modulu,
  - tamtéž oddíl 16.2: audit = seznam podnětů, ne automatické rozhodnutí o proveditelnosti.
- Povinná upozornění: závazná vymezení [UT](04-zavazne-vymezeni-ut.md),
  [PT](20-vymezeni-pt.md), [MT](22-vymezeni-mt.md), [RT](24-vymezeni-rt.md) – všechna
  výslovně platí „v každém exportovaném protokolu“.
- Hledání obsahu zkušebního protokolu podle norem (ověřeno vyhledáváním 20. 10. 2026): plné
  texty jsou placené a veřejné ukázky požadovaný obsah nevypisují. Potvrzeno jen to, že
  [ISO 17640](https://webstore.ansi.org/preview-pages/ISO/preview_ISO+17640-2018.pdf) má
  oddíl o informacích před zkouškou a písemném postupu. Název zprávy proto vychází jen
  z opatrnosti, ne z článku normy.
- Doby výpočtů: změřeno 20. 10. 2026 v cloudu na ukázkách `examples/ndt/` s nastavením
  uloženým ve studiích. Doby návrhu poloh a plánu dráhy pocházejí z návrhů etap
  [09](17-navrh-etapa-09.md) a [10](18-navrh-etapa-10.md).

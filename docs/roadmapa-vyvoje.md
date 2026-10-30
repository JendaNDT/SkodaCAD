# Schválená roadmapa dalšího vývoje ŠkodaCADu

Datum zápisu: **20. 10. 2026**. Výchozí větev: `main`, commit
[`94c6e1d`](https://github.com/JendaNDT/SkodaCAD/commit/94c6e1d0f78f8944f81fd18db28a7ebbe2d18ec7)
(po sloučení [PR #29](https://github.com/JendaNDT/SkodaCAD/pull/29)).

## Mandát a původ

Autor schválil celkový plán v rozhovoru **Dokončení testů ŠkodaCAD**
(`6ad1cfbd-e12c-83eb-be6c-b2e07c95e08b`, odpověď „ok, schvaluji“).
V navazujícím zadání výslovně potvrdil pořadí **P0 stabilizace → P1 bezpečná geometrie
→ P2 přímé modelování → P3 STEP import → P4 výkresy → P5 sestavy → P6 pokročilé
modelování → P7 ergonomie → P8 výkon/stabilizace**, paralelně **NDT-17 validace**.
**NDT-16 je mimo schválený rozsah.**

Dostupný export staršího rozhovoru obsahuje místo těla odpovědí pouze odkazy
`chatgpt-content-reference`. Tento dokument proto není doslovným přepisem chybějícího
plánu: zachycuje výslovně potvrzený rámec a rozpracovává jej do ověřitelných kroků podle
aktuálního repozitáře. Konkrétní návrhy níže nejsou dokladem dalšího schválení rozhraní,
závislostí nebo datového formátu.

**Původní povolený rozsah byl P0 bez změny produkčního chování.** Pozdější konkrétní
schválení a dokončení P1.1/P1.2A/P1.2B jsou zaznamenaná v oddílu P1 níže.
Další implementaci P1 ani P2 nezahajovat bez dalšího schválení. P3–P8 zůstávají plán.
Nový formát modelu,
změnu architektury a nové závislosti nejprve předložit autorovi. Žádné sloučení do
`main` ani automatické slučování bez souhlasu autora.

## Stav k 30. 10. 2026

**Pokyn autora z 28. 10. 2026:** pokračovat v roadmapě samostatně; běžná rozhodnutí
a sloučení po úspěšných kontrolách (úplná sada testů, obě workflow včetně kontroly
staženého balíčku) nevyžadují další souhlas. Má přednost před staršími požadavky na
jednotlivá schválení v tomto dokumentu. Ruční přijetí etap a odborná validace NDT
zůstávají na autorovi.

| Etapa | Stav | Co zbývá |
|---|---|---|
| P0 | sloučeno (PR #30) | – |
| P1 | přijato autorem 25. 10. 2026 | R03, R04/P16, R12, historická identita |
| P2 | P2.1–P2.5 sloučeno (PR #42–45) | ruční zkouška a přijetí autorem |
| P3 | P3.1–P3.5 + jednotky metry sloučeno (PR #46–48), formát 24 | přijetí autorem, soubory z jiných CADů |
| P4 | P4.1–P4.4 pracovní výkres sloučen (PR #49–58), formáty 25–28 | P4.5 přejímka (tisk, DXF v jiném CADu, oba OS) |
| P5 | P5.1 schválen (S1–S12); [P5.2 polohy](p5-2-jadro-sestav.md) sloučeny (PR #63), autor: „Ok, funguje to“; [návrh P5.3](p5-3-navrh-vazeb.md) předán | schválení M1–M12, P5.3 vazby |
| P6–P8 | nezahájeno | – |
| NDT-17 | nezahájeno | – |

Formát modelu je verze **29** (načítá verze 1–29; 29 = soubor sestavy, díly zůstávají ve verzi 24–28). Výkon: průniky NDT bez zápisu do
vstupů a rychlejší ořez buněk objemu (PR #59, #60) – testy na Windows 26:55 → 14:53 min.
Podrobnosti a odkazy na evidence jsou v `CLAUDE.md`, oddíl *Plán*.

## Výchozí stav a pravidla předávání

- Python ≥ 3.11, build123d 0.13.0 / OCCT, slvs 3.2, PySide6 6.11.2.
- JSON model **verze 22**, načítání verzí 1–22; výsledky NDT a pohledy jsou dočasné.
- Parametrické díly, skicář, měření, export STEP/STL/3MF/GLB/SVG, řez DXF/SVG,
  NDT UT/PT/MT/RT, audit a konstrukční varianty již existují. Neimplementovat je znovu.
- Etapa NDT 15B je na `main` v PR #29. Sloučení není důkazem ručního ani odborného ověření.
- [Pravidla a známé pasti](../CLAUDE.md), [audit P0](p0-audit-a-overeni.md),
  [původní NDT plán](ndt/03-implementacni-plan.md), [NDT index](ndt/README.md).
  Historické „Fáze 0–4“ v CLAUDE nejsou nové etapy P0–P8.
- Každý implementační krok: omezený diff, geometrické/regresní ověření, Ruff a pytest,
  český popis změny a ruční scénář. GUI navíc skutečný prohlížeč a test balíčku.
- Každý větší milník: samostatné posouzení autora, zelené Windows i macOS Actions
  (sestavení **i kontrola staženého balíčku**). Otevřená rizika se předávají výslovně.
- Jednotky mm/°, výběr ploch významem, změny přes ModelSession a Zpět/Znovu.
  NDT závazná vymezení UT/PT/MT/RT mají přednost před staršími návrhy.

## Závislosti a pořadí

| Etapa | Vstupní závislost | Hlavní výstup / brána |
|---|---|---|
| P0 | aktuální main a existující testy | audit, evidence výchozího stavu, regrese, měřicí baseline, PR |
| P1 | P0 + nové schválení implementace | bezpečné geometrické operace a odmítnutí neplatného výsledku |
| P2 | P1 + nové schválení implementace | omezené přímé úpravy s historií a vratností |
| P3 | P1, P2 pro navazující úpravy | kontrolovaný STEP import s doloženými omezeními |
| P4 | P1; P3 pro výkresy importovaných dílů | asociativní základ technického výkresu |
| P5 | P1–P3, rozhodnutí o více dílech a ukládání | sestava s polohami a základními vazbami |
| P6 | stabilní P1–P5, schválený seznam operací | vybrané pokročilé operace s referenčními díly |
| P7 | stabilní pracovní postupy P2–P6 | sjednocené a ověřené ovládání |
| P8 | měření z P0 a výsledky P1–P7 | doložený výkon a stabilní balíčky |
| NDT-17 | existující NDT 00–15; průběžně změny P0–P8 | dohledatelné záznamy validace a meze použití |

P7/P8 dostávají nálezy průběžně, ale rozsáhlé přepracování UI a optimalizace počkají
na funkční milníky. NDT-17 **nezávisí na NDT-16**; tímto se pro schválený rozsah
zpřesňuje historická závislost „00–16“ v původním NDT plánu.

## P0 — stabilizace a prokazatelný výchozí stav

| Krok | Postup a závislost | Výstup a kritérium dokončení |
|---|---|---|
| P0.1 Inventura | Zafixovat SHA main, přečíst dokumentaci, zmapovat dokument → session → přepočet → worker → GUI/CLI/NDT. | Mapa skutečných modulů, rozhraní, současných formátů a existujícího pokrytí. |
| P0.2 Rizika | Po P0.1 projít selhání geometrie, odkazy na plochy, uložení, rušení, cache, balení a NDT omezení. | Každé riziko má důkaz v kódu, dopad, stávající ochranu a další krok; domněnka je označena. |
| P0.3 Výchozí verifikace | Na nezměněném main připravit izolované prostředí, Ruff, celý pytest včetně dostupného Qt, časy nejpomalejších testů. | Počty testů, chyby/přeskočení, verze a prostředí; selhání nezamlčet ani neodstranit test. |
| P0.4 Regrese | Doplnit chybějící ochrany skutečných uživatelských scénářů: ztráta dat při otevření/uložení, historie po chybě, přenos částečného výsledku, ukázky v podsložkách. | Testy kontrolují obsah, objem/rozměry a stav, ne jen „nespadlo“; žádná změna src. |
| P0.5 Baseline | Pevné ukázky, zahřátí + opakování přepočtu, přenosu a NDT paprsků; zaznamenat vstupy, prostředí, jednotlivé časy a souhrn. | Spustitelný samostatný měřič, čitelná metodika a uložený výsledek; žádný náhodný časový práh v pytest. |
| P0.6 Předání | Ruff/pytest po změně, oba workflow Windows/macOS, kontrola rozsahu diffu; český návod ruční zkoušky a PR do main. | PR obsahuje důkazy a otevřené položky. Ruční zkoušku potvrzuje autor; P0 PR sám neopravňuje spustit P1. |

**V tomto kroku se neopravují produkční nálezy.** Změna algoritmu, fallbacku, persistence,
GUI či významu výsledků patří do zvlášť schváleného kroku. P0 je dokončené jako
technické předání po ověření PR; ruční přijetí a schválení další etapy zůstávají samostatné.

## P1 — bezpečná geometrie

**P1.1 dokončeno — schváleno autorem 20. 10. 2026:**
[smlouva geometrických operací](p1-1-navrh-smlouvy-geometrickych-operaci.md), rozhodnutí D1–D7 a matice budoucích testů.
Zachovává existující podporu více solidů. Sloučené dokumentační PR #31 zaznamenává schválení;
implementace P1.2–P1.5 ani nový formát tím nejsou schválené.

**P1.2A schváleno autorem 20. 10. 2026:** [konkrétní rozsah společné kontroly geometrie](p1-2a-navrh-spolecne-kontroly-geometrie.md).
Body A1–A7 a kroky A.1–A.3 jsou autorizované; plán je sloučený v PR #32 (`15b8bf4`).
Implementace A.1–A.3 je sloučená v [PR #33](https://github.com/JendaNDT/SkodaCAD/pull/33)
(`edf9b8e`); [protokol z 21. 10. 2026](p1-2a-rucni-overeni-macos-2026-10-21.md)
dokládá sedm vedených zkoušek autora na Macu i samostatný souhlas se sloučením.
[Evidence P1.2A](p1-2a-overeni.md) rozlišuje automatické a ruční výsledky.

**P1.2B — schváleno autorem 21. 10. 2026:**
[transakce celého kontextu prvku](p1-2b-navrh-transakce-kontextu.md), rozhodnutí B1–B7,
kroky B.1–B.3, matice T01–T14. Autor odpověděl „ok, schvaluji“ a návrhové PR #34
je sloučené (`cbf19b1`). Implementace je dokončená a sloučená v
[PR #35](https://github.com/JendaNDT/SkodaCAD/pull/35) jako `3a8deff`.
[Evidence](p1-2b-overeni.md) a [protokol z 22. 10. 2026](p1-2b-rucni-overeni-macos-2026-10-22.md)
dokládají oba celé cílové workflow, 17 vedených kontrol autora na Macu a samostatný
pokyn ke sloučení. R05 je vyřešené pro schválená pole, vlastnictví a podporované cesty B1–B7.

**P1.3 — schváleno autorem 22. 10. 2026:**
[bezpečné vyhodnocování geometrických odkazů](p1-3-navrh-bezpecnych-referenci.md),
C1–C8, kroky C.1–C.3 a S01–S20. Rozlišuje skupinu od jednoho odkazu, odmítá
rovnocenné kandidáty a oslabování filtrů. Zachovává formát 22 a přiznává zbytkové
riziko historické identity. Autor odpověděl „ok, schvaluji vše“ na C1–C8, C.1–C.3,
S01–S20 a sloučení návrhového PR #36 (`c46d0e2`). Implementace je sloučená v
[PR #37](https://github.com/JendaNDT/SkodaCAD/pull/37) jako `f5fbe2c` na samostatný
pokyn autora. [Evidence sloučení a vydání](p1-3-overeni.md#sloučení-a-vydání-z-main)
dokládá 1 451 testů, oba celé cílové workflow i self-test stažených balíčků;
meze ručního přijetí a historické identity zůstávají výslovně uvedené.

**P1.4 — E1–E9 schválené autorem 24. 10. 2026, implementace sloučená:**
[export a NDT při chybě modelu](p1-4-navrh-exportu-a-ndt-pri-chybe.md), rozhodnutí
E1–E9, kroky E.1–E.4 a matice E01–E22. Ponechat poslední geometrii k opravě,
exporty a NDT vyžadují celý aktuální úspěšný model. Návrh rozlišuje vadnou studii,
zastavený audit a chybu samotného modelu. Autor odpověděl „ok, schvaluji“ na
návrh a zahájení implementace. [Evidence P1.4](p1-4-overeni.md) rozlišuje postup
od skutečného ověření; implementace je v [PR #39](https://github.com/JendaNDT/SkodaCAD/pull/39).
Autor po předání schválil sloučení; main obsahuje `e7f9ac6`.
[Obě vydání z main](p1-4-overeni.md#sloučení-a-vydání-z-main) prošla
1 549 testy na každém systému, self-testy stažených balíčků a dalšími kontrolami.
P1.5 tím schválené není.

**P1.5 — dokončeno a sloučeno:** [přijetí bezpečné geometrie](p1-5-navrh-prijeti-bezpecne-geometrie.md),
F1–F9, F.1–F.4 a P01–P24. Autor 24. 10. 2026 po návrhu v PR #40 odpověděl „schvaluji“.
[Evidence P1.5](p1-5-overeni.md) rozlišuje inventuru, doplnění a skutečné výsledky;
sedm nových případů, 1 556 úspěšných místních testů a
[nativní protokol](p1-5-agent-overeni-macos-2026-10-24.md) s 15 kroky.
Autor sloučil [PR #41](https://github.com/JendaNDT/SkodaCAD/pull/41) jako `fe2a087`;
obě workflow z main včetně kontroly stažení prošla.

**P1 přijato autorem 25. 10. 2026** slovy „Přijímám P1“
([zápis](p1-5-overeni.md#sloučení-a-přijetí-p1-autorem)). R03, R04/P16, R12, širší
ruční matice Windows/macOS a NDT-17 zůstávají otevřené; nové produkční opravy dál
vyžadují samostatný návrh.

1. **P1.1 Smlouva operace** (po P0): navrhnout vstupy, očekávaný počet těles, jednotky,
   toleranci a postpodmínky pro přidání/odebrání/průnik, zaoblení, skořepinu a loft.
   Výstup: matice operace × platný/neplatný/hraniční vstup, schválená autorem.
2. **P1.2 Transakce** (po P1.1): připravit kandidátní geometrii, validovat a až pak
   přijmout; při chybě zachovat konzistentní předchozí díl, skici a návaznosti.
   Výstup: česká chyba + regrese obnovy, bez tiché ztráty materiálu.
3. **P1.3 Reference** (po P1.1): jednoznačné sémantické odkazy, detekce chybějící či
   nejednoznačné plochy; nesprávnou vazbu nehádat. Výstup: sada změn parametrů, které
   udrží správnou vazbu nebo ji výslovně odmítnou.
4. **P1.4 Export a NDT při chybě** (po P1.2–3): rozhodnout, jak nakládat s částečným
   dílem, neplatnou historií a zastaralou studií; případnou změnu chování schválit.
   Výstup: jednotné pravidlo pro GUI/CLI/AI, příslušné regrese a návod obnovy.
5. **P1.5 Přijetí**: analytické objemy, degenerované vstupy, geometrické hraniční případy,
   Zpět/Znovu, pracovní proces, Windows/macOS. Hotovo až při absenci tichého přijetí
   chybné geometrie v dohodnuté sadě; zachování starých modelů doložené testy.

## P2 — přímé modelování (sloučeno, čeká na přijetí autorem)

**P2.1 — schváleno autorem 25. 10. 2026** slovy „schvaluji G1–G8“:
[rozsah přímého modelování](p2-1-navrh-rozsahu-primeho-modelovani.md), rozhodnutí
G1–G8 a matice Q01–Q24, s [průzkumem jádra](p2-1-pruzkum-jadra.py). Návrh je v PR #42.
Schválení P2.1 nespouští P2.2–P2.5 ani formát 23; každý krok má vlastní schválení.

**P2.2 — schváleno autorem 25. 10. 2026** slovy „schvaluji H1–H8“:
[zápis přímé úpravy](p2-2-navrh-zapisu-prime-upravy.md), rozhodnutí H1–H8 (typy
`move_face` a `face_diameter`, pojistka původu plochy, formát 23, oprava R12) a matice
W01–W16, s [průzkumem pojistky](p2-2-pruzkum-puvodu.py). Návrh je v PR #43;
schválení opravňuje implementaci P2.3 podle tohoto zápisu (bez sloučení do main).

**P2.3 — sloučeno v PR #44 (`e1cb3bc`):** `direct_edit.py`, prvky `move_face`
a `face_diameter`, formát 23, README pro AI (R12), testy Q01–Q23 a W01–W16;
[evidence](p2-3-overeni.md).

**P2.4–P2.5 — sloučeno v PR #45 (`5cbab6f`):** výběr plochy ve 3D, náhled na kopii,
potvrzení, nástroj AI jen s dialogem; [evidence P2.4](p2-4-overeni.md),
[přejímka P2.5](p2-5-overeni.md). Ruční zkouška a výslovné přijetí P2 autorem čekají.

1. **P2.1 Omezený rozsah** (P1): vybrat první podporované typy ploch a úprav; navržený
   začátek je posun rovinné plochy a změna válcového otvoru. Sepsat nepodporované případy.
2. **P2.2 Historie** (P2.1): navrhnout reprezentaci operace a sémantické reference.
   Před zápisem nových polí/prvků samostatně schválit formát a kompatibilitu.
3. **P2.3 Výpočet** (P2.2): náhled na kopii, ověření P1, potvrzení a jeden krok Zpět;
   zánik návazné plochy musí být vysvětlen, NDT výsledky se zneplatní.
4. **P2.4 Ovládání** (P2.3): výběr plochy → zadání hodnoty → náhled → použít/zrušit;
   stejné pravidlo platí pro případný nástroj AI.
5. **P2.5 Přijetí**: referenční kvádr a díra mají analyticky správný objem/rozměry;
   nepodporovaná plocha a kolize se odmítnou beze změny; uložit/otevřít/Zpět/Znovu
   reprodukuje výsledek. Výstup: omezené, popsané přímé modelování.

## P3 — STEP import

**Stav:** P3.1–P3.5 sloučeno v PR #46 a #47 (`59cfb8c`), jednotky metry v PR #48
(`731d0c2`), formát 24; [evidence](p3-3-5-overeni.md), [metry](p3-step-metry.md).
Přijetí autorem a zkouška se soubory z jiných CADů čekají.

1. **P3.1 Sada vstupů** (P1): jeden solid, několik solidů, sestava, jiné jednotky,
   otevřený povrch a poškozený soubor; u každého původ a očekávané rozměry.
   [Připravená sada a její omezení](p3-1-step-vstupy.md).
2. **P3.2 Uložení importu**: rozhodnout přenositelné uložení zdroje, identitu, odkazy,
   velikost a obnovu chybějícího souboru. Schválit formát před implementací.
3. **P3.3 Importní služba** (P3.1–2): mimo Qt, diagnostika jednotek/těles/platnosti,
   omezené prostředky a zrušení; žádné tiché opravy bez zprávy.
4. **P3.4 Session a GUI**: náhled, potvrzení, měření, export, omezené P2 úpravy;
   jasné vysvětlení, že původní parametrická historie ve STEP není k dispozici.
5. **P3.5 Přijetí**: objem, rozměry, jednotky a počet těles po importu/exportu v určené
   toleranci; opětovné otevření na druhém OS bez závislosti na absolutní cestě autora.
   Výstup: ověřená podmnožina STEP, seznam omezení a ukázky.

## P4 — technické výkresy

**Stav:** P4.1 schváleno (V1–V9); pracovní výkres sloučen v PR #49–58 – pohledy a řez
([P4.2](p4-2-geometrie-pohledu.md)), kóty s vazbami a odchylkami, popisové pole, list
a měřítko, skryté pohledy ([P4.3](p4-3-vazby-kot.md), [P4.4](p4-4-koty-na-listu.md)),
export PDF/DXF ([P4.5 řez a export](p4-5-rez-export.md)), upozornění na překrytí
([P4.6](p4-6-kontrola-prekryti.md)); formáty 25–28. Zbývá přejímka (bod 5 níže): fyzický
tisk, DXF v jiném CADu a ruční průchod na obou OS.

1. **P4.1 Rozsah výkresu** (P1, případně P3): dohodnout list, měřítko, jednotky,
   základní pohledy a řez; odlišit již existující export obrysu řezu.
2. **P4.2 Geometrie pohledů**: přesná projekce viditelných/skrytých hran a řezu,
   testy jednoduchých těles, orientace a měřítka.
3. **P4.3 Kóty a vazby**: rozměry/vzdálenosti/průměry, odkazy na model a označení
   zastaralé či zaniklé kóty; navrhnout a schválit ukládání výkresu.
4. **P4.4 List a export**: umístění pohledů, popisky, PDF a dohodnutý výměnný export,
   čitelnost češtiny a skutečné měřítko při tisku.
5. **P4.5 Přijetí**: změna modelu aktualizuje pohledy a platné kóty, rozbité vazby
   jsou viditelné; ručně změřený export odpovídá listu a jednotkám na obou OS.
   Výstup: použitelný základ výkresu s uvedenými nepodporovanými značkami/normami.

## P5 — sestavy

1. **P5.1 Datový návrh** (P1–P3): oddělit díl, instanci a sestavu; identity, relativní
   cesty, cyklické odkazy, chybějící komponenty a verze. Formát nejprve schválit.
   Návrh S1–S12 s průzkumem a maticí A01–A22: [p5-1-navrh-formatu-sestav.md](p5-1-navrh-formatu-sestav.md).
2. **P5.2 Polohy**: vkládání, opakované instance, posun/rotace a pevná komponenta;
   změna instance nesmí měnit zdrojový díl ani jinou instanci.
3. **P5.3 Základní vazby**: po odsouhlasení řešiče souosost, dotyk a vzdálenost,
   stavy nedourčeno/přeurčeno, spolehlivé odmítnutí konfliktu.
   Návrh M1–M12 s průzkumem a maticí B01–B20: [p5-3-navrh-vazeb.md](p5-3-navrh-vazeb.md).
4. **P5.4 Kontroly**: kolize a vůle, kusovníkový základ a export; vymezit působení
   NDT mezi komponentami, nepřenášet automaticky závěry z jednoho dílu na sestavu.
5. **P5.5 Přijetí**: analytické polohy dvou a více dílů, opakované instance, Zpět/Znovu,
   uložení/otevření a export na druhém OS. Výstup: sestava v dohodnutém rozsahu vazeb.

## P6 — pokročilé modelování

1. **P6.1 Výběr operací** (P1–P5): sestavit priority podle skutečných dílů autora,
   např. proměnné zaoblení, robustnější skořepina, vodicí křivky loftu, další křivky/plochy.
   Jde o kandidáty k výběru, ne automatické schválení všech.
2. **P6.2 Proveditelnost**: samostatné malé pokusy s aktuálním jádrem; objem, tloušťka,
   validita a známé selhání. Nenahradit neproveditelnou operaci tichou aproximací.
3. **P6.3 Jeden prvek po druhém**: služba → session/schema → regresní test → GUI;
   u každého zvlášť posoudit formát, odkazy a Zpět/Znovu.
4. **P6.4 Přijetí**: referenční díl autora a hraniční případy pro každou schválenou
   operaci; omezení a případné aproximace viditelné ve výsledku. Výstup: otestovaná
   sada vybraných operací, bez slibu podpory libovolné geometrie.

## P7 — ergonomie

1. **P7.1 Pozorování** (stabilní P2–P6): autor provede vytvoření dílu, úpravu, import,
   výkres, sestavu a NDT audit; zapsat záměny, počet kroků a zablokování.
2. **P7.2 Konzistence**: sjednotit výběr, předvýběr, klávesy, potvrzení/zrušení,
   chyby a průběh; odlišit skrytí pohledu od změny modelu.
3. **P7.3 Úpravy po jednom toku**: čitelné panely, skicář, navigace a obnova rozložení,
   přístupné ovládání, Retina/trackpad i myš na Windows.
4. **P7.4 Přijetí**: opakovat stejné scénáře s autorem; bez ztráty dat a nechtěné
   změny, zdokumentované zkratky a snímky skutečného GUI. Výstup: ověřené pracovní toky.

## P8 — výkon a závěrečná stabilizace

1. **P8.1 Rozšíření baseline** (P0, P1–P7): velké historie, importy, sestavy a více NDT
   studií; startup, přepočet, přenos, paměť, odezva a ukončení dlouhé úlohy.
2. **P8.2 Profilování**: identifikovat skutečnou dominující část, až pak navrhnout cache,
   částečný přepočet či omezení kopírování. Nové mechanismy vyžadují návrh invalidace.
3. **P8.3 Optimalizace odděleně**: jeden zásah, před/po na stejných vstupech a prostředí;
   numerický výsledek a stav studií musí zůstat shodné v dohodnuté toleranci.
4. **P8.4 Dlouhý provoz**: opakované otevření/editace/rušení/export, havárie workeru,
   omezené zdroje a velké soubory; zjistit úniky a schopnost obnovy.
5. **P8.5 Přijetí**: dohodnuté rozpočty paměti a času jsou splněné na zařízení autora,
   CI a stažené balíčky pro oba OS ověřené; známá omezení a postup obnovy zveřejněné.
   Výstup: stabilizovaná verze s doloženým měřením, ne pouze vyšším počtem testů.

## Paralelní NDT-17 — validace a meze použití

1. **N17.1 Inventura důkazů**: pro každou metodu oddělit analytické regrese, referenční
   geometrii, ruční zkoušku programu a odbornou/fyzickou validaci. Existující
   [referenční díly](ndt/05-referencni-dily.md) nejsou potvrzením reálné detekce vad.
2. **N17.2 Protokol případu**: identifikace dílu a zařízení, původ hodnot, jednotky,
   nastavení/krok/tolerance, verze algoritmu a aplikace, očekávání, výsledek, odchylka,
   nejistota, podmínky a osoba, která případ ověřila. Nevyplněné položky zůstanou čekající.
3. **N17.3 Analytické a hraniční zkoušky**: deska, otvor, trubka, žebro, kapsa, svary;
   dotyk/tečnost/hrana, kolize, nedostupná oblast, citlivost kroku a objemové váhy.
   Navazovat na existující testy, sporný výsledek neoznačit zeleně.
4. **N17.4 Fyzické a odborné porovnání**: autor a kvalifikovaný NDT pracovník dodají
   vzorky, měření a postup; zaznamenat shodu/neshodu pouze v rámci geometrického posouzení.
5. **N17.5 Průběžná regrese**: po změně geometrie, importu či sestav znovu ověřit
   dotčené případy, invalidaci studií a úplnost zpráv. Ověření neplatí pro jiný model.
6. **Brána dokončení**: každá deklarovaná oblast použitelnosti má dohledatelný protokol
   a schválené meze; bez nich zůstává výsledek předběžný/orientační. Žádná automatická
   certifikace, volba kvalifikovaného postupu nebo tvrzení o detekovatelnosti vad.

**NDT-16 se neprovádí** a není podmínkou NDT-17. V P0 vzniká pouze technická evidence;
nezapisovat jméno ověřovatele ani výsledek fyzické validace bez skutečného ověření.

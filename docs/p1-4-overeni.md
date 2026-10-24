# P1.4 — implementace a ověření

Autor 24. 10. 2026 schválil [E1–E9, E.1–E.4 a E01–E22](p1-4-navrh-exportu-a-ndt-pri-chybe.md)
slovy „ok, schvaluji“. Implementace proběhla ve větvi `codex/p1-4-safe-outputs`
nad schváleným návrhem z PR #38 (`c2d0e97`); produkční základ je `main / f5fbe2c`.
Po předání autor výslovně schválil sloučení. PR #39 je na main jako `e7f9ac6`;
[závěrečné ověření vydání](#sloučení-a-vydání-z-main) je níže.

## Postup

| Krok | Stav |
|---|---|
| E.1 | Společná kontrola historie/tělesa, aktuálnosti session, exportu dílu a řezu. CLI zachovává označenou diagnostiku mezistavu, ale neexportuje a vrací 1. Nových 20 regresí; cílená sada 102 prošla / 12,03 s, Ruff OK. Celá místní sada **1 471 prošlo / 427,75 s**, 0 chyb, selhání a přeskočení. |
| E.2 | Kontrola úplného modelu před NDT potvrzením/ověřením, odhady a výpočty UT/PT/MT/RT/auditu/variant; nedostupné stavy studií při chybě historie bez výpočtu cílů a mapy tloušťky. Staré mapy, náhledy a zprávy blokované také po pádu workeru. CLI paprsek/sonda/pokrytí vyžadují úspěšný model; otisk odpovídá `--set`, jednorázový cíl se neoznačuje jako platná uložená studie. 60 nových případů včetně skutečných výsledků všech metod, řízené pozdní odpovědi a skutečného spawn. Celá místní sada **1 531 prošlo / 440,61 s**, Ruff OK, 0 chyb, selhání a přeskočení. Přerušený předchozí běh se nezapočítává. |
| E.3 | Trvalá příčina a diagnostické vlastnosti; nedostupné výstupy a NDT při chybě/starém modelu, zachované ukládání a úpravy. Pracovní náhled UT/MT/RT označený; offline AI označuje obrázek i čísla. 18 nových regresí včetně obnovy, skutečného workeru, starého PDF a zastavení auditu po jednom výsledku. Cílených 47 zkoušek prošlo / 39,81 s a dodatečná zkouška částečného auditu / 0,48 s. Konečná celá sada **1 549 prošlo / 448,00 s**, Ruff OK; 0 chyb, selhání a přeskočení. |
| E.4 | Načítání nových testů okna zachovává volitelnost GUI: při řízeně nedostupném PySide6 se přeskočí jen modul GUI, 80 nových zkoušek jádra se dál načte; instalované knihovny se nemění. Po této úpravě znovu celý pytest: **1 549 prošlo / 448,38 s**, Ruff OK, bez chyb/selhání/přeskočení. Nativní zkoušky zdrojového okna hotové podle [protokolu](p1-4-agent-overeni-macos-2026-10-24.md); matice níže. Místní měřicí evidence a obě celé CI včetně baseline a self-testů stažených balíčků se vážou ke konkrétní hlavě; konečné odkazy a výsledky uvádí PR #39 při předání. |

Výchozí baseline P0 vznikla před změnou zdrojů, zahřátí + 3 opakování;
vstupy a fyzické podpisy zůstávají pro závěrečné srovnání. Formát je 22,
závislosti ani worker protokol se nemění. Odborná NDT-17 se neprohlašuje za hotovou.

## Regresní matice E01–E22

Nové zkoušky jsou v `tests/test_output_guard.py` (E.1),
`tests/test_output_ndt.py` (E.2) a `tests/test_output_gui.py` (E.3).
Všech **77 původních testovacích souborů** je zachovaných byte shodně s výchozím
`main`; nejsou vypnuté testy ani změněné geometrické tolerance.

| ID | Doložení |
|---|---|
| E01 | Nativní průchod: kvádr, všech pět formátů přes obsluhu okna, STEP znovu načten s 24 000 mm³ / 20×30×40 / 1 tělesem; oba exporty řezu s plochou 600 mm². Dosavadní `test_examples_and_cli.py` a `test_section.py` zachované. |
| E02 | E.1 `test_valid_two_body_export_preserves_both_solids`: 24 250 mm³, dvě tělesa a rozměry po znovunačtení STEP. |
| E03 | E.1 pomocný scénář `fail_history`: R50 `error`, následný prvek `skipped`, zachovaný platný mezistav 24 000 mm³; blokace dílu i řezu. |
| E04 | E.1 parametrizované nové/existující cíle všech formátů a CLI bez vytvoření složky; E.3 přímé GUI obsluhy odmítnou před dialogem. Existující bytes a session beze změny. |
| E05 | E.1 prázdný recept, samotná skica, prázdný Part a `skipped` bez první chyby; E.3 vadné uložené měření neblokuje platný STEP. Dosavadní chyby přepočtu zachované. |
| E06 | E.1 export za běhu; E.3 skutečný worker a nedostupné akce do dokončení; E.2 NDT kontroluje celý současný model. |
| E07 | E.1 pád workeru se starým `ok` výsledkem a opakování; E.2 všechny skutečné výsledky metod; E.3 trvalé varování i při starém úspěšném `result`. |
| E08 | E.3 parametrizované `test_timeout_and_stop_restore_the_actual_last_recipe`: nulová mez čekání, Zastavit na úspěšném/chybném předchozím receptu, odpovídající export, Znovu vrací zrušenou změnu. Skutečný spawn/Zastavit také v původních `test_background.py`. |
| E09 | E.2 28 veřejných vstupů nad chybným modelem; potvrzení/ověření bez změny dokumentu či historie. Odhady i synchronní/pozadí cesty. |
| E10 | E.2 plochový i objemový cíl, UT/MT/RT, sonda/jho/projekce, plán/polohy a všechny výstupy včetně PNG. |
| E11 | E.2 `compute_map` nahrazen zákazem spuštění na vadném receptu, přenos `map_error`; skutečná stará mapa znepřístupněná po neúspěchu. |
| E12 | E.2 skutečný spawn → oprava → zastaralá studie → výslovné potvrzení → nový výpočet bez odborného ověření; E.3 označené pracovní náhledy. |
| E13 | Původní `test_reference_consumers.py`, `test_ndt_study.py`, `test_ndt_volume_session.py` a P1.3; E.2 neúplné potvrzení odmítnuté, vadná/zastaralá studie neblokuje platný export geometrie. |
| E14 | E.2 skutečné mapy UT/PT/MT/RT, audit, návrh poloh, plán, varianty a tloušťka → změna → chyba transportu; getter, náhled i export nedostupné. |
| E15 | E.2 řízená odpověď staré úlohy 41 po spuštění 42, skutečný spawn/obnova; původní zkoušky nové změny a otevření v `test_background.py`. |
| E16 | E.2 audit platného modelu s nedostupnou studií bez procent; E.3 `test_stopped_audit_preserves_one_real_result_and_marks_the_remaining_study`: skutečná první PT mapa, řízené doručení a Zastavit, druhá studie `neprovedeno`, HTML/CSV bez její mapy. Původní skutečný proces a průběh auditu zachované. |
| E17 | E.2 všechny vstupy/výstupy auditu a variant na vadném/starém modelu; E.3 přímé GUI obsluhy se skutečnou starou zprávou neotevřou dialog ani PDF zapisovač. |
| E18 | Původní `test_ndt_design.py::test_variant_that_cannot_be_evaluated`, `test_ndt_design_session.py::test_session_settings_undo_and_separate_variant`: chyba varianty bez cílového výsledku, odmítnuté použití, nový soubor jen pro přijatou variantu, originál zachovaný. Zpřísnění základního modelu v E.2 tyto zkoušky nemění. |
| E19 | E.3 parametr, varování, přímo volaný export/řez, obnova a skutečný worker; [nativní protokol](p1-4-agent-overeni-macos-2026-10-24.md) a kontrolované snímky. |
| E20 | E.3 offline `ModelTools`: diagnostický obrázek i report, aktuální stavy studií během přepočtu, oprava seskupená pro Zpět/Znovu; žádná síť ani nový AI nástroj. |
| E21 | E.1 JSON formát 22, kopie, oprava a historie; E.3 skutečné akce Uložit jako/otevřít/parametr/Zpět/Znovu; nativně původní soubor byte shodný. |
| E22 | E.2 CLI paprsek/sonda/pokrytí nad chybou před algoritmem a zápisem; oba jednorázové cíle s `--set h=50`, analytický průchod 50 mm a otisk aplikovaného receptu, oddělený původ sondy a cíle. Uložené studie nadále podléhají kontrole celé oblasti. |

Řízené zkoušky transportu se nevydávají za pád skutečného OCCT procesu. Skutečný
spawn je ověřen odděleně. Zkoušky `offscreen` používají náhradní prohlížeč;
nativní protokol ověřuje skutečné kreslení, ale netvrdí fyzické klikání.

## Předání a obnova

Implementace je v [PR #39](https://github.com/JendaNDT/SkodaCAD/pull/39); zahrnuje
také schválený návrh z PR #38. Konečné běhy obou workflow, konkrétní sestavení,
stažené zprávy a balíčky uvádí popis PR při předání. Zelený starší commit není
důkazem konečné hlavy PR. Kontroly před sloučením vydání nespouštěly;
vydání ze skutečného main po schváleném sloučení dokládá následující oddíl.

Při chybě nejprve ulož pracovní JSON kopii, přečti prvek a příčinu pod stromem,
oprav parametr/výběr nebo použij Zpět a počkej na úspěšný přepočet. Export se
obnoví sám. Po změně dílu zvlášť zkontroluj oblast NDT, případně ji znovu vyber,
technicky potvrď pro aktuální díl a teprve potom spočítej novou mapu.
Odborné ověření starého dílu se tím neobnovuje. Přepočet lze opakovat;
Zastavit se vrací do posledního skutečně spočítaného receptu.

Rozsah nezahrnuje nový formát, nové geometrické operace ani změnu algoritmů NDT.
R03, R04, R12 a NDT-17 zůstávají otevřené. Sloučení do main autor schválil až po předání.

## Sloučení a vydání z main

Po předání implementace a doporučení sloučit PR #39 autor odpověděl
**„ok, schvaluji“**. PR bylo sloučené 24. 10. 2026 v 18:26 SELČ jako
[`e7f9ac6111fa789a7bbaa80aba6e8cfda9c45271`](https://github.com/JendaNDT/SkodaCAD/commit/e7f9ac6111fa789a7bbaa80aba6e8cfda9c45271).
Hlava implementace byla `3fe590d56ca2c9b5835a3fe5b174992d2f52a6c5`, testovací merge
PR `214eb733c8a4873dc7b97e9cb2ac9e32002afc3f`. Jejich strom souborů i skutečný
merge mají shodné SHA `772ba4b4e7d4e295e6d0dd1b10fdb283bb430164`.

| Ověření 24. 10. 2026 | macOS | Windows |
|---|---|---|
| Celý běh ze skutečného main | [#158 / 40111552514](https://github.com/JendaNDT/SkodaCAD/actions/runs/40111552514), úspěch | [#199 / 40111552478](https://github.com/JendaNDT/SkodaCAD/actions/runs/40111552478), úspěch |
| JUnit | 1 549 testů / 1 047,900 s, bez chyb a přeskočení | 1 549 testů / 1 520,503 s, bez chyb a přeskočení |
| Ruff, baseline P0, sestavení | Úspěch, arm64 a hluboký podpis | Úspěch včetně kontroly DLL |
| Druhá úloha — skutečně stažený balíček | Self-test `VÝSLEDEK: OK` | Self-test `VÝSLEDEK: OK` |
| Zveřejnění po self-testu | [nejnovejsi-mac](https://github.com/JendaNDT/SkodaCAD/releases/tag/nejnovejsi-mac), správný commit | [nejnovejsi](https://github.com/JendaNDT/SkodaCAD/releases/tag/nejnovejsi), správný commit |

Stažené zprávy i balíčky prošly SHA-256 podle metadat GitHubu a kontrolou CRC.
Baseline nese skutečný commit main, čisté sledované zdroje, shodné otisky zdrojů
(při rozlišení LF/CRLF), vstupů a měřiče. Všech šest fyzických podpisů odpovídá
místní referenci, včetně každého z 1 000 paprsků s 20 mm materiálu. Časy mezi
různými zařízeními/OS se nevydávají za srovnání rychlosti.

Mac ZIP z Releases je bajtově totožný s vnitřním ZIPem otestovaného artefaktu
`12567546537`; SHA-256 vydání je
`215ec69c50793bd55ad4ac210b430deeaa87c8a20979a5018a41b03b8d079da3`.
Windows ZIP z Releases má SHA-256
`c9993ab003a82ffa840fd9b7e82828846add4cf6c085d41fc099751c0e2a6f0f`;
všech **6 892 souborů** má stejnou cestu, velikost a SHA-256 jako v otestovaném
artefaktu `12567602777`, včetně spustitelného souboru a potřebných DLL.
Rozdíl komprese obou Windows ZIPů není rozdílem jejich souborů.
Obě značky vydání ukazovaly při závěrečné kontrole na `e7f9ac6`;
`releases/latest` zůstalo správně na Windows.

Stažená vydaná aplikace pro Mac prošla na místním **Macu M4** hlubokým ověřením
podpisu, architekturou arm64 a celým self-testem `VÝSLEDEK: OK` s odděleným
testovacím profilem. Zpráva uvádí sestavení **e7f9ac6111fa (2026-10-24)**,
skutečné OpenGL `Apple / Apple M4 / 2.1 Metal`, 3D kreslení, řez, výběr a přepočet
v pomocném procesu. Windows se spouštěl v CI. Toto není nové fyzické ovládání všech
dialogů ani odborné přijetí NDT-17. CI artefakty s balíčky mají retenci 7 dní, zprávy 14 dní;
stažená surová evidence byla uchována v pracovním předání mimo repozitář.

Tento záznam dokládá dokončení dodání P1.4. Neopravňuje zahájit P1.5 nebo P2
a nemění zbytkové meze uvedené výše.

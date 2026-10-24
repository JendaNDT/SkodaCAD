# P1.4 — implementace a ověření

Autor 24. 10. 2026 schválil [E1–E9, E.1–E.4 a E01–E22](p1-4-navrh-exportu-a-ndt-pri-chybe.md)
slovy „ok, schvaluji“. Implementace běží ve větvi `codex/p1-4-safe-outputs`
nad schváleným návrhem z PR #38 (`c2d0e97`); produkční základ je `main / f5fbe2c`.
Do main se bez dalšího pokynu autora neslučuje.

## Postup

| Krok | Stav |
|---|---|
| E.1 | Společná kontrola historie/tělesa, aktuálnosti session, exportu dílu a řezu. CLI zachovává označenou diagnostiku mezistavu, ale neexportuje a vrací 1. Nových 20 regresí; cílená sada 102 prošla / 12,03 s, Ruff OK. Celá místní sada **1 471 prošlo / 427,75 s**, 0 chyb, selhání a přeskočení. |
| E.2 | Kontrola úplného modelu před NDT potvrzením/ověřením, odhady a výpočty UT/PT/MT/RT/auditu/variant; nedostupné stavy studií při chybě historie bez výpočtu cílů a mapy tloušťky. Staré mapy, náhledy a zprávy blokované také po pádu workeru. CLI paprsek/sonda/pokrytí vyžadují úspěšný model; otisk odpovídá `--set`, jednorázový cíl se neoznačuje jako platná uložená studie. 60 nových případů včetně skutečných výsledků všech metod, řízené pozdní odpovědi a skutečného spawn. Celá místní sada **1 531 prošlo / 440,61 s**, Ruff OK, 0 chyb, selhání a přeskočení. Přerušený předchozí běh se nezapočítává. |
| E.3 | Trvalá příčina a diagnostické vlastnosti; nedostupné výstupy a NDT při chybě/starém modelu, zachované ukládání a úpravy. Pracovní náhled UT/MT/RT označený; offline AI označuje obrázek i čísla. 18 nových regresí včetně obnovy, skutečného workeru, starého PDF a zastavení auditu po jednom výsledku. Cílených 47 zkoušek prošlo / 39,81 s a dodatečná zkouška částečného auditu / 0,48 s. Konečná celá sada **1 549 prošlo / 448,00 s**, Ruff OK; 0 chyb, selhání a přeskočení. |
| E.4 | Nativní zkoušky zdrojového okna hotové podle [protokolu](p1-4-agent-overeni-macos-2026-10-24.md); matice níže. Místní měřicí evidence a obě celé CI včetně baseline a self-testů stažených balíčků se vážou ke konkrétní hlavě; konečné odkazy a výsledky uvádí PR #39 při předání. |

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
důkazem konečné hlavy PR. Vydání z `main` se tímto PR nespouští.

Při chybě nejprve ulož pracovní JSON kopii, přečti prvek a příčinu pod stromem,
oprav parametr/výběr nebo použij Zpět a počkej na úspěšný přepočet. Export se
obnoví sám. Po změně dílu zvlášť zkontroluj oblast NDT, případně ji znovu vyber,
technicky potvrď pro aktuální díl a teprve potom spočítej novou mapu.
Odborné ověření starého dílu se tím neobnovuje. Přepočet lze opakovat;
Zastavit se vrací do posledního skutečně spočítaného receptu.

Rozsah nezahrnuje nový formát, nové geometrické operace ani změnu algoritmů NDT.
R03, R04, R12 a NDT-17 zůstávají otevřené. Bez dalšího pokynu autora neslučovat.

# P2.3 — výpočet přímých úprav ploch: evidence

Implementace podle schválených [G1–G8](p2-1-navrh-rozsahu-primeho-modelovani.md)
a [H1–H8](p2-2-navrh-zapisu-prime-upravy.md). Výchozí main
`857afcd2b5ad7211c429479451a896a4ca61d9c9` (po sloučení PR #43). Prostředí: cloud Linux,
Python 3.13.17, build123d 0.13.0, OCCT 8.0.1, PySide6 6.11.2 (offscreen).

## Co se změnilo

| Místo | Změna |
|---|---|
| `direct_edit.py` (nový) | `move_face`, `set_diameter`: posun jen vybrané plochy (`BRepOffset_MakeOffset` + `SetOffsetOnFace`), kontroly vstupu G6 (druh plochy, hladce navazující soused) a výsledku G5 (příslušnost plochy, platnost a počet těles podle P1, stejný počet ploch, žádná plocha s výměrou ≤ 10⁻⁶ mm², poloha upravené plochy do 10⁻⁶ mm, rozlišitelná změna objemu). Pojistka původu `face_origin` / `check_origin` (H3, H4). |
| `features.py` | prvky `move_face` a `face_diameter`, `BuildContext.history` (díl po každém přijatém prvku, jen ke čtení), obě v `VOLUME_FEATURES`, ne v `REPEATABLE_FEATURES`; text chyby pole/zrcadlení zmiňuje přímé úpravy; popis ve stromu („– o −3 mm“, „– na Ø8“). |
| `rebuild.py` | po přijetí prvku zapíše `(id, díl)` do `ctx.history`. |
| `document.py` | `VERSION = 23`, načítání 1–23. |
| `schema.py`, `gui/` | schémata obou typů s `menu=False` (v nabídce *Přidat prvek* nejsou – plochu vybere až P2.4), editor zobrazí plochu a původ jen ke čtení, číslo jde měnit. |
| `examples/prime_upravy.json` (nová ukázka) | deska s čepem a dvěma dírami, horní plocha posunutá o −4 mm a kopie díry na Ø10; objem 37 922,478 mm³ = 60·40·16 + π·6²·14 − π·4²·16 − π·5²·16. Strážce `test_native_input_audit_examples_cover_all_registered_builders` vyžaduje ukázku pro každý typ prvku; ukázka má i baseline v `test_p12a_compatibility.py`. |
| `README.md` | oddíl „Formát modelu“: verze 23 (oprava **R12**), oba typy v tabulce prvků a vlastní pododdíl – pokyn AI je tak zná. |
| testy | nový `tests/test_direct_edit.py` (50 případů), GUI test editoru; u 17 kontrol uložené verze 22 → 23 (H6, nic jiného se v nich nemění). Strážce transakcí P1.2B (`test_every_context_field_is_accounted_for`) správně ohlásil nové pole `history`: kandidát prvku ho teď dostává jako n-tici jen ke čtení a nový test `test_candidate_cannot_change_history_of_accepted_parts` to hlídá. |

## Matice a testy

Q-případy z P2.1, W-případy z P2.2; všechny v `tests/test_direct_edit.py`, pokud není
uvedeno jinak.

| Č. | Test | Výsledek |
|---|---|---|
| Q01 | `test_q01_box_top_face_moves` | objem, rozměry i výška horní plochy podle vzorce |
| Q02 | `test_q02_face_moved_through_the_part_is_rejected` | chyba, díl beze změny, další prvek přeskočen |
| Q03 | `test_q03_through_hole_diameter` | Ø8 i Ø12, osa na místě |
| Q04 | `test_q04_blind_hole_keeps_depth` | dno v původní hloubce |
| Q05 | `test_q05_boss_diameter_keeps_height` | čep Ø12, výška beze změny |
| Q06 | `test_q06_hole_breaking_the_wall_is_rejected` | odmítnuto |
| Q07 | `test_q07_slanted_face_moves_along_its_normal`, `test_q07_trapezoid_top_extends_slanted_sides` | objem i poloha boku |
| Q08 | `test_q08_sharp_neighbouring_fillets_keep_radius` | poloměry R3 zachované |
| Q09 | `test_q09_tangent_neighbour_is_rejected_before_the_kernel` | odmítnuto před jádrem |
| Q10 | `test_q10_chamfered_hole` | Ø11 podle vzorce, Ø12 odmítnuto (zaniklé sražení) |
| Q11 | `test_q11_step_face` | +3 vzorec, +10 a +15 odmítnuto |
| Q12 | `test_q12_pocket_bottom` | hloubka 3 a 8 mm |
| Q13 | `test_q13_fork_inner_wall` | +10 vzorec, +22 odmítnuto |
| Q14 | `test_q14_pin_stays_in_place_when_its_face_moves` | čep zkrácen o 5 mm |
| Q15 | `test_q15_flange_one_bolt_hole` | jedna díra Ø20, tři Ø18 |
| Q16 | `test_q16_flange_faces` | tloušťka 15 a 21 mm podle vzorce, horní −3 odmítnuto |
| Q17 | `test_q17_values_without_effect_or_invalid` | 0, dělení nulou, neznámý parametr, stejný a záporný průměr |
| Q18 | `test_q18_face_of_another_part_is_rejected` | odmítnuto (jádro by plochu tiše přeskočilo) |
| Q19 | `test_q19_unsupported_faces` | kužel, jádro i ploška vymodelovaného závitu odmítnuty |
| Q20 | `test_q20_other_bodies_stay_unchanged` | druhé těleso 1 000 mm³ beze změny |
| Q21 | `test_q21_following_features_use_edited_part` | díra podle vzorce, zaoblení na výšce 25 |
| Q22 | `test_q22_parameter_change_before_the_edit_follows_or_stops` | sleduje desku, zastaví záměnu čepu |
| Q23 | `test_q23_session_undo_redo_and_reopen` | Zpět, Znovu, uložení a otevření přes `ModelSession` |
| Q24 | `test_w15_ndt_study_goes_stale_and_measurement_follows` | otisk NDT se změní, měření ukáže 25 mm |
| W01, W02 | `test_w01_w02_old_files_open_and_save_as_23` | verze 1–22 se načtou a postaví, uloží se 23 |
| W03 | `test_w03_both_types_survive_save_and_open` | totožný dokument i objem |
| W04 | `test_w04_newer_version_is_refused` | verze 24 odmítnuta |
| W05, W06 | `test_w05_w06_bad_face_reference`, `test_w06_diameter_needs_a_cylinder` | chybějící plocha, jiný druh, neznámý klíč |
| W07 | `test_q17_values_without_effect_or_invalid` | viz Q17 |
| W08 | `test_w08_missing_origin` | „chybí původ plochy“ |
| W09 | `test_w09_origin_not_before_the_edit` | neexistující i pozdější prvek |
| W10 | `test_w10_swapped_face_stops_with_czech_error`, `test_w10_moved_pattern_copy_is_not_replaced_by_the_original` | záměna po smazání čepu, po změně parametru H a po posunu kopie pole |
| W11 | `test_w11_ordinary_changes_pass` | změna H a průměru díry před úpravou projde |
| W12 | `test_w12_known_limit_copy_of_the_same_pattern` | **přiznaná mez** – jiná kopie téhož pole se upraví |
| W13 | `test_w13_two_edits_of_the_same_face` | druhá úprava má původ v první |
| W14 | `test_w14_pattern_cannot_repeat_a_direct_edit` | odmítnuto, text zmiňuje přímou úpravu |
| W15 | `test_w15_ndt_study_goes_stale_and_measurement_follows` | viz Q24 |
| W16 | `test_w16_ai_prompt_knows_the_new_format` | pokyn AI obsahuje oba typy a verzi 23 |
| okno | `tests/test_gui.py::test_direct_edit_feature_shows_its_face_and_edits_only_the_value` | plocha a původ jen k prohlédnutí, číslo jde měnit, v nabídce typy nejsou |

## Nový nález mimo rozsah (N1)

`build123d.Face.radius` vrací u některých válcových ploch `None` (např. díra, která
protíná okraj dílu). `selectors.find_face` s klíčem `radius` pak u takové plochy spadne
na `TypeError`; uložené měření to dnes ukáže jako „neočekávaná chyba jádra“ místo
hodnoty (reprodukce: deska 40 × 30, díra Ø10 v ose a kopie pole po 12 mm v ose Y,
měření průměru kopie s `"radius": 5`). Program nespadne. Přímé úpravy používají poloměr
z adaptéru plochy a nález se jich netýká. **Neopraveno** – podle pravidel projektu patří
oprava do samostatného návrhu.

## Celé ověření

VYPLNIT po doběhnutí.

## Co zůstává

- P2.4: výběr plochy ve 3D (*Převzít výběr* doplní `face` i `origin`), náhled, Použít /
  Zrušit, nástroj AI. Do té doby jde úpravu vytvořit jen zápisem do souboru nebo přes AI
  s ručně zadaným `origin`.
- P2.5: přijetí na obou systémech a ruční zkouška autora.
- Zbytek R04 (W12), R03, NDT-17, nález N1.

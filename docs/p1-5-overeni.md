# P1.5 — přijetí bezpečné geometrie a evidence

Autor 24. 10. 2026 schválil [F1–F9, F.1–F.4 a P01–P24](p1-5-navrh-prijeti-bezpecne-geometrie.md)
slovem **„schvaluji“** po předložení návrhového [PR #40](https://github.com/JendaNDT/SkodaCAD/pull/40).
Tím povolil provedení, nikoli sloučení do main ani produkční opravy podle F8.
Výchozí main je `e7f9ac6111fa789a7bbaa80aba6e8cfda9c45271`; implementační větev
`codex/p1-5-acceptance` vychází z návrhu `ec26699f0d9f4091503779df44a148b2c5190023`.
Produkční zdroje a všechny dosavadní testy jsou v těchto dvou základech shodné.

## Postup a důkazy

| Krok | Stav |
|---|---|
| F.1 | Inventura konkrétních kontrol níže a nová výchozí baseline P0 hotové. Čtyři mezery M1–M4 jsou výslovně oddělené od existujících důkazů. Ruff OK, celý místní pytest **1 549 prošlo / 451,59 s**, bez chyb a přeskočení. Všech 180 odkazů matice má skutečně provedené případy v JUnit. |
| F.2 | Čeká: doplnit M1–M4, bez změny zdrojů nebo dosavadních očekávání. |
| F.3 | Čeká: nový nativní průchod a obě celé konečné CI včetně stažených balíčků. |
| F.4 | Čeká: souhrn, srovnání, konečné předání autorovi; P1 není zatím přijata. |

Výchozí baseline vznikla na stejném Macu M4, Python 3.12.14, s instalovanými
knihovnami zaznamenanými ve zprávě: zahřátí + 3 měření, bez souběžných testů.
Obsahuje šest scénářů, otisky vstupů/zdrojů/měřiče, prostředí a fyzické podpisy.
Celá dosavadní sada má 1 549 případů. Konečné počty a konkrétní běhy budou v předání;
starší zelené CI z P1.4 se nezapočítává jako cílové CI P1.5.

## Jak číst inventuru

Odkaz `zkratka::test_jmeno` znamená přesný test ve složce `tests/`; započítávají
se všechny jeho parametrizované případy. Každé jméno je kontrolované proti AST
skutečného souboru a následně proti výslednému JUnit. Kontrola názvu sama není
důkaz správnosti; při inventuře byly čtené i skutečné podmínky testu.

| Zkratka | Soubor |
|---|---|
| GV | `test_geometry_validation.py` |
| GM | `test_geometry_modifications.py` |
| FE | `test_features.py` |
| ER | `test_rebuild_errors.py` |
| SL | `test_sweep_loft.py` |
| BC | `test_body_counts.py` |
| TX | `test_feature_transactions.py` |
| TI | `test_feature_transaction_interfaces.py` |
| RS | `test_reference_selectors.py` |
| RM | `test_reference_mapping.py` |
| RC | `test_reference_consumers.py` |
| RI | `test_reference_interfaces.py` |
| RL | `test_reference_limits.py` |
| SK | `test_reference_sketcher_roundtrip.py` |
| PK | `test_picking.py` |
| OG | `test_output_guard.py` |
| ON | `test_output_ndt.py` |
| OQ | `test_output_gui.py` |
| BG | `test_background.py` |
| CP | `test_p12a_compatibility.py` |
| GUI | `test_gui.py` |
| EX | `test_examples_and_cli.py` |
| NS | `test_ndt_study.py` |

**Doloženo** níže znamená existující konkrétní regresi se správným očekáváním,
která musí znovu projít na konečné verzi. **Doplnit** není úspěch.
**Známé omezení** není bezpečně vyřešená vazba. **Mimo rozsah** se týká pouze
už předem vyloučeného průniku, nikoli nově zjištěné chyby.

## Přejímací matice P01–P24

| ID a stav inventury | Konkrétní důkaz | Co skutečně kontroluje / zbývá |
|---|---|---|
| P01 — doloženo | `GV::test_first_body_and_two_separate_sketch_regions_are_supported`, `FE::test_rectangle_extrude_gives_exact_box`, `ER::test_second_new_body_is_rejected` | První new/add, objem/rozměry a odmítnutí druhého new. |
| P02 — doloženo | `GV::test_first_body_and_two_separate_sketch_regions_are_supported`, `SL::test_pattern_repeats_a_sweep`, `BC::test_core_cli_and_ai_report_the_same_actual_body_counts` | Obě kružnice, 500π, tři skutečné trubky, jejich součet i zprávy v rozhraních. |
| P03 — doloženo | `GV::test_add_overlap_contacts_separation_and_kernel_resolution`, `BC::test_core_cli_and_ai_report_the_same_actual_body_counts` | Překryv/dotyky/oddělení, obálka, body v původním i přidaném materiálu, nezměněný vstup a skutečný počet. |
| P04 — doloženo | `GV::test_cut_removes_material_at_the_requested_location` | Kapsa i rozdělující pás, skutečně prázdné body, okolní materiál a obálka. |
| P05 — doloženo | `GV::test_two_cutters_make_both_holes_and_one_remaining_body` | 16 000−80π, obě díry i materiál mezi nimi. |
| P06 — doloženo | `GV::test_add_without_effect_is_an_error_and_does_not_record_an_operation`, `GV::test_rejected_cut_keeps_geometry_and_recording` | Bezúčelné přidání, míjející/tečný/úplný řez, nezměněné těleso i záznamy. |
| P07 — doloženo | `GV::test_bad_volume_tool_is_rejected_whole_without_changing_part_or_recording`, `GV::test_open_shell_can_have_positive_volume_without_being_acceptable`, `GM::test_unchanged_identity_does_not_bypass_guard_and_sketch_only_is_valid` | Prázdné/otevřené/smíšené tvary, malé složky a platný 2D mezikrok. |
| P08 — doloženo | `GV::test_nonfinite_geometric_inputs_are_rejected_before_building`, `GV::test_cut_effect_boundary_at_different_scales`, `GV::test_add_effect_boundary_uses_result_and_not_tool_volume`, `GV::test_real_booleans_at_model_scales`, `GV::test_real_shallow_cut_is_decided_by_measured_not_nominal_effect` | Aritmetická hranice oddělená od skutečného OCCT; také konečnost vstupů a měřítka. |
| P09 — doplnit M4 | `GV::test_add_overlap_contacts_separation_and_kernel_resolution`; existující zprávy `BC::test_core_cli_and_ai_report_the_same_actual_body_counts` | Skutečné mikromezery jsou ověřené přímo přes kontext; chybí spojení právě těchto dvou numerických případů se zprávou prvku po přepočtu. |
| P10 — doplnit M1 | `FE::test_fillet_vertical_edges`, `GM::test_chamfer_four_vertical_corners_matches_formula_and_preserves_body_count` | Sražení už má bodovou kontrolu. Vnější R3 zatím ověřuje objem, chybí materiál v každém rohu a geometrie válcových zaoblení. |
| P11 — doloženo | `GM::test_inner_corner_modifications_can_add_material` | Objemové vzorce, obálka, výplň vnitřního rohu a nezměněný původní díl pro oba druhy. |
| P12 — doplnit M3 | `GM::test_open_shell_keeps_envelope_floor_and_wall_material`, `GM::test_shell_without_openings_or_with_impossible_wall_is_rejected` | 8 472, obálka, dno/stěny/dutina, bez otevření a nemožná stěna; doplnit explicitní nenalezenou otevřenou plochu. |
| P13 — doplnit M2 | `SL::test_ruled_loft_between_squares_is_a_pyramid_frustum`, `SL::test_loft_between_circles_is_a_cone_frustum`, `SL::test_loft_errors_are_czech`, `SL::test_hollow_cone_has_wall_perpendicular_to_the_surface`, `SL::test_hollow_round_to_square_keeps_the_wall_in_the_sketch_planes` | Objem a chyby i oba významy duté stěny existují. Doplnit výšku, tři analytické průřezy a polohu materiálu u dvou jednoduchých plných loftů. |
| P14 — doloženo | `TX::test_whole_feature_failure_discards_all_context_changes`, `TX::test_real_late_failure_restores_operations_and_material`, `TX::test_thread_failure_after_drilling_discards_the_entire_hole`, `TX::test_failed_sketch_is_not_published_in_build_result` | Všech pět polí, aliasy, reálné pozdní podoperace i řízená chyba závitu; nikoli pouze objem. |
| P15 — doloženo | `RS::test_equidistant_edges_reject_without_removing_original_material`, `RS::test_fixed_face_radius_is_hard_and_missing_type_is_not_a_fallback`, `RM::test_line_mapping_checks_both_endpoints_and_all_candidates`, `RM::test_entire_circular_arc_interval_is_contained`, `RC::test_ndt_methods_cannot_silently_use_only_the_unbroken_subset` | Jednoznačnost, pevné filtry, celý fragment/oblast a pořadí. Podrobná S01–S20 níže. |
| P16 — známé omezení | `RL::test_deleted_hole_can_still_resolve_to_a_different_unique_geometric_match`, `RL::test_geometric_replacement_has_no_persisted_topological_identity`, `RL::test_top_offset_survives_deleted_pocket_without_proving_a_physical_floor` | Charakterizace přijetí náhradní shody; historická identita není vyřešená. |
| P17 — doloženo | `SK::test_existing_profile_transfers_projected_references_through_editor_and_history` | Přidání/výměna/smazání reference přes skutečné akce skicáře, geometrie, historie, kopie i zdrojové bajty; viewer/dialog jsou v tomto testu nahrazené. |
| P18 — doloženo testy; nový nativní průchod čeká | `OG::test_failed_history_cannot_create_or_overwrite_geometry`, `OG::test_section_remains_visible_but_partial_recipe_cannot_export_it`, `OG::test_cli_refuses_all_outputs_before_mkdir_or_write`, `OG::test_valid_two_body_export_preserves_both_solids`, `EX::test_examples_build_and_export_everything`, `GUI::test_export_menu_writes_file` | Všechny formáty a přímé cesty, původní bytes, 2 tělesa po STEP. Platný kvádr přes GUI se znovunačteným STEP ověří i nový nativní protokol F.3. |
| P19 — doloženo | `OG::test_invalid_json_can_be_saved_reopened_and_repaired_with_history`, `OQ::test_bad_recipe_can_be_saved_as_copy_reopened_and_repaired`, `OQ::test_parameter_repair_undo_redo_and_explicit_study_confirmation` | Chybná pracovní kopie, originál, oprava i odemčení/zamčení exportu a stav studie. |
| P20 — doloženo | `ON::test_every_ndt_entry_rejects_partial_model_without_mutating_it`, `ON::test_each_real_result_cannot_reappear_after_worker_failure`, `ON::test_incomplete_confirmation_is_rejected_and_stale_study_does_not_block_geometry`, `OQ::test_stopped_audit_preserves_one_real_result_and_marks_the_remaining_study` | Všechny vstupy, skutečné výsledky všech metod, dostupnost, technické potvrzení a částečná zpráva. E01–E22 níže doplňuje konkrétní cesty. |
| P21 — doloženo | `BG::test_rebuild_in_worker_matches_direct_rebuild`, `BG::test_crashed_worker_is_reported_and_replaced`, `BG::test_cancel_returns_to_last_computed_state_and_redo_retries`, `ON::test_late_reply_from_replaced_job_cannot_restore_old_result_or_map`, `OQ::test_timeout_and_stop_restore_the_actual_last_recipe` | Skutečný spawn/pád/rušení vedle oddělené řízené pozdní odpovědi a timeoutu. |
| P22 — doloženo | `RI::test_cli_offline_report_history_and_saved_copy_keep_the_same_reference_state`, `OQ::test_export_handlers_refuse_before_opening_file_dialog`, `OQ::test_ai_reports_partial_image_and_repairs_offline`, `ON::test_successful_one_off_cli_uses_overridden_recipe_fingerprint` | Konzistence session/CLI/GUI/offline AI, přímá akce a původ skutečného receptu. |
| P23 — doloženo s vymezeným rozsahem | `CP::test_all_recursive_examples_keep_baseline_geometry_and_round_trip`, `CP::test_simple_legacy_recipe_loads_without_new_persisted_fields`, `NS::test_old_models_load_without_ndt_and_save_as_current_version` | 26 ukázek, jednoduché verze 1–22 a staré recepty bez NDT. Konkrétní novější sekce níže; netvrdí všechny možné historické kombinace. |
| P24 — doplnit F.3/F.4 | Nové celé Windows/macOS CI, JUnit a self-testy stažených balíčků; baseline před/po | Výchozí baseline je uložená. Nové CI a konečné měření nejsou ještě vykazované jako hotové. |

## Přesné mezery F.2

| ID | Minimální doplnění | Nezávislé očekávání |
|---|---|---|
| M1 | Vnější svislá R3 na kvádru, všechny čtyři rohy. | Vzorec objemu, 1 solid, obálka, body uvnitř a mimo zaoblený roh ve více výškách, čtyři válcové plochy R3; původní Part se nezmění. |
| M2 | Plný čtvercový a kruhový loft 40→20 / výška 30. | 28 000 / 7 000π, obálka, řezy z=5/15/25 s lineárně klesající stranou/poloměrem a body po obou stranách pláště; originál se řezy nemění. |
| M3 | Explicitní sražení 50 a nenalezená otevřená plocha skořepiny. | Chyba správného prvku, český důvod, přeskočený konec, původní kvádr/obálka/materiál; žádná změna tolerance. |
| M4 | Stejné dvě mikromezery přes celý recept. | 24 250, obálka, oba objemy a zpráva 1→skutečné N; při 10⁻⁸ N∈{1,2}, bez falešného tvrzení o fyzickém spojení. |

Tyto mezery jsou chybějící důkazy, nikoli zatím prokázané produkční vady.
Pokud nová regrese odhalí vadu, platí F8: reprodukce a samostatný návrh opravy.

## Předchozí smlouvy a matice

Následující tabulky používají přesné P-identifikátory výše; jde o dohledatelný
řetězec požadavek → P-případ → konkrétní test a jeho fyzické podmínky, nikoli
o tvrzení založené pouze na odkazu na soubor. Stavy P-případů se dědí včetně mezer.

### Rozhodnutí

| Smlouva | Pokrytí a mez |
|---|---|
| D1 | P02–P04, P09; počty a jejich zprávy, více solidů je povolené. |
| D2 | P03–P08, P14; tvar, účinek i prostorová poloha. |
| D3 | P08–P09; aritmetika oddělená od OCCT, tolerance beze změny. |
| D4 | P10–P13; obě úpravy rohů a otevřená skořepina. |
| D5 | P14, P19–P22; kontext, recept, náhled a vratnost. |
| D6 | X01–X03 jsou mimo rozsah, nevzniká nová operace průniku. |
| D7 | Schválení každé etapy doložené návrhy/protokoly; tento dokument zaznamenává nové schválení, ne souhlas se sloučením. |
| A1, A2 | P01–P14 a `GM::test_every_current_3d_type_is_classified_for_the_final_guard`, `GM::test_final_guard_rejects_a_builder_bypassing_the_acceptance_path`. |
| A3 | P06–P09, P12; bez tichého opravování nebo změny tolerancí. |
| A4 | P02–P03, P09, `GUI::test_successful_body_counts_are_visible_in_tree_and_properties`, `GUI::test_long_feature_name_keeps_body_count_visible_in_a_narrow_tree`. |
| A5 | P01–P23 a V1–V14 níže. |
| A6, A7 | Historické commity/CI/autorovo přijetí v [P1.2A](p1-2a-overeni.md); nové cílové ověření P24 čeká. |
| B1, B2 | P14; `TX::test_every_context_field_is_accounted_for`, `TX::test_candidate_container_changes_cannot_mutate_accepted_aliases`, `TX::test_whole_feature_failure_discards_all_context_changes`. |
| B3 | `TX::test_mutation_of_an_owned_shape_copy_cannot_change_original_geometry`, `CP::test_all_recursive_examples_keep_baseline_geometry_and_round_trip`; audit vlastnictví při každém prvku všech ukázek. |
| B4 | `TX::test_changed_working_parameters_are_rejected_before_any_publication`, `TX::test_changed_nested_json_is_rejected_without_mutating_the_source`, `TX::test_successful_return_does_not_accept_hidden_input_changes`. |
| B5, B6 | P14, P19, P21–P23 a T01–T14 níže. |
| B7 | Historické přijetí/CI v [P1.2B](p1-2b-overeni.md); P24 ověří dnešní balíčky. |
| C1, C2 | P15; skupiny/nejednoznačnost/duplicity v S02–S06 níže. |
| C3, C4 | P15; pevné filtry, normály, krajní roviny v S07–S08/S13. |
| C5, C6 | P15, P17, P20; tvorba/přenos, celý fragment a všichni spotřebitelé v S09–S17. |
| C7 | P16, P23; charakterizované meze, formát/IPC bez nových polí. |
| C8 | Historické přijetí v [P1.3](p1-3-overeni.md); nová F.3/P24 čeká. |
| E1, E2 | P18, P21; celý aktuální model a výstupy. |
| E3 | P19, P22; zachovaný chybný recept, oprava, diagnostika i historie. |
| E4, E5 | P19–P20; NDT stavy, potvrzení a původ výsledků. |
| E6, E7 | P20–P22; CLI/session/offline AI, skutečné výsledky a cache. |
| E8, E9 | P18–P24 a E01–E22 níže; historické přijetí P1.4 a nové balíčky jsou oddělené. |

### Geometrická matice P1.1

| Původní ID | Konkrétní přejímací důkaz |
|---|---|
| G01, G02, G03, G04 | P07–P08; prázdný/open/mixed/malá složka a konečná čísla. |
| N01, N02, N03 | P01–P02. |
| A01, A02, A03, A04 | P03; všechny odpovídající parametrizace GV. |
| A05 | P06; vnitřní a totožný nástroj. |
| C01, C04 | P04; kapsa a rozdělení. |
| C02, C03 | P06; miss/touch/whole. |
| C05 | P05; skutečně obě díry. |
| F01 | P10 / M1; doplnit prostorový důkaz. |
| F02, H02 | P11; růst objemu vnitřního rohu je správný. |
| F03 | `ER::test_too_large_fillet_keeps_previous_part_and_skips_rest`, `ER::test_feature_errors_have_czech_messages`, `GM::test_invalid_modification_dimensions_keep_previous_geometry`. |
| H01 | P10; existující sražení čtyř rohů. |
| H03 | P10 / M3; negativní rozměr existuje, s50 doplnit. |
| S01, S02 | P12 / M3; chybějící konkrétní otevřenou plochu doplnit. |
| L01, L02 | P13 / M2; prostorové průřezy doplnit. |
| L03, L04 | P13; existující chyby skic a oba významy dutého loftu. |
| M01 | P02 a zprávy BC. |
| M02 | P14; skutečné pozdní pole/zrcadlení. |
| T01, T02 | P09 / M4; numerické meze přiznané. |
| T03 | P08; přesné hranice i reálné mělké řezy/měřítka. |
| X01, X02, X03 | Mimo rozsah: pouze budoucí specifikace průniku. |

### Matice V1–V14 z P1.2A

| Původní ID | Důkaz |
|---|---|
| V1 | P07; všechny složky i kontejnery, dutina v `GV::test_valid_separate_solids_and_a_closed_cavity_are_preserved`. |
| V2 | P08 a `GM::test_invalid_modification_dimensions_keep_previous_geometry`; konečný záporný posun není rozměrem vyžadujícím kladnost. |
| V3 | P01–P02. |
| V4 | P03, P06. |
| V5 | P04–P06. |
| V6 | P10–P11, M1/M3, F03 výše. |
| V7 | P12/M3. |
| V8 | P13, registr GM a `CP::test_native_input_audit_examples_cover_all_registered_builders`; analytické rotace/tažení/standardy/závity zůstávají ve celé původní sadě. |
| V9 | P02, P14. |
| V10 | P08–P09/M4. |
| V11 | P02–P03, P09/M4 a GUI z rozhodnutí A4. |
| V12 | `BC::test_body_messages_survive_existing_transfer_without_new_protocol_fields`, `BC::test_body_messages_survive_a_real_spawned_rebuild`, `BC::test_new_rejections_can_be_undone_redone_repaired_and_saved`. |
| V13 | P23. |
| V14 | P07, závěrečná pojistka GM z rozhodnutí A1/A2. |

### Matice T01–T14 z P1.2B

| Původní ID | Důkaz |
|---|---|
| T01, T02 | `TX::test_whole_feature_failure_discards_all_context_changes`; všech pět typů výjimky i původní aliasy. |
| T03 | `TX::test_success_records_all_operations_once_and_preserves_older_aliases`, `TX::test_complete_recording_is_replayed_once_in_original_order`. |
| T04 | `TX::test_failed_sketch_is_not_published_in_build_result`, 2D případ P07. |
| T05 | `TX::test_final_volume_guard_rejects_metadata_together_with_bad_geometry`, pojistky GM. |
| T06, T07 | `TX::test_real_late_failure_restores_operations_and_material`; skutečné pole i zrcadlení, geometrie, pořadí a nástroje. |
| T08 | `TX::test_thread_failure_after_drilling_discards_the_entire_hole`; skutečné úspěšné závity zůstávají v celé sadě. |
| T09 | `TX::test_unknown_type_never_prepares_a_candidate_and_preserves_state`, `TX::test_candidate_preparation_failure_is_reported_without_changes`, `TX::test_missing_recording_rejects_before_publication`. |
| T10 | Testy rozhodnutí B4. |
| T11 | Testy rozhodnutí B3 a P23. |
| T12 | `TI::test_partial_or_complete_result_survives_existing_bin_tools_protocol`, `TI::test_real_spawn_preserves_failure_repair_and_accepted_sketches`, P21. |
| T13 | `TI::test_repair_undo_redo_round_trip_and_interface_messages`, `BG::test_late_transaction_failure_repair_and_history_in_background_window`. |
| T14 | P23, registr všech polí TX a původní sada jako celek. |

### Matice S01–S20 z P1.3

| Původní ID | Důkaz |
|---|---|
| S01 | `PK::test_picked_fillet_follows_parameter_change`. |
| S02 | `RS::test_group_union_keeps_every_prescribed_edge_once`, `RS::test_named_plane_uses_extreme_not_first_level_inside_group_band`. |
| S03 | `RS::test_equidistant_edges_reject_without_removing_original_material`. |
| S04 | `RS::test_edge_distance_boundary_and_duplicates`, `RS::test_distance_tie_on_real_geometry`. |
| S05 | `RS::test_two_bodies_have_ambiguous_faces_but_a_valid_named_plane`. |
| S06 | `RS::test_edge_point_on_two_faces_needs_a_distinguishing_normal`, `RS::test_normal_score_boundary_is_independent_of_order`. |
| S07 | `RS::test_fixed_face_radius_is_hard_and_missing_type_is_not_a_fallback`, `RC::test_fixed_radius_change_is_visible_until_explicit_new_selection`. |
| S08 | `RS::test_bad_face_input_is_rejected_before_accessing_geometry`, `RS::test_bad_edge_input_is_validated_before_any_geometry_filter`, `RS::test_invalid_near_is_not_hidden_by_an_empty_circle_filter`. |
| S09 | `RM::test_fallback_recovers_with_sufficient_precision_and_is_rechecked`, `RM::test_final_fallback_refuses_an_unrepresentable_selection`, `RM::test_curved_face_reference_must_resolve_to_the_actual_clicked_shape`. |
| S10 | `RM::test_line_mapping_checks_both_endpoints_and_all_candidates`, `RM::test_entire_circular_arc_interval_is_contained`, `RM::test_equal_radius_or_a_common_point_is_not_the_same_circle`, `RM::test_general_curve_requires_native_identity_for_cross_state_mapping`, `RL::test_almost_parallel_circle_carriers_are_not_the_same_plane`, `RL::test_carrier_position_and_radius_errors_cannot_each_consume_the_full_distance_band`. |
| S11 | `RM::test_real_section_fragments_map_without_mutating_original_geometry`, `RM::test_one_interior_point_cannot_map_a_fragment_spanning_two_original_faces`, `RM::test_distinct_containing_faces_are_ambiguous_and_opposite_orientation_is_refused`. |
| S12 | `RC::test_projection_reports_ambiguity_and_never_reuses_stale_points`, P17. |
| S13 | `RS::test_split_top_face_rejects_point_in_slot_but_preserves_named_group`. |
| S14 | P15, `RC::test_fixed_radius_change_is_visible_until_explicit_new_selection`, fyzické hodnoty v `RI::test_cli_offline_report_history_and_saved_copy_keep_the_same_reference_state`. |
| S15 | `RC::test_ambiguous_study_cannot_be_confirmed_and_repair_has_undo_history`, `RC::test_ndt_methods_cannot_silently_use_only_the_unbroken_subset`, P20. |
| S16 | `RI::test_reference_states_use_the_unchanged_nine_key_bin_tools_protocol`, `RI::test_real_spawn_preserves_bad_good_bad_reference_results`, `RI::test_qt_window_repairs_actual_worker_geometry_by_replacing_the_picked_edge`, P22. |
| S17 | `RI::test_cli_offline_report_history_and_saved_copy_keep_the_same_reference_state`, P17. |
| S18 | P23 a původní TNP/měření ve celé sadě. |
| S19 | `RS::test_two_bodies_have_ambiguous_faces_but_a_valid_named_plane`, P14/P21; nové P0 měření před/po a historické benchmarky P1.3 jsou rozlišené. |
| S20 | P16 — známé omezení, ne bezpečné odmítnutí. |

### Matice E01–E22 z P1.4

| Původní ID | Důkaz |
|---|---|
| E01, E02 | P18; EX všechny formáty, GUI exportní akce, OG obě tělesa po STEP; nový nativní průchod čeká. |
| E03, E04 | `OG::test_failed_history_cannot_create_or_overwrite_geometry`, `OG::test_cli_refuses_all_outputs_before_mkdir_or_write`, `OQ::test_export_handlers_refuse_before_opening_file_dialog`. |
| E05 | `OG::test_empty_or_sketch_only_model_has_no_exportable_body`, `OG::test_shared_guard_rejects_empty_shape_and_skipped_without_first_error`, `OQ::test_error_in_saved_measurement_does_not_block_valid_geometry_export`. |
| E06 | `OQ::test_real_background_rebuild_recovers_window_actions`, vstupy ON v P20. |
| E07 | `OG::test_failed_worker_cannot_export_old_ok_result_and_retry_recovers`, `ON::test_each_real_result_cannot_reappear_after_worker_failure`, `OQ::test_failed_worker_shows_stale_warning_even_with_previous_ok_result`. |
| E08 | `OQ::test_timeout_and_stop_restore_the_actual_last_recipe`, skutečné rušení BG z P21. |
| E09, E10 | `ON::test_every_ndt_entry_rejects_partial_model_without_mutating_it`, `ON::test_no_ndt_output_is_created_or_overwritten_on_partial_model`, `ON::test_geometry_picks_cannot_anchor_a_study_to_partial_body`. |
| E11 | `ON::test_failed_history_never_validates_targets_or_computes_thickness`, `ON::test_old_real_maps_stay_hidden_after_failed_rebuild_and_fresh_results_recover`. |
| E12 | `ON::test_actual_spawn_keeps_failed_history_diagnostic_and_recovers`, `OQ::test_parameter_repair_undo_redo_and_explicit_study_confirmation`, `OQ::test_stale_study_working_preview_is_labelled`. |
| E13 | `ON::test_incomplete_confirmation_is_rejected_and_stale_study_does_not_block_geometry`, S15/RC. |
| E14 | `ON::test_each_real_result_cannot_reappear_after_worker_failure`; skutečné výsledky všech metod i zpráv. |
| E15 | `ON::test_late_reply_from_replaced_job_cannot_restore_old_result_or_map`, P21 a S17. |
| E16 | `OQ::test_stopped_audit_preserves_one_real_result_and_marks_the_remaining_study`; skutečná první PT mapa a řízené doručení do auditu. |
| E17 | Vstupy/výstupy ON v E09/E10 a `OQ::test_gui_cannot_export_old_report_or_pdf_after_worker_failure`. |
| E18 | `test_ndt_design.py::test_variant_that_cannot_be_evaluated`, `test_ndt_design_session.py::test_session_settings_undo_and_separate_variant`; konkrétní neúspěšná varianta, odmítnuté použití a zachovaný originál. |
| E19 | `OQ::test_partial_model_has_persistent_warning_and_unavailable_outputs`, P19/P21; nový nativní průchod čeká. |
| E20 | `OQ::test_ai_reports_partial_image_and_repairs_offline`, `OQ::test_ai_labels_stale_body_after_failed_worker`. |
| E21 | P19, přímé GUI ukládání a kopie. |
| E22 | `ON::test_direct_cli_ndt_commands_never_use_partial_body`, `ON::test_successful_one_off_cli_uses_overridden_recipe_fingerprint`. |

### Konkrétní kompatibilita novějších sekcí

Vedle jednoduchých receptů v1–22 jsou zachované zejména
`test_ndt_volume_session.py::test_older_versions_keep_face_studies_and_original_file_until_explicit_save`,
`test_ndt_library.py::test_format_17_stores_probe_origins_and_ut_material`,
`test_ndt_mt_session.py::test_format_20_saves_mt_and_rejects_it_in_other_studies`,
`test_ndt_rt_session.py::test_format_21_saves_rt_and_rejects_it_in_other_studies`,
`test_ndt_design_session.py::test_format_22_and_backwards_compatibility`,
`SL::test_format_version_11_loads_and_old_files_still_open` a
`test_standards.py::test_format_version_12`. Testy očekávají konkrétní obsah
sekcí, původní soubory a současný zápis; nejde o slib všech historických souborů.

## Omezení a brána předání

R03 — zápis není atomický a test zachování session neprokazuje obnovu při přerušení
diskového zápisu. R04/P16 — není uložená historická identita ploch. R12 — oddíl
README používaný AI se tímto nemění. Žádné nové NDT algoritmy ani jejich odborné
přijetí. NDT-16 mimo rozsah, NDT-17 samostatně. Více těles není sestava P5.

Místní Qt testy mají náhradní viewer/dialogy, řízené poruchy nepředstírají pád
OCCT. Nativní průchod a balíčky budou oddělené. Windows F7 vyžaduje skutečné
spuštění v CI; fyzická ergonomie Windows ani všechny Retina/trackpad/GPU varianty
se netvrdí. Samostatný souhlas autora je nutný pro konečné přijetí a sloučení.

Předání může proběhnout až po M1–M4, novém místním Ruff/celém pytest,
obou úplných konečných workflow, kontrole stažených balíčků, dostupném Mac
průchodu a pravdivém protokolu. Případný produkční nález tuto bránu blokuje
v povinném rozsahu a postupuje se podle F8, ne změnou očekávání.

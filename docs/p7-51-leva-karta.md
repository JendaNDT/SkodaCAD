# P7.51 – levá karta Prvky | Parametry | Díl (vydání B, krok 1)

*Součást [plánu nového okna](p7-48-plan-noveho-okna.md); rozhodnutí R1–R7 schválil
autor 6. 11. 2026.*

## Co se změnilo

- Levá karta má **segmentový přepínač Prvky | Parametry | Díl** (`gui/model_card.py`).
  Ten nahradil čtyři sekce pod sebou, takže už se nemusí posouvat celý dlouhý panel.
  - **Prvky:** filtr prvků (zaoblené pole, Ctrl/⌘+F) a strom. Pod ním patička
    + − ↑ ↓ a počet prvků („1 prvek“, „3 prvky“, „6 prvků“).
  - **Parametry:** filtr parametrů (Ctrl/⌘+Shift+F) a pole parametrů.
  - **Díl:** název, materiál, popis a vlastnosti dílu ve sbalitelných sekcích.
- **Řádky stromu** jsou vysoké 26 px. Vlevo je ikona Duo podle typu prvku (skica,
  vysunutí, díra…), vpravo počet těles a stav ✓ / ✕ v barvě stavu. Vybraný řádek má
  podklad `--accentbg` a tučné písmo. Strom leží přímo na kartě, bez záhlaví sloupců.
- Data řádků se nemění: text „✓  Skica …“ dál slouží filtru, hledání, čtečkám obrazovky
  i testům. Mění se jen kreslení (`FeatureRowDelegate`).
- Ctrl/⌘+F otevře záložku Prvky, Ctrl/⌘+Shift+F záložku Parametry. Zvolená záložka se
  ukládá do `okno.json` (`sidebar_tab`). Obnovit rozložení začne na Prvcích se
  sekcemi Dílu rozbalenými.
- Model, výpočty ani formát souborů se nemění.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_model_card.py` (9) | čeština počtu prvků; tři záložky; data řádků beze změny; ikona, stav a počet těles v kresbě; výška 26 px; Ctrl+F a Ctrl+Shift+F otevřou správnou záložku; sekce Parametry sleduje záložku; uložení a obnova záložky |
| testy okna, filtrů, hledání a rozložení | viz PR |
| self-test „Levá karta“ (Linux Xvfb) | skutečné kliky na záložky Díl, Parametry a Prvky ukážou jejich obsah; skutečné Ctrl+Shift+F a Ctrl+F přepnou záložku; řádky 26 px; „6 prvků“ |

Snímek: [záložky Prvky (světlý, vybraný řádek), Parametry (tmavý) a Díl](p7-48-snimky/leva-karta.png).

## Meze

- Skupina „NDT studie“ pod prvky v činnosti NDT přijde s NDT průvodcem (P7.55).
  Seznam studií zůstává zatím v kartě NDT.
- Souhrn typu „M6 ×4“ vpravo v řádku není. Velikost díry je dál v názvu řádku
  („Díra „Upínání“ – M6 …“) a vpravo je počet těles, jak si autor dřív vyžádal (P7.2).
- Sekce na záložce Díl mají zatím dosavadní tlačítka. Sbalitelné sekce z návrhu
  sjednotí P7.52.

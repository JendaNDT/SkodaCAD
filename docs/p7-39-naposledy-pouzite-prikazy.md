# P7.39 – naposledy použité příkazy v hledání

Navazuje na [P7.37 hledání příkazů](p7-37-hledani-prikazu.md) a
[P7.38 oblíbené příkazy](p7-38-oblibene-prikazy.md). Sloučeno v
[PR #122](https://github.com/JendaNDT/SkodaCAD/pull/122) jako `c537087`.

1. V dílu nebo sestavě otevři **Najít příkaz…** (Ctrl+Shift+P, na Macu ⌘+Shift+P)
   a nic nepiš.
2. Nahoře jsou naposledy použité příkazy, od nejnovějšího. Ve sloupci nabídky mají
   předponu **Nedávno ·**. Pod nimi následují ostatní příkazy v pořadí nabídek.
3. Předvybraný je poslední příkaz, který lze právě spustit. **Enter** ho zopakuje
   bez psaní.
4. Jakmile začneš psát, hledání funguje přesně jako v P7.37: nedávné příkazy
   nemají přednost a označení **Nedávno** zmizí.

## Chování a meze

- Za použití se počítá každé spuštění příkazu, který jde připnout do Oblíbených
  (stálé příkazy aplikace): z nabídky, klávesovou zkratkou, z pásu nebo lišty,
  z hledání i tlačítkem v Oblíbených. Samotné připnutí ani procházení seznamu
  se nepočítá. Položky z názvů ukázkových souborů se nezaznamenávají.
- Pamatuje se nejvýš šest příkazů, zvlášť pro díl a pro sestavu. Otevřená okna
  sestav sdílejí jeden seznam. Opakovaně použitý příkaz se přesune nahoru, nezdvojí se.
- Nedávný příkaz, který teď nejde spustit, zůstává v seznamu s označením
  **[nedostupné]**, ale Enter ho nepředvybere. Když není dostupný žádný nedávný
  příkaz, předvybere se první položka jako dosud.
- Seznam platí jen **do zavření aplikace**: neukládá se na disk, do osobního
  nastavení oblíbených ani do modelu. Po novém spuštění je prázdný. To odpovídá
  P7.37 (bez ukládání historie hledání).
- Spouští se vždy původní příkaz se svou dostupností, potvrzením, náhledem
  a Zpět/Znovu. Žádná změna formátu modelů, geometrie ani závislostí.

## Ověření

- `tests/test_command_search.py::test_recent_commands_precede_menu_order_only_for_empty_search`:
  pořadí od nejnovějšího, limit šest, bez zdvojení, nedostupná položka nahoře
  bez předvýběru, předvybraný poslední dostupný příkaz; po zadání textu běžné
  pořadí bez označení.
- `tests/test_favorite_commands.py`: připnutí historii nemění, kliknutí na
  připnuté tlačítko ji zapíše, nové okno po znovuotevření začíná s prázdnou
  historií, sestavy sdílejí seznam a díl má vlastní.
- Self-test stažené aplikace (díl i sestava) otevře hledání zkratkou, ověří
  prázdné pole, předvybraný poslední příkaz s označením **Nedávno** a zopakuje
  ho Enterem; zapíše řádek „✓ Naposledy použité příkazy“.
- Workflow „Windows aplikace“ a „macOS aplikace“ prošly nad PR i nad `main`
  (`c537087`) včetně kontroly stažených balíčků; vydání `nejnovejsi`
  a `nejnovejsi-mac` z 5. 11. 2026 obsahuje P7.39.

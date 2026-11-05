# P7.40 – filtr stromu prvků v dílu

Navazuje na hledání příkazů [P7.37](p7-37-hledani-prikazu.md), které záměrně
nehledá prvky modelu. U dlouhé historie prvků se ve stromu špatně hledá
konkrétní prvek. Proto má strom prvků nahoře pole filtru jako
prohlížeč modelu v Inventoru nebo Solid Edge.

1. **Ctrl+F** (na Macu **⌘+F**) nebo **Úpravy → Filtrovat strom prvků** dá
   fokus do pole nad stromem. Je-li strom modelu skrytý (F9), otevře ho.
2. Piš část názvu, druhu nebo id prvku, např. `srazeni`, `dira m6`, `deska`.
   Velikost písmen ani diakritika nerozhoduje; více slov musí být přítomných
   všech. Slovo `chyba` najde prvky s chybou přepočtu, `preskoceno` přeskočené.
3. Pod polem je počet: „Filtr: 2 z 6 prvků“. Když nic neodpovídá, řádek to
   napíše a strom je prázdný.
4. **Enter** nebo **↓** vybere první nalezený prvek a přesune fokus do stromu –
   vybraný prvek se zvýrazní ve 3D a otevře v editoru jako po kliknutí.
5. **Esc** v poli (nebo křížek) filtr zruší a strom ukáže všechny prvky.

## Chování a meze

- Filtr je jen pohled. Nemění model, výběr ani historii Zpět a neukládá se.
  Otevření jiného dílu nebo nový díl filtr vyprázdní.
- **Vybraný prvek zůstává vždy vidět**, i když filtru neodpovídá – editor tak
  nikdy neukazuje prvek, který ve stromu chybí. Po přidání nového prvku je ten
  nový vybraný, takže se také ukáže.
- Filtr platí i po přepočtu, změně parametru nebo Zpět: nové řádky se hned
  filtrují stejným textem.
- Řádky stromu se jen skrývají, nikdy nemažou ani nevytvářejí znovu. To chrání
  přístupnost Cocoa na Macu (pád `libqcocoa` při mazání buněk, viz P5.5/P7.3).
- Během náhledu nového prvku a práce AI je strom i filtr zamčený jako dosud.
- Prohledává se jen strom prvků dílu. Parametry, měření a NDT studie filtr
  nemají; strom sestavy ho dostal v [P7.41](p7-41-filtr-stromu-sestavy.md)
  (sdílený `gui/tree_filter.py` umí vnořené řádky a nechá vidět rodiče nalezených).
- Bez změny formátu modelů, geometrie a závislostí.

## Ověření

- `tests/test_tree_filter.py` (7 testů): filtr bez diakritiky a více slov,
  hledání podle id, prázdný výsledek, Esc, zachování týchž řádků stromu,
  nezměněný model a historie; Enter vybere první nalezený a editor ho ukáže;
  vybraný prvek zůstává vidět; filtr po přepočtu a nalezení prvků s chybou;
  vyprázdnění při Otevřít/Nový; Ctrl+F otevře skrytý strom; vnořené řádky
  s rodiči; ovladač self-testu se skutečnými klávesami.
- Související sady okna (`test_gui`, `test_command_search`,
  `test_favorite_commands`, `test_sketcher_gui` a další testy okna) prošly.
- Self-test balíčku (`_self_test_tree_filter`) stiskne v hlavním okně skutečné
  Ctrl+F, napíše jednoznačné id prvku, Enterem ho vybere, Esc obnoví všechny
  řádky a ověří, že se model ani historie nezměnily; zapíše řádek
  „✓ Filtr stromu prvků“. Na Windows a Macu ho spustí workflow nad hotovou dávkou.
- Snímek okna pod Xvfb: příruba, filtr `srazeni`, „Filtr: 2 z 6 prvků“,
  vybrané Sražení obvodu se zvýrazněnými hranami a otevřeným editorem.

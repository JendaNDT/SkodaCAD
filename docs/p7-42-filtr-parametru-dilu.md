# P7.42 – filtr parametrů dílu

Navazuje na filtr stromu prvků [P7.40](p7-40-filtr-stromu-prvku.md) a stromu
sestavy [P7.41](p7-41-filtr-stromu-sestavy.md). U dílu s mnoha parametry
(rozměry, rozteče, počty) se ve skupině *Parametry dílu* špatně hledá ten správný,
proto má skupina nahoře stejné pole filtru.

1. **Ctrl+Shift+F** (na Macu **⌘+Shift+F**) nebo **Úpravy → Filtrovat parametry dílu**
   rozbalí skupinu *Parametry dílu* (a otevře strom modelu, je-li skrytý) a dá
   fokus do pole filtru.
2. Piš část **názvu** nebo **hodnoty** parametru. Velikost písmen ani diakritika
   nerozhoduje, takže `d` najde `D`, `d` i `dh`; `18` najde parametry s hodnotou
   nebo výrazem obsahujícím 18. Více slov musí být přítomných všech.
3. Pod polem je počet, např. „Filtr: 3 z 7 parametrů“.
4. **Enter** nebo **↓** skočí do pole prvního nalezeného parametru (text je
   označený, rovnou přepíšeš hodnotu a Enter ji použije jako dosud).
5. **Esc** v poli filtru (nebo křížek) filtr zruší.

## Chování a meze

- Filtr je jen pohled: nemění model, historii Zpět ani hodnoty a neukládá se.
  Řádky formuláře se jen skrývají (`QFormLayout.setRowVisible`), pole parametrů
  zůstávají tatáž.
- **Upravované pole a pole s chybou zůstávají vidět**, i když filtru neodpovídají
  – červeně označený chybný výraz tak nikdy nezmizí z očí.
- Filtr platí i po Zpět/Znovu a dalších změnách, které pole parametrů obnoví.
  Otevřít a Nový díl filtr vyprázdní; díl bez parametrů pole filtru nezobrazuje.
- Ctrl+F zůstává filtrem stromu prvků (P7.40); filtr parametrů má vlastní zkratku.
- Parametry sestavy mají vlastní tabulku (P7.32–P7.36), tohoto filtru se netýkají.
- Sdílený základ `FilterBox` v `gui/tree_filter.py` drží pole, hlášku, Enter/↓
  a Esc pro filtr stromu i parametrů, aby se chovaly stejně.
- Bez změny formátu, geometrie a závislostí.

## Ověření

- `tests/test_tree_filter.py` (5 nových testů, celkem 18): filtr podle názvu
  i hodnoty bez rozlišení velikosti písmen, prázdný výsledek, Esc, stejná pole,
  nezměněný model a historie; Enter skočí do pole, přepsání hodnoty skutečnými
  klávesami se přijme jako jeden krok Zpět; pole s chybou zůstane vidět; filtr po
  Zpět, vyprázdnění při Otevřít; skutečné Ctrl+Shift+F rozbalí sbalenou skupinu;
  nový díl bez parametrů filtr skryje; ovladač self-testu. Testy filtru nově
  místo zaseknutí na nečekaném dialogu selžou (pravidlo 11).
- Self-test (`_self_test_param_filter`): sbalí skupinu, skutečné Ctrl+Shift+F ji
  rozbalí a dá fokus do filtru, napíše jednoznačný název parametru, Enter skočí do
  jeho pole, Esc obnoví všechny parametry; díl, historie ani pole se nezmění.

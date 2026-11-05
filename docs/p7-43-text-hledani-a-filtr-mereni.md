# P7.43 a P7.44 – zapamatovaný text hledání a filtr uložených měření

Dvě drobnosti ovládání z téže dávky jako [P7.42](p7-42-filtr-parametru-dilu.md).

## P7.43 – text hledání příkazů po zavření

**Najít příkaz…** (Ctrl+Shift+P, na Macu ⌘+Shift+P,
[P7.37](p7-37-hledani-prikazu.md)) si pamatuje rozepsaný text:

- Když hledání zavřeš **bez spuštění** (Esc, Zavřít), příště se otevře s tímtéž
  textem. Text je **označený**: psaním ho přepíšeš, Backspace ho smaže.
- Když příkaz **spustíš**, příště se hledání otevře **prázdné**, takže nahoře
  jsou naposledy použité příkazy a Enter zopakuje poslední
  ([P7.39](p7-39-naposledy-pouzite-prikazy.md)).
- Když pole vymažeš, předvybere se znovu poslední použitý příkaz, ne příkaz,
  který zůstal vybraný ze starého textu (oprava nalezená při této úpravě).
- Díl a každé okno sestavy si text pamatují zvlášť, jen do zavření aplikace;
  nic se neukládá na disk ani do modelu.

## P7.44 – filtr uložených měření

Panel **Měření** má nad seznamem **Uložená měření** pole filtru (stejné
ovládání jako filtr stromu a parametrů, společný základ `FilterBox`):

- **Úpravy → Filtrovat uložená měření** otevře panel Měření a dá fokus do filtru
  (vlastní klávesovou zkratku nemá; Ctrl+F a Ctrl+Shift+F patří stromu
  a parametrům).
- Hledá v textu položky (název a hodnota měření, např. „Vnější průměr: 114.30 mm“)
  i v id (`m2`), bez
  rozlišení velikosti písmen a diakritiky. „Filtr: 2 z 3 měření“.
- **Enter** / **↓** vybere první nalezené (ve 3D se ukáže jeho čára),
  **Esc** filtr zruší. Vybrané měření zůstává vidět vždy.
- Filtr platí i po přepočtu; Otevřít a Nový ho vyprázdní a díl bez uložených
  měření pole nezobrazuje. Jen pohled – model, měření ani historie se nemění.
- Filtruje se jen seznam uložených měření; okamžité měření výběru (pár řádků)
  filtr nemá.

## Ověření

- `tests/test_command_search.py::test_cancelled_search_text_returns_selected_and_run_clears_it`:
  Esc si text zapamatuje, při novém otevření je označený a psaní ho přepíše,
  po spuštění příkazu je pole prázdné s předvybraným posledním příkazem, smazání
  textu vrátí předvýběr posledního použitého.
- `tests/test_tree_filter.py`: dva testy filtru měření na ukázce `trubka.json`
  (tloušťky / průměr / id, vybrané měření zůstává vidět, Enter, Esc, přepočet,
  Otevřít bez měření) a ovladač self-testu.
- Self-test balíčku: krok hledání příkazů nově ověřuje obnovený označený text po
  Zrušit a prázdné pole po spuštění („✓ Text hledání“); nový krok „✓ Filtr
  uložených měření“ otevře trubku, filtruje „tloustka“, Enter, Esc, beze změny dílu.

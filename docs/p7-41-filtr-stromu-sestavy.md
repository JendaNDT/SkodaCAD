# P7.41 – filtr stromu komponent v sestavě

Stejné pole filtru jako ve stromu prvků dílu ([P7.40](p7-40-filtr-stromu-prvku.md))
je nově i nad stromem komponent sestavy. Sdílí ho `gui/tree_filter.py`.

1. **Ctrl+F** (na Macu **⌘+F**) nebo **Úpravy → Filtrovat strom komponent** dá
   fokus do pole nad stromem. Je-li panel *Komponenty* zavřený (F9), otevře ho.
2. Piš část názvu, id nebo souboru komponenty, např. `nozicka`, `vicko.json`,
   nebo stav (`chybi`, `pevna`). Vazby se najdou podle názvu, druhu a komponent,
   které spojují; slovo `vazba` ukáže všechny vazby. Velikost písmen ani
   diakritika nerozhoduje, více slov musí být přítomných všech.
3. U vnořené podsestavy zůstane vidět i její rodič, aby bylo jasné, kam díl patří.
4. **Enter** nebo **↓** vybere první nalezený řádek (komponentu nebo vazbu),
   **Esc** filtr zruší.
5. **Ctrl+A** (⌘+A) ve stromu s aktivním filtrem vybere **jen nalezené**
   komponenty. Typický postup: filtr `sroub` → Ctrl+A → **H** skryje všechny šrouby,
   **I** je izoluje, **T** zprůhlední. Bez filtru Ctrl+A vybere všechno jako dosud.

## Chování a meze

- Filtr zkracuje **jen strom**. Ve 3D zůstává vidět všechno; skrývání dílů ve 3D
  dál řídí zaškrtávátka, **H**, izolace a průhlednost (P7.13–P7.16). Model,
  výběr, historie Zpět ani soubor sestavy se filtrem nemění a filtr se neukládá.
- **Vybrané řádky zůstávají vždy vidět** – i když filtru neodpovídají nebo byly
  vybrané klikem ve 3D. Žádný příkaz tak nemůže změnit komponentu, kterou ve
  stromu nevidíš. Výběr rozsahu Shiftem skryté řádky přeskočí (Qt je nevybere).
- Filtr platí i po přepočtu a *Načíst díly znovu*; řádky se jen skrývají, nikdy
  nemažou (ochrana přístupnosti Cocoa na Macu). Otevřít a Nová sestava filtr
  vyprázdní.
- Text skupiny „Vazby (N)“ ukazuje dál celkový počet vazeb.
- Bez změny formátu, geometrie a závislostí.

## Ověření

- `tests/test_tree_filter.py` (6 nových testů sestavy, celkem 13): komponenty
  podle názvu i souboru, vazby nožiček podle komponenty, slovo `vazba`, Esc,
  stejné řádky stromu, beze změny sestavy, historie, viditelnosti, izolace a 3D;
  skutečné Ctrl+A s filtrem vybere jen 4 nožičky a **H** je skryje, bez filtru
  vybere všech 6; vybraná komponenta zůstává vidět; výběr ze 3D řádek odkryje;
  Enter vybere vazbu; Shift-rozsah přeskočí skryté řádky; filtr po
  *Načíst díly znovu*, vyprázdnění při Otevřít; ovladač self-testu.
- Sady okna sestavy, parametrů sestavy, hledání příkazů, oblíbených, výběru
  středu otáčení a hlavního okna: 387 + 101 testů prošlo.
- Self-test (`_self_test_assembly_tree_filter`): skutečné Ctrl+F, psaní (písmena
  I/T/H, která jsou zkratky okna, pole přijme), Enter, ponechání vybraného řádku,
  Ctrl+A bez filtru a s filtrem, Esc; sestava, historie, viditelnost a počet dílů
  ve 3D beze změny. Pod Xvfb **VÝSLEDEK: OK** (105 kontrol), řádek
  „✓ Filtr stromu komponent“. Na Windows a Macu ho spustí workflow nad hotovou dávkou.
- Snímek okna pod Xvfb: krabička s vazbami, filtr `nozicka` → „8 z 14 položek“,
  Ctrl+A vybralo 4 nožičky (zvýrazněné ve 3D), ve 3D dál všech 6 dílů.

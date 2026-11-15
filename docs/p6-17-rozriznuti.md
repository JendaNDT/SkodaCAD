# P6.17 – Rozříznutí dílu rovinou: návrh a provedení

*Datum 15. 11. 2026. Autor na pokyn „další rozšíření modelování“ nechal výběr na mně; vybral jsem
rozříznutí, protože krabičky na elektroniku a 3D tisk potřebují **základnu a víčko z jednoho
návrhu** a dosavadní prvky to neumí (vysunutí s řezem odebírá materiál podle skici, ne podle
roviny). Navazuje P6.18 (lem víčka).*

## K čemu to je

Navrhneš uzavřenou krabičku, rozříznuješ ji rovinou a máš základnu a víčko. Změna výšky řezu
(parametr) posune obě části. Pro tisk jde ponechat jen jednu část.

## Jak rozříznutí funguje (D1–D7)

- **D1 Nový prvek `split`**, formát **37** jen s ním. Díly bez něj zůstávají ve verzích 24–36.
- **D2 Zadání.** Rovina (`plane`, `offset` – jako u skici, i plocha dílu), `keep` =
  `below` / `above` / `both`, volitelně `gap` (jen s `both`). Hodnoty mohou být výrazy s parametry.
- **D3 Strany.** „Nad rovinou“ je strana, kam míří normála roviny (XY nahoru, XZ dozadu −Y,
  YZ doprava). Je to ověřeno testem, protože XZ bývá matoucí.
- **D4 Přesný řez.** Jádro `split` z build123d; objem obou částí se sečte a musí dát původní objem.
- **D5 Žádné tiché odříznutí.** Rovina mimo díl, na jeho povrchu nebo takto, že jedna strana je
  prázdná, se **odmítne** českou radou („Rovina díl neprotíná…“). Prvek nic nezahodí potichu.
- **D6 Dvě tělesa.** `both` dá dvě tělesa v jednom dílu; horní se odsune po normále o `gap`
  (bez mezery se jen dotýkají). Díl s více tělesy je dosavadní běžný stav (pole, import).
- **D7 Okno.** *Přidat prvek → Rozříznutí rovinou* (náhled, Potvrdit = jeden krok Zpět); výchozí
  rovina XY ve výšce 5 s oběma částmi a mezerou 5 nad blokem 40 × 30 × 10.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_split.py` (36) | objem částí podle vzorce (kvádr × výška řezu), `both` = původní objem, mezera posune horní část, strana normály u XZ, skořepina → základna + víčko, díl se dvěma tělesy, odmítnutí (rovina mimo / na povrchu / špatná mezera / mezera bez `both`), parametry, plocha dílu jako rovina, prvek po řezu, formát 37, ukázka |
| `tests/test_gui.py` (+1) | nabídka *Rozříznutí*: náhled se dvěma tělesy, potvrzení = jeden krok, Zpět |
| nativní self-test | „✓ Rozříznutí“ – základna 17 812,5 + víčko 14 687,5 mm³ podle vzorce |
| ukázka [`rozriznuta_krabicka.json`](../examples/rozriznuta_krabicka.json) | uzavřená krabička 80 × 50 × 25 s dutinou, řez ve V = 15, mezera M = 8 |

## Meze

- Řez je jen **rovinou**; šikmá plocha nebo řez křivkou není součástí této verze.
- Víčko se při `both` neotáčí a nepřikládá na desku – jen se odsune. Otočení pro tisk je na
  dalším kroku.
- Lem a drážka mezi základnou a víčkem jsou samostatný prvek (P6.18).
- Neověřeno na vlastním dílu autora.

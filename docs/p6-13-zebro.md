# P6.13/P6.14 – Žebro: návrh a provedení

*Datum 10. 11. 2026. Autor na pokyn „ok, pokračuj dalším rozšířením P6“ nechal výběr na mně;
vybral jsem **Žebro**, protože chybí v krabičkách, krytech a držácích a nejde ho udělat
jednoduše z dosavadních prvků (vysunutí skici nezná „až k tělesu“). Zbylí kandidáti
(proměnné zaoblení pro víc hran, přechod s kruhy) zůstávají otevřené.*

## K čemu je žebro

Tenká výztuha, která podepírá stěnu nebo dno: příčka uvnitř krabičky, úhlová výztuha v rohu mezi
stěnou a podlahou, žebro pod deskou. Vysunutí skici to umí jen s výškou „od oka“; žebro se
má **opřít o to, co už v dílu je**, ať se díl změní jakkoli.

## Jak žebro funguje (D1–D8)

- **D1 Nový prvek `rib`**, formát **36** jen s ním. Díly bez něj zůstávají ve verzích 24–35.
- **D2 Zadání.** Rovina skici (`plane`, `offset`, jako u skici a díry), **trasa** `points` =
  otevřená lomená čára `[[x, y], …]` (2–50 bodů), `thickness` a `side` (`left` / `right`).
  Hodnoty mohou být výrazy s parametry.
- **D3 Trasa je horní hrana žebra.** Žebro vede od trasy kolmo ke spojnici prvního a posledního
  bodu na zvolenou stranu a je **souměrné kolem roviny skici**. Trasa musí postupovat jedním
  směrem (bez vracení), jinak by se stěna křížila.
- **D4 Až k tělesu.** Z trasy se vytáhne dlouhá stěna, **těleso se od ní odečte** a ponechají se
  jen kusy, které leží na trase. Kusy za tělesem (pod dnem, za protější stěnou) zmizí. Žebro tak
  vždy končí na prvním materiálu – i když trasa začíná nebo končí uvnitř stěn krabičky.
- **D5 Žádné tiché přečnívání.** Kus, který by dosáhl až na konec vytažené stěny (trasa delší
  než díl, strana bez materiálu), se **odmítne** česky s radou; stejně trasa ležící celá v
  materiálu, nebo kus, který se tělesa nedotýká.
- **D6 Společná kontrola P1.** Přidání jde přes `ctx.apply` (kontrola objemů, jedno těleso).
  Prvek patří do `VOLUME_FEATURES` i `REPEATABLE_FEATURES`, takže ho jde opakovat polem
  (tři žebra v ukázce).
- **D7 Okno.** Nabídka *Přidat prvek → Žebro* (náhled, Potvrdit = jeden krok Zpět), formulář
  s rovinou, trasou, tloušťkou a stranou; výchozí trasa leží nad blokem, aby byl náhled hned
  vidět. Zápis starší aplikace nepoškodí: o prvku neví a verze 36 ji zastaví.
- **D8 Meze.** Trasa se neprodlužuje automaticky (žebro, které přečnívá, by viselo ve vzduchu),
  tloušťka je souměrná kolem roviny skici, rozšíření úkosem žebra ani zaoblení hran žebra
  není součástí této verze. Strana se volí podle směru trasy, ne šipkou ve 3D – náhled
  ukáže, jestli je správně.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_rib.py` (28) | objem žebra podle vzorce (deska: 40 × 10 × 3; lomená trasa: plocha pod trasou × tloušťka; úhlová výztuha: trojúhelník 20 × 16 × 3; příčka v krabičce se stěnami: 56 × 10 × 3), jedno těleso a platnost po spojení, souměrnost kolem roviny, posun roviny, zahození kusů za tělesem, odmítnutí (špatná strana, přečnívání, trasa v materiálu, vracející se trasa, nulová tloušťka, neznámý klíč), parametry, pole, popis ve stromu, formát 36, starší formát odmítnut, ukázka |
| `tests/test_gui.py` (+1) | nabídka *Žebro*: náhled s objemem podle vzorce, potvrzení = jeden krok, Zpět |
| příbuzné sady (schéma, sestavy, loft, NDT návrhy, regrese P0) | 216 úspěšných po úpravě očekávané verze formátu na 36 |
| ukázka [`zebro_krabicka.json`](../examples/zebro_krabicka.json) | objem 28 337,5 mm³ přesně podle vzorce, jedno těleso, platné |

Snímky okna (Linux Xvfb, 1440 × 900):
[hotové žebro](p6-14-snimky/zebro-hotove-karta-prvku.png),
[nové žebro – náhled](p6-14-snimky/zebro-nove-nahled.png).

## Meze

- Žebro se opírá o to, co už v dílu před ním je. Změní-li se díl tak, že trasa už na materiál
  nedosáhne, prvek skončí chybou (ne tichým přečnívajícím žebrem).
- Pole opakuje samotné těleso žebra posunuté, ne znovu výpočet „až k tělesu“. Kopie, která na
  materiál nedosedne (rozteč větší než díl), vznikne jako **samostatné těleso** – jako u každého
  jiného prvku v poli; ve stromu je to vidět na počtu těles („1 → 2“). Rozteč tedy volit tak, aby
  každé žebro leželo nad materiálem.
- Neověřeno na vlastním dílu autora.

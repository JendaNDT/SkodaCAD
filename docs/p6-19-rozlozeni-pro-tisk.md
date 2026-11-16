# P6.19 – Rozložení pro tisk u rozříznutí: návrh a provedení

*Datum 16. 11. 2026, pokyn autora „ok, pokračuj dalším rozšířením“ (výběr nechal na mně).
Navazuje na [P6.17](p6-17-rozriznuti.md) a [P6.18](p6-18-lem-a-drazka.md): po rozříznutí krabičky
a lemu zbývalo víčko ručně otočit a posunout. Rozložení pro tisk to udělá samo.*

## Co se změnilo

U rozříznutí s `keep: both` přibyla volba **Rozložení**:

- `stack` (výchozí, dosavadní chování) – víčko nad základnou, odsunuté o `gap` po normále roviny.
- `print` – víčko se **otočí o 180° kolem osy X roviny řezu** (otevřená strana nahoru, strop dole),
  položí se na **úroveň dna základny** a odsune **vedle ní** ve směru X roviny o `gap`; ve směru
  Y roviny se vystředí. Obě části leží na jedné desce, otevřenou stranou nahoru, jak se tisknou.

## Pravidla (R1–R6)

- **R1 Formát 38** jen s `arrange: print`; `stack` a starší zápisy zůstávají ve verzi 37.
- **R2 Jen `both`.** Rozložení pro tisk s jednou částí se odmítne.
- **R3 Osové roviny.** Rovina řezu musí být rovnoběžná s osami souřadnic (XY, XZ, YZ, plochy dílu
  kolmé k ose); šikmá rovina se odmítne českou radou.
- **R4 Beze změny objemu.** Otočení a posun jsou tuhý pohyb, součet objemů se neliší od řezu.
- **R5 Lem a drážka** se tvoří před otočením (z obrysu řezu), takže drážka ve víčku míří po
  otočení nahoru a lem základny také – ověřuje test bodů uvnitř a vně drážky.
- **R6 Okno.** Pole „Rozložení“ v kartě *Rozříznutí rovinou*; ukázka `krabicka_pro_tisk.json`.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_split.py` (58) | strop víčka na úrovni dna základny, výška víčka 10 po otočení, mezera ve směru X přesně `gap`, vystředění v Y, objem beze změny; drážka míří nahoru (bod v drážce prázdný, ve vnější stěně a pod dnem drážky materiál), lem základny nahoru; rovina XZ (normála −Y); odmítnutí (jedna část, šikmá rovina, špatná hodnota); formát 38 a starý zápis ve 37; ukázka podle vzorců |
| `tests/test_gui.py` (+1) | pole „Rozložení“ v kartě, volba „pro tisk“ se uloží do prvku |
| nativní self-test | „✓ Rozříznutí s lemem … a rozložení pro tisk (v38)“ |

Snímek okna: [základna a víčko rozložené pro tisk](p6-17-snimky/krabicka-pro-tisk.png).

## Meze

- Víčko se otáčí kolem osy X roviny řezu a klade se vedle základny ve směru X; jiný směr nebo
  více víček vedle sebe zatím není.
- Tvar se jen přeskupí; tiskové podpěry, orientaci kvůli převisům ani tolerance tiskárny řešit
  nebude.
- Neověřeno na vlastním dílu ani vytištěním.

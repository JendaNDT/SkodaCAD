# P7.81–P7.82 – krátký popis hran a náhled nového prvku bez pole Název (rám 3a)

*10. 11. 2026, pokyn autora „ok, pokračuj zbývajícími rozdíly okna“. Jen vzhled okna a čtení
modelu, formát (36) a výpočty se nemění.*

## Co se změnilo

- **P7.81 „Obvod horní plochy“.** Když vybrané hrany tvoří celý obvod jedné rovinné plochy
  (nebo všechny její hrany), karta prvku to řekne jednou větou jako rám 3a návrhu, místo
  výčtu hran významem. Platí pro horní, spodní, přední, zadní, levou a pravou plochu.
  Cokoli nejednoznačného (část obvodu, hrany dvou ploch, šikmá plocha) zůstává ve starém
  popisu – nikdy se nehádá. Čtení dělá `selectors.outline_name`, do okna ho dává
  `ModelSession.edge_outline_name`; popis hran v souboru, v AI ani v CLI se nemění.
- **P7.82 Náhled nového prvku bez pole Název.** Nový prvek se v náhledu jmenuje sám
  („Sražení 1“), pole *Název* se skryje (rám 3a ho nemá). Hodnota názvu zůstává v prvku;
  v prohlížecí a upravovací kartě existujícího prvku se pole *Název* zobrazuje dál.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_selectors_outline.py` (nový) | šest směrů kvádru, zaoblená deska (8 hran), plocha s dírou (všechny hrany × jen obvod), část obvodu / žádné hrany / hrany dvou ploch = bez zkráceného názvu |
| `tests/test_tool_cards.py` | v náhledu sražení obvodu horní plochy je popis „Obvod horní plochy“, pole *Název* skryté, hodnota názvu v prvku zůstala |
| cílené sady okna (`test_gui`, `test_model_card`, `test_sketch_mode`, `test_feature_preview`, `test_inspector_card`, `test_reference_interfaces`) | 230 úspěšných |
| nativní self-test (Xvfb) | VÝSLEDEK: OK |
| skript responzivity (5 velikostí × 7 rámů) | žádný nový nález, zůstává známých 7 posuvníků obsahu karty NDT |

Snímek: [rám 3a, návrh vlevo / aplikace vpravo](p7-81-snimky/3a-nahled-prvku-srovnani.png).

## Zbývající rozdíly proti návrhu (vědomé meze)

- Zapnutí řezu zaškrtávátkem (rám 3c má jiný ovládací prvek).
- Štítek měření bez zeleného podkladu (podklad pod popiskem shazuje GDI Generic, viz Známé pasti).
- Celé povinné upozornění UT zůstává doslova (R7), rám 3d má zkrácené s odkazem.
- Další tlačítka NDT průvodce; karta rámu 3d je delší než 900 px (posuvník).
- Systémová nabídka v okně na Linuxu a Windows (na Macu je v liště systému).
- Titulek dokumentu „nový model · ocel“ místo ukázkového textu návrhu.

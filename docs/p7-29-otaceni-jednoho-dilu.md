# P7.29 – osa a rotační rukojeti pro jeden díl

Datum: **2. 11. 2026**. Rozšíření stávajícího otáčení výběru na jedinou komponentu.

Při výběru jednoho dílu je dostupný panel **Otočení [°]**, při výběru více dílů
**Společné otočení [°]**. Oba používají stejné příkazy a nabízí světové osy XYZ,
volbu středu, osu válce, přímé hrany, kolmici k ploše i dvojici vrcholů. Dostupné
jsou výběr reference ve 3D, obrácení směru, číselné otočení i rotační rukojeti.

Otočení jednoho dílu používá stejné těžiště nebo zvolený bod pro číselný příkaz
i myš. Celý pohyb je jeden krok Zpět/Znovu. Ostatní díly se nepohybují. Pevné
komponenty, vnitřní díly podsestav, neúplný výsledek a nepovolený pohyb podle
vazeb jsou nadále blokovány. Pravidla parametrických výrazů zůstávají zachována.
Posouvací rukojeti se touto změnou nerozšiřují.

## Ověření

- Regrese v `tests/test_single_part_rotation.py`: všech sedm typů os číselným
  příkazem i přes potvrzení rukojeti, obrácení převzatého směru, skutečné vrcholy
  všech těles, platnost geometrie, neměnné okolí, jeden Zpět/Znovu, odmítnutí
  starého tahu při změně výběru a blokování pevných i vnořených komponent.
- Nativní kontrola v `gui/app.py` běží pro více dílů i jeden díl: skutečné tažení
  XYZ kolem těžiště i vlastního bodu, přerušení náhledu, kliknutí na všechny čtyři
  druhy geometrické osy, obrácení, Enter, tažení, Zpět/Znovu a zachování okolí.
- Tyto nativní scénáře jsou součástí `--self-test`, který kontroly pro Windows
  i macOS spouštějí ze staženého sestaveného balíčku před vydáním.

Místní protokoly a snímky jsou v `out/single-part-rotation/`. Výsledky úplné sady
na Windows a macOS jsou dohledatelné v kontrolách změny na GitHubu.

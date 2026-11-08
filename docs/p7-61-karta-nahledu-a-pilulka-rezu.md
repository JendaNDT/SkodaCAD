# P7.61 – karta náhledu prvku a pilulka řezu (rámy 3a, 3c)

*Navazuje na [P7.60](p7-60-karta-prvku-a-pilulka.md) (PR #133, `016cde7`, ověřeně vydané).
Pokračování na pokyn autora „ok, pokračuj“ (8. 11. 2026). Nové srovnání osmi rámů
[skriptem P7.58](p7-58-srovnani-ramu.py) ukázalo jako nejviditelnější rozdíly kartu náhledu
nového prvku (rám 3a) a pilulku u zapnutého řezu (rám 3c).*

## Co se změnilo

- **Hrany jako krátká hodnota.** Řádek „Hrany“ ukazuje jen popis výběru („Úsečky na horní
  ploše; hrany na horní ploše, poloměr 6“). Dlouhý návod, jak přidat další hrany, je
  v bublině. V prohlížecí kartě hotového prvku je pod popisem krátká věta „Změnit: Ctrl+klik
  na hrany ve 3D → pravé tlačítko“. V náhledu se schová, protože se během náhledu ve 3D
  nevybírá.
- **Patička náhledu jen Esc zahodí · Zrušit · Potvrdit.** Náhled se po každé změně hodnoty
  obnovuje sám. Tlačítko *Náhled* se ukáže jen po chybě (chybná hodnota nebo spadlý pomocný
  proces), aby šlo zkusit znovu.
- **Věta v modrém rámečku podle rámu 3a:** „Náhled je připravený: objem … mm³, počet těles 1.
  Hrany prvku svítí ve 3D modře, pohled můžeš dál otáčet. Uložení a export počkají na
  Potvrdit.“ Objem zůstal, protože je to užitečná kontrola.
- **Pilulka u řezu.** Se zapnutým řezem a bez jiného hlášení pilulka ukáže „Řez · Y = 0 mm |
  Na plochy řezu jde klikat a měřit“, jako v rámu 3c. Hlášení okna má dál přednost. Po
  vypnutí řezu se vrátí výběr nebo „F1: zkratky a ovládání myší“.
- Model, formát souborů (34), `ModelSession` ani výpočty se nemění.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_tool_cards.py` (+1) | skutečný náhled sražení obvodu horní plochy: krátký popis hran s velkým písmenem a návodem v bublině, věta o změně v náhledu skrytá, tlačítko *Náhled* skryté; chybná hodnota „1+“ tlačítko ukáže, oprava a klik ho schovají; po potvrzení prohlížecí karta větu o změně ukazuje; řez zapnutý → „Na plochy řezu jde klikat a měřit“, vypnutý → „F1: …“ |
| `tests/test_inspector_card.py`, `tests/test_gui.py` (upravené 3) | patička Esc zahodí · Zrušit · Potvrdit; popis hran se čte z nového krátkého popisku |
| testy okna, karet, pilulky, náhledů, skicáře, stromu, sestavy, vodítek, NDT průvodce (Linux) | 47 + 308 + 253 úspěšných, 0 chyb; `ruff check src tests` bez nálezů |
| self-test „Pravá karta“ a „Karty nástrojů“ (Linux Xvfb, skutečné 3D) | patička bez tlačítka *Náhled*, věta o modrých hranách, pilulka řezu „Na plochy řezu jde klikat a měřit“; celý self-test OK |

Srovnání s návrhem (Linux Xvfb, 1440 × 900):
[3a náhled prvku](p7-61-srovnani/3a-nahled-prvku-srovnani.png),
[3c řez](p7-61-srovnani/3c-rez-srovnani.png).

## Meze

- Návrh popisuje hrany slovy „Obvod horní plochy“. Aplikace ukazuje, jak jsou hrany
  uložené v modelu (úsečky a oblouky na horní ploše). Poznat „obvod“ by vyžadovalo
  porovnání s geometrií dílu, to je samostatný krok.
- Odkaz „Změnit výběrem ve 3D“ v náhledu není. Během náhledu je výběr ve 3D vypnutý;
  hrany se mění u hotového prvku přes pravé tlačítko.
- Pole Název zůstává i v náhledu nového prvku, aby šlo prvek pojmenovat hned.
- Zapnutí řezu je dál zaškrtávátko „zapnutý (klávesa R)“ (meze P7.54).
- Šířku a zalomení se skutečným písmem Windows a macOS ověří až self-test na GitHubu.

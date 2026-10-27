# P2.4 – ovládání přímých úprav

Autor zadal P2.4 dne 27. 10. 2026. Pracovní změna doplňuje výběr rovinné nebo válcové
plochy, zadání hodnoty, náhled počítaný na kopii a potvrzení nebo zrušení. Náhled mění
jen zobrazení, potvrzení zapíše jedinou změnu dokumentu. Ověřuje se také shoda dokumentu
se stavem při vytvoření náhledu. U existující úpravy lze převzít jinou plochu s novou
pojistkou původu; změna její hodnoty používá stejný náhled a původ zachovává.

Nástroj asistenta pracuje s plochou vybranou uživatelem a vyžaduje stejný dialog.
Přímé přidání, změna, přesun nebo smazání takových prvků obecnými nástroji asistenta
se odmítne; nahrazení modelu nesmí změnit samotné definice přímých úprav.

## Kontroly

- Místní kompletní sada na macOS: **1 619 testů prošlo**, po ní prošlo dalších 9
  cílených případů včetně nově doplněného testu průchodu AI. Ruff prošel. Během
  kompletního běhu byla doplněna typová anotace a rozšířeny testy; závěrečné cílené
  testy už běžely nad konečným stavem těchto souborů.
- Vlastní test aplikace spuštěné ze zdrojového prostředí na Macu skončil výsledkem OK.
- Regresní testy pokrývají analytické objemy kvádru a válcové díry, neplatnou hodnotu,
  druh plochy, zastaralý náhled, Zpět/Znovu, uložení a otevření, převzetí výběru,
  zrušení, potvrzení a návrh asistenta s náhradním klientem.
- Nativní okno na tomto Macu bylo spuštěno s reálným 3D prohlížečem; programově vybraná
  plocha a vykreslení platného náhledu byly zkontrolovány. Skutečná práce myší a celý
  průchod uživatelem ještě nebyly samostatně ověřeny.
- Výpočet náhledu nyní běží v hlavním vlákně. U složitého modelu proto může okno během
  přepočtu dočasně nereagovat. P2.5 musí prověřit reálnou odezvu a případně navrhnout
  výpočet mimo hlavní vlákno.
- Windows, stažené balíčky, živé volání externí AI ani GitHub Actions pro tuto změnu
  zatím nejsou ověřené. Formát modelu se nemění (verze 23); známá omezení P2.3 trvají.

## Ruční zkouška

1. Otevři model s objemovým tělesem, vyber rovinnou plochu a v nabídce pravého tlačítka
   zvol posunutí. Zobraz náhled a vyzkoušej Zrušit: model se nesmí změnit.
2. Zopakuj s Použít; ověř rozměr, jeden krok Zpět a Znovu, uložení a otevření.
3. Na válcové ploše díry nebo čepu vyzkoušej změnu průměru a nepřípustnou hodnotu.
4. Vyber existující přímou úpravu ve stromu; zkus změnu hodnoty i převzetí jiné plochy.
5. Vyber plochu a požádej asistenta o návrh. Bez potvrzení musí model zůstat beze změny.

P2.5 je samostatné přijetí; tato evidence sama nedokládá přijetí nebo sloučení do main.

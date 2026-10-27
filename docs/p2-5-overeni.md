# P2.5 – přejímka přímého modelování

Autor zadal P2.5 dne 27. 10. 2026. Tento zápis rozlišuje automatické ověření,
zkoušku agenta v okně a samostatné přijetí autorem. Neslibuje sloučení do main.

## Rozsah a nalezené mezery

Přejímka vychází z matice Q01–Q24 v `p2-1-navrh-rozsahu-primeho-modelovani.md` a
W01–W16 v `p2-2-navrh-zapisu-prime-upravy.md`. Existující mapování Q01–Q23 a W01–W16
je v `p2-3-overeni.md`; Q24 byl rozšířen o test skutečného zastarání dvou NDT studií,
přepočtu uložené tloušťky 20 → 25 mm a obnovení obojího příkazem Zpět. Nové testy
koule, toroidu z tažení a obecné plochy přechodu kontrolují jejich odmítnutí bez
změny dokumentu. W01 používá syntetické soubory se starými čísly verzí; sám o sobě
nepředstavuje sadu archivních modelů vzniklých v jednotlivých historických verzích.

Při ověření se našly a opravily tři nedostatky P2.4: zadání výrazu s parametry místo
pouze čísla; upozornění, že se označení závitu ani tabulková velikost původní díry
nemění; a chybová zpráva neplatného náhledu, která nově výslovně říká, že původní model
zůstal beze změny. Souborový formát zůstává 23.

## Ověření na tomto Macu

- Celá sada **1 629 testů prošla** na Apple Silicon, Python 3.12; Ruff prošel.
  Výsledek celé sady je uložen lokálně jako `out/p2-5-macos-final.xml`.
- Sestavenou aplikaci ze zkušebního ZIPu agent spustil v reálném 3D okně. Myší vybral
  rovinnou plochu příruby, v nabídce vyvolal posun, zadal parametrický výraz, náhled
  zrušil a ověřil, že Zpět zůstalo nedostupné. Při opakování náhled potvrdil; nový
  prvek se objevil ve stromu a Zpět/Znovu změnu vrátilo a obnovilo.
- Poté vybral válcovou stěnu otvoru, změnil průměr 62 → 64 mm a nový průměr ověřil
  měřením v okně. Neplatný návrh Ø300 byl odmítnut a potvrzení zůstalo nedostupné.
  Tato zkouška předcházela závěrečné úpravě textu chybové zprávy.
- Po závěrečné opravě byl vytvořen nový místní ZIP, rozbalen a jeho self-test skončil OK;
  podpis byl ověřen i po rozbalení a spustitelný soubor je pro Apple Silicon. Nejde
  o balíček stažený z GitHubu. Místní ZIP má SHA-256
  `cfc7d91a1b877bc03e5bcef71affa73896fe3f88e2af4162e49daa56f703d291`.
- Jeden náhled referenční příruby trval přibližně 0,05 s na tomto Macu; nejde o zátěžový
  test. Při složitých modelech výpočet na hlavním vlákně může zablokovat okno.

## Dosud neuzavřeno

- Kompletní testy a sestavení Windows a macOS pro finální verzi a self-test stažených
  artefaktů GitHub Actions.
- Samostatná ruční zkouška autora a jeho výslovné rozhodnutí o přijetí P2.
- Reálné externí volání AI; dosud ověřeny pouze nástroje a dialog s náhradním klientem.
- Známé zbytkové riziko W12 u kopií stejného pole, R03/R04 a odborná validace NDT-17.

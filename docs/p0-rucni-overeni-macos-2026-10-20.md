# P0 — ruční funkční ověření na Macu, 20. 10. 2026

Autor **JendaNDT** v navazujícím rozhovoru postupně potvrdil níže uvedené kroky.
Výsledky jsou záznamem jeho hlášení při vedeném ručním průchodu; nejde o automatické
pozorování všech úkonů ani o odborné přijetí NDT výpočtů.

## Identifikace sestavení a prostředí

- [PR #30](https://github.com/JendaNDT/SkodaCAD/pull/30), testovaná hlava
  `acfa97566fd945c6779bb38fc9e2a2a261465d58`, základ main `94c6e1d`.
- [macOS Actions, běh 133](https://github.com/JendaNDT/SkodaCAD/actions/runs/39462721048),
  [artefakt 12284292607](https://github.com/JendaNDT/SkodaCAD/actions/runs/39462721048/artifacts/12284292607).
  PR workflow sestavil syntetický merge `37b717d0e03c913b3996dcacd8462f5d6b884d72`;
  log posledního spuštění uvádí `sestavení 37b717d0e03c`, Python **3.13.15**.
- Místní zařízení: **Apple M4**, model **Mac16,12**; **macOS 27.0.1**, build **26A434**
  (zjištěno na sdíleném hostiteli při zápisu protokolu).
- SHA-256 spustitelného souboru běžící aplikace odpovídá souboru uvnitř artefaktu:
  `007208cb62af8ad69566e4d529da299009de3715caa2e9bea83465b2857b3423`.
- SHA-256 vnějšího ZIPu artefaktu:
  `5f54306f6b3d544084259bd50dc793512d0ca259836989dca4c80e4e960148b2`;
  odpovídá metadatům GitHubu. Vnitřní `SkodaCAD-macos.zip` má SHA-256
  `c0c37e0d5be689ae45c3000404087575936967ed0d90620c80699783f557d69f`.

## Potvrzené kroky

| Krok | Požadované chování | Hlášení autora |
|---|---|---|
| Spuštění | Rozbalená aplikace se otevře na skutečném Macu. | „otevřelo se to“ |
| Editace a historie | Změna jednoho rozměru přepočítá model; Zpět obnoví původní stav a Znovu změnu vrátí. | „ok, funguje to“ |
| Uložení kopie | Uložit jako do nového souboru; po zavření a otevření zůstane rozměr i tvar. | „ano“ |
| Chybný výraz | `1+` je odmítnuto, aplikace zůstane spuštěná, původní model se zachová; lze vrátit platnou hodnotu. | „ok, to také funguje“ |
| Chybná geometrie | Příruba, sražení `s=50`: chyba ve stromu; Zpět obnoví platný model. | „ok, to také funguje“ |
| 3D a řez | Otáčení, přiblížení, výběr horní plochy, měření, posun a vypnutí řezu; rozměry se nezmění. | „ok, to také funguje“ |
| Zastarání NDT | NDT 1 – Deska: změna `t=20` na `30` označí studii jako zastaralou; Zpět vrátí tloušťku. | „ok, to také funguje“ |
| Náhled konstrukčního návrhu | NDT 10: odhad, výpočet a Zastavit; náhled varianty bez změny originálu, stěna 15 mm. | „ok, to také funguje“ |
| Použití varianty | Zrušení potvrzení nemění model; potvrzené použití jej upraví; jediný krok Zpět obnoví původní parametry. | „ok, to také funguje“ |
| Poškozený soubor | Otevření záměrně neúplného JSON `{"version":` zobrazí srozumitelnou chybu a zachová rozpracovaný model. | „jj v pořádku“ |
| Výstupy a návrat | Export auditu a návrhu do nové složky, otevření dostupných HTML/CSV/PDF, kontrola čitelnosti, hodnot, upozornění a studií; ukončení, nové spuštění a otevření uložené kopie zachová zadání. | „ok, to také funguje“ |

U první editace nebyly v dialogu předepsány konkrétní hodnoty ani přesný ukázkový
model; nelze tedy zpětně tvrdit měření příruby `t=18 → 36`. U exportů autor potvrdil
celý zadaný postup, ale jednotlivé soubory, čísla a formáty nebyly přiloženy.

## Co tento průchod samostatně nedokládá

- Odmítnutí neexistujícího názvu parametru (zkoušen byl syntakticky chybný výraz `1+`).
- Samostatný pokus použít nevyhovující variantu: byl požadován podmíněně, pokud se
  taková varianta v seznamu vyskytla; její přítomnost autor výslovně nepotvrdil.
- Všechny body širšího [macOS seznamu](ndt/08-navrh-macos.md#5-ruční-test-na-macbooku-podmínky-dokončení-z-05-podpora-macosmd):
  zejména přesnost výběru při různých měřítkách Retiny, Shift+tažení na trackpadu,
  konkrétní ovladač GPU, mapa tloušťky, export STEP a porovnání stejného modelu s Windows.
- Ukončení všech pomocných procesů: uživatel potvrdil ukončení a nové spuštění aplikace;
  mezi nimi neproběhlo samostatné měření procesů.
- Ruční zkouška Windows, číselná a fyzická validace metod NDT, původ referenčních hodnot
  a odborné přijetí podle [NDT-17](roadmapa-vyvoje.md#paralelní-ndt-17--validace-a-meze-použití).

## Nález při stažení

Chrome nejprve zablokoval nový macOS ZIP jako nebezpečný. Přiložené snímky obsahovaly
obecný verdikt bez označení konkrétní hrozby. Autor následně povolil jednotlivé stažení
a aplikaci spustil. Příčina verdiktu není objasněná; tento záznam nepotvrzuje malware
ani falešný poplach. Kontrolní součty dokládají totožnost souborů, nikoli výsledek
antivirové kontroly. Ad-hoc podpis a chybějící notarizace jsou stávající omezení distribuce.

## Závěr

Autor potvrdil uvedený funkční průchod P0 na konkrétním Macu. Produkční nálezy
[auditu P0](p0-audit-a-overeni.md#2-registr-rizik-a-omezení) zůstávají otevřené.
Širší přijetí macOS a NDT-17 pokračují v uvedeném rozsahu. Tento protokol není
souhlasem se sloučením PR, zahájením P1/P2 ani změnou formátu modelu.

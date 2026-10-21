# P1.2A — ruční ověření autora

Datum potvrzení: 21. 10. 2026 (Europe/Prague).
Předaná implementace: [PR #33](https://github.com/JendaNDT/SkodaCAD/pull/33),
hlava `8852a6b6a974b9f561865e079d12f5f50c9fd02e`.
macOS balíček: běh 141, sestavení `2d25a8adc91576775eeecee1e390ffb9167db871`.
Prostředí: **macOS 27.0.1, arm64, Apple M4**. Systém byl ověřen místně;
aplikační log od startu 21. 10. 2026 v 16:13:16 uvádí sestavení `2d25a8adc915`
a Python 3.13.15. Běžící aplikace má dva pomocné procesy pro přepočet.
Tyto technické údaje pocházejí z místní kontroly, nikoli z tvrzení, že je autor
samostatně opisoval z dialogu. Git strom uvedeného sestavení byl již ověřen jako
shodný s hlavou PR. Místní vývojové testy s Pythonem 3.12.14 jsou samostatná evidence.

## Potvrzené skutečnosti

Autor odpověděl **„všechno sedí“** na tuto konkrétní kontrolu souboru
`p1-2a-dve-telesa.json` v novém ŠkodaCADu:

- ve 3D jsou dva oddělené válce;
- ve stromu je zelené „Počet těles: 0 → 2.“;
- ve vlastnostech je „Počet těles: 2“.

Tím je potvrzené zobrazení obou částí i obě informace o počtu těles.
Na následnou kontrolu objemu přibližně **1 571 mm³** autor odpověděl
**„to také sedí“**. První zkouška dvou válců je tím potvrzená včetně objemu.

Autor následně odpověděl **„to také sedí“** na kontrolu souboru
`p1-2a-zmeny-poctu.json`:

- ve stromu jsou postupně změny **0→1, 1→2, 2→1, 1→1**;
- ve 3D zůstává jedno těleso se sraženými svislými rohy;
- konečný objem je **23 680 mm³**.

Druhá zkouška je tím potvrzená ve všech třech požadovaných bodech.

Autor odpověděl **„to také sedí“** také na kontrolu souboru
`p1-2a-tri-trubky.json`:

- ve 3D jsou tři celé, oddělené trubky;
- u pole je zelené „Počet těles: 1 → 3.“;
- ve vlastnostech je „Počet těles: 3“.

Třetí zkouška je tím potvrzená ve všech třech požadovaných bodech.

Autor odpověděl **„to také sedí“** na chybový stav souboru
`p1-2a-pridani-bez-ucinku.json`:

- přídavek je odmítnut s chybou „přidání nepřidalo rozlišitelný materiál“;
- následující prvek je přeskočený;
- zůstává původní kvádr s objemem **24 000 mm³**.

Autor následně odpověděl **„to také sedí“** na opravu a Zpět/Znovu:

- po změně vysunutí prvku `chyba` na **60 mm** je model zelený a konečný objem
  **24 380 mm³**;
- **Zpět** obnoví chybu a objem **24 000 mm³**;
- **Znovu** obnoví platný model s objemem **24 380 mm³**.

Čtvrtá zkouška je tím potvrzená včetně opravy a Zpět/Znovu.

Autor odpověděl **„to také sedí“** na chybový stav souboru
`p1-2a-skorepina-bez-otevreni.json`:

- chyba oznamuje, že skořepina potřebuje alespoň jednu otevřenou plochu;
- následující prvek `dalsi_prvek` je přeskočený;
- zůstává plný kvádr s objemem **30 000 mm³**.

Autor následně odpověděl **„to také sedí“** na opravu skořepiny a Zpět/Znovu:

- po odebrání posledního prvku `dalsi_prvek` a zaškrtnutí horní otevřené plochy
  u skořepiny `chyba` vznikne zelená dutá krabička se dnem, objem **8 472 mm³**;
- **Zpět** obnoví chybu skořepiny a plný kvádr **30 000 mm³**;
- **Znovu** obnoví krabičku **8 472 mm³**.

Pátá zkouška je tím potvrzená včetně opravy a Zpět/Znovu.

Autor odpověděl **„to také sedí“** na kontrolu příruby
`p1-2a-priruba.json`:

- změna parametru `t` z **18** na **20** dává tloušťku **20 mm**, jedno těleso
  a všechny prvky zelené;
- **Zpět** vrátí tloušťku **18 mm**, **Znovu** tloušťku **20 mm**;
- po „Uložit jako…“ pod jiným názvem a opětovném otevření má kopie stále
  **20 mm** a jedno těleso;
- znovu otevřený původní soubor má stále **18 mm**.

Šestá zkouška je tím potvrzená včetně uložení kopie a zachování originálu.

Autor odpověděl **„všechno sedí“** na poslední zkoušku obou souborů
`p1-2a-trubky-chybne-zaobleni.json` a `p1-2a-trubky-chybne-srazeni.json`:

- **zaoblení 50 mm:** prvek `chyba` je červený s vysvětlením, `dalsi_prvek`
  přeskočený; zachované jsou tři celé trubky a počet těles **3**;
- **sražení 50 mm:** stejná kontrola chyby, přeskočení dalšího prvku a zachování
  tří celých trubek s počtem těles **3**;
- u obou variant změna poloměru/velikosti na **0.5 mm** obnoví zelené prvky
  a počet těles **3**;
- u obou variant **Zpět** obnoví chybu a přeskočený poslední prvek,
  **Znovu** obnoví zelený stav.

Sedmá zkouška je tím potvrzená pro zaoblení i sražení včetně opravy a Zpět/Znovu.

## Výsledek vedené sady

| Kontrola | Stav |
|---|---|
| Dva válce, počet a objem | Potvrzeno |
| Změny počtu těles a konečný objem | Potvrzeno |
| Tři celé trubky a počet těles | Potvrzeno |
| Přídavek bez účinku, oprava a Zpět/Znovu | Potvrzeno |
| Skořepina bez otevření, oprava a Zpět/Znovu | Potvrzeno |
| Příruba, změna rozměru, Zpět/Znovu a uložení kopie | Potvrzeno |
| Chybné zaoblení i sražení, oprava a Zpět/Znovu | Potvrzeno |

Všech **sedm vedených ručních zkoušek na autorově Macu je potvrzených**.
Protokol zaznamenává konkrétní výše uvedené kontroly; netvrdí samostatné ruční
ověření každého mezistavu ani všech automatických případů V1–V14.
Shoda CLI/offline souhrnu AI a skutečný přepočet pomocným procesem jsou technická
ověření vedená samostatně v [přehledu ověření](p1-2a-overeni.md), nikoli další
nevyřčená potvrzení autora. Ve vedené zkoušce byly změny a historie provedeny
v aplikaci, jejíž přepočet používá pomocné procesy.

Ruční průchod na Windows ani odborná NDT-17 tímto nejsou potvrzené.
Po dokončení zkoušek autor na konkrétní žádost o schválení sloučení PR #33
odpověděl **„ok, schvaluji“**. Tento samostatný souhlas byl proveden:
[PR #33](https://github.com/JendaNDT/SkodaCAD/pull/33) je sloučené do `main`
21. 10. 2026 v 17:55:22 UTC jako commit
[`edf9b8e`](https://github.com/JendaNDT/SkodaCAD/commit/edf9b8ec74b7bdbfa98101796564f22624d45532).
Před sloučením byly znovu ověřené obě úspěšné cílové kontroly včetně kontroly
stažených balíčků. Obsah `main` po sloučení je přesně shodný s otestovanou hlavou PR.
Souhlas se sloučením nezahrnuje implementaci P1.2B ani další neschválené etapy.

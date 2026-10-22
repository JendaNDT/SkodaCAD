# P1.2B — vedená ruční zkouška

Použij **balíček konečné hlavy implementačního PR**, nikoli starší Releases.
Odkaz na konkrétní běh a balíček bude v PR. Ke zkoušce jsou připravené soubory
`p1-2b-zkusebni-modely.zip`; originály ponech, změny ukládej pod novým jménem.
Není potřeba upravovat JSON. Automatické ověření je v [evidenci](p1-2b-overeni.md).

Do protokolu zapiš datum, OS, zařízení a identifikaci sestavení z aplikace.
Každý bod potvrď podle skutečnosti; automatický test ani tento návod nenahrazuje
potvrzení autora. Dosud **čeká na ruční přijetí**. Mac nenahrazuje ruční Windows test.

## 1. Pozdní chyba pole

Otevři `p1-2b-pole-pozdejsi-chyba.json` přes **Soubor → Otevřít**.
Má být vidět deska se dvěma slepými otvory, **1 těleso**, objem přibližně
**79 874 mm³**. `Pole dvou otvorů` hlásí chybu a `Kontrola po chybě` je přeskočená.
Uprostřed desky nemá vzniknout částečná třetí díra.

Vyber `Pole dvou otvorů`. Vpravo změň **Rozteč [mm]** z `20` na `-20` a potvrď Enter.
Výsledek má mít čtyři otvory, **1 těleso**, přibližně **79 749 mm³**; všechny prvky
mají být úspěšné. **Zpět** obnoví chybu a dvě díry; **Znovu** obnoví čtyři díry.
Přes **Uložit jako** vytvoř kopii, znovu ji otevři a ověř čtyři díry i úspěšný strom.
Původní soubor po novém otevření musí stále obsahovat chybu a dvě díry.

## 2. Pozdní chyba zrcadlení

Otevři `p1-2b-zrcadleni-pozdejsi-chyba.json`. Očekávej původní dvě díry, **1 těleso**,
**79 874 mm³**, chybu `Zrcadlení dvou otvorů` a přeskočený následující prvek.
Žádná částečná kopie nesmí zůstat ve výsledku.

Vyber chybný prvek a změň **Posun roviny [mm]** z `20` na `0`, Enter.
Očekávej čtyři díry, **79 749 mm³**, **1 těleso** a úspěch všech prvků.
Vyzkoušej **Zpět/Znovu**, ulož a znovu otevři kopii; původní soubor se nezmění.

## 3. Příruba a uložená kopie

Otevři `p1-2b-priruba.json`. Parametr **t** změň z `18` na `20`.
Příruba má zesílit, zůstat jedním tělesem a všechny prvky mají projít.
**Zpět** vrátí tloušťku 18; **Znovu** tloušťku 20. Ulož přes **Uložit jako**,
znovu otevři kopii a ověř tloušťku 20. Originál musí mít stále t=18.

## 4. Tři trubky a chyba úpravy hrany

Otevři `p1-2b-tri-trubky.json`: mají být vidět všechny **3 trubky**, bez chyby,
objem přibližně **96 496 mm³**. Zprávy mají odpovídat souboru `p1-2b-zpravy.txt`.

Otevři `p1-2b-trubky-chybne-zaobleni.json`: `Zkouška chyby` má chybu a kontrolní skica
je přeskočená, přesto zůstávají všechny **3 trubky** v původním tvaru a objemu.
Vyber chybný prvek a změň **Poloměr [mm]** z `50` na `0.5`, Enter.
Zaoblení má projít a počet zůstane **3**. **Zpět/Znovu** musí vracet chybu/opravu.
Srovnej znění zpráv s přiloženým souhrnem; počet tří těles je platný výsledek.

## 5. Zastavení výpočtu

Otevři `p1-2b-zastavit.json`. Deska s jednoduchou dírou M5 má být úspěšná,
**1 těleso**, přibližně **11 861 mm³**. Vyber `Zkouška zastavení – díra M5`
a zaškrtni **Vymodelovat závit (3D tisk)**. Během přepočtu stiskni **Zastavit**.
Má zůstat předchozí deska s jednoduchou dírou, zaškrtnutí se vrátí a zpráva oznámí
zastavení přepočtu. Nesmí se dodatečně ukázat opuštěný nedokončený výsledek.
Jestli výpočet doběhne dříve, než stihneš Zastavit, není to důkaz zrušení;
zkoušku zopakuj. Po zastavení ověř, že jde dál pracovat a uložit kopii.

## Protokol

| Položka | Skutečný výsledek |
|---|---|
| Datum / OS / zařízení / sestavení | Čeká na autora |
| Pole: chyba, oprava, Zpět/Znovu, uložená kopie, originál | Čeká na autora |
| Zrcadlení: chyba, oprava, Zpět/Znovu, uložená kopie, originál | Čeká na autora |
| Příruba: rozměr, historie a kopie | Čeká na autora |
| Tři trubky: úspěch, chyba/oprava zaoblení a zprávy | Čeká na autora |
| Zastavit a další práce po zrušení | Čeká na autora |

P1.2B tímto dokumentem není prohlášeno za dokončené. Po přijetí je nutný
**samostatný souhlas autora se sloučením implementačního PR**.

# P7.22 – volitelný střed otáčení

Datum: **2. 11. 2026**. Navazuje na P7.20–P7.21. Formát a závislosti beze změny.

## Ovládání

Po výběru více komponent nabízí panel **Společné otočení [°]** volbu **Střed otáčení**:

- **Střed výběru**: dosavadní geometrické těžiště, vážené objemem všech vybraných
  kopií včetně skrytých a celých podsestav, bez vlivu materiálu.
- **Počátek sestavy**: bod (0, 0, 0) celé sestavy.
- **Vlastní bod**: souřadnice X/Y/Z v mm v osách celé sestavy. Číslo, desetinná čárka
  nebo výraz s parametry sestavy. Výchozí rozepsaný bod je (0, 0, 0).

**Převzít střed výběru** vyplní do vlastního bodu aktuální těžiště všech vybraných
větví, i skrytých. Používá plnou přesnost; popisek vyhodnoceného bodu je zaokrouhlený
na tři desetinná místa. Převzetí je snímek, při dalších výběrech už bod samo neposouvá.

Tlačítko **Otočit vybrané**, Enter v úhlu či souřadnici a rotační rukojeti používají
tentýž vyhodnocený bod. Prstence se kreslí kolem něj. Změna pole, volby nebo převzetí
bodu zruší rozpracovaný tah. Chybné pole zobrazí důvod v panelu a vypne otočení
a prstence, ale pole a převzetí středu zůstanou dostupné k opravě.

Volba i rozepsané hodnoty zůstávají v otevřeném okně přes změnu výběru, viditelnosti,
průhlednosti a Zpět/Znovu. Jsou nastavením ovládání: samy nepřepočítávají model,
neoznačují ho jako změněný, nepřidávají historii ani neruší Znovu. Do souboru sestavy
se neukládají; nové okno začíná režimem Střed výběru. Výběr bodu kliknutím zatím není.

## Výpočet a bezpečné přijetí

`AssemblySession.rotation_center(ids, center=None)` vrací ověřený snímek bodu;
vlastní souřadnice vyhodnotí v parametrech celé sestavy. Vyžaduje tři konečná reálná
čísla, odmítá neznámé parametry, chyby výrazů i logické hodnoty. Chyba označí osu.
`turn_many_around(..., center=...)` používá stejnou mapu `p'=c+Q(p−c)`, `R'=QR` jako
P7.20. Bez volitelného argumentu je chování původní. Neplatný vlastní bod se odmítne
i při 0/360°, bez zrušení Znovu. Platné celé otáčky nepřidávají historii.

Výrazy středu se při příkazu změní na číselný snímek, nikoli na trvalou vazbu.
Původní výrazy poloh zůstávají parametrické; pozdější změna jejich parametrů se dál
uplatňuje v otočeném směru kolem použitého bodu. Změna parametru středu už vykonané
otočení zpětně neposune. Natočení zadané výrazem nadále podporuje jen osu Z.

Pevnost, omezení vnitřních cest podsestav, vazby, změny zdrojů a úplnost výsledku se
ověřují stejně jako v P7.20. Přijetí je atomické a jeden krok Zpět/Znovu. Nová revize
středu v rotačním tokenu odmítne staré puštění i po změně bodu tam a zpět. Kamera,
viditelnost, izolace, průhlednost a rozepsané ostatní hodnoty zůstávají zachované.

## Ověření

Regrese porovnávají skutečné vrcholy a těžiště proti nezávislé Rodriguesově matici
kolem počátku i posunutého bodu v osách XYZ. Kontrolují objem, platnost, okolí,
zdroje a jediný krok Zpět/Znovu. Dále výrazy a jejich snímek, neplatné souřadnice
včetně celé otáčky, pevnost, vazby, změnu zdroje, uložení/otevření a STEP.

Regrese okna ověřují společný bod pro tlačítko i rukojeti, skutečné potvrzení Enterem,
desetinnou čárku, skryté díly, preference a zachování Znovu, přesné převzetí těžiště,
opravitelné neplatné pole a odmítnutí zastaralého tahu po změně středu.

Nativní self-test na skutečném OCCT prohlížeči táhne XYZ kolem vlastního bodu,
ověřuje AIS náhled, pevný bod, potvrzení i přerušení změnou bodu/volby/chybným polem.
Také číselně otočí dva díly kolem počátku sestavy Enterem a ověří jejich těžiště.
Běží i ve stažených balíčcích obou systémů. Místní protokoly a snímky:
`out/p7-custom-rotation-center/`; úplné výsledky před sloučením patří do PR.

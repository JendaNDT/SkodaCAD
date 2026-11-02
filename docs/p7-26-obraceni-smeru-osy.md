# P7.26 – obrácení směru převzaté osy

Datum: **2. 11. 2026**. Navazuje na P7.24/25. Jádro otáčení, formát a závislosti beze změny.

Navazující [P7.27](p7-27-kolmice-k-plose.md) přidává i obrácení kolmice k rovinné ploše.

## Ovládání

Vyber více komponent. V panelu **Společné otočení [°]** zvol **Válcová plocha** nebo
**Přímá hrana**, tlačítkem **Vybrat osu ve 3D** převezmi referenci a stiskni
**Obrátit směr osy**. Bod osy se nezmění, směr se přesně neguje. Při zapnutých
rotačních rukojetích se obrátí šipka. Stejný kladný číselný úhel nebo kladný tah pak
otáčí opačně kolem téže přímky. Záporný úhel působí opačně vůči aktuální šipce.

Samotné obrácení nepohybuje díly, nemění model, Zpět/Znovu ani rozepsané hodnoty
úhlu, posunu, vlastního středu či krok. Druhý stisk vrátí původní směr. Nastavení je
preference otevřeného okna, ne položka modelu. Hrana i válec mají vlastní snímek
včetně směru; přepnutí jej zachová. Nové převzetí přepíše snímek směrem nové geometrie.
XYZ zůstávají obvyklé kladné světové osy a tlačítko pro ně není zobrazené.

Bez převzaté osy je tlačítko vypnuté. Stejně jako výběr osy vyžaduje více způsobilých
komponent a dokončenou sestavu. Omezení natočení zadaného výrazem se nemění: přesné
±Z jej zachovají, šikmý směr vyžaduje číselné natočení. Tlačítko lze použít i při
tomto omezení. Osa zůstává pevným snímkem; po změně referenčního dílu ji převezmi znovu.

## Životní cyklus a ověření

`_reverse_rotation_axis` zachová bod a neguje trojici směru pouze aktuálního druhu.
`_rotation_center_changed` zruší rozpracovaný výběr reference a rotační náhled,
zvýší revizi tokenu a obnoví prstenec i panel. Starý požadavek na výběr nebo potvrzení
tahu nelze přijmout ani po dvojím obrácení zpět. Staré dokončení výběru nesmí zrušit
nově spuštěný požadavek. Otočení dál používá společné `turn_many_around` a jeho
atomickou kontrolu výsledku; tlačítko samotné tuto modelovou operaci nevolá.

Regrese ověřují oba druhy, přesné zachování kotvy, výběru a podkladů vazeb,
rozepsaných hodnot, viditelnosti, 35/85 % průhlednosti, identity výsledku, historie
a Znovu. Skutečné vrcholy otočených těles se porovnávají s nezávislou rotací:
kladný úhel kolem obrácené osy musí odpovídat zápornému kolem původní. Kontroluje
se platnost těles, jeden Zpět/Znovu, oddělené směry, opětovné převzetí, staré
požadavky, zakázané ovládání a výrazy natočení.

Nativní self-test na obou systémech vybere šikmou válcovou plochu a přímý šev jiného
dílu. Třikrát skutečně stiskne tlačítko, zachová bod i výběr AIS, kameru, pole a historii
a potom ověří Enter 90° i tažení 30° kolem obrácené osy, těžiště, platnost těles
a jeden Zpět/Znovu. Evidence je v `out/p7-reverse-rotation-axis/`; úplné výsledky patří do PR.

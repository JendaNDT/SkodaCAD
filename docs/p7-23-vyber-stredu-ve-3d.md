# P7.23 – výběr středu kliknutím ve 3D

Datum: **2. 11. 2026**. Navazuje na P7.22. Formát, závislosti a modelovací jádro beze změny.

## Ovládání

Při hromadném výběru zvol v panelu **Společné otočení [°]** způsob výběru a stiskni
**Vybrat ve 3D**. K dispozici jsou:

- **Střed kružnice** – klik na kruhovou hranu nebo kruhový oblouk. Přesný střed jeho
  nosné kružnice, nikoli místo kliknutí. Přímky, elipsy a nekruhové křivky se odmítnou.
  U křížení s jinou hranou klikni na jinou část oblouku.
- **Vrchol** – klik na topologický vrchol dílu, přesné souřadnice ve světě sestavy.
- **Bod na ploše** – bod na skutečné ploše pod kurzorem. Výpočet zjemní zásah sítě
  přesným průsečíkem paprsku pohledu s BRep plochou.

Lze vybrat geometrii kteréhokoli zobrazeného dílu, včetně nevybraného nebo vnitřního
dílu podsestavy. Skryté větve se neodkrývají a nejsou zdrojem výběru. Kliknutí zůstává
oddělené od výběru komponent pro otočení: ten i rozpracované podklady vazeb se zachovají.

Po úspěchu se nastaví **Vlastní bod** v plné přesnosti a režim skončí. Stejný bod
použije číselné otočení i rotační prstence; následný pohyb má dosavadní jeden krok
Zpět/Znovu. Samotné převzetí nemění model, díly, soubory, kameru, materiál ani historii
a nemaže Znovu. Bod je snímek a preference okna, nikoli nová parametrická vazba.

Prázdný klik či nevhodná geometrie zobrazí pokyn a dál čeká. Levým tažením lze
otáčet kameru, Shift+levým nebo pravým tažením ji posouvat a kolečkem přibližovat.
Tyto pohyby bod nepotvrdí. Rukojeti jsou během výběru skryté, aby klik neuchopil osu.

**Esc**, pravý klik bez tahu nebo **Zrušit výběr** skončí bez změny předchozího bodu.
Změna středu/druhu, komponent, geometrie, viditelnosti či průhlednosti, resize,
skrytí okna nebo přepnutí do jiné aplikace výběr také zruší. Esc zruší nejprve režim,
nikoli výběr dílů. Fokus mezi ovládacími prvky stejného okna sám režim neruší.

## Přesnost a přijetí

Prohlížeč uloží aktivní výběrové režimy aktuálního AIS a zapne pouze příslušný typ
geometrie. Nevolá `SelectDetected` ani nemění `picked_point`; původní vlastníci
výběru ploch zůstanou zachovaní. Po dokončení či zrušení se režimy, kurzor a rukojeti
obnoví. Každá prezentace a detekce jsou vztažené ke skutečnému poměru pixelů OCCT/Qt.

Kružnici a vrchol čte přímo z již umístěného tvaru. U plochy protne paprsek přesným
intersektorem s tolerancí 1e-7 mm a zvolí průsečík nejbližší původnímu zásahu AIS.
Pokud bezpečný zásah neexistuje, bod se nepřevezme. Výběr nepoužívá pořadí hran/ploch.

Controller přijme jen právě aktivní požadavek: shodný model, výběr, výsledek, revize
středu, viditelné větve, způsob a pořadové číslo výběru. Ověří i příslušnost tvaru
aktuální viditelné geometrii a konečné souřadnice přes `AssemblySession.rotation_center`.
Zrušený nebo dřívější požadavek se nepřijme ani po opětovném zapnutí stejného režimu.
Pole a volbu nastaví se zablokovanými signály a obnoví střed pouze jednou, bez `_run`.

## Ověření

Regrese ověřují umístěné kružnice XYZ, oblouk a vrchol, přesný průsečík válce mimo
trojúhelníkovou síť, nevhodnou hranu a nulový paprsek. Interakce v poměrech 1/1,25/2
kontrolují jediný signál, nezměněný běžný výběr, obnovené režimy, prázdný klik,
navigaci i zrušení. Testy okna zahrnují nevybranou referenci, podsestavy, skutečnou
následnou geometrii otočení, Zpět/Znovu, viditelnost, chybné a zastaralé návrhy.

Nativní self-test kliká skutečnou myší na střed kružnice, vrchol a plochu jiné nožičky.
Kontroluje existující AIS výběr, podklady vazby, výběr komponent, kameru, 35/85 %
průhlednost, rozepsaná pole a historii. Ověří Esc/tlačítko/změnu druhu, prázdný klik
i následné otočení se stejným bodem a jedním Zpět/Znovu. Běží i ve stažených balíčcích
obou systémů. Místní evidence: `out/p7-pick-rotation-center/`; úplné výsledky patří do PR.

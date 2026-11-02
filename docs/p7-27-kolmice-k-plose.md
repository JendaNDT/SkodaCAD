# P7.27 – osa kolmo k rovinné ploše

Datum: **2. 11. 2026**. Navazuje na P7.24–26. Jádro otáčení, formát a závislosti beze změny.

## Ovládání a význam osy

Vyber více komponent. V panelu **Společné otočení [°]** zvol **Kolmo k ploše**,
stiskni **Vybrat osu ve 3D** a klikni na rovinnou stěnu viditelného dílu. Může být
nevybraný, pevný nebo uvnitř podsestavy. Osa povede **přesným místem kliknutí**,
kolmo k této ploše. Jiným místem na téže ploše lze určit jinou rovnoběžnou osu.
Není to automaticky kolmice vedená těžištěm plochy, dílu nebo výběru.

Šipka a popisek **Kolmice k ploše** při zapnutých rotačních rukojetích ukazují kladný
směr. Pro uzavřené správně orientované těleso míří z materiálu. **Obrátit směr osy**
směr neguje bez pohybu dílů nebo změny historie. Číselný úhel i prstenec používají
stejný bod a směr, dosavadní krok tažení a jeden Zpět/Znovu pro potvrzený pohyb.

Přijímá se pouze přesná analytická rovina. Válec, kužel, koule ani jiná zakřivená
či spline plocha se nenahrazují tečnou rovinou. Klik mimo skutečnou plochu či do
jejího otvoru nevytvoří osu. Nevhodný klik dál čeká, Esc, pravý klik a Zrušit výběr
ponechají předchozí snímek. Výběr otáčených komponent, ploch a podkladů vazeb se nemění.

Kolmice, osa válce a osa hrany mají samostatné pevné snímky otevřeného okna, včetně
obráceného směru. Přepnutí je nezamění, nové převzetí nahradí jen aktuální druh.
Neukládají se do modelu a nejsou asociativní: po změně reference je vyber znovu.
XYZ obnoví dosavadní nastavení středu a jeho rozepsané hodnoty. Omezení natočení
zadaného výrazem zůstává stejné: přesné ±Z jej zachovají, ostatní směry vyžadují
číselné natočení. Výběr jiné osy i obrácení zůstávají při tomto omezení dostupné.

## Přesnost a ověření

Viewer přijme pouze FACE s `BRepAdaptor_Surface.GetType() == GeomAbs_Plane`.
`_rotation_pick_point(face, "face", hit, ray)` určí průsečík skutečného pixelového
paprsku s oříznutou BRep plochou, včetně děr. AIS bod je jen podklad detekce;
kotva neleží na jeho síti. Směr `Plane().Axis().Direction()` již obsahuje světové
umístění a obrací se pro `TopAbs_REVERSED`. Jiné orientace a nekonečné souřadnice
se odmítnou. Výběr používá generační a revizní protokol z P7.23–26, vlastní `plane`
druh v datech prstence i potvrzení. Staré potvrzení, cizí/skrytá plocha nebo jiný
druh osy se odmítají. Obrácení používá dosavadní společný životní cyklus.

Regrese kontrolují všech šest orientovaných stěn umístěného kvádru, šikmé plochy,
opačnou orientaci, průsečík mimo těžiště, díry, okraj rozsahu a neplatné paprsky,
odmítnutí křivých ploch, DPI 1/1,25/2, náhled AIS i potvrzení, skutečné vrcholy
otočených těles podle nezávislé rotace, historii a Znovu, samostatné snímky, staré
požadavky, výrazy a výběr plochy uvnitř podsestavy.

Nativní scénář skutečně odmítne válcový plášť, pak klikne mimo střed šikmého čela
třetí nožičky. Kotvu nezávisle ověří průsečíkem pixelového paprsku s rovinou čela,
směr s natočeným lokálním +Z. Ověří zachování AIS výběru, podkladů vazeb, kamery,
polí a historie, tři kliky Obrátit směr osy, Enter90, myš30, transformační matici
náhledu, těžiště a jeden Zpět/Znovu. Současně zůstávají scénáře válce a přímé hrany.
Evidence je v `out/p7-plane-normal-axis/`; úplné výsledky patří do PR.

# P7.24 – osa otáčení z válcové plochy

Datum: **2. 11. 2026**. Navazuje na P7.23. Formát souborů a závislosti beze změny.

Navazující [P7.25](p7-25-osa-prime-hrany.md) přidává nezávisle převzatou osu přímé hrany.

## Ovládání a rozsah

Při výběru více komponent v panelu **Společné otočení [°]** zvol osu **Válcová plocha**.
Stiskni **Vybrat osu ve 3D** a klikni na válcovou stěnu otvoru nebo čepu libovolného
viditelného dílu. Může být nevybraný, pevný nebo uvnitř podsestavy; výběr otáčených
komponent se kvůli referenci nemění. Skryté komponenty se neodkrývají.

Plocha určí celou přímku: bod a jednotkový směr v souřadnicích sestavy. Obě hodnoty
vidíš v panelu. Číselný úhel (tlačítko nebo Enter) i jeden oranžový rotační prstenec
používají tutéž přímku. Šipka ukazuje kladný směr, úhel je podle pravidla pravé ruky;
záporný úhel jej obrací. Platí dosavadní krok myši, náhled bez změny modelu a jeden
krok Zpět/Znovu po potvrzení. Zahrnuté jsou všechny vybrané větve včetně skrytých.

Rovina, kužel, eliptický či obecný spline plášť se nepřevádějí na přibližný válec.
Nevhodný klik dál čeká. Esc, pravý klik a **Zrušit výběr** ponechají poslední osu;
tažení dál ovládá kameru. Režim ruší také změny dat, výběru, osy, viditelnosti,
průhlednosti, rozměrů a aktivního okna stejně jako výběr středu v P7.23.

Osa je **pevný snímek a preference otevřeného okna**, není asociativní vazbou na plochu,
neukládá se do receptu a sama nevytváří historii. Po změně reference ji převezmi znovu.
Dosavadní pole středu jsou při válcové ose skrytá a jejich obsah se zachová pro návrat
na X/Y/Z. Natočení komponent zadané výrazy lze zachovat jen při ose přesně rovnoběžné
se světovým ±Z; pro šikmou osu je nutné číselné natočení. Panel omezení vysvětlí.

## Přesnost a přijetí

Viewer používá `BRepAdaptor_Surface(TopoDS.Face(shape), True)` nad skutečným umístěným
tvarem. Přijme jen `GeomAbs_Cylinder`, převezme směr z `Cylinder.Axis()` a bod
`Cylinder.Location() + direction * (FirstVParameter/2 + LastVParameter/2)`.
Střed konečného V intervalu umístí rukojeť k ploše, nepoužívá obálku ani síť AIS.
Směr válce může mít opačné znaménko než lokální Z dílu; rozhoduje vykreslená šipka.
Nekonečný či nečíselný interval se odmítne. Pořadí ploch se nepoužívá.

Sdílený režim detekce P7.23 nezmění vlastníky AIS výběru, `picked_point`, komponenty
ani podklady vazeb. Controller ověří aktivní generaci, model, výsledek, výběr,
viditelnost, příslušnost plochy, konečný bod a nenulový konečný směr. Stará odpověď
ani dokončení dřívějšího požadavku nesmějí vypnout nově spuštěný výběr. Přepnutí osy
tam a zpět také zneplatní starý návrh otočení.

`axis_direction` normalizuje i extrémně velké/malé konečné vektory přes škálování.
`axis_matrix` používá Rodriguesovu rotaci. `turn_many_around` provede stejnou afinní
mapu poloh a levé násobení orientací jako u XYZ; zachová výrazy poloh, otisky zdrojů
a ověření všech poloh po řešiči. Pevné díly, konflikt vazeb nebo změna zdroje odmítnou
celý pohyb. 0/360° nemění historii ani Znovu, chybná osa se ověří i pro celou otáčku.
Pro ±Z zůstanou výrazy natočení, pro ostatní směry se vyžadují číselné orientace.

Prstenec má pravotočivý ortonormální rám kolmý k převzatému směru. Úhel vychází
z průsečíku paprsku s jeho rovinou, AIS náhled i potvrzený pohyb mají stejnou osu.
Téměř boční prstenec se nezobrazuje. Kamera a výběr ploch se nemění.

## Ověření

Regrese porovnávají vrcholy, orientace a polohy s nezávislou osovou rotací, včetně
extrémních vektorů, podsestav, parametrů, pevných dílů, vazeb, změny zdroje, historie,
uložení/opětovného otevření a STEP exportu. Geometrický výběr rozlišuje šikmé válce,
čela a kužely. Interakční test kontroluje skutečnou AIS transformaci náhledu a jediné
potvrzení; testy okna také staré tokeny, zrušení, opravu chybějící osy a výrazy natočení.

Nativní self-test na obou systémech kliká na šikmou nožičku mimo výběr, odmítne rovinu,
ověří skutečný AIS výběr a podklady vazeb, přesný bod/směr, kameru, materiály 35/85 %,
pole a historii. Následně otočí Enterem o 90° a tažením prstence o 30°, kontroluje
skutečná těžiště, validitu těles a jeden Zpět/Znovu. Esc/tlačítko/změna osy ukončí
další výběr bez změny snímku. Místní evidence: `out/p7-cylinder-rotation-axis/`;
úplné výsledky Windows/macOS a stažených balíčků patří do implementačního PR.

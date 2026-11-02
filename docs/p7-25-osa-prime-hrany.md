# P7.25 – osa otáčení z přímé hrany

Datum: **2. 11. 2026**. Navazuje na P7.24; jádro otáčení, formát a závislosti beze změny.

Navazující [P7.26](p7-26-obraceni-smeru-osy.md) přidává tlačítko **Obrátit směr osy**.

## Ovládání a rozsah

Při výběru více komponent zvol v panelu **Společné otočení [°]** osu **Přímá hrana**.
Stiskni **Vybrat osu ve 3D** a klikni na přímou hranu libovolného viditelného dílu.
Může být nevybraný, pevný nebo uvnitř podsestavy. Výběr otáčených komponent a podklady
vazeb zůstávají zachované; převzetí samo nemění model, soubory ani historii.

Osa je celá nosná přímka hrany ve světě sestavy, platí i pro šikmé hrany. Bod uprostřed
úsečky pouze určuje umístění rukojeti; neomezuje délku osy. Číselný úhel a oranžový
prstenec používají stejný bod a směr. Popisek **Osa hrany** a šipka ukazují zvolenou
referenci a kladný směr, záporný úhel otáčí opačně. Platí dosavadní krok tažení,
náhled pouze v prezentaci a jeden krok Zpět/Znovu pro celý potvrzený pohyb.

Přijme se pouze skutečná konečná přímá hrana. Kružnice, oblouk, Bézierova či spline
křivka se neaproximují přímkou, ani když působí rovně. Degenerovaná, nulová nebo
nekonečná hrana není platnou referencí. Klik na nevhodnou hranu či prázdné místo
dál čeká. Esc, pravý klik a **Zrušit výběr** ponechají předchozí osu i výběr dílů.
Kamera se dá dál ovládat tažením a kolečkem; navigace osu nepotvrdí.

Osa hrany a osa válce jsou **samostatné pevné snímky preference otevřeného okna**.
Přepnutí na dosud nepřevzatý druh vyžaduje nový výběr, nemůže použít osu druhého druhu.
Návrat obnoví poslední snímek daného druhu. Nejde o asociativní vazbu ani uloženou
položku modelu; po změně referenčního dílu osu převezmi znovu. Volba XYZ obnoví
dosavadní nastavení středu a jeho rozepsané hodnoty. Omezení výrazů natočení z P7.24
zůstává: přesné ±Z je zachová, ostatní směry vyžadují číselné natočení komponent.

Přímý šev na válcové ploše je také skutečná přímá hrana. Jeho osa vede tímto švem,
nikoli středem válce. Pro středovou osu otvoru nebo čepu použij **Válcová plocha**.

## Přesnost a životní cyklus

Viewer aktivuje pouze EDGE detekci a využívá generační protokol výběru z P7.23/24.
Nevolá SelectDetected ani nemění `picked_point`. `BRepAdaptor_Curve(TopoDS.Edge(shape))`
čte již umístěnou geometrii; přijme pouze `GeomAbs_Line`, odmítne `Degenerated_s`,
nekonečné/nekonečně velké meze i `last <= first`. Kotva je `Value(first/2+last/2)`,
směr `Line().Direction()`. Číselná kontrola odmítne nekonečné souřadnice. Výběr
nepoužívá pořadí hran, jejich obálku, síť ani kliknutý bod místo skutečné osy.

Směr vychází z parametrizace nosné přímky. Opačná topologická orientace hrany sama
nezmění její přímku ani směr; ten je vidět šipkou při zapnutých rotačních rukojetích.
Controller ověří aktivní generaci, revizi, druh reference, model, výsledek, výběr,
viditelnost, příslušnost hrany a konečný bod/směr. Změna druhu, geometrie nebo prezentace
výběr ruší stejně jako u válce. Stará odpověď ani staré dokončení nesmějí vypnout
nový požadavek. Přepnutí tam a zpět zneplatní také staré potvrzení rotačního tahu.

Data prstence nesou `axis_kind`; puštění vysílá `line` nebo `cylinder` a controller
přijme jen aktuální druh. Matematika náhledu a `turn_many_around` zůstává společná
s P7.24, včetně atomického odmítnutí nepovoleného pohybu vazbami a ochrany zdrojů.

## Ověření

Regrese kontrolují umístěné hrany XYZ i šikmé, konečný výřez mimo počátek nosné přímky,
opačnou orientaci, neplatné hrany a odmítnutí křivek. Poměry pixelů 1/1,25/2 ověřují
jediné převzetí i potvrzení tahu, nezměněný výběr, obnovu režimů a přesnou AIS rotaci.
Okno kontroluje skutečný pohyb obou vybraných dílů proti nezávislé rotaci, historii,
Znovu, vazební výběr, samostatné snímky, zrušení a staré požadavky, podsestavy a výrazy.

Nativní self-test obou systémů sdílí scénář válce a přímé hrany. Pro hranu skutečně
klikne na kružnici a odmítne ji; pak vybere šikmý přímý šev nevybrané třetí nožičky.
Kontroluje nezávisle spočítanou osu mimo střed válce, AIS výběr a podklady vazeb,
kameru, 35/85 % průhlednost, pole a historii. Enterem provede 90° a myší 30° kolem
téže přímky s kontrolou těžišť, validity těles a jednoho Zpět/Znovu. Po převzetí
je kamera beze změny; před tažením se výslovně přepne ze zadního pohledu na izometrii.
Místní evidence a snímky: `out/p7-line-rotation-axis/`; úplné výsledky patří do PR.

Windows při úplném ověření dvakrát dokončil všech 2 614 testů (29:34 a 29:21), ale
30minutový limit přerušil následné nativní ukončování procesu. Proto má testovací
krok rezervu 35 minut, stejně jako macOS. Příkaz celé sady a požadavek normálního
úspěšného ukončení, ruff i zkoušky stažených balíčků se nemění; žádný test se nepřeskakuje.
Tato úprava CI a dokumentace nemění produktový kód ani již ověřenou místní aplikaci.

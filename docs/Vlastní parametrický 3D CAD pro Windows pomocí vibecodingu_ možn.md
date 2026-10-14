# Vlastní parametrický 3D CAD pro Windows pomocí vibecodingu: možnosti, licence a funkce (stav k říjnu 2026)

Nejlepší realistická cesta pro tebe je postavit aplikaci na jádře Open CASCADE Technology (OCCT 8.0.x, LGPL 2.1 s výjimkou), ideálně v C# na základě otevřeného projektu Macad|3D (licence MIT, C#/.NET + WPF + automaticky generovaný C++/CLI wrapper OCCT), a skicu řešit FreeCADovým solverem PlaneGCS (LGPL) jako samostatnou DLL. Klon Inventoru nebo Solid Edge jeden člověk s AI nepostaví, ale dobrý, „chytrý" parametrický modelář jednotlivých dílů s exportem STEP/STL a několika strojařskými/NDT vychytávkami je dosažitelný cíl.

## TL;DR

- **Jádro a stack:** OCCT je jediné bezplatné, zralé B-rep jádro s fillety, skořepinou, booleany a STEP; doporučuju C# + WPF + OCCT přes MIT wrapper z Macad|3D (cesta A), alternativně C++ + Qt + OCCT s inspirací v Mayo/Dune 3D/FreeCAD (cesta B). Rust (Fornjot byl v červnu 2026 ukončen, Truck je nezralý) a mesh/SDF knihovny pro strojařský CAD nedoporučuju jako hlavní jádro.
- **Licence:** OCCT (LGPL + výjimka), PlaneGCS (LGPL), Qt (LGPL) a Macad|3D (MIT) nechávají otevřenou komerci, pokud linkuješ dynamicky a zveřejníš změny v samotných knihovnách; SolveSpace solver (GPLv3) a CGAL (z velké části GPL) tě tlačí do GPL; CalculiX a Gmsh (GPL) spouštěj jako samostatné programy přes soubory, ne linkováním.
- **Rozsah:** MVP = skicář s vazbami + vysunutí/rotace/kapsa + zaoblení/sražení + strom prvků s přepočtem + STEP/STL export + měření a hmotnost. Sestavy, výkresy a plechy jsou další fáze; „wow" prvky jako AI asistent nad textovým popisem modelu, mapa tloušťky stěn pro NDT nebo FEA přes CalculiX jsou proveditelné, protože stojí na hotových knihovnách.

## Key Findings

1. **OCCT je pro tebe de facto jediná volba bezplatného B-rep jádra.** Verze 8.0.0 vyšla 7. května 2026; podle oznámení Open Cascade vývojový cyklus zahrnoval pět release kandidátů a tři bety a „accumulated more than 500 changes since 7.9.0", šlo o „the largest single-version step in OCCT in many years"; 8.0.1 (30. července 2026) se zaměřila na spolehlivost modelování, shape healing, export STEP a souběžné fillety. Licence je LGPL 2.1 s „Open CASCADE Exception", která dovoluje distribuovat objektový kód obsahující materiál z hlavičkových souborů „za podmínek dle tvé volby", pokud v dokumentaci výrazně uvedeš, že software používá OCCT. [opencascade](https://dev.opencascade.org/content/open-cascade-technology-changes-its-license-gnu-lgpl) [opencascade](https://dev.opencascade.org/doc/occt-7.7.0/overview/html/occt_public_license.html)
2. **Komerční jádra jsou pro hobby projekt mimo hru.** Parasolid (Siemens) je podle stránky Siemensu licencovaný „200+ independent software vendors" a mezi CAD licenciáty jmenuje Bentley Systems, Fujitsu, IronCAD, Onshape, Shapr3D a Top Systems; cena není veřejná a dostaneš jen 60denní zkušební verzi. C3D Toolkit má podle licenční stránky C3D Labs roční poplatek plus royalty (typicky 2–7 % z ceny produktu), a pokud je produkt „based almost entirely on the capabilities of the C3D Toolkit, a royalty rate of 25–30% applies"; akademická licence stojí 5 000 USD ročně za všechny moduly.
3. **Plasticity i Shapr3D stojí na Parasolidu**; Shapr3D navíc licencuje od Siemensu D-Cubed PGM. [siemens](https://www.siemens.com/en-us/products/plm-components/parasolid/) Plasticity přitom během vývoje začínalo na jádře C3D a později přešlo na Parasolid – to ukazuje, že i úspěšný indie vývojář nakonec platí za komerční jádro, když chce špičkové zaoblování. [note](https://note.com/tomo1230ee/n/n42b0663ae8dd?hl=en) [demystifyingplm](https://www.demystifyingplm.com/cad-modeling-paradigms-nurbs-parametric-implicit)
4. **Topological naming problem je hlavní technická past parametrického CAD.** FreeCAD ho „zmírnil" až ve verzi 1.0 (listopad 2024) převzetím algoritmu z forku vývojáře Realthunder; integraci podle blogu Ondsel dělali placení vývojáři bgbsww, CalligaroV a John Dupuy spolu s dobrovolníky (RealThunder, Chris Hennes, Pesc0) přes rok, a výroční zpráva FreeCAD Project Association za rok 2024 uvádí granty na toponaming pro bgbsww (4 800 + 5 000 + 5 000 USD) a CalligaroV (3 400 EUR). FreeCAD 1.1 vyšel 24. března 2026 s více než 1 700 změnami a mitigaci rozšířil.
5. **Rust není dnes dobrá volba:** Fornjot jeho autor Hanno Braun 19. června 2026 oficiálně ukončil („Fornjot is ending; unfinished, incomplete."; „Six years without even delivering something useful"), a Truck (Apache-2.0) se vyvíjí hlavně ve forcích (např. monstertruck) s fillety a booleany, ale bez zralosti OCCT.
6. **Text-to-CAD dospěl ke „kódu jako modelu".** Podle výzkumného článku Zoo (5. února 2026) firma „In January 2026 … shipped our conversational agent as 'Zookeeper' with Zoo Design Studio v1.1"; agent píše parametrický kód v jazyce KCL a převod STEP → editovatelný KCL je na roadmapě „In Progress – Q4 2026". Pro tebe z toho plyne architektonické doporučení: ukládej model jako čitelný textový recept, protože ten umí LLM číst i upravovat.

## Details

### 1. Geometrická jádra a alternativy

| Jádro | Fillety / shell / booleany / STEP | Licence a cena | Zralost a dokumentace | Verdikt pro tebe |
|---|---|---|---|---|
| **OCCT 8.0.1** | Ano / ano / ano / ano (STEP, IGES, STL, glTF, OBJ) | LGPL 2.1 + výjimka, zdarma; volitelně komerční licence | Desítky let vývoje (od roku 1999 jako open source), velká komunita, FreeCAD, CadQuery, build123d, Dune 3D, Macad|3D [github +2](https://github.com/gumyr/build123d) | **Doporučeno** |
| Parasolid (Siemens) | Vše, špička trhu, přes 900 funkcí [siemens](https://resources.sw.siemens.com/en-US/parasolid-free-evaluation/) | Proprietární, cena na vyžádání, [TechCrunch](https://techcrunch.com/2019/04/27/this-startup-just-raised-10-million-dyndrite/) 60denní evaluace [siemens](https://resources.sw.siemens.com/en-US/parasolid-free-evaluation/) [Wikipedia](https://en.wikipedia.org/wiki/Parasolid) | Průmyslový standard (NX, Solid Edge, SolidWorks, Onshape, Shapr3D) [3dprint](https://3dprint.com/164312/verashape-licenses-parasolid/) [siemens](https://www.siemens.com/en-us/products/plm-components/parasolid/) | Jen při vážné komerci s investorem |
| ACIS (Spatial / Dassault) | Vše | Proprietární, cena na vyžádání | Zralé | Mimo rozpočet |
| C3D Toolkit (C3D Labs) | Vše + vlastní solver vazeb, převodník, vizualizace [c3dlabs](https://c3dlabs.com/products/c3d-toolkit/) | Roční poplatek + royalty 2–7 % (až 25–30 %), akademická licence 5 000 USD/rok, 90denní evaluace [c3dlabs](https://c3dlabs.com/products/c3d-toolkit/) | Zralé, původem z KOMPAS-3D (Rusko) [dbpedia](https://dbpedia.org/page/C3D_Toolkit) [Wikipedia](https://en.wikipedia.org/wiki/Geometric_constraint_solving) | Pro jaderný průmysl zvaž compliance a sankční rizika dodavatele |
| Manifold | Jen mesh booleany (garantovaně manifold), SDF level sety; žádné přesné fillety ani STEP | Apache-2.0 | Velmi rychlé, používá OpenSCAD a Blender | Doplněk pro 3D tisk/síťové operace, ne hlavní jádro |
| CGAL | Robustní síťové a polyedrické booleany, ne B-rep CAD | Základy LGPL, většina algoritmů GPL; komerční licence od GeometryFactory | Akademicky špičkové | Licenčně nevhodné pro uzavřenou komerci |
| Truck (Rust) | Základní booleany a fillety hlavně ve forcích, STEP I/O [github](https://github.com/stefangolas/truck) [github](https://github.com/KroneCorylus/truck) | Apache-2.0 | Nezralé, roztříštěné forky [github](https://github.com/ricosjp/truck/blob/master/truck-modeling/examples/bottle.rs) | Ne |
| Fornjot (Rust) | Jen základní sweepy | — | **Ukončeno 19. 6. 2026** | Ne |
| libfive (SDF/F-rep) | Hladké blendy, CSG triviální; výstup je síť [libfive](https://libfive.com/) [github](https://github.com/libfive/libfive) | Jádro MPL-2.0, Studio GPL [libfive](https://libfive.com/) | Stabilní, úzce zaměřené | Jen „wow" funkce (mřížky, organické tvary) |

Poznámka k OCCT: na GitHubu je otevřený issue #1564, podle kterého osm souborů v TKGeomBase (release V8_0_1) má v hlavičce text „This file is part of commercial software by OPEN CASCADE SAS", což je v rozporu se zbytkem repozitáře pod LGPL. [github](https://github.com/Open-Cascade-SAS/OCCT/issues/1564) Pro hobby to nevadí, před komerčním vydáním si ověř, jak byl vyřešen.

Open Cascade v oznámení OCCT 8.0.0 uvádí, že čtení STEP je oproti verzi 7.7 rychlejší „by up to 75%" a že zrychlily i čtečky DXF, SAT a Parasolid – je to tvrzení dodavatele, ne nezávislý benchmark. OCCT 8.0 navíc vyžaduje C++17, reorganizoval strom zdrojů a odstranil některé starší balíčky, takže AI generovaný kód podle starších příkladů (7.x) může narazit na neexistující třídy. [github](https://github.com/Open-Cascade-SAS/OCCT/discussions/1275)

### 2. Řešiče geometrických vazeb pro skicář

| Solver | Licence | Poznámka |
|---|---|---|
| **PlaneGCS (FreeCAD)** | LGPL-2.1-or-later [github](https://github.com/spookylukey/planegcs/) [github](https://github.com/2wiceUponATime/PlaneGCS) | 2D solver s algoritmy DogLeg, Levenberg-Marquardt, BFGS a SQP; existují samostatné extrakce (např. Python wrapper, WebAssembly wrapper, buildy z větve FreeCAD 1.1). Lze přeložit jako `planegcs.dll` a volat přes P/Invoke. **Doporučeno.** [github +3](https://github.com/Salusoft89/planegcs) |
| SolveSpace (libslvs) | GPLv3, komerční licence po dohodě s autorem [github](https://github.com/BBBSnowball/python-solvespace) [solvespace](https://solvespace.com/library.pl) | Velmi dobrý 2D/3D solver, používá ho Dune 3D a CAD Sketcher pro Blender. Autor sám píše, že GPLv3 „generally forbids linking the library with proprietary software". | [github](https://github.com/BBBSnowball/python-solvespace)
| D-Cubed DCM (Siemens) | Proprietární | Průmyslový standard; nedostupné pro hobby. [occt3d](https://occt3d.com/dev/content/constraint-solver/index.html) [Wikipedia](https://en.wikipedia.org/wiki/Geometric_constraint_solving) |
| C3D Solver | Proprietární, součást C3D Toolkit | Viz výše. [Wikipedia](https://en.wikipedia.org/wiki/Geometric_constraint_solving) |

Prakticky: PlaneGCS ti nechá otevřenou komerci, SolveSpace by celou aplikaci udělal GPL. Dune 3D musel navíc solver SolveSpace upravit, aby byl dost rychlý [github](https://github.com/dune3d/dune3d) – počítej s tím, že ani PlaneGCS nebude „zadarmo" bez ladění (FreeCAD v roce 2026 stále opravuje pády DogLeg solveru při tažení oblouků s vazbou tečnosti). [github](https://github.com/FreeCAD/FreeCAD/pull/33215)

### 3. Jazyky a frameworky pro nativní Windows

**C# + WPF + OCCT (cesta A).** Macad|3D je „mainly based on the technologies .Net, C#, C++/CLI and OpenCASCADE Technology". Wrapper do jmenného prostoru `Macad.Occt` se generuje automaticky a vygenerovaný kód je v repozitáři; nepokrývá celé OCCT – co chybí, doplníš úpravou konfigurace generátoru. [github](https://github.com/Macad3D/Macad3D) Verze 4.0 přešla na .NET 8 a C# 12, verze 4.4 používá OCCT 7.9.2; aktuální větev main už v README požaduje Visual Studio 2026 a .NET 10. [github](https://github.com/Macad3D/Macad3D) [macad3d](https://macad3d.net/userguide/docs/Changelog/Changelog-v4.html) Pro zobrazení používá nativní OCCT viewer (`V3d_View` ve třídě `ViewportController`). [macad3d](https://macad3d.net/userguide/api/Macad.Interaction.ViewportController.html) Wrapper se dá použít samostatně – uživatel na fóru Autodesku popisuje, že projekt sestavil a použil jen wrapper. [autodesk](https://forums.autodesk.com/t5/revit-api-forum/boolean-operation-fail/td-p/7531968/page/3) Další možnosti:
- **NetOcc**: SWIG-generované C# bindingy pro OCCT 8.0.1 ve stylu pythonOCC, pro .NET 6/8/10 a Windows x64/x86; [github](https://github.com/paulbuechner/netocc) zralost a licenci vlastního kódu jsem neověřil.
- **Oficiální C# vzorky OCCT**: ručně psaný C++/CLI proxy; ve WPF je OCCT viewer vložen buď přes WinForms control („WPF does not provide the necessary interface to embed OpenGl view"), nebo přes Direct3D povrch. [github](https://github.com/Open-Cascade-SAS/OCCT-samples-csharp) [opencascade](https://old.opencascade.com/doc/occt-7.4.0/overview/html/samples_csharp_direct3d.html) Jsou ale pro starý .NET Framework. [opencascade](https://dev.opencascade.org/doc/occt-7.8.0/overview/html/samples_csharp_direct3d.html)
- **Komerční OCCT3D C# Wrapper**: dodáván ve zdrojové formě, s NuGet balíčky a nativními runtime soubory, podporuje OCCT 8.0.0 a .NET 6–10; [occt3d](https://occt3d.com/open-cascade-c-wrapper-updated-for-occt-8-0-0/) cena na vyžádání. [occt3d +2](https://occt3d.com/news/open-cascade-c-wrapper-updated-for-occt-8-0-0/)
- **WinUI 3 / Avalonia**: možné, ale nemáš pro ně hotový vzor s OCCT viewerem; WPF je nejbezpečnější, protože na něm Macad|3D funguje.

**C++ + Qt + OCCT (cesta B).** Na této kombinaci stojí FreeCAD (OCCT + Coin3D + Qt), Mayo (C++, Qt, OCCT; licence BSD-2-Clause, tedy volně použitelná i komerčně) i Dune 3D (OCCT + solver SolveSpace + UI z Horizon EDA). [linuxlinks +3](https://www.linuxlinks.com/mayo-3d-cad-viewer-converter/) Výhoda: nejvíc příkladů na webu i v trénovacích datech AI, přímý přístup k celému API bez wrapperu. Nevýhoda: sestavení OCCT a Qt přes CMake na Windows a ladění pádů v C++ je pro neprogramátora nejtěžší část celého projektu.

**Python (pythonOCC / CadQuery / build123d).** CadQuery a build123d jsou pod Apache-2.0; build123d je „derived from portions of CadQuery, but is extensively refactored" a stojí nad OCCT; balíček cadquery-ocp už nabízí OCCT 8.0.1 pro Python 3.11–3.14. [github +2](https://github.com/gumyr/build123d) Skvělé na prototypování geometrie a jako „skriptovací vrstva" pro AI, ale pro distribuci nativní Windows aplikace s plynulým GUI je Python slabší.

**Rust (Truck/Fornjot).** Nedoporučuju – viz Key Findings.

**Tvůj Raylib-cs + ImGui přístup.** Dá se použít: OCCT tvar se teselací převede na trojúhelníky a ty vykreslíš Raylibem. Ale přijdeš o hotový výběr hran/ploch, zvýraznění a manipulátory z OCCT AIS, které bys musel vibecodovat znovu. Doporučuju ho jen jako experiment nebo pro samostatný „viewer" režim, ne jako základ.

**Rendering.** Nejjednodušší je vestavěný OCCT viewer (V3d/AIS nad OpenGL). DirectX je dostupný přes interop vzorek OCCT; [github](https://github.com/Open-Cascade-SAS/OCCT/wiki/samples) [wordpress](https://unlimited3d.wordpress.com/2021/03/27/occt-minimal-viewer-setup/) Vulkan by znamenal vlastní renderer – zbytečná práce navíc.

### 4. Open-source projekty k učení nebo forknutí

| Projekt | Stack | Licence | K čemu ti je |
|---|---|---|---|
| **Macad|3D 4.4** | C#, .NET 8, WPF, C++/CLI, OCCT 7.9.x | MIT | Přímý základ pro cestu A (fork nebo převzetí wrapperu) |
| **Mayo** | C++, Qt, OCCT | BSD-2-Clause | Kostra Qt+OCCT aplikace: viewer, import/export |
| **Dune 3D** | C++, OCCT, solver SolveSpace | GPL (kvůli solveru) | Vzor UX: nemodální skicář ve 2D i 3D, vazby i pro vysunutí; jen k učení, ne ke kopírování kódu do ne-GPL projektu |
| **FreeCAD 1.1** | C++, Python, Qt, OCCT, Coin3D | LGPL-2.1+ | Referenční implementace TNP, PlaneGCS, sestav, FEM (CalculiX, Gmsh) | [Wikipedia +2](https://en.wikipedia.org/wiki/FreeCAD)
| **SolveSpace** | C++ | GPLv3 | Elegantní parametrický workflow, solver | [solvespace](https://solvespace.com/) [archive](https://archive.org/details/solvespace-3.1)
| **CAD Sketcher** | Blender add-on se solverem SolveSpace | GPL | Inspirace pro skicování |
| **BRL-CAD** | C/C++, CSG | — | Historicky zajímavý, pro tvůj cíl spíš ne |
| Plasticity / Shapr3D | Proprietární, Parasolid | — | Inspirace pro UX (gesta, radiální menu, přímá manipulace) [siemens](https://www.siemens.com/en-us/products/plm-components/parasolid/) |

### 5. Klíčové technické problémy

**Topological naming problem.** Když změníš rozměr dřívějšího prvku, jádro přečísluje plochy a hrany a pozdější prvky (zaoblení „hrany 12", skica „na ploše 5") se odkazují na něco jiného. FreeCAD to řeší tak, že „tracks how individual sub-elements (faces, edges, vertices) evolve through modeling operations by building a history map that records whether elements were modified, generated, or deleted". [github](https://freecad.github.io/Website/download/releases/1-0/) Ani to není úplné řešení – samotná dokumentace FreeCADu stále doporučuje kotvit skici na základní roviny nebo pomocné roviny místo na plochy těla. [github](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Topological_naming_problem.md) Pro tebe:
- Od začátku ukládej odkazy sémanticky („boční plocha vzniklá vysunutím úsečky L3 ze Skici 1"), ne indexem.
- Využij historii, kterou vrací OCCT operace (Generated/Modified/IsDeleted u booleanů a sweepů), případně mechanismus TNaming v OCAF.
- V MVP kotvi skici přednostně na roviny a osy.

**Historie a parametrický strom.** Model = seznam prvků (feature list) s parametry; přepočet od změněného prvku dolů. Ukládej ho jako čitelný JSON (nebo vlastní mini-jazyk) – je diffovatelný v gitu, AI ho umí upravovat a je to stejná myšlenka jako KCL od Zoo. [texocad](https://blog.texocad.ai/glossary/kcl)

**Výkon.** Fillety a booleany na složitých tělech trvají sekundy; přepočítávej v pozadí, cachuj výsledné tvary prvků a teselaci. OCCT 8.0.1 výslovně opravil bezpečnost souběžného počítání filletů ve vláknech. [opencascade](https://dev.opencascade.org/content/open-cascade-technology-801-release)

**Formáty.** STEP a IGES přímo v OCCT (STEP i s barvami a strukturou sestavy přes XDE). [occt3d](https://occt3d.com/open-cascade-technology-7-9-0-released/) STL přímo v OCCT. 3MF a DXF nejsou v open-source OCCT; řeš je externí knihovnou (např. lib3mf pro 3MF, pro DXF knihovna v C# nebo C++). Nativní formát: JSON receptura + volitelně uložený BREP jako cache.

### 6. Proveditelnost pro vibecodera bez znalosti programování

**Realistické měřítko.** FreeCAD má za sebou přes 20 let vývoje; samotnou integraci TNP dělalo přes rok několik vývojářů placených z grantů FreeCAD Project Association (bgbsww, CalligaroV) a Ondselu (John Dupuy) spolu s dobrovolníky; Fornjot po šesti letech skončil, aniž dodal použitelný výsledek. Na druhou stranu Dune 3D postavil jeden autor (byť zkušený programátor) složením hotových dílů: OCCT + solver + vlastní UI. Tohle je i tvoje strategie: **nepiš jádro, skládej hotové komponenty.**

**Který stack AI zvládá nejlépe.**
- C++/OCCT: nejvíc kódu na webu (FreeCAD, Mayo, Dune 3D, oficiální vzorky), ale chyby při sestavení a pády za běhu jsou pro tebe nejhůř čitelné.
- C#: čitelnější chybové hlášky, výjimky místo pádů, a máš s ním zkušenost; nevýhoda je, že AI musí příklady z C++ API „překládat" na názvy z wrapperu.
- Python/build123d: nejsnazší pro samotnou geometrii, nejhorší pro distribuci desktopové aplikace.

**Typické pasti a jak jim předejít.**
1. *Halucinace API:* AI vymýšlí neexistující třídy OCCT nebo míchá verze 7.x a 8.0. Zamkni verzi (OCCT 8.0.1 nebo konkrétní verzi z Macad|3D) a dej Claude Code přístup k lokálním hlavičkám a dokumentaci.
2. *Nevalidní geometrie:* po každé operaci kontroluj tvar (BRepCheck_Analyzer) a selhání vracej jako čitelnou chybu prvku („Zaoblení R5 selhalo – poloměr je větší než hrana").
3. *Paměť mezi .NET a nativním kódem:* drž se konvencí vlastnictví objektů z wrapperu; nativní pád shodí celou aplikaci. [occt3d](https://occt3d.com/components/csharp-wrapper/)
4. *Monolit:* AI se ztrácí ve velkých souborech. Odděl **Core** (geometrie, feature list, bez UI) od **UI** a od **IO**.
5. *Chybějící testy:* geometrie má skvělé „orákulum" – objem, těžiště a plochu. Pro každý prvek měj headless test „krychle 100×100×100 s dírou ⌀20 má objem X" a kontroluj ho po každé změně, kterou AI udělá.
6. *Kontext:* udržuj soubor `CLAUDE.md` s architekturou, pravidly a seznamem modulů; dávej AI malé, ověřitelné úkoly.

**Doporučené dvě cesty.**

**Cesta A (doporučená): C# (.NET 8/10) + WPF + OCCT přes wrapper Macad|3D + PlaneGCS jako DLL.**
- Proč: znáš C#, MIT licence základu, OCCT viewer už funguje ve WPF, otevřená cesta ke komerci (LGPL komponenty dynamicky).
- Varianta A1: forkni rovnou Macad|3D a přetvoř jeho workflow (je zaměřený na modeláře – „model making hobbyist") na strojařský parametrický CAD. [macad3d](https://macad3d.net/)
- Varianta A2: převezmi jen `Macad.Occt` wrapper a postav vlastní aplikaci od nuly – čistší architektura, víc práce.
- Riziko: C++/CLI je jen pro Windows (to ti nevadí), regenerace wrapperu je složitější krok.

**Cesta B: C++ + Qt + OCCT, s Mayo (BSD-2) jako kostrou a FreeCADem/Dune 3D jako referencí.**
- Proč: nejvíc příkladů, žádná mezivrstva, plná kontrola. Vhodné, pokud v cestě A narazíš na limity wrapperu.
- Riziko: náročné sestavení a ladění.

Python/build123d použij paralelně jako **pískoviště**: rychle si ověř, jak se má geometrická operace chovat, a teprve pak ji nech AI přepsat do hlavní aplikace.

**Fázovaný roadmap.**
- *Fáze 0 (2–4 týdny):* sestavit fork, zobrazit krychli, export STEP/STL, první automatický test objemu.
- *Fáze 1 – MVP (cca 3–6 měsíců večerní práce):* skicář (úsečka, oblouk, kružnice, obdélník) s vazbami PlaneGCS a kótami; vysunutí, kapsa, rotace; zaoblení, sražení; strom prvků s editací a přepočtem; JSON formát; měření, objem, hmotnost.
- *Fáze 2:* skořepina, díry včetně závitů, pole, zrcadlení, sweep, loft, řezy modelem, materiály, vyhledávání příkazů.
- *Fáze 3:* jednoduché sestavy, 2D výkresy, kusovník, plechy.
- *Fáze 4 („wow"):* AI asistent, NDT vizualizace, FEA.

Časové odhady jsou můj úsudek, ne změřená data.

## ČÁST 2 – Funkce a vychytávky

### Rozdělení funkcí: MVP / další fáze / „wow"

Náročnost: 🟢 nízká (hotová funkce OCCT + UI), 🟡 střední, 🔴 vysoká (vlastní algoritmy nebo velký UX).

**MVP**

| Funkce | Náročnost | Poznámka |
|---|---|---|
| Skicář s vazbami a kótami | 🔴 | Nejtěžší část MVP: PlaneGCS + interakce myší + odvozování vazeb |
| Vysunutí, kapsa, rotace | 🟢 | Přímé OCCT operace |
| Zaoblení, sražení | 🟡 | OCCT umí; těžké je vybírání hran a TNP |
| Strom prvků + přepočet | 🟡 | Jádro tvé architektury |
| Měření, objem, těžiště, hmotnost | 🟢 | OCCT výpočty vlastností těles; hustota z tabulky materiálů |
| Export STEP/STL | 🟢 | V OCCT |
| Undo/redo | 🟡 | Snadné, pokud je model jen seznam prvků |

**Další fáze**

| Funkce | Náročnost | Poznámka |
|---|---|---|
| Skořepina (shell) | 🟡 | OCCT umí, často selhává na složitých tělech |
| Díry se závity dle ISO (tabulka M, MF, G) | 🟡 | Tvoje strojnické tabulky z Android aplikace přeneseš jako data |
| Pole (lineární, kruhové), zrcadlení | 🟢–🟡 | |
| Sweep, loft | 🟡 | OCCT umí; UX výběru profilů je práce |
| Řez modelem | 🟢 | Clipping roviny ve vieweru |
| Časová osa (Fusion 360 styl) | 🟡 | Jiné zobrazení stromu, „rollback marker" |
| Sestavy s vazbami | 🔴 | Potřebuješ 3D solver vazeb (FreeCAD má vlastní assembly solver, pozor na licence) |
| 2D výkresy s kótami a řezy | 🔴 | OCCT má skrytí čar (HLR), ale kótování a normy výkresů jsou velký projekt |
| Kusovník (BOM) | 🟢 | Po zavedení sestav jednoduché |
| Plechové díly | 🔴 | Ohyby, rozvin, K-faktor |
| Export 3MF, import/export DXF | 🟡 | Externí knihovny |

**„Wow" vychytávky**

| Funkce | Náročnost | Poznámka |
|---|---|---|
| Vyhledávání příkazů (Ctrl+K) | 🟢 | Malá práce, velký efekt |
| Radiální (marking) menu, kontextový minitoolbar | 🟡 | Plasticity zavedlo radiální menu ve verzi 1.3 [cgchannel](https://www.cgchannel.com/2023/10/nick-kallen-ships-plasticity-1-3/) |
| Chytré odvozování vazeb (horizontála, tečnost, shoda při kreslení) | 🟡 | Heuristika podle tolerance |
| Přímá manipulace: tahání plochy šipkou mění kótu prvku | 🟡 | Mapování plochy zpět na parametr prvku |
| Synchronní/direct modeling (Solid Edge) | 🔴 | Přesun a odsazení ploch bez historie; OCCT má jen základní nástroje, robustnost Parasolidu nečekej [Wikipedia](https://en.wikipedia.org/wiki/Parasolid) |
| AI asistent v aplikaci (Claude API) | 🟡 | Díky textovému formátu modelu: „přidej 4 díry M8 na roztečné kružnici 80" → AI upraví JSON → přepočet; vždy s náhledem a potvrzením |
| Text-to-CAD | 🟡 | Stejný mechanismus jako AI asistent, jen z prázdného modelu |
| AI automatické vazby ve skice | 🟡 | Spíš heuristika než LLM; LLM může navrhnout chybějící kóty |
| Generativní design / topologická optimalizace | 🔴 | Mimo realistický rozsah |
| Knihovna normalizovaných dílů (ISO/ČSN šrouby, matice, podložky, ložiska) | 🟡 | Parametrické generátory z tabulek; data jsou hlavní práce |
| Integrace strojnických tabulek | 🟢 | Máš je z Android aplikace |
| Svary a značky svarů (ISO 2553) | 🟡 | Jako anotace ve 3D a na výkresu; geometrie svaru volitelně |
| Export pro 3D tisk + kontrola (minimální tloušťka, převisy) | 🟡 | Manifold (Apache-2.0) se hodí na síťové operace [github](https://github.com/elalish/manifold) |
| FEA přes CalculiX + Gmsh | 🔴 (ale proveditelné) | Spouštěj jako externí programy přes soubory, stejně jako FreeCAD (.inp → CalculiX → .frd) [github](https://github.com/Virtastic/freecad-web) [github](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/FEM_CalculiX.md) |
| **NDT: mapa tloušťky stěny** | 🟡 | Paprsek z každého bodu teselace proti normále → barevná mapa; velmi užitečné pro UT měření tloušťky a relativně snadné |
| **NDT: přístupnost pro sondy** | 🔴 | Kontrola, zda se sonda daného rozměru dostane k povrchu a pod jakým úhlem; kolizní test tělesa sondy |
| **NDT: řezy s vyznačením kontrolních zón a svarů** | 🟡 | Řez modelem + anotace oblastí kontroly |

### Moderní UX – co opravdu dělá modelování intuitivním

- **Nemodální skicář** (Dune 3D): skicování a 3D jsou v jednom prostoru, vazby fungují i pro vysunutí. [github](https://github.com/dune3d/dune3d)
- **Časová osa** (Fusion 360): přehled historie a možnost vrátit se k libovolnému kroku.
- **Přímá manipulace a gesta** (Shapr3D, Plasticity): tahání ploch, kontextové widgety místo dialogů; Plasticity staví UX na zkratkách a výběrových režimech známých z Blenderu. [cgchannel](https://www.cgchannel.com/2023/12/nick-kallen-ships-plasticity-1-4/)
- **Synchronní modelování** (Solid Edge): kombinace historie a přímých úprav ploch; s OCCT realizovatelné jen omezeně.

### AI funkce v CAD – stav 2025–2026

Zoo (dříve KittyCAD) prošlo cestou od alfa verze Text-to-CAD, která generovala B-rep a STEP, ke konverzačnímu agentovi Zookeeper (leden 2026), který píše parametrický kód KCL. [zoo](https://zoo.dev/research/zookeeper) [zoo](https://zoo.dev/blog/introducing-text-to-cad) V březnu 2026 přibylo nahrávání obrázků a dokumentů (výkres v PDF/DXF → 3D model) a v květnu 2026 přepracovaný skicovací režim s přístupem k solveru vazeb. [zoo](https://zoo.dev/blog/whats-new-mar-2026) [texocad](https://blog.texocad.ai/glossary/kcl) Nezávislá recenze Leo AI (září 2026) ho hodnotí jako užitečný pro jednotlivé díly typu konzola, příruba nebo pouzdro, ale slabší pro sestavy, lícování a složité plochy, a upozorňuje, že neověřuje pevnost ani vyrobitelnost (Leo AI je zároveň konkurent, ber recenzi s rezervou). [engtechnica](https://engtechnica.com/zoo-turns-text-prompts-into-editable-cad-parts/) Pro tvou aplikaci z toho plyne: AI generuj vždy do čitelného receptu, nikdy přímo do geometrie, a výsledek nech uživatele zkontrolovat.

## Recommendations

1. **Začni cestou A:** naklonuj Macad|3D, nech Claude Code projekt sestavit a popsat architekturu do `CLAUDE.md`. Teprve pak se rozhodni mezi forkem (A1) a převzetím jen wrapperu (A2).
2. **Licence od prvního dne:** jen MIT/BSD/Apache/LGPL komponenty, LGPL knihovny jako samostatné DLL, žádný kód ze SolveSpace, Dune 3D ani GPL částí CGAL; CalculiX a Gmsh jen jako externí procesy. Veď si soubor `THIRD_PARTY_LICENSES` a do „O aplikaci" dej povinné upozornění na OCCT. [opencascade](https://dev.opencascade.org/content/open-cascade-technology-changes-its-license-gnu-lgpl)
3. **Model jako text:** JSON receptura prvků – umožní undo, git, testy i AI asistenta.
4. **Testy přes fyziku:** objem, těžiště a plocha jako automatická kontrola každé změny.
5. **Odlišení od konkurence:** neporážej Inventor v šíři funkcí; vyhraj v úzkém místě, které znáš z praxe – strojnické tabulky, normalizované díly, NDT vizualizace tloušťky stěn a svarů, AI asistent v češtině.
6. **Komerční jádro řeš až s reálnými zákazníky:** Parasolid nebo C3D jsou smysluplné jen s rozpočtem; C3D navíc pro jadernou energetiku zvaž z hlediska původu dodavatele.

## Caveats

- Časové odhady a hodnocení náročnosti jsou můj úsudek, ne naměřená data.
- Nepodařilo se ověřit, jak přesně Macad|3D vkládá OCCT viewer do WPF (WinForms host, D3DImage nebo HwndHost) ani jaký parser používá generátor wrapperu; ověř si to ve zdrojích (složka Source/).
- Licenci vlastního kódu NetOcc a jeho zralost jsem neověřil.
- Údaj o tom, že Manifold používá čísla s jednoduchou přesností, pochází z PR OpenSCADu z roku 2023 a mohl se změnit. [github](https://github.com/openscad/openscad/pull/4533)
- Ceny Parasolidu a ACIS nejsou veřejné; C3D ceny pocházejí z ceníku výrobce.
- Část informací o Zoo pochází z recenzí firem, které jsou samy v oboru AI CAD (Leo AI, TexoCAD) – ber je jako názory, ne nezávislé testy.
- Toto není právní rada; před komerčním vydáním si nech licence zkontrolovat.
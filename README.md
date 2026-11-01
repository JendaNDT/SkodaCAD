# ŠkodaCAD

Osobní parametrický 3D CAD postavený na jádře **Open CASCADE** (přes knihovnu
[build123d](https://github.com/gumyr/build123d)). Vyvíjený vibecodingem v Claude Code.

**Stav:** jádro + první okno pro Windows. Díl se popíše v čitelném souboru JSON
(parametry + seznam prvků), jádro z něj postaví přesné těleso, spočítá objem a hmotnost
a uloží exporty pro jiné CAD programy i 3D tisk. Okno ukáže díl ve 3D a dovolí měnit
parametry.

## Aplikace pro Windows

1. Stáhni **[SkodaCAD-windows.zip](https://github.com/JendaNDT/SkodaCAD/releases/latest/download/SkodaCAD-windows.zip)**
   (stránka [Releases](https://github.com/JendaNDT/SkodaCAD/releases), vydání „nejnovejsi“).
2. Rozbal ho (pravé tlačítko → *Extrahovat vše*).
3. Ve složce `SkodaCAD` spusť **`SkodaCAD.exe`**.
4. Windows může napsat *„Systém Windows ochránil váš počítač“* – aplikace není digitálně
   podepsaná. Klikni na *Další informace* → *Přesto spustit*.

Aplikace sestavuje GitHub automaticky po každé změně ve větvi `main`
(postup [.github/workflows/windows.yml](.github/workflows/windows.yml)).

## Aplikace pro macOS (Apple Silicon) – zkušební

Pro Mac s čipem M1–M4 a macOS 13 nebo novějším. Autor 20. 10. 2026 potvrdil
[ruční funkční průchod na Apple M4 / macOS 27.0.1](docs/p0-rucni-overeni-macos-2026-10-20.md)
u balíčku z PR #30. Širší kontroly Retiny, trackpadu a kompatibility zůstávají otevřené
([postup a seznam zkoušek](docs/ndt/08-navrh-macos.md)). Odkaz níže vede na vydání z main;
protokol se vztahuje ke konkrétnímu sestavení z PR.

1. Stáhni **[SkodaCAD-macos.zip](https://github.com/JendaNDT/SkodaCAD/releases/download/nejnovejsi-mac/SkodaCAD-macos.zip)**
   (vydání „nejnovejsi-mac“, označené jako předběžné).
2. Rozbal ho (dvojklik ve Finderu) a **SkodaCAD** přetáhni do složky *Aplikace*.
3. Při prvním spuštění macOS napíše, že aplikaci nejde ověřit – není podepsaná certifikátem
   Apple ani notarizovaná. Otevři *Nastavení systému → Soukromí a zabezpečení*, sjeď dolů
   a u SkodaCAD klikni na **Přesto otevřít** (od macOS 15 už nefunguje pravý klik → Otevřít).
   Kdyby to nešlo, v Terminálu: `xattr -dr com.apple.quarantine /Applications/SkodaCAD.app`.
4. Ovládání je stejné jako ve Windows, jen místo `Ctrl` používej **`Cmd` (⌘)**: `Cmd`+klik
   přidá plochu do výběru, `Cmd`+`Z` je Zpět. Na trackpadu posouváš pohled **`Shift` + tažením**,
   zoom dvěma prsty.
5. Nastavení, log (`skodacad.log`) a výchozí místo pro modely je složka **`SkodaCAD`** ve tvé
   domovské složce – stejně jako ve Windows.
6. Kdyby 3D nešlo spustit s grafickou kartou (virtuál, vzdálená plocha), aplikace kreslí
   softwarově – pomaleji, ale funguje. Kontrolu celé aplikace spustíš v Terminálu:
   `/Applications/SkodaCAD.app/Contents/MacOS/SkodaCAD --self-test ~/SkodaCAD/self-test.txt`
   (výsledek je v souboru `self-test.txt`, na konci „VÝSLEDEK: OK“).

AI asistent posílá model společnosti Anthropic **jen** po tvém dotazu v panelu *AI asistent*
a jen s vloženým API klíčem. Bez klíče (např. při prezentaci) z aplikace nic neodchází.

Mac sestavuje samostatný postup [.github/workflows/macos.yml](.github/workflows/macos.yml);
sestavení pro Windows se tím nemění.

### Nové hlavní okno (P7 – nativní prototyp)

Pás činností nahoře, strom dílu vlevo a jeden panel po celé výšce vpravo.
Pravý panel zvolíš v jeho hlavičce nebo přes **Zobrazení → Panely**. **F4**
přepíná editor, **F9** strom, **Ctrl+F1** (na Macu Cmd+F1) sbalí pás.
**Zobrazení → Obnovit rozložení** vrátí výchozí podobu; v menším okně skryje
strom, aby zůstal prostor pro 3D. **Zobrazení → Vzhled** přepíná světlý/tmavý
režim. Rozložení se pamatuje v `~/SkodaCAD/okno.json`, odděleně od dílu.

U vodítek vyber roh A–D a rukojeť 1/2. Pro změnu X/Y spusť **Upravit prvek**,
uprav široká pole v náhledu a stiskni **Potvrdit**. Podrobný rozsah prostředí:
[P7.2](docs/p7-2-nativni-prostredi.md).

[Ověření modelování desky od nuly](docs/p7-3-overeni-workflow-2026-11-01.md)
pokrývá parametry, vysunutí, čtyři průchozí otvory Ø6, R2 a historii. Hotový
recept je v **Příklady → deska_workflow**. V souřadnicích otvorů Enter přidává
řádek a Tab opouští pole a potvrzuje platný vstup.

Nové prvky se nejprve zobrazují v pravém panelu **Nový prvek · náhled**.
Uprav hodnoty, prohlédni výsledek a stiskni **Potvrdit**; celý nový prvek pak
vrátíš jedním krokem Zpět. **Zrušit** nebo Esc návrh zahodí. Hrany/plochy pro
příkaz z výběru označ před jeho spuštěním. Ve skicáři **Hotovo** dokončí obrys,
potom ještě potvrď náhled skici vpravo. Během náhledu lze ovládat pohled;
uložení, export a další změny počkají na ukončení příkazu.
[Podrobný postup a ověření P7.5](docs/p7-5-nahled-noveho-prvku.md).

Existující prvek otevři dvojklikem ve stromu nebo tlačítkem **Upravit prvek**
(Ctrl+E, na Macu Cmd+E). Panel **Úprava prvku · náhled** přepočítá i všechny
navazující prvky. **Potvrdit** přijme celou úpravu jako jeden krok Zpět;
**Zrušit** nebo Esc zachová původní díl. Běžný panel hodnot slouží k prohlížení.
Přidání či nahrazení hran vybraného prvku výběrem ve 3D také otevře tento náhled.
[Postup, ověření a meze P7.6](docs/p7-6-nahled-uprav-prvku.md).

### Ovládání

| Akce | Jak |
|---|---|
| Otáčení | levé tlačítko + táhnout |
| Posun | prostřední nebo pravé tlačítko + táhnout, nebo `Shift` + levé tlačítko + táhnout |
| Zoom | kolečko (ke kurzoru) |
| Výběr plochy / hrany | klik – popis (typ, obsah, průměr…) se ukáže dole ve stavovém řádku a **změří se** (panel *Měření* vpravo) |
| Více hran / ploch | `Ctrl`+klik (nebo `Shift`+klik) přidá nebo ubere – u dvou věcí se změří vzdálenost a úhel |
| Co s výběrem | pravé tlačítko (bez tažení): Zaoblit, Srazit, Skica na ploše, Skořepina… |
| Zrušit výběr | `Esc` |
| Celý díl | dvojklik nebo `F` |
| Pohledy | `0` izometrie, `1` zepředu, `3` zprava, `7` shora (s `Ctrl` opačná strana) |
| Změna parametru | přepiš hodnotu vlevo a stiskni Enter (číslo, `12,5` i výraz `D/2 + 5`) |
| Přepočítat | `F5` (pomalý přepočet jde zastavit tlačítkem dole vpravo) |

Neplatná hodnota parametru se zbarví červeně a model zůstane beze změny. Když některý
prvek nejde spočítat, ve stromu prvků se ukáže ✕ a česky proč.

**Přepočet na pozadí:** model se přepočítává v samostatném pomocném procesu, takže okno
nikdy nezamrzne – ani u pomalých prvků, jako je vymodelovaný závit. Trvá-li přepočet déle,
strom prvků zešedne (⏳), vlastnosti ukazují hodnoty z minulého stavu a dole běží
„Přepočítávám… N s“ s tlačítkem **Zastavit přepočet**. Zastavení vrátí model do posledního
spočítaného stavu (*Znovu* změnu vrátí a zkusí to znovu). Když během výpočtu změníš další
hodnotu, rozpočítaný přepočet se zahodí a hned se počítá ten nejnovější. Export a prvky
z výběru ve 3D počkají, až bude model spočítaný.

### Vlastní díl od nuly

1. **Soubor → Nový**, vlevo nahoře vyplň název a materiál.
2. **Přidat prvek → Skica**: na rovině XY vznikne obdélník 40 × 30. Vpravo v panelu
   *Úprava prvku* změň rozměry, přidej další tvary (*Přidat tvar*) – otvor je tvar
   s režimem *odečíst*.
3. **Přidat prvek → Vysunutí**: ze skici vznikne těleso, vpravo nastav vzdálenost.
4. Díra nebo výstupek: další **Skica** se sama položí na horní plochu dílu (kružnice Ø10),
   pak **Vysunutí** s operací *odebrat materiál* a případně *Řez skrz celý díl*.
5. **Zaoblení / Sražení kliknutím**: klikni ve 3D na hranu (další s `Ctrl`), pravé tlačítko →
   *Zaoblit vybrané hrany*. Program si hranu nezapamatuje číslem, ale významem („hrana mezi
   přední a pravou plochou“, „kružnice R3 na horní ploše“) – výběr tak platí i po změně
   rozměrů. Hrany vybraného zaoblení svítí ve 3D růžově; další přidáš přes pravé tlačítko →
   *Přidat vybrané hrany do…*. Hrany jde vybrat i ručně ve formuláři (na ploše, rovnoběžné…).
6. **Skica na ploše kliknutím**: klikni na plochu (i dno kapsy, schod, **šikmou** plochu
   sražení nebo **válec**), pravé tlačítko → *Skica na vybrané ploše* – kružnice Ø10 vznikne
   v místě kliknutí. Na zakřivené ploše (válec, kužel, koule) leží skica na rovině, která se
   plochy v místě kliknutí dotýká (**tečná rovina**) – tak vznikne třeba drážka pro pero nebo
   plocha na hřídeli. U šikmé a zakřivené plochy je počátek skici v místě kliknutí a osa X
   míří podél osy válce (jinak vodorovně po ploše).
7. **Díra podle tabulek kliknutím**: klikni na plochu (i šikmou nebo válcovou – příčná díra do
   hřídele) tam, kde má díra být, pravé
   tlačítko → *Díra na vybrané ploše*. Vpravo vyber druh (závitová, průchozí, zahloubení,
   3D tisk) a velikost M2–M30. Další díru stejného prvku přidáš kliknutím na plochu a
   *Přidat díru v místě kliknutí*. Viz [Díry](#díry-podle-strojnických-tabulek).
8. **Skicář (obrys z čar s vazbami)**: *Přidat prvek → Skica – nakreslit obrys…* (nebo u tvaru
   „Obrys z čar“ tlačítko *Upravit ve skicáři…*). Viz [Skicář](#skicář) níže.
9. **+ Parametr** vytvoří pojmenovaný rozměr; jeho název pak můžeš napsat do kteréhokoli
   pole (např. `sirka` nebo `sirka/2 - 5`).

### Skicář

1. Nástroj **Úsečka** (`L`): klikej body obrysu. Klik na existující bod čáry napojí, klik do
   počátku (zelený kroužek) obrys k počátku připne. Skoro vodorovná/svislá čára dostane vazbu
   sama. Konec řetězu: `Esc` nebo pravé tlačítko. **Oblouk** (`A`): začátek, konec a bod,
   kudy má vést. **Kružnice** (`R`): střed a bod na obvodu – střed na existujícím bodě (třeba
   středu oblouku) ji udělá soustřednou, obvod na existujícím bodě ho na kružnici připne.
2. Nástroj **Výběr** (`S`): klikni na čáru nebo bod (`Ctrl` = přidat další) a přidej vazbu
   tlačítkem vlevo – *Vodorovně, Svisle, Rovnoběžně, Kolmo, Tečně, Stejně velké, Na bodě/čáře,
   Uprostřed, Soustředně, Souměrně, Pevný bod*. Tažením obvodu kružnice měníš její velikost.
3. **Kóta…** (`D`): úsečka = délka, oblouk = poloměr, kružnice = průměr (Ø), dva body nebo
   bod a čára = vzdálenost, dvě úsečky = úhel. Hodnota může být číslo i výraz s parametrem
   (`sirka`, `D/2`) – obrys se pak mění s parametrem.
4. Dole vpravo je vidět, kolik rozměrů **zbývá určit** (modrý obrys jde ještě táhnout myší),
   nebo **✓ plně určeno** (černý obrys). Vazby, které si odporují, jsou **červeně** – smaž je
   (*Smazat vazbu*) nebo dej *Zpět* (`Ctrl+Z`).
5. **Pomocná čára** (`G`) se účastní vazeb, ale není součástí obrysu (např. osa souměrnosti).
6. **Hotovo** uloží obrys do modelu (jako jeden krok pro Zpět v hlavním okně). Obrys pak vysuň
   nebo orotuj; s režimem *odečíst* je z něj otvor.

**Díry a vazby mezi tvary:** jeden obrys smí mít víc uzavřených smyček. Smyčka (nebo kružnice)
uvnitř jiné je **díra**, smyčka uvnitř díry je zase materiál. Díky tomu jde díru navázat na
obrys: *Soustředně* s obloukem, *Tečně* (kružnice se dotkne čáry, oblouku nebo jiné
kružnice), *Souměrně* podle osy, *Stejně velké* (i kružnice s obloukem), *Na bodě/čáře* (bod
na obvodu) nebo kótou vzdálenosti středu od hrany. Smyčky se nesmí křížit – skicář to hned
hlásí červeně.

Ukázky: *Soubor → Otevřít ukázku → paka* – změň `L` nebo `R` a obrys páky se přepočítá.
*prilozka* – příložka s pěti otvory navázanými na obrys; změň `L` nebo `B` a otvory jdou s ní.

**Promítnutí hran dílu:** když skica leží na dílu (třeba na horní ploše), skicář ukáže hrany
dílu pod ní šedě. Nástroj **Promítnout** (`U`) – klik na šedou hranu ji převezme jako pevnou
**fialovou** čáru (úsečku, kružnici díry, oblouk zaoblení). K ní jde dát vazby a kóty (bod na
hraně, vzdálenost od hrany, soustředně s dírou, tečně, napojení na roh – fialové body se
přichytávají). **Převzít do obrysu** (`W`) z vybraných fialových hran udělá skutečný obrys
navázaný na díl (třeba výstupek přesně podle plochy). Když se díl změní (parametr, posunutá
díra), skica jde s ním. Promítnout jde úsečka a kružnice či oblouk rovnoběžné se skicou.

Ukázka *sloupky* – deska se 4 dírami M3 a distančními sloupky pro plošný spoj: sloupky jsou
soustředné s promítnutými dírami; změň rozteč `rx` nebo `ry` a sloupky jdou s dírami.

### Díry podle strojnických tabulek

Ukázka: *Soubor → Otevřít ukázku → deska*. Závit je ve výchozím stavu jen **vyznačený**
(jako v běžných CAD): díra má průměr vrtáku pod závit a u prvku je zapsáno „M8 závit,
hl. 12“. Do STEP/STL jde jen díra, ne závit.

**Vymodelovaný závit pro 3D tisk:** u závitové díry zaškrtni *Vymodelovat závit (3D tisk)*.
Vznikne skutečná šroubovice se základním profilem ISO 68-1 (úhel 60°, malý průměr
D1 = D − 1,0825·P) zvětšená o *vůli pro tisk* (výchozí 0,2 mm na průměru – když šroub
nejde zašroubovat, zvětši ji). Díra má ploché dno, závit vede po celé hloubce. Závit je
složený z drobných plošek (nejvýš 0,05 mm od přesného tvaru – pod rozlišením tiskárny),
protože s hladkou šroubovicí jádro OCCT neumí spolehlivě řezat. Přepočet trvá pár sekund
(M3 nejdéle – nejvíc závitů); pro tisk doporučeno od M6.

| Druh (`kind`) | Co vznikne | Tabulka | Velikosti |
|---|---|---|---|
| `tapped` – závitová | vrták pod závit, slepá díra končí špičkou vrtáku 118° | ISO 2306 (vrták ≈ d − stoupání ISO 261) | M2–M30 |
| `clearance` – průchozí | díra pro šroub, řada jemná/střední/hrubá | ISO 273 | M2–M30 |
| `counterbore` – válcové zahloubení | pro imbus s válcovou hlavou ISO 4762 | DIN 974-1 | M3–M24 |
| `countersink` – kuželové 90° | pro zápustnou hlavu ISO 10642 | DIN 74 tvar F (Würth) | M3–M12 |
| `insert` – 3D tisk | díra pro zálisnou (zatavovací) matici, ploché dno | doporučení ruthex/Accu | M2–M6 |
| `plastic` – 3D tisk | šroub přímo do plastu, ploché dno | vrták pod závit (norma není) | M2–M30 |

Příklad: M6 → vrták Ø5,0; průchozí Ø6,4 / 6,6 / 7,0; zahloubení Ø11 × 6,4; kuželové Ø13,7.
U 3D tisku se zdroje liší o desetiny mm a záleží na tiskárně – vytiskni zkušební kousek
a případně zadej *Vlastní průměr*. Tabulky a zdroje jsou v
[src/skodacad/holes.py](src/skodacad/holes.py) (normy samotné jsou placené; hodnoty jsou
ověřené porovnáním více zdrojů – u průchozí díry M16 jeden zdroj uvádí 18 místo 17,5).

### Měření

Ukázka: *Soubor → Otevřít ukázku → trubka* (trubka s korozní jamkou a uloženými měřeními
tloušťky stěny). Měří se samo – stačí kliknout, výsledky jsou vpravo v panelu **Měření**.

| Vybráno | Co se změří |
|---|---|
| jedna plocha | **tloušťka stěny v místě kliknutí** (jako ultrazvukový tloušťkoměr: kolmo do materiálu až k protější ploše), u válce a koule průměr, obsah plochy |
| jedna hrana | délka, u kružnice průměr, u oblouku poloměr |
| dvě rovnoběžné plochy | jejich kolmá vzdálenost (tloušťka desky, šířka drážky) |
| dvě díry (válce nebo jejich hrany) | **rozteč os**, u hran i vzdálenost středů |
| díra a plocha | vzdálenost osy díry od plochy (je-li s ní rovnoběžná) |
| dvě plochy / hrany pod úhlem | úhel mezi nimi (sražení 45°, šikmá hrana a plocha …) |
| vždy u dvou věcí | nejkratší vzdálenost |

* Vybraný řádek se ve 3D ukáže jako **zelená čára** s hodnotou (odkud kam se měřilo).
  Hlavní hodnota dvou věcí je i dole ve stavovém řádku.
* **Uložit do modelu** (nebo pravé tlačítko → *Uložit měření do modelu*) uloží vybraný řádek
  do souboru. Uložené měření se **přepočítá při každé změně** modelu – změníš tloušťku
  stěny a hned vidíš novou zbytkovou tloušťku. Přejmenovat (i dvojklikem) a smazat jde pod
  seznamem *Uložená měření*, Zpět/Znovu funguje i tady.
* Uložené měření si plochy a hrany pamatuje **významem**, ne číslem: plochu bodem, směrem,
  druhem a poloměrem (díra se najde, i když se posune), hranu jako zaoblení. Když plocha
  zmizí, měření se zbarví červeně a napíše proč.
* Měří se vždy jedna nebo dvě věci; u víc vybraných se nic nezměří.

### Pracovní výkres

V panelu **Měření → Příprava kót výkresu** přidej podporované kóty, zvol list a měřítko.
List a měřítko se uloží s modelem (jde je vrátit Zpět) a po otevření souboru zůstanou;
náhled i export je berou z modelu.
Tlačítkem **Popisové pole…** zadej číslo výkresu, revizi, autora a datum; název dílu
a materiál se přebírají z modelu. Údaje se uloží s výkresem a objeví se v náhledu i exportu.
U vybrané kóty lze nastavit pohled, stranu a odstup. Tlačítkem **Nastavit toleranci**
zadej horní (kladnou nebo nulovou) a dolní (zápornou nebo nulovou) odchylku v mm;
například +0,1 a −0,1 se zobrazí jako ±0,1. Tolerance lze odebrat samostatným
tlačítkem. Ukládají se s výkresem a zůstávají stejné při změně jmenovitého rozměru.
Soubor s tolerancí vyžaduje aktuální verzi aplikace (formát 26). Pro řez A–A zvol osu, polohu
v milimetrech a případně otočení; nastavení potvrď tlačítkem **Nastavit řez**. Náhled
ukáže pohledy, kóty, rovinu řezu a šrafy; pokud se obsah nevejde, zvol větší list
nebo menší měřítko, nebo skryj pohled, který nepotřebuješ.

Zaškrtávátky **Pohledy: Zepředu / Shora / Zprava** zvolíš, které pohledy výkres ukáže;
aspoň jeden zůstane vždy. Kóta bez vlastního umístění se ze skrytého pohledu přesune do
jiného zobrazeného pohledu, kde ji lze nakreslit (hodnota se nemění); kóta umístěná do
skrytého pohledu a průměr otvoru, který je kružnicí jen ve skrytém pohledu, se nevykreslí
a výkres to oznámí. Rovina řezu se označuje v pohledu shora (řez X a Y) nebo zepředu
(řez Z) – ten musí zůstat zobrazený. Soubor se skrytým pohledem vyžaduje aktuální verzi
aplikace (formát 28).

Tlačítko **Export PDF/DXF…** uloží pracovní výkres. Neplatné kóty, zastaralý model
nebo nepodporovanou křivku PDF aplikace oznámí a export zastaví. Při tisku nastav
skutečnou velikost a změř kontrolní úsečku 50 mm. Výkres před výrobou zkontroluj:
program upozorní na možná překrytí textů, kótovacích čar a některých hran, ale tato
kontrola není úplná. Upozornění je i v exportovaném výkresu. Zatím chybí některé
druhy kót a toleranční značky uložení. Fyzický tisk a otevření DXF v jiné CAD
aplikaci ještě nebyly ověřeny.

### Sestavy

Sestava skládá hotové díly do poloh – krabička, víčko, šrouby, deska elektroniky… Každý díl
zůstává ve svém souboru, sestava na něj jen odkazuje a **nikdy ho nepřepíše**.

- *Soubor → Nová sestava…* se nejdřív zeptá, kam sestavu uložit (cesty k dílům se počítají
  od její složky – celou složku projektu pak jde přenést i mezi Windows a Macem).
  *Soubor → Otevřít…* pozná sestavu sama a otevře ji ve **vlastním okně**.
- *Vložit díl…* (Ctrl+I) přidá díl nebo jinou sestavu. První vložený díl je **pevný**.
  Stejný díl jde vložit vícekrát (čtyři nožičky = jeden soubor, čtyři polohy).
- Komponentu vyber ve stromu nebo kliknutím ve 3D. Vpravo zadáš **posun** v mm a **otočení**
  ve stupních (kolem os sestavy nejdřív X, pak Y, pak Z; čísla i výrazy s parametry sestavy),
  tlačítka **±90°** otočí díl kolem osy vedené jeho počátkem. *Použít* = jeden krok Zpět.
- Chybějící nebo poškozený soubor dílu je ve stromu červeně „✕ chybí“ s důvodem; sestava se
  přesto otevře a záznam nesmaže. *Najít soubor…* ho přesměruje (u dílu s jiným receptem se
  nejdřív zeptá). Vpravo dole je počet komponent, objem a hmotnost; neúplná sestava to řekne.
- *Otevřít díl* otevře soubor dílu v hlavním okně. Po uložení a návratu do okna sestavy se
  změna projeví sama (nebo F5 *Načíst díly znovu*); když se díl od posledního uložení sestavy
  změnil, sestava upozorní „zkontroluj polohy“.
- Ukázka: *Soubor → Otevřít ukázku → Sestavy → krabicka_s_vickem* (krabička, víčko otočené
  o 180° lemem dolů, čtyři nožičky). *Uložit* ukázky se zeptá kam a zkopíruje k sestavě
  i její díly (složka `dily/`) – vznikne samostatný projekt, ukázka zůstane beze změny.

**Vazby** – místo čísel řekneš, jak díly k sobě patří, a aplikace polohu dopočítá:

- Klikni ve 3D na plochu první komponenty, **s Ctrl** na plochu druhé a dej *Přidat vazbu…*
  (Ctrl+L). U dvou rovinných ploch vybereš **dotyk** (plochy na sobě), **zarovnání** (v jedné
  rovině) nebo **vzdálenost** (dotyk s mezerou v mm, nabídne se dnešní vzdálenost; jde i výraz
  s parametry sestavy), u dvou válcových ploch (díra, čep) je to **souosost**.
- Vazby jsou ve stromu pod komponentami se stavem (✓ splněna, ✕ ve sporu, ✕ odkaz nenalezen).
  Vybranou vazbu jde přejmenovat, u vzdálenosti změnit hodnotu (*Použít vazbu*) a smazat
  (*Smazat vazbu* nebo Delete). Každá změna je jeden krok Zpět.
- U komponenty je ve stromu vidět, co jí vazby nechaly: **plně určená**, **volná: 2 posuny,
  1 otočení**, **ve sporu**. Volné pohyby zůstanou, jak byly; ruční posun nebo ±90° vázané
  komponenty se přijme a vazby ji hned srovnají (změní se jen to, co je volné).
- Vazba, která by odporovala ostatním, se **nepřijme** – okno řekne, které vazby si odporují,
  a sestava zůstane, jak byla. Pevná komponenta a komponenta s polohou zadanou výrazem se
  nehýbou nikdy (u výrazu poradí „nahraď výraz číslem“).
- Když se díl změní (vyšší krabička), polohy se po načtení samy přepočítají, sestava dostane
  hvězdičku „neuloženo“ a okno napíše, které polohy se změnily. Pokud se vazby po změně dílu
  splnit nedají, polohy zůstanou a vazby jsou červeně „ve sporu“.
- Ukázka: *Otevřít ukázku → Sestavy → krabicka_s_vazbami* – víčko určují tři vazby, nožičky
  se dotýkají dna. Přepiš u vazby *Víčko na okraji* vzdálenost `mezera` třeba na 15 a víčko
  se nadzvedne.

**Kontrola sestavy** – panel dole v okně sestavy (záložky *Kolize a vůle* a *Kusovník*):

- *Zkontrolovat kolize a vůle* (F7, i v nabídce *Kontrola*) projde každou dvojici kopií dílů
  (i v podsestavách) a počítá na pozadí – okno mezitím jde používat, *Zastavit* výpočet
  ukončí. **Kolize** = díly se prostupují víc než 0,001 mm³ (tabulka ukáže objem průniku),
  **malá vůle** = díly jsou k sobě blíž než *Mez vůle* (výchozí 0,5 mm), ale nedotýkají se.
  Dotyk (víčko na krabičce) není vada. Když jádro průnik nespočítá, nález je „nelze ověřit“ –
  nikdy „bez kolize“.
- Klik na nález zvýrazní obě kopie a červenou kuličkou ukáže střed průniku.
- **Přijmout kolizi…** zapíše kolizi, která je v pořádku (šroub v díře pod závit, nalisovaný
  čep), s poznámkou proč – jeden krok Zpět. Přijatá kolize se po změně dílu, která její
  objem změní o víc než 1 %, ukáže znovu jako kolize. *Zrušit přijetí* záznam smaže.
- Výsledek kontroly je jen pohled: po změně sestavy (poloha, díl, mez vůle) neplatí a je
  třeba ji pustit znovu.
- Záložka **Kusovník** je rozbalený (i díly z podsestav), jeden řádek = jeden soubor dílu
  s počtem kusů, materiálem, hmotností a id komponent; *Uložit kusovník CSV…* (středník,
  česky čitelné v Excelu).
- *Soubor → Exportovat STEP…* uloží sestavu do STEP se stromem: díl jednou, jeho kopie
  s polohami a jmény podle id (bez diakritiky – jiné CADy češtinu často rozbijí).
- Kusovník do souboru a export STEP jdou jen z **úplné** sestavy.
- V sestavě se **nepočítá NDT** – studie dílu platí jen pro samotný díl (sousední díl může
  sondě, jhu nebo zdroji zavazet); kusovník jen ukáže, kolik studií díl má.
- Ukázka: *Otevřít ukázku → Sestavy → deska_se_sroubem* – šroub M3 × 10 v díře pod závit
  (vrták 2,5 mm) prostupuje deskou 12,959 mm³; kolize je přijatá s poznámkou „závit M3“.

Zatím bez úhlových a tečných vazeb a tažení vázaných dílů myší.

### Mapa tloušťky stěny (NDT)

Ukázka: *Soubor → Otevřít ukázku → trubka* a pak **Model → Mapa tloušťky stěny** (klávesa
`M` nebo tlačítko v horní liště). Celý povrch dílu se obarví podle tloušťky stěny:

| Barva | Význam |
|---|---|
| červená → žlutá → zelená → modrá | od nejtenčího místa po horní mez škály (výchozí = nejčastější tloušťka dílu, tedy jmenovitá stěna); tlustší místa jsou modrá |
| fialová | pod **minimální dovolenou tloušťkou** (zadáš ji v panelu) |
| šedá | tloušťku tu nejde jednoznačně změřit – okraj jamky, drážky nebo ostrá hrana |

* Tloušťka se měří jako ultrazvukovým tloušťkoměrem: v hustě rozmístěných bodech po celém
  povrchu kolmo do materiálu až k protější stěně. Platí jen stěna, která k paprsku stojí
  zhruba kolmo („koncové echo“) – jinak je místo šedé, ne s nesmyslně malým číslem.
* Nejtenčí místo má ve 3D fialovou značku s hodnotou. Klikem kamkoli na mapu změříš přesnou
  tloušťku v tom bodě (stavový řádek a panel *Měření*).
* Panel **Mapa tloušťky** (záložka vedle *Měření*): minimální tloušťka, krok bodů (prázdné
  = automaticky, asi 30 000 bodů) a horní mez škály. Nastavení se **ukládá do modelu**
  (Zpět/Znovu funguje). Pod nimi legenda a souhrn: nejtenčí místo se souřadnicemi,
  nejčastější tloušťka, kolik procent povrchu je pod minimem.
* Zapnutá mapa se **přepočítá s modelem** – změníš tloušťku stěny nebo hloubku jamky a mapa
  se na pozadí spočítá znovu (okno nezamrzne, výpočet trvá pár sekund).
* **Export CSV…** uloží body mapy (x, y, z, tloušťka, pod minimem) pro Excel – se
  středníkem a desetinnou čárkou, jak je zvyklý český Excel. Hodí se k porovnání
  s naměřenými hodnotami z ultrazvuku.
* Pod mapou je díl jen v obrysech hran, aby byly vidět barvy.

### Řez modelem

**Model → Řez modelem** (klávesa `R` nebo tlačítko v horní liště) díl přesně rozřízne rovinou
a ukáže jednu polovinu – vidíš dovnitř (stěny, díry, závity, jamky). Model se přitom
**nemění**, řez je jen pohled a do souboru se neukládá.

* Panel **Řez** (záložka vedle *Měření* a *Mapy tloušťky*):
  * **Rovina** – kolmo na osu X, Y nebo Z (výchozí podélně kolmo na Y, uprostřed dílu),
    nebo **rovnoběžně s vybranou plochou**: klikni na rovinnou plochu (i šikmou) a zvol tuto
    možnost (nebo pravé tlačítko → *Řez rovnoběžně s vybranou plochou*) – posuvník pak
    posouvá řez do hloubky pod plochu.
  * **Poloha** posuvníkem (řez se spočítá po puštění) nebo přesně číslem v mm.
  * **Otočit stranu** – zbude druhá polovina.
  * **Export DXF/SVG…** – obrys plochy řezu jako 2D výkres: DXF pro jiné CADy či laser,
    SVG (vyplněný řez) jako obrázek do protokolu.
* Plochy řezu jsou **cihlové** a pod panelem je jejich obsah (průřez dílu v té rovině).
* Na rozříznutý díl jde klikat jako jindy: měření (i na ploše řezu – vzdálenosti, tloušťka),
  zaoblení, sražení, skica a díra na ploše. Prvek se přidá na celý díl. Co vzniklo jen řezem
  (plocha řezu), na díl použít ani uložit nejde – okno to česky řekne.
* Se zapnutou **mapou tloušťky** zůstane barevná i rozříznutá – mapa se ořízne přesně
  rovinou řezu a uvidíš i vnitřek (třeba korozi uvnitř trubky).

### NDT studie (předběžné posouzení)

Začátek modulu NDT podle plánu v [docs/ndt/](docs/ndt/) (etapy 00 a 01). **NDT studie** je
záznam v modelu: metoda (**UT, PT, MT, RT**), **kontrolovaná oblast** (plochy dílu), poznámka
a ověření. Zatím se nic nepočítá (paprsek, sonda a pokrytí přijdou v dalších etapách) – studie
ale hlídá, jestli ještě platí pro aktuální díl. Díl samotný nikdy nemění.

> Předběžné posouzení proveditelnosti NDT. Nenahrazuje kvalifikovaný postup, normové
> vyhodnocení ani reálnou kontrolu.

**UT je závazně vymezené** ([docs/ndt/04-zavazne-vymezeni-ut.md](docs/ndt/04-zavazne-vymezeni-ut.md),
má přednost před starším plánem): program posuzuje jen **přístupnost UT sondy** (jde přiložit
a posouvat bez kolize?) a **geometrické pokrytí** kontrolované oblasti – nikdy prozvučitelnost
materiálu (útlum, struktura, akustická vazba) ani detekovatelnost vad. V okně (skupina
*Přístupnost UT sondy*) i ve výpisech příkazové řádky je povinné upozornění:

> ŠkodaCAD provádí pouze geometrické posouzení přístupnosti ultrazvukové sondy a pokrytí
> kontrolované oblasti na základě zjednodušeného modelu ultrazvukového svazku. Nevyhodnocuje
> fyzikální prozvučitelnost materiálu ani detekovatelnost vad. Výsledky nenahrazují
> kvalifikovaný NDT postup ani odborné posouzení.

* **Referenční díly:** *Soubor → Otevřít ukázku → NDT – referenční díly* – deska, blok
  s kapsou, deska se žebrem, otvor, trubka, tupý svar V, koutový svar a obtížný přístup.
  Každý má ukázkovou studii; ručně spočítané očekávané výsledky (půlkroky, mezní úhly, vůle
  sondy) jsou v [docs/ndt/05-referencni-dily.md](docs/ndt/05-referencni-dily.md).
* **Panel NDT** (záložka vedle *Měření*, nabídka *NDT*): vyber ve 3D plochy kontrolované
  oblasti (Ctrl+klik přidá další), zvol metodu a **Nová NDT studie z výběru** (i pravým
  tlačítkem → *Z výběru ve 3D*). Klik na studii v seznamu oblast ve 3D zvýrazní.
* Stav studie se počítá při každé změně modelu:

| Stav | Kdy |
|---|---|
| ✓ **platná** | díl je stejný jako při nastavení studie a všechny plochy oblasti se našly |
| ⚠ **zastaralá** | díl se od nastavení změnil (parametr, prvek, materiál) – u plochy, která se posunula, i o kolik; zkontroluj a dej **Potvrdit pro aktuální díl** |
| ⚠ **neúplná** | chybí kontrolovaná oblast – vyber plochy a dej **Oblast z výběru** |
| ✕ **neplatná vazba** | plocha oblasti na dílu už není (nebo díl nejde postavit) |

* Pozná se to podle **otisku dílu** – kontrolního součtu parametrů, prvků a materiálu.
  Přejmenování prvku se nepočítá, posunutá díra ano (i když objem zůstane stejný).
  Přejmenování studie zastaralou studii neopraví – jen *Potvrdit*.
* **Ověřit…** zapíše, kdo studii odborně ověřil a kdy. Ověření platí jen pro díl, pro který
  se dalo – po změně dílu se ukáže „ověření neplatí“. Změna metody nebo oblasti ho smaže.
* Každá úprava studie je jeden krok **Zpět**; změníš tloušťku → studie zastaralá → Ctrl+Z →
  zase platná.
* **Geometrické jádro NDT** (etapa 02, zatím bez okna): průchod přímky dílem (úseky
  v materiálu, úhly dopadu), směr a zakřivení plochy, bod uvnitř/vně, viditelnost a kolize
  tělesa (budoucí sonda) s dílem. Hraniční případy – přímka po povrchu, přes hranu nebo
  tečně – jsou **nejisté** s vysvětlením a nikdy se nezapočítají jako materiál. Vyzkoušet
  jde příkazem `skodacad paprsek` (viz *Příkazová řádka*).
* **Virtuální sonda, geometrický paprsek UT a ruční pohyb sondy** (etapy 03 až 05, milník M1): ve
  skupině *Přístupnost UT sondy* v panelu NDT nastavíš sondu
  (*Sonda…* – přímá Ø D × výška, nebo úhlová délka × šířka × výška s výstupním bodem od čela,
  úhlem paprsku v materiálu $\beta$ [°], počtem odrazů v dílu, dovolenou mezerou pod sondou
  a manipulační rezervou; uloží se do studie). Klikni ve 3D na plochu
  a dej **Přiložit sondu sem** (nebo zapni **Jezdit sondou myší**, případně kdykoli drž `Alt` +
  levé tlačítko myši a táhni po povrchu dílu): sonda i lomená dráha osy paprsku v dílu (včetně
  odrazu od stěn) se nakreslí **zeleně** (přiloženo), **oranžově** (málo místa, nedosedá,
  přesahuje přes okraj či otvor) nebo **červeně** (koliduje) a pod ní je vysvětlení s čísly
  (mezera, průnik v mm³, volno k překážkám, ramena paprsku v materiálu, půlkrok, celý krok a
  jistota).
  * **Natočení a krokování:** *Směr paprsku [°]* (nebo kolečko myši při zapnutém *Jezdit sondou
    myší* / s podrženým `Alt`) sondu natočí po 15° (0° = osa +X, 90° = +Y). Tlačítka **◀ / ▶**
    posouvají přiloženou sondu po ploše o zvolený *Krok [mm]* dopředu ve směru paprsku a dozadu.
  * **Projet čáru a posuvník:** tlačítko **Projet čáru** zkontroluje přímku zvolené délky
    (*Délka čáry [mm]*) po 1 mm ve směru paprsku, vypíše souhrn (*„Volně: 0–5 mm. První potíž
    po 6 mm: Koliduje.“*) a zpřístupní posuvník, kterým lze sondu po čáře plynule posouvat.
  * *Odebrat sondu* ji schová. Přiložení, posuv i dráha paprsku jsou jen pohled (vidět i
    v zapnutém *Řezu modelem*) – do souboru se neukládají a po změně dílu se přepočítají.
* Sonda vždy dosedá kontaktní plochou do tečné roviny. Mezera pod ní se měří přesně (na trubce
  Ø 114,3 dá přímá sonda Ø 20 mezeru 0,88 mm → nedosedá; výchozí mez 0,5 mm odpovídá
  EN ISO 17640). Vůle se počítá jen k překážkám **nad** rovinou přiložení. Lom podle Snellova
  zákona (`--snell ALFA,C1,C2`) se počítá jen s výslovně zadanými rychlostmi.
* **Mapa geometrického pokrytí UT (etapa 06):** vyber cílové plochy jako oblast platné UT
  studie, nastav sondu a přilož ji na pojezdovou plochu. V panelu NDT zvol *Po ploše přiložení*
  nebo *Z přímé dráhy*, krok v mm a **Spočítat pokrytí**. Přímá dráha používá *Délku čáry*.
  Výpočet běží na pozadí, tlačítkem *Zastavit přepočet* jej lze přerušit. Barvy plošek:
  zelená = geometricky pokryto, červená = geometricky nepokryto, žlutá = nelze spolehlivě
  vyhodnotit. Souhrn obsahuje podíly v % i mm², počet poloh, krok a toleranci. **Export CSV…**
  uloží vzorky, první zasahující rameno, délku dráhy a předpoklady. **Skrýt mapu** obnoví běžný
  pohled. Při zobrazení pokrytí má tato mapa přednost před mapou tloušťky; řez ji ořízne.
  Po změně dílu, studie, sondy či přiložení výsledek zanikne; do JSON se neukládá (verze 15).
  Numerická tolerance sama neospravedlňuje kolidující polohu sondy: na rovinném pojezdu se
  mezilehlé polohy znovu ověřují. Procento je geometrický podíl, nikoli pravděpodobnost nálezu
  vady. Na ploše, kde sonda stojí, se nepočítá místo, odkud paprsek jen vychází (první
  rameno); odražený paprsek, který se na plochu vrátí (celý krok), se počítá. Krok zjemni
  a porovnej výsledky; u bodových dotazů jde o podíl bodů, nikoli plochu.
  Zaškrtnuté **Ověřit citlivost na krok** (výchozí, výpočet trvá zhruba o polovinu déle)
  nebo `--konvergence` porovná krok a 2× krok a nahoře v souhrnu napíše zeleně nízkou
  citlivost, nebo oranžově „Výsledek je citlivý na krok – zjemni krok“. Hrubý běh hledá
  s automatickou tolerancí svých kroků (aspoň s tolerancí jemného běhu), jinak by část
  paprsků jen nenašel. Výslovně zadaná tolerance menší než krok × 0,71 (po čáře × 0,6)
  dostane v souhrnu upozornění.

  Příklady příkazové řádky (bez změny modelu):

  ```powershell
  python -m skodacad pokryti examples/ndt/deska.json --plocha 0,0,20 --prima 10 --cil-plocha 0,0,0 --krok 5 --konvergence --csv pokryti.csv
  python -m skodacad pokryti examples/ndt/zebro.json --plocha 60,0,20 --cil 0,0,0 --sklon 45 --smer 180 --odrazy 0 --rezim line --delka 50 --krok 2
  ```
* **Svar a cílový objem v okně (etapa 07C):** v panelu NDT tlačítko **Cílový objem…** otevře
  editor: *Tupý svar V*, *Koutový svar* nebo *Obecný hranol*, počátek X/Y/Z, směr podél a
  napříč (±X/±Y/±Z; šikmý směr ze souboru zůstane), délka a rozměry. Vedle je nákres průřezu
  a zadaný objem ze vzorce, **Zkontrolovat v dílu** spočítá účinný objem v materiálu bez
  změny modelu. *Podle vybrané hrany* převezme směr a délku z rovné hrany vybrané ve 3D.
  Cíl se ve 3D ukáže průhledně modře (i skrz díl). U objemového cíle má mapa pokrytí navíc
  **krok cíle** (výchozí šestina menšího rozměru průřezu, u 12mm V svaru 2,5 mm; pojezd
  5 mm), toleranci zachycení (automaticky) a zapnuté
  **Ověřit citlivost na krok**; před spuštěním je vidět odhad (buňky, polohy sondy). Výsledek:
  tučná procenta tří stavů v mm³, citlivost nahlas (oranžově „zjemni krok“), barevný povrch
  cíle a tlačítko **Průřez svarem** – řez kolmo na osu cíle, posuvník v panelu *Řez* jede
  podél svaru. Šedá barva = *nerozlišeno v kresbě* (buňka s více kusy), čísla to nemění.
  Ukázky: *Soubor → Otevřít ukázku → NDT – cílové objemy*.
* **Knihovna sond a materiálů (etapa 08):** v dialogu **Sonda…** vyber *Profil* (obecné
  profily nebo *Moje sondy*); u každé hodnoty je vidět původ (obecný profil / zadáno ručně),
  u výstupního bodu a úhlu jde zaškrtnout **změřeno** (na kalibračním bloku). Dál *Úhel platí
  v materiálu*, jen informativní frekvence a průměr měniče, *Zdroj údajů*, pomůcka **Úhel ze
  Snellova zákona** (α, c₁, c₂ zadáš sám) a **Uložit do Mých sond…**. V panelu NDT je pod
  sondou **Materiál pro UT**; když úhel sondy platí v jiném materiálu, oranžové upozornění
  ukáže přepočtený úhel a tlačítko **Přepočítat úhel** ho použije (jeden krok Zpět).
  *Použít materiál dílu* zvolí profil podle materiálu dílu. V příkazové řádce:
  `skodacad sonda MODEL --bod X,Y,Z --profil uhlova-standardni-70 --material-ut hliník` vybere
  obecný profil sondy (přímá Ø 10 / Ø 20, úhlová malá / standardní / velká × 45° / 60° / 70°
  v oceli) a materiál pro UT (ocel, nerez, hliník, měď, mosaz – orientační rychlosti zvuku
  ze dvou zdrojů; litina a titan zatím chybí). Když úhel sondy platí v jiném materiálu, výpis
  upozorní a ukáže přepočtený úhel; použije ho jen s `--prepocet-uhlu` (Snellův zákon,
  70° v oceli → 65,2° v hliníku). Vlastní sondy a materiály jsou v
  `~/SkodaCAD/ndt-knihovna.json` (*Moje sondy*, `--profil "název"`, jiný soubor
  `--knihovna`). Výpis, souhrn pokrytí i CSV uvedou profil, původ hodnot (obecný profil /
  změřeno / zadáno ručně / katalog / přepočteno), materiál a zdroj rychlostí. Frekvence
  a průměr měniče jsou jen informativní.
* **Návrh poloh UT sondy (etapa 09):** program sám vyzkouší varianty *rovinná plocha × směr
  paprsku × úhel × počet odrazů* (směry po 45° + k cíli, od cíle a kolmo na svar; úhel ze
  studie, na přání i 45°, 60°, 70° se stejnými rozměry sondy; odrazy 0 a 1). Nejdřív levně
  zjistí, odkud paprsek k cíli vůbec míří, sondu přiloží jen tam a varianty, kde se nevejde
  nebo k cíli nemíří, vyřadí s českým důvodem. Zbylé spočítá stávajícím výpočtem pokrytí
  krokem analýzy (výchozí 10 mm, nejvýš 40 variant), seřadí (pokrytí, při rozdílu do 1 p. b.
  víc platných poloh, méně nejistého, jednodušší postup) a složí **kombinaci** nejvýš tří
  variant sjednocenou vzorek po vzorku. Pořadí vyjadřuje jen geometrické pokrytí
  a přístupnost, nikoli zjistitelnost vad; „nenalezeno“ neznamená „nemožné“. Zakřivené plochy
  se jako kontaktní nezkoušejí. Výsledek je jen pohled (model se nemění); *Použít variantu*
  uloží úhel a odrazy do studie (jeden krok Zpět) a přiloží sondu do nejlepší polohy –
  přepočet stejným krokem dá totéž číslo. V okně je to skupina **Návrh poloh sondy** v panelu
  NDT: kontaktní plochy (všechny rovinné / vybrané ve 3D), směry, *zkusit i 45°, 60°, 70°*,
  odrazy a krok analýzy, odhad času, **Navrhnout polohy** (běží na pozadí s průběhem,
  **Zastavit** nechá hotové varianty), tabulka 10 nejlepších variant, kombinace, vyřazené
  a **Mapa ve 3D**: *cíl* (sjednocení kombinace – červená = nepokryto žádnou vyzkoušenou
  variantou; mapa ze *Spočítat pokrytí* má přednost) nebo *kontaktní plochy* (body mřížky:
  zelená = sonda se vejde ve všech směrech mířících k cíli, oranžová = jen v některých,
  červená = paprsek by k cíli mířil, ale sonda se nevejde, šedá = odsud k cíli nemíří).
  **Ukázat variantu** přiloží sondu s úhlem varianty jen jako pohled. V příkazové řádce:
  `skodacad polohy MODEL --studie s1 [--krok 10] [--smery 45] [--uhly 45,60,70]
  [--odrazy 0,1] [--csv polohy.csv]` (odhad a průběh na chybový výstup, souhrn a CSV
  s povinným upozorněním). Návrh: [Etapa 09](docs/ndt/17-navrh-etapa-09.md).
* **Plán dráhy UT sondy (etapa 10):** z přiložené sondy nebo z varianty (či kombinace) návrhu
  poloh sestaví **souvislou dráhu**: řádky tam a zpět s roztečí (výchozí 5 mm) ve vzoru
  *k cíli a zpět* nebo *podél* (automaticky vyhraje méně přestavení, pak kratší dráha, pak méně
  řádků). Úseky vedou jen tam, kde se sonda vejde (bez kolize, dosedá, nepřesahuje, mimo
  **zakázané zóny**) a odkud paprsek míří k cíli; konec u překážky se dohledá na 0,5 mm. Celá
  jízda po povrchu se kontroluje **po 1 mm**; kde se řádek přerušit musí, sonda se **přestaví**
  a ověří se **nájezd** (tělo sondy prodloužené o výšku nájezdu, výchozí 20 mm, nesmí narazit;
  pod převisem se sonda spustí vedle a dojede po povrchu, zvedá se tam, kam se po projeté dráze
  vrátí). **Hodnocení** bez souhrnného skóre: geometrické pokrytí (stávajícím výpočtem
  z poloh plánu – řádky = spojitě projetý pás šířky rozteče), délka po povrchu a vzduchem,
  přestavení, **robustnost** (boční rezerva napříč řádku, místa „na hraně“, nejmenší volno),
  volitelně srovnání s celou plochou a odolnost po posunu řádků o ± půl rozteče. Tabulka poloh
  po rozteči a CSV s povinným upozorněním UT. Plán a zóny se **ukládají do studie** (formát 18);
  po změně dílu, cíle nebo sondy je plán *zastaralý* a sám se nikdy nepřepočítá ani neposune
  (*ověřit znovu* / *sestavit znovu*). Ruční úpravy úseků (smazat, obrátit, přeřadit, upravit
  konce, přidat z přiložené sondy) jsou kroky Zpět. Uložený plán po novém otevření souboru
  spočítá totéž pokrytí. V okně je to skupina **Plán dráhy sondy** v panelu NDT: z čeho
  plánovat (přiložená sonda, vybraná varianta nebo kombinace návrhu poloh), vzor, rozteč,
  výška nájezdu, **Naplánovat dráhu**, **Ověřit a spočítat**, stav plánu, tabulka úseků
  (návaznost a **přínos** – kolik vzorků cíle úsek zasáhne jako první; **Smazat úseky bez
  přínosu** pokrytí nezmenší), úpravy úseků, **Zakázané zóny…** a **přehrávání** (sonda
  s paprskem jede po dráze, mapa pokrytí narůstá). Ve 3D jsou úseky zeleně, přesuny po povrchu
  šedě, přestavení oranžově obloukem nad dílem a zóny průhledně červeně. V příkazové řádce:
  `skodacad draha MODEL --studie s1
  (--plocha X,Y,Z --smer 180 | --varianta N | --kombinace | --prepocet) [--vzor auto|k-cili|podel]
  [--roztec 5] [--najezd 20] [--kontrola 1] [--zona X1,Y1,Z1:X2,Y2,Z2] [--srovnani]
  [--odolnost] [--ulozit] [--csv plan.csv]`. Návrh: [Etapa 10](docs/ndt/18-navrh-etapa-10.md).
* **PT – přístupnost povrchu pro kapilární zkoušku (etapa 11):** jen geometrie podle
  [závazného vymezení PT](docs/ndt/20-vymezeni-pt.md) – žádná smáčivost, vzlínání, citlivost
  ani detekovatelnost vad. Plochy PT studie se rozdělí na drobné plošky a pro každou se zjistí
  **nástřik** (volná přímka zvenku do 60° od kolmice, šikmo do 85°), **otření nástrojem**
  (kulička špičky + dřík s libovolným sklonem, hlavní Ø 10 a jemný Ø 3, dřík 100 mm – přesný
  průnik s dílem) a **prohlídka** (aspoň 30° k povrchu, oko do 600 mm s volným prostorem
  Ø 50 mm; meze z ASME V čl. 9 a BINDT CP25). K tomu upozornění na **úzkou mezeru** a **hluboké
  nebo zakryté místo** (otevřenost pod 10 % směrů). Výsledek: přístupné / omezené / nepřístupné
  / nelze spolehlivě vyhodnotit, s českými důvody, souhrnem po kontrolách a CSV s povinným
  upozorněním PT. Zvolené hodnoty (nástroje, úhly nástřiku, oko) jsou označené „zvoleno pro
  výpočet, ne z normy“; osvětlení a UV (ISO 3059) se nepočítají. Postup čištění **otřením**
  (výchozí) nebo **oplachem**. Nastavení se ukládá do PT studie (formát 19), mapa je jen pohled.
  Ukázka: referenční díl 9 (štěrbina a slepý otvor) a PT studie v kapse a koutovém svaru.
  V příkazové řádce: `skodacad kapilarni MODEL --studie s1 [--krok 2] [--nastroj 10]
  [--jemny 3] [--delka 100] [--oplach] [--ulozit] [--csv pt.csv]`.
  Návrh: [Etapa 11](docs/ndt/19-navrh-etapa-11.md).
* **MT – přiložení jha a směry magnetizace (etapa 12):** jen geometrie zkoušky jhem podle
  [závazného vymezení MT](docs/ndt/22-vymezeni-mt.md) – žádná intenzita ani rozložení
  magnetického pole, citlivost ani detekovatelnost vad. Virtuální **kloubové jho** (dva póly
  Ø 20 mm, výška nohy 60 mm, tělo 40 × 40 mm; zvolené hodnoty) se zkouší přiložit z mřížky
  středů v **8 směrech po 22,5°**: póly musí mít kam dosednout (mezera pod pólem do 1 mm,
  pól celý na ploše), nohy svírají nejvýš 90°, mezi místem a pólem nesmí být stěna a nohy ani
  tělo nesmí narazit (přesný průnik). Rozteč pólů **100 mm**, když nejde, **75 mm** (ISO 17638:
  aspoň 75 mm). **Účinná oblast** mezi póly je obdélník (d − 50) × d/2 (u pólu 25 mm ne) a směr
  pole v ní je jen orientační (přímka mezi póly). Místo mimo rovinu jha se počítá, jen když
  patří k materiálu pod jhem (vypouklá trubka, svar na plechu – ne dno kapsy vedle jha). Místo je **pokryté ve všech orientacích vad**,
  když ho zasáhnou dva směry pole aspoň 60° od sebe (vada skloněná k poli aspoň o 30°, ISO 9934-1
  a ISO 17638); jinak výstup uvede nepokryté orientace. Nanesení detekčního prostředku a
  prohlídka se počítají kontrolami PT. Materiál musí být feromagnetický (ocel, litina; nerez
  a neuvedený jen s potvrzením). Mapa: celkem, zvlášť pro směry pole 0°/45°/90°/135°
  (**rozdíl při otočení magnetizace**), nanesení a prohlídka; CSV s povinným upozorněním MT.
  Nastavení se ukládá do MT studie (formát 20), mapa je jen pohled. Ukázky: MT studie desky,
  trubky, kapsy a koutového svaru. V příkazové řádce: `skodacad magneticka MODEL --studie s2
  [--roztec 100] [--nejmensi 75] [--krok 5] [--krok-stredu 10] [--feromagneticky]
  [--bez-naneseni] [--bez-prohlidky] [--ulozit] [--csv mt.csv]`. V okně: u MT studie
  skupina *Přiložení jha a směry magnetizace* v panelu NDT – *Nastavení MT…*, *Spočítat mapu
  MT* (na pozadí, jde zastavit), přepínač mapy, klik do mapy (směry a důvody místa),
  *Ukázat jho* (jho, které místo pokryje ve zvoleném směru) a *Přiložit jho sem* (střed
  v kliknutém bodě, zvolené natočení). Návrh: [Etapa 12](docs/ndt/21-navrh-etapa-12.md).
* **RT – geometrie projekce (etapa 13):** jen geometrie podle
  [závazného vymezení RT](docs/ndt/24-vymezeni-rt.md). Program nepočítá dávku ani radiační
  ochranu, expozici, kvalitu obrazu, citlivost ani detekovatelnost vad.
  * **Zdroj a detektor:** bodový zdroj (ohnisko 3 mm, kužel 40°, tělo Ø 120 × 300 mm;
    zvolené hodnoty) a plochý detektor 100 × 240 mm (film 10 × 24 cm). Detektor se přiloží na
    plochu, kudy střední paprsek vystupuje (při nárazu se odsune), nebo volně kolmo ke
    střednímu paprsku. Kolize těla zdroje a detektoru se kontroluje přesně.
  * **Výpočet pro každé místo oblasti** (plochy nebo objem svaru) a každou projekci:
    * leží ve svazku a promítne se na detektor,
    * **prozařovaná tloušťka** (všechny úseky v materiálu),
    * **poměr** k tloušťce na středu svazku nejvýš 1,1 (třída B) / 1,2 (A); když střední
      paprsek míří do otvoru, zadá se jmenovitá tloušťka ručně,
    * **nejmenší vzdálenost zdroje** f_min = 15 / 7,5 · d · b^(2/3) (ISO 17636-1, vzorec pro
      film),
    * zvětšení a geometrická neostrost informativně,
    * překryv obrazů (protější stěna trubky).
  * **Výsledek:** promítne se / jen omezeně / nepromítne se / nelze spolehlivě vyhodnotit,
    s českými důvody. Víc projekcí se sjednotí a počítá se, kolik jich místo promítne.
    **Náhled prozařované tloušťky** na detektoru není radiografický snímek. CSV nese povinné
    upozornění RT.
  * **Uložení:** nastavení a projekce se ukládají do RT studie (formát 21), mapa je jen
    pohled.
  * **Ukázky:** RT studie desky s otvorem (kolmo a pod 30°) a tupého V svaru.
  * **Příkazová řádka:** `skodacad radiografie MODEL --studie s2 [--projekce P1]
    [--trida A|B] [--ohnisko 3] [--vzdalenost 500] [--krok 5] [--krok-nahledu 2]
    [--ulozit] [--csv rt.csv]`.

  * **V okně:** u RT studie skupina *Geometrie projekce RT* v panelu NDT:
    * *Nastavení RT…* – třída, zdroj, detektor, kroky,
    * seznam projekcí: *Zdroj nad vybrané místo* (klikni na plochu; u svaru film podél
      svaru), *Upravit projekci…* (zaměřený bod, sklon a natočení, vzdálenost, detektor,
      jmenovitá tloušťka), *Kopírovat posunutou…*, *Smazat projekci*,
    * zdroj s tělem, paprsky do rohů detektoru a deska detektoru vybrané projekce ve 3D
      v barvě stavu (červeně = naráží),
    * *Spočítat projekce* (na pozadí, jde zastavit), mapa celkem nebo pro jednu projekci,
      klik do mapy (stav a čísla v každé projekci),
    * náhled prozařované tloušťky s obrysem oblasti (*Uložit náhled PNG…*), *Export CSV…*.

  Návrh: [Etapa 13](docs/ndt/23-navrh-etapa-13.md).
* **Předběžný NDT audit (etapa 14):** jedním příkazem spočítá všechny studie modelu jejich
  uloženým nastavením a složí **„Předběžný NDT audit – zpráva o geometrickém posouzení“**.
  Nic nevybírá, nepíše „vyhovuje“ a model nemění (výsledek je jen pohled, formát 21).
  * **Co se spočítá:** PT, MT a RT studie svou mapou; UT studie ověřením uloženého plánu
    dráhy s pokrytím, jinak výsledkem spočítaným v tomto sezení (plán, mapa pokrytí, návrh
    poloh), jinak „neprovedeno“ – pomalý návrh poloh jen na výslovné přání. Mapa tloušťky
    stěny, jen když má model nastavenou mez. Zastaralou studii audit sám nepotvrdí
    („nedostupné“ s důvodem).
  * **Problémová místa:** sousední místa se stejným stavem (nepokryto, nelze spolehlivě
    vyhodnotit, omezeně) spojená do jednoho, s plochou nebo objemem, polohou a důvody
    s podíly.
  * **Zpráva:** povinná upozornění všech metod (UT, PT, MT, RT), hlavička s otiskem dílu,
    sestavením programu a knihovnami, přehled studií se stavem, tabulka míst, celý záznam
    studie (nastavení) a verze algoritmů. Složka: `zprava.html`, `mista.csv` a CSV studií.
  * **Příkazová řádka:** `skodacad audit MODEL [--studie s2] [--navrh-poloh s1]
    [--slozka zprava] [--zpracovatel "J. N."]`.
  * **V okně:** *NDT → Předběžný NDT audit…* otevře panel *NDT audit*:
    * seznam studií se zaškrtávátky, co se spočítá a jak dlouho (nebo proč ne), u UT bez
      plánu „i návrh poloh“ s odhadem; *Zpracoval(a)*,
    * *Spustit audit* (na pozadí) / *Zastavit* – spočítané studie zůstanou,
    * přehled studií a tabulka problémových míst; klik na místo vybere studii v panelu NDT
      a ukáže její mapu ve 3D s modrou kuličkou ve středu místa,
    * mapy z auditu jsou i v panelu NDT – po výběru studie se nemusí počítat znovu,
    * *Exportovat zprávu…* – složka se `zprava.html`, `zprava.pdf`, `mista.csv`, CSV studií
      a obrázky map z 3D okna.

  Návrh: [Etapa 14](docs/ndt/25-navrh-etapa-14.md).

### Tažení a přechod

**Tažení** protáhne profil po trase – trubky, kolena, madla, rámy z jeklu. Ukázka:
*Soubor → Otevřít ukázku → koleno*.

* **Trasa** jsou body `x; y; z`, jeden na řádek (i s parametry, např. `L; 0; L`). Profil se
  táhne od prvního bodu k poslednímu.
* **Poloměr ohybu** zaoblí rohy trasy jako ohýbačka trubek. Prázdné nebo 0 = ostrý roh,
  kusy se potkají **na pokos** (svařený rám).
* **Profil**: *kruh / trubka* (průměr), *obdélník / jekl* (šířka × výška), nebo *tvar ze skici*
  (libovolná skica, i s dírami). S **tloušťkou stěny** je kruh trubka a obdélník jekl.
* Profil stojí kolmo na začátek trasy, jeho střed (počátek skici) je v prvním bodě. Šířka
  jde vodorovně; když trasa začíná svisle, šířka jde podél osy X (stejně jako skica na XY).
* **Ocelový profil podle tabulek** (*Profil → ocelový profil*): IPE, U, L, jekl nebo trubka –
  profil stojí na výšku, střed obalového obdélníku je v prvním bodě trasy.
* **Uzavřená trasa** (poslední bod = první) udělá rám: všechny rohy jsou stejné (na pokos
  nebo s ohybem). Ukázka: *ram* – rám z jeklu 40 × 20 × 2.
* Tažení jde i odebírat (*Operace → odebrat*: drážka podél hrany) a opakovat polem.

**Přechod** plynule spojí dvě a více skic – výsypka, redukce, násypka. Ukázka: *výsypka*.

1. Nakresli skicu dole (třeba kruh na XY) a další výš (*Posun roviny* např. 300 – čtverec).
2. *Přidat prvek → Přechod* – spojí dvě poslední skici. Pořadí je pořadí ve stromu, v panelu
   jde zaškrtnout i víc skic (dole kruh, uprostřed ovál, nahoře čtverec).
3. **Rovné stěny** – mezi skicami rovné plochy (jehlan, komolý kužel); bez nich se plocha
   mezi více skicami plynule prohne.
4. **Tloušťka stěny** – dutý přechod s otevřenými konci. Prázdné nebo 0 = plné těleso.
5. **Tloušťku měřit** – u nového přechodu vyber jednu ze dvou možností:
   **Kolmo ke stěně** (výchozí) používá 3D offset; když jej jádro neumí nebo výsledek
   neprojde kontrolami, zobrazí chybu. **V rovinách skic** zmenší každý profil o zadanou
   hodnotu a odečte vnitřní přechod. Kolmo ke šikmému plášti je pak materiál tenčí.
   Starý přechod bez volby ukazuje **Automaticky (starší model)** a zachovává původní
   geometrii. Úprava jiného políčka jej nepřevede na nový režim.

6. **Změřit stěnu** pod formulářem zobrazí rozsah vzorkovaných tlouštěk v aktuálním
   hotovém dílu a počty bodů pod zadáním, u zadání, s delším průchodem a nejistých.
   Kliknutí na řádek ukáže místo a měřicí úsečku ve 3D. Po změně modelu měření zopakuj.
   Výpočet běží na pozadí a lze jej zastavit. Vzorky nejsou globální minimum ani
   výrobní přejímka; zesílený roh může mít delší průchod a paprsek přes hranu je nejistý.
   Jde o CAD délku kolmo do materiálu, nezávislou na filtru NDT měřidla.

Ukázka **loft_stena.json**: redukce Ø80 → Ø40, výška 60 mm a stěna 3 mm.
V normálovém režimu má objem **33 879,562165 mm³**, v rovinách skic **32 232,740626 mm³**
a kolmo k plášti asi **2,846 mm**. Přepnutí jde vrátit přes Zpět/Znovu.
Stávající výsypka zachovává původní výsledek; při výslovném požadavku 3 mm kolmo
se její neproveditelný offset odmítne. Mapa tloušťky ukazuje vzorky měření,
u okrajů a zesílených rohů má samostatná omezení.

Skici přechodu musí mít každá jeden obrys bez děr (dutý přechod se dělá tloušťkou stěny).

### Řízený přechod se čtyřmi vodítky

*Přidat prvek → Řízený přechod* vytvoří plné těleso mezi dvěma obdélníkovými
skicami v rovinách XY. Druhá skica musí být výše. Čtyři kubická vodítka A–D
spojují rohy určené znaménky X/Y; každé má dvě rukojeti s posunem X/Y
oproti přímému spojení, ve výšce H/3 a 2H/3. Hodnoty mohou být výrazy parametrů.
Kliknutí na A–D zvýrazní vodítko a zobrazí jeho čárkovaný řídicí polygon ve 3D.
**Větší bod rukojeti uchop levým tlačítkem a táhni.** Pohyb je v XY při stejné
výšce; během tahu se mění jen náhled vodítka. Puštění myši ověří celý model
na pozadí a úspěšný tah uloží jako jeden krok Zpět. Esc nebo přepnutí z okna
tah zruší. Neplatný výsledek ponechá původní model i historii. Výraz rukojeti
si zachová vazbu na parametry. Nad vodítky je **Krok tažení**: 0 = **Volně**,
kladná hodnota 0,001–1000 mm přichytává posun v X i Y od začátku tahu
(např. 0,1 / 0,5 / 1 / 5 mm). Polovina kroku se zaokrouhlí od nuly.
Volba platí pro otevřené okno, drží se při přepínání prvků a Zpět/Znovu,
model ani jeho formát nemění. [Podrobnosti kroku](docs/p6-9-krok-tazeni.md).
Pod krokem je **Směr tažení**: **XY (obě osy)**, **Pouze X** nebo **Pouze Y**
v souřadnicích dílu. Zvolená osa používá nastavený krok, druhá souřadnice a výška
zůstávají pevné. X lze táhnout i zepředu, Y zprava; při pohledu přímo podél zvolené
osy aplikace doporučí pohled natočit. Změna směru rozpracovaný tah zruší.
[Podrobnosti omezení směru](docs/p6-10-smer-tazeni.md). Při bočním pohledu nebo překrytých rukojetích
zvol Izometrii či Shora nebo díl přibliž. [Podrobnosti tažení](docs/p6-8-tazeni-rukojeti.md).
Posun rukojeti není skutečné vyboulení: při stejném posunu obou rukojetí
je prostřední bod vychýlen o 3/4 tohoto posunu.

Otevři ukázku `examples/rizeny_prechod.json`: čela 40 × 30 a 24 × 18 mm,
výška 60 mm, skutečné prostřední vyboulení Bx = 7 a By = 5 mm, objem
**77 760 mm³** (bez vyboulení 47 040 mm³). Úpravy podporují Zpět/Znovu,
uložení a opětovné otevření; lze vytvořit nové těleso, přidávat nebo odebírat.

Křížení, zborcení i neprůkazná konvexita se odmítnou kontrolou celého intervalu
výšky. Meziřezy mohou být obecné konvexní čtyřúhelníky. Zaoblené nebo kruhové
profily, díry, šikmá čela a dutá stěna zatím nejsou podporované.
[Popis formátu, přesnosti a kontrol](docs/p6-7-rizeny-prechod.md).
[Geometrický průzkum](docs/p6-6-vodici-krivky-overeni-a-navrh.md) zůstává podkladem
pro pozdější rozšíření o další profily.


### Normalizované díly

*Přidat prvek → Normalizovaný díl* vloží díl podle strojnických tabulek. Ukázka:
*drzak_loziska* (kapsa na ložisko 608 a kapsy na matice M3 pro 3D tisk).

| Druh | Velikosti | Délka |
|---|---|---|
| šroub s válcovou hlavou, imbus – ISO 4762 | M2–M30 | dřík pod hlavou |
| šroub se šestihrannou hlavou – ISO 4017 | M2–M30 | dřík pod hlavou |
| zápustný šroub, imbus – ISO 10642 | M3–M20 | celková i s hlavou |
| šestihranná matice – ISO 4032, podložka – ISO 7089 | M2–M30 | – |
| kuličkové ložisko | 623–626, 608, 688, řady 6000 a 6200 (do 6010/6210) | – |
| válcový kolík – ISO 2338 | Ø2–Ø20 | délka kolíku |
| těsné pero – DIN 6885 tvar A | 2 × 2 až 28 × 16 (u každého rozsah hřídele) | délka pera |
| ocelový profil – tyč | IPE 80–400, U 80–240, L 20 × 3 – 120 × 12, jekly, trubky | délka tyče |

* Díl stojí na zvolené **rovině** v **polohách** `x; y` (jako díra – víc kusů najednou):
  šroub má hlavu nad plochou a dřík v materiálu, zápustný šroub je zapuštěný, matice,
  podložka, ložisko, kolík a tyč leží na ploše. **Natočení** otočí šestihran, pero či profil.
* **Operace**: *nový díl* (samotný šroub k tisku nebo do STEP), *přidat*, nebo **odebrat =
  kapsa**. Kapsa je obrys dílu bez děr (matice bez díry, ložisko jako válec) zvětšený o
  **vůli kapsy** na každou stranu (pro 3D tisk 0,1–0,2 mm). Aby kapsa šla do materiálu,
  zvol *Směr → otočit do materiálu*.
* **Drážka pro pero**: na hřídeli klikni na plášť (*Skica na ploše* → tečná rovina) a pero
  odeber – vznikne drážka hloubky t1 podle DIN 6885 (pero leží podél osy hřídele).
* Závit je **vyznačený** – dřík má jmenovitý průměr (M6 = 6 mm), stejně jako u děr. Tvary jsou
  zjednodušené (bez sražení hlav, ložisko jako prstenec).
* Ocelový profil jde dát i **do skici** (*tvar Ocelový profil*) – pak ho jde vysunout,
  táhnout či otáčet jako každou skicu.

Rozměry jsou z tabulek ověřených porovnáním více zdrojů (normy jsou placené) – zdroje jsou
v `src/skodacad/standards.py`. Plochy průřezů IPE, U a L souhlasí s tabulkovými.

### AI asistent

**Model → AI asistent** (`Ctrl+I`, tlačítko v liště) otevře rozhovor s Claude (Anthropic).
Napiš česky, co s modelem udělat – AI ho upraví sama:

* „zvětši přírubu na průměr 200 a přidej jednu díru se závitem M8 na roztečnou kružnici“
* „udělej krabičku 100 × 60 × 40, stěna 2 mm, 4 sloupky se závitem M3“ (nový díl od nuly)
* „proč je vysunutí červeně?“, „kolik díl váží?“ (vysvětlí a navrhne opravu)

Jak to funguje:

* AI mění model **stejnými kroky jako formulář** (parametry, prvky, název a materiál) a po
  každém kroku vidí výsledek přepočtu – chyby, objem, rozměry. Úpravu si tak sama ověří,
  případně opraví, a může si díl i prohlédnout (snímek 3D pohledu).
* V panelu průběžně vidíš, co dělá („→ Nastavuji parametry: D = 200“), a na konci shrnutí.
  **Celou úpravu vrátíš jedním Zpět** (`Ctrl+Z`). Během práce AI jsou ruční úpravy
  zamčené; *Zastavit AI* ji přeruší (co stihla, zůstane – vrátíš jedním Zpět).
* *Nová konverzace* – AI zapomene předchozí dotazy (při otevření jiného modelu samo).

**Nastavení AI…** (tlačítko v panelu nebo menu Model):

* **API klíč** – vytvoř ho na [console.anthropic.com](https://console.anthropic.com/settings/keys)
  (účet s kreditem – předplatné Claude.ai API nezahrnuje). Uloží se jen do tvého profilu
  (`C:\Users\<jméno>\SkodaCAD\nastaveni.json`); funguje i proměnná `ANTHROPIC_API_KEY`.
* **Model** – *Claude Opus 5.5* (výchozí, nejschopnější) nebo *Claude Sonnet 5.5* (poloviční
  cena). **Důkladnost** – rychle a levně / vyváženě / důkladně (výchozí).
* **Cena**: jedna úprava stojí orientačně 2–7 Kč u Opus, u Sonnet zhruba polovinu; spotřebu
  konverzace ukazuje panel. Model (JSON) se posílá ke zpracování společnosti Anthropic.
  Kdyby bezpečnostní filtr dotaz odmítl, zkusí ho automaticky záložní model Claude.

### Pole a zrcadlení

Ukázka: *Soubor → Otevřít ukázku → kryt*. **Pole** zopakuje vybrané prvky (díru, výřez,
výstupek, žebro …), **zrcadlení** je převrátí podle roviny. Kopie nejsou samostatné – když
změníš původní prvek (průměr díry, rozměr výstupku), přepočítají se s ním.

1. Ve stromu vyber prvek, který chceš opakovat (třeba díru).
2. *Přidat prvek → Pole* (nebo *Zrcadlení*) – nový prvek se vloží za vybraný a rovnou ho
   opakuje. V panelu *Úprava prvku* jde zaškrtnout i víc prvků najednou.
3. Zvol druh pole a vyplň hodnoty:

| Druh | Hodnoty | Příklad |
|---|---|---|
| **kruhové** – dokola | počet kusů, osa (X/Y/Z), bod na ose, celkový úhel | 6 děr dokola na přírubě |
| **lineární** – v řadě | počet kusů, směr (X/Y/Z), rozteč (záporná = opačně) | 5 žeber v řadě |
| **mřížka** | k lineárnímu navíc druhý směr, počet a rozteč | 4 × 3 větrací otvory |

* Počet kusů je **včetně původního** (6 = původní + 5 kopií).
* Celkový úhel 360° (výchozí) rozloží kusy rovnoměrně dokola; menší úhel dá první a poslední
  kus na kraje úhlu (4 kusy na 90° = po 30°).
* **Zrcadlení celého dílu:** když u zrcadlení nic nezaškrtneš, zrcadlí se celý díl – stačí
  namodelovat polovinu souměrného dílu. Rovina může být i plocha dílu (např. *pravá
  plocha* díl zdvojí).
* Opakovat jde vysunutí, rotace, tažení, přechod, normalizované díly, díry, pole a
  zrcadlení. Zaoblení, sražení a skořepina se
  opakovat nedají – dej je do stromu až za pole.

Prvek vybraný ve stromu jde smazat (*Smazat*, klávesa Delete) nebo posunout (▲ ▼). Nový prvek
se vloží za vybraný. **Zpět / Znovu**: `Ctrl+Z` / `Ctrl+Y`.

Do složky **`SkodaCAD`** ve tvém uživatelském profilu (`C:\Users\<jméno>\SkodaCAD`) se
zapisuje soubor `skodacad.log` – při potížích ho pošli, je v něm popis chyby.

## Příkazová řádka

```bash
skodacad build examples/priruba.json            # postaví přírubu, exporty do out/
skodacad build examples/priruba.json --set n=8  # totéž s 8 dírami místo 4
skodacad build examples/krabicka.json --format 3mf,svg
skodacad ai examples/priruba.json "zvětši D na 200"   # AI asistent → priruba-ai.json
skodacad ai krabicka.json "krabička 100 × 60 × 40, stěna 2 mm"  # nový díl (soubor neexistuje)
skodacad paprsek examples/ndt/trubka.json --z 0,0,100 --smer 0,0,-1   # NDT: přímka dílem
skodacad sonda examples/ndt/zebro.json --bod 22,0,20 --smer -1,0,0 --posun -1,0,0 --delka 10
skodacad sestava examples/sestavy/krabicka_s_vickem.json   # komponenty, stav, objem, hmotnost
skodacad sestava examples/sestavy/krabicka_s_vazbami.json  # … i vazby a volnost komponent
skodacad sestava examples/sestavy/deska_se_sroubem.json --kontrola --kusovnik k.csv --export s.step
```

`skodacad sestava` vypíše komponenty sestavy (✓ v pořádku, ✕ chybí nebo nejde postavit
s českým důvodem) s volností podle vazeb (*plně určená*, *volná: 2 posuny, 1 otočení*),
vazby se stavem, upozornění, objem, hmotnost a obálku. Když některá komponenta chybí nebo
jsou vazby ve sporu, napíše „NEÚPLNÁ“ a skončí kódem 1. Když vazby dají jiné polohy, než jsou
v souboru (změnil se díl), vypíše je – soubor sestavy ani díly se přitom nemění.
`--kontrola` přidá kolize a vůle (s `--vule 0,2` jinou mez vůle) a skončí kódem 1 při
nepřijaté kolizi nebo místu, které nejde ověřit; `--kusovnik soubor.csv` uloží kusovník
a `--export soubor.step` sestavu do STEP (obojí jen z úplné sestavy).

`skodacad paprsek` vypíše, kudy přímka z bodu `--z` směrem `--smer` prochází materiálem
(úseky, délky, úhly dopadu od normály) a jestli je výsledek jistý. Souřadnice v mm jako
`0,0,100`, s desetinnou čárkou `"0;0;12,5"`; `--delka` omezí délku přímky, `--set` dočasně
změní parametr. Jde jen o geometrii přímky – ne o fyzikální model UT:

```
Paprsek z [0; 0; 100] směrem [0; 0; -1] (algoritmus ndt-geometrie 1):
  úsek 1: 42.85 → 48.85 mm, v materiálu 6.00 mm (vstup 0.0°, výstup 0.0°)
  úsek 2: 151.15 → 157.15 mm, v materiálu 6.00 mm (vstup 0.0°, výstup 0.0°)
  celkem v materiálu: 12.00 mm (jen jisté úseky), jistota: ok
```

`skodacad sonda` přiloží virtuální sondu do bodu `--bod` (na povrchu) se směrem paprsku
`--smer` a spočítá geometrickou dráhu osy UT paprsku v dílu: výchozí úhlová 40 × 20 × 25 mm
($\beta = 45^\circ$, 1 odraz), jiná přes `--prima 10`, `--uhlova 40x20x25`, `--celo 12`,
`--uhel 60` (nebo `--snell 36.44,2730,3250` a `--vlna shear`), `--odrazy 1`, `--dosah 100`,
sonda ze studie `--studie s1`; meze `--mezera 0.5` a `--rezerva 5`. S `--posun`
(a `--delka`, `--krok`) sondu posouvá a vypíše, odkud kam volně jede:

```
Úhlová sonda 40 × 20 × 25 mm, výstupní bod 12 mm od čela (mezera nejvýš 0.50 mm, rezerva 0.00 mm)
Přiložení v [22; 0; 20], paprsek [-1; 0; 0]:
  Přiloženo. Mezera pod sondou 0.00 mm, volno k překážkám 5.00 mm.
Dráha paprsku (úhel lomu 45.0°, nejvýš 1 odraz, algoritmus ndt-ut-paprsek 1):
  rameno 1: [22; 0; 20] → [2; 0; 0], délka 28.28 mm, vodorovně 20.00 mm, hloubka 20.00 mm (dopad 45.0°)
  ...
Posun směrem [-1; 0; 0] o 10 mm po 1 mm: volně 0–5 mm
  první potíž po 6 mm: Koliduje. Průnik těla sondy s dílem 500 mm³.
  (ŠkodaCAD provádí pouze geometrické posouzení přístupnosti ultrazvukové sondy a pokrytí …)
```

`skodacad ai` průběžně vypíše kroky AI, výsledek uloží vedle původního modelu jako
`<model>-ai.json` (`-o` jinam, `--prepsat` do původního) a ukáže spotřebu. Klíč a model bere
z nastavení okna (nebo `ANTHROPIC_API_KEY`), `--claude claude-sonnet-5-5` a
`--dukladnost low|medium|high` je přepíšou.

Výstup:

```
Strom prvků:
  ✓ Skica „Obrys příruby“
  ✓ Vysunutí „Deska“
  ...
Vlastnosti dílu:
  Objem:     311 093 mm³ (311.09 cm³)
  Hmotnost:  2.442 kg (ocel, 7.85 g/cm³)
  Rozměry:   165.00 × 165.00 × 18.00 mm
Uloženo: out/priruba.step, out/priruba.stl, out/priruba.3mf, out/priruba.svg
```

Model s NDT studiemi vypíše i jejich stav (`skodacad build examples/ndt/deska.json
--set t=30`):

```
NDT studie:
  ⚠ UT desky shora (UT) – zastaralá
      Díl se od nastavení studie změnil – zkontroluj ji a potvrď pro aktuální díl.
      Kontrolovaná plocha se posunula o 10.00 mm – zkontroluj, že je to pořád ta správná.
      Neověřeno.
```

Model s uloženými měřeními je vypíše taky a s nastavenou mapou tloušťky (nebo s volbou
`--mapa`) i její souhrn – body mapy uloží do `out/<model>-tloustka.csv`
(`skodacad build examples/trubka.json --set h=4`):

```
Měření:
  Jmenovitá tloušťka stěny: 6.00 mm
  Zbytková tloušťka pod jamkou: 2.00 mm
  Vnější průměr: 114.30 mm
Mapa tloušťky stěny:
  Nejtenčí místo: 2.00 mm (X 49.24  Y 0.00  Z 53.15)
  Nejčastější tloušťka: 6.00 mm, největší: 300.00 mm
  Pod minimem 4.00 mm: 0.30 % povrchu (619 mm²)
  27940 bodů po 12.4 mm, výpočet 3.9 s
```

| Formát | K čemu |
|---|---|
| `step` | přesná geometrie pro jiné CAD programy (Inventor, Solid Edge, Fusion …) |
| `stl`, `3mf` | 3D tisk (3MF je modernější a nese jednotky) |
| `glb` | prohlížeče, Blender |
| `svg` | izometrický náhled se skrytými hranami |

## Formát modelu

```json
{
  "format": "skodacad",
  "version": 24,
  "name": "Plochá příruba",
  "material": "ocel",
  "parameters": {"D": 165, "t": 18, "k": "D - 40"},
  "features": [ ... ],
  "measurements": [ ... ],
  "thickness_map": {"limit": 4},
  "ndt": {"studies": [ ... ]}
}
```

Každá číselná hodnota může být číslo nebo **výraz** s parametry, např. `"D/2 - 5"`.
Výrazy umí `+ - * / **`, závorky, `sqrt`, `sin`, `cos`, `tan` (ve stupních), `min`, `max`, `pi`.
Rozměry jsou v milimetrech, úhly ve stupních.

### Prvky (`features`)

Každý prvek má jedinečné `id`, `type` a volitelně český `name` pro výpis stromu.

| `type` | Co dělá | Hodnoty |
|---|---|---|
| `step_import` | vložený zdroj STEP, první těleso | `source_name`, `size_bytes`, `sha256`, `encoding`, `data` – vzniká příkazem Importovat STEP, AI jej nesestavuje ani nepřepisuje |
| `sketch` | 2D skica | `plane`, `offset`, `elements` (seznam tvarů) |
| `extrude` | vysunutí skici | `sketch`, `distance`, `operation`, `direction`, `through_all` |
| `revolve` | rotace skici kolem osy | `sketch`, `axis` (`X`/`Y`/`Z`), `angle` (výchozí 360) |
| `sweep` | tažení profilu po trase | `path` (`[[x, y, z], …]`, aspoň 2 body; poslední = první → uzavřený rám), `bend_radius` (0 = ostré rohy na pokos), `profile` (`circle`/`rectangle`/`steel`/`sketch`), `diameter`; `width`, `height`; `section` (`"IPE 100"`, `"L 50x5"`, `"RHS 40x20x2"`, `"CHS 48.3x2.6"`); `sketch`; `wall` (trubka/jekl), `operation` |
| `standard` | normalizovaný díl | `kind` (`socket_screw`, `hex_screw`, `countersunk_screw`, `nut`, `washer`, `bearing`, `pin`, `key`, `profile`), `size` (`"M6"`, `"608"`, `"6"`, `"8x7"`, `"IPE 100"`), `length`, `plane`, `offset`, `positions` (`[[x, y], …]`), `angle`, `direction` (`normal`/`reverse` = do materiálu), `operation`, `clearance` (vůle kapsy) |
| `guided_loft` | řízený plný přechod | dvě `sketches`, čtyři `guides` s rohem `corner` a dvěma XY posuny `controls`, `operation` (verze 34) |
| `loft` | přechod mezi skicami | `sketches` (`["dole", "nahore"]`, v pořadí), `ruled`, `wall`, `wall_mode` (`normal` / `sections`, verze 33), `operation` |
| `fillet` | zaoblení hran | `edges`, `radius` |
| `variable_fillet` | lineární proměnné zaoblení jedné přímé pravoúhlé vnější hrany | `edges`, `radius_start`, `radius_end`, `reverse`; `direction`, `origin`, `normals` vyplní výběr ve 3D |
| `chamfer` | sražení hran | `edges`, `distance` |
| `shell` | skořepina (vydlabání) | `thickness`, `open_faces` (např. `["top"]`) |
| `hole` | díra podle tabulek | `kind`, `size` (`"M6"`), `fit`, `plane`, `offset`, `positions` (`[[x, y], …]`), `depth` nebo `through_all`, `thread_depth`, `diameter` (vlastní průměr), `modeled_thread` (`true` = vymodelovaný závit), `print_clearance` |
| `pattern` | pole – opakuje prvky | `features` (`["dira1"]`), `kind` (`circular`/`linear`), `count` (včetně původního); kruhové: `axis`, `center` (`[x, y, z]`), `angle` (výchozí 360); lineární: `direction` (`X`/`Y`/`Z`), `spacing`, pro mřížku `direction2`, `count2`, `spacing2` |
| `mirror` | zrcadlení | `plane`, `offset`, `features` (bez nich se zrcadlí celý díl) |
| `move_face` | posunutí rovinné plochy (přímá úprava) | `face`, `origin`, `distance` (+ ven z materiálu, − dovnitř) |
| `face_diameter` | nový průměr válcové plochy – díry nebo čepu (přímá úprava) | `face`, `origin`, `diameter` |

* **`plane`** – základní rovina `XY`, `XZ`, `YZ`, nebo plocha dílu `top`, `bottom`, `front`,
  `back`, `left`, `right`. Souřadnice skici na ploše dílu jsou globální (na `top` platí X a Y dílu).
  Šikmá či zakřivená plocha: `{"at": [x, y, z], "normal": [nx, ny, nz]}` – plocha nejbližší
  bodu `at` (směr `normal` rozhodne na hraně); rovinná plocha nese skicu přímo, zakřivená
  tečnou rovinou v tom bodě. Počátek skici je v bodě `at`, osa X podél osy válce/kužele,
  jinak vodorovně po ploše. Ukázka: *cep* (příčná díra a drážka pro pero na čepu).
* **`operation`** – `new` (první těleso), `add` (přidat materiál), `cut` (odebrat).
* **`direction`** – `normal` (ven z roviny), `reverse` (opačně), `both` (symetricky, `distance` je
  celková tloušťka). Řez (`cut`) jde ve výchozím stavu do materiálu.
* **`through_all": true`** – řez skrz celý díl.

### Proměnné zaoblení (`variable_fillet`, verze 32)

Ve 3D vyber **jednu přímou vnější hranu** a v místní nabídce zvol
**Proměnné zaoblení vybrané hrany**. Vpravo zadej R1 a R2 (čísla nebo výrazy).
Konce původní hrany označují zelené značky **R1** a **R2**. Volba
**Obrátit směr R1 → R2** prohodí konce; hodnoty poloměrů zůstanou stejné.
Ukázka: *Soubor → Otevřít ukázku → promenne_zaobleni*.

První verze vyžaduje dva **rovinné pravoúhlé boky** a oba konce uzavřené
**kolmými rovinnými plochami**. Neumí vnitřní kout, křivou hranu, tečný řetězec,
šikmé zakončení ani zaoblení zasahující do díry nebo jiného detailu. Takový případ
odmítne; původní geometrie zůstane k opravě a export vyžaduje celý platný model.
Poloměr v řezech kolmých k původní hraně roste **lineárně po délce hrany**.
Výpočet je přesný přímkový loft čtvrtkruhového řezacího profilu, ne síťová aproximace.

```json
{"id": "zaobleni", "type": "variable_fillet",
 "edges": {"between": ["back", "right"]},
 "radius_start": "R1", "radius_end": "R2", "reverse": false,
 "direction": [0, 0, 1], "origin": "teleso", "normals": [[1, 0, 0], [0, 1, 0]]}
```

`direction` je uložený jednotkový směr od R1 k R2 před obrácením; pořadí vrcholů
OCCT jej nemění. `origin` je id prvku, od kterého vybraná hrana nepřetržitě existuje;
`normals` jsou vnější normály jejích boků. Změna původu, boků nebo směru vyžaduje
nový výběr. Tyto pojistky se nesmějí odhadovat ani automaticky opravovat v JSON.
Formulář je zachovává při úpravě poloměrů. Pole a zrcadlení tento dokončovací prvek
neopakují. Dokument s tímto prvkem se ukládá ve **verzi 32**, pokud neobsahuje
výslovný režim stěny loftu (pak verze 33) nebo řízený přechod (pak verze 34).
Ostatní díly nadále používají nejnižší potřebnou verzi 24–28; verze 1–34 se stále načítají.

### Význam stěny loftu (`wall_mode`, verze 33)

```json
{"id": "redukce", "type": "loft", "sketches": ["dole", "nahore"],
 "wall": 3, "wall_mode": "normal"}
```

`normal` znamená vnitřní 3D offset a nikdy tiše nepřechází na náhradní postup.
`sections` používá 2D offset skic; kolmo může být stěna tenčí. Chybějící klíč zachová
starší automatické chování. Nové pole vyžaduje verzi **33**, i když je `wall` právě
prázdné nebo 0; starší aplikace musí takový soubor odmítnout. Bez tohoto pole se
verze starých dílů nemění. Podrobnosti: [návrh a kontroly](docs/p6-4-rezim-steny-loftu.md).

### Import STEP (`step_import`, verze 24)

Příkaz **Soubor → Importovat STEP** v prázdném modelu přečte jeden platný uzavřený
objemový díl v milimetrech, metrech nebo palcích, ukáže jeho náhled a vyžádá potvrzení. Původní STEP
(do 16 MiB) se uloží do modelu; původní parametrická historie není k dispozici.
Sestavy, více těles, otevřené plochy a soubory s hlášenými opravami se odmítají.
Při poškození uložených dat lze vybrat import ve stromu a použít **Obnovit zdroj
STEP** se stejným původním souborem. AI zdrojová data nevidí a nesmí je vytvářet.

### Přímé úpravy ploch (`move_face`, `face_diameter`, verze 23)

V okně klikni na jednu plochu, otevři pravým tlačítkem nabídku a zvol posunutí plochy
nebo změnu průměru. Zadej hodnotu v mm nebo výraz s parametry a stiskni **Zobrazit
náhled**: původní díl je průhledný, navržený výsledek plný. **Použít** zapíše úpravu
jako jeden krok Zpět;
**Zrušit** model nezmění. Změna hodnoty existující přímé úpravy také vyžaduje náhled.
Plochu existující úpravy lze znovu vybrat příkazem **Převzít vybranou plochu**.
Asistent může navrhnout úpravu plochy vybrané uživatelem, ale její použití musí uživatel
potvrdit v tomtéž dialogu. Výpočet náhledu u složitých dílů může chvíli trvat.
Změna průměru díry nemění její původní označení závitu ani tabulkovou velikost.

```json
{"id": "tensi_deska", "type": "move_face", "name": "Tenčí deska",
 "face": {"at": [10, 15, 20], "normal": [0, 0, 1], "type": "plane"},
 "origin": "deska", "distance": -3}
{"id": "dira_8", "type": "face_diameter",
 "face": {"at": [18, 12, 10], "normal": [-1, 0, 0], "type": "cylinder"},
 "origin": "pole", "diameter": 8}
```

* Mění **hotový díl** v místě prvku ve stromu – hodí se i na díl bez historie. Sousední
  plochy se jen prodlouží nebo zkrátí; čep stojící na posunuté ploše zůstane na místě.
* **`face`** – plocha jako u měření: bod `at` na ploše, směr `normal` ven z materiálu
  a `type` (`plane` u posunutí, `cylinder` u průměru). Pevný poloměr se neukládá.
* **`origin`** – id prvku, kterým plocha vznikla (od kterého v bodě `at` na díle
  nepřetržitě je). Je povinný: když se po změně dřívějšího prvku najde plocha jiného
  původu, prvek skončí chybou místo tiché záměny. Doplní ho výběr plochy ve 3D.
* Odmítne se: posun 0 nebo stejný průměr, plocha s hladce navazujícím sousedem
  (zaoblení, vymodelovaný závit), kužel, koule a obecné plochy, úprava, při které by
  soused zanikl, plocha splynula s jinou nebo vnikla do jiné části tělesa.
* Pole a zrcadlení vybraných prvků přímé úpravy neopakují (jako zaoblení).

### Tvary ve skice (`elements`)

| `shape` | Hodnoty |
|---|---|
| `rectangle` | `width`, `height`, `corner_radius` |
| `circle` | `diameter` |
| `circle_pattern` | `count`, `pitch_diameter`, `diameter`, `start_angle` – díry na roztečné kružnici |
| `regular_polygon` | `sides`, `diameter` (opsaný) – např. šestihran |
| `slot` | `length` (rozteč středů), `width` – drážka |
| `polygon` | `points` – seznam bodů `[[x, y], …]` |
| `profile` | obrys z úseček a oblouků s vazbami – kreslí se ve skicáři, viz níže |
| `steel` | `section` – průřez ocelového profilu podle tabulek (`"IPE 100"`, `"UPN 100"`, `"L 50x5"`, `"RHS 40x20x2"`, `"CHS 48.3x2.6"`), střed obalového obdélníku v `center` |

Všechny tvary mají navíc `center` (`[x, y]`), `angle` a `mode` (`add` = přidat, `subtract` = odečíst,
tak vzniká např. otvor v kruhu).

### Obrys s vazbami (`profile`)

```json
{"shape": "profile",
 "points": {"A": [0, 0], "B": [40, 0], "C": [40, 20], "M": [40, 10], "D": [0, 20]},
 "segments": {"s1": {"type": "line", "start": "A", "end": "B"},
              "s2": {"type": "arc", "start": "B", "end": "C", "center": "M"},
              "s3": {"type": "line", "start": "C", "end": "D"},
              "s4": {"type": "line", "start": "D", "end": "A"}},
 "constraints": [{"type": "coincident", "point": "A", "on": "origin"},
                 {"type": "horizontal", "segment": "s1"},
                 {"type": "length", "segment": "s1", "value": "sirka"},
                 {"type": "radius", "segment": "s2", "value": 10},
                 {"type": "tangent", "segments": ["s1", "s2"]}]}
```

* `points` jsou přibližné polohy – přesné spočítá řešič vazeb (SolveSpace) při každém přepočtu.
* Oblouk vede **proti směru hodinových ručiček** od `start` do `end`; `"construction": true`
  = pomocná čára. Bod `origin` je počátek skici.
* Kružnice: `{"type": "circle", "center": "K", "radius": 5}` – `radius` je přibližný, přesný
  určí vazby (po vyřešení se uloží). Víc smyček v jednom obrysu = vnořené jsou díry.
* Vazby: `fix` (point), `coincident` (point + on: bod/čára/oblouk/kružnice/origin),
  `horizontal`/`vertical` (segment, nebo points), `parallel`, `perpendicular`, `tangent`,
  `equal`, `concentric` (segments), `midpoint` (point + segment), `symmetric` (points +
  segment = osa); kóty s `value` (číslo nebo výraz): `length` (segment), `distance` (points,
  nebo point + segment), `radius`, `diameter` (segment – oblouk či kružnice), `angle`
  (segments, °).
* `tangent` u čar se společným koncovým bodem řeší přímo SolveSpace, jinak (kružnice, oblouk
  bez společného bodu) přes skrytý bod dotyku.
* Promítnuté hrany dílu: `"references": {"r1": {"edge": {"face": "top", "type": "circle",
  "near": [40, 25, 3]}, "kind": "circle", "center": [40, 25], "radius": 1.7}}` – `edge` je
  hrana popsaná významem (jako u zaoblení), `kind` a souřadnice se při každém přepočtu
  spočítají znovu z dílu před skicou. Jsou pevné; vazby na ně odkazují jménem (`r1`) a body
  `r1.start`, `r1.end`, `r1.center`.

### Výběr hran (`edges`)

Hrany se vybírají **významem, ne číslem** – výběr tak platí i po změně rozměrů.

```json
"edges": "all"
"edges": {"face": "top"}                                  // hrany horní plochy
"edges": {"face": "top", "type": "circle", "radius": "D/2"} // jen vnější kružnice nahoře
"edges": {"parallel": "Z"}                                // svislé hrany
"edges": {"between": ["front", "right"]}                  // hrana mezi přední a pravou plochou
"edges": {"face": "top", "radius": 3, "near": [20, 0, 10]} // z děr R3 nahoře ta nejbližší k bodu
"edges": [{"face": "top"}, {"parallel": "Z"}]             // seznam = všechny dohromady
```

Výběr kliknutím ve 3D vytváří tyto popisy sám: zkusí nejjednodušší, který vybere přesně
kliknuté hrany. `near` (nejbližší k bodu) použije jen tam, kde nic jiného nestačí – třeba jedna
ze čtyř stejných děr. Soubory verze 1 (bez `between`, `near` a seznamu) se načtou dál.

### Uložená měření (`measurements`)

```json
{"id": "m1", "name": "Tloušťka desky", "kind": "thickness",
 "a": {"face": {"at": [60, 0, 18], "normal": [0, 0, 1], "type": "plane"}}}
{"id": "m2", "name": "Rozteč os", "kind": "parallel",
 "a": {"edge": {"face": "top", "radius": 9, "near": [37.83, 37.83, 18]}},
 "b": {"edge": {"face": "top", "radius": 9, "near": [-37.83, 37.83, 18]}}}
```

* **`kind`** – co se měří: `thickness` (tloušťka stěny v bodě `at`), `parallel` (kolmá
  vzdálenost rovnoběžných ploch/hran, rozteč os), `distance` (nejkratší vzdálenost),
  `angle` (úhel), `centers` (vzdálenost středů), `diameter`, `radius`, `length`, `area`.
* **`a`**, **`b`** – plocha `{"face": {"at", "normal", "type", "radius"}}` (nejbližší
  plocha toho druhu k bodu `at`, rovina přednostně se stejným směrem, válec se stejným
  poloměrem) nebo hrana `{"edge": …}` popsaná jako u zaoblení. Druhou věc má jen měření
  dvou věcí.
* Hodnota se do souboru neukládá – spočítá se při každém přepočtu (okno, příkazová řádka).
  Soubory verze 1–8 (bez měření) se načtou dál.

### Mapa tloušťky stěny (`thickness_map`)

```json
"thickness_map": {"limit": 4, "step": 2.5, "scale_max": 8}
```

Vše je nepovinné: `limit` = minimální dovolená tloušťka [mm] (pod ní fialově), `step` =
vzdálenost bodů [mm] (bez ní automaticky, asi 30 000 bodů), `scale_max` = horní mez barevné
škály [mm] (bez ní nejčastější tloušťka dílu). Samotná mapa se do souboru neukládá – spočítá
se znovu. Soubory verze 1–9 se načtou dál. Verze 11 přidala prvky `sweep` a `loft`,
verze 12 normalizované díly (`standard`) a ocelový profil (`steel`), verze 13 NDT studie
(`ndt`), verze 14 sonda ve studii (`device`), verze 15 úhel paprsku a počet odrazů sondy
(`beam_angle`, `bounces`), verze 16 cílové objemy a svary NDT (krok 07A), verze 17 knihovna
NDT (původ hodnot sondy, materiál pro UT; etapa 08), verze 18 plán dráhy sondy a zakázané
zóny ve studii (`plan`, `zones`; etapa 10), verze 19 nastavení PT studie (`pt`; etapa 11),
verze 20 nastavení MT studie (`mt`; etapa 12), verze 21 nastavení a projekce RT studie
(`rt`; etapa 13).
Starší soubory verze 1–20 se načtou beze změny. Uložení novou aplikací zapisuje verzi 21;
starší aplikace takový soubor neumí otevřít. Pouhé otevření původní soubor nepřepisuje.

### NDT studie (`ndt`)

```json
"ndt": {"studies": [
  {"id": "s1", "name": "UT desky shora", "method": "UT",
   "target": {"kind": "faces",
              "faces": [{"face": {"at": [0, 0, 20], "normal": [0, 0, 1], "type": "plane"}}]},
   "note": "Přímá sonda z horní plochy.", "created": "2026-10-16", "part": "3f9a1c0b7d2e4a65",
   "verified": {"by": "J. N.", "date": "2026-10-16", "part": "3f9a1c0b7d2e4a65"}}
]}
```

* **`method`** – `UT`, `PT`, `MT` nebo `RT`. **`target`** – kontrolovaná oblast:
  `"kind": "faces"` se seznamem ploch zapsaných jako u měření (bod `at`, směr `normal`, druh,
  poloměr), nebo objem/svar podle popisu níže. Bez oblasti (nebo s prázdným seznamem ploch)
  je studie neúplná.
* **`part`** – otisk dílu (16 znaků), ke kterému byla studie založena nebo naposledy
  potvrzena; jiný otisk = studie zastaralá. **`verified`** (nepovinné) – kdo a kdy ověřil,
  pro jaký otisk dílu. `name`, `note`, `created` jsou texty.
* Stav studie se do souboru neukládá – spočítá se při každém přepočtu. Neznámé položky
  ve studii jsou chyba (překlep se tak nepřehlédne). Sekce bez studií se nezapisuje.
* **`device`** (verze 14–15, nepovinné) – sonda studie, bez ní výchozí úhlová:
  `{"kind": "angle", "length": 40, "width": 20, "height": 25, "front": 12, "beam_angle": 45,
  "bounces": 1, "max_gap": 0.5, "reserve": 0}` nebo `{"kind": "straight", "diameter": 10,
  "height": 25, "bounces": 0, "max_gap": 0.5, "reserve": 0}` (mm; `front` = výstupní bod od čela,
  `beam_angle` = úhel lomu v materiálu $\beta$ [°] 1–85, `bounces` = počet odrazů 0–10,
  `max_gap` = dovolená mezera pod sondou, `reserve` = manipulační rezerva). Přiložení sondy ani
  dráha paprsku se do souboru neukládají.
* **Původ hodnot sondy a materiál pro UT** (verze 17, nepovinné): v `device` `profile` (název
  profilu), `library` (vestavěná knihovna nebo „Moje sondy“), `origins` – původ hodnot, např.
  `{"beam_angle": "measured"}` (`profile` = obecný profil, `measured` = změřeno, `entered` =
  zadáno ručně, `catalog` = katalog, `transferred` = přepočteno), `angle_material` (materiál,
  ve kterém platí `beam_angle`; bez něj platí přímo v materiálu dílu), `angle_note`, `wave`
  (`shear` / `longitudinal`), jen informativní `frequency_mhz` a `crystal_mm` a `source`.
  Studie může mít `material`: `{"name": "hliník", "c_l": 6320, "c_t": 3130, "source": "…",
  "profile": "hlinik"}` (podélná a příčná rychlost v m/s, 0 = neuvedeno). Geometrii ani výpočet
  tyto údaje nemění; úhel se do jiného materiálu přepočítá jen na pokyn.
* **Plán dráhy a zakázané zóny** (verze 18, nepovinné, etapa 10): `zones` – seznam kvádrů,
  kam sonda nesmí zasáhnout žádnou částí těla: `[{"name": "štítek", "min": [60, -20, 12],
  "max": [90, 20, 20]}]` (mm, souřadnice dílu). `plan` – plán dráhy sondy:

  ```json
  "plan": {"pattern": "auto", "row_step_mm": 5, "approach_mm": 20, "check_step_mm": 1,
    "passes": [{"face": {"at": [40, 0, 12], "normal": [0, 0, 1], "type": "plane"},
                "angle_deg": 180, "beta": 70, "bounces": 0, "pattern": "toward",
                "segments": [{"start": [50, -10, 12], "end": [22.1875, -10, 12]}]}],
    "part": "…", "target": "…", "probe": "…", "edited": false}
  ```

  Průchod = rovinná plocha (bod a směr, nikdy číslo), směr paprsku `angle_deg` (jako při
  přiložení sondy), úhel `beta` (0 = přímá sonda), `bounces` a úseky v pořadí jízdy
  (`pattern`: `toward` = k cíli a zpět, `along` = podél, `manual` = ručně). `part`,
  `target`, `probe` jsou otisky dílu, cíle a rozměrů sondy, pro které plán vznikl – jiný
  otisk = plán zastaralý; sám se nikdy nepřepočítá ani neposune. `edited` = ručně upravený.
  Výsledek ověření a pokrytí se do souboru neukládá.
* **Nastavení PT** (verze 19, nepovinné, jen u PT studie, etapa 11): `pt` –
  `{"step_mm": 2, "cleaning": "wipe", "tool_mm": 10, "fine_tool_mm": 3,
  "tool_length_mm": 100, "spray_deg": 60, "spray_limit_deg": 85, "view_deg": 30,
  "view_limit_deg": 5, "view_distance_mm": 600, "eye_mm": 50, "open_warning": 10}`.
  Chybějící hodnota = výchozí (bez `step_mm` = automaticky asi 1500 vzorků), `cleaning`
  `wipe` = otřením, `rinse` = oplachem, `fine_tool_mm` 0 = bez jemného nástroje. Úhly
  nástřiku jsou od kolmice, úhly prohlídky k povrchu. Mapa PT se do souboru neukládá.
* **Nastavení MT** (verze 20, nepovinné, jen u MT studie, etapa 12): `mt` –
  `{"spacing_mm": 100, "min_spacing_mm": 75, "pole_zone_mm": 25, "pole_mm": 20, "leg_mm": 60,
  "body_mm": 40, "body_overhang_mm": 20, "max_gap_mm": 1, "leg_angle_deg": 90,
  "step_over_mm": 10, "detect_deg": 30, "apply": true, "inspect": true, "spray_deg": 60,
  "spray_limit_deg": 85, "view_deg": 30, "view_limit_deg": 5, "view_distance_mm": 600,
  "eye_mm": 50}`, nepovinně `step_mm` a `center_step_mm` (krok sítě míst a středů jha; bez nich
  automaticky) a `ferromagnetic: true` (materiál potvrzený uživatelem – jen u nerezi
  a neuvedeného materiálu, u neferomagnetického nic nezmění). Chybějící hodnota = výchozí;
  `min_spacing_mm` = `spacing_mm` vypne zálohu menší roztečí. Mapa MT se do souboru neukládá.
* **Nastavení a projekce RT** (verze 21, nepovinné, jen u RT studie, etapa 13): `rt` –

  ```json
  "rt": {"class": "B", "focal_mm": 3, "cone_deg": 40,
    "housing_diameter_mm": 120, "housing_length_mm": 300,
    "detector_width_mm": 100, "detector_length_mm": 240, "detector_thickness_mm": 2,
    "image_step_mm": 2,
    "projections": [{"name": "P1", "aim": [0, 0, 14], "direction": [0, 0, 1],
                     "distance_mm": 500, "detector": "contact", "detector_angle_deg": 90}]}
  ```

  * `class` – třída zkoušky `A` nebo `B`. Nepovinné `step_mm` = krok sítě míst (bez něj
    automaticky).
  * Projekce:
    * `aim` – zaměřený bod,
    * `direction` – jednotkový směr od něj ke zdroji,
    * `distance_mm` – vzdálenost zdroje od zaměřeného bodu,
    * `detector` – `contact` (na ploše, kudy střední paprsek vystupuje) nebo `free` (volně,
      pak `detector_distance_mm` = vzdálenost od zdroje),
    * `detector_angle_deg` – natočení delší strany detektoru (0° = průmět osy +X),
    * nepovinné `reference_mm` – ručně zadaná jmenovitá prozařovaná tloušťka.
  * Chybějící hodnota = výchozí. Mapa RT ani náhled se do souboru neukládají.

### Cílové objemy a svary (07A, verze 16)

Krok 07A ukládá a geometricky ověřuje pomocné objemy, 07B přidává výpočet objemového
pokrytí (CLI a ModelSession) a **07C editor, náhled a objemovou mapu v okně** (popis ovládání
výše, návrh [Etapa 07C](docs/ndt/14-navrh-etapa-07c.md)).
Podrobnosti a meze výpočtu: [Etapa 07B](docs/ndt/13-navrh-etapa-07b.md).
Plošné mapy Etapy 06 fungují dál. Objemový cíl
se do výrobního dílu nepřidává a nemění jeho hmotnost, objem ani exporty.

Objemový výsledek se váží v **mm³**, plochový dál v mm² a bodový počtem bodů.
Buňky se oříznou skutečným cílem a každý jejich oddělený kus má vlastní ověřený
vnitřní bod. Jeho stav zastupuje celý kus: jde o aproximaci podle kroku cíle.
Známý objem bez spolehlivého vnitřního bodu zůstává nejistý. Součet vah se kontroluje
bez přenormování. Výsledky zůstávají pouze v paměti a zanikají se změnou zadání.

`skodacad pokryti MODEL --studie s1 --plocha X,Y,Z --rezim face --krok 5 --krok-cile 2
--konvergence --csv out/pokryti.csv` vyhodnotí cíl uložený ve studii. Adresář `out`
musí existovat. Bez `--krok-cile` je krok cíle šestina menšího rozměru průřezu.
Porovnání zdvojnásobí oba kroky; hrubý běh hledá aspoň s tolerancí krok × √0,5 (na
rovině je tolerance jen poloměr hledání, každý zásah se přesně ověří); nízký rozdíl
není zárukou přesnosti. Výstup i CSV vždy obsahují úplné upozornění UT.
Objemový pojezd po čáře (`line`) s nulovým rozevřením se odmítá, protože ideální
osy nevymezují kladný objem. Nenulové rozevření vyžaduje výslovné zadání.
Počty buněk/kusů/poloh a porovnání jsou omezené; příliš jemný výpočet doporučí
zhrubnout, nepřepne se na hrubší krok automaticky.

Ukázky k otevření přes **Soubor → Otevřít**:

- [Tupý V svar](examples/ndt/cilove_objemy/tupy_svar_objem.json): 14 613,843876 mm³.
- [Dva koutové svary](examples/ndt/cilove_objemy/koutovy_svar_objem.json): dva nezávislé cíle
  po 2 450 mm³. Díl je geometricky stejný jako původní referenční příklad.

Pomocný objem je polygonální hranol:

```json
"target": {
  "kind": "volume",
  "frame": {"origin": [0, 0, 0], "axis": [0, 1, 0], "across": [1, 0, 0]},
  "length_mm": 20,
  "profile_mm": [[0, 0], [10, 0], [10, 10], [0, 10]]
}
```

`axis` je směr délky od počátku, `across` první souřadnice průřezu; druhá souřadnice
má směr `across × axis` (zde +Z). Směry musí být nenulové a kolmé; při načtení se
normalizují. Rozměry jsou konečná čísla v mm, bez výrazů. Cíl je průnik hranolu
s materiálem dílu; souhrn odděluje zadaný a účinný objem. Prázdný průnik je neplatný.

U `kind: "weld"` se místo `profile_mm` zadává `weld_type` a `dimensions`:

- `fillet`: kladná ramena `leg_across_mm`, `leg_height_mm`.
- `butt_v` bez otupení kořene: `thickness_mm`, `angle_deg` (0–180° bez krajních hodnot)
  a nezáporná `root_gap_mm`; volitelně skupina `cap_width_mm`, `cap_top_width_mm`,
  `cap_height_mm` pro převýšení a `root_width_mm`, `root_tip_width_mm`, `root_height_mm`
  pro podkořen. Chybějící skupina má rozměry 0. Při nenulové výšce je nutná kladná
  šířka u plechu, koncová šířka 0 vytvoří trojúhelník.

Jde o nominální geometrii zadanou člověkem. Svar musí tvořit souvislé těleso a musí
se celý vejít do materiálu (objemová tolerance `max(0,000001 mm³; objem × 10⁻⁸)`);
chybějící materiál se nesmí tiše odříznout. Skutečnou hranici natavení ani tepelně
ovlivněnou oblast program neurčuje.

`ModelSession.set_ndt_volume_target(id, target)` nastaví validovaný cíl s historií
Zpět/Znovu; `ndt_target_volume(id)` vrací jeho pomocné těleso a objemy v mm³.
Po změně receptu dílu je studie zastaralá; pokud svar už nemá materiál, vazba je neplatná.
Potvrzení ponechá zadané souřadnice, nepřesune cíl na jiné místo. Změna cíle odstraní
starou mapu i ověření. Ověření objemu má navíc `verified.target`, otisk zadání cíle;
při ruční změně cíle v JSON přestane platit i při stejném dílu.

### Sestavy (`"kind": "assembly"`, verze 29–31)

Sestava je **samostatný soubor**, který skládá díly (a jiné sestavy) do poloh. Na soubory
dílů jen odkazuje a nikdy je nemění. Díly zůstávají ve své verzi (24–28); sestava má verzi 29 (s vazbami 30, s kontrolami 31).

```json
{
  "format": "skodacad", "kind": "assembly", "version": 29,
  "name": "Krabička s víčkem", "units": "mm", "parameters": {"H": 30},
  "components": [
    {"id": "krabicka", "source": {"path": "../krabicka.json"},
     "placement": {"position": [0, 0, 0], "rotation": [0, 0, 0]}, "fixed": true},
    {"id": "vicko", "name": "Víčko", "source": {"path": "dily/vicko.json"},
     "placement": {"position": [0, 0, "H + 2"], "rotation": [180, 0, 0]}}
  ]
}
```

| Klíč komponenty | Význam |
|---|---|
| `id` | jedinečné v sestavě; vše se na komponentu odkazuje jím, nikdy pořadím |
| `name` | nepovinný český název |
| `source.path` | cesta k souboru dílu nebo podsestavy **vůči složce sestavy**, oddělovač `/`, `..` jen na začátku; bez písmene disku a `\` |
| `source.fingerprint` | otisk receptu zdroje při posledním uložení (zapisuje aplikace); liší-li se, sestava upozorní „zdroj se změnil“ – nikdy neblokuje |
| `placement.position` | posun [x, y, z] v mm (čísla nebo výrazy s `parameters` sestavy) |
| `placement.rotation` | úhly [rx, ry, rz] ve stupních: otočení kolem **pevných os sestavy nejdřív X, pak Y, pak Z**; díl se točí kolem svého počátku |
| `fixed` | `true` = pevná komponenta (nehne ji tažení ani vazby) |

Bez měřítka a zrcadlení (zrcadlený díl = vlastní soubor s prvkem *Zrcadlení*). Neznámý klíč
je chyba. Komponenta, jejíž soubor chybí, nejde přečíst, má chybu přepočtu nebo vede v kruhu
zpět na sestavu, v sestavě zůstane se stavem a důvodem; součty pak platí jen pro nalezené
díly a export je jen pro úplnou sestavu. Nejvýš 8 úrovní podsestav a 1 000 komponent.
Kopie téhož dílu se počítají jednou. NDT studie, výkres a měření patří dílu, ne sestavě.
Ukázka: `examples/sestavy/krabicka_s_vickem.json`.

#### Vazby v sestavě (`constraints`, verze 30)

Vazba říká, jak k sobě dvě komponenty patří; polohu dopočítá řešič a **zapíše ji do
`placement`** (soubor jde tedy číst i bez řešiče). Sestava bez vazeb zůstává ve verzi 29,
s vazbami se ukládá ve verzi 30 (starší aplikace ji odmítne, místo aby vazby tiše zahodila).

```json
"constraints": [
  {"id": "v1", "type": "distance", "name": "Víčko na okraji", "value": "mezera",
   "a": {"component": "krabicka", "face": {"at": [0, 24, 30], "normal": [0, 0, 1], "type": "plane"}},
   "b": {"component": "vicko", "face": {"at": [0, 24, 2], "normal": [0, 0, 1], "type": "plane"}}},
  {"id": "v2", "type": "coaxial",
   "a": {"component": "deska", "face": {"at": [25, 0, 5], "normal": [-1, 0, 0], "type": "cylinder"}},
   "b": {"component": "cep", "axis": "Z"}}
]
```

| `type` | Česky | Odkazy | Co platí |
|---|---|---|---|
| `mate` | dotyk | dvě rovinné plochy (`plane`) nebo roviny dílu | plochy leží na sobě, normály proti sobě |
| `flush` | zarovnání | dvě rovinné plochy nebo roviny dílu | plochy v jedné rovině, normály stejným směrem |
| `distance` | vzdálenost | dvě rovinné plochy nebo roviny dílu | jako dotyk, ale s mezerou `value` mm (číslo nebo výraz s `parameters` sestavy) ve směru normály plochy `a` |
| `coaxial` | souosost | dvě válcové plochy (`cylinder`) nebo osy dílu | osy splývají (posun podél osy a otočení kolem ní zůstanou volné) |

Odkaz `a` / `b` má `component` (id komponenty) a právě jedno z: `face` – plocha **významem
v souřadnicích dílu té komponenty** (`at` bod na ploše, `normal` směr ven z materiálu,
`type` `plane` nebo `cylinder`; bez poloměru, aby se díra našla i po změně průměru), `plane`
– základní rovina dílu `XY` (normála +Z), `XZ` (normála −Y, jako u skic) nebo `YZ` (+X),
`axis` – osa dílu `X`, `Y` nebo `Z`. U podsestavy se plocha hledá na celé podsestavě v jejích
souřadnicích. Vazba spojuje dvě různé komponenty; `value` má jen vzdálenost; neznámý klíč je
chyba; smazání komponenty smaže i její vazby.

Řešení: polohy co nejblíž dnešním – co vazby neurčují (posun do strany, otočení kolem osy),
zůstane. Díl, který leží obráceně, řešič zkusí obrátit o 180°. **Pevná** komponenta se nehne
nikdy, komponenta s polohou zadanou **výrazem** také ne (vazba, která by s ní musela hýbat, je
spor s radou „nahraď výraz číslem“). Skupina vázaných komponent bez pevné drží první z nich.
Vazby, které si odporují (zbytek nad 0,000001 mm), aplikace **nepřijme**; když spor vznikne
změnou souboru dílu, polohy zůstanou uložené, vazby jsou „ve sporu“ a sestava je neúplná.
Stav komponenty: *pevná*, *plně určená*, *volná: 2 posuny, 1 otočení*, *ve sporu*.
Ukázka: `examples/sestavy/krabicka_s_vazbami.json`.

#### Kontroly sestavy (`checks`, verze 31)

Mez vůle a přijaté kolize. Sestava bez `checks` zůstává ve verzi 29 nebo 30; s `checks` se
ukládá ve verzi 31 (starší aplikace ji odmítne, místo aby přijaté kolize tiše zahodila).
Výsledek kontroly se neukládá – je to jen pohled.

```json
"checks": {
  "clearance": 0.3,
  "accepted": [
    {"a": ["deska"], "b": ["sroub_1"], "volume": 12.959,
     "note": "závit M3 – díra je jen vrták pod závit (2,5 mm)"}
  ]
}
```

| Klíč | Význam |
|---|---|
| `clearance` | mez vůle v mm (kladné číslo, výchozí 0,5); hlásí se dvojice blíž než mez, které se nedotýkají |
| `accepted[].a`, `.b` | dvě různé komponenty jako **cesta id** od kořene sestavy (kopie v podsestavě: `["pod", "sroub_1"]`); pořadí `a`/`b` nehraje roli |
| `accepted[].volume` | objem průniku v mm³ při přijetí; liší-li se nový objem o víc než 1 % (nejméně 0,01 mm³), je to znovu kolize |
| `accepted[].note` | nepovinná poznámka, proč je kolize v pořádku |

Neznámý klíč je chyba, stejná dvojice smí být přijatá jen jednou; smazání komponenty smaže
i přijaté kolize, kterých se týká. Ukázka: `examples/sestavy/deska_se_sroubem.json`.

### Materiály

`ocel`, `nerez`, `litina`, `hlinik`, `mosaz`, `med`, `titan`, `pla`, `petg`, `abs`
(diakritika a velká písmena nevadí).

## Pro vývoj

Pravidla projektu, architektura a plán jsou v [CLAUDE.md](CLAUDE.md). Podkladové výzkumy
jsou ve složce [docs/](docs/).

Další vývoj řídí [schválená roadmapa P0–P8 a NDT-17](docs/roadmapa-vyvoje.md).
P0 obsahuje [audit, rizika, baseline a ruční zkoušky](docs/p0-audit-a-overeni.md) a je sloučené v PR #30.
Autor 20. 10. 2026 schválil [P1.1 — smlouvu geometrických operací](docs/p1-1-navrh-smlouvy-geometrickych-operaci.md),
rozhodnutí D1–D7 a matici budoucích testů (sloučené PR #31). P1.1 je dokončeno bez změny chování aplikace.
Autor 20. 10. 2026 schválil [P1.2A — společnou kontrolu geometrie](docs/p1-2a-navrh-spolecne-kontroly-geometrie.md)
včetně bodů A1–A7; plán je sloučený v PR #32. Implementace A.1–A.3 je sloučená v
[PR #33](https://github.com/JendaNDT/SkodaCAD/pull/33) jako `edf9b8e`;
[protokol autora z 21. 10. 2026](docs/p1-2a-rucni-overeni-macos-2026-10-21.md)
dokládá sedm vedených zkoušek na Macu a samostatný souhlas se sloučením.
[Konkrétní návrh P1.2B — transakce celého kontextu prvku](docs/p1-2b-navrh-transakce-kontextu.md)
schválil autor 21. 10. 2026: B1–B7, kroky B.1–B.3 a matice T01–T14.
Plán je sloučený v PR #34 (`cbf19b1`); [implementace a ověření](docs/p1-2b-overeni.md)
jsou dokončené a sloučené v [PR #35](https://github.com/JendaNDT/SkodaCAD/pull/35)
jako `3a8deff`. [Protokol autora z 22. 10. 2026](docs/p1-2b-rucni-overeni-macos-2026-10-22.md)
dokládá 17 vedených kontrol na Macu a samostatný pokyn ke sloučení.
[Návrh P1.3 — bezpečné geometrické odkazy](docs/p1-3-navrh-bezpecnych-referenci.md)
schválil autor 22. 10. 2026 slovy „ok, schvaluji vše“: C1–C8, C.1–C.3 a S01–S20.
Návrhové PR #36 je sloučené (`c46d0e2`); implementaci autor výslovně přijal ke sloučení
v [PR #37](https://github.com/JendaNDT/SkodaCAD/pull/37), nyní na `main` jako `f5fbe2c`.
[Evidence včetně obou vydání z main](docs/p1-3-overeni.md#sloučení-a-vydání-z-main)
rozlišuje 1 451 testů, self-testy stažených balíčků a meze ručního ověření.
[Záznam převzetí zkoušek agentem z 23. 10. 2026](docs/p1-3-agent-overeni-macos-2026-10-23.md)
zůstává protokolem skutečně provedených kontrol.
[P1.4 — export a NDT při chybě modelu](docs/p1-4-navrh-exportu-a-ndt-pri-chybe.md)
autor 24. 10. 2026 schválil slovy „ok, schvaluji“: E1–E9, kroky E.1–E.4,
E01–E22. Implementace je v [PR #39](https://github.com/JendaNDT/SkodaCAD/pull/39);
[evidence](docs/p1-4-overeni.md) a [nativní protokol](docs/p1-4-agent-overeni-macos-2026-10-24.md) uvádějí
hotové kroky a meze ověření. Autor schválil sloučení; P1.4 je na main jako `e7f9ac6`.
[Obě vydání z main](docs/p1-4-overeni.md#sloučení-a-vydání-z-main) prošla
1 549 testy na každém systému a kontrolami stažených balíčků. Chybný recept zůstane
k opravě, exporty/NDT vyžadují celý aktuální úspěšný model.
[P1.5 — přijetí bezpečné geometrie](docs/p1-5-navrh-prijeti-bezpecne-geometrie.md)
autor 24. 10. 2026 schválil slovem „schvaluji“: F1–F9, kroky F.1–F.4 a P01–P24.
Inventura a 7 cílených regresí jsou hotové; celý místní běh má 1 556 úspěšných případů.
[Evidence P1.5](docs/p1-5-overeni.md) a [nový nativní protokol](docs/p1-5-agent-overeni-macos-2026-10-24.md)
oddělují místní kontroly, 15 kroků skutečného okna a otevřená omezení.
Konečné CI a balíčky dokládá při předání [PR #41](https://github.com/JendaNDT/SkodaCAD/pull/41).
Produkční chování je zachované; přijetí P1 a sloučení vyžadují další pokyn autora.
P2 a změna formátu vyžadují vlastní schválení. Model zůstává ve verzi 22.
Měřicí evidence vzniká příkazem `python tests/benchmark_p0.py --output out/p0-baseline.json`
(výstup musí být nový soubor).

```bash
pip install -e ".[dev,gui]"   # jádro, okno a nástroje pro vývoj
# Jen macOS, před prvním spuštěním ze zdrojů (Xcode Command Line Tools):
python packaging/build_macos_accessibility.py
pytest -q                     # testy (ověřují geometrii výpočtem objemu)
ruff check src tests          # kontrola kódu
skodacad-gui                  # spustí okno (bez argumentu otevře ukázku příruby)
skodacad-gui --self-test zprava.txt   # kontrola aplikace bez obsluhy
```


## Konstrukční návrhy pro NDT (etapa 15B – okno a výpočet)

ŠkodaCAD umí připravit a porovnat **kopie** dílu s různými číselnými parametry a
geometrickým posouzením UT/PT/MT/RT. Srovnává geometrickou přístupnost a pokrytí, **ne**
pevnost, technologičnost ani detekovatelnost vad. Původní díl se po výpočtu nikdy sám
nezmění; použití varianty vyžaduje výslovné rozhodnutí konstruktéra.

**Model verze 22:** do oddílu `ndt` se může uložit `design` s cílovou studií,
povolenými parametry a hodnotami, zamčenými měřeními a podmínkami. Výsledky
výpočtu jsou jen pohled (neukládají se). Verze 1–21 se stále načtou.

Referenční model: `examples/ndt/navrh_kapsa.json`, včetně podmínky
stěny kapsy nejméně 15 mm.

Příklady v příkazové řádce:

```bash
skodacad navrh examples/ndt/navrh_kapsa.json --slozka out/navrh
skodacad navrh examples/ndt/navrh_kapsa.json --studie s3 --parametr a=40,60,80,90,100 --podminka "m1>=15:stena" --bez-overeni --slozka out/navrh
skodacad navrh examples/ndt/navrh_kapsa.json --parametr a=40:100:20 --zamek m1 --ulozit-zadani
```

`--ulozit-zadani` jako jediná volba výslovně zapisuje **zadání** do původního
souboru modelu. Bez ní je i samotné spuštění CLI pouze čtecí a výpočetní operace.
Výstupem `--slozka` jsou `navrh.html` a `varianty.csv`.
Další volby zobrazí `skodacad navrh --help`.

**Grafické ovládání:** Otevři model s NDT studiemi (např. NDT – referenční díly →
NDT 10 – Konstrukční návrh kapsy pro jho), potom **NDT → Konstrukční návrh…**.
Klikni na **Zadat návrh…** (výběr parametrů, mezí, zamčených rozměrů), na **Odhad doby**
a **Spustit návrh**. Tabulka porovnává varianty; klik na variantu zobrazí ve 3D její
geometrii s původním dílem průhledně. Výsledek stále nic nemění na otevřeném dílu.

**Použít variantu…** vyžaduje výslovné potvrzení a jeden krok Zpět vrátí původní
parametry. **Uložit variantu jako…** vytvoří nový soubor a původní nikdy nepřepíše.
Z panelu jde uložit zprávu HTML/CSV/PDF a obrázky náhledů variant. Srovnání není
ověřením pevnosti, technologie výroby, normové způsobilosti ani detekovatelnosti vad.

Výpočetní jádro a příkazová řádka jsou hotové ve fázi 15A.2; okno a export PDF jsou
součástí etapy 15B. Podle schváleného plánu se všechny změny před sloučením ověřují na
Windows i macOS.

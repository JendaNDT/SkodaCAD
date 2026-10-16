# Dokumentace modulu NDT — ŠkodaCAD

> Podklad ke konzultaci a plánování. Nejde o schválený NDT postup ani o potvrzení detekovatelnosti vad.

Škoda CAD | Modul NDT
Technický a produktový návrh pro konzultaci před implementací

Pracovní návrh • 16. října 2026 • Verze 0.1 • Určeno k připomínkám, nikoli ke schválení kontrolního
postupu

Cíl: umožnit konstruktérovi na 3D modelu ověřovat praktickou proveditelnost nedestruktivní
kontroly (UT, RT, PT a MT) a hledat vhodné přístupové polohy ještě před výrobou.



1. Rozhodnutí a hranice projektu
-   Primární výstup: mapa geometrické přístupnosti a orientačního pokrytí zvolené kontrolované
    oblasti, konkrétní překážky a srozumitelná doporučení.
-   Pro UT bude uživatel pohybovat virtuální sondou po součásti a sledovat zjednodušenou dráhu či
    obálku svazku v řezu i ve 3D.
-   Pro RT se bude polohovat zdroj a detektor; pro PT se bude analyzovat přístup pro přípravu,
    nanesení, odstranění a vyhodnocení; pro MT orientace magnetizace a přístup zařízení.
-   Konstrukční změny se nejprve pouze navrhují jako alternativy; žádná se automaticky
    nepromítne do originálního modelu.
-   Offline výpočty mají přednost. Externí API ani jazyková AI nejsou pro první verzi potřeba.

Nezaměňovat: geometrické zasažení oblasti, fyzikální možnost získat použitelný signál,
detekovatelnost konkrétní vady a normovou způsobilost postupu jsou čtyři různé otázky. Výsledek
aplikace musí vždy jasně uvádět, kterou z nich vyhodnocuje.



2. Co už Škoda CAD nabízí
Podle README repozitáře JendaNDT/SkodaCAD (čteno 16. 10. 2026) používá projekt parametrické
jádro Open CASCADE prostřednictvím build123d, vytváří model z JSON, nabízí 3D výběr ploch a hran,
měření vzdáleností a tloušťky a barevnou „Mapu tloušťky stěny (NDT)“. To představuje vhodný
výchozí základ pro volbu kontrolovaných ploch, geometrické dotazy a barevné překryvy. Neověřoval
jsem implementaci jednotlivých modulů ve zdrojovém kódu; rozhraní je třeba nejprve zmapovat.

Zásada integrace: výpočetní NDT modul oddělit od tvorby a editace parametrického tělesa. NDT
výsledky musí být navázané na konkrétní verzi geometrie a po změně modelu přepočítány či jasně
označeny jako neplatné.



3. Uživatelský scénář
-   Otevřít díl, označit kontrolovaný svar, objem nebo povrch a zvolit „NDT → Nová studie“. U svaru
    může být zprvu cílová oblast vyznačena ručně; samotný CAD model totiž nemusí znát polohu
    svaru ani jeho kořen.
-   Vybrat metodu a profil: materiál, požadovaná oblast, parametry sondy / zařízení a omezení podle
    kontrolního postupu.

                        
-     Pohybovat virtuálním zařízením myší, uchovávat polohy a spouštět automatické vyhledávání
      dostupných míst.
-     Přepnout 3D zobrazení, řez a legendu: geometricky pokryto, nepokryto, nepřístupné,
      nevyhodnoceno a nejisté.
-     Zobrazit důvod problému: kolize tělesa sondy, nedostatek dráhy skenování, nepříznivý dopad,
      překryv expozice, špatný přístup pro čištění apod.
-     Vygenerovat varianty alternativního přiložení a později návrhy úprav geometrie. Exportovat
      zprávu se vstupy a upozorněním na omezení.



4. Společné technické jádro


4.1 Geometrie a reprezentace
-     Využít přesné B-Rep těleso z Open CASCADE pro klasifikaci bodu vůči materiálu, průsečíky úseček
      a křivek s povrchem, normály, vzdálenosti a testy kolizí.
-     Připravit volitelnou síť / vzorky pro rychlé barevné zobrazení; nenechávat vizuální
      trojúhelníkovou síť jako jedinou autoritu pro kritická rozhodnutí.
-     Odděleně modelovat měřený díl, definovaný cílový objem či plochu, tělo sondy nebo zdroje a
      detektoru, obálku přístupu a historii skenování.
-     Pro první verzi začít s jedním pevným dílem a jednoduchým přístupem bez robotické kinematiky.
      V sestavách přidat později kolize i se sousedními komponentami.



4.2 Datový model studie
    Entita                                               Povinný obsah

    NDT studie                                           ID, metoda, ID/otisk geometrie, název, verze
                                                         nastavení, datum, jednotky
    Kontrolní oblast                                     Typ: povrch/objem; odkazy na plochy nebo
                                                         lokální souřadnice; toleranční pravidla
    Vybavení                                             Geometrie a rozměry zařízení, místo kontaktu,
                                                         orientace, nastavení metody
    Skenovací dráha                                      Seznam poloh a orientací, krok, čas či index,
                                                         informace o kolizích
    Výsledek                                             Typ pokrytí, přijaté předpoklady, nerozhodnuté
                                                         oblasti, důvody omezení



Uložené odkazy na plochy se mohou po parametrické změně rozpadnout. Využít obdobné sémantické
rozpoznávání ploch, které projekt popisuje u měření, ale vždy zkontrolovat jednoznačnost
znovunalezené plochy.




                          
4.3 Výkonnost a přesnost
-   Interaktivní náhled počítat zjednodušeně a rychle; přesnější celkové pokrytí spouštět jako
    samostatnou úlohu s možností zastavení.
-   Zaznamenat krok vzorkování a toleranci. Procenta pokrytí mají význam jen společně s
    vymezením cílové oblasti a rozlišením výpočtu.
-   Po každé změně parametrů nesmí zůstat na obrazovce stará mapa jako platný výsledek; označit ji
    „zastaralá“ nebo automaticky obnovit.
-   U každé analýzy musí existovat stav: úspěšně vypočteno, částečné, nespolehlivé, chyba vstupu.
    Nepřekrývat „neznámé“ červenou barvou jako prokázanou nepřístupnost.



5. Ultrazvuková kontrola (UT)

5.1 První realizovatelná verze
-   Ruční přikládání virtuální přímé i úhlové sondy na volitelný povrch; test, zda se celé tělo sondy
    dotýká nebo může přiložit v dovolené toleranci a zda nenaráží do geometrie.
-   Nastavení obrysu a rozměrů sondy, nominálního úhlu v materiálu, druhu vlny, frekvence,
    rychlosti zvuku v materiálu a max. zvukové dráhy. Výchozí hodnoty nezaměňovat za skutečně
    kalibrované parametry.
-   Interaktivní řez rovinou svazku a průhledný model; střední paprsek, volitelná geometrická
    obálka a průsečíky s rozhraními.
-   Při přechodu mezi prostředími použít Snellův zákon pro zvolený typ vlny; u šikmých ploch a
    konverzí módů uvádět limity zjednodušeného modelu.
-   Záznam poloh sondy a orientační označování vzorkovaných buněk cílového objemu jako
    geometricky protnutých obálkou. Samotné protnutí není průkaz detekce vady.
-   Výpis omezení: sonda se nevejde, není skenovací dráha, svazek oblast mine, vstupní plocha má
    nepříznivou geometrii.



5.2 Co první verze nesmí předstírat
Svazek není nekonečně tenký paprsek; šíření závisí na typu měniče, apertuře, frekvenci, vazbě,
zakřivení, útlumu, rozptylu, orientaci vady, změnách módu a dalších jevech. Jednoduchá
geometrická obálka proto nemůže poctivě vypočítat pravděpodobnost detekce ani garantovat
normové pokrytí. Zobrazení odrazů navíc nesmí vytvářet dojem skutečného A-scanu.



5.3 Následující úrovně UT
-   Úroveň B: vícenásobný odraz od hranic na základě geometrické optiky, zjednodušené ztráty a
    rozsah svazku, více sond a vyhodnocení skenovací dráhy.
-   Úroveň C: pokročilé výpočty akustického pole a simulace vad až po samostatném fyzikálním
    ověření, například porovnáním se známými referenčními konfiguracemi.
-   PAUT/TOFD jako zvláštní pozdější profily; nikdy je neschovat pod jednu univerzální „UT sondu“.


                        
6. Radiografická kontrola (RT)
-   Zdroj záření: poloha, směr, ohnisko; detektor či film: poloha, rozměry, citlivá plocha a orientace.
    První fáze počítá geometrii, ne plnohodnotný vznik RT obrazu.
-   Zkoušet různé projekce skrz model a vyznačovat části cílového objemu, které leží v promítaném
    svazku a ve vymezené oblasti detektoru.
-   Počítat geometrické zvětšení a neostrost z velikosti ohniska a vzdáleností, minimální a maximální
    prozařovanou tloušťku v dané projekci, překrytí geometrií a kolize zařízení.
-   Volitelně promítnout rozložení délek průchodu materiálem jako ilustrativní mapu; skutečný
    kontrast, rozptyl, šum, energie spektra, absorpce, detektor a citlivost na vadu vyžadují
    pokročilejší model.
-   Oddělit „geometricky proveditelné“ od „splňuje expozici, citlivost a normu“. Aplikace nesmí
    sloužit k určování radiačně bezpečných pracovišť bez samostatně validovaného výpočtu a
    posouzení.



7. Kapilární kontrola (PT)
-   Analyzovat přístupnost skutečného povrchu pro čištění, nanesení penetrantu, odstranění
    přebytku, nanesení vývojky a vizuální prohlídku. Každá operace má jiný požadovaný prostor.
-   Modelovat jednoduché manipulační obálky nástroje či aplikační trysky a pozorovací směry;
    hledat úzké kapsy, slepé otvory, skryté styčné plochy a překážky výhledu.
-   Barevná mapa: dostupné pro všechny zadané operace / omezené / nepřístupné / bez údaje. K
    tomu textové vysvětlení příčiny.
-   Bez znalosti materiálu, stavu povrchu, kontaminace, teploty a konkrétního postupu nevyvozovat
    smáčivost, schopnost vzlínání, odstranitelnost penetrantu ani citlivost na vady.



8. Magnetická prášková kontrola (MT)
-   Nejprve ověřit, zda materiál vůbec spadá mezi feromagnetické, a evidovat přístup pro pólové
    nástavce, kontakty či cívku a pozorování povrchu.
-   Pro vybraný typ magnetizace zobrazit pouze orientační směr magnetického pole a problematiku
    orientace očekávaných vad. Pro různé směry indikací je obvykle nutné více směrů magnetizace.
-   Skutečné rozložení magnetické indukce, dostatečná intenzita magnetizace, rozptylová pole a
    citlivost na indikace z pouhé geometrie spolehlivě nevyplývají.
-   Pokročilý model by mohl používat magnetostatický výpočet s vlastnostmi materiálu a okrajovými
    podmínkami; v první verzi jde o plánovací pomůcku, ne o potvrzení způsobilosti MT.



9. Automatická doporučení a změny geometrie
Nejprve řešit alternativní techniku kontroly bez úpravy dílu: změnu přístupové plochy, směru,
velikosti vhodné sondy, polohy zdroje a detektoru či krok skenování. Teprve potom geometrickou
změnu a vždy v samostatném návrhu.

Mechanismus optimalizace: vymezit parametry, které konstruktér dovolí změnit (např. šířka
manipulační plochy, poloměr přechodu nebo poloha žebra), určit zakázané oblasti a případné

                          
výrobní/pevnostní limity, vygenerovat kandidáty, přepočítat geometrii, zkontrolovat kolize a NDT
dostupnost a vybrat nejlepší kompromis.

Příklad cíle: zvýšit geometrické pokrytí označeného objemu při co nejmenší změně objemu a při
zachování výslovně zamknutých rozměrů. Hranice 95 % je případný uživatelský cíl, nikoli
automaticky platná normová podmínka.

Pro parametrický model lze využít prohledávání variant, bezderivační optimalizaci či jednoduchý
heuristický výběr. Jazyková AI může návrhy vysvětlovat, ale přesnost a platnost výsledku musí
vznikat z výpočtového jádra. U geometrie neznámého původu může být obtížné určit, jaký
konstrukční prvek se smí měnit; v takovém případě jen nabídnout doporučení bez automatické
editace.

Kontrola pevnosti, únavy, technologie výroby a schválení změny zůstává mimo NDT modul. Výsledky
musí nést výrazné označení „Návrh ke konstruktérskému posouzení“.



10. Postup vývoje
    Etapa                           Funkční výsledek                  Akceptační podmínka

    0 – analýza                     Napojení na stávající 3D          Bez zásahu do současného
                                    zobrazení, model a měření         ovládání, jasné oddělení
                                                                      modulu
    1 – UT interakce                Virtuální sonda, kolize, řez a    Sonda reaguje na model;
                                    základní průsečík                 chybná konfigurace je zřetelně
                                                                      hlášena
    2 – UT pokrytí                  Vymezení kontrolní oblasti,       Výsledek lze reprodukovat se
                                    skenování, mapa a protokol        stejnými parametry
    3 – UT varianty                 Hledání jiných přístupů a         U každé varianty uvedeno
                                    poloh sondy                       zdůvodnění a omezení
    4 – RT geometrie                Zdroj, detektor, projekce,        Správnost ověřena na
                                    tloušťky, neostrost               jednoduchých tělesech
    5 – PT přístupnost              Fáze přípravy a aplikace,         Vysvětlené důvody
                                    přístup nástrojů                  problémových ploch
    6 – MT plánování                Materiál, přístup vybavení,       Nezaměňuje orientační směr
                                    směry magnetizace                 za výpočet pole
    7 – optimalizace                Návrhy změn odvozené z            Původní díl beze změny,
                                    parametrického modelu             srovnání variant




11. Minimální testovací sada
-     Rovná deska: přímá sonda, jednoduchý průchod a měřitelná vzdálenost; parametrická změna
      tloušťky.
-     Svarový spoj s přístupem jen z jedné strany: označená cílová oblast a porovnání dvou úhlů.

                         
-   Žebro těsně u svaru: kolize těla úhlové sondy a výpočet minimální požadované manipulační
    plochy.
-   Trubka s lokálním úbytkem stěny: oddělení současné mapy tloušťky od geometrického pokrytí
    UT.
-   RT přes dvě různé tloušťky: mapování délky průchodu a změna zvětšení při posunu detektoru.
-   PT hluboká úzká kapsa: mechanicky nepřístupná plocha pro odstranění přebytku penetrantu.
-   MT feromagnetická a neferomagnetická varianta: upozornění na nevhodný materiál a na
    chybějící druhý směr magnetizace.
-   Rozpad vazby na vybranou plochu po změně modelu: výsledek se nesmí tvářit jako platný.



12. Uživatelské rozhraní a protokol
-   Jeden panel „NDT“ s výběrem metody; vlevo vstupy, ve 3D model a zařízení, vpravo výsledky.
    České termíny, nápověda u parametrů a rychlá výchozí konfigurace.
-   Vizuální legenda odlišuje pokryto, nepokryto, nepřístupné, nejisté a nevypočtené. Neznámé
    nesmí vypadat jako dobrý výsledek.
-   Uložit studii odděleně od konstrukčních prvků; umožnit ji pojmenovat, duplikovat a porovnat s
    jinou variantou.
-   Protokol: metoda, model/verze, vybraná oblast, materiál, všechny parametry, krok výpočtu,
    polohy zařízení, mapa výsledků, varování, čas vytvoření a verze výpočetního modulu.
-   Viditelné upozornění: „Nástroj slouží k předběžnému posouzení proveditelnosti NDT.
    Nenahrazuje kvalifikovaný postup, normové vyhodnocení ani reálnou kontrolu.“



13. Rizika a rozhodnutí před implementací
-   Neurčená poloha svaru či kontrolovaného objemu: potřeba ruční definice cílové oblasti.
-   Topologické změny parametrického modelu: trvalé odkazy na povrchy jsou technicky náročné.
-   Kolize sondy: zohlednit kontaktní plochu a možnost skutečného ustavení; samotný bod dotyku
    nestačí.
-   UT fyzika: obálka svazku, odrazy a skutečná detekční schopnost mají odlišnou míru ověření.
-   Čas výpočtu: interaktivita jen s přiměřeným zjednodušením; podrobný výpočet asynchronně.
-   Normy: požadavky se liší materiálem, výrobkem, metodou a edicí normy; nevkládat automatické
    tvrzení „vyhovuje“ bez výslovně ověřených pravidel.
-   Kompetence: potvrzení správnosti NDT postupu náleží kvalifikované osobě; schvalování
    konstrukčních úprav odpovědné konstrukci.



14. Konkrétní zadání pro první implementaci v Claude Code
Vybuduj izolovaný prototyp „NDT → UT – geometrický náhled“ nad existujícím 3D tělesem Škoda
CAD. Nezasahuj do parametrického jádra více, než vyžaduje čtecí rozhraní. Přidej volbu
kontrolované plochy/oblasti, jednoduchý model přímé a úhlové sondy se zadanými rozměry,
přichycení k povrchu, pohyb po dostupné ploše, kolizní test, střední dráhu svazku uvnitř materiálu,
jednoduchý řez a uložení konfigurace studie. Výsledek označ jako geometrický náhled bez tvrzení o
detekovatelnosti. Vytvoř automatické testy na desce, žebru a změně rozměru; nepokračuj k
                       
automatickým úpravám modelu, dokud interakce a geometrie neprojdou testy. Zachovej české UI a
dosavadní ovládání aplikace.



15. Kritérium úspěchu prvního milníku
Konstruktér otevře jednoduchý model se žebrem u svaru, zvolí virtuální úhlovou sondu a pohybem
myší okamžitě pozná, kde ji lze fyzicky přiložit, kde dochází ke kolizi a jaká část ručně určeného
kontrolovaného objemu leží v orientačně zobrazené dráze či obálce svazku. Program jasně ukáže, co
neví. Výsledek po změně modelu nezůstane falešně platný.

Stav dokumentu: NÁVRH K PŘEČTENÍ A PŘIPOMÍNKÁM. Bez zápisu na GitHub, bez změny
zdrojového kódu.




                        
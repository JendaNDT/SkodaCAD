# P7.8 – sestavy z Dokumentů v macOS

Datum: **1. 11. 2026**. Navazuje na [P7.7](p7-7-otevirani-dokumentu-macos.md).

## Nález

Skutečná sestavená aplikace spuštěná přes Launch Services přijala v systémovém
panelu `examples/sestavy/krabicka_s_vickem.json`. Před zobrazením sestavy se
hlavní vlákno zablokovalo v Python `os_listdir` → `__opendir2` →
`__open_nocancel`. `assembly_build.locate` vypisuje složky kvůli kontrole
velikosti písmen cest. Výběr souboru sestavy nepředává přístup k celé složce
projektu a jejím ostatním souborům. Pomocný proces přitom čekal na práci;
nejde o výpočet geometrie. Vzorky jsou v `out/p7-assembly-documents/`.

## Změna

Interaktivní **Otevřít** v hlavním okně i okně sestavy na macOS před načítáním
komponent požádá o společnou **složku projektu**. Před jejím výběrem se přečte
jen zvolený soubor sestavy; návrh složky se určí lexikálně ze zápisů cest,
bez výpisu adresářů a čtení dílů. Složka musí obsahovat sestavu i přímo
odkazované zdroje, jinak otevření nepokračuje. U podsestav má autor vybrat
celý projekt včetně jejich zdrojů, nikoli pouze podsložku hlavní sestavy.

Zrušení ani chybný výběr nemění otevřený model. Potvrzená složka se pamatuje
pouze v procesu a pokrývá další sestavy stejného projektu. Po novém spuštění
se vybírá znovu. Windows a Linux nemají další panel. Ukázky načítané přímo
z balíčku, neinteraktivní API a self-test nejsou náhradou této nativní zkoušky.
Nemění se formát receptu, výpočty sestav ani systémová nastavení oprávnění.

Opora: [Apple NSOpenPanel](https://developer.apple.com/documentation/appkit/nsopenpanel),
[Apple – What's New in File Management and Quick Look](https://developer.apple.com/videos/play/wwdc2019/719/)
a [Qt QFileDialog – getExistingDirectory](https://doc.qt.io/qt-6/qfiledialog.html#getExistingDirectory).

## Ověření

Regrese pokrývají obě cesty Otevřít, zrušení, nevhodnou složku, relativní
odkaz `../`, další projekt a zachování zdrojových dat. U správně načtené
krabičky se kontroluje šest platných komponent, objem **31309,29 mm³**
a obálka **(−40, −25, −3) až (40, 25, 32) mm**. Úplný vzorec pro součet
krabičky, víčka a čtyř válcových nožiček hlídá také test A16 sestav.

Rozhodující místní průchod: přes systémový panel vybrat sestavu z Dokumentů,
vybrat složku projektu, ověřit šest dílů bez chyb, uložit kopii do jiné složky
a znovu ji otevřít. Zkontrolovat přepočtené relativní cesty, stejné zdroje,
geometrii i nezměněné původní soubory. Skutečný průchod a jeho meze jsou
evidovány samostatně; výsledky testů nejsou tvrzením o ruční přejímce P5.

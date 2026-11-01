# P7.16 – nastavitelná míra průhlednosti

Datum: **1. 11. 2026**. Navazuje na P7.15.

## Ovládání

V pravém panelu komponenty je pole **Průhlednost 0–100 %**. Číslo lze zadat
klávesnicí a potvrdit Enterem nebo ztrátou fokusu, případně měnit šipkami.
**0 %** vrátí plný vzhled, **100 %** zcela průhledné plochy. Obrysy a výběr
geometrie zůstávají i při 100 %. Pro skrytí včetně obrysů dál slouží H.

Hodnota platí pro vybranou kopii dílu, nikoli pro všechny výskyty souboru.
U podsestavy se zadáním procent sjednotí celá větev, včetně aktuálně skrytých
dílů. Při různých hodnotách potomků pole ukáže **Různé**. Tento mezistav je
pouze zobrazení; záporná míra se do pohledu nikdy nepřenese. Bubliny ve stromu
uvádějí konkrétní hodnotu nebo rozsah, souhrn rozsah viditelných průhledných dílů.

**T** nebo checkbox průhlednost vypne a znovu obnoví poslední kladné míry
jednotlivých dílů. Výchozí míra je 70 %. Vypnutí celé podsestavy nezapomene
rozdílné míry dětí. Opětovné zapnutí sjednotí jejich zapnutí a obnoví jejich míry;
zadání čísla sjednotí i míru. Také **Zrušit průhlednost všech dílů** zachová
zapamatovaná procenta pro další zapnutí. **Zobrazit vše** míry nemění.

## Data a životnost

Zapnutí i zapamatované míry jsou stav okna, mimo recept, historii a profil.
Přepnutí zachová kameru, výběr ploch pro vazby, rozepsanou polohu i vazbu.
Geometrie, součty, kontroly, kusovník a exporty používají celý model.
Formát souboru a závislosti se nemění.

Přepočet, úpravy a Uložit jako zachovají míry podle existujících id.
Nový potomek zdědí míru nejbližšího předka. Odstranění komponenty zahodí
její vlastní pravidla; po Zpět zdědí platná pravidla předka, případně výchozí
stav. Zrušené či neúspěšné otevření pravidla zachová. Úspěšné otevření nebo
založení dokumentu vyčistí zapnutí i zapamatované míry.

## Provedení a ověření

Viewer dostává dvojice část/alfa 0…1 a mění pouze vlastní materiály stejného
AIS. Neplatnou míru odmítne před změnou prezentace, nuly se kreslí plně.
Při synchronizaci pole se blokují signály. `valueChanged` zachytí i nativní
AX ovládání, vypnuté keyboardTracking brání přenosu rozepsaného čísla do pohledu.

Kontrola aktivace okna už při nezměněných zdrojích a receptu zachová identitu
zobrazeného výsledku. Původně přepočet vytvořil nové kopie tvarů bez překreslení
AIS; materiály a výběr pak mohly odkazovat na jiné tvary. Změněný zdroj nebo
recept nadále vyvolá překreslení. Regrese ověřuje oba případy a změnu fyzického
objemu dvou kopií podsestavy 24 000→36 000 mm³ po změně zdrojového dílu.

Testy ověřují různé míry samostatných kopií, mezistav a sjednocení podsestavy,
dědění, 0/100 %, obnovení přes T/AX, uložení a import úplného STEP, životnost
i zachování výběru, polí, historie a fyzické geometrie. Test vieweru čte skutečné
materiály AIS a kontroluje objem i světovou obálku.

Nativní self-test zadá 35 % klávesnicí, přepne 0/100/T a ověří skutečný výběr
průhledné plochy. Druhá komponenta dostane nezávisle 85 % a přes QAccessible
55 %. Ověří materiály po skrytí/zobrazení a stálou kameru, AIS, objem a recept.
Stávající nativní zkoušky checkbox/AX/T, obrazů a lišty 1024/960 zůstávají aktivní.

Protokoly a snímky: `out/p7-transparency-level/`; úplné výsledky Windows/macOS
a stažených balíčků patří do implementačního PR. P7.4 (autorská přejímka)
zůstává otevřená.

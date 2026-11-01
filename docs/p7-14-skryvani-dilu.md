# P7.14 – samostatné skrývání dílů

Datum: **1. 11. 2026**. Navazuje na izolaci P7.13.

## Ovládání

Zaškrtávátko u názvu komponenty ovládá její ruční viditelnost. Na liště
i v nabídce Zobrazení je také **Skrýt / Zobrazit vybrané (H)**. U podsestavy
se příkaz týká všech potomků. Při částečné viditelnosti ukazuje rodič mezistav;
jeho zaškrtnutí znovu zobrazí celou větev. Skryté řádky zůstávají ve stromu.

Lze zobrazit jedno dítě skryté podsestavy a ponechat ostatní skrytá. Nastavení
rodiče zruší předchozí výjimky potomků; nové díly v přepočtené podsestavě dědí
stav předka. Kopie stejného souboru se rozlišují úplnou cestou id.

Checkboxy ukazují **ruční** stav. Šedé názvy a bubliny s počtem zobrazených dílů
popisují skutečný pohled, tedy i omezení izolací. Text stavu, problémy a cesty
ke zdrojům zůstávají dostupné. H při psaní do pole dál zapisuje písmeno.

Skrýt/zobrazit nemění přiblížení ani směr kamery. **F** vměstná viditelné díly;
příkaz nese název Vměstnat, pokud je aktivní některé omezení viditelnosti.
Je možné skrýt vše. Prázdný pohled má stále dostupný strom i Zobrazit vše.

## Kombinace s izolací

Izolace je další omezení: ručně skryté díly neodkryje. Zcela skrytou komponentu
je třeba nejdřív zobrazit checkboxem nebo H, než ji lze izolovat.

**Ukončit izolaci** v nabídce Zobrazení nebo pod šipkou u tlačítka Izolovat
obnoví předchozí rozsah pohledu a zachová ruční viditelnost. Změny checkboxů
provedené během izolace se zachovají. **Zobrazit vše (Ctrl+Shift+I, na Macu
Cmd+Shift+I)** vyčistí oba druhy omezení a vrátí celek do záběru.

## Data a životnost

Jde o stav okna, mimo recept a historii. Skrývání nezmění polohy, geometrii,
výběr komponenty ani rozepsané hodnoty. Výběr ploch pro přidání vazby se vyčistí.
Skryté plochy se nedají převzít ze starého výběru ani odkrýt přes zvýraznění.
Při omezeném pohledu se plochy vazeb nezvýrazňují a editor nabídne Zobrazit vše.

Součty, kontroly, kusovník, uložení i STEP používají celý výsledek sestavy.
Titulek a souhrn rozlišují počet viditelných dílů od součtů za celek.

Přepočet, úpravy, Zpět/Znovu i Uložit jako zachovají stav podle id existujících
komponent. Odstranění komponenty zahodí její pravidla viditelnosti; Zpět ji
obnoví s výchozí viditelností. Úspěšné otevření či založení jiného dokumentu
viditelnost vynuluje. Stav se neukládá do souboru ani profilu. Formát a závislosti
se nemění.

## Ověření

Regrese ověřují fyzický objem a světovou obálku filtrovaných kopií, checkboxy
a mezistav podsestavy, dědění při změně zdroje, samostatné zobrazení dítěte,
kombinaci s izolací, uchování rozepsané polohy i vazby, historii, uložení a
import úplného STEP. Funkční testy bez obrazovky používají skutečný sizeHint;
kompaktní rozměry ověřuje nativní balíček, protože Windows offscreen používá
náhradní široké písmo (viz P7.12).

Nativní self-test kontroluje sedm ovládacích tlačítek v okně 1024/960. Skutečný
checkbox, H a tlačítko skrývání musí změnit AIS 6→5→6 těles se správným objemem
a bez změny kamery. Ruční skrývání s izolací projde 5→1→5 a prázdný pohled
0→6 přes Zobrazit vše. Recept, historie, výběr a rozepsané pole se zachovají.

Místní protokoly a snímky patří do `out/p7-assembly-visibility/`; úplné výsledky
macOS/Windows a stažených balíčků do implementačního PR. P7.4 (autorská přejímka)
zůstává otevřená.

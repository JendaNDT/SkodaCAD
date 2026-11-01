# P7.15 – průhlednost vybraného dílu

Datum: **1. 11. 2026**. Navazuje na samostatnou viditelnost P7.14.

## Ovládání

Ve stromu nebo ve 3D vyber komponentu. **Průhledná komponenta (T)** v pravém
panelu a stejný příkaz v nabídce **Zobrazení** přepínají průhlednost **70 %**.
Klávesa T při psaní do pole dál zadává písmeno. Hlavní lišta se nerozšiřuje.

U podsestavy se přepíná celá větev, včetně aktuálně skrytých dílů. Lze potom
samostatně vrátit vybrané dítě k plnému vzhledu. Mezistav přepínače rodiče
znamená, že jsou průhledné jen některé díly; klik sjednotí celou větev na
průhlednou, další klik na plnou. Změna rodiče ruší výjimky potomků. Dvě kopie
stejného souboru mají vlastní nastavení podle úplné cesty id.

Kurzíva názvů ve stromu upozorňuje na průhlednost alespoň části větve, bublina
uvádí přesný stav a souhrn počet průhledných z aktuálně viditelných dílů.
Zaškrtávátka ve stromu nadále ovládají pouze viditelnost.

**Zobrazení → Zrušit průhlednost všech dílů** vrátí plný vzhled. Zachová
izolaci i ručně skryté díly. **Zobrazit vše** naopak obnoví viditelnost a
průhlednost zachová. Při skrytí a opětovném zobrazení se vzhled obnoví.

Průhledná geometrie zůstává vybíratelná, včetně ploch pro vazby. Průhlednost
nemění pořadí výběru: pokud přední plocha překáží výběru vnitřní, skryj její
komponentu pomocí H nebo stromu.
Při průhledném pohledu se výběr a najetí myší zvýrazňují obrysem, aby barevná
výplň nezakrývala vnitřek. Po vypnutí průhlednosti se běžné zvýraznění obnoví.

## Data a životnost

Jde o stav okna, mimo recept, historii a profil. Přepnutí zachová kameru,
komponentu, skutečný výběr ploch/hran, rozepsanou polohu i vazbu. Objem,
hmotnost, kontroly, kusovník, uložený JSON a STEP se nemění.

Přepočet, úpravy, Zpět/Znovu a Uložit jako zachovávají pravidla existujících id.
Nové děti zdědí pravidlo předka. Odstranění zahodí pravidla odstraněné větve;
Zpět vrátí komponentu s výchozím plným vzhledem. Zrušené či neúspěšné otevření
stav zachová. Úspěšné otevření nebo založení dokumentu jej vyčistí.
Formát souboru a závislosti se nemění.

## Vykreslení a ověření

Prohlížeč používá custom materiál částí stávajícího AIS_ColoredShape.
Při přepnutí samotného vzhledu nepřidává ani neodstraňuje geometrii a nemění
kontejner výběru. RecomputePrsOnly obnovuje prezentaci; Redisplay by navíc
přepočítal výběr ([zdroj OCCT](https://github.com/Open-Cascade-SAS/OCCT/blob/V7_9_0/src/AIS/AIS_InteractiveContext.cxx)).
Reset mění jen průhlednost, zachová vlastní barvy. Při obnovení viditelnosti
nebo přepočtu dostane nová prezentace vzhled jen aktuálně viditelných částí.
Požadavek před připravením nativní plochy se přenáší v čekající prezentaci.

Regrese ověřují dvě umístěné kopie s fyzickým objemem a obálkou, nezávislé
podsestavy, mezistav, dědění, skryté větve, izolaci, historii, životnost,
uložení a opětovný import úplného STEP. Test prohlížeče čte skutečný materiál
AIS, nikoli jen uložené volby GUI.

Nativní self-test obou balíčků klikne na skutečnou plochu, stiskne T a ověří
zachování téhož AIS, materiál 70 %, neprůhlednou sousední komponentu, skutečný
výběr a rozepsané pole. Vybere také průhlednou plochu. Přes checkbox projde
70→0→70 % a porovná oba vykreslené obrazy při stejné kameře. Ověří objem,
skrývání, izolaci a reset vzhledu bez zrušení izolace. Stávající kontrola
lišty při 1024/960 zůstává aktivní.
Také přepne checkbox přes QAccessible toggle a ověří skutečný materiál.
Průchod macOS odhalil, že AX přepínání nevysílá clicked; propojení proto
používá změnu stavu a blokuje signály při synchronizaci ovládacích prvků.

Protokoly a snímky patří do `out/p7-assembly-transparency/`. Úplné výsledky
macOS/Windows a stažených balíčků patří do implementačního PR.
P7.4 (autorská přejímka) zůstává otevřená.

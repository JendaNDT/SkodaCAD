# P4.3 — první vazby kót

Tato etapa připravuje ukládání a přepočet vybraných kót. Nejde zatím o hotový
výkres ani export PDF/DXF a neprohlašuje se soulad s výkresovou normou.

## Uložení a kompatibilita

Formát modelu 25 přidává nepovinný objekt `drawing`. Starší verze 1–24 se nadále
načítají bez změny obsahu. Dokud model nemá výkres, uloží se ve verzi 24;
s výkresem se uloží ve verzi 25, kterou starší aplikace nemusí otevřít. Výkres je součástí stejného
souboru jako model a prochází Zpět/Znovu. Nahrazení modelu asistentem zachovává
výkres uživatele, který ovšem může následně obsahovat neplatné vazby.

List (`paper`, A4/A3) a měřítko (`scale`) výkresu se od 29. 10. 2026 opravdu ukládají:
dřív se zapisovaly jen výchozí A4 a 1:1 a okno je po otevření nečetlo. Volba se ukládá
jako jeden krok Zpět, náhled i export ji berou z modelu. Výchozí A4 a 1:1 u modelu bez
výkresu výkres nezakládá. Formát se nemění (pole patří do verze 25).

Každá kóta má samostatné id a druh. Celkový rozměr s osou X/Y/Z znamená obálku
celého dílu. Vzdálenost podporuje dvě rovnoběžné rovinné plochy pocházející z jednoduchých
obdélníkových vysunutí v základních rovinách. Průměr nebo poloměr podporuje
pouze válcovou plochu otvoru
vytvořeného odebráním jediné kruhové skici v základní rovině. Ukládá se původ
plochy a otisk historie prvků, nikoli index plochy ani ručně zadaná hodnota.
Kóta se přepočítává při změně hodnot parametrů; pokud se změní recept prvků,
původ zmizí či odpovídá více válcům, je neplatná a vyžaduje nové určení.
Při chybném nebo zastaralém výpočtu nevznikne žádná hodnota. Je to úmyslně
konzervativní první podmnožina, nikoliv obecné sledování topologické identity.

## Zbývá

Doplnit kótování konkrétních hran a dalších druhů vzdáleností, vazby dalších typů prvků,
umístění kót v pohledech, dokončení listu, řez, PDF/DXF a nezávislou kontrolu
exportu i tisku. Výstup smí vzniknout teprve po ověření všech vazeb a úplnosti
modelu; při neplatné nebo nejednoznačné kótě nesmí být potichu vypuštěna.

Pracovní náhled listu rozmisťuje tři pohledy podle zvoleného formátu a měřítka.
Kóty, řez ani popisové pole v něm zatím nejsou; náhled není exportní výkres.

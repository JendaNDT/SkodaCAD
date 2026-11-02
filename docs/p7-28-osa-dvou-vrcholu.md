# P7.28 – osa ze dvou vrcholů

Datum: **2. 11. 2026**. Navazuje na P7.24–27. Formát, závislosti a jádro otáčení beze změny.

## Ovládání

Vyber více komponent. V panelu **Společné otočení [°]** zvol **Dva vrcholy → Vybrat
osu ve 3D**. První klik na skutečný vrchol určí bod osy a zobrazí oranžovou značku.
Druhý klik na jiný vrchol určí kladný směr **od prvního ke druhému**. Vrcholy mohou
ležet na různých viditelných dílech, v podsestavě i na pevném nebo nevybraném dílu.
Kliky nemění výběr otáčených komponent, podklady vazeb, model ani historii.

První klik ponechá dosavadní osu. Teprve druhý platný vrchol nahradí snímek osy.
Stejné místo (i jiný topologický vrchol) a vzdálenost nejvýše **0,0000001 mm** se
odmítnou; výběr dál čeká na druhý bod. Klik mimo vrchol také ponechá první bod.
Esc, pravý klik nebo **Zrušit výběr** odstraní rozpracovaný pár i značku a zachovají
předchozí osu. Totéž platí při změně výběru, sestavy, viditelnosti nebo režimu.

Při zapnutých rotačních rukojetích se zobrazí prstenec a šipka **Osa dvou vrcholů**.
**Obrátit směr osy** neguje směr bez změny bodu, dílů, polí nebo historie. Číselný
úhel a tažení používají tutéž osu, nastavený krok a jeden Zpět/Znovu pro celý pohyb.

Pár vrcholů má vlastní snímek, oddělený od osy válce, hrany a kolmice k ploše.
Snímek zůstává v souřadnicích sestavy, není asociativní a neukládá se do souboru.
Po změně reference jej vyber znovu. Přepnutí na XYZ obnoví dosavadní nastavení
středu včetně rozepsaných hodnot. Omezení natočení zadaného výrazem zůstává:
přesné ±Z je zachovají, šikmá osa vyžaduje číselné natočení; výběr i obrácení jsou dostupné.

## Přesnost a ověření

Viewer aktivuje VERTEX detekci a čte přesné `BRep_Tool.Pnt_s` již umístěných vrcholů,
nikoli bod sítě AIS. Kotva je první bod, směr normalizovaný rozdíl druhý minus první.
Nekonečné souřadnice, nevhodné tvary a neurčitý směr se odmítají. První bod má
samostatnou neselektovatelnou značku; ta se vždy odstraní při dokončení nebo zrušení.
Okno před převzetím ověří generaci, revizi, druh osy a příslušnost **obou** vrcholů
k aktuálně viditelným kopiím. Starý výsledek ani dokončení starého výběru nesmí
přepsat osu nebo vypnout nový výběr. Druh prstence i potvrzení je `vertices`.

Regrese ověřují světové souřadnice šikmých dílů, pořadí kliků, různá tělesa a podsestavy,
shodné body s odlišnou topologií, mez tolerance, DPI 1/1,25/2, opakované chybné kliky,
odstranění značky všemi cestami, zachování výběru a historie, nezávislé snímky, výrazy,
staré požadavky i staré tažení po dvojím obrácení. Skutečné vrcholy otočených těles a
AIS náhled porovnávají s nezávislou rotací, včetně jednoho Zpět/Znovu.

Nativní scénář klikne na vrchol šikmé třetí nožičky a na vrchol čtvrté nožičky.
Nezávislé očekávání používá známé lokální souřadnice a umístění obou dílů. První klik
nevytvoří osu, opakovaný klik na něj se odmítne, druhý platný klik převezme přesný pár.
Scénář ověří AIS výběr, podklady vazeb, kameru, pole, historii, tři skutečná obrácení,
Enter90, myš30, matici náhledu, těžiště, průhlednost 35/85 % a Zpět/Znovu. Rušení
zkouší i po prvním vrcholu. Současně běží scénáře válce, hrany a kolmice.
Evidence je v `out/p7-two-vertex-axis/`; úplné výsledky patří do PR.

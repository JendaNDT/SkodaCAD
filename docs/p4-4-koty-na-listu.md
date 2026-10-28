# Kóty v pracovním náhledu listu

První uživatelský náhled ukazuje již uložené kóty celkových rozměrů, vzdáleností
rovnoběžných ploch a podporovaných kruhových otvorů. Hodnota je rozměrem modelu
v milimetrech, délka obrázku se řídí měřítkem listu. Pomocné čáry celkového
rozměru vycházejí z krajních bodů viditelných hran; u vzdálenosti z vybraných
ploch. Kruh musí být v daném pohledu viditelný a jednoznačný.

U vybrané kóty lze zvolit pohled, stranu a odstup v milimetrech na listu;
umístění se ukládá spolu s kótou a podporuje Zpět/Znovu. Starší kóty bez
nastavení dostanou výchozí polohu. Nepoužitelná vazba, chybějící či nevhodný
pohled, neviditelný kruh nebo umístění mimo stránku se v náhledu vypíše jako
upozornění. Žádná taková kóta se nevykreslí s odhadnutou hodnotou. Náhled
nesmí kombinovat geometrii a hodnoty z různých verzí modelu.

Jde stále o pracovní náhled, nikoli hotový výrobní výkres. Autor má zkontrolovat
čitelnost a překrytí kót; automatická kontrola kolizí textu a dalších čar zatím
není hotová. Kótování hran, další typy modelových vazeb, řez, kompletní
popisové pole, export PDF/DXF a nezávislé ověření výstupu teprve navazují.
Formát zůstává verzí 25; umístění je nepovinné pole uvnitř uložené kóty.
